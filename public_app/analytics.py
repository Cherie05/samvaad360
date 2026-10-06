"""Observable portfolio analytics, rule explanations and fictional comparisons.

All figures are derived from the selected customer records. Heuristic scores
are reproduced from the current demonstration rules, never treated as trained
predictions, business outcomes, fairness validation or financial approvals.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite

from public_app.insights import SCENARIOS, explain_action, simulate_interaction

ACTION_LABELS = {
    "HARDSHIP_RESTRUCTURE_CALL": "Hardship support",
    "GENTLE_REMINDER_CALL": "Payment care",
    "RETENTION_RATE_MATCH_CALL": "Retention review",
    "TOPUP_PREAPPROVAL_CALL": "Conditional growth",
    "NO_ACTION": "Monitor / policy hold",
}
DPD_BUCKETS = ["Current", "1–30 days overdue", "31–60 days overdue", "61+ days overdue"]
WINDOWS = {"HARDSHIP_RESTRUCTURE_CALL": 45, "RETENTION_RATE_MATCH_CALL": 60,
           "TOPUP_PREAPPROVAL_CALL": 90, "GENTLE_REMINDER_CALL": 30}


def _timestamp(value):
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _reference(view):
    timestamp = _timestamp(view.get("metrics", {}).get("evaluation_time"))
    if timestamp is None:
        raise ValueError("An explicit policy evaluation time is required for historical analytics.")
    return timestamp


def _number(value, default=0):
    try:
        number = float(value)
        return number if isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _bucket(dpd):
    dpd = _number(dpd)
    return DPD_BUCKETS[0 if dpd <= 0 else 1 if dpd <= 30 else 2 if dpd <= 60 else 3]


def _recent(interaction, days, reference):
    timestamp = _timestamp(interaction.get("ts"))
    return bool(timestamp and 0 <= (reference - timestamp).total_seconds() <= days * 86400)


def _freshness(view):
    reference = _reference(view)
    timestamps = [_timestamp(i.get("ts")) for i in view.get("interactions", [])]
    observed = [timestamp for timestamp in timestamps if timestamp is not None and timestamp <= reference]
    latest = max(observed, default=None)
    window = WINDOWS.get(view["decision"]["action_code"], 30)
    age = (reference - latest).total_seconds() / 86400 if latest else None
    status = "No observed conversation" if latest is None else "Within lookback" if age <= window else "Outside lookback"
    return {"as_of": reference.isoformat(), "latest_conversation": latest.isoformat() if latest else None,
            "days_since_conversation": int(age) if age is not None else None,
            "lookback_days": window, "status": status,
            "future_records": sum(timestamp is not None and timestamp > reference for timestamp in timestamps),
            "invalid_timestamps": sum(timestamp is None for timestamp in timestamps)}


def heuristic_drivers(view):
    """Reproduce actual churn rule contributions in priority points (0–100)."""
    reference = _reference(view)
    metrics = view["metrics"]
    recent = [i for i in view.get("interactions", []) if _recent(i, 30, reference)]
    mean_sentiment = sum(_number(i.get("sentiment")) for i in recent) / len(recent) if recent else 0
    transfers = [i for i in view.get("interactions", []) if _recent(i, 60, reference)
                 and i.get("intent") == "balance transfer or foreclosure"]
    complaints = [i for i in recent if i.get("intent") == "complaint about service or rate"]
    established_high_rate = metrics.get("tenure_months", 0) >= 24 and metrics.get("max_rate", 0) >= 13
    negative = [i for i in recent if _number(i.get("sentiment")) < 0]
    return [
        {"driver": "Transfer / foreclosure intent", "points": 40.0 if transfers else 0.0,
         "rule": "40 points when transfer intent is observed within 60 days", "observed": bool(transfers),
         "evidence_ids": [i["interaction_id"] for i in transfers]},
        {"driver": "Service or rate complaint", "points": 20.0 if complaints else 0.0,
         "rule": "20 points for a complaint within 30 days", "observed": bool(complaints),
         "evidence_ids": [i["interaction_id"] for i in complaints]},
        {"driver": "Negative conversation sentiment", "points": round(20 * max(-mean_sentiment, 0), 4),
         "rule": "Up to 20 points from the negative average sentiment within 30 days",
         "observed": mean_sentiment < 0, "evidence_ids": [i["interaction_id"] for i in negative]},
        {"driver": "Established relationship, higher rate", "points": 20.0 if established_high_rate else 0.0,
         "rule": "20 points when relationship ≥24 months and active rate ≥13%",
         "observed": bool(established_high_rate), "evidence_ids": []},
    ]


def customer_analytics(view):
    reference = _reference(view)
    month_floor = reference.year * 12 + reference.month - 12
    groups = defaultdict(lambda: {"payments": 0, "amount_due": 0.0, "amount_paid": 0.0})
    status_labels = {"PAID": "On time", "LATE": "Late", "BOUNCED": "Bounced", "PENDING": "Pending"}
    invalid_payments = future_payments = 0
    for payment in view.get("payments", []):
        due = _timestamp(payment.get("due_date"))
        if due is None:
            invalid_payments += 1
            continue
        if due.date() > reference.date():
            future_payments += 1
            continue
        if due.year * 12 + due.month <= month_floor:
            continue
        month = due.strftime("%Y-%m-01")
        status = status_labels.get(payment.get("status"), "Other")
        values = groups[(month, status)]
        values["payments"] += 1
        values["amount_due"] += _number(payment.get("amount_due"))
        values["amount_paid"] += _number(payment.get("amount_paid"))
    payments = [{"month": month, "status": status, **values}
                for (month, status), values in sorted(groups.items())]
    conversations = []
    for interaction in view.get("interactions", []):
        timestamp = _timestamp(interaction.get("ts"))
        if timestamp is None or timestamp > reference or timestamp.year * 12 + timestamp.month <= month_floor:
            continue
        conversations.append({"timestamp": timestamp.isoformat(), "channel": str(interaction.get("channel", "Other")).title(),
                              "sentiment": _number(interaction.get("sentiment")), "intent": str(interaction.get("intent", "Recorded interaction")),
                              "evidence_id": interaction["interaction_id"],
                              "excerpt": str(interaction.get("evidence_text", ""))[:240]})
    drivers = heuristic_drivers(view)
    score = round(min(100, sum(d["points"] for d in drivers)))
    checks = explain_action(view)["checks"]
    trace = [{"step": "01 · Source evidence", "status": "Observed" if view.get("interactions") else "Limited",
              "detail": f'{len(view.get("interactions", []))} recorded interactions and {len(view.get("payments", []))} repayment records.'},
             *[{"step": f'{index + 2:02d} · {check["label"]}', "status": check["status"], "detail": check["detail"]}
               for index, check in enumerate(checks)],
             {"step": "06 · Recommendation", "status": "Review only", "detail": view["decision"]["rationale"]}]
    return {"customer_id": view["customer"]["customer_id"], "payment_history": payments,
            "conversation_history": sorted(conversations, key=lambda item: item["timestamp"]),
            "heuristic_drivers": drivers, "heuristic_priority_points": score,
            "reported_priority_points": round(_number(view["metrics"].get("churn_risk")) * 100),
            "freshness": _freshness(view), "policy_trace": trace,
            "excluded_future_payments": future_payments, "invalid_payment_dates": invalid_payments,
            "prediction_validated": False, "history_scope": "Observed repayment and conversation records over the last 12 calendar months"}


def portfolio_analytics(profiles):
    profiles = list(profiles)
    exposure = {bucket: {"bucket": bucket, "balance": 0.0, "loans": 0, "customers": set()} for bucket in DPD_BUCKETS}
    codes = Counter()
    counts = Counter()
    segments = defaultdict(lambda: {"customers": 0, "contact_permitted": 0, "actions_for_review": 0})
    alerts = []
    references = []
    for view in profiles:
        customer, metrics, decision = view["customer"], view["metrics"], view["decision"]
        cid = customer["customer_id"]
        references.append(_reference(view))
        for loan in view.get("loans", []):
            if loan.get("status") != "ACTIVE":
                continue
            bucket = exposure[_bucket(loan.get("current_dpd", 0))]
            bucket["balance"] += _number(loan.get("outstanding"))
            bucket["loans"] += 1
            bucket["customers"].add(cid)
        code = decision["action_code"]
        codes[code] += 1
        contact = bool(customer.get("consent_calls") and not customer.get("dnd"))
        freshness = _freshness(view)
        quality = metrics.get("data_quality_flags", [])
        counts["complete_profiles"] += not quality
        counts["contact_protected"] += not contact
        counts["hardship"] += bool(metrics.get("hardship_flag"))
        counts["transfer"] += bool(metrics.get("bt_intent"))
        counts["negative"] += _number(metrics.get("sentiment_30d")) < -.3
        counts["data_gaps"] += bool(quality)
        counts["signal_within_lookback"] += freshness["status"] == "Within lookback"
        counts["missing_conversation"] += freshness["status"] == "No observed conversation"
        counts["outside_lookback"] += freshness["status"] == "Outside lookback"
        counts["future_signal_records"] += freshness["future_records"]
        counts["invalid_signal_timestamps"] += freshness["invalid_timestamps"]
        counts["actions_for_review"] += code != "NO_ACTION"
        counts["actions_with_citations"] += code != "NO_ACTION" and bool(decision.get("evidence_ids"))
        segment = segments[str(customer.get("segment", "UNKNOWN")).replace("_", " ").title()]
        segment["customers"] += 1
        segment["contact_permitted"] += contact
        segment["actions_for_review"] += code != "NO_ACTION"
        title = detail = kind = level = None
        if metrics.get("hardship_flag"):
            title, kind, level = "Put support before growth", "Hardship", "High"
            detail = "Recent hardship evidence suppresses growth offers. An officer should review the support context."
        elif not contact:
            title, kind, level = "Respect the contact restriction", "Consent", "Protected"
            detail = "No call workflow is eligible while calling consent is absent or DND is active."
        elif quality:
            title, kind, level = "Complete the missing context", "Data quality", "Review"
            detail = "Manual review is required: " + ", ".join(quality)
        elif metrics.get("bt_intent") and _number(metrics.get("churn_risk")) >= .6:
            title, kind, level = "A retention conversation needs attention", "Retention", "High"
            detail = "Transfer intent and the current heuristic priority support a capped retention review."
        elif metrics.get("dpd", 0) > 0:
            title, kind, level = "Review the overdue relationship", "Payment care", "Review"
            detail = f'{metrics["dpd"]} days overdue. Check support needs before choosing respectful contact.'
        if title:
            alerts.append({"customer_id": cid, "name": customer["full_name"], "kind": kind, "level": level,
                           "title": title, "detail": detail, "action_code": code,
                           "evidence_ids": list(decision.get("evidence_ids", []))})
    size = len(profiles)
    exposure_rows = [{**row, "customers": len(row["customers"]), "balance": round(row["balance"], 2)} for row in exposure.values()]
    action_mix = [{"action_code": code, "action": ACTION_LABELS[code], "customers": codes[code],
                   "share": codes[code] / size if size else 0} for code in ACTION_LABELS]
    prevalence = [{"signal": label, "customers": counts[key]}
                  for key, label in [("hardship", "Recent hardship"), ("transfer", "Transfer intent"),
                                     ("negative", "Negative conversation tone"), ("data_gaps", "Missing lending context"),
                                     ("contact_protected", "Contact restricted")]]
    coverage = [{"segment": name, **values, "review_share": values["actions_for_review"] / values["customers"]}
                for name, values in sorted(segments.items())]
    governance = {"customers": size, **dict(counts),
                  "prediction_validated": False, "fairness_evaluated": False,
                  "fairness_note": "Segment coverage is descriptive. A small synthetic sample cannot establish fairness or real-world outcomes.",
                  "as_of": max(references).isoformat() if references else None}
    order = {"High": 0, "Review": 1, "Protected": 2}
    return {"exposure_by_dpd": exposure_rows, "action_mix": action_mix, "driver_prevalence": prevalence,
            "alerts": sorted(alerts, key=lambda item: (order[item["level"]], item["customer_id"])),
            "governance": governance, "segment_coverage": coverage,
            "total_exposure": round(sum(row["balance"] for row in exposure_rows), 2)}


def intervention_matrix(view):
    """Compare all supported scenarios by executing the actual domain rules."""
    rows = []
    for scenario in SCENARIOS:
        comparison = simulate_interaction(view, scenario)
        before, after = comparison["before"], comparison["after"]
        offer_before, offer_after = before.get("offer", {}), after.get("offer", {})
        offer_change = "Suppressed" if offer_before and not offer_after else "New conditional proposal" if not offer_before and offer_after else "Changed" if offer_before != offer_after else "No change"
        rows.append({"scenario": scenario, "label": comparison["label"],
                     "before_action": ACTION_LABELS.get(before["action_code"], before["action_code"]),
                     "after_action": ACTION_LABELS.get(after["action_code"], after["action_code"]),
                     "before_action_code": before["action_code"], "after_action_code": after["action_code"],
                     "action_changed": comparison["changed"], "offer_change": offer_change,
                     "priority_points": round(comparison["metrics"]["churn_risk"] * 100),
                     "hardship_flag": comparison["metrics"]["hardship_flag"],
                     "evidence_id": comparison["added_evidence"]["interaction_id"],
                     "evidence_quote": comparison["added_evidence"]["evidence_text"],
                     "rationale": after["rationale"], "simulation_only": True, "database_write": False})
    return rows
