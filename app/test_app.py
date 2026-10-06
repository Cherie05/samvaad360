"""Real UI-to-service acceptance checks on an isolated SQLite database."""
from pathlib import Path
import io
import wave

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


APP_FILE = Path(__file__).with_name("streamlit_app.py")


@pytest.fixture
def portal(tmp_path, monkeypatch):
    from samvaad import voice_audio

    # UI checks exercise real voice state/DB writes while mocking the platform
    # audio transport. The voice adapter has separate real-audio verification.
    sample = io.BytesIO()
    with wave.open(sample, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 1600)
    audio = sample.getvalue()
    monkeypatch.setattr(voice_audio, "status", lambda: {
        "tts_ready": True, "tts_provider": "AppTest PCM transport", "asr_ready": True,
        "asr_provider": "AppTest recognizer", "production_ready": False,
    })
    monkeypatch.setattr(voice_audio, "synthesize", lambda text, voice_name=None: {
        "audio": audio, "mime_type": "audio/wav", "provider": "AppTest PCM transport", "voice": "Test voice",
    })
    monkeypatch.setattr(voice_audio, "transcribe", lambda data: {
        "text": "Yes, I am the account holder.", "provider": "AppTest recognizer", "language": "en",
    })
    st.cache_data.clear()
    db_path = tmp_path / "portal.sqlite3"
    monkeypatch.setenv("SAMVAAD_BACKEND", "local")
    monkeypatch.setenv("SAMVAAD_DB_PATH", str(db_path))
    portal = AppTest.from_file(str(APP_FILE), default_timeout=30).run()
    assert not portal.exception
    return portal, db_path


def button(portal, label):
    return next(item for item in portal.button if item.label == label)


def test_local_portal_shows_accurate_provider_and_customer_scope(portal):
    page, _ = portal
    assert page.selectbox(key="demo_operator").value == "Meera · Analyst"
    assert page.selectbox(key="customer_picker").value == "C0002"
    rendered = "\n".join(item.value for item in page.markdown)
    assert "Local working demo" in rendered
    assert "Deterministic offline analysis" in rendered
    assert "Ananya" in rendered
    assert [tab.label for tab in page.tabs] == [
        "Customer 360", "Approvals & execution", "Ask Samvaad", "Action history", "Voice lab", "Relationship hub"
    ]


def test_manager_approval_and_simulated_execution_update_database(portal):
    from samvaad.service import LocalService

    page, db_path = portal
    button(page, "Generate next best action").click().run()
    assert not page.exception and not page.error
    service = LocalService(db_path=db_path)
    action = next(item for item in service.actions() if item["customer_id"] == "C0002")
    page.selectbox(key="action_review").set_value(action["action_id"]).run()
    assert button(page, "Approve action").disabled
    page.selectbox(key="demo_operator").set_value("Arjun · Retention manager").run()
    assert not button(page, "Approve action").disabled
    button(page, "Approve action").click().run()
    assert not page.exception and not page.error
    assert next(item for item in service.actions() if item["action_id"] == action["action_id"])["approved_by"] == "arjun"
    button(page, "Run simulated action").click().run()
    assert not page.exception and not page.error
    completed = next(item for item in service.actions() if item["action_id"] == action["action_id"])
    assert completed["status"] == "COMPLETED"
    assert completed["execution_mode"] == "simulate"
    assert completed["outcome"] == "ACCEPT"
    assert any("simulat" in str(event).lower() for event in service.audit(action_id=action["action_id"]))


def test_evidence_answer_and_credit_offer_are_available_in_portal(portal):
    from samvaad.service import LocalService

    page, db_path = portal
    button(page, "Ask selected question").click().run()
    assert not page.exception and not page.error
    assert len(page.chat_message) == 2
    assert any(item.label.startswith("Supporting evidence (") for item in page.expander)
    assert any("Provider:" in item.value for item in page.caption)
    page.selectbox(key="customer_picker").set_value("C0003").run()
    button(page, "Generate next best action").click().run()
    service = LocalService(db_path=db_path)
    action = next(item for item in service.actions() if item["customer_id"] == "C0003")
    page.selectbox(key="action_review").set_value(action["action_id"]).run()
    page.selectbox(key="demo_operator").set_value("Kavya · Credit officer").run()
    button(page, "Approve action").click().run()
    button(page, "Run simulated action").click().run()
    assert not page.exception and not page.error
    offers = service.offers("C0003")
    assert len(offers) == 1
    assert offers[0]["expires_at"] and offers[0]["token"]


def test_new_hardship_interaction_recalculates_decision_and_replaces_queue(portal):
    from samvaad.service import LocalService

    page, db_path = portal
    page.selectbox(key="customer_picker").set_value("C0007").run()
    button(page, "Generate next best action").click().run()
    service = LocalService(db_path=db_path)
    previous = next(item for item in service.actions() if item["customer_id"] == "C0007")
    assert previous["action_code"] == "GENTLE_REMINDER_CALL"
    page.selectbox(key="interaction_channel_C0007").set_value("CALL_IN")
    page.text_area(key="interaction_text_C0007").set_value(
        "Customer: I was laid off last week. My EMI is overdue and I cannot pay this month. "
        "Can an officer discuss support options?"
    )
    button(page, "Add synthetic interaction").click().run()
    assert not page.exception and not page.error
    refreshed = service.customer360("C0007")
    assert refreshed["metrics"]["hardship_flag"]
    assert refreshed["current_decision"]["action_code"] == "HARDSHIP_RESTRUCTURE_CALL"
    assert refreshed["recommendation"]["action_id"] == previous["action_id"]
    assert any("Latest evidence changes" in item.value for item in page.warning)
    button(page, "Generate next best action").click().run()
    assert not page.exception and not page.error
    actions = [item for item in service.actions() if item["customer_id"] == "C0007"]
    assert next(item for item in actions if item["action_id"] == previous["action_id"])["status"] == "CANCELLED"
    current = next(item for item in actions if item["action_code"] == "HARDSHIP_RESTRUCTURE_CALL")
    assert current["status"] == "APPROVED"
    assert current["approved_by"] == "service-policy"


def _start_retention_voice(portal):
    from samvaad.service import LocalService
    from samvaad.voice import VoiceService

    page, db_path = portal
    service = LocalService(db_path=db_path)
    action = next(item for item in service.actions() if item["customer_id"] == "C0002")
    page.selectbox(key="action_review").set_value(action["action_id"]).run()
    page.selectbox(key="demo_operator").set_value("Arjun · Retention manager").run()
    button(page, "Approve action").click().run()
    assert not page.exception and not page.error
    button(page, "Start local voice session").click().run()
    assert not page.exception and not page.error
    voice = VoiceService(service)
    session = voice.sessions(customer_id="C0002")[0]
    return page, service, voice, session


def _say(page, session_id, text):
    page.text_area(key=f"voice_text_{session_id}").set_value(text)
    button(page, "Send borrower response").click().run()
    assert not page.exception and not page.error


def test_voice_lab_requires_approved_action(portal):
    page, _ = portal
    assert not any(item.label == "Start local voice session" for item in page.button)
    assert any("No approved action is available" in item.value for item in page.info)


def test_voice_permission_identity_and_interest_complete_approved_action(portal):
    page, service, voice, session = _start_retention_voice(portal)
    sid = session["session_id"]
    assert session["state"] == "AWAIT_PERMISSION"
    assert not session["permission_granted"] and not session["identity_confirmed"]
    _say(page, sid, "What are the terms?")
    assert voice.get(sid)["state"] == "AWAIT_PERMISSION"
    assert "100 basis points" not in voice.get(sid)["turns"][-1]["text"]
    _say(page, sid, "Yes, you may continue.")
    assert voice.get(sid)["state"] == "AWAIT_IDENTITY"
    _say(page, sid, "What are the terms?")
    assert voice.get(sid)["state"] == "AWAIT_IDENTITY"
    assert "100 basis points" not in voice.get(sid)["turns"][-1]["text"]
    _say(page, sid, "Yes, I am the account holder.")
    assert voice.get(sid)["state"] == "ACTIVE"
    assert "100 basis points" in voice.get(sid)["turns"][-1]["text"]
    _say(page, sid, "I am interested. Please proceed.")
    ended = voice.get(sid)
    assert ended["state"] == "ENDED" and ended["outcome"] == "ACCEPT"
    action = next(item for item in service.actions() if item["action_id"] == session["action_id"])
    assert action["status"] == "COMPLETED" and action["outcome"] == "ACCEPT"
    assert service.offers("C0002")
    assert any(item["interaction_id"] == "VOICE-" + sid for item in service.customer360("C0002")["interactions"])
    assert len(page.get("audio")) == 1


def test_voice_optout_before_identity_persists_and_blocks_contact(portal):
    page, service, voice, session = _start_retention_voice(portal)
    _say(page, session["session_id"], "Do not contact me again.")
    ended = voice.get(session["session_id"])
    assert ended["state"] == "ENDED" and ended["outcome"] == "OPT_OUT"
    customer = service.customer360("C0002")["customer"]
    assert not customer["consent_calls"] and not customer["consent_marketing"]
    assert not voice.available_actions("C0002")
    assert not any(i["interaction_id"] == "VOICE-" + session["session_id"] for i in service.customer360("C0002")["interactions"])


def test_voice_human_escalation_ends_with_callback(portal):
    page, service, voice, session = _start_retention_voice(portal)
    sid = session["session_id"]
    _say(page, sid, "Yes, you may continue.")
    _say(page, sid, "Yes, I am the account holder.")
    _say(page, sid, "Please connect me to a human officer.")
    assert voice.get(sid)["state"] == "ENDED"
    assert voice.get(sid)["outcome"] == "CALLBACK"
    assert not service.offers("C0002")


def test_voice_microphone_controls_and_operator_stop(portal):
    page, service, voice, session = _start_retention_voice(portal)
    sid = session["session_id"]
    page.radio(key=f"voice_input_mode_{sid}").set_value("Microphone / WAV").run()
    assert not page.exception and not page.error
    assert len(page.get("audio_input")) == 1
    assert len(page.get("file_uploader")) == 1
    button(page, "End voice session").click().run()
    assert not page.exception and not page.error
    assert voice.get(sid)["state"] == "ENDED" and voice.get(sid)["outcome"] == "CALLBACK"
    assert not service.offers("C0002")


@pytest.mark.parametrize("failure_path", ["recommendation", "assistant", "voice"])
def test_unexpected_errors_do_not_render_or_log_secret_payloads(portal, monkeypatch, caplog, failure_path):
    from samvaad.service import LocalService
    from samvaad import voice_audio

    page, _ = portal
    secret = "SECRET_DATABASE_PASSWORD__SHOULD_NEVER_APPEAR"

    def fail(*args, **kwargs):
        raise RuntimeError(secret)

    if failure_path == "recommendation":
        monkeypatch.setattr(LocalService, "recommend", fail)
        button(page, "Generate next best action").click().run()
        assert any("Please check the application logs" in item.value for item in page.error)
    elif failure_path == "assistant":
        monkeypatch.setattr(LocalService, "ask", fail)
        button(page, "Ask selected question").click().run()
        assert any("Unable to answer. Please check" in item.value for item in page.markdown)
    else:
        page, _, _, _ = _start_retention_voice(portal)
        monkeypatch.setattr(voice_audio, "synthesize", fail)
        st.cache_data.clear()
        page.run()
        assert any("Local voice request failed. Please check" in item.value for item in page.error)
    assert not page.exception
    rendered = "\n".join(item.value for item in page.markdown) + "\n".join(item.value for item in page.error)
    assert secret not in rendered
    records = [record for record in caplog.records if record.name.startswith("samvaad.")]
    assert any("RuntimeError" in record.getMessage() for record in records)
    assert all(secret not in record.getMessage() and record.exc_info is None for record in records)


