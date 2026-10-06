"""The private outbox must acknowledge a durable, version-checked projection."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from cloud.config import CloudConfig, CloudError
from cloud.relationship_sync import (
    DATABASE, ROLE, MAX_STATEMENTS, PrivateProjectionSink, SyncError,
    connect_private_sink, sync_once, validate_event,
)
from samvaad.models import DEMO_ACTORS


def event(version=1, *, customer_id="C-onboard-001", now=None):
    now = now or datetime.now(timezone.utc)
    payload = {"customer": {"customer_id": customer_id, "full_name": "अनन्या Rao", "phone": "+919000000001"},
               "loans": [], "payments": [], "interactions": [],
               "relationship": {"lifecycle_stage": "ACTIVE", "cases": []}}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"event_id": "event-00000001", "customer_id": customer_id, "version": version,
            "event_hash": hashlib.sha256(encoded.encode()).hexdigest(), "payload": payload,
            "lease_token": "secret-lease", "lease_expires_at": (now + timedelta(seconds=900)).isoformat()}


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.closed = False

    def execute(self, query, parameters=None, timeout=None):
        con = self.connection
        con.calls.append((query, parameters, timeout))
        if con.fail_on and con.fail_on in query:
            raise RuntimeError("provider-password=private-customer@example.test")
        if "CURRENT_ROLE" in query:
            self.rows = [(con.role, con.database, con.warehouse)]
        elif query == "BEGIN":
            con.pending = deepcopy(con.rows)
        elif query.startswith("MERGE"):
            customer_id, version, digest, _, _ = parameters
            existing = con.pending.get(customer_id, [])
            if not existing:
                con.pending[customer_id] = [(version, digest)]
            else:
                con.pending[customer_id] = [(version, digest) if version > stored[0] else stored for stored in existing]
        elif query.startswith("SELECT VERSION"):
            self.rows = con.pending.get(parameters[0], [])
        elif query == "COMMIT":
            con.rows = con.pending
            con.pending = None
            con.committed += 1
        elif query == "ROLLBACK":
            con.pending = None
            con.rolled_back += 1
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True
        self.connection.closed_cursors += 1


class Connection:
    def __init__(self, *, role=ROLE, database=DATABASE, warehouse="SAMVAAD_XS", rows=None, fail_on=None):
        self.role, self.database, self.warehouse = role, database, warehouse
        self.rows = rows or {}
        self.pending = None
        self.fail_on = fail_on
        self.calls = []
        self.closed_cursors = self.committed = self.rolled_back = 0
        self.closed = False

    def cursor(self):
        return Cursor(self)

    def close(self):
        self.closed = True
        self.pending = None


class Queue:
    def __init__(self, events, connection=None):
        self.events = events
        self.connection = connection
        self.claims = []
        self.completions = []
        self.fail_first_ack = False
        self.expired = False

    def claim_outbox(self, actor, *, limit, lease_seconds):
        self.claims.append((actor, limit, lease_seconds))
        return self.events[:limit]

    def complete_outbox(self, event_id, lease_token, actor, error=None):
        if self.expired:
            raise SyncError("LEASE_EXPIRED")
        if self.fail_first_ack and error is None:
            self.fail_first_ack = False
            raise RuntimeError("local acknowledgement unavailable")
        if error is None and self.connection:
            assert self.connection.pending is None, "A local ACK cannot precede Snowflake COMMIT."
            assert self.connection.committed > 0
        self.completions.append((event_id, lease_token, error))


def test_version_checked_private_projection_commits_before_ack():
    pending = event()
    connection = Connection()
    queue = Queue([pending], connection)
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.status == "COMPLETED"
    assert report.acknowledged == 1 and report.statements == 5
    assert connection.rows[pending["customer_id"]] == [(1, pending["event_hash"])]
    assert connection.closed and connection.closed_cursors == 5
    merge, params, timeout = connection.calls[2]
    assert "RELATIONSHIP" in merge and "PUBLIC_DEMO" not in merge
    assert "अनन्या" not in merge and "+919000000001" not in merge
    assert "अनन्या" in params[-1] and timeout == 15
    assert "private-customer" not in json.dumps(report.as_dict())
    assert queue.claims[0][2] == 900


@pytest.mark.parametrize("kwargs,code", [
    ({"role": "SAMVAAD_PUBLIC_READER"}, "PRIVATE_ROLE_REQUIRED"),
    ({"database": "OTHER"}, "PRIVATE_DATABASE_REQUIRED"),
    ({"warehouse": None}, "WAREHOUSE_REQUIRED"),
])
def test_identity_gate_does_not_claim_any_source_event(kwargs, code):
    connection = Connection(**kwargs)
    queue = Queue([event()])
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.status == "FAILED" and report.error_code == code
    assert not queue.claims and not queue.completions
    assert connection.closed and report.statements == 1


@pytest.mark.parametrize("change,code", [
    ({"version": True}, "INVALID_EVENT"),
    ({"version": 0}, "INVALID_EVENT"),
    ({"customer_id": "C';DROP TABLE customers;--"}, "INVALID_EVENT"),
    ({"event_id": "tiny"}, "INVALID_EVENT"),
    ({"event_hash": "0" * 64}, "HASH_MISMATCH"),
    ({"payload": {"customer": {"customer_id": "OTHER"}}}, "INVALID_PAYLOAD"),
])
def test_invalid_events_cannot_reach_sql(change, code):
    pending = event()
    pending.update(change)
    connection = Connection()
    queue = Queue([pending])
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.error_code == code and report.retried == 1
    assert report.statements == 1 and not connection.rows


def test_nonfinite_payload_rejected_before_hashing_or_mutation():
    pending = event()
    pending["payload"]["customer"]["monthly_income"] = float("nan")
    with pytest.raises(SyncError, match="INVALID_PAYLOAD"):
        validate_event(pending)


def test_projection_is_not_downgraded_by_an_older_retry():
    pending = event(version=1)
    connection = Connection(rows={pending["customer_id"]: [(4, "newerhash")]})
    queue = Queue([pending], connection)
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.acknowledged == report.superseded == 1
    assert connection.rows[pending["customer_id"]] == [(4, "newerhash")]


def test_same_version_conflict_rolls_back_and_retries_without_ack():
    pending = event()
    connection = Connection(rows={pending["customer_id"]: [(1, "differenthash")]})
    queue = Queue([pending])
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.error_code == "PROJECTION_CONFLICT" and report.acknowledged == 0
    assert connection.rolled_back == 1 and connection.committed == 0
    assert queue.completions[0][2] == "PROJECTION_CONFLICT"


def test_duplicate_snowflake_key_is_detected_despite_unenforced_constraint():
    pending = event(version=3)
    before = [(1, "first"), (2, "second")]
    connection = Connection(rows={pending["customer_id"]: before})
    queue = Queue([pending])
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.error_code == "DUPLICATE_PROJECTION"
    assert connection.rows[pending["customer_id"]] == before
    assert connection.rolled_back == 1 and report.acknowledged == 0


def test_expired_lease_cannot_write_or_acknowledge():
    pending = event(now=datetime.now(timezone.utc) - timedelta(seconds=1000))
    connection = Connection()
    queue = Queue([pending])
    queue.expired = True
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.error_code == "LEASE_EXPIRED" and report.unacknowledged == 1
    assert report.statements == 1 and not queue.completions and not connection.rows


def test_commit_without_source_acknowledgement_is_safe_to_retry():
    pending = event()
    connection = Connection()
    first = Queue([pending], connection)
    first.fail_first_ack = True
    report = sync_once(first, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    assert report.acknowledged == 0 and report.retried == 1
    assert len(connection.rows[pending["customer_id"]]) == 1
    second_connection = Connection(rows=deepcopy(connection.rows))
    second = Queue([pending], second_connection)
    again = sync_once(second, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(second_connection))
    assert again.acknowledged == 1
    assert len(second_connection.rows[pending["customer_id"]]) == 1


def test_connector_error_is_sanitized_and_connection_is_closed():
    connection = Connection(fail_on="MERGE")
    queue = Queue([event()])
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection))
    encoded = json.dumps(report.as_dict())
    assert report.error_code == "WORKER_FAILED" and report.retried == 1
    assert "password" not in encoded and "private-customer" not in encoded
    assert connection.closed and connection.rolled_back == 1


def test_statement_budget_is_checked_before_issuing_next_query():
    connection = Connection()
    queue = Queue([event()])
    report = sync_once(queue, DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection, max_statements=1))
    assert report.error_code == "STATEMENT_BUDGET" and report.statements == 1
    assert len(connection.calls) == 1 and report.retried == 1
    with pytest.raises(ValueError):
        PrivateProjectionSink(connection, max_statements=MAX_STATEMENTS + 1)


def test_batch_limit_prevents_unbounded_source_claims():
    connection = Connection()
    with pytest.raises(ValueError):
        sync_once(Queue([]), DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection), limit=6)
    with pytest.raises(ValueError):
        sync_once(Queue([]), DEMO_ACTORS["demo-admin"], PrivateProjectionSink(connection), limit=True)


def test_private_config_must_have_a_named_connection_and_private_database(monkeypatch):
    attempts = []
    monkeypatch.setattr("cloud.relationship_sync.connect", lambda config: attempts.append(config))
    with pytest.raises(CloudError, match="private SAMVAAD_STAGING"):
        connect_private_sink(CloudConfig("relationship-sync", "PUBLIC_DB", "SAMVAAD_XS"))
    assert not attempts


def test_cli_default_does_not_create_or_seed_an_operational_database(tmp_path, capsys):
    from scripts.relationship_sync import main
    missing = tmp_path / "missing.db"
    assert main(["--db", str(missing)]) == 1
    assert not missing.exists()
    assert json.loads(capsys.readouterr().out)["error_code"] == "OPERATIONAL_DB_REQUIRED"


def test_single_writer_lock_rejects_another_writer_on_the_same_host(tmp_path):
    from scripts.relationship_sync import single_writer_lock
    lock_path = tmp_path / "sync.lock"
    with single_writer_lock(lock_path):
        with pytest.raises(CloudError, match="Another relationship sync writer"):
            with single_writer_lock(lock_path):
                pytest.fail("Two workers acquired the same host-local lock")
    with single_writer_lock(lock_path):
        pass


def approved_local_customer(tmp_path):
    from samvaad.service import LocalService
    from samvaad.relationship import RelationshipService
    relationship = RelationshipService(LocalService(tmp_path / "operational.db", seed=False))
    intake = relationship.submit_onboarding({"full_name": "Private Fictional Prospect", "preferred_language": "Hindi",
                                            "identity_review": True, "document_review": True},
                                           DEMO_ACTORS["meera"], "private-intake-0001")
    approved = relationship.review_onboarding(intake["onboarding_id"], "APPROVE", "Synthetic reviewed documents",
                                               DEMO_ACTORS["arjun"])
    return relationship, approved["customer_id"]


def test_real_operational_outbox_hash_contract_and_durable_acknowledgement(tmp_path):
    relationship, customer_id = approved_local_customer(tmp_path)
    connection = Connection()
    report = sync_once(relationship, DEMO_ACTORS["local-runner"], PrivateProjectionSink(connection))
    assert report.acknowledged == 1 and report.status == "COMPLETED"
    assert connection.rows[customer_id][0][0] == 1
    counts = relationship.outbox_status(DEMO_ACTORS["demo-admin"])["counts"]
    assert counts == {"SENT": 1}
    from samvaad.relationship import RelationshipService
    from samvaad.service import LocalService
    reopened = RelationshipService(LocalService(tmp_path / "operational.db", seed=False))
    assert reopened.outbox_status(DEMO_ACTORS["demo-admin"])["counts"] == {"SENT": 1}


def test_real_outbox_exports_one_customer_version_at_a_time(tmp_path):
    relationship, customer_id = approved_local_customer(tmp_path)
    relationship.add_case(customer_id, {"category": "SERVICE", "subject": "Fictional servicing",
                                        "description": "Request a permitted officer follow-up"},
                          DEMO_ACTORS["meera"], "case-after-intake-0001")
    connection = Connection()
    first = sync_once(relationship, DEMO_ACTORS["local-runner"], PrivateProjectionSink(connection))
    assert first.claimed == first.acknowledged == 1
    assert relationship.outbox_status(DEMO_ACTORS["demo-admin"])["counts"] == {"PENDING": 1, "SENT": 1}
    second_connection = Connection(rows=deepcopy(connection.rows))
    second = sync_once(relationship, DEMO_ACTORS["local-runner"], PrivateProjectionSink(second_connection))
    assert second.acknowledged == 1 and second_connection.rows[customer_id][0][0] == 2


def test_cli_inspection_reads_counts_without_claiming_or_connecting(tmp_path, monkeypatch, capsys):
    relationship, _ = approved_local_customer(tmp_path)
    from scripts.relationship_sync import main
    monkeypatch.setattr("scripts.relationship_sync.connect_private_sink",
                        lambda config: pytest.fail("Default inspection attempted a Snowflake connection"))
    assert main(["--db", str(tmp_path / "operational.db")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "NOT_APPLIED" and report["queue_totals"] == {"PENDING": 1}
    assert report["public_demo_updated"] is False
    assert relationship.outbox_status(DEMO_ACTORS["demo-admin"])["counts"] == {"PENDING": 1}
    assert "payload" not in report and "Private Fictional Prospect" not in json.dumps(report)
