"""Grounded local query provider. Deterministic answers are explicitly labeled.

This provider can answer the supported lending questions with current service
data. It never pretends to have called Snowflake Cortex or a generative model.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PROVIDER = "Local evidence retrieval · deterministic answers"


def answer_question(service, question, customer_id, actor):
    question = (question or "").strip()
    result = {"answer": "", "citations": [], "tools": [], "provider": PROVIDER}
    if not question or len(question) > 4000:
        return {**result, "answer": "Please ask a customer or portfolio question of 1-4,000 characters."}
    low = question.lower()
    now = datetime.now(timezone.utc)

    def parsed_time(value):
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
        except (ValueError, TypeError):
            return None

    def recent(value, days):
        stamp = parsed_time(value)
        return stamp is not None and timedelta(0) <= now - stamp <= timedelta(days=days)

    def requested_days(default=None):
        match = re.search(r"last\s+(\d+)\s+days?", low)
        if match:
            return min(int(match[1]), 3650)
        if re.search(r"(?:last|past)\s+(?:3|three)\s+months?", low):
            return 90
        return default
    customers = service.list_customers()
    explicit = [c for c in customers if c["customer_id"].lower() in low or c["full_name"].lower() in low
                or (c["customer_id"] in {"C0001", "C0002", "C0003"} and c["full_name"].split()[0].lower() in low)]
    if customer_id and any(c["customer_id"] != customer_id for c in explicit):
        return {**result, "answer": "That customer is outside the selected scope. Select their profile or switch to portfolio scope."}
    scope = [service.customer360(customer_id)] if customer_id else [service.customer360(c["customer_id"]) for c in (explicit or customers)]

    def citations(interactions, cid):
        return [{"interaction_id": i["interaction_id"], "customer_id": cid, "channel": i["channel"],
                 "ts": i["ts"], "text": i.get("evidence_text") or i["text"]}
                for i in interactions if i["channel"] != "ACTION_OUTCOME"]

    def context(view):
        result["tools"] = ["local_customer_metrics", "local_conversation_search"]
        result["citations"] = citations(view["interactions"], view["customer"]["customer_id"])
        metrics = view["metrics"]
        return f"{view['customer']['full_name']} ({view['customer']['customer_id']}) has DPD {metrics['dpd']}, outstanding Rs {metrics['total_outstanding']:,.0f}, and repayment ratio {metrics['on_time_ratio']:.0%}."

    if re.search(r"\bapprove\b|bypass|ignore.*(?:rules|instructions|approval)|override|\bforce\b|\bexecute\b", low):
        return {**result, "answer": "I cannot approve financial offers or bypass policy checks. The appropriate manager or credit officer must review an action in Approvals."}
    if re.search(r"\bcall\b.*\bnow\b|place (?:a |the )?call|contact.*(?:now|immediately)", low):
        return {**result, "answer": "I cannot place calls or contact customers. Only the approved runner can execute an approved action after policy checks."}
    if re.search(r"send.*(?:link|offer|email)|generate.*(?:link|offer)", low):
        view = scope[0] if len(scope) == 1 else next((v for v in scope if v["customer"]["customer_id"] == "C0003"), scope[0])
        offers = service.offers(view["customer"]["customer_id"])
        if offers:
            result["answer"] = f"An existing synthetic invitation is available: {offers[0]['url']}. Its validity is checked when opened. I did not send a message."
        else:
            result["answer"] = "A pre-approval link requires credit approval and execution by the approved runner. I cannot send an offer or bypass that approval. Review the recommendation in Approvals first."
        return result
    if re.search(r"queue|recommend (?:an |the |a )?(?:action|next)|next best action for", low):
        if len(scope) != 1:
            return {**result, "answer": "Select one customer to queue a recommendation."}
        action = service.recommend(scope[0]["customer"]["customer_id"], actor)
        result["tools"] = ["queue_next_best_action"]
        result["answer"] = f"{action['action_code']} / {action['status']}. " + action["rationale"]
        result["citations"] = citations([i for i in scope[0]["interactions"] if i["interaction_id"] in action.get("evidence_ids", [])], scope[0]["customer"]["customer_id"])
        return result
    if "policy" in low and ("hardship" in low or "job loss" in low):
        return {**result, "tools": ["local_policy_lookup"], "answer": "The fictional DemoLend hardship policy allows an officer to review an EMI break of up to 3 months or a tenure extension. A callback promises no financial change; a credit officer must approve any actual revised terms. [DemoLend hardship policy v1]"}
    if ("maximum" in low or "max " in low or "who approve" in low) and ("rate" in low or "cut" in low):
        item = next(c for c in service.catalogue() if c["action_code"] == "RETENTION_RATE_MATCH_CALL")
        return {**result, "tools": ["local_policy_lookup"], "answer": f"The current retention cap is {item['max_rate_cut_bps']} bps and requires manager approval. The proposal is capped, so it may not match a competitor's rate. [DemoLend retention policy v{item['version']}]"}
    if ("job" in low or "hardship" in low) and ("which" in low or "mentioned" in low or "borrowers" in low):
        days = requested_days(45)
        matches = [v for v in scope if any(i["intent"] == "financial hardship" and recent(i["ts"], days) for i in v["interactions"])
                   and (not ("past due" in low or "overdue" in low) or v["metrics"]["dpd"] > 0)]
        result["tools"] = ["local_customer_metrics", "local_conversation_search"]
        result["answer"] = "\n".join(f"{v['customer']['full_name']} ({v['customer']['customer_id']}) — DPD {v['metrics']['dpd']}; recent hardship conversation." for v in matches) or "No customer in this scope has a recent hardship signal."
        for view in matches:
            result["citations"].extend(citations([i for i in view["interactions"] if i["intent"] == "financial hardship" and recent(i["ts"], days)], view["customer"]["customer_id"]))
        return result
    if "bounce" in low and "rate" in low:
        days = requested_days()
        grouped = {}
        for view in scope:
            active = {loan["loan_id"]: loan["product"] for loan in view["loans"] if loan["status"] == "ACTIVE"}
            for payment in view["payments"]:
                due = parsed_time(payment["due_date"])
                if payment["loan_id"] not in active or due is None or due > now or (days is not None and not recent(payment["due_date"], days)):
                    continue
                counts = grouped.setdefault(active[payment["loan_id"]], [0, 0])
                counts[0] += payment["status"] == "BOUNCED"
                counts[1] += 1
        period = f"the last {days} days" if days is not None else "the available history"
        lines = [f"{product}: {bounced}/{total}, or {bounced / total:.1%}" for product, (bounced, total) in sorted(grouped.items())]
        return {**result, "tools": ["local_customer_metrics"], "answer": f"Bounce rate by product for {period} (bounced payments / all due payment rows on active loans): " + "; ".join(lines) if lines else "There is no payment history in this scope and period."}
    if "outstanding" in low and ("total" in low or "personal" in low):
        relevant = [v for v in scope if v["metrics"]["bounces_3m"] > 0] if "bounce" in low else scope
        amount = sum(v["metrics"]["total_outstanding"] for v in relevant)
        return {**result, "tools": ["local_customer_metrics"], "answer": f"Total outstanding for the selected active-loan customers: Rs {amount:,.0f}. Loans are aggregated once per customer before this total is calculated."}
    if "city" in low and ("past due" in low or "dpd" in low or "overdue" in low):
        grouped = {}
        for view in scope:
            if 1 <= view["metrics"]["dpd"] <= 30:
                city = view["customer"]["city"]
                grouped[city] = grouped.get(city, 0) + 1
        return {**result, "tools": ["local_customer_metrics"], "answer": "Active borrowers 1-30 DPD by city: " + "; ".join(f"{city}: {count}" for city, count in sorted(grouped.items())) if grouped else "No borrowers in this scope are 1-30 days past due."}
    if "blocked" in low or "opted out" in low or "opt-out" in low:
        events = [e for v in scope for e in service.audit(customer_id=v["customer"]["customer_id"])]
        kind = "ACTION_BLOCKED" if "blocked" in low else "OPTED_OUT"
        matches = [e for e in events if e["event"] == kind]
        local_now = now.astimezone(ZoneInfo("Asia/Kolkata"))
        start = None
        period = "in the available local history"
        if "today" in low:
            start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            period = "today (IST)"
        elif "this week" in low:
            start = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            period = "this week (Monday onward, IST)"
        if start:
            matches = [e for e in matches if parsed_time(e["ts"]) is not None and start <= parsed_time(e["ts"]) <= now]
        reasons = sorted({e["detail"].get("code", "consent withdrawn") for e in matches})
        count = len(matches) if kind == "ACTION_BLOCKED" else len({e["customer_id"] for e in matches if e["customer_id"]})
        subject = "Blocked action attempts" if kind == "ACTION_BLOCKED" else "Distinct borrowers who opted out"
        return {**result, "tools": ["local_audit_metrics"], "answer": f"{subject} {period} in this scope: {count}. Reasons: {', '.join(reasons) if reasons else 'none recorded'}. No real calls are placed by the local product."}
    if len(scope) == 1:
        view = scope[0]
        preface = context(view)
        if "eligible" in low or "how much" in low or "top-up" in low or "topup" in low:
            metrics = view["metrics"]
            result["answer"] = preface + (f" Eligible under the illustrative rules for up to Rs {metrics['topup_amount']:,.0f}, subject to credit approval and further checks." if metrics["topup_eligible"] else " Not currently eligible under the illustrative top-up rules.")
        elif "competitor" in low or "other lenders" in low or "brightline" in low:
            result["answer"] = preface + " " + " ".join(i.get("evidence_text", i["text"]) for i in view["interactions"] if i["entities"].get("competitor"))
        elif any(k in low for k in ("why", "journey", "summar", "risk", "flag", "situation", "tell me", "said", "happen", "next best action")):
            result["answer"] = preface + " " + view["current_decision"]["rationale"]
            days = requested_days()
            if days is not None:
                result["citations"] = [c for c in result["citations"] if recent(c["ts"], days)]
        else:
            result["answer"] = preface + " Ask about eligibility, competitor mentions, recent hardship, or the recommended action."
        return result
    if "eligible" in low and ("top-up" in low or "topup" in low):
        eligible = [v for v in scope if v["metrics"]["topup_eligible"]]
        return {**result, "tools": ["local_customer_metrics"], "answer": "\n".join(f"{v['customer']['full_name']} ({v['customer']['customer_id']}): up to Rs {v['metrics']['topup_amount']:,.0f}, subject to credit approval." for v in eligible) or "No customers in this scope meet the illustrative top-up rules."}
    if "churn" in low and ("how many" in low or "high" in low):
        count = sum(v["metrics"]["churn_risk"] >= .6 for v in scope)
        return {**result, "tools": ["local_customer_metrics"], "answer": f"{count} customers in this scope have a churn review score of at least 0.6. This is a local heuristic priority score, not a churn probability."}
    if "how many" in low or "portfolio" in low:
        portfolio = service.portfolio()
        return {**result, "tools": ["local_customer_metrics"], "answer": f"The local portfolio has {portfolio['customers']} customers, {portfolio['active_loans']} active loans, {portfolio['past_due']} past-due borrowers, and {portfolio['pending_approvals']} pending approvals."}
    return {**result, "answer": "I can answer customer journeys, hardship evidence, competitor mentions, top-up eligibility, portfolio DPD, and current policy caps. Select a customer or use one of those question types. This local provider does not generate unrestricted LLM answers."}
