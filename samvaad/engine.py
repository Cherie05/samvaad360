"""Catalogue-driven, deterministic decisioning for synthetic lending data."""
import math
from datetime import datetime, timezone

CATALOGUE = [
    {"action_code": "HARDSHIP_RESTRUCTURE_CALL", "title": "Supportive hardship callback", "priority": 1,
     "approval_role": "AUTO", "channel": "SIMULATED_CONTACT", "active": True,
     "max_rate_cut_bps": None, "max_topup_amount": None, "version": 1},
    {"action_code": "GENTLE_REMINDER_CALL", "title": "Gentle payment reminder", "priority": 2,
     "approval_role": "AUTO", "channel": "SIMULATED_CONTACT", "active": True,
     "max_rate_cut_bps": None, "max_topup_amount": None, "version": 1},
    {"action_code": "RETENTION_RATE_MATCH_CALL", "title": "Capped retention rate review", "priority": 3,
     "approval_role": "MANAGER", "channel": "SIMULATED_CONTACT", "active": True,
     "max_rate_cut_bps": 100, "max_topup_amount": None, "version": 1},
    {"action_code": "TOPUP_PREAPPROVAL_CALL", "title": "Conditional top-up invitation", "priority": 4,
     "approval_role": "CREDIT", "channel": "SIMULATED_EMAIL", "active": True,
     "max_rate_cut_bps": None, "max_topup_amount": 500000, "version": 1},
]


def _recent(interaction: dict, days: int, reference: datetime) -> bool:
    try:
        timestamp = datetime.fromisoformat(interaction["ts"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return 0 <= (reference - timestamp).total_seconds() <= days * 86400
    except (ValueError, KeyError, TypeError):
        return False


def compute_metrics(customer: dict, loans: list, payments: list, interactions: list,
                    reference: datetime | None = None) -> dict:
    reference = reference or datetime.now(timezone.utc)
    active = [loan for loan in loans if loan["status"] == "ACTIVE"]
    active_ids = {loan["loan_id"] for loan in active}
    completed = [p for p in payments if p["loan_id"] in active_ids and p["status"] != "PENDING"]
    recent = [i for i in interactions if _recent(i, 30, reference)]
    hardship = [i for i in interactions if _recent(i, 45, reference) and i["intent"] == "financial hardship"]
    transfer = [i for i in interactions if _recent(i, 60, reference) and i["intent"] == "balance transfer or foreclosure"]
    topup = [i for i in interactions if _recent(i, 90, reference) and i["intent"] == "top-up or new loan interest"]
    complaint = any(i["intent"] == "complaint about service or rate" for i in recent)
    dpd = max((loan["current_dpd"] for loan in active), default=0)
    total_emi = sum(loan["emi"] for loan in active)
    income = customer.get("monthly_income", 0)
    foir = total_emi / income if income and income > 0 else None
    quality = []
    if not active:
        quality.append("NO_ACTIVE_LOAN")
    if foir is None:
        quality.append("MISSING_INCOME")
    if not completed:
        quality.append("MISSING_PAYMENT_HISTORY")
    tenure = min((loan["relationship_months"] for loan in active), default=0)
    def within_payment_window(payment, days):
        try:
            due = datetime.fromisoformat(payment["due_date"]).date()
            return 0 <= (reference.date() - due).days <= days
        except (KeyError, TypeError, ValueError):
            return False
    late = sum(p["status"] in {"LATE", "BOUNCED"} and within_payment_window(p, 365) for p in completed)
    bounces = sum(p["status"] == "BOUNCED" and within_payment_window(p, 90) for p in completed)
    on_time = sum(p["status"] == "PAID" for p in completed) / len(completed) if completed else 0
    sentiment = sum(i["sentiment"] for i in recent) / len(recent) if recent else 0
    max_rate = max((loan["interest_rate"] for loan in active), default=0)
    collections = min(1, .30 * min(dpd / 30, 1) + .20 * min(bounces / 2, 1)
                      + .20 * bool(hardship) + .15 * max(-sentiment, 0))
    churn = min(1, .40 * bool(transfer) + .20 * complaint + .20 * max(-sentiment, 0)
                + .20 * (tenure >= 24 and max_rate >= 13))
    eligible = bool(not quality and dpd == 0 and late == 0 and tenure >= 12 and foir < .5 and not hardship)
    # Illustrative affordability sizing only; not a real underwriting decision.
    amount = max(0, math.floor((.5 * income - total_emi) * 24 / 10000) * 10000) if foir is not None else 0
    reason_codes = []
    for flag, label in [(dpd > 0, f"DPD_{dpd}"), (bounces > 0, f"BOUNCES_3M_{bounces}"),
                        (bool(hardship), "HARDSHIP"), (bool(transfer), "BT_INTENT"),
                        (sentiment < -.3, "NEGATIVE_SENTIMENT"), (bool(topup), "TOPUP_INTENT")]:
        if flag:
            reason_codes.append(label)
    return {"dpd": dpd, "dpd_now": dpd, "active_loans": len(active), "evaluation_time": reference.isoformat(),
            "total_outstanding": sum(loan["outstanding"] for loan in active), "total_emi": total_emi,
            "foir": round(foir, 3) if foir is not None else None,
            "collections_risk": round(collections, 2), "churn_risk": round(churn, 2),
            "topup_propensity": round(.4 * on_time + .3 * bool(topup) + .3 * (1 - min(foir or 0, 1)), 2),
            "topup_eligible": eligible, "topup_amount": amount, "max_rate": max_rate,
            "late_12m": late, "bounces_3m": bounces, "tenure_months": tenure, "sentiment_30d": round(sentiment, 2),
            "on_time_ratio": round(on_time, 3), "hardship_flag": bool(hardship),
            "bt_intent": bool(transfer), "topup_intent": bool(topup),
            "reason_codes": reason_codes, "data_quality_flags": quality}


def decide_customer(customer: dict, metrics: dict, interactions: list, catalogue: list) -> dict:
    base = {"action_code": "NO_ACTION", "approval_role": None, "offer": {}, "reason_codes": [],
            "evidence_ids": [], "rationale": "No eligible action under the current demo policy.", "script": ""}
    if not customer.get("consent_calls") or customer.get("dnd"):
        return {**base, "rationale": "Contact is suppressed by consent or DND preferences."}
    if metrics["data_quality_flags"]:
        return {**base, "rationale": "Manual review is required: " + ", ".join(metrics["data_quality_flags"])}
    eligible = {
        "HARDSHIP_RESTRUCTURE_CALL": metrics["hardship_flag"] and 1 <= metrics["dpd"] <= 60,
        "GENTLE_REMINDER_CALL": 1 <= metrics["dpd"] <= 30 and not metrics["hardship_flag"],
        "RETENTION_RATE_MATCH_CALL": metrics["churn_risk"] >= .6 and metrics["late_12m"] == 0 and not metrics["hardship_flag"],
        "TOPUP_PREAPPROVAL_CALL": metrics["topup_eligible"] and metrics["topup_intent"] and customer.get("consent_marketing")
                                  and metrics["topup_amount"] >= 50000,
    }
    candidates = [c for c in catalogue if c["active"] and eligible.get(c["action_code"], False)]
    if not candidates:
        return base
    pick = min(candidates, key=lambda c: (c["priority"], c["action_code"]))
    code = pick["action_code"]
    intent_for_code = {"HARDSHIP_RESTRUCTURE_CALL": "financial hardship",
                       "RETENTION_RATE_MATCH_CALL": "balance transfer or foreclosure",
                       "TOPUP_PREAPPROVAL_CALL": "top-up or new loan interest"}
    reference = datetime.fromisoformat(metrics.get("evaluation_time", datetime.now(timezone.utc).isoformat()))
    window = {"HARDSHIP_RESTRUCTURE_CALL": 45, "RETENTION_RATE_MATCH_CALL": 60, "TOPUP_PREAPPROVAL_CALL": 90}.get(code, 30)
    evidence = sorted([i for i in interactions if i["intent"] == intent_for_code.get(code) and _recent(i, window, reference)],
                      key=lambda i: i["ts"], reverse=True)[:3]
    if not evidence and code == "GENTLE_REMINDER_CALL":
        evidence = interactions[:1]
    ids = [i["interaction_id"] for i in evidence]
    name = customer["full_name"].split()[0]
    offer = {}
    if code == "RETENTION_RATE_MATCH_CALL":
        competitor_rate = next((i["entities"].get("offered_rate") for i in evidence if i["entities"].get("offered_rate")), None)
        gap = max(0, round((metrics["max_rate"] - competitor_rate) * 100)) if competitor_rate else 25
        cut = min(pick["max_rate_cut_bps"] or 0, math.floor(gap / 25) * 25)
        if cut < 25:
            return base
        offer = {"rate_cut_bps": cut, "current_rate": metrics["max_rate"],
                 "proposed_rate": round(metrics["max_rate"] - cut / 100, 2), "competitor_rate": competitor_rate}
        rationale = f"{name} requested foreclosure and mentioned a competitor. A {cut} bps capped retention proposal needs manager approval."
        script = f"{name}, a manager-reviewed proposal could reduce your current rate by {cut} basis points. We can explain the terms and record your preference."
    elif code == "TOPUP_PREAPPROVAL_CALL":
        amount = min(metrics["topup_amount"], pick["max_topup_amount"] or 0)
        if amount < 50000:
            return base
        offer = {"amount": amount, "topup_amount": amount, "indicative_rate": 12.5,
                 "tenure_months": 36, "processing_fee_pct": 1, "currency": "INR"}
        rationale = f"{name} expressed top-up interest and meets the illustrative repayment and affordability rules. Credit approval is required for this conditional invitation."
        script = f"{name}, after credit review, we can share a conditional top-up invitation of up to Rs {amount:,}. The terms require further checks; this demo does not offer a real loan."
    elif code == "HARDSHIP_RESTRUCTURE_CALL":
        request = "job-loss conversation" if any(i.get("entities", {}).get("hardship_reason") == "job loss" for i in evidence) else "hardship request"
        rationale = f"{name}'s {request} and overdue payment support a helpful officer callback."
        script = f"{name}, an officer can discuss support options with you. This callback request does not promise a payment break, a rate change, or loan approval."
    else:
        rationale = f"{name} has a recently overdue payment without an identified hardship request. A respectful payment reminder is available."
        script = f"{name}, this is a gentle reminder about a pending payment. If you already paid or need support, we can ask an officer to review it."
    if ids:
        rationale += " " + " ".join(f"[{id_}]" for id_ in ids)
    return {"action_code": code, "title": pick["title"], "approval_role": pick["approval_role"],
            "channel": pick["channel"], "offer": offer, "reason_codes": metrics["reason_codes"],
            "evidence_ids": ids, "rationale": rationale, "script": script,
            "catalogue_version": pick["version"], "priority": pick["priority"]}
