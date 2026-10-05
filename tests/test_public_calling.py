"""The public conversation changes visit state, never loans or contacts."""
import copy
import json

import pytest

from cloud.config import WORKSPACE
from public_app.calling import CallSandbox, MAX_REPLIES, MAX_SESSIONS
from public_app.repository import DemoError, ReviewSandbox, SnapshotReader
from public_app.ui.call_audio import voice_document


@pytest.fixture
def reader():
    return SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")


def approved(reader, customer_id="C0003", state=None):
    reviews = []
    review = ReviewSandbox(reviews, reader)
    review_id = review.request(customer_id)
    review.review(review_id, "APPROVED_IN_SIMULATION", "Fictional call studio review")
    calls = CallSandbox(state if state is not None else {}, reader, reviews)
    return calls, calls.start(customer_id), reviews


def activate(calls, session):
    sid = session["session_id"]
    permission = calls.reply(sid, "Yes, you may continue")
    assert permission["state"] == "AWAIT_IDENTITY"
    return calls.reply(sid, "Yes, I am the account holder")


def test_no_unapproved_dnd_or_cross_visit_call(reader):
    calls = CallSandbox({}, reader)
    with pytest.raises(DemoError, match="Approve"):
        calls.start("C0003")
    with pytest.raises(DemoError, match="suppressed"):
        calls.start("C0004")
    calls, session, _ = approved(reader)
    other = CallSandbox({}, reader)
    with pytest.raises(DemoError, match="current visit"):
        other.reply(session["session_id"], "Yes")
    assert calls.sessions() and other.sessions() == []


def test_terms_require_permission_identity_and_reviewed_proposal(reader):
    before = copy.deepcopy(reader.customer360("C0003"))
    calls, session, reviews = approved(reader)
    amount = session["decision"]["offer"]["amount"]
    assert f"{amount:,.0f} rupees" not in str(session["turns"])
    sid = session["session_id"]
    permission = calls.reply(sid, "Yes, you may continue")
    assert permission["permission_granted"] and not permission["identity_confirmed"]
    assert f"{amount:,.0f} rupees" not in str(permission["turns"])
    active = calls.reply(sid, "Yes, I am the account holder")
    assert active["identity_confirmed"] and f"{amount:,.0f} rupees" in active["turns"][-1]["text"]
    result = calls.reply(sid, "I am interested")
    assert result["outcome"] == "INTEREST_RECORDED_SIMULATION"
    assert result["simulated_invitation"]["offer"] == reviews[0]["decision"]["offer"]
    assert result["simulated_invitation"]["delivery_sent"] is False
    assert result["real_call_placed"] is False and result["financial_execution"] is False
    assert reader.customer360("C0003") == before
    assert {turn["role"] for turn in result["turns"]} == {"lender", "borrower"}


@pytest.mark.parametrize("stage,text", [
    ("permission", "Yes, but I do not consent"),
    ("identity", "Yes, but I am not the account holder"),
    ("identity", "This is the wrong number"),
])
def test_negative_gate_never_discloses_account_terms(reader, stage, text):
    calls, session, _ = approved(reader, "C0002")
    sid = session["session_id"]
    if stage == "identity":
        calls.reply(sid, "Yes")
    result = calls.reply(sid, text)
    assert result["state"] == "ENDED"
    assert "100 basis points" not in str(result["turns"])
    assert not result["simulated_invitation"]


@pytest.mark.parametrize("text", ["Yes, if this is free", "What happens if I say yes?", "Yesterday was fine"])
def test_conditional_or_question_is_not_gate_permission(reader, text):
    calls, session, _ = approved(reader)
    result = calls.reply(session["session_id"], text)
    assert result["state"] == "AWAIT_PERMISSION" and not result["permission_granted"]
    assert not any(t["role"] == "borrower" for t in result["turns"])


@pytest.mark.parametrize("text", ["I do not accept", "I am not interested", "I cannot accept", "No, thanks"])
def test_negative_interest_never_becomes_acceptance(reader, text):
    calls, session, _ = approved(reader, "C0002")
    activate(calls, session)
    result = calls.reply(session["session_id"], text)
    assert result["outcome"] == "DECLINED_SIMULATION" and not result["simulated_invitation"]


@pytest.mark.parametrize("text", [
    "Yes, if you reduce it by 500 basis points", "I accept only with a larger amount", "I accept but change the rate",
    "I accept a rate of 0%", "I accept whatever you decide",
])
def test_negotiation_stays_open_and_cannot_modify_offer(reader, text):
    calls, session, _ = approved(reader, "C0002")
    original = copy.deepcopy(session["decision"]["offer"])
    activate(calls, session)
    result = calls.reply(session["session_id"], text)
    assert result["state"] == "ACTIVE" and result["decision"]["offer"] == original
    assert not result["simulated_invitation"] and "TERMS_CHANGE_BLOCKED" in result["events"]


@pytest.mark.parametrize("stage", ["permission", "identity", "active"])
def test_hardship_overrides_topup_at_every_gate(reader, stage):
    calls, session, _ = approved(reader)
    sid = session["session_id"]
    if stage in {"identity", "active"}:
        calls.reply(sid, "Yes")
    if stage == "active":
        calls.reply(sid, "Yes, I am the account holder")
    result = calls.reply(sid, "I lost my job, but I am interested")
    assert result["outcome"] == "HUMAN_HANDOFF" and "HARDSHIP_OVERRIDE" in result["events"]
    assert result["simulated_invitation"] is None
    with pytest.raises(DemoError, match="hardship evidence"):
        calls.start("C0003")
    if stage == "permission":
        assert not any(t["role"] == "borrower" for t in result["turns"])


def test_actual_hardship_turn_becomes_cited_evidence_and_changes_decision(reader):
    calls, session, _ = approved(reader)
    activate(calls, session)
    utterance = "I lost my job yesterday and cannot afford another loan. Please help."
    result = calls.reply(session["session_id"], utterance)
    assert result["decision_before"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    assert result["decision_after"]["action_code"] == "NO_ACTION"
    assert result["new_evidence"]["evidence_text"] == "Customer: " + utterance
    assert result["new_evidence"]["interaction_id"] == "SIM-C0003-JOB_LOSS"
    assert result["new_evidence"]["intent"] == "financial hardship"
    assert result["policy_change"]["metrics"]["hardship_flag"]
    assert result["policy_change"]["simulation_only"] and not result["policy_change"]["database_write"]
    assert calls.state["hardship_holds"] == ["C0003"]
    assert reader.customer360("C0003")["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"


def test_actual_optout_recomputes_contact_suppression_and_retains_consented_evidence(reader):
    calls, session, _ = approved(reader)
    activate(calls, session)
    result = calls.reply(session["session_id"], "Please stop calling me about this loan")
    assert result["decision_after"]["action_code"] == "NO_ACTION"
    assert "suppressed" in result["decision_after"]["rationale"]
    assert result["new_evidence"]["evidence_text"] == "Customer: Please stop calling me about this loan"


def test_unconsented_speech_is_not_retained_as_evidence(reader):
    calls, session, _ = approved(reader)
    utterance = "Do not call me, I have personal private reasons"
    result = calls.reply(session["session_id"], utterance)
    assert utterance not in calls.export()
    assert result["decision_after"]["action_code"] == "NO_ACTION"
    calls, session, _ = approved(reader)
    utterance = "I lost my job and my landlord is threatening me"
    result = calls.reply(session["session_id"], utterance)
    assert utterance not in calls.export()
    assert result["decision_after"]["action_code"] == "NO_ACTION"


def test_negated_hardship_does_not_override_explicit_interest(reader):
    calls, session, _ = approved(reader)
    activate(calls, session)
    # No implicit acceptance from mentioning a topic. Explicit interest follows.
    result = calls.reply(session["session_id"], "I did not lose my job")
    assert "HARDSHIP_OVERRIDE" not in result["events"]
    assert result["state"] == "ACTIVE" and result["simulated_invitation"] is None
    assert calls.reply(session["session_id"], "I am interested")["outcome"] == "INTEREST_RECORDED_SIMULATION"


@pytest.mark.parametrize("text", ["Yes, please explain", "Yes, what is the rate", "I don't understand"])
def test_asking_for_details_is_not_acceptance_or_decline(reader, text):
    calls, session, _ = approved(reader)
    activate(calls, session)
    result = calls.reply(session["session_id"], text)
    assert result["state"] == "ACTIVE" and result["simulated_invitation"] is None


@pytest.mark.parametrize("stage", ["permission", "active"])
def test_optout_blocks_later_contact_only_inside_this_visit(reader, stage):
    calls, session, reviews = approved(reader)
    if stage == "active":
        activate(calls, session)
    result = calls.reply(session["session_id"], "Stop calling me")
    assert result["outcome"] == "OPT_OUT_FOR_VISIT"
    with pytest.raises(DemoError, match="opt-out"):
        calls.start("C0003")
    separate_visit = CallSandbox({}, reader, copy.deepcopy(reviews))
    assert separate_visit.start("C0003")["state"] == "AWAIT_PERMISSION"
    assert reader.customer360("C0003")["customer"]["consent_calls"]


def test_human_and_hardship_callback_never_make_financial_invitation(reader):
    calls, session, _ = approved(reader)
    activate(calls, session)
    result = calls.reply(session["session_id"], "Please connect an officer")
    assert result["outcome"] == "HUMAN_HANDOFF" and not result["simulated_invitation"]
    calls, session, _ = approved(reader, "C0001")
    activate(calls, session)
    result = calls.reply(session["session_id"], "Yes")
    assert result["outcome"] == "HUMAN_HANDOFF" and not result["simulated_invitation"]


@pytest.mark.parametrize("stage", ["permission", "identity"])
def test_human_request_at_early_gate_stops_without_account_disclosure(reader, stage):
    calls, session, _ = approved(reader, "C0002")
    if stage == "identity":
        calls.reply(session["session_id"], "Yes")
    result = calls.reply(session["session_id"], "Please connect me to a human")
    assert result["outcome"] == "HUMAN_HANDOFF"
    assert "100 basis points" not in str(result["turns"])
    assert not result["simulated_invitation"]
    if stage == "permission":
        assert not any(turn["role"] == "borrower" for turn in result["turns"])


def test_repeated_start_no_extra_attempt_and_results_are_copies(reader):
    calls, session, _ = approved(reader)
    assert calls.start("C0003")["session_id"] == session["session_id"]
    session["decision"]["offer"]["amount"] = 1
    assert calls.get(session["session_id"])["decision"]["offer"]["amount"] != 1
    assert calls.state["attempts"]["C0003"] == 1


def test_stale_review_or_recommendation_cannot_begin_or_continue(reader, monkeypatch):
    calls, session, _ = approved(reader)
    original = reader.customer360
    def changed(customer_id):
        view = original(customer_id)
        view["decision"]["offer"]["amount"] += 10000
        return view
    monkeypatch.setattr(reader, "customer360", changed)
    with pytest.raises(DemoError, match="Approve"):
        calls.start("C0003")
    result = calls.reply(session["session_id"], "Yes")
    assert result["outcome"] == "HUMAN_HANDOFF" and not result["permission_granted"]


def test_consent_revocation_stops_active_conversation_without_terms(reader, monkeypatch):
    calls, session, _ = approved(reader)
    original = reader.customer360
    def revoked(customer_id):
        view = original(customer_id)
        view["customer"]["consent_calls"] = False
        return view
    monkeypatch.setattr(reader, "customer360", revoked)
    result = calls.reply(session["session_id"], "Yes")
    assert result["outcome"] == "CONTACT_SUPPRESSED" and not result["simulated_invitation"]


def test_attempt_turn_and_session_caps_are_enforced(reader):
    calls, session, _ = approved(reader)
    sid = session["session_id"]
    for _ in range(MAX_REPLIES):
        result = calls.reply(sid, "Please explain")
    assert result["state"] == "ENDED" and result["outcome"] == "HUMAN_HANDOFF"
    for _ in range(2):
        calls.end(calls.start("C0003")["session_id"])
    with pytest.raises(DemoError, match="three-attempt"):
        calls.start("C0003")
    full = CallSandbox({"sessions": [dict(result, session_id=str(i), customer_id="C0002")
                                     for i in range(MAX_SESSIONS)]}, reader, calls.reviews)
    with pytest.raises(DemoError, match="conversation limit"):
        full.start("C0003")


def test_export_and_invalid_replies_are_bounded_and_truthful(reader):
    calls, session, _ = approved(reader)
    for value in ["", " " * 3, "a" * 1001, None]:
        with pytest.raises(DemoError):
            calls.reply(session["session_id"], value)
    assert calls.get(session["session_id"])["reply_count"] == 0
    document = json.loads(calls.export(session["session_id"]))
    assert not document["real_call_placed"] and not document["financial_execution"]
    assert document["sessions"][0]["simulation_only"]


def test_browser_voice_escapes_script_payload_and_uses_click_without_capture():
    html = voice_document('</script><script>fetch("private")</script>')
    assert html.count("</script>") == 1
    assert "\\u003c/script\\u003e" in html
    assert "play.addEventListener('click'" in html
    assert "SpeechSynthesisUtterance(message)" in html and "role=\"status\"" in html
    assert not any(value in html for value in ["getUserMedia", "SpeechRecognition", "src=", "eval("])
    with pytest.raises(ValueError):
        voice_document("a" * 4001)
