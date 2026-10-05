"""Voice boundary authentication, raw audio bounds, and controlled execution."""
import io
import wave

import pytest
from fastapi.testclient import TestClient

from samvaad.models import ActionError
from webhook.main import create_app

TOKENS = {"voice-test-analyst-token-length24": "meera", "voice-test-runner-token-length24": "local-runner"}


def auth(user):
    return {"Authorization": "Bearer " + next(t for t, u in TOKENS.items() if u == user)}


@pytest.fixture
def voice_client(service):
    with TestClient(create_app(service, TOKENS), raise_server_exceptions=False) as client:
        yield client


def test_voice_api_needs_auth_and_cannot_impersonate_runner(voice_client, service):
    assert voice_client.get("/api/voice/sessions").status_code == 401
    assert voice_client.get("/api/voice/status", headers=auth("meera")).json()["pstn_enabled"] is False
    aid = next(a["action_id"] for a in service.actions() if a["customer_id"] == "C0001")
    assert voice_client.post("/api/voice/sessions", json={"action_id": aid}, headers=auth("meera")).status_code == 403
    assert voice_client.post("/api/voice/sessions", json={"action_id": aid, "role": "AUTOMATION"}, headers=auth("meera")).status_code == 422
    session = voice_client.post("/api/voice/sessions", json={"action_id": aid}, headers=auth("local-runner"))
    assert session.status_code == 200 and session.json()["state"] == "AWAIT_PERMISSION"
    assert voice_client.get("/api/voice/sessions/missing", headers=auth("meera")).status_code == 404


def test_authenticated_voice_turn_optout_and_replay(voice_client, service):
    aid = next(a["action_id"] for a in service.actions() if a["customer_id"] == "C0001")
    session = voice_client.post("/api/voice/sessions", json={"action_id": aid}, headers=auth("local-runner")).json()
    route = "/api/voice/sessions/" + session["session_id"] + "/turn"
    body = {"text": "Stop calling me", "event_id": "voice-optout-01"}
    result = voice_client.post(route, json=body, headers=auth("local-runner"))
    assert result.status_code == 200 and result.json()["outcome"] == "OPT_OUT"
    before = service.audit()
    assert voice_client.post(route, json=body, headers=auth("local-runner")).json() == result.json()
    assert service.audit() == before
    assert not service.customer360("C0001")["customer"]["consent_calls"]


def test_audio_endpoint_rejects_wrong_format_and_oversized_input(voice_client):
    assert voice_client.post("/api/voice/transcribe", content=b"anything").status_code == 401
    assert voice_client.post("/api/voice/transcribe", json={}, headers=auth("meera")).status_code == 415
    headers = {**auth("meera"), "Content-Type": "audio/wav"}
    assert voice_client.post("/api/voice/transcribe", content=b"x" * 10_000_001, headers=headers).status_code == 413
    assert voice_client.post("/api/voice/transcribe", content=b"invalid wav", headers=headers).status_code == 409


def test_raw_audio_and_synthesis_api_do_not_accept_execution_fields(voice_client, monkeypatch):
    from samvaad import voice_audio
    monkeypatch.setattr(voice_audio, "synthesize", lambda text: {"audio": b"RIFF-demo", "mime_type": "audio/wav"})
    response = voice_client.post("/api/voice/speech", json={"text": "Hello synthetic borrower"}, headers=auth("meera"))
    assert response.status_code == 200 and response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    assert voice_client.post("/api/voice/speech", json={"text": "hello", "execute": True}, headers=auth("meera")).status_code == 422


def test_pcm_duration_checked_before_model_load():
    from samvaad.voice_audio import transcribe
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000 * 61)
    with pytest.raises(ActionError) as error:
        transcribe(data.getvalue())
    assert error.value.code == "INVALID_AUDIO"
