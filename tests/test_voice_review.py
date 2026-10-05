"""Voice regressions for changed eligibility and conflicting completion events."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from samvaad.models import ActionError
from samvaad.voice import VoiceService


def approved_session(service, customer_id, approver):
    voice = VoiceService(service)
    action = service.recommend(customer_id, service.resolve_actor("meera"))
    service.approve_action(action["action_id"], service.resolve_actor(approver))
    session = voice.start(action["action_id"], service.resolve_actor("local-runner"))
    return voice, action, session


def activate(service, voice, session):
    runner = service.resolve_actor("local-runner")
    voice.turn(session["session_id"], "Yes, you may continue", "permission", runner)
    return voice.turn(session["session_id"], "Yes, I am the account holder", "identity", runner)


@pytest.mark.parametrize("utterance", [
    "I do not accept this invitation",
    "I cannot accept this invitation",
    "I don't accept this invitation",
    "I won't accept this invitation",
    "I am uninterested",
])
def test_negative_interest_never_creates_offer(service, utterance):
    voice, action, session = approved_session(service, "C0002", "arjun")
    session = activate(service, voice, session)
    result = voice.turn(session["session_id"], utterance, "response", service.resolve_actor("local-runner"))
    assert result["outcome"] != "ACCEPT"
    assert not service.offers("C0002")
    stored = next(item for item in service.actions() if item["action_id"] == action["action_id"])
    assert stored["outcome"] != "ACCEPT"


def test_hardship_in_active_turn_suppresses_financial_invitation(service):
    voice, action, session = approved_session(service, "C0003", "kavya")
    session = activate(service, voice, session)
    result = voice.turn(session["session_id"], "I lost my job. Yes, please proceed.", "changed-circumstances", service.resolve_actor("local-runner"))
    assert result["state"] == "ENDED" and result["outcome"] == "CALLBACK"
    assert not service.offers("C0003")
    view = service.customer360("C0003")
    transcript = next(item for item in view["interactions"] if item["interaction_id"] == "VOICE-" + session["session_id"])
    assert transcript["intent"] == "financial hardship"
    assert view["metrics"]["hardship_flag"] and not view["metrics"]["topup_eligible"]
    assert view["current_decision"]["action_code"] != "TOPUP_PREAPPROVAL_CALL"


def test_hardship_before_identity_prevents_disclosure_of_growth_terms(service):
    voice, action, session = approved_session(service, "C0003", "kavya")
    runner = service.resolve_actor("local-runner")
    session = voice.turn(session["session_id"], "Yes, you may continue. I lost my job.", "permission", runner)
    assert session["state"] == "AWAIT_IDENTITY"
    result = voice.turn(session["session_id"], "Yes, I am the account holder", "identity", runner)
    assert result["state"] == "ENDED" and result["outcome"] == "CALLBACK"
    assert not service.offers("C0003")
    assert "credit-approved synthetic invitation" not in str(result["turns"])
    transcript = next(item for item in service.customer360("C0003")["interactions"] if item["interaction_id"] == "VOICE-" + session["session_id"])
    assert transcript["intent"] == "financial hardship"


def test_external_completion_does_not_fabricate_optout(service):
    voice, action, session = approved_session(service, "C0002", "arjun")
    session = activate(service, voice, session)
    runner = service.resolve_actor("local-runner")
    service.record_response(action["action_id"], "CALLBACK", "independent-response", runner)
    assert service.customer360("C0002")["customer"]["consent_calls"]
    result = voice.turn(session["session_id"], "Could you repeat that?", "after-completion", runner)
    assert result["state"] == "ENDED" and result["outcome"] != "OPT_OUT"
    assert service.customer360("C0002")["customer"]["consent_calls"]
    stored = next(item for item in service.actions() if item["action_id"] == action["action_id"])
    assert stored["outcome"] == "CALLBACK"
    assert not service.offers("C0002")


@pytest.mark.parametrize("utterance,outcome", [
    ("No, I do not consent to saving my transcript. Private reference ABC-123.", "CALLBACK"),
    ("Do not call me again. Private reference ABC-123.", "OPT_OUT"),
])
def test_refusal_and_optout_before_recording_permission_never_store_raw_text(service, utterance, outcome):
    voice, action, session = approved_session(service, "C0002", "arjun")
    runner = service.resolve_actor("local-runner")
    result = voice.turn(session["session_id"], utterance, "unconsented-event", runner)
    assert result["state"] == "ENDED" and result["outcome"] == outcome
    assert not result["permission_granted"]
    assert not [turn for turn in result["turns"] if turn["role"] == "borrower"]
    assert "ABC-123" not in str(result)
    view = service.customer360("C0002")
    assert not any(item["interaction_id"] == "VOICE-" + session["session_id"] for item in view["interactions"])
    with service._db() as connection:
        stored = connection.execute("SELECT text,payload_hash FROM voice_events WHERE session_id=?", (session["session_id"],)).fetchone()
    assert stored["text"] == "" and len(stored["payload_hash"]) == 64
    before = service.audit()
    assert voice.turn(session["session_id"], utterance, "unconsented-event", runner) == result
    assert service.audit() == before
    with pytest.raises(ActionError) as error:
        voice.turn(session["session_id"], "Yes, you may continue", "unconsented-event", runner)
    assert error.value.code == "EVENT_CONFLICT"
    assert not service.offers("C0002")


def test_ambiguous_permission_keeps_only_fingerprint_until_explicit_consent(service):
    voice, action, session = approved_session(service, "C0002", "arjun")
    runner = service.resolve_actor("local-runner")
    result = voice.turn(session["session_id"], "My private reference is ABC-123", "unclear-permission", runner)
    assert result["state"] == "AWAIT_PERMISSION" and not result["permission_granted"]
    assert "ABC-123" not in str(result)
    assert not [turn for turn in result["turns"] if turn["role"] == "borrower"]
    result = voice.turn(session["session_id"], "Yes, you may save this transcript", "consent-granted", runner)
    assert result["state"] == "AWAIT_IDENTITY" and result["permission_granted"]
    assert [turn["text"] for turn in result["turns"] if turn["role"] == "borrower"] == ["Yes, you may save this transcript"]
    assert not service.offers("C0002")


def test_legacy_raw_event_replays_migrate_to_fingerprint_and_preserve_conflict_guard(service):
    # Exercise the existing three-column local schema, not only a new database.
    with service._db(write=True) as connection:
        connection.execute("CREATE TABLE voice_events (session_id TEXT NOT NULL REFERENCES voice_sessions ON DELETE CASCADE,event_id TEXT NOT NULL,text TEXT NOT NULL,PRIMARY KEY(session_id,event_id))")
    voice, action, session = approved_session(service, "C0002", "arjun")
    runner = service.resolve_actor("local-runner")
    with service._db(write=True) as connection:
        connection.execute("INSERT INTO voice_events (session_id,event_id,text) VALUES (?,?,?)", (session["session_id"], "legacy-response", "No, please stop this test"))
    before = service.audit()
    assert voice.turn(session["session_id"], "No, please stop this test", "legacy-response", runner) == session
    assert service.audit() == before
    with service._db() as connection:
        stored = connection.execute("SELECT text,payload_hash FROM voice_events WHERE session_id=?", (session["session_id"],)).fetchone()
    assert stored["text"] == "" and len(stored["payload_hash"]) == 64
    with pytest.raises(ActionError) as error:
        voice.turn(session["session_id"], "Yes", "legacy-response", runner)
    assert error.value.code == "EVENT_CONFLICT"
    assert not voice.get(session["session_id"])["permission_granted"]


def test_unconsented_hardship_stops_growth_offer_without_retaining_utterance(service):
    voice, action, session = approved_session(service, "C0002", "arjun")
    utterance = "I lost my job and cannot pay my EMI"
    result = voice.turn(session["session_id"], utterance, "unconsented-hardship", service.resolve_actor("local-runner"))
    assert result["state"] == "ENDED" and result["outcome"] == "CALLBACK"
    assert not result["permission_granted"] and not result["identity_confirmed"]
    assert not [turn for turn in result["turns"] if turn["role"] == "borrower"]
    assert utterance not in str(result)
    assert "100 basis" not in str(result["turns"])
    assert "officer review" in result["turns"][-1]["text"]
    assert not service.offers("C0002")
    with service._db() as connection:
        event = connection.execute("SELECT text,payload_hash FROM voice_events WHERE session_id=?", (session["session_id"],)).fetchone()
    assert event["text"] == "" and len(event["payload_hash"]) == 64
    assert not any(item["interaction_id"] == "VOICE-" + session["session_id"] for item in service.customer360("C0002")["interactions"])


def test_concurrent_legacy_schema_initialization_is_atomic(service):
    with service._db(write=True) as connection:
        connection.execute("CREATE TABLE voice_events (session_id TEXT NOT NULL REFERENCES voice_sessions ON DELETE CASCADE,event_id TEXT NOT NULL,text TEXT NOT NULL,PRIMARY KEY(session_id,event_id))")
    with ThreadPoolExecutor(max_workers=4) as pool:
        providers = list(pool.map(lambda _: VoiceService(service), range(4)))
    assert all(not provider.sessions() for provider in providers)
    with service._db() as connection:
        columns = [row["name"] for row in connection.execute("PRAGMA table_info(voice_events)")]
    assert columns.count("payload_hash") == 1
