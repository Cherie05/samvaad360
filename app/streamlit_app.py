"""Samvaad 360 portal. Run: python -m streamlit run app/streamlit_app.py."""
from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

import streamlit as st

# Streamlit starts with app/ on sys.path; include the repo package locally.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from samvaad.factory import create_service
from samvaad.models import Actor, ActionError
from app.voice_ui import render_voice_lab

logger = logging.getLogger("samvaad.ui")


st.set_page_config(
    page_title="Samvaad 360 · Customer intelligence",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_service(backend: str, db_path: str):
    # Include the configured path in the key so independent local demos/tests
    # cannot share one cached connection. The factory owns configuration.
    return create_service(backend=backend, db_path=db_path or None)


def escaped(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def label(value: Any) -> str:
    return str(value or "—").replace("_", " ").title()


def money(value: Any) -> str:
    try:
        return f"₹{float(value):,.0f}"
    except (ValueError, TypeError):
        return "—"


def date_label(value: Any) -> str:
    if not value:
        return "—"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y · %H:%M IST")
    except ValueError:
        return str(value)


def to_rows(records: list[dict]) -> list[dict]:
    """Keep tables readable when records include nested payloads."""
    return [
        {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
         for k, v in row.items()}
        for row in records
    ]


def badge(value: str, kind: str = "") -> str:
    return f'<span class="badge {escaped(kind)}">{escaped(label(value))}</span>'


def show_error(error: Exception) -> None:
    if isinstance(error, ActionError):
        code = getattr(error, "code", "ACTION_BLOCKED")
        message = getattr(error, "message", str(error))
        st.error(f"{message} ({code})")
    else:
        logger.error("Unexpected UI error: %s", type(error).__name__)
        st.error("The request could not be completed. Please check the application logs.")


def changed(message: str) -> None:
    st.session_state["flash"] = message
    st.rerun()


def action_name(action: dict) -> str:
    names = {
        "RETENTION_RATE_REVIEW": "Capped retention offer",
        "RETENTION_OFFER": "Capped retention offer",
        "RETENTION": "Capped retention offer",
        "RETENTION_RATE_MATCH_CALL": "Capped retention rate review",
        "TOPUP_PREAPPROVAL": "Conditional top-up invitation",
        "TOPUP_INVITATION": "Conditional top-up invitation",
        "TOPUP": "Conditional top-up invitation",
        "TOPUP_PREAPPROVAL_CALL": "Conditional top-up invitation",
        "HARDSHIP_CALLBACK": "Supportive hardship callback",
        "HARDSHIP": "Supportive hardship callback",
        "HARDSHIP_RESTRUCTURE_CALL": "Supportive hardship callback",
        "NO_ACTION": "No eligible action",
    }
    code = action.get("action_code", "")
    return names.get(code, label(code))


def display_offer(offer: dict) -> None:
    if not offer:
        return
    terms = []
    for key, value in offer.items():
        if key.startswith("_") or value is None:
            continue
        if key == "amount" and "topup_amount" in offer:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif any(part in key.lower() for part in ("amount", "principal", "outstanding")):
            value = money(value)
        elif "bps" in key.lower():
            value = f"{value} bps"
        elif ("rate" in key.lower() or key.endswith("_pct")) and isinstance(value, (int, float)):
            value = f"{value:g}%"
        terms.append(
            '<div class="term">'
            f'<span class="term-label">{escaped(label(key))}</span>'
            f'<span class="term-value">{escaped(value)}</span></div>'
        )
    st.markdown("".join(terms), unsafe_allow_html=True)


def evidence_cards(action: dict, interactions: list[dict]) -> None:
    evidence_ids = action.get("evidence_ids") or []
    if not evidence_ids:
        st.caption("This action has no conversation citations. Review structured eligibility before approval.")
        return
    indexed = {i.get("interaction_id"): i for i in interactions}
    st.markdown("**Supporting conversations**")
    for evidence_id in evidence_ids:
        item = indexed.get(evidence_id)
        if item:
            st.markdown(
                '<div class="evidence-card">'
                f'<div class="evidence-id">{escaped(evidence_id)} · {escaped(label(item.get("channel")))}</div>'
                f'<div class="evidence-text">{escaped(item.get("text", ""))}</div>'
                '</div>', unsafe_allow_html=True,
            )
        else:
            st.warning(f"Evidence {evidence_id} is unavailable in this customer's timeline.")


def recommendation_card(action: dict, interactions: list[dict], show_evidence: bool = True) -> None:
    status = str(action.get("status", "RECOMMENDED"))
    kind = "badge-teal" if status in ("APPROVED", "COMPLETED") else "badge-orange"
    if status in ("REJECTED", "BLOCKED", "FAILED", "CANCELLED", "EXPIRED"):
        kind = "badge-red"
    rationale = action.get("rationale", "")
    if isinstance(rationale, list):
        rationale = " · ".join(str(x) for x in rationale)
    approval_role = action.get("approval_role")
    approval_text = "Service workflow · no financial offer" if approval_role == "AUTO" else f"{label(approval_role)} approval"
    st.markdown(
        '<div class="nba-card">'
        '<div class="eyebrow">Next best action</div>'
        f'{badge(status, kind)}'
        f'<div class="nba-title">{escaped(action_name(action))}</div>'
        f'<div class="nba-body">{escaped(rationale)}</div>'
        f'<div class="small-note">{escaped(action.get("action_id", "Preview"))} · '
        f'{escaped(label(action.get("channel")))} · '
        f'{escaped(approval_text)}</div>'
        '</div>', unsafe_allow_html=True,
    )
    if action.get("offer"):
        with st.expander("Proposed terms", expanded=True):
            display_offer(action["offer"])
            st.caption("Fictional demo policy. Financial terms require the designated approval.")
    if show_evidence:
        evidence_cards(action, interactions)
    if action.get("script"):
        with st.expander("Contact script"):
            st.write(action["script"])


def customer_header(customer: dict, metrics: dict) -> None:
    name = str(customer.get("name", "Customer"))
    initials = "".join(part[0] for part in name.split()[:2]).upper()
    dnd = customer.get("dnd", False)
    tags = [badge(customer.get("segment", "Customer"))]
    tags.append(badge("Calls consented" if customer.get("consent_calls") else "Calls not consented", "badge-teal" if customer.get("consent_calls") else "badge-orange"))
    tags.append(badge("Marketing consented" if customer.get("consent_marketing") else "Marketing not consented", "badge-teal" if customer.get("consent_marketing") else "badge-orange"))
    if dnd:
        tags.append(badge("Do not disturb", "badge-red"))
    st.markdown(
        '<div class="customer-card"><div class="customer-heading">'
        f'<div class="avatar">{escaped(initials)}</div><div>'
        f'<div class="customer-name">{escaped(name)}</div>'
        f'<div class="customer-meta">{escaped(customer.get("id"))} · '
        f'{escaped(customer.get("city"))} · {escaped(label(customer.get("language")))}</div>'
        '</div></div>'
        f'<div class="tag-row">{"".join(tags)}</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Outstanding balance", money(metrics.get("total_outstanding")))
    c2.metric("Monthly EMI", money(metrics.get("total_emi")))
    c3.metric("Days past due", str(metrics.get("dpd", "—")))
    risk = metrics.get("churn_risk", "—")
    c4.metric("Churn priority score", str(risk))
    st.caption("Priority scores are demo rule-based heuristics; they are not predicted probabilities.")


def synthetic_interaction_form(service, selected_id: str, actor: Actor, is_demo: bool) -> None:
    if not is_demo:
        return
    with st.expander("Add a synthetic interaction"):
        st.caption("Offline signal extraction · Add fictional customer speech to this local demo. Intent, sentiment, entities, and the current decision are recalculated immediately. Generate the next best action afterward to refresh the queue.")
        if actor.role not in {"ANALYST", "ADMIN"}:
            st.info("An analyst or demo administrator can add interactions. Switch to an analyst persona for this demonstration.")
            return
        with st.form(f"interaction_form_{selected_id}", clear_on_submit=True):
            channel = st.selectbox("New interaction channel", ["EMAIL", "CHAT", "CALL_IN", "COMPLAINT"], key=f"interaction_channel_{selected_id}")
            text = st.text_area("Interaction text", placeholder="Customer: I was laid off last week. Can an officer discuss support options?", max_chars=20000, key=f"interaction_text_{selected_id}")
            submitted = st.form_submit_button("Add synthetic interaction", type="primary")
        if submitted:
            try:
                result = service.add_interaction(selected_id, text, channel=channel, actor=actor)
                changed(f"Synthetic interaction {result.get('interaction_id', '')} added. Offline signals and the current decision were refreshed; review the evidence, then generate the next best action.")
            except Exception as error:
                show_error(error)


def borrower_view(service, selected_id: str, actor: Actor, view: dict, is_demo: bool) -> None:
    customer = view.get("customer") or {}
    metrics = view.get("metrics") or {}
    interactions = view.get("interactions") or []
    customer_header(customer, metrics)
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        st.markdown('<div class="section-title">Customer journey</div>', unsafe_allow_html=True)
        synthetic_interaction_form(service, selected_id, actor, is_demo)
        channels = sorted({str(i.get("channel", "Unknown")) for i in interactions})
        chosen_channel = st.selectbox("Interaction channel", ["All channels"] + channels, label_visibility="collapsed")
        displayed = sorted(interactions, key=lambda item: str(item.get("ts", "")), reverse=True)
        if chosen_channel != "All channels":
            displayed = [i for i in displayed if str(i.get("channel")) == chosen_channel]
        if not displayed:
            st.info("No interactions match this selection.")
        for item in displayed:
            sentiment = item.get("sentiment", "Unknown")
            sentiment_text = f"Sentiment {sentiment}" if isinstance(sentiment, (int, float)) else label(sentiment)
            st.markdown(
                '<div class="timeline-item"><div class="timeline-head">'
                f'<span class="timeline-channel">{escaped(label(item.get("channel")))}</span>'
                f'<span class="timeline-time">{escaped(date_label(item.get("ts")))}</span></div>'
                f'<div class="timeline-text">{escaped(item.get("text", ""))}</div>'
                '<div class="tag-row">'
                f'{badge(item.get("intent", "Unknown"))}{badge(sentiment_text)}'
                '</div>'
                f'<div class="timeline-footer">Evidence: {escaped(item.get("interaction_id"))}</div></div>',
                unsafe_allow_html=True,
            )
            if item.get("entities"):
                with st.expander(f"Extracted entities · {item.get('interaction_id')}"):
                    st.json(item["entities"])
        with st.expander("Loans and payment history"):
            st.markdown("**Loans**")
            st.dataframe(to_rows(view.get("loans") or []), use_container_width=True, hide_index=True)
            st.markdown("**Payments**")
            st.dataframe(to_rows(view.get("payments") or []), use_container_width=True, hide_index=True)
    with right:
        st.markdown('<div class="section-title">Recommended response</div>', unsafe_allow_html=True)
        queued = view.get("recommendation")
        current = view.get("current_decision")
        decision_changed = bool(current and queued and queued.get("action_id") and (
            queued.get("action_code") != current.get("action_code") or queued.get("offer") != current.get("offer")
        ))
        recommendation = current if decision_changed else queued
        if decision_changed:
            st.warning("Latest evidence changes the suggested response. Generate the next best action to replace the previous queued recommendation.")
            st.caption(f"Previous queue: {action_name(queued)} · {label(queued.get('status'))} · {queued.get('action_id')}")
        if recommendation:
            recommendation_card(recommendation, interactions)
        else:
            st.markdown('<div class="empty-card">No queued action yet.<br>Evaluate this customer against the demo action catalogue.</div>', unsafe_allow_html=True)
        if st.button("Generate next best action", key="generate_nba", type="primary", use_container_width=True):
            try:
                result = service.recommend(selected_id, actor)
                changed(f"Action {result.get('action_id', '')} is now {label(result.get('status'))}.")
            except Exception as error:
                show_error(error)
        st.caption("Queues a recommendation only. The selected operator cannot approve on another person's behalf.")
        with st.expander("Eligibility and customer facts"):
            foir = metrics.get("foir")
            st.write(f"Monthly income: {money(customer.get('income'))}")
            if isinstance(foir, (int, float)):
                st.write(f"FOIR: {foir:.1%}" if foir <= 1 else f"FOIR: {foir:.1f}%")
            st.write(f"Collections priority: {metrics.get('collections_risk', '—')}")
            st.write(f"Top-up eligible: {'Yes' if metrics.get('topup_eligible') else 'No'}")
            st.write(f"Top-up bound: {money(metrics.get('topup_amount'))}")
            codes = metrics.get("reason_codes") or []
            st.write("Reason codes:", ", ".join(map(str, codes)) or "None")
            if metrics.get("data_quality_flags"):
                st.warning("Manual review needed: " + ", ".join(map(str, metrics["data_quality_flags"])))
        with st.expander("Consent controls"):
            st.caption("Record this synthetic customer's opt-out. This revokes contact consent and cancels affected queued actions.")
            confirmed = st.checkbox("Customer requested no further contact", key=f"optout_confirm_{selected_id}")
            if st.button("Record customer opt-out", disabled=not confirmed, key=f"optout_{selected_id}"):
                try:
                    service.revoke_consent(selected_id, actor)
                    changed("Customer opt-out recorded. Affected pending contacts were cancelled.")
                except Exception as error:
                    show_error(error)


def approval_view(service, actor: Actor, selected_id: str, is_demo: bool) -> None:
    st.subheader("Review before execution")
    st.caption(f"Current operator: {actor.user_id} · {label(actor.role)}. Approvals are validated by the backend.")
    queue = service.actions()
    actionable = [a for a in queue if a.get("status") in ("PENDING_APPROVAL", "RECOMMENDED", "APPROVED")]
    scope = st.radio("Queue scope", ["All customers", "Selected customer"], horizontal=True, key="approval_scope")
    if scope == "Selected customer":
        actionable = [a for a in actionable if a.get("customer_id") == selected_id]
    if not actionable:
        st.info("No actions awaiting review or execution. Generate an action from Customer 360.")
        return
    by_id = {a["action_id"]: a for a in actionable}
    action_id = st.selectbox(
        "Action to review", list(by_id),
        format_func=lambda aid: f"{by_id[aid].get('customer_name', by_id[aid].get('customer_id'))} · {action_name(by_id[aid])} · {label(by_id[aid].get('status'))}",
        key="action_review",
    )
    action = by_id[action_id]
    snapshot = service.customer360(action["customer_id"])
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        recommendation_card(action, snapshot.get("interactions") or [])
    with right:
        status = action.get("status")
        if status in ("PENDING_APPROVAL", "RECOMMENDED"):
            required = action.get("approval_role", "")
            permitted = actor.role == required
            st.markdown("**Approval decision**")
            if not permitted:
                st.info(f"This action requires {label(required)} approval. Your current role is {label(actor.role)}.")
            note = st.text_area("Review note", placeholder="Reason for approving or declining this action", key=f"approval_note_{action_id}")
            approve, reject = st.columns(2)
            if approve.button("Approve action", type="primary", disabled=not permitted, key=f"approve_{action_id}", use_container_width=True):
                try:
                    service.approve_action(action_id, actor, decision="APPROVE", note=note)
                    changed(f"{action_id} approved by {actor.user_id}.")
                except Exception as error:
                    show_error(error)
            if reject.button("Reject action", disabled=not permitted, key=f"reject_{action_id}", use_container_width=True):
                try:
                    service.approve_action(action_id, actor, decision="REJECT", note=note)
                    changed(f"{action_id} rejected by {actor.user_id}.")
                except Exception as error:
                    show_error(error)
        elif status == "APPROVED":
            st.success(f"Approved by {action.get('approved_by', 'authorized workflow')}")
            if is_demo:
                st.markdown("**Simulated contact runner**")
                st.caption("Runs as local-runner · Automation. No real email, phone call, or credit decision is sent. Approval, consent, and eligibility checks still apply.")
                outcome = st.selectbox("Synthetic customer response", ["ACCEPT", "CALLBACK", "OPT_OUT", "NO_ANSWER"], format_func=label, key=f"outcome_{action_id}")
                if st.button("Run simulated action", type="primary", key=f"execute_{action_id}", use_container_width=True):
                    try:
                        result = service.execute_action(action_id, Actor("local-runner", "AUTOMATION"), mode="simulate", outcome=outcome)
                        changed(f"Simulation completed: {label(result.get('outcome', outcome))}. The customer timeline and audit history are updated.")
                    except Exception as error:
                        show_error(error)
            else:
                st.info("Execute this approved action through the configured automation worker.")
        st.divider()
        st.caption("Approving an action authorizes only its stored terms. Changed policy, consent, or eligibility can still block execution.")


def render_citations(citations: list[dict]) -> None:
    if not citations:
        return
    with st.expander(f"Supporting evidence ({len(citations)})", expanded=True):
        for citation in citations:
            st.markdown(
                '<div class="evidence-card">'
                f'<div class="evidence-id">{escaped(citation.get("interaction_id"))} · '
                f'{escaped(citation.get("customer_id"))} · {escaped(label(citation.get("channel")))}</div>'
                f'<div class="evidence-text">{escaped(citation.get("text", ""))}</div>'
                '</div>', unsafe_allow_html=True,
            )


def ask_view(service, actor: Actor, selected_id: str, customer: dict) -> None:
    st.subheader("Ask Samvaad")
    st.caption("Investigate the customer journey with source evidence. The assistant cannot approve offers or execute contacts.")
    scope = st.radio("Question scope", ["Selected customer", "Portfolio"], horizontal=True, key="question_scope")
    scoped_id = selected_id if scope == "Selected customer" else None
    scope_key = scoped_id or "portfolio"
    conversations = st.session_state.setdefault("conversations", {})
    messages = conversations.setdefault(scope_key, [])
    st.caption(f"Investigating {customer.get('name', selected_id)}" if scoped_id else "Investigating the synthetic lending portfolio")
    examples = ["Why might this customer leave?", "What is the next best action?", "Summarize the customer journey"] if scoped_id else ["Show borrowers 1-30 DPD by city", "Which borrowers mentioned job loss?", "What is the personal-loan bounce rate in the last 3 months?"]
    example = st.selectbox("Suggested question", examples, key=f"suggested_{scope_key}")
    prompt_from_button = example if st.button("Ask selected question", key=f"ask_example_{scope_key}") else None
    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["text"])
            if message.get("citations"):
                render_citations(message["citations"])
            if message.get("provider"):
                st.caption(f"Provider: {message['provider']} · Tools: {', '.join(map(str, message.get('tools', [])))}")
    typed_prompt = st.chat_input("Ask about signals, eligibility, or the customer's journey", key=f"chat_{scope_key}")
    prompt = prompt_from_button or typed_prompt
    if prompt:
        messages.append({"role": "user", "text": prompt})
        with st.spinner("Reviewing customer evidence…"):
            try:
                result = service.ask(prompt, customer_id=scoped_id, actor=actor)
                messages.append({
                    "role": "assistant", "text": result.get("answer", "No answer returned."),
                    "citations": result.get("citations") or [], "provider": result.get("provider", "Unknown"),
                    "tools": result.get("tools") or [],
                })
            except Exception as error:
                if isinstance(error, ActionError):
                    error_text = f"Unable to answer: {error.message} ({error.code})"
                else:
                    logger.error("Unexpected assistant UI error: %s", type(error).__name__)
                    error_text = "Unable to answer. Please check the application logs."
                messages.append({"role": "assistant", "text": error_text})
        st.rerun()
    if messages and st.button("Clear this conversation", key=f"clear_chat_{scope_key}"):
        conversations[scope_key] = []
        st.rerun()


def history_view(service, selected_id: str) -> None:
    st.subheader("Actions and outcomes")
    scope = st.radio("History scope", ["Selected customer", "All customers"], horizontal=True, key="history_scope")
    customer_id = selected_id if scope == "Selected customer" else None
    actions = service.actions()
    if customer_id:
        actions = [a for a in actions if a.get("customer_id") == customer_id]
    if actions:
        columns = ["action_id", "customer_name", "action_code", "status", "approved_by", "attempts", "outcome", "execution_mode", "created_at"]
        st.dataframe(to_rows([{key: action.get(key) for key in columns} for action in actions]), use_container_width=True, hide_index=True)
    else:
        st.info("No actions have been queued in this scope.")
    st.markdown("**Offer links**")
    offers = service.offers(customer_id)
    if not offers:
        st.caption("Offer links appear after an approved top-up action is executed.")
    for offer in offers:
        st.write(f"{offer.get('offer_id', offer.get('action_id', 'Offer'))} · {label(offer.get('status'))}")
        url = offer.get("url") or offer.get("offer_url")
        if url:
            st.link_button("Open demo offer", str(url))
        st.caption(f"Expires: {date_label(offer.get('expires_at'))}")
    st.markdown("**Audit trail**")
    records = service.audit(customer_id=customer_id)
    if records:
        st.dataframe(to_rows(records), use_container_width=True, hide_index=True)
    else:
        st.caption("Review and execution events will appear here.")


def main() -> None:
    css_path = Path(__file__).with_name("styles.css")
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    try:
        service = get_service(os.environ.get("SAMVAAD_BACKEND", "local"), os.environ.get("SAMVAAD_DB_PATH", ""))
    except Exception as error:
        show_error(error)
        st.stop()
    backend_label = str(getattr(service, "backend_label", "Local demo"))
    is_demo = bool(getattr(service, "is_demo", any(word in backend_label.lower() for word in ("local", "demo", "sqlite"))))
    with st.sidebar:
        st.markdown('<div class="samvaad-brand">samvaad<span>360</span></div><div class="brand-subtitle">Customer intelligence workspace</div>', unsafe_allow_html=True)
        if is_demo:
            st.caption("DEMO ROLE SIMULATION")
            operators = {"Meera · Analyst": Actor("meera", "ANALYST"), "Arjun · Retention manager": Actor("arjun", "MANAGER"), "Kavya · Credit officer": Actor("kavya", "CREDIT"), "Farah · Support analyst": Actor("farah", "ANALYST")}
            operator_name = st.selectbox("Demo operator", list(operators), key="demo_operator")
            actor = operators[operator_name]
            st.caption("Switch personas to demonstrate role permissions. This is local role simulation, not authentication.")
        else:
            trusted_user = getattr(st, "user", None)
            user_id = None
            for key in ("user_name", "email", "sub"):
                if trusted_user is not None:
                    try:
                        user_id = trusted_user.get(key)
                    except (AttributeError, KeyError):
                        user_id = getattr(trusted_user, key, None)
                if user_id:
                    break
            if not user_id:
                st.error("Authenticated viewer identity is required. No operator role is assigned.")
                st.stop()
            try:
                actor = service.resolve_actor(str(user_id))
            except Exception as error:
                show_error(error)
                st.stop()
            st.write(f"{actor.user_id} · {label(actor.role)}")
        st.divider()
        st.caption("CUSTOMER LOOKUP")
        search = st.text_input("Search customers", placeholder="Name, ID, or city", key="customer_search")
        try:
            customers = service.list_customers(search=search)
        except Exception as error:
            show_error(error)
            st.stop()
        if not customers:
            st.info("No customers found. Clear the search to continue.")
            st.stop()
        customer_map = {str(c.get("id", c.get("customer_id"))): c for c in customers}
        selected_id = st.selectbox("Customer", list(customer_map), index=list(customer_map).index("C0002") if "C0002" in customer_map else 0, format_func=lambda cid: f"{customer_map[cid].get('name', cid)} · {cid}", key="customer_picker")
        st.divider()
        st.caption(f"Backend: {backend_label}")
        if is_demo:
            with st.expander("Demo controls"):
                st.caption("Restores synthetic fixtures and removes local actions, offers, and audit events.")
                confirm_reset = st.checkbox("Reset this local demo data", key="confirm_reset")
                if st.button("Reset local demo", disabled=not confirm_reset, key="reset_demo"):
                    try:
                        service.reset_demo(Actor("demo-admin", "ADMIN"))
                        st.session_state.pop("conversations", None)
                        for key in list(st.session_state):
                            if key.startswith("voice_"):
                                st.session_state.pop(key, None)
                        changed("Local synthetic demo has been reset.")
                    except Exception as error:
                        show_error(error)
    st.markdown('<div class="eyebrow">Lending · Customer 360 + Next best action</div><div class="workspace-title">Every interaction. A clearer next step.</div><div class="workspace-subtitle">Bring repayment facts and customer conversations together, then act with evidence and approval.</div>', unsafe_allow_html=True)
    if is_demo:
        st.markdown('<div class="local-banner"><strong>Local working demo</strong> · Synthetic customer data · SQLite database · Deterministic offline analysis and answers · Simulated contacts</div>', unsafe_allow_html=True)
    # Keep this root position stable. Conditional feedback used to move the
    # stateful tab container between delta paths during an early rerun.
    feedback = st.empty()
    if "flash" in st.session_state:
        feedback.success(st.session_state.pop("flash"))
    try:
        portfolio = service.portfolio()
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Customers", portfolio.get("total_customers", portfolio.get("customers", len(customers))))
        p2.metric("Risk review", portfolio.get("at_risk", portfolio.get("high_churn", portfolio.get("high_churn_risk", "—"))))
        p3.metric("Top-up eligible", portfolio.get("topup_eligible", portfolio.get("eligible_topup", "—")))
        p4.metric("Awaiting approval", portfolio.get("pending_approval", portfolio.get("pending_approvals", "—")))
        view = service.customer360(selected_id)
        customer = view.get("customer") or customer_map[selected_id]
        borrower, approvals, ask, history, voice = st.tabs(["Customer 360", "Approvals & execution", "Ask Samvaad", "Action history", "Voice lab"], key="workspace_tab", on_change="rerun")
        with borrower:
            borrower_view(service, selected_id, actor, view, is_demo)
        with approvals:
            approval_view(service, actor, selected_id, is_demo)
        with ask:
            ask_view(service, actor, selected_id, customer)
        with history:
            history_view(service, selected_id)
        with voice:
            render_voice_lab(service, selected_id, actor, is_demo)
    except Exception as error:
        show_error(error)
    st.divider()
    st.caption("Samvaad 360 · Lender-first hackathon prototype · Fictional policy and synthetic outcomes · Snowflake/Cortex migration pending")


if __name__ == "__main__":
    main()
