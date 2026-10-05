"""Real persisted conversation checks; no audio/network provider mocked here."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from samvaad.models import ActionError, Actor
from samvaad.voice import VoiceService


@pytest.fixture
def voice(service):
    return VoiceService(service)


def start_retention(service, voice):
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], service.resolve_actor("arjun"))
    return voice.start(action["action_id"], service.resolve_actor("local-runner"))


def activate(service, voice, session):
    runner = service.resolve_actor("local-runner")
    voice.turn(session["session_id"], "Yes, you may continue", "permission", runner)
    return voice.turn(session["session_id"], "Yes, I am the account holder", "identity", runner)


def test_unapproved_action_and_nonrunner_cannot_start(service, voice):
    action = service.recommend("C0002", service.resolve_actor("meera"))
    for actor, code in [(service.resolve_actor("local-runner"), "APPROVAL_REQUIRED"), (service.resolve_actor("arjun"), "FORBIDDEN"), (Actor("arjun", "AUTOMATION"), "FORBIDDEN")]:
        with pytest.raises(ActionError) as error:
            voice.start(action["action_id"], actor)
        assert error.value.code == code
    assert not voice.sessions() and not service.offers()


def test_permission_identity_and_approved_terms_before_accept(service, voice):
    session = start_retention(service, voice)
    assert session["state"] == "AWAIT_PERMISSION"
    assert "100 basis" not in str(session["turns"]) and "14%" not in str(session["turns"])
    runner = service.resolve_actor("local-runner")
    session = voice.turn(session["session_id"], "Yes", "permission", runner)
    assert session["state"] == "AWAIT_IDENTITY" and "100 basis" not in str(session["turns"])
    session = voice.turn(session["session_id"], "Yes, I am the account holder", "identity", runner)
    assert session["state"] == "ACTIVE" and "100 basis" in session["turns"][-1]["text"]
    session = voice.turn(session["session_id"], "I am interested", "interest", runner)
    assert session["state"] == "ENDED" and session["outcome"] == "ACCEPT"
    assert len(service.offers("C0002")) == 1
    view = service.customer360("C0002")
    transcript = next(i for i in view["interactions"] if i["interaction_id"] == "VOICE-" + session["session_id"])
    assert transcript["simulated"] and "Customer:" in transcript["text"] and "Agent:" in transcript["text"]
    assert "100 basis" not in transcript["evidence_text"]


@pytest.mark.parametrize("stage,text", [("permission", "Yes, but I do not consent"), ("identity", "Yes, but I am not the account holder")])
def test_negative_gate_never_discloses_terms(service, voice, stage, text):
    session = start_retention(service, voice)
    runner = service.resolve_actor("local-runner")
    if stage == "identity":
        voice.turn(session["session_id"], "Yes", "permission", runner)
    result = voice.turn(session["session_id"], text, "negative", runner)
    assert result["state"] == "ENDED"
    assert "100 basis" not in str(result["turns"]) and not service.offers()
    assert not any(i["interaction_id"].startswith("VOICE-") for i in service.customer360("C0002")["interactions"])


def test_optout_before_identity_and_duplicate_event_one_effect(service, voice):
    session = start_retention(service, voice)
    runner = service.resolve_actor("local-runner")
    result = voice.turn(session["session_id"], "Do not call me again", "optout", runner)
    assert result["outcome"] == "OPT_OUT"
    before = service.audit()
    assert voice.turn(session["session_id"], "Do not call me again", "optout", runner) == result
    assert service.audit() == before
    assert not service.customer360("C0002")["customer"]["consent_calls"]
    with pytest.raises(ActionError) as error:
        voice.turn(session["session_id"], "Yes", "optout", runner)
    assert error.value.code == "EVENT_CONFLICT"


def test_stale_approval_and_revocation_block_voice_start(service, voice):
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], service.resolve_actor("arjun"))
    service.update_catalogue("RETENTION_RATE_MATCH_CALL", service.resolve_actor("demo-admin"), max_rate_cut_bps=50)
    with pytest.raises(ActionError) as error:
        voice.start(action["action_id"], service.resolve_actor("local-runner"))
    assert error.value.code == "STALE_APPROVAL"
    assert not voice.sessions()


def test_no_new_terms_or_implicit_conditional_acceptance(service, voice):
    session = activate(service, voice, start_retention(service, voice))
    runner = service.resolve_actor("local-runner")
    result = voice.turn(session["session_id"], "I am interested only if you reduce by 500 basis points", "condition", runner)
    assert result["state"] == "ACTIVE" and not service.offers()
    assert "cannot negotiate" in result["turns"][-1]["text"]
    result = voice.turn(session["session_id"], "Please connect a human officer", "human", runner)
    assert result["state"] == "ENDED" and result["outcome"] == "CALLBACK"
    assert not service.offers()


def test_concurrent_start_and_end_create_one_session_and_effect(service, voice):
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], service.resolve_actor("arjun"))
    runner = service.resolve_actor("local-runner")
    with ThreadPoolExecutor(max_workers=2) as pool:
        sessions = list(pool.map(lambda _: voice.start(action["action_id"], runner), range(2)))
    assert sessions[0]["session_id"] == sessions[1]["session_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: voice.end(sessions[0]["session_id"], runner), range(2)))
    assert results[0] == results[1]
    assert next(a for a in service.actions() if a["action_id"] == action["action_id"])["attempts"] == 1
    assert len([e for e in service.audit() if e["event"] == "VOICE_SESSION_ENDED"]) == 1


def test_existing_session_stops_after_external_consent_revoke(service, voice):
    session = start_retention(service, voice)
    service.revoke_consent("C0002", service.resolve_actor("meera"))
    result = voice.turn(session["session_id"], "yes", "later-turn", service.resolve_actor("local-runner"))
    assert result["state"] == "ENDED" and result["outcome"] == "OPT_OUT"
    assert not service.offers()


def test_reset_cascades_sessions_and_turns(service, voice):
    session = start_retention(service, voice)
    service.reset_demo(service.resolve_actor("demo-admin"))
    assert not voice.sessions() and len(service.list_customers()) == 20
    with pytest.raises(ActionError):
        voice.get(session["session_id"])
