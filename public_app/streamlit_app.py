"""Anonymous public website backed by restricted reads from Snowflake."""
import logging
import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from public_app.repository import DemoError, ReviewSandbox, SnapshotReader, connect_reader

st.set_page_config(page_title="Samvaad 360", page_icon="💬", layout="wide")
st.markdown("""<style>
.stApp {background:#f5f7fc;color:#18223a}
[data-testid="stMetric"] {background:white;border:1px solid #dfe5f2;border-radius:12px;padding:14px}
h1,h2,h3 {color:#263d81} .block-container {padding-top:2rem;max-width:1250px}
</style>""", unsafe_allow_html=True)
st.title("Samvaad 360")
st.caption("Customer 360 and Next Best Action Engine · Lending demonstration")


@st.cache_resource(ttl=300, show_spinner=False)
def reader():
    connected = None
    try:
        local_secrets = os.getenv("SAMVAAD_PUBLIC_SECRETS_FILE")
        settings = (tomllib.loads(Path(local_secrets).read_text(encoding="utf-8"))["snowflake"]
                    if local_secrets else dict(st.secrets["snowflake"]))
        connected = connect_reader(settings)
        connected.customers()  # Verify readable fictional data before claiming a live backend.
        return connected
    except Exception as error:
        if connected is not None:
            connected.session.connection.close()
        logging.getLogger("samvaad.public").warning("Public fallback activated: %s", type(error).__name__)
        return SnapshotReader(Path(__file__).with_name("synthetic_snapshot.json"))


@st.cache_data(ttl=300, max_entries=1, show_spinner=False)
def customers(source):
    return reader().customers()


@st.cache_data(ttl=300, max_entries=100, show_spinner=False)
def profile(customer_id, source):
    return reader().customer360(customer_id)


try:
    repository = reader()
    source = "snowflake" if repository.is_live else "snapshot"
    portfolio = customers(source)
except Exception as error:
    logging.getLogger("samvaad.public").error("Public connection failure: %s", type(error).__name__)
    st.error("The Snowflake backend is temporarily unavailable or its hosting connection is not configured.")
    st.caption("This website needs its dedicated server connection. Visitors do not need a Snowflake account.")
    st.stop()

st.sidebar.markdown("### Explore the portfolio")
customer_id = st.sidebar.selectbox("Customer", [c["customer_id"] for c in portfolio],
    format_func=lambda cid: next(f"{c['full_name']} · {cid}" for c in portfolio if c["customer_id"] == cid))
if repository.is_live:
    st.sidebar.success("Data source: Snowflake")
else:
    st.sidebar.warning("Data source: offline synthetic snapshot")
    st.warning("The live Snowflake connection is unavailable. You are exploring a bundled fictional snapshot. "
               "No live Snowflake or Cortex request is being represented by this backup mode.")
    st.sidebar.caption("Snapshot reference: " + repository.reference)
st.sidebar.caption(f"{len(portfolio)} fictional customers · cached reads up to 5 minutes")
st.sidebar.caption("Try Ravi for hardship, Ananya for retention, Imran for top-up, and Neha for consent restrictions.")
st.info("Explore fictional lending journeys. Review decisions are isolated to this visit and simulate a workflow. "
        "They do not change loan terms, send invitations or place telephone calls.")

if "public_reviews" not in st.session_state:
    st.session_state["public_reviews"] = []
sandbox = ReviewSandbox(st.session_state["public_reviews"], repository)

try:
    view = profile(customer_id, source)
    customer, metrics, decision = view["customer"], view["metrics"], view["decision"]
    tabs = st.tabs(["Customer 360", "Ask with evidence", "Review simulation", "Conversation handoff"])
    with tabs[0]:
        st.subheader(customer["full_name"])
        st.caption(f"{customer['city']} · {customer['segment']}")
        columns = st.columns(4)
        values = [f"Rs {metrics['total_outstanding']:,.0f}", metrics["dpd"],
                  f"{metrics['on_time_ratio']:.0%}", metrics["churn_risk"]]
        for column, label, value in zip(columns, ["Outstanding", "Days past due", "Payment ratio", "Churn review score"], values):
            column.metric(label, value)
        st.caption("The churn score is an illustrative priority score, not a validated probability.")
        st.subheader("Next best action")
        st.write(decision.get("title", decision["action_code"]))
        st.text(decision["rationale"])
        if decision["offer"]:
            st.json(decision["offer"])
        if st.button("Try review workflow", disabled=decision["action_code"] == "NO_ACTION"):
            sandbox.request(customer_id)
            st.success("Recommendation added to your simulation. Open Review simulation to review it.")
        st.subheader("Loan history")
        st.dataframe(view["loans"], hide_index=True, width="stretch")
        st.subheader("Interaction timeline")
        for interaction in view["interactions"]:
            with st.expander(f"{interaction['channel']} · {interaction['interaction_id']} · {interaction['ts']}"):
                st.text(interaction["evidence_text"])
                st.caption(f"Intent: {interaction['intent']} · sentiment: {interaction['sentiment']}")
    with tabs[1]:
        st.subheader("Ask about this customer")
        with st.form("public_question"):
            question = st.text_input("Question", value="Why is this next action recommended?", max_chars=1000)
            submitted = st.form_submit_button("Ask")
        if submitted:
            result = repository.answer(customer_id, question)
            st.session_state["public_answer"] = {"customer_id": customer_id, **result}
        result = st.session_state.get("public_answer", {})
        if result.get("customer_id") == customer_id:
            st.caption(result["provider"])
            st.text(result["answer"])
            for evidence in result["evidence"]:
                with st.expander(f"Source {evidence['id']} · {evidence['channel']}"):
                    st.text(evidence["text"])
        st.caption("This public answer uses Snowflake records and evidence rules. Live Cortex requests remain "
                   "in the private operator app so anonymous traffic cannot trigger AI charges.")
    with tabs[2]:
        st.subheader("Your review simulation")
        st.caption("Records are stored only in this browser session. This is not a staff approval or a database write. "
                   "A new or expired session starts a fresh simulation.")
        for record in st.session_state["public_reviews"]:
            with st.expander(f"{record['customer_id']} · {record['decision']['action_code']} · {record['status']}"):
                st.text(record["decision"]["rationale"])
                if record["decision"]["offer"]:
                    st.json(record["decision"]["offer"])
                if record["status"] == "PENDING_SIMULATION":
                    with st.form("public_review_" + record["id"]):
                        outcome = st.selectbox("Simulation decision", ["APPROVED_IN_SIMULATION", "REJECTED_IN_SIMULATION"])
                        note = st.text_input("Fictional review note", max_chars=500)
                        save = st.form_submit_button("Save simulation decision")
                    if save:
                        sandbox.review(record["id"], outcome, note)
                        st.rerun()
                else:
                    st.text("Simulation note: " + record["note"])
        if not st.session_state["public_reviews"]:
            st.caption("Choose a customer and click Try review workflow in Customer 360.")
        else:
            st.download_button("Download this simulation", sandbox.export(), "samvaad360-simulation.json", "application/json")
    with tabs[3]:
        st.subheader("Conversation handoff")
        st.text(decision.get("script") or "Consent or policy prevents contact with this customer.")
        st.json({"call_consent": bool(customer["consent_calls"]),
                 "marketing_consent": bool(customer["consent_marketing"]), "do_not_disturb": bool(customer["dnd"])})
        st.caption("The recommendation uses interaction transcripts stored in Snowflake. The separate local "
                   "voice lab supports speech experiments; live carrier calls are not part of this public demo.")
except DemoError as error:
    st.error(str(error))
except Exception as error:
    logging.getLogger("samvaad.public").error("Public workflow failure: %s", type(error).__name__)
    st.error("This operation could not complete. Try again later; connection details are kept private.")

st.caption("Synthetic hackathon prototype · Insurance & Lending track · Implements the lender journey")
