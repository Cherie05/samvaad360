"""Samvaad 360: an evidence-led public lending command center."""
import logging
import json
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from public_app.calling import CallSandbox
from public_app.analytics import customer_analytics, intervention_matrix, portfolio_analytics
from public_app.insights import explain_action, priority_queue, simulate_interaction, summarize_portfolio
from public_app.repository import DemoError, GuardedSnapshotReader, ReviewSandbox, SnapshotReader, connect_reader
from public_app.security import PublicGuard
from public_app.ui.call_audio import render_browser_voice
from public_app.ui.charts import render_driver_chart, render_governance, render_intervention_matrix, render_portfolio_charts, render_relationship_timeline
from public_app.ui.telephone import render_telephone
from public_app.ui.relationship import PublicRelationshipSandbox, render_relationship_hub
from public_app.relationship_repository import VisitRelationshipReader
from public_app.ui.visuals import CSS, chip, date_label, empty_state, evidence_card, fields, metric_grid, money, safe, section

st.set_page_config(page_title="Samvaad 360 | Lending command center", page_icon="◉", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<h1 class="sr-only">Samvaad 360 customer intelligence workspace</h1>', unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def usage_guard():
    return PublicGuard()


def visitor_identity():
    return usage_guard().visitor(context_ip=st.context.ip_address, headers=st.context.headers,
                                 edge_secret=os.getenv("SAMVAAD_TRUSTED_EDGE_SECRET"))


@st.cache_resource(show_spinner=False)
def reader():
    settings = None
    try:
        local_secrets = os.getenv("SAMVAAD_PUBLIC_SECRETS_FILE")
        settings = (tomllib.loads(Path(local_secrets).read_text(encoding="utf-8"))["snowflake"]
                    if local_secrets else dict(st.secrets["snowflake"]))
    except Exception as error:
        logging.getLogger("samvaad.public").warning("Public fallback activated: %s", type(error).__name__)
    def load(permit):
        if settings is None:
            raise DemoError("Live data settings are unavailable.")
        return connect_reader(settings, budget=permit)
    return GuardedSnapshotReader(load, SnapshotReader(Path(__file__).with_name("synthetic_snapshot.json")),
                                 usage_guard(), refresh_seconds=3600)


def customers(source):
    return visit_reader().customers()


def portfolio_profiles(source):
    return visit_reader().portfolio_profiles()


def profile(customer_id, source):
    return visit_reader().customer360(customer_id)


def relationship_sandbox():
    return PublicRelationshipSandbox(st.session_state.setdefault("public_relationship_state", {}), reader().customers())


def visit_reader():
    return VisitRelationshipReader(reader(), relationship_sandbox())


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def open_workspace(customer_id, tab="Customer 360"):
    st.session_state["selected_customer"] = customer_id
    st.session_state["workspace_tabs"] = tab


def queue_action(customer_id):
    def action():
        ReviewSandbox(st.session_state["public_reviews"], visit_reader()).request(customer_id)
        st.session_state["public_flash"] = "Recommendation added. Review the proposal, then try the call simulation."
    run_visit_action("Review queue", action)


def run_visit_action(tab, action, *, select_tab=True):
    """Apply a visit action before Streamlit chooses which tab to render."""
    if select_tab:
        st.session_state["workspace_tabs"] = tab
    try:
        admission = usage_guard().admit(visitor_identity(), kind="action")
        if not admission.allowed:
            st.session_state["public_flash_error"] = f"Too many actions. Try again in {admission.retry_after} seconds."
            return
        action()
    except DemoError as error:
        st.session_state["public_flash_error"] = str(error)
    except Exception as error:
        logging.getLogger("samvaad.public").error("Public workflow failure: %s", type(error).__name__)
        st.session_state["public_flash_error"] = "This operation could not complete. Please try again. Connection details remain private."


def run_relationship_action(tab, action):
    # Relationship forms execute inside their already selected tab. Changing
    # its widget state here is forbidden after Streamlit has instantiated it.
    run_visit_action(tab, action, select_tab=False)


def ask_evidence(customer_id):
    def action():
        result = visit_reader().answer(customer_id, st.session_state["public_question_text"])
        st.session_state["public_answer"] = {"customer_id": customer_id, **result}
    run_visit_action("Evidence desk", action)


def compare_interventions(customer_id, source):
    def action():
        comparison = simulate_interaction(profile(customer_id, source), st.session_state["what_if_scenario"])
        st.session_state["public_what_if"] = {"customer_id": customer_id, **comparison}
    run_visit_action("Customer 360", action)


def save_review(request_id):
    def action():
        ReviewSandbox(st.session_state["public_reviews"], visit_reader()).review(
            request_id, st.session_state["review_outcome_" + request_id], st.session_state["review_note_" + request_id])
        st.session_state["public_review_open"] = request_id
    run_visit_action("Review queue", action)


def call_action(action_name, customer_or_session, text=None, field_key=None):
    def action():
        studio = CallSandbox(st.session_state["public_calls"], visit_reader(), st.session_state["public_reviews"])
        if action_name == "start":
            studio.start(customer_or_session)
        elif action_name == "reply":
            studio.reply(customer_or_session, st.session_state[field_key] if field_key else text)
            if field_key:
                st.session_state[field_key] = ""
        elif action_name == "end":
            studio.end(customer_or_session)
    run_visit_action("Call studio", action)


def action_name(decision):
    if decision.get("title"):
        return decision["title"]
    if decision.get("action_code") == "NO_ACTION":
        return "Contact on hold" if "contact" in decision.get("rationale", "").lower() else "No eligible intervention"
    return str(decision.get("action_code", "Manual review")).replace("_", " ").title()


def action_chip(code):
    labels = {"HARDSHIP_RESTRUCTURE_CALL": ("Support first", "amber"),
              "GENTLE_REMINDER_CALL": ("Payment care", "blue"),
              "RETENTION_RATE_MATCH_CALL": ("Retention", "green"),
              "TOPUP_PREAPPROVAL_CALL": ("Growth", "blue"), "NO_ACTION": ("Policy hold", "gray")}
    return chip(*labels.get(code, ("Review", "gray")))


def review_role(role):
    return {"MANAGER": "Manager review", "CREDIT": "Credit review", "AUTO": "Policy checks"}.get(role, "Contact restricted")


def visit_hold(customer_id):
    preferences = st.session_state.get("public_relationship_state", {}).get("preferences", {}).get(customer_id, {})
    if preferences.get("dnd") or preferences.get("consent_calls") is False:
        return "Contact permission was withdrawn in Customer hub. Further contact is held for this visit."
    state = st.session_state.get("public_calls", {})
    if customer_id in state.get("suppressed_contacts", []):
        return "The borrower opted out in this visit. Further conversation rehearsals are blocked."
    if customer_id in state.get("hardship_holds", []):
        return "New hardship evidence places this visit’s earlier offer on hold for officer review."
    return ""


def visit_update(customer_id):
    return next((record for record in reversed(st.session_state.get("public_calls", {}).get("sessions", []))
                 if record["customer_id"] == customer_id and record.get("decision_after")), None)


def admit_telephone_action():
    admission = usage_guard().admit(visitor_identity(), kind="action")
    if not admission.allowed:
        st.warning(f"Too many telephone operations. Try again in {admission.retry_after} seconds.")
    return admission.allowed


def render_usage_protection():
    status = reader().source_status()
    html(section("Usage protection", "Shared limits keep visitor activity away from warehouse queries"))
    html(metric_grid([
        ("Visitor database queries", 0, "Customer views, evidence and reviews use the shared snapshot"),
        ("Refresh statements today", f'{status.get("application_statements_day", 0)}/{status.get("daily_statement_limit", 64)}', "Application statement reservations · not billed credits"),
        ("Automatic refresh", "Hourly", "Single refresh for all visitors · no public refresh control"),
        ("Requests held", status.get("requests_blocked", 0), "Shared host throttle and circuit breaker"),
    ]))
    if status.get("last_refresh"):
        st.caption("Last successful Snowflake snapshot: " + status["last_refresh"])
    if status.get("stale"):
        st.warning("Live refresh is held. These are dated facts from the last successful Snowflake snapshot.")
    st.caption("Current hosting uses a shared visitor limit. Verified IP limits require a trusted gateway. "
               "Host limits do not meter all account credits or survive every hosting replacement; the Snowflake warehouse monitor remains a separate safeguard.")


def render_offer(view):
    explanation = explain_action(view)
    html(fields(explanation["offer_fields"]))
    estimate = explanation.get("estimated_annual_interest_difference")
    if estimate is not None:
        st.caption(f"Illustrative annual interest difference: {money(estimate)}. Simple balance × rate difference; "
                   "actual savings depend on amortisation, fees and approval.")


def render_action(view, *, show_button=False):
    decision = view["decision"]
    html('<div class="action-card">' + action_chip(decision["action_code"]) +
         f'<h3>{safe(action_name(decision))}</h3><p>{safe(decision["rationale"])}</p></div>')
    render_offer(view)
    if decision["action_code"] != "NO_ACTION":
        html(chip(review_role(decision.get("approval_role")), "gray") + chip("Illustrative terms", "gray"))
    if show_button:
        hold = visit_hold(view["customer"]["customer_id"])
        st.button("Add to review queue", type="primary", width="stretch", key="request_selected_review",
                  disabled=decision["action_code"] == "NO_ACTION" or bool(hold), on_click=queue_action,
                  args=(view["customer"]["customer_id"],))
        if hold:
            st.caption(hold)


def render_checks(view):
    for check in explain_action(view)["checks"]:
        status = str(check.get("status", "")).lower()
        okay = status in {"pass", "passed", "allowed", "eligible", "true", "met", "ok", "protect", "support"}
        marker = "✓" if okay else "○" if status in {"review", "pending", "info"} else "!"
        html(f'<div class="check-row"><span class="check-icon {"" if okay else "blocked"}">{marker}</span>'
             f'<div><strong>{safe(check["label"])}</strong><div class="small">{safe(check.get("detail", ""))}</div></div></div>')


def render_comparison(before, after, label):
    html(f'<div class="compare-card"><div class="eyebrow">Before the new context</div><h4>{safe(action_name(before))}</h4>'
         f'<div class="eyebrow" style="margin-top:1rem">{safe(label)}</div><h4>{safe(action_name(after))}</h4>'
         f'<p>{safe(after["rationale"])}</p></div>')


def render_command_center(source):
    html('<div class="hero"><div class="eyebrow">Customer intelligence · Insurance &amp; lending</div>'
         '<h2>A better next conversation.</h2><p>See the whole relationship. Understand what changed. '
         'Choose the right intervention before you reach out.</p>'
         '<div class="hero-tag">Evidence → Policy → Review → Conversation</div></div>')
    with st.spinner("Preparing your portfolio overview…"):
        views = portfolio_profiles(source)
    summary = summarize_portfolio(views)
    html(metric_grid([
        ("Portfolio outstanding", money(summary["total_outstanding"]), f'{summary["customers"]} fictional customer relationships'),
        ("Actions ready for review", summary["actions_ready"], "Ranked by policy and customer context"),
        ("Support & retention", summary["hardship_cases"] + summary["retention_cases"], "Relationships needing a thoughtful response"),
        ("Contact protected", summary["contact_blocked"], "Consent restrictions enforced before contact"),
    ]))
    left, right = st.columns([1.65, 1], gap="large")
    with left:
        html(section("Today's priority queue", "Recommended interventions"))
        queue = [item for item in priority_queue(views) if item["action_code"] != "NO_ACTION"]
        selected_filter = st.segmented_control("Filter actions", ["All", "Support", "Retention", "Growth"],
                                               default="All", required=True, label_visibility="collapsed")
        filter_codes = {"Support": {"HARDSHIP_RESTRUCTURE_CALL", "GENTLE_REMINDER_CALL"},
                        "Retention": {"RETENTION_RATE_MATCH_CALL"}, "Growth": {"TOPUP_PREAPPROVAL_CALL"}}
        filtered = [item for item in queue if selected_filter == "All" or item["action_code"] in filter_codes[selected_filter]]
        if not filtered:
            html(empty_state("No actions in this view", "Choose another filter to explore the portfolio."))
        for item in filtered[:6]:
            with st.container(border=True):
                identity, detail, action = st.columns([1.8, 1.55, 1.05], gap="small", vertical_alignment="center")
                with identity:
                    html(f'<div class="priority-name">{safe(item["name"])}</div>'
                         f'<div class="priority-meta">{safe(item["customer_id"])} · {safe(item["segment"].replace("_", " ").title())}</div>')
                with detail:
                    html(action_chip(item["action_code"]))
                    st.caption(f'{money(item["outstanding"])} · {item["dpd"]} days overdue')
                with action:
                    st.button("Open →", key="priority_" + item["customer_id"], width="stretch",
                              on_click=open_workspace, args=(item["customer_id"],))
        if len(filtered) > 6:
            st.caption(f"Showing 6 of {len(filtered)} recommended actions. Explore every customer from the sidebar.")
    with right:
        html(section("Built for the whole journey", "Three connected capabilities"))
        with st.container(border=True):
            for number, label, title, copy in [
                ("01", "Relationship intelligence", "Hear what the numbers miss", "A perfect payment history can hide a relationship at risk. Combine repayment facts with the customer’s own words."),
                ("02", "Policy-aware intervention", "Compare before acting", "Test a new life event or contact preference. See how it changes the recommendation and which evidence supports it."),
                ("03", "Conversation rehearsal", "Turn review into a conversation", "Approve a fictional proposal, then practise a voice conversation with permission, identity and opt-out checks.")]:
                html(f'<div class="eyebrow">{number} / {safe(label)}</div><h3>{safe(title)}</h3><p class="sidebar-note">{safe(copy)}</p>')
        with st.container(border=True):
            st.markdown("**Your workflow this visit**")
            pending = sum(r["status"] == "PENDING_SIMULATION" for r in st.session_state["public_reviews"])
            approved = sum(r["status"] == "APPROVED_IN_SIMULATION" for r in st.session_state["public_reviews"])
            html(fields([{"label": "Awaiting your review", "value": pending}, {"label": "Ready to rehearse", "value": approved}]))
            st.button("Open review queue →", width="stretch", on_click=open_workspace,
                      args=(st.session_state["selected_customer"], "Review queue"))
    html(section("Portfolio intelligence", "Observed exposure and intervention priorities"))
    analytics = portfolio_analytics(views)
    render_portfolio_charts(analytics)
    with st.expander("Data quality and policy coverage"):
        render_governance(analytics)
        alerts = analytics.get("alerts", [])
        if alerts:
            st.dataframe(alerts, hide_index=True, width="stretch")
    with st.expander("Database usage protection"):
        render_usage_protection()
    html(section("Explore four customer stories", "A guided tour of the decision engine"))
    stories = [("C0001", "Ravi", "A job loss changes the conversation", "Hardship evidence prioritises support over payment pressure.", "amber"),
               ("C0002", "Ananya", "A loyal borrower may leave", "A competitor offer prompts a capped, reviewable retention proposal.", "green"),
               ("C0003", "Imran", "Growth with affordability checks", "Top-up interest meets repayment and income policy checks.", "blue"),
               ("C0004", "Neha", "Sometimes the right action is none", "An opt-out blocks contact even when an opportunity looks attractive.", "gray")]
    for col, (cid, name, title, copy, tone) in zip(st.columns(4, gap="small"), stories):
        with col, st.container(border=True):
            html(chip(name, tone) + f'<div class="scenario-copy"><h3>{safe(title)}</h3><p>{safe(copy)}</p></div>')
            st.button(f"Explore {name} →", key="story_" + cid, width="stretch", on_click=open_workspace, args=(cid,))


def render_customer(view):
    if view.get("rehearsal"):
        st.info("Visit-only relationship · Created or updated in Customer hub. Shared Snowflake records remain separate.")
    customer, metrics = view["customer"], view["metrics"]
    analytics = customer_analytics(view)
    initials = ''.join(word[0] for word in customer["full_name"].split()[:2])
    html(f'<div class="identity"><div class="avatar">{safe(initials)}</div><div><div class="eyebrow">Customer workspace</div>'
         f'<h2>{safe(customer["full_name"])}</h2><div class="meta">{safe(customer["customer_id"])} · {safe(customer["city"])}'
         f' · {safe(customer["segment"].replace("_", " ").title())} · {metrics["tenure_months"]} months together</div></div></div>')
    html(metric_grid([
        ("Outstanding balance", money(metrics["total_outstanding"]), f'{metrics["active_loans"]} active loan(s)'),
        ("Payment reliability", f'{metrics["on_time_ratio"]:.0%}', f'{metrics["dpd"]} days overdue today'),
        ("Retention priority", f'{round(metrics["churn_risk"] * 100)}/100', "Illustrative rules score · not a probability"),
        ("Monthly commitments", money(metrics["total_emi"]), f'{metrics["foir"]:.0%} of monthly income' if metrics["foir"] is not None else "Income needs review"),
    ]))
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        update = visit_update(customer["customer_id"])
        if update:
            html(section("Latest conversation update", "Applied to this visit"))
            st.warning(visit_hold(customer["customer_id"]))
            render_comparison(update["decision_before"], update["decision_after"], "After the borrower’s new context")
        html(section("Recorded next step" if update else "Recommended next step", "Evidence-backed and reviewable"))
        with st.container(border=True):
            render_action(view, show_button=True)
            st.caption("Review and call actions in this public experience are fictional simulations.")
        html(section("Repayment and conversation timeline", "Connect recorded numbers with customer context"))
        render_relationship_timeline(analytics, key_prefix=customer["customer_id"])
        html(section("Omnichannel journey", f'{len(view["interactions"])} recorded interactions'))
        if not view["interactions"]:
            html(empty_state("No interactions recorded", "The recommendation relies on available lending facts."))
        else:
            entries = []
            for interaction in sorted(view["interactions"], key=lambda item: item["ts"], reverse=True):
                entries.append(f'<div class="journey-item"><div class="stamp">{safe(date_label(interaction["ts"]))} · '
                               f'{safe(interaction["channel"].title())}</div><div class="title">{safe(interaction["intent"].capitalize())}</div>'
                               f'<div class="excerpt">{safe(interaction["evidence_text"])}</div>'
                               f'<div class="source">{safe(interaction["interaction_id"])}</div></div>')
            html('<div class="timeline">' + ''.join(entries) + '</div>')
        with st.expander("Loan & repayment details"):
            display_loans = [{"Loan": l["loan_id"], "Product": l["product"].replace("_", " ").title(),
                              "Balance": money(l["outstanding"]), "Monthly EMI": money(l["emi"]),
                              "Rate": f'{l["interest_rate"]:g}%', "Status": l["status"].title()} for l in view["loans"]]
            st.dataframe(display_loans, hide_index=True, width="stretch")
            paid = sum(p["status"] == "PAID" for p in view["payments"])
            late = sum(p["status"] in {"LATE", "BOUNCED"} for p in view["payments"])
            st.caption(f"{len(view['payments'])} repayment records · {paid} paid on time · {late} late or bounced")
    with right:
        html(section("Retention priority drivers", "See the contribution of each rule"))
        render_driver_chart(analytics, key_prefix=customer["customer_id"])
        html(section("Why this action", "Policy checkpoints"))
        with st.container(border=True):
            render_checks(view)
        html(section("Contact preferences", "Customer control comes first"))
        with st.container(border=True):
            html(chip("Calls permitted" if customer["consent_calls"] else "Calls not permitted", "green" if customer["consent_calls"] else "red") +
                 chip("Marketing opted in" if customer["consent_marketing"] else "Marketing opted out", "green" if customer["consent_marketing"] else "gray") +
                 chip("Do not disturb" if customer["dnd"] else "DND clear", "red" if customer["dnd"] else "gray"))
            st.caption("No real phone number is exposed in this fictional portfolio.")
        html(section("What-if studio", "Test the turning point"))
        with st.container(border=True):
            st.markdown("**How would new context change the next step?**")
            scenarios = {"job_loss": "A job loss", "competitor_offer": "A competitor offer",
                         "opt_out": "A contact opt-out", "topup_interest": "A top-up request"}
            scenario = st.selectbox("New customer context", list(scenarios), format_func=scenarios.get, key="what_if_scenario")
            st.button("Compare interventions", type="primary", width="stretch", on_click=compare_interventions,
                      args=(customer["customer_id"], "snowflake" if reader().is_live else "snapshot"))
            comparison = st.session_state.get("public_what_if", {})
            if comparison.get("customer_id") == customer["customer_id"]:
                render_comparison(comparison["before"], comparison["after"], "With " + comparison["label"])
                if comparison["changed"]:
                    st.success("The new context changes the recommended intervention.")
                else:
                    st.info("The current policy keeps the same intervention.")
                if isinstance(comparison.get("added_evidence"), dict):
                    html(evidence_card(comparison["added_evidence"]))
                st.caption("Fictional scenario overlay. Saved customer data and the live recommendation remain unchanged.")
            else:
                st.caption("Runs the same policy rules against fictional context. No loan terms or contact preferences are saved.")
    with st.expander("Compare all four customer-context changes"):
        render_intervention_matrix(intervention_matrix(view), key_prefix=customer["customer_id"])


def render_evidence(view, repository):
    customer = view["customer"]
    html(section("Evidence desk", f'Scoped to {customer["full_name"]}'))
    left, right = st.columns([1.2, 1], gap="large")
    with left:
        with st.container(border=True):
            st.subheader("Ask the relationship, not a table")
            st.caption("Get a grounded summary with the original conversations alongside it.")
            with st.form("public_question"):
                st.text_input("Question", value="Why is this next action recommended?", max_chars=1000, key="public_question_text")
                st.form_submit_button("Find the evidence", type="primary", width="stretch",
                                      on_click=ask_evidence, args=(customer["customer_id"],))
            result = st.session_state.get("public_answer", {})
            if result.get("customer_id") == customer["customer_id"]:
                html(f'<div class="reason">{safe(result["answer"])}</div>')
                st.caption(result["provider"])
            else:
                html(empty_state("Start with a question", "Ask about repayment, customer intent or the reason behind the recommendation.", "⌕"))
            st.caption("Answers use customer facts and evidence rules. Financial actions require a separate review.")
        html(section("Lending facts", "Structured relationship context"))
        html(fields([{"label": "Relationship", "value": f'{view["metrics"]["tenure_months"]} months'},
                     {"label": "Recent payment bounces", "value": view["metrics"]["bounces_3m"]},
                     {"label": "Current rate", "value": f'{view["metrics"]["max_rate"]:g}%'},
                     {"label": "Days past due", "value": view["metrics"]["dpd"]}]))
    with right:
        html(section("Source conversations", "Trace every recommendation"))
        evidence = explain_action(view)["evidence"]
        if evidence:
            for item in evidence:
                html(evidence_card(item))
        else:
            st.caption("No supporting conversation has been selected for this recommendation.")
        with st.expander("All recorded conversations"):
            for interaction in view["interactions"]:
                html(evidence_card(interaction))
    with st.expander("Policy trace and evidence export"):
        st.dataframe(customer_analytics(view)["policy_trace"], hide_index=True, width="stretch")
        from public_app.repository import decision_hash
        packet = {"customer_id": customer["customer_id"], "as_of": view["metrics"]["evaluation_time"],
                  "decision_fingerprint": decision_hash(view["decision"]), "decision": view["decision"],
                  "policy_checks": explain_action(view)["checks"], "evidence": explain_action(view)["evidence"],
                  "scope": "Fictional customer evidence; review required; no financial execution", "contacts_excluded": True}
        st.download_button("Download decision evidence", json.dumps(packet, indent=2, ensure_ascii=False),
                           f'samvaad360-{customer["customer_id"]}-evidence.json', "application/json")


def render_reviews(repository, sandbox, portfolio):
    html(section("Review queue", "A human checkpoint before the next conversation"))
    st.caption("This visit’s fictional proposals. Approvals unlock a conversation rehearsal; they do not approve a real loan.")
    names = {c["customer_id"]: c["full_name"] for c in portfolio}
    reviews = st.session_state["public_reviews"]
    if not reviews:
        html(empty_state("Your review queue is clear", "Explore a customer, add the recommended action to review, then approve it to try the call studio.", "✓"))
        st.button("Explore selected customer →", type="primary", on_click=open_workspace,
                  args=(st.session_state["selected_customer"], "Customer 360"))
        return
    html(metric_grid([
        ("Pending review", sum(r["status"] == "PENDING_SIMULATION" for r in reviews), "Waiting for a fictional decision"),
        ("Approved for rehearsal", sum(r["status"] == "APPROVED_IN_SIMULATION" for r in reviews), "Call studio is available"),
        ("Declined", sum(r["status"] == "REJECTED_IN_SIMULATION" for r in reviews), "No contact action unlocked"),
        ("Visit proposals", len(reviews), "Isolated to this browser session"),
    ]))
    for record in reversed(reviews):
        status_label = {"PENDING_SIMULATION": "Pending review", "APPROVED_IN_SIMULATION": "Approved for rehearsal", "REJECTED_IN_SIMULATION": "Declined"}[record["status"]]
        with st.expander(f'{names.get(record["customer_id"], record["customer_id"])} · {status_label}',
                         expanded=record["status"] == "PENDING_SIMULATION" or record["id"] == st.session_state.get("public_review_open")):
            html(action_chip(record["decision"]["action_code"]))
            st.markdown(f'**{action_name(record["decision"])}**')
            st.write(record["decision"]["rationale"])
            fresh = profile(record["customer_id"], "snowflake" if repository.is_live else "snapshot")
            render_offer({**fresh, "decision": record["decision"]})
            if record["status"] == "PENDING_SIMULATION":
                with st.form("public_review_" + record["id"]):
                    st.selectbox("Review decision", ["APPROVED_IN_SIMULATION", "REJECTED_IN_SIMULATION"],
                                           key="review_outcome_" + record["id"],
                                           format_func=lambda v: "Approve for conversation rehearsal" if v == "APPROVED_IN_SIMULATION" else "Decline the proposal")
                    st.text_input("Review note", max_chars=500, key="review_note_" + record["id"],
                                  placeholder="Why is this a suitable fictional intervention?")
                    st.form_submit_button("Save review decision", type="primary", on_click=save_review, args=(record["id"],))
            else:
                st.caption("Review note: " + record["note"])
                if record["status"] == "APPROVED_IN_SIMULATION":
                    st.button("Open call studio →", type="primary", key="review_call_" + record["id"],
                              on_click=open_workspace, args=(record["customer_id"], "Call studio"))
    st.download_button("Export this visit’s review record", sandbox.export(), "samvaad360-simulation.json", "application/json")
    st.caption("Reviews are stored only for this session. A new or expired visit starts a fresh queue.")


def render_call(view, call_sandbox):
    customer, decision = view["customer"], view["decision"]
    html(section("Call studio", f'Conversation workspace for {customer["full_name"]}'))
    with st.expander("Telephone calling · existing or additional number", expanded=call_sandbox.current(customer["customer_id"]) is None):
        render_telephone(view, admit_telephone_action)
    st.subheader("Conversation lab")
    st.caption("Interactive voice & transcript simulation. No phone call is placed and no message is sent.")
    left, right = st.columns([1.55, 1], gap="large")
    current = call_sandbox.current(customer["customer_id"])
    objective = (current.get("decision_after") if current else None) or decision
    with right:
        with st.container(border=True):
            html('<div class="eyebrow">Conversation objective</div>')
            st.subheader(action_name(objective))
            if current and current.get("decision_after"):
                st.write("The borrower’s new context changes the plan for this visit. The earlier offer is not being continued.")
                st.caption(objective["rationale"])
            else:
                st.write(objective.get("script") or "Contact is restricted by the customer’s preferences.")
            html(chip("Calls permitted" if customer["consent_calls"] else "Call consent absent", "green" if customer["consent_calls"] else "red") +
                 chip("DND active" if customer["dnd"] else "DND clear", "red" if customer["dnd"] else "gray"))
            if visit_hold(customer["customer_id"]):
                html(chip("Contact on hold this visit", "red"))
                st.caption(visit_hold(customer["customer_id"]))
            st.caption("A current approved simulation review is required. The conversation asks permission and confirms identity before discussing terms.")
        with st.container(border=True):
            st.markdown("**A customer-controlled conversation**")
            for label, text in [("Permission first", "The borrower chooses whether the conversation continues."),
                                ("Identity before terms", "Financial details wait until account-holder confirmation."),
                                ("Opt-out is respected", "A stop request ends the simulation immediately."),
                                ("An officer can take over", "Support needs and complex decisions have a human handoff.")]:
                html(f'<div class="check-row"><span class="check-icon">✓</span><div><strong>{safe(label)}</strong><div class="small">{safe(text)}</div></div></div>')
    with left:
        if current is None:
            with st.container(border=True):
                if decision["action_code"] == "NO_ACTION":
                    html(empty_state("Contact is protected", "Customer preferences or policy checks prevent this call rehearsal.", "⊘"))
                    st.button("Start conversation rehearsal", type="primary", disabled=True, width="stretch")
                elif not call_sandbox.eligible_review(customer["customer_id"]):
                    html(empty_state("Review before reaching out", "Add this intervention to the review queue and approve it. Then return here to start a borrower conversation.", "◉"))
                    st.button("Prepare this proposal for review", type="primary", width="stretch", on_click=queue_action, args=(customer["customer_id"],))
                else:
                    html(empty_state("Ready for the next conversation", "Play the lender’s voice, choose a borrower reply and see how the conversation adapts.", "◉"))
                    st.button("Start conversation rehearsal", type="primary", width="stretch", on_click=call_action,
                              args=("start", customer["customer_id"]))
        else:
            state_labels = {"AWAIT_PERMISSION": "Waiting for permission", "AWAIT_IDENTITY": "Confirming account holder",
                            "ACTIVE": "Conversation in progress", "ENDED": "Conversation complete"}
            html(f'<div class="call-status">◉ {safe(state_labels.get(current["state"], current["state"]))} · Fictional borrower simulation</div>')
            with st.container(border=True):
                html('<div class="transcript">' + ''.join(
                    f'<div class="turn {"assistant" if str(turn["role"]).lower() in {"assistant", "lender", "agent"} else "customer"}">'
                    f'<span class="speaker">{"Samvaad assistant" if str(turn["role"]).lower() in {"assistant", "lender", "agent"} else "Borrower"}</span>'
                    f'{safe(turn["text"])}</div>' for turn in current["turns"]) + '</div>')
                latest = next((t for t in reversed(current["turns"]) if str(t["role"]).lower() in {"assistant", "lender", "agent"}), None)
                if latest:
                    render_browser_voice(latest["text"], key=f'voice_{current["session_id"]}_{len(current["turns"])}')
            if current["state"] != "ENDED":
                suggestions = {"AWAIT_PERMISSION": ["Yes, you may continue", "Stop calling me"],
                               "AWAIT_IDENTITY": ["Yes, I am the account holder", "This is not my account"],
                               "ACTIVE": ["I am interested", "I lost my job", "Please connect an officer", "Stop calling me"]}
                st.caption("Choose a fictional borrower reply, or type your own:")
                options = suggestions.get(current["state"], [])
                for index, column in enumerate(st.columns(2, gap="small")):
                    with column:
                        for reply in options[index::2]:
                            st.button(reply, key=f'call_reply_{current["session_id"]}_{reply}', width="stretch", on_click=call_action,
                                      args=("reply", current["session_id"], reply))
                with st.form("borrower_reply_" + current["session_id"], clear_on_submit=True):
                    field_key = "borrower_reply_text_" + current["session_id"]
                    st.text_input("Borrower reply", max_chars=500, key=field_key, placeholder="Enter a fictional response")
                    st.form_submit_button("Send simulated reply", type="primary", width="stretch", on_click=call_action,
                                          args=("reply", current["session_id"], None, field_key))
                st.button("End rehearsal", key="end_" + current["session_id"], on_click=call_action,
                          args=("end", current["session_id"]))
            else:
                outcome = current.get("outcome") or "Completed"
                st.success("Recorded outcome: " + str(outcome).replace("_", " ").capitalize())
                if current.get("decision_after"):
                    html(section("New conversation changed the plan", "Evidence → revised policy decision"))
                    render_comparison(current["decision_before"], current["decision_after"], "After the borrower’s new context")
                    if current.get("new_evidence"):
                        html(evidence_card(current["new_evidence"]))
                    st.caption("The borrower’s actual simulated reply was evaluated by the decision rules. This visit’s overlay does not change saved customer data.")
                invitation = current.get("simulated_invitation")
                if invitation:
                    with st.container(border=True):
                        html(chip("Conditional invitation", "green") + chip("Not delivered", "gray"))
                        st.markdown("**Fictional offer summary**")
                        render_offer({**view, "decision": current["decision"]})
                        st.caption("Reference: " + invitation["invitation_id"] + ". Further checks and real lender approval would be required.")
                    st.info("A conditional invitation was generated for this simulation. Nothing was sent.")
                st.download_button("Download conversation record", call_sandbox.export(current["session_id"]),
                                   "samvaad360-conversation.json", "application/json")
                st.caption("The record confirms a simulation. No financial action, link delivery or real call occurred.")
                try:
                    eligible = call_sandbox.eligible_review(customer["customer_id"])
                except DemoError:
                    eligible = None
                if eligible:
                    st.button("Start another rehearsal", key="restart_" + current["session_id"], on_click=call_action,
                              args=("start", customer["customer_id"]))


try:
    admission = usage_guard().admit(visitor_identity(), kind="browse")
    if not admission.allowed:
        st.warning(f"This workspace is receiving too many requests. Try again in {admission.retry_after} seconds.")
        st.stop()
    repository = visit_reader()
    source = "snowflake" if repository.is_live else "snapshot"
    portfolio = customers(source)
except Exception as error:
    logging.getLogger("samvaad.public").error("Public connection failure: %s", type(error).__name__)
    st.error("The customer workspace is temporarily unavailable. Please try again shortly.")
    st.stop()

with st.sidebar:
    html('<div class="brand"><div class="brand-icon">s</div><div><div class="brand-name">samvaad<span>360</span></div>'
         '<div class="brand-tag">Customer intelligence</div></div></div>')
    html('<div class="sidebar-label">Lending workspace</div>')
    st.selectbox("Customer", [c["customer_id"] for c in portfolio], key="selected_customer",
                 format_func=lambda cid: next(f'{c["full_name"]} · {cid}' for c in portfolio if c["customer_id"] == cid))
    html('<div class="sidebar-label">Data connection</div>')
    if repository.is_live:
        st.success("Data source: Snowflake")
    else:
        st.warning("Data source: offline synthetic snapshot")
        st.caption("Snapshot reference: " + repository.reference)
    shared_count = len(reader().customers())
    visit_count = len(relationship_sandbox().state.get("customers", {}))
    html(f'<div class="sidebar-note">{shared_count} shared fictional customers'
         + (f' + {visit_count} visit-only relationships' if visit_count else '')
         + '<br>Shared hourly snapshot · usage protected</div>')
    status = repository.source_status() if hasattr(repository, "source_status") else {}
    if status.get("stale"):
        st.caption("Last successful Snowflake snapshot. Refresh is paused; saved facts remain browsable.")
    st.divider()
    html('<div class="sidebar-label">Explore a story</div>')
    for cid, label in [("C0001", "Ravi · support"), ("C0002", "Ananya · retention"),
                       ("C0003", "Imran · growth"), ("C0004", "Neha · consent")]:
        st.button(label, key="sidebar_" + cid, width="stretch", on_click=open_workspace, args=(cid,))
    st.divider()
    html('<div class="sidebar-note"><strong>Public demo</strong><br>Fictional lending records. Reviews and voice conversations are simulations for this visit.</div>')
    with st.expander("Start here · Judge's guide"):
        st.write("1. Explore Imran's growth recommendation and its cited evidence.")
        st.write("2. Add it to Review queue, approve the fictional proposal, and open Call studio.")
        st.write("3. Choose ‘I lost my job’. See the growth offer become a supportive officer handoff.")
        st.write("4. Open Customer hub to try onboarding, a validated import, and contact withdrawal.")
        st.caption("All exercises use fictional data. New records and reviews belong only to your visit.")
        st.markdown("[Public source and setup](https://github.com/Cherie05/samvaad360) · "
                    "[Submission guide](https://github.com/Cherie05/samvaad360/blob/main/docs/submission-guide.md) · "
                    "[Prototype deck](https://github.com/Cherie05/samvaad360/blob/main/submission/Samvaad360_Prototype_Deck.pdf)")
        st.markdown("[Watch the product walkthrough](https://github.com/Cherie05/samvaad360/releases/download/hackathon-submission-2026/Samvaad360_Demo.mp4)")

html('<div class="topline"><span>WORKSPACE / CUSTOMER RELATIONSHIPS</span>'
     f'<span class="live-pill"><span class="live-dot"></span>{"Protected Snowflake snapshot" if repository.is_live else "Snapshot demonstration"}</span></div>')
if not repository.is_live:
    st.warning("The live Snowflake connection is unavailable. You are exploring a bundled fictional snapshot. "
               "The site is not claiming a live Snowflake or Cortex request in this mode.")

for flash_key, display in [("public_flash", st.success), ("public_flash_error", st.error)]:
    if flash_key in st.session_state:
        display(st.session_state.pop(flash_key))

if "public_reviews" not in st.session_state:
    st.session_state["public_reviews"] = []
if "public_calls" not in st.session_state:
    st.session_state["public_calls"] = {}
sandbox = ReviewSandbox(st.session_state["public_reviews"], repository)
call_sandbox = CallSandbox(st.session_state["public_calls"], repository, st.session_state["public_reviews"])

try:
    tabs = st.tabs(["Command center", "Customer 360", "Evidence desk", "Review queue", "Call studio", "Customer hub"],
                   default=st.session_state.get("workspace_tabs", "Command center"),
                   key="workspace_tabs", on_change="rerun")
    if tabs[0].open:
        with tabs[0]:
            render_command_center(source)
    if any(tab.open for tab in tabs[1:]):
        view = profile(st.session_state["selected_customer"], source)
        if tabs[1].open:
            with tabs[1]:
                render_customer(view)
        if tabs[2].open:
            with tabs[2]:
                render_evidence(view, repository)
        if tabs[3].open:
            with tabs[3]:
                render_reviews(repository, sandbox, portfolio)
        if tabs[4].open:
            with tabs[4]:
                render_call(view, call_sandbox)
        if tabs[5].open:
            with tabs[5]:
                render_relationship_hub(reader(), sandbox=relationship_sandbox(), run_action=run_relationship_action,
                                        selected_cid=st.session_state["selected_customer"])
except DemoError as error:
    st.error(str(error))
except Exception as error:
    logging.getLogger("samvaad.public").error("Public workflow failure: %s", type(error).__name__)
    st.error("This operation could not complete. Please try again. Connection details remain private.")

html('<div class="footer"><span>Samvaad 360 · Customer intelligence, with context.</span>'
     '<span>Synthetic hackathon prototype · Lending journey · No real calls or financial execution</span></div>')
