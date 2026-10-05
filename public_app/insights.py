"""Portfolio explanations and reversible scenario comparisons using actual rules."""
from __future__ import annotations

import copy
from datetime import datetime

from samvaad.engine import CATALOGUE, compute_metrics, decide_customer
from samvaad.signals import extract_signals

SCENARIOS = {
    "job_loss": ("New hardship conversation", "Customer: I lost my job and cannot pay my EMI. I need support."),
    "competitor_offer": ("Competitor rate offer", "Customer: I want to foreclose my loan and transfer to Brightline Bank. They offered 10.75%."),
    "opt_out": ("Customer withdraws contact consent", "Customer: Do not call me again. Please remove me from your calling list."),
    "topup_interest": ("Customer asks about a top-up", "Customer: I want a top-up loan for my shop renovation. Please explain the terms."),
}


def summarize_portfolio(profiles):
    codes = [p["decision"]["action_code"] for p in profiles]
    return {
        "customers": len(profiles),
        "total_outstanding": sum(p["metrics"]["total_outstanding"] for p in profiles),
        "actions_ready": sum(code != "NO_ACTION" for code in codes),
        "contact_blocked": sum(not p["customer"].get("consent_calls") or p["customer"].get("dnd", False) for p in profiles),
        "hardship_cases": codes.count("HARDSHIP_RESTRUCTURE_CALL"),
        "retention_cases": codes.count("RETENTION_RATE_MATCH_CALL"),
        "priority_count": sum(p["metrics"]["dpd"] > 0 or p["metrics"]["churn_risk"] >= .6 for p in profiles),
    }


def priority_queue(profiles):
    rows = []
    for profile in profiles:
        customer, metrics, decision = profile["customer"], profile["metrics"], profile["decision"]
        code = decision["action_code"]
        priority = "High" if code in {"HARDSHIP_RESTRUCTURE_CALL", "GENTLE_REMINDER_CALL", "RETENTION_RATE_MATCH_CALL"} else "Opportunity" if code == "TOPUP_PREAPPROVAL_CALL" else "Hold" if (not customer.get("consent_calls") or customer.get("dnd") or metrics["data_quality_flags"]) else "Monitor"
        rows.append({"customer_id": customer["customer_id"], "name": customer["full_name"],
            "segment": customer["segment"], "dpd": metrics["dpd"], "outstanding": metrics["total_outstanding"],
            "churn_score": metrics["churn_risk"], "action_code": code,
            "action_title": decision.get("title", "Contact on hold" if priority == "Hold" else "No action required"),
            "priority": priority, "reason": decision["rationale"],
            "rank": decision.get("priority", 5 if priority == "Hold" else 6)})
    return sorted(rows, key=lambda row: (row["rank"], -row["churn_score"], -row["dpd"], row["customer_id"]))


def explain_action(view):
    customer, metrics, decision = view["customer"], view["metrics"], view["decision"]
    contact = bool(customer.get("consent_calls") and not customer.get("dnd"))
    quality = metrics["data_quality_flags"]
    checks = [
        {"label": "Contact permission", "status": "Pass" if contact else "Blocked",
         "detail": "Calling consent is present and DND is clear." if contact else "The customer cannot be contacted under current preferences."},
        {"label": "Data completeness", "status": "Pass" if not quality else "Review",
         "detail": "Income, active loan and repayment history are available." if not quality else "Missing: " + ", ".join(quality)},
        {"label": "Hardship protection", "status": "Protect" if metrics["hardship_flag"] else "Pass",
         "detail": "Financial growth offers are suppressed while hardship is present." if metrics["hardship_flag"] else "No recent hardship evidence has been identified."},
        {"label": "Review owner", "status": "Required" if decision.get("approval_role") in {"MANAGER", "CREDIT"} else "Support",
         "detail": {"MANAGER": "A manager must review the capped rate proposal.", "CREDIT": "Credit review is required before a conditional invitation."}.get(decision.get("approval_role"), "No financial offer can be executed by this demonstration.")},
    ]
    cited = set(decision.get("evidence_ids", []))
    interactions = sorted(view["interactions"], key=lambda item: item["ts"], reverse=True)
    interactions.sort(key=lambda item: item["interaction_id"] not in cited)
    evidence = [{"id": i["interaction_id"], "channel": i["channel"], "ts": i["ts"],
        "text": i["evidence_text"], "sentiment": i["sentiment"], "intent": i["intent"]} for i in interactions[:5]]
    offer = decision.get("offer", {})
    fields = []
    annual_difference = None
    if "rate_cut_bps" in offer:
        fields = [{"label": "Current rate", "value": f"{offer['current_rate']:g}%"},
                  {"label": "Proposed rate", "value": f"{offer['proposed_rate']:g}%"},
                  {"label": "Policy-capped reduction", "value": f"{offer['rate_cut_bps']} basis points"}]
        annual_difference = round(metrics["total_outstanding"] * offer["rate_cut_bps"] / 10000, 2)
    elif "topup_amount" in offer:
        fields = [{"label": "Conditional amount", "value": f"Rs {offer['topup_amount']:,.0f}"},
                  {"label": "Indicative annual rate", "value": f"{offer['indicative_rate']:g}%"},
                  {"label": "Indicative term", "value": f"{offer['tenure_months']} months"},
                  {"label": "Processing fee", "value": f"{offer['processing_fee_pct']:g}%"}]
    return {"evidence": evidence, "checks": checks, "offer_fields": fields,
            "estimated_annual_interest_difference": annual_difference}


def simulate_interaction(view, scenario, text=None):
    if scenario not in SCENARIOS:
        raise ValueError("Choose a supported conversation scenario.")
    label, default_text = SCENARIOS[scenario]
    if text is None:
        text = default_text
    elif not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ValueError("Enter a bounded fictional borrower statement.")
    else:
        text = "Customer: " + text.strip()
    projected = copy.deepcopy(view)
    reference = datetime.fromisoformat(view["metrics"]["evaluation_time"].replace("Z", "+00:00"))
    signals = extract_signals(text)
    added = {"interaction_id": "SIM-" + projected["customer"]["customer_id"] + "-" + scenario.upper(),
        "customer_id": projected["customer"]["customer_id"], "channel": "CALL_SIMULATION",
        "ts": reference.isoformat(), "text": text, "evidence_text": signals["evidence_text"],
        "intent": signals["intent"], "sentiment": signals["sentiment"], "entities": signals["entities"]}
    projected["interactions"] = [added, *projected["interactions"]]
    if scenario == "opt_out":
        projected["customer"].update(consent_calls=False, consent_marketing=False, dnd=True)
    metrics = compute_metrics(projected["customer"], projected["loans"], projected["payments"], projected["interactions"], reference)
    after = decide_customer(projected["customer"], metrics, projected["interactions"], CATALOGUE)
    return {"scenario": scenario, "label": label, "before": copy.deepcopy(view["decision"]),
            "after": after, "metrics": metrics, "added_evidence": added,
            "changed": view["decision"]["action_code"] != after["action_code"],
            "simulation_only": True, "database_write": False}
