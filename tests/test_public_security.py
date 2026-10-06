"""Adversarial public admission, atomic spend reservations and snapshot isolation."""
import hashlib
import hmac
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from cloud.config import WORKSPACE
from public_app.repository import (DemoError, GuardedSnapshotReader, IDENTITY_SQL,
                                   PublicReader, ReadSession, ReviewSandbox, SnapshotReader)
from public_app.security import (BudgetExceeded, GuardUnavailable, PublicGuard,
                                 QueryPermit, VisitorIdentity, resolve_visitor)
from test_public_cloud import Connection


class Clock:
    def __init__(self, now=1760000000):
        self.now = now
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def guard(tmp_path):
    clock = Clock()
    return PublicGuard(tmp_path / "guard.db", clock=clock), clock


def signed_headers(address="198.51.100.7", stamp=1760000000, secret="private-edge-signing-key-for-tests-only"):
    signature = hmac.new(secret.encode(), f"v1\n{address}\n{stamp}".encode(), hashlib.sha256).hexdigest()
    return {"X-Samvaad-Client-IP": address, "X-Samvaad-Timestamp": str(stamp), "X-Samvaad-Signature": signature}


@pytest.mark.parametrize("address", ["198.51.100.7", "127.0.0.1", "2001:db8::1", "::ffff:198.51.100.9"])
def test_unverified_streamlit_ip_and_forwarded_headers_do_not_create_new_identities(address):
    visitor = resolve_visitor(context_ip=address, headers={"X-Forwarded-For": address, "Forwarded": "for=" + address})
    assert visitor == VisitorIdentity()


def test_only_fresh_hmac_attestation_from_configured_ingress_creates_ip_identity():
    secret = "private-edge-signing-key-for-tests-only"
    verified = resolve_visitor(headers=signed_headers(secret=secret), edge_secret=secret, now=1760000000)
    assert verified.verified and verified.address == "198.51.100.7" and verified.source == "verified-edge-ip"
    assert not resolve_visitor(headers=signed_headers(), edge_secret="different-unknown-key-that-is-32-characters", now=1760000000).verified
    assert not resolve_visitor(headers=signed_headers(stamp=1759999900), edge_secret=secret, now=1760000000).verified
    assert not resolve_visitor(headers=signed_headers(stamp=1760000100), edge_secret=secret, now=1760000000).verified
    assert not resolve_visitor(headers=signed_headers(), edge_secret="too-short", now=1760000000).verified


@pytest.mark.parametrize("mutation", [
    {"X-Samvaad-Client-IP": "198.51.100.8"},
    {"X-Samvaad-Client-IP": "198.51.100.7, 10.0.0.1"},
    {"X-Samvaad-Client-IP": "invalid-ip"},
    {"X-Samvaad-Timestamp": "1760000000.0"},
    {"X-Samvaad-Signature": "z" * 64},
    {"X-Samvaad-Signature": "\u00df" * 64},
    {"x-samvaad-client-ip": "198.51.100.8"},
])
def test_modified_duplicate_or_malformed_signed_headers_share_unverified_bucket(mutation):
    headers = {**signed_headers(), **mutation}
    visitor = resolve_visitor(headers=headers, edge_secret="private-edge-signing-key-for-tests-only", now=1760000000)
    assert visitor == VisitorIdentity()


def test_streamlit_repeated_header_values_are_not_trusted():
    from streamlit.runtime.context import StreamlitHeaders
    headers = StreamlitHeaders([*signed_headers().items(), ("X-Samvaad-Client-IP", "198.51.100.8")])
    assert not resolve_visitor(headers=headers, edge_secret="private-edge-signing-key-for-tests-only", now=1760000000).verified


def test_action_burst_refills_without_clock_rollback_bypass(guard):
    limiter, clock = guard
    visitor = VisitorIdentity()
    assert all(limiter.admit(visitor, kind="action").allowed for _ in range(30))
    blocked = limiter.admit(visitor, kind="action")
    assert not blocked.allowed and blocked.retry_after == 2
    clock.advance(-50)
    assert not limiter.admit(visitor, kind="action").allowed
    clock.advance(52)
    assert limiter.admit(visitor, kind="action").allowed
    assert not limiter.admit(visitor, kind="action").allowed


def test_verified_ips_have_separate_quota_but_unknown_ips_cannot_rotate(guard):
    limiter, _ = guard
    first = VisitorIdentity("198.51.100.1", True, "verified-edge-ip")
    second = VisitorIdentity("198.51.100.2", True, "verified-edge-ip")
    assert all(limiter.admit(first, kind="action").allowed for _ in range(15))
    assert not limiter.admit(first, kind="action").allowed
    assert limiter.admit(second, kind="action").allowed
    for _ in range(30):
        assert limiter.admit(limiter.visitor(context_ip="203.0.113.1"), kind="action").allowed
    assert not limiter.admit(limiter.visitor(context_ip="203.0.113.2"), kind="action").allowed


def test_parallel_requests_cannot_overspend_burst(guard):
    limiter, _ = guard
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: limiter.admit(VisitorIdentity(), kind="action"), range(80)))
    assert sum(r.allowed for r in results) == 30
    assert limiter.stats()["requests_blocked"] == 50


def test_bucket_capacity_is_bounded_and_addresses_are_not_persisted(tmp_path):
    limiter = PublicGuard(tmp_path / "guard.db", max_buckets=3, clock=Clock())
    assert limiter.admit(VisitorIdentity("198.51.100.1", True), kind="action").allowed
    assert limiter.admit(VisitorIdentity("198.51.100.2", True), kind="action").allowed
    assert limiter.admit(VisitorIdentity("198.51.100.3", True), kind="action").reason == "identity-capacity"
    assert b"198.51.100." not in limiter.path.read_bytes()
    assert "198.51.100." not in json.dumps(limiter.stats())


def test_failed_ip_request_does_not_deduct_other_visitors_global_tokens(guard):
    limiter, _ = guard
    first = VisitorIdentity("198.51.100.1", True)
    for _ in range(15):
        assert limiter.admit(first, kind="action").allowed
    for _ in range(150):
        assert not limiter.admit(first, kind="action").allowed
    assert limiter.admit(VisitorIdentity("198.51.100.2", True), kind="action").allowed


def test_budget_is_reserved_before_work_and_persisted_across_guard_instances(guard):
    limiter, clock = guard
    permit = limiter.reserve_queries(5)
    assert permit.remaining == 5
    second = PublicGuard(limiter.path, clock=clock)
    assert second.stats()["application_statements_hour"] == 5
    with pytest.raises(BudgetExceeded):
        second.reserve_queries(5)
    assert second.stats()["application_statements_hour"] == 5
    clock.advance(3600)
    second.reserve_queries(5)
    assert second.stats()["application_statements_day"] == 10


def test_trusted_configured_volume_path_retains_budget_and_explicit_path_wins(tmp_path, monkeypatch):
    persisted = tmp_path / "mounted-data" / "public-guard.db"
    monkeypatch.setenv("SAMVAAD_PUBLIC_GUARD_PATH", str(persisted))
    first = PublicGuard(clock=Clock())
    first.reserve_queries(5)
    # A recreated application process/cache reads the same volume reservation.
    second = PublicGuard(clock=Clock())
    assert second.path == persisted and second.stats()["application_statements_day"] == 5
    with pytest.raises(BudgetExceeded):
        second.reserve_queries(5)
    isolated = PublicGuard(tmp_path / "isolated-verification.db", clock=Clock())
    assert isolated.stats()["application_statements_day"] == 0
    isolated.reserve_queries(5)
    assert first.stats()["application_statements_day"] == 5


def test_parallel_budget_reservations_charge_at_most_the_configured_cap(guard):
    limiter, _ = guard
    def reserve(_):
        try:
            limiter.reserve_queries(5)
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(reserve, range(25)))
    assert sum(results) == 1 and limiter.stats()["application_statements_hour"] == 5


def test_daily_budget_remains_bounded_when_hourly_windows_advance(tmp_path):
    clock = Clock(now=1760054400)  # UTC midnight, no day change during the test.
    limiter = PublicGuard(tmp_path / "guard.db", clock=clock)
    accepted = 0
    for _ in range(20):
        try:
            limiter.reserve_queries(5)
            accepted += 1
        except BudgetExceeded:
            pass
        clock.advance(3600)
    assert accepted == 12 and limiter.stats()["application_statements_day"] == 60


def test_permit_cannot_execute_more_than_its_reserved_statements():
    permit = QueryPermit(5)
    with ThreadPoolExecutor(max_workers=8) as pool:
        def spend(_):
            try:
                permit.before_execute()
                return True
            except BudgetExceeded:
                return False
        results = list(pool.map(spend, range(20)))
    assert sum(results) == 5 and permit.remaining == 0


def test_corrupt_or_lost_store_fails_closed_for_requests_and_query_work(guard):
    limiter, _ = guard
    with sqlite3.connect(limiter.path) as connection:
        connection.execute("DROP TABLE guard_buckets")
        connection.execute("DROP TABLE guard_windows")
    assert limiter.admit(VisitorIdentity()).reason == "protection-unavailable"
    with pytest.raises(GuardUnavailable):
        limiter.reserve_queries()


def test_invalid_circuit_metadata_fails_closed_before_any_cloud_reservation(guard):
    limiter, _ = guard
    with sqlite3.connect(limiter.path) as connection:
        connection.execute("UPDATE guard_metadata SET value='corrupt' WHERE name='circuit-until'")
    with pytest.raises(GuardUnavailable):
        limiter.reserve_queries()


def test_circuit_breaker_is_persisted_and_blocks_without_charging_again(guard):
    limiter, clock = guard
    limiter.reserve_queries(5)
    limiter.refresh_failed()
    assert limiter.stats()["circuit_open"] and limiter.stats()["circuit_retry_seconds"] == 60
    with pytest.raises(BudgetExceeded, match="circuit-open"):
        PublicGuard(limiter.path, clock=clock).reserve_queries()
    assert limiter.stats()["application_statements_day"] == 5
    clock.advance(60)
    limiter.refresh_failed()
    assert limiter.stats()["circuit_retry_seconds"] == 120
    limiter.refresh_succeeded()
    assert not limiter.stats()["circuit_open"]


@pytest.fixture
def cached(guard):
    limiter, clock = guard
    fallback = SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")
    connections = []
    def loader(permit):
        connection = Connection()
        connections.append(connection)
        permit.before_execute()
        with connection.cursor() as cursor:
            cursor.execute(IDENTITY_SQL)
        return PublicReader(ReadSession(connection, budget=permit))
    return GuardedSnapshotReader(loader, fallback, limiter, clock=clock), connections, limiter, clock


def test_all_customer_evidence_review_reads_share_one_closed_five_statement_refresh(cached):
    reader, connections, limiter, _ = cached
    assert reader.is_live
    for cid in [c["customer_id"] for c in reader.customers()]:
        reader.customer360(cid)
        reader.answer(cid, "What is the recommendation?")
    review = ReviewSandbox([], reader)
    request = review.request("C0003")
    review.review(request, "APPROVED_IN_SIMULATION", "Synthetic isolated approval")
    assert len(connections) == 1 and connections[0].closed
    assert len(connections[0].calls) == 5
    assert limiter.stats()["application_statements_day"] == 5
    assert reader.source_status()["visitor_queries"] == 0
    with pytest.raises(DemoError):
        reader.answer("C0003", "Use live AI", cortex=True)
    with pytest.raises(DemoError):
        reader.rows("SELECT 1")


def test_parallel_first_visitors_trigger_exactly_one_refresh(cached):
    reader, connections, _, _ = cached
    with ThreadPoolExecutor(max_workers=16) as pool:
        views = list(pool.map(lambda _: reader.customer360("C0003"), range(80)))
    assert len(views) == 80 and len(connections) == 1 and len(connections[0].calls) == 5


def test_returned_snapshot_cannot_be_mutated_by_another_visitor(cached):
    reader, _, _, _ = cached
    view = reader.customer360("C0003")
    view["customer"]["consent_calls"] = False
    view["decision"]["action_code"] = "INVENTED"
    all_views = reader.portfolio_profiles()
    all_views[0]["customer"]["full_name"] = "MUTATED"
    assert reader.customer360("C0003")["customer"]["consent_calls"]
    assert reader.customer360("C0003")["decision"]["action_code"] != "INVENTED"
    assert reader.customers()[0]["full_name"] != "MUTATED"


def test_new_refresh_runs_only_after_hour_and_budget_denial_retains_dated_snapshot(cached):
    reader, connections, limiter, clock = cached
    reader.customers()
    clock.advance(3599)
    reader.customer360("C0003")
    assert len(connections) == 1
    clock.advance(1)
    reader.customer360("C0003")
    assert len(connections) == 2 and limiter.stats()["application_statements_day"] == 10
    # Simulate another host-local consumer spending the remaining day allowance.
    with sqlite3.connect(limiter.path) as connection:
        connection.execute("UPDATE guard_windows SET used=64 WHERE name='day'")
    clock.advance(3600)
    assert reader.is_live
    status = reader.source_status()
    assert len(connections) == 2 and status["stale"] and status["refresh_status"] == "query-budget-reached"
    assert status["snapshot_age_seconds"] == 3600


def test_no_budget_or_failed_guard_never_invokes_cloud_loader(guard):
    limiter, clock = guard
    limiter.reserve_queries(5)
    fallback = SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")
    reader = GuardedSnapshotReader(lambda _: pytest.fail("Cloud loader must not run"), fallback, limiter, clock=clock)
    assert not reader.is_live and len(reader.customers()) == 20
    assert reader.source_status()["source"] == "bundled-synthetic-snapshot"


def test_unavailable_guard_store_falls_back_before_connecting(guard):
    limiter, clock = guard
    with sqlite3.connect(limiter.path) as connection:
        connection.execute("DROP TABLE guard_windows")
    fallback = SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")
    reader = GuardedSnapshotReader(lambda _: pytest.fail("Cloud loader must not run"), fallback, limiter, clock=clock)
    assert not reader.is_live and reader.source_status()["refresh_status"] == "protection-unavailable"


def test_backend_errors_are_charged_once_without_secret_messages_or_retry_storm(guard, caplog):
    limiter, clock = guard
    calls = []
    def failing_loader(_):
        calls.append(1)
        raise RuntimeError("PRIVATE_CREDENTIAL_MUST_NOT_APPEAR")
    reader = GuardedSnapshotReader(failing_loader, SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json"), limiter, clock=clock)
    for _ in range(100):
        reader.customers()
    assert len(calls) == 1 and limiter.stats()["application_statements_day"] == 5
    assert reader.source_status()["circuit_open"]
    assert "PRIVATE_CREDENTIAL_MUST_NOT_APPEAR" not in caplog.text + json.dumps(reader.source_status())


def test_public_refresh_interval_cannot_be_lowered_by_configuration(cached):
    reader, _, guard, _ = cached
    with pytest.raises(ValueError):
        GuardedSnapshotReader(reader.loader, reader.fallback, guard, refresh_seconds=1)
