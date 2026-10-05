"""Local borrower/lender voice lab, separated from the Customer 360 screens."""
from __future__ import annotations

from hashlib import sha256
import logging
from uuid import uuid4

import streamlit as st

from samvaad.models import ActionError, Actor


RUNNER = Actor("local-runner", "AUTOMATION")
logger = logging.getLogger("samvaad.voice_ui")
ACTION_TITLES = {
    "RETENTION_RATE_MATCH_CALL": "Capped retention rate review",
    "TOPUP_PREAPPROVAL_CALL": "Conditional top-up invitation",
    "HARDSHIP_RESTRUCTURE_CALL": "Supportive hardship callback",
    "GENTLE_REMINDER_CALL": "Gentle payment reminder",
}


@st.cache_data(show_spinner=False, max_entries=32)
def lender_audio(text: str, voice_name: str | None = None) -> dict:
    """Cache only generated synthetic lender speech, keyed by its exact text."""
    from samvaad.voice_audio import synthesize

    return synthesize(text, voice_name=voice_name)


def _error(error: Exception) -> None:
    if isinstance(error, ActionError):
        st.error(f"{error.message} ({error.code})")
    else:
        logger.error("Unexpected voice UI error: %s", type(error).__name__)
        st.error("Local voice request failed. Please check the application logs.")


def _refresh(session: dict, message: str) -> None:
    lender_turns = [t for t in session.get("turns", []) if t.get("role") == "lender"]
    if lender_turns:
        st.session_state[f"voice_autoplay_{session['session_id']}"] = lender_turns[-1].get("seq")
    st.session_state["flash"] = message
    st.rerun()


def _send(voice, session: dict, text: str) -> None:
    try:
        updated = voice.turn(session["session_id"], text, event_id=str(uuid4()), actor=RUNNER)
        _refresh(updated, "Borrower response recorded. The local lender assistant has replied.")
    except Exception as error:
        _error(error)


def _text_entry(voice, session: dict) -> None:
    sid = session["session_id"]
    state = session.get("state")
    examples = {
        "AWAIT_PERMISSION": "Yes, you may continue.",
        "AWAIT_IDENTITY": "Yes, I am the account holder.",
        "ACTIVE": "What are the approved terms? / Please arrange a callback. / Do not contact me again.",
    }
    with st.form(f"voice_text_form_{sid}", clear_on_submit=True):
        text = st.text_area("Synthetic borrower response", placeholder=examples.get(state, "Your response"), max_chars=4000, key=f"voice_text_{sid}")
        submitted = st.form_submit_button("Send borrower response", type="primary")
    if submitted:
        _send(voice, session, text)


def _audio_entry(voice, session: dict, audio_status: dict) -> None:
    from samvaad import voice_audio

    sid = session["session_id"]
    st.caption("Record fictional borrower speech or upload a PCM WAV (up to 60 seconds / 10 MB). Review the locally recognized text before sending it into the conversation.")
    recorded = st.audio_input("Record synthetic borrower speech", sample_rate=16000, key=f"voice_mic_{sid}")
    uploaded = st.file_uploader("Or upload a borrower WAV", type=["wav"], key=f"voice_upload_{sid}")
    if not audio_status.get("asr_ready"):
        st.info("Local speech recognition is not configured. You can record/preview audio, or continue using text. Install the optional local recognizer to enable transcription.")
    media = recorded or uploaded
    if media is None:
        return
    data = media.getvalue()
    if len(data) > 10_000_000:
        st.error("Use a WAV recording smaller than 10 MB for this local lab.")
        return
    st.audio(data, format="audio/wav")
    audio_hash = sha256(data).hexdigest()
    recognized_key = f"voice_recognized_{sid}"
    if st.button("Transcribe locally", disabled=not audio_status.get("asr_ready"), key=f"voice_transcribe_{sid}"):
        try:
            with st.spinner("Transcribing on this machine…"):
                result = voice_audio.transcribe(data)
            st.session_state[recognized_key] = {**result, "audio_hash": audio_hash}
            st.session_state[f"voice_review_{sid}"] = result.get("text", "")
        except Exception as error:
            _error(error)
    recognized = st.session_state.get(recognized_key)
    if recognized and recognized.get("audio_hash") == audio_hash:
        st.caption(f"Speech recognizer: {recognized.get('provider', 'Local')} · Language: {recognized.get('language', '—')}")
        reviewed = st.text_area("Review recognized borrower text", key=f"voice_review_{sid}", max_chars=4000)
        if st.button("Send reviewed transcript", type="primary", disabled=not reviewed.strip(), key=f"voice_send_audio_{sid}"):
            _send(voice, session, reviewed)


def _transcript(session: dict) -> None:
    turns = session.get("turns") or []
    st.markdown("**Conversation transcript**")
    for turn in turns:
        is_lender = turn.get("role") == "lender"
        with st.chat_message("assistant" if is_lender else "user", avatar="🏦" if is_lender else "👤"):
            st.caption(f"{'Lender assistant' if is_lender else 'Synthetic borrower'} · Turn {turn.get('seq', '—')}")
            st.write(turn.get("text", ""))
    export = [f"Samvaad 360 local voice lab · {session['session_id']}", f"State: {session.get('state')} · Outcome: {session.get('outcome') or 'Pending'}", ""]
    export.extend(f"{turn.get('role', 'unknown').upper()}: {turn.get('text', '')}" for turn in turns)
    st.download_button("Download voice transcript", "\n".join(export), file_name=f"samvaad-voice-{session['session_id']}.txt", mime="text/plain", key=f"voice_transcript_{session['session_id']}")


def _lender_playback(session: dict, audio_status: dict) -> None:
    st.markdown("**Latest lender response**")
    lender_turns = [t for t in session.get("turns", []) if t.get("role") == "lender"]
    if not lender_turns:
        st.caption("Lender speech appears when the conversation starts.")
        return
    latest = lender_turns[-1]
    st.write(latest.get("text", ""))
    if not audio_status.get("tts_ready"):
        st.warning("Local speech synthesis is unavailable. The conversation remains usable through its transcript.")
        return
    try:
        with st.spinner("Preparing local lender speech…"):
            result = lender_audio(latest["text"])
        pending_key = f"voice_autoplay_{session['session_id']}"
        autoplay = st.session_state.get(pending_key) == latest.get("seq")
        st.audio(result["audio"], format=result.get("mime_type", "audio/wav"), autoplay=autoplay)
        st.session_state.pop(pending_key, None)
        st.caption(f"Speech: {result.get('provider', audio_status.get('tts_provider', 'Local'))} · Voice: {result.get('voice', 'OS default')}")
        st.download_button("Download lender WAV", result["audio"], file_name=f"samvaad-lender-{session['session_id']}-{latest.get('seq', 0)}.wav", mime="audio/wav", key=f"voice_audio_{session['session_id']}_{latest.get('seq', 0)}")
    except Exception as error:
        _error(error)


def render_voice_lab(service, selected_id: str, actor: Actor, is_demo: bool) -> None:
    """Render a persisted voice session; the backend enforces every transition."""
    st.subheader("Local voice lab")
    st.caption("An automated lender assistant and a synthetic borrower conversation on this machine. No phone call is placed and no real loan is offered.")
    if not is_demo:
        st.info("The local voice lab is available only in demo mode. A production voice channel requires its own deployment and authorization checks.")
        return
    try:
        from samvaad.voice import VoiceService
        from samvaad import voice_audio

        voice = VoiceService(service)
        audio_status = voice_audio.status()
        available = voice.available_actions(selected_id)
        sessions = voice.sessions(customer_id=selected_id)
    except Exception as error:
        _error(error)
        return
    st.caption(f"Operator: {actor.user_id} · Conversation runner: local-runner / Automation · Mode: LOCAL_VOICE_LAB")
    st.caption("Installed OS voice for this local lab. A production stock voice model is selected separately after license review and a latency benchmark; no personal recordings are required.")
    with st.expander("Start from an approved action", expanded=not sessions):
        st.caption("Only approved actions that still pass policy, consent, and eligibility checks can start. The voice assistant uses the stored approved terms.")
        if available:
            indexed = {action["action_id"]: action for action in available}
            action_id = st.selectbox("Approved action for voice lab", list(indexed), format_func=lambda aid: f"{indexed[aid].get('customer_name', selected_id)} · {indexed[aid].get('title') or ACTION_TITLES.get(indexed[aid].get('action_code'), 'Approved service action')}", key=f"voice_start_action_{selected_id}")
            if st.button("Start local voice session", type="primary", key=f"voice_start_{selected_id}"):
                try:
                    session = voice.start(action_id, RUNNER)
                    st.session_state[f"voice_session_pick_{selected_id}"] = session["session_id"]
                    _refresh(session, "Local voice session started. Permission and account-holder confirmation are required before discussing approved terms.")
                except Exception as error:
                    _error(error)
        else:
            st.info("No approved action is available for this customer. Generate a next best action and obtain the designated approval first.")
    if not sessions:
        st.info("Start a local session to see lender audio, borrower input, and the speaker-labeled transcript.")
        return
    by_id = {session["session_id"]: session for session in sessions}
    picker_key = f"voice_session_pick_{selected_id}"
    if st.session_state.get(picker_key) not in by_id:
        st.session_state.pop(picker_key, None)
    session_id = st.selectbox("Voice session", list(by_id), format_func=lambda sid: f"{by_id[sid].get('state', '').replace('_', ' ').title()} · {sid[:8]}", key=picker_key)
    try:
        session = voice.get(session_id)
    except Exception as error:
        _error(error)
        return
    state = session.get("state", "UNKNOWN")
    c1, c2, c3 = st.columns(3)
    c1.metric("Conversation state", state.replace("_", " ").title())
    c2.metric("Permission to continue", "Granted" if session.get("permission_granted") else "Pending")
    c3.metric("Account-holder confirmation", "Confirmed" if session.get("identity_confirmed") else "Pending")
    if state == "AWAIT_PERMISSION":
        st.info("Permission gate: the borrower must agree to continue. The lender does not disclose loan terms before both conversation gates pass.")
    elif state == "AWAIT_IDENTITY":
        st.info("Identity gate: use an explicit account-holder confirmation for this local verbal simulation. This is not real identity verification or KYC.")
    elif state == "ACTIVE":
        st.success("Both local conversation gates passed. The assistant can explain the approved offer, arrange a callback, or record an opt-out.")
    elif state == "ENDED":
        st.success(f"Conversation ended · Outcome: {str(session.get('outcome') or 'Recorded').replace('_', ' ').title()}")
    left, right = st.columns([1.35, 1], gap="large")
    with right:
        _lender_playback(session, audio_status)
        if state != "ENDED":
            st.divider()
            if st.button("End voice session", key=f"voice_end_{session_id}", use_container_width=True):
                try:
                    ended = voice.end(session_id, RUNNER, outcome="CALLBACK")
                    _refresh(ended, "Local conversation stopped. A callback outcome was recorded.")
                except Exception as error:
                    _error(error)
        st.caption("This is a local demonstration. Browser microphone permissions and playback settings apply. Production telephony and the selected stock neural voice require separate integration.")
    with left:
        if state != "ENDED":
            entry = st.radio("Borrower input", ["Text", "Microphone / WAV"], horizontal=True, key=f"voice_input_mode_{session_id}")
            if entry == "Text":
                _text_entry(voice, session)
            else:
                _audio_entry(voice, session, audio_status)
            st.divider()
        _transcript(session)
