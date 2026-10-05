"""Policy and state-machine acceptance checks for complete local journeys."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from samvaad.models import ActionError, Actor


def test_seed_has_twenty_distinct_customers_and_reconciled_hero_views(service):
    customers = service.list_customers()
    assert len(customers) == 20
    assert len({c["customer_id"] for c in customers}) == 20
    for customer_id in ("C0001", "C0002", "C0003"):
        view = service.customer360(customer_id)
        assert view["customer"]["customer_id"] == customer_id
        assert view["loans"] and view["payments"] and view["interactions"]
        assert all(i["customer_id"] == customer_id for i in view["interactions"])
        assert view["metrics"]["total_outstanding"] == pytest.approx(
            sum(float(loan["outstanding"]) for loan in view["loans"] if loan["status"] == "ACTIVE")
        )


@pytest.mark.parametrize(
    "customer_id,action_code,approval_role",
    [
        ("C0001", "HARDSHIP_RESTRUCTURE_CALL", "AUTO"),
        ("C0002", "RETENTION_RATE_MATCH_CALL", "MANAGER"),
        ("C0003", "TOPUP_PREAPPROVAL_CALL", "CREDIT"),
    ],
)
def test_hero_recommendations_include_customer_scoped_evidence(
    service, analyst, customer_id, action_code, approval_role
):
    action = service.recommend(customer_id, analyst)
    assert action["action_code"] == action_code
    assert action["approval_role"] == approval_role
    assert action["rationale"] and action["script"] and action["evidence_ids"]
    evidence = {i["interaction_id"] for i in service.customer360(customer_id)["interactions"]}
    assert set(action["evidence_ids"]) <= evidence


def test_queueing_same_recommendation_is_idempotent(service, analyst):
    baseline_count = len(service.actions())
    first = service.recommend("C0002", analyst)
    second = service.recommend("C0002", analyst)
    assert first["action_id"] == second["action_id"]
    assert len(service.actions()) == baseline_count
    assert sum(a["customer_id"] == "C0002" for a in service.actions()) == 1


def test_retention_requires_manager_and_executes_once(
    service, queued_retention, manager, runner
):
    action_id = queued_retention["action_id"]
    with pytest.raises(ActionError):
        service.execute_action(action_id, runner)
    assert not service.offers("C0002")
    service.approve_action(action_id, manager)
    audit_count = len(service.audit(action_id=action_id))
    service.approve_action(action_id, manager)
    assert len(service.audit(action_id=action_id)) == audit_count
    result = service.execute_action(action_id, runner, mode="simulate", outcome="ACCEPT")
    assert result["status"] == "COMPLETED"
    assert result["execution_mode"] == "simulate"
    assert result["outcome"] == "ACCEPT"
    offers = service.offers("C0002")
    audit_count = len(service.audit(action_id=action_id))
    repeated = service.execute_action(action_id, runner, mode="simulate", outcome="ACCEPT")
    assert repeated["status"] == "COMPLETED"
    assert service.offers("C0002") == offers
    assert len(service.audit(action_id=action_id)) == audit_count


def test_topup_requires_credit_approval_before_creating_expiring_offer(
    service, queued_topup, manager, credit, runner
):
    action_id = queued_topup["action_id"]
    with pytest.raises(ActionError):
        service.approve_action(action_id, manager)
    with pytest.raises(ActionError):
        service.execute_action(action_id, runner)
    assert not service.offers("C0003")
    service.approve_action(action_id, credit)
    service.execute_action(action_id, runner, mode="simulate", outcome="ACCEPT")
    offers = service.offers("C0003")
    assert len(offers) == 1
    offer = offers[0]
    assert offer["token"]
    assert service.get_offer(offer["token"])["customer_id"] == "C0003"
    expiry = datetime.fromisoformat(offer["expires_at"].replace("Z", "+00:00"))
    with pytest.raises(ActionError) as exc:
        service.get_offer(offer["token"], now=expiry + timedelta(seconds=1))
    assert exc.value.code == "OFFER_EXPIRED"


@pytest.mark.parametrize("actor_id", ["meera", "farah", "local-runner", "kavya"])
def test_wrong_identity_cannot_approve_retention(service, queued_retention, actor_id):
    with pytest.raises(ActionError):
        service.approve_action(queued_retention["action_id"], service.resolve_actor(actor_id))
    retained = next(a for a in service.actions() if a["action_id"] == queued_retention["action_id"])
    assert retained["status"] == "PENDING_APPROVAL"


@pytest.mark.parametrize(
    "forged_actor", [Actor("evil", "MANAGER"), Actor("meera", "MANAGER")]
)
def test_forged_identity_and_role_escalation_are_rejected(service, queued_retention, forged_actor):
    with pytest.raises(ActionError):
        service.approve_action(queued_retention["action_id"], forged_actor)
    retained = next(a for a in service.actions() if a["action_id"] == queued_retention["action_id"])
    assert retained["approved_by"] is None


@pytest.mark.parametrize("actor_id", ["meera", "arjun", "kavya"])
def test_interactive_users_cannot_bypass_approved_runner(
    service, queued_topup, credit, actor_id
):
    service.approve_action(queued_topup["action_id"], credit)
    with pytest.raises(ActionError):
        service.execute_action(queued_topup["action_id"], service.resolve_actor(actor_id))
    assert not service.offers("C0003")


def test_revoking_consent_cancels_pending_and_approved_actions(
    service, analyst, manager, runner
):
    pending = service.recommend("C0003", analyst)
    approved = service.recommend("C0002", analyst)
    service.approve_action(approved["action_id"], manager)
    service.revoke_consent("C0002", analyst)
    service.revoke_consent("C0003", analyst)
    by_id = {a["action_id"]: a for a in service.actions()}
    for action in (pending, approved):
        assert by_id[action["action_id"]]["status"] == "CANCELLED"
        with pytest.raises(ActionError):
            service.execute_action(action["action_id"], runner)
    assert not service.offers()
    for customer_id in ("C0002", "C0003"):
        assert not service.customer360(customer_id)["customer"]["consent_calls"]


def test_catalogue_cap_is_dynamic_and_existing_approval_is_stale(
    service, analyst, manager, runner, admin
):
    first = service.recommend("C0002", analyst)
    service.approve_action(first["action_id"], manager)
    service.update_catalogue("RETENTION_RATE_MATCH_CALL", admin, max_rate_cut_bps=25)
    with pytest.raises(ActionError) as exc:
        service.execute_action(first["action_id"], runner)
    assert exc.value.code == "STALE_APPROVAL"
    assert not service.offers("C0002")
    fresh = service.recommend("C0002", analyst)
    assert fresh["offer"]["rate_cut_bps"] <= 25
    assert fresh["action_id"] != first["action_id"]


def test_catalogue_changes_are_admin_only(service, analyst):
    with pytest.raises(ActionError):
        service.update_catalogue("TOPUP_PREAPPROVAL_CALL", analyst, max_topup_amount=99999999)


def test_opt_out_response_is_deduplicated_and_persisted(service, queued_topup, credit, runner):
    action_id = queued_topup["action_id"]
    service.approve_action(action_id, credit)
    service.execute_action(action_id, runner, mode="simulate", outcome="NO_ANSWER")
    service.record_response(action_id, "OPT_OUT", "evt-optout-1", runner)
    count = len(service.audit(action_id=action_id))
    service.record_response(action_id, "OPT_OUT", "evt-optout-1", runner)
    assert len(service.audit(action_id=action_id)) == count
    assert not service.customer360("C0003")["customer"]["consent_calls"]


def test_hardship_callback_has_no_automatic_financial_offer(service, analyst, runner):
    action = service.recommend("C0001", analyst)
    assert action["status"] == "APPROVED"
    result = service.execute_action(action["action_id"], runner, mode="simulate", outcome="CALLBACK")
    assert result["outcome"] == "CALLBACK"
    assert not service.offers("C0001")


def test_simulation_is_available_outside_live_contact_hours(service, queued_retention, manager, runner):
    service.approve_action(queued_retention["action_id"], manager)
    # 03:30 IST is outside the fictional 08:00-19:00 contact window.
    overnight = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)
    result = service.execute_action(queued_retention["action_id"], runner, mode="simulate", now=overnight)
    assert result["status"] == "COMPLETED"


def test_unknown_offer_token_does_not_expose_customer_data(service):
    with pytest.raises(ActionError):
        service.get_offer("not-an-offer-token")


def test_retry_gap_and_three_attempt_limit(service, queued_retention, manager, runner):
    action_id = queued_retention["action_id"]
    service.approve_action(action_id, manager)
    start = datetime.now(timezone.utc)
    first = service.execute_action(action_id, runner, outcome="NO_ANSWER", now=start)
    assert first["attempts"] == 1
    with pytest.raises(ActionError) as exc:
        service.execute_action(action_id, runner, outcome="NO_ANSWER", now=start + timedelta(hours=3))
    assert exc.value.code == "RETRY_TOO_SOON"
    second = service.execute_action(action_id, runner, outcome="NO_ANSWER", now=start + timedelta(hours=4))
    assert second["attempts"] == 2
    final = service.execute_action(action_id, runner, outcome="NO_ANSWER", now=start + timedelta(hours=8))
    assert final["attempts"] == 3
    assert final["status"] == "EXHAUSTED"
    with pytest.raises(ActionError):
        service.execute_action(action_id, runner, outcome="NO_ANSWER", now=start + timedelta(hours=12))
    retained = next(a for a in service.actions() if a["action_id"] == action_id)
    assert retained["attempts"] == 3
    assert not service.offers("C0002")


def test_competing_local_workers_execute_once(service, queued_topup, credit, runner):
    action_id = queued_topup["action_id"]
    service.approve_action(action_id, credit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.execute_action, action_id, runner) for _ in range(2)]
        results = [future.result() for future in futures]
    assert all(result["status"] == "COMPLETED" for result in results)
    retained = next(a for a in service.actions() if a["action_id"] == action_id)
    assert retained["attempts"] == 1
    assert len(service.offers("C0003")) == 1


def test_expired_recommendations_cannot_be_approved_or_executed(
    service, queued_retention, queued_topup, manager, credit, runner, monkeypatch
):
    import samvaad.service as service_module

    service.approve_action(queued_retention["action_id"], manager)
    future = datetime.now(timezone.utc) + timedelta(days=8)
    monkeypatch.setattr(service_module, "utcnow", lambda: future)
    with pytest.raises(ActionError) as approval_error:
        service.approve_action(queued_topup["action_id"], credit)
    assert approval_error.value.code == "ACTION_EXPIRED"
    with pytest.raises(ActionError) as execution_error:
        service.execute_action(queued_retention["action_id"], runner)
    assert execution_error.value.code == "ACTION_EXPIRED"
    assert not service.offers()


def test_new_hardship_signal_supersedes_pending_growth_offer(
    service, queued_topup, analyst, runner
):
    action_id = queued_topup["action_id"]
    assert queued_topup["status"] == "PENDING_APPROVAL"
    service.add_interaction(
        "C0003", "Borrower: I lost my job this week and cannot afford my EMI.",
        channel="CALL_IN", actor=analyst,
    )
    view = service.customer360("C0003")
    assert view["metrics"]["dpd"] == 0
    assert view["metrics"]["hardship_flag"] is True
    current = service.recommend("C0003", analyst)
    assert current["action_code"] == "NO_ACTION"
    old = next(a for a in service.actions() if a["action_id"] == action_id)
    assert old["status"] == "CANCELLED"
    with pytest.raises(ActionError):
        service.execute_action(action_id, runner)
    assert not service.offers("C0003")
    assert any("supersed" in event["event"].lower() for event in service.audit(action_id=action_id))
