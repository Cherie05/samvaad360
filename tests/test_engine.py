"""Financial exclusions and timestamp boundaries independent of the web UI."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from samvaad.engine import CATALOGUE, compute_metrics, decide_customer
from samvaad.signals import extract_signals


NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def fixtures():
    customer = {"customer_id": "EDGE1", "full_name": "Edge Borrower", "monthly_income": 100000,
                "consent_calls": True, "consent_marketing": True, "dnd": False}
    loans = [{"loan_id": "L1", "status": "ACTIVE", "current_dpd": 0, "emi": 10000,
              "outstanding": 240000, "relationship_months": 24, "interest_rate": 14.0}]
    payments = [{"loan_id": "L1", "status": "PAID", "due_date": (NOW - timedelta(days=30 * month)).date().isoformat()}
                for month in range(12, 0, -1)]
    return customer, loans, payments


def interaction(text, days=5, interaction_id="I1"):
    return {"interaction_id": interaction_id, "ts": (NOW - timedelta(days=days)).isoformat(), **extract_signals(text)}


def decide(customer, loans, payments, interactions, catalogue=None):
    metrics = compute_metrics(customer, loans, payments, interactions, reference=NOW)
    return decide_customer(customer, metrics, interactions, deepcopy(CATALOGUE) if catalogue is None else catalogue)


def test_hardship_suppresses_growth_even_with_topup_interest():
    customer, loans, payments = fixtures()
    loans[0]["current_dpd"] = 9
    result = decide(customer, loans, payments, [interaction("Borrower: I lost my job and cannot afford payments."),
                                             interaction("Borrower: Do you have top-up loan options?", interaction_id="I2")])
    assert result["action_code"] == "HARDSHIP_RESTRUCTURE_CALL"
    assert not result["offer"]


@pytest.mark.parametrize("flag", ["dnd", "consent_calls", "consent_marketing"])
def test_contact_and_marketing_exclusions_suppress_topup(flag):
    customer, loans, payments = fixtures()
    customer[flag] = flag == "dnd"
    result = decide(customer, loans, payments, [interaction("Borrower: I want a top-up loan.")])
    assert result["action_code"] == "NO_ACTION"


def test_missing_income_requires_manual_review():
    customer, loans, payments = fixtures()
    customer["monthly_income"] = None
    result = decide(customer, loans, payments, [interaction("Borrower: I want a top-up loan.")])
    assert result["action_code"] == "NO_ACTION"
    assert "review" in result["rationale"].lower()


@pytest.mark.parametrize("days", [100, -1])
def test_old_or_future_interest_is_not_eligible(days):
    customer, loans, payments = fixtures()
    result = decide(customer, loans, payments, [interaction("Borrower: I want a top-up loan.", days=days)])
    assert result["action_code"] == "NO_ACTION"


def test_topup_cap_comes_from_catalogue():
    customer, loans, payments = fixtures()
    catalogue = deepcopy(CATALOGUE)
    topup = next(row for row in catalogue if row["action_code"] == "TOPUP_PREAPPROVAL_CALL")
    topup["max_topup_amount"] = 75000
    result = decide(customer, loans, payments, [interaction("Borrower: I want a top-up loan.")], catalogue)
    assert result["offer"]["amount"] == 75000


def test_inactive_catalogue_entry_cannot_be_selected():
    customer, loans, payments = fixtures()
    catalogue = deepcopy(CATALOGUE)
    next(row for row in catalogue if row["action_code"] == "TOPUP_PREAPPROVAL_CALL")["active"] = False
    result = decide(customer, loans, payments, [interaction("Borrower: I want a top-up loan.")], catalogue)
    assert result["action_code"] == "NO_ACTION"


def test_retention_evidence_and_competitor_rate_use_current_customer_signals():
    customer, loans, payments = fixtures()
    interactions = [
        interaction("Borrower: Brightline Bank offered to take over my loan at 5%.", days=120, interaction_id="OLD"),
        interaction("Borrower: Brightline Bank offered to take over my loan at 10.75%. Why should I stay?", interaction_id="CURRENT"),
    ]
    result = decide(customer, loans, payments, interactions)
    assert result["action_code"] == "RETENTION_RATE_MATCH_CALL"
    assert result["evidence_ids"] == ["CURRENT"]
    assert result["offer"]["competitor_rate"] == 10.75


def test_recent_bounce_window_counts_all_active_loans_not_last_three_rows():
    customer, loans, _ = fixtures()
    loans.append({**loans[0], "loan_id": "L2"})
    payments = [
        {"loan_id": loan_id, "status": "BOUNCED" if days == 70 and loan_id == "L1" else "PAID",
         "due_date": (NOW - timedelta(days=days)).date().isoformat()}
        for days in (70, 40, 10) for loan_id in ("L1", "L2")
    ]
    metrics = compute_metrics(customer, loans, payments, [], reference=NOW)
    assert "BOUNCES_3M_1" in metrics["reason_codes"]


def test_late_history_older_than_twelve_months_does_not_fail_current_eligibility():
    customer, loans, _ = fixtures()
    payments = [
        {"loan_id": "L1", "status": status, "due_date": (NOW - timedelta(days=days)).date().isoformat()}
        for days, status in ((400, "BOUNCED"), (70, "PAID"), (40, "PAID"), (10, "PAID"))
    ]
    metrics = compute_metrics(customer, loans, payments, [], reference=NOW)
    assert metrics["late_12m"] == 0
    assert metrics["topup_eligible"] is True
