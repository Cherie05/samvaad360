"""Private, synthetic Snowflake-hosted Customer 360 hackathon demonstration."""
import json
import logging
from pathlib import Path

import streamlit as st
from snowflake.snowpark.context import get_active_session

from demo_repository import DemoError, DemoRepository

st.set_page_config(page_title="Samvaad 360", page_icon="◉", layout="wide")
st.markdown("""<style>
.stApp {background:#f5f7fc;color:#18223a}
[data-testid="stMetric"] {background:white;border:1px solid #dfe5f2;border-radius:12px;padding:14px}
h1,h2,h3 {color:#263d81} .block-container {padding-top:2rem}
</style>""", unsafe_allow_html=True)
st.title("Samvaad 360")
st.caption("Customer journeys and next best actions · Insurance & Lending track · Lender demonstration")

try:
    settings = json.loads(Path(__file__).with_name("demo_settings.json").read_text(encoding="utf-8"))
    viewer = st.user.get("user_name", "")
    repository = DemoRepository(get_active_session(), settings, viewer)
    customers = repository.customers()
except DemoError as error:
    st.error(str(error))
    st.stop()
except Exception as error:
    logging.getLogger("samvaad.cloud").error("Cloud startup failure: %s", type(error).__name__)
    st.error("Cloud startup is incomplete. Check the fixture import, app settings and account permissions.")
    st.stop()

st.sidebar.markdown("### Workspace")
st.sidebar.write(f"Signed in as **{viewer}**")
st.sidebar.caption("Private hackathon app · synthetic data")
if st.sidebar.button("Refresh cloud data"):
    st.rerun()
customer_id = st.sidebar.selectbox("Customer", [c["customer_id"] for c in customers],
                                  format_func=lambda cid: next(f"{c['full_name']} · {cid}" for c in customers if c["customer_id"] == cid))
st.info("Synthetic lending data. Review approvals are demo records; financial changes, invitations and external calls are disabled.")

try:
    view = repository.customer360(customer_id)
    metrics, decision, customer = view["metrics"], view["decision"], view["customer"]
    tabs = st.tabs(["Customer 360", "Ask with evidence", "Review queue", "Conversation handoff"])
    with tabs[0]:
        st.subheader(customer["full_name"])
        st.caption(f"{customer['city']} · {customer['segment']} · {len(customers)} customers in cloud portfolio")
        columns = st.columns(4)
        for column, label, value in zip(columns, ["Outstanding", "Days past due", "Payment ratio", "Churn review score"],
                                        [f"Rs {metrics['total_outstanding']:,.0f}", metrics["dpd"], f"{metrics['on_time_ratio']:.0%}", metrics["churn_risk"]]):
            column.metric(label, value)
        st.caption("Churn score is an illustrative priority score, rather than a validated probability.")
        st.subheader("Next best action")
        st.write(decision.get("title", decision["action_code"]))
        st.write(decision["rationale"])
        if decision["offer"]:
            st.json(decision["offer"])
        if st.button("Request demo review", disabled=decision["action_code"] == "NO_ACTION"):
            request = repository.request_review(customer_id)
            st.success(f"Review request saved in Snowflake: {request}")
        st.subheader("Loan history")
        st.dataframe(view["loans"], use_container_width=True, hide_index=True)
        st.subheader("Interaction timeline")
        for interaction in view["interactions"]:
            with st.expander(f"{interaction['channel']} · {interaction['interaction_id']} · {interaction['ts']}"):
                st.write(interaction["evidence_text"])
                st.caption(f"Deterministic intent: {interaction['intent']} · sentiment: {interaction['sentiment']}")
        with st.expander("Cloud AI enrichment for human review"):
            signals = repository.cortex_signals(customer_id)
            if signals:
                for signal in signals:
                    st.json(signal, expanded=False)
            else:
                st.caption("No Cortex enrichment has been run for this profile. It can be enabled after the account capability check.")
    with tabs[1]:
        st.subheader("Ask about this customer")
        with st.form("ask"):
            question = st.text_input("Question", value="Why is this next action recommended?", max_chars=1000)
            cortex = st.checkbox("Use Cortex AI for this answer (consumes Snowflake credits)", value=False)
            submitted = st.form_submit_button("Ask")
        if submitted:
            result = repository.answer(customer_id, question, cortex=cortex)
            st.session_state["answer"] = {"customer_id": customer_id, **result}
        result = st.session_state.get("answer", {})
        if result.get("customer_id") == customer_id:
            st.caption(result["provider"])
            # Model text must not embed remote images, clickable instructions
            # or HTML through Markdown rendering.
            st.text(result["answer"])
            if result.get("model_output_requires_review"):
                st.caption("Generated answer: verify its claims against the source excerpts below.")
            for evidence in result["evidence"]:
                with st.expander(f"Source {evidence['id']} · {evidence['channel']}"):
                    st.write(evidence["text"])
    with tabs[2]:
        st.subheader("Your cloud review queue")
        st.caption("This single-operator demo records review decisions. Production requires independent approvers and a transactional execution service.")
        reviews = repository.reviews()
        for review in reviews:
            with st.expander(f"{review['CUSTOMER_ID']} · {review['DECISION']['action_code']} · {review['STATUS']}"):
                st.write(review["DECISION"]["rationale"])
                st.json(review["DECISION"]["offer"], expanded=False)
                if review["STATUS"] == "PENDING_REVIEW":
                    with st.form("review_" + review["REQUEST_ID"]):
                        outcome = st.selectbox("Review decision", ["APPROVED_FOR_DEMO", "REJECTED"])
                        note = st.text_input("Review note", max_chars=500)
                        reviewed = st.form_submit_button("Save demo decision")
                    if reviewed:
                        repository.review(review["REQUEST_ID"], outcome, note)
                        st.rerun()
                else:
                    st.caption(f"Reviewed by {review['REVIEWED_BY']}: {review['REVIEW_NOTE']}")
        if not reviews:
            st.caption("Request a recommendation review from Customer 360.")
    with tabs[3]:
        st.subheader("Conversation handoff")
        st.write(decision.get("script") or "No contact script is permitted for this customer under the current rules.")
        st.write({"call_consent": bool(customer["consent_calls"]), "marketing_consent": bool(customer["consent_marketing"]), "do_not_disturb": bool(customer["dnd"])})
        st.caption("Call transcripts are stored in Snowflake and inform Customer 360. Live audio and automated telephone conversations remain in the separate Windows voice lab until a licensed media worker and carrier are deployed.")
except DemoError as error:
    st.error(str(error))
except Exception as error:
    logging.getLogger("samvaad.cloud").error("Cloud operation failure: %s", type(error).__name__)
    st.error("This operation could not complete. Check the app role, warehouse and Cortex availability. Provider details were kept out of the UI.")

