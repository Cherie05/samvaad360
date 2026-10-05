"""Decision comparisons remain evidence-backed, scoped and reversible."""
import copy

import pytest

from cloud.config import WORKSPACE
from public_app.insights import explain_action, priority_queue, simulate_interaction, summarize_portfolio
from public_app.repository import SnapshotReader


@pytest.fixture
def reader():
    return SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")


def test_portfolio_matches_individual_profiles_and_dashboard_counts(reader):
    profiles = reader.portfolio_profiles()
    summary = summarize_portfolio(profiles)
    assert summary["customers"] == 20 and summary["contact_blocked"] == 2
    assert summary["actions_ready"] == 4 and summary["hardship_cases"] == 1 and summary["retention_cases"] == 1
    for cid in ["C0001", "C0002", "C0003", "C0004", "C0007"]:
        bulk = next(p for p in profiles if p["customer"]["customer_id"] == cid)
        assert bulk["metrics"] == reader.customer360(cid)["metrics"]
        assert bulk["decision"] == reader.customer360(cid)["decision"]
    assert priority_queue(profiles)[0]["customer_id"] == "C0001"


def test_new_hardship_replaces_reminder_without_changing_stored_view(reader):
    view = reader.customer360("C0007")
    original = copy.deepcopy(view)
    result = simulate_interaction(view, "job_loss")
    assert result["before"]["action_code"] == "GENTLE_REMINDER_CALL"
    assert result["after"]["action_code"] == "HARDSHIP_RESTRUCTURE_CALL"
    assert result["added_evidence"]["interaction_id"] in result["after"]["evidence_ids"]
    assert result["changed"] and not result["database_write"] and view == original


def test_hardship_stops_growth_and_optout_overrides_every_offer(reader):
    view = reader.customer360("C0003")
    hardship = simulate_interaction(view, "job_loss")
    assert hardship["after"]["action_code"] == "NO_ACTION" and hardship["metrics"]["hardship_flag"]
    assert not hardship["after"]["offer"]
    assert simulate_interaction(view, "opt_out")["after"]["action_code"] == "NO_ACTION"
    assert reader.customer360("C0003")["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"


def test_explanation_cites_real_evidence_and_labels_interest_estimate(reader):
    view = reader.customer360("C0002")
    explanation = explain_action(view)
    assert explanation["evidence"][0]["id"] in view["decision"]["evidence_ids"]
    assert explanation["estimated_annual_interest_difference"] == view["metrics"]["total_outstanding"] * .01
    assert explanation["offer_fields"] and any(c["label"] == "Review owner" and c["status"] == "Required" for c in explanation["checks"])
    assert any(c["status"] == "Blocked" for c in explain_action(reader.customer360("C0004"))["checks"])


def test_unknown_scenario_cannot_inject_a_policy_change(reader):
    with pytest.raises(ValueError):
        simulate_interaction(reader.customer360("C0003"), "override_credit_approval")
