"""Analytics conserve actual records and explain the rules without predictions."""
import copy
import json

import pytest

from cloud.config import WORKSPACE
from public_app.analytics import customer_analytics, heuristic_drivers, intervention_matrix, portfolio_analytics
from public_app.repository import SnapshotReader
from public_app.ui.charts import action_mix_spec, driver_spec, exposure_spec, relationship_timeline_spec, signal_spec


@pytest.fixture
def reader():
    return SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")


def test_exposure_conserves_active_balances_and_action_mix_covers_every_customer(reader):
    profiles = reader.portfolio_profiles()
    result = portfolio_analytics(profiles)
    assert result["total_exposure"] == sum(p["metrics"]["total_outstanding"] for p in profiles)
    assert sum(row["balance"] for row in result["exposure_by_dpd"]) == result["total_exposure"]
    assert sum(row["customers"] for row in result["action_mix"]) == len(profiles)
    assert sum(row["share"] for row in result["action_mix"]) == pytest.approx(1)
    assert result["governance"]["actions_for_review"] == 4
    assert result["governance"]["actions_with_citations"] == 4
    assert result["governance"]["contact_protected"] == 2
    assert result["governance"]["complete_profiles"] == 19


def test_exposure_buckets_each_loan_instead_of_using_customer_worst_dpd(reader):
    view = reader.customer360("C0002")
    current_balance = view["loans"][0]["outstanding"]
    overdue = {**view["loans"][0], "loan_id": "TEST-OVERDUE", "outstanding": 200, "current_dpd": 40}
    closed = {**overdue, "loan_id": "TEST-CLOSED", "status": "CLOSED", "outstanding": 99999}
    view["loans"].extend([overdue, closed])
    rows = {row["bucket"]: row for row in portfolio_analytics([view])["exposure_by_dpd"]}
    assert rows["Current"]["balance"] == current_balance
    assert rows["31–60 days overdue"]["balance"] == 200
    assert rows["Current"]["customers"] == rows["31–60 days overdue"]["customers"] == 1


def test_driver_contributions_reproduce_fixture_scores_and_cite_real_sources(reader):
    for view in reader.portfolio_profiles():
        result = customer_analytics(view)
        assert result["heuristic_priority_points"] == result["reported_priority_points"]
        actual_ids = {i["interaction_id"] for i in view["interactions"]}
        assert all(set(driver["evidence_ids"]) <= actual_ids for driver in result["heuristic_drivers"])
        assert result["prediction_validated"] is False
    ananya = customer_analytics(reader.customer360("C0002"))
    assert ananya["heuristic_priority_points"] == 65
    assert next(d for d in ananya["heuristic_drivers"] if "Transfer" in d["driver"])["points"] == 40


def test_future_and_invalid_records_do_not_appear_as_observed_history(reader):
    view = reader.customer360("C0002")
    baseline = customer_analytics(view)
    future = {**view["interactions"][0], "interaction_id": "FUTURE", "ts": "2027-01-01T00:00:00Z", "sentiment": -1}
    invalid = {**future, "interaction_id": "INVALID", "ts": "not-a-date"}
    view["interactions"].extend([future, invalid])
    view["payments"].extend([{**view["payments"][0], "due_date": "2027-01-01"},
                             {**view["payments"][0], "due_date": "invalid"}])
    result = customer_analytics(view)
    assert result["conversation_history"] == baseline["conversation_history"]
    assert result["payment_history"] == baseline["payment_history"]
    assert result["freshness"]["future_records"] == 1
    assert result["freshness"]["invalid_timestamps"] == 1
    assert result["excluded_future_payments"] == result["invalid_payment_dates"] == 1
    assert heuristic_drivers(view) == baseline["heuristic_drivers"]


def test_history_uses_policy_reference_and_the_last_twelve_calendar_months(reader):
    view = reader.customer360("C0002")
    view["payments"] = [
        {**view["payments"][0], "due_date": "2025-10-31"},
        {**view["payments"][0], "due_date": "2025-11-01"},
        {**view["payments"][0], "due_date": "2026-10-01"},
        {**view["payments"][0], "due_date": "2026-10-06"},
    ]
    result = customer_analytics(view)
    assert [row["month"] for row in result["payment_history"]] == ["2025-11-01", "2026-10-01"]
    assert result["excluded_future_payments"] == 1
    assert result["freshness"]["as_of"] == view["metrics"]["evaluation_time"]


def test_alerts_preserve_contact_protection_and_never_imply_validated_fairness(reader):
    result = portfolio_analytics(reader.portfolio_profiles())
    neha = next(a for a in result["alerts"] if a["customer_id"] == "C0004")
    assert neha["kind"] == "Consent" and neha["level"] == "Protected"
    assert neha["action_code"] == "NO_ACTION"
    assert result["governance"]["fairness_evaluated"] is False
    assert result["governance"]["prediction_validated"] is False
    assert sum(row["customers"] for row in result["segment_coverage"]) == 20
    assert all(0 <= row["review_share"] <= 1 for row in result["segment_coverage"])


def test_intervention_matrix_executes_rules_preserves_scope_and_never_changes_source(reader):
    view = reader.customer360("C0003")
    original = copy.deepcopy(view)
    rows = {row["scenario"]: row for row in intervention_matrix(view)}
    assert rows["job_loss"]["after_action_code"] == rows["opt_out"]["after_action_code"] == "NO_ACTION"
    assert rows["job_loss"]["offer_change"] == "Suppressed"
    assert rows["job_loss"]["hardship_flag"] is True
    assert rows["competitor_offer"]["after_action_code"] == "TOPUP_PREAPPROVAL_CALL"
    assert all("C0003" in row["evidence_id"] and row["simulation_only"] and not row["database_write"] for row in rows.values())
    assert view == original


def test_analytics_require_an_explicit_reference_and_support_empty_portfolios(reader):
    view = reader.customer360("C0002")
    view["metrics"]["evaluation_time"] = "invalid"
    with pytest.raises(ValueError, match="explicit policy evaluation"):
        customer_analytics(view)
    result = portfolio_analytics([])
    assert result["total_exposure"] == 0 and result["governance"]["customers"] == 0
    assert all(row["share"] == 0 for row in result["action_mix"])


def test_chart_specs_are_valid_json_and_leave_analytics_unchanged(reader):
    alt = pytest.importorskip("altair", reason="Chart schema validation requires the public website dependencies.")

    portfolio = portfolio_analytics(reader.portfolio_profiles())
    customer = customer_analytics(reader.customer360("C0002"))
    before = copy.deepcopy((portfolio, customer))
    for builder, data in [(exposure_spec, portfolio), (action_mix_spec, portfolio),
                          (signal_spec, portfolio), (driver_spec, customer), (relationship_timeline_spec, customer)]:
        spec = builder(data)
        json.dumps(spec, allow_nan=False)
        chart = alt.VConcatChart.from_dict(spec) if "vconcat" in spec else alt.Chart.from_dict(spec)
        chart.to_dict(validate=True)
    assert (portfolio, customer) == before


def test_timeline_plots_dated_evidence_instead_of_inventing_outcomes(reader):
    result = customer_analytics(reader.customer360("C0002"))
    spec = relationship_timeline_spec(result)
    points = [row for row in spec["data"]["values"] if row["kind"] == "conversation"]
    assert {p["evidence_id"] for p in points} == {i["evidence_id"] for i in result["conversation_history"]}
    assert all(p["when"] == p["timestamp"] for p in points)
    assert "probability" not in json.dumps(spec).lower()


def test_chart_renderers_support_the_public_streamlit_runtime():
    pytest.importorskip("streamlit", reason="Runtime rendering requires public website dependencies.")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string("""
from cloud.config import WORKSPACE
from public_app.repository import SnapshotReader
from public_app.analytics import portfolio_analytics, customer_analytics, intervention_matrix
from public_app.ui.charts import render_portfolio_charts, render_relationship_timeline, render_driver_chart, render_intervention_matrix, render_governance
reader = SnapshotReader(WORKSPACE / 'public_app/synthetic_snapshot.json')
portfolio = portfolio_analytics(reader.portfolio_profiles())
customer = customer_analytics(reader.customer360('C0002'))
render_portfolio_charts(portfolio)
render_relationship_timeline(customer)
render_driver_chart(customer)
render_intervention_matrix(intervention_matrix(reader.customer360('C0003')))
render_governance(portfolio)
""").run()
    assert not app.exception
    assert len(app.get("vega_lite_chart")) == 5
    assert len(app.dataframe) == 2
    assert any("not a trained prediction" in caption.value for caption in app.caption)
