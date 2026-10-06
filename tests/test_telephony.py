"""Controlled-pilot calling gates, durable dispatch, actual HTTP contract, callbacks.

Transport doubles isolate unit tests from paid carrier operations; these tests
are not evidence that a call or SMS has reached a telephone.
"""
import base64
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from urllib.parse import urlencode, parse_qs

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from samvaad.models import ActionError, Actor
from samvaad.service import timestamp, utcnow
from samvaad.telephony import ProviderFailure, TelephonyService, TelephonySettings, TwilioProvider, e164, validate_signature
from webhook.telephony_routes import build_telephony_router

PHONE = "+15017122661"  # Documentation number; tests never contact a carrier.
CALL = "CA" + "a" * 32
VERIFY = "VE" + "b" * 32


@pytest.fixture
def settings():
    return TelephonySettings(enabled=True, account_sid="AC" + "c" * 32,
        auth_token="test-signature-token-not-provider-secret", verify_service_sid="VA" + "d" * 32,
        from_number="+15005550006", public_url="https://voice.example.invalid",
        permitted_prefixes=("+1",), authorised_test_numbers=(PHONE,), start_hour=0, end_hour=24)


class Provider:
    def __init__(self, settings):
        self.settings = settings
        self.calls = []
        self.verifications = []
        self.failure = None
        self.check_status = "approved"

    def start_verification(self, phone):
        self.verifications.append(phone)
        return {"sid": VERIFY, "status": "pending", "to": phone, "service_sid": self.settings.verify_service_sid}

    def check_verification(self, sid, code):
        return {"sid": sid, "status": self.check_status, "to": PHONE, "service_sid": self.settings.verify_service_sid}

    def create_call(self, phone, call_id):
        self.calls.append((phone, call_id))
        if self.failure:
            raise self.failure
        return {"sid": CALL, "account_sid": self.settings.account_sid, "status": "queued"}

    def get_call(self, sid):
        return {"sid": sid, "account_sid": self.settings.account_sid, "status": "completed"}

    def cancel_call(self, sid):
        return self.get_call(sid)


@pytest.fixture
def pilot(service, settings):
    provider = Provider(settings)
    return TelephonyService(service, settings, provider), provider


def recipient(pilot, service, cid="C0002"):
    telephony, _ = pilot
    operator = service.resolve_actor("arjun")
    row = telephony.request_verification(cid, PHONE, "alternate", "Owner requested a controlled live test", True, operator)
    return telephony.verify(row["recipient_id"], "123456", operator)


def ready_call(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], service.resolve_actor("arjun"))
    call = telephony.start(action["action_id"], person["recipient_id"], "live-request-test-001", service.resolve_actor("arjun"), True)
    return telephony, provider, call


def event(settings, **values):
    return {"AccountSid": settings.account_sid, "CallSid": CALL, "To": PHONE, "From": settings.from_number, **values}


@pytest.mark.parametrize("phone", ["******0000", "15017122661", "+01234567890", "+1", "+1 5017122661", None])
def test_e164_rejects_masked_ambiguous_and_invalid_inputs(phone):
    with pytest.raises(ActionError):
        e164(phone)


def test_default_disabled_configuration_never_invokes_transport(service, settings):
    provider = Provider(settings)
    telephony = TelephonyService(service, provider=provider)
    assert not telephony.status()["pilot_ready"] and not telephony.status()["production_ready"]
    with pytest.raises(ActionError, match="disabled"):
        telephony.request_verification("C0002", PHONE, "alternate", "Owner asked for a live test", True, service.resolve_actor("arjun"))
    assert not provider.calls and not provider.verifications


def test_exact_destination_allowlist_and_staff_role_before_delivery(pilot, service):
    telephony, provider = pilot
    for actor in [service.resolve_actor("meera"), Actor("arjun", "ADMIN")]:
        with pytest.raises(ActionError):
            telephony.request_verification("C0002", PHONE, "alternate", "Owner asked for a live test", True, actor)
    with pytest.raises(ActionError, match="outside"):
        telephony.request_verification("C0002", "+15017122662", "alternate", "Owner asked for a live test", True, service.resolve_actor("arjun"))
    assert not provider.verifications


def test_primary_must_match_account_and_alternate_needs_requested_verification(pilot, service):
    telephony, provider = pilot
    for source, requested, code in [("primary", True, "PRIMARY_PHONE_MISMATCH"), ("alternate", False, "RECIPIENT_CONSENT_REQUIRED")]:
        with pytest.raises(ActionError) as error:
            telephony.request_verification("C0002", PHONE, source, "Owner asked for a live test", requested, service.resolve_actor("arjun"))
        assert error.value.code == code
    assert not provider.verifications


def test_provider_verification_is_required_not_a_local_flag(pilot, service):
    telephony, provider = pilot
    actor = service.resolve_actor("arjun")
    row = telephony.request_verification("C0002", PHONE, "alternate", "Owner requested a live controlled test", True, actor)
    assert row["verified"] is False and row["phone_masked"] == "***2661"
    assert VERIFY not in json.dumps(row) and PHONE not in json.dumps(row)
    provider.check_status = "pending"
    with pytest.raises(ActionError) as error:
        telephony.verify(row["recipient_id"], "123456", actor)
    assert error.value.code == "VERIFICATION_FAILED"
    provider.check_status = "approved"
    assert telephony.verify(row["recipient_id"], "123456", actor)["verified"]


def test_verified_recipient_approval_and_acknowledgement_required(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    with pytest.raises(ActionError) as error:
        telephony.start(action["action_id"], person["recipient_id"], "unapproved-live-request", actor, True)
    assert error.value.code == "APPROVAL_REQUIRED"
    service.approve_action(action["action_id"], actor)
    with pytest.raises(ActionError) as error:
        telephony.start(action["action_id"], person["recipient_id"], "unacknowledged-live-request", actor)
    assert error.value.code == "LIVE_CALL_ACKNOWLEDGEMENT_REQUIRED"
    assert not provider.calls


def test_parallel_idempotent_dispatch_has_one_provider_request(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    service.approve_action(action["action_id"], actor)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: telephony.start(action["action_id"], person["recipient_id"], "parallel-live-request", actor, True), range(2)))
    assert results[0]["call_id"] == results[1]["call_id"] and len(provider.calls) == 1
    with pytest.raises(ActionError) as error:
        telephony.start(action["action_id"], "another-recipient", "parallel-live-request", actor, True)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"


def test_ambiguous_dispatch_is_durable_and_never_redialed(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    service.approve_action(action["action_id"], actor)
    provider.failure = ProviderFailure(uncertain=True)
    with pytest.raises(ActionError) as error:
        telephony.start(action["action_id"], person["recipient_id"], "uncertain-live-request", actor, True)
    assert error.value.code == "CALL_DISPATCH_UNCERTAIN"
    saved = telephony.calls(actor)[0]
    assert saved["status"] == "DISPATCH_UNCERTAIN" and saved["provider_sid"] is None
    restarted = TelephonyService(service, telephony.settings, provider)
    assert restarted.start(action["action_id"], person["recipient_id"], "uncertain-live-request", actor, True)["call_id"] == saved["call_id"]
    with pytest.raises(ActionError):
        restarted.start(action["action_id"], person["recipient_id"], "new-key-after-uncertainty", actor, True)
    with pytest.raises(ActionError) as error:
        restarted.reconcile(saved["call_id"], actor)
    assert error.value.code == "RECONCILIATION_REQUIRED" and len(provider.calls) == 1


def test_stale_approval_consent_dnd_or_expired_recipient_blocks_delivery(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    service.approve_action(action["action_id"], actor)
    service.revoke_consent("C0002", service.resolve_actor("meera"))
    with pytest.raises(ActionError):
        telephony.start(action["action_id"], person["recipient_id"], "withdrawn-contact-request", actor, True)
    assert not provider.calls


def test_contact_window_and_call_budget(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    service.approve_action(action["action_id"], actor)
    local_hour = utcnow().astimezone(__import__("zoneinfo").ZoneInfo(telephony.settings.timezone)).hour
    start = (local_hour + 1) % 24
    telephony.settings = replace(telephony.settings, start_hour=start, end_hour=start + 1)
    with pytest.raises(ActionError) as error:
        telephony.start(action["action_id"], person["recipient_id"], "outside-contact-window", actor, True)
    assert error.value.code == "CALLING_WINDOW_CLOSED" and not provider.calls


@pytest.mark.parametrize("change", ["stale_offer", "expired_recipient", "dnd"])
def test_fresh_recipient_and_offer_gates_hold_real_dispatch(pilot, service, change):
    telephony, provider = pilot
    person = recipient(pilot, service)
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    service.approve_action(action["action_id"], actor)
    if change == "stale_offer":
        service.update_catalogue("RETENTION_RATE_MATCH_CALL", service.resolve_actor("demo-admin"), max_rate_cut_bps=50)
    elif change == "expired_recipient":
        with service._db(write=True) as con:
            con.execute("UPDATE telephony_recipients SET verified_until=? WHERE recipient_id=?", (timestamp(utcnow() - timedelta(seconds=1)), person["recipient_id"]))
    else:
        with service._db(write=True) as con:
            con.execute("UPDATE customers SET dnd=1 WHERE customer_id='C0002'")
    with pytest.raises(ActionError):
        telephony.start(action["action_id"], person["recipient_id"], "fresh-gate-" + change, actor, True)
    assert not provider.calls


def test_verified_number_cannot_authorise_another_customer(pilot, service):
    telephony, provider = pilot
    person = recipient(pilot, service, "C0003")
    action = service.recommend("C0002", service.resolve_actor("meera"))
    actor = service.resolve_actor("arjun")
    service.approve_action(action["action_id"], actor)
    with pytest.raises(ActionError) as error:
        telephony.start(action["action_id"], person["recipient_id"], "cross-customer-live-request", actor, True)
    assert error.value.code == "VERIFIED_RECIPIENT_REQUIRED" and not provider.calls


def test_permission_identity_and_call_input_replays_never_disclose_financial_terms(pilot, service, settings):
    telephony, _, call = ready_call(pilot, service)
    cid = call["call_id"]
    opener = telephony.conversation(cid, event(settings))
    assert "Gather" in opener and "transcript" in opener and "100 basis" not in opener
    permission = event(settings, Digits="1")
    assert "registered account holder" in telephony.conversation(cid, permission, 0)
    before = telephony.get(cid, service.resolve_actor("arjun"))
    assert telephony.conversation(cid, permission, 0)
    assert telephony.get(cid, service.resolve_actor("arjun"))["turns"] == before["turns"]
    proposal = telephony.conversation(cid, event(settings, Digits="1"), 1)
    assert "will not disclose financial" in proposal and "100 basis" not in proposal and "14%" not in proposal
    result = telephony.conversation(cid, event(settings, SpeechResult="I am interested"), 2)
    assert "Hangup" in result
    saved = telephony.get(cid, service.resolve_actor("arjun"))
    assert saved["outcome"] == "INTEREST_RECORDED" and not service.offers("C0002")
    assert not saved["financial_execution"]


@pytest.mark.parametrize("text", ["I do not consent", "Yes, but I am not the account holder"])
def test_negative_early_gate_ends_without_account_terms(pilot, service, settings, text):
    telephony, _, call = ready_call(pilot, service)
    cid = call["call_id"]
    telephony.conversation(cid, event(settings))
    if "account holder" in text:
        telephony.conversation(cid, event(settings, Digits="1"), 0)
        step = 1
    else:
        step = 0
    result = telephony.conversation(cid, event(settings, SpeechResult=text), step)
    assert "Hangup" in result and "100 basis" not in result
    assert not service.offers("C0002")


def test_optout_is_global_before_identity_and_replayed_once(pilot, service, settings):
    telephony, _, call = ready_call(pilot, service)
    cid = call["call_id"]
    values = event(settings, SpeechResult="Stop calling me")
    result = telephony.conversation(cid, values, 0)
    assert "Hangup" in result and not service.customer360("C0002")["customer"]["consent_calls"]
    audit = service.audit()
    assert telephony.conversation(cid, values, 0) == result and service.audit() == audit
    assert not any(t["speaker"] == "borrower" for t in telephony.get(cid, service.resolve_actor("arjun"))["turns"])
    assert not telephony.recipients("C0002", service.resolve_actor("arjun"))[0]["verified"]


def test_hardship_turn_refreshes_customer_evidence_without_invitation(pilot, service, settings):
    telephony, _, call = ready_call(pilot, service)
    cid = call["call_id"]
    telephony.conversation(cid, event(settings, Digits="1"), 0)
    telephony.conversation(cid, event(settings, Digits="1"), 1)
    telephony.conversation(cid, event(settings, SpeechResult="I lost my job and cannot afford payments"), 2)
    saved = telephony.get(cid, service.resolve_actor("arjun"))
    assert saved["outcome"] == "HARDSHIP_HANDOFF"
    view = service.customer360("C0002")
    evidence = next(i for i in view["interactions"] if i["interaction_id"] == "TEL-" + cid)
    assert not evidence["simulated"] and evidence["intent"] == "financial hardship"
    assert "I lost my job" in evidence["evidence_text"] and not service.offers("C0002")


def test_status_terminal_and_sequence_prevent_regression(pilot, service, settings):
    telephony, _, call = ready_call(pilot, service)
    cid = call["call_id"]
    telephony.provider_status(cid, event(settings, CallStatus="ringing", SequenceNumber="2"))
    telephony.provider_status(cid, event(settings, CallStatus="initiated", SequenceNumber="1"))
    assert telephony.get(cid, service.resolve_actor("arjun"))["status"] == "ringing"
    telephony.provider_status(cid, event(settings, CallStatus="completed", SequenceNumber="3"))
    telephony.provider_status(cid, event(settings, CallStatus="ringing", SequenceNumber="4"))
    assert telephony.get(cid, service.resolve_actor("arjun"))["status"] == "completed"


def test_no_answer_is_retryable_with_contact_interval_not_completed_preference(pilot, service, settings):
    telephony, provider, call = ready_call(pilot, service)
    telephony.provider_status(call["call_id"], event(settings, CallStatus="no-answer", SequenceNumber="3"))
    action = next(a for a in service.actions() if a["action_id"] == call["action_id"])
    assert action["status"] == "APPROVED" and action["outcome"] == "NO_ANSWER"
    with pytest.raises(ActionError) as error:
        telephony.start(call["action_id"], call["recipient_id"], "retry-before-four-hours", service.resolve_actor("arjun"), True)
    assert error.value.code == "RETRY_TOO_SOON" and len(provider.calls) == 1


def test_verified_callback_identity_cannot_bind_another_call(pilot, service, settings):
    telephony, _, call = ready_call(pilot, service)
    with pytest.raises(ActionError):
        telephony.callback_identity(call["call_id"], event(settings, CallSid="CA" + "e" * 32))
    with pytest.raises(ActionError):
        telephony.callback_identity(call["call_id"], event(settings, AccountSid="AC" + "f" * 32))


def test_expired_or_repeated_verification_cannot_be_forced(pilot, service):
    telephony, _ = pilot
    actor = service.resolve_actor("arjun")
    row = telephony.request_verification("C0002", PHONE, "alternate", "Owner requested a live controlled test", True, actor)
    with service._db(write=True) as con:
        con.execute("UPDATE telephony_recipients SET created_at=? WHERE recipient_id=?", (timestamp(utcnow() - timedelta(minutes=11)), row["recipient_id"]))
    with pytest.raises(ActionError) as error:
        telephony.verify(row["recipient_id"], "123456", actor)
    assert error.value.code == "VERIFICATION_EXPIRED"


def test_http_transport_uses_real_provider_contract_and_no_write_retry(settings, monkeypatch):
    captured = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, *_): return json.dumps({"sid": CALL, "account_sid": settings.account_sid, "status": "queued"}).encode()
    class Opener:
        def open(self, request, timeout):
            captured.append((request, timeout))
            return Connection()
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: Opener())
    TwilioProvider(settings).create_call(PHONE, "request-id")
    request, timeout = captured[0]
    values = parse_qs(request.data.decode())
    assert request.full_url == f"https://api.twilio.com/2010-04-01/Accounts/{settings.account_sid}/Calls.json"
    assert values["To"] == [PHONE] and values["Record"] == ["false"]
    assert values["StatusCallbackEvent"] == ["initiated", "ringing", "answered", "completed"]
    assert timeout == 12 and "Authorization" in request.headers
    def fail(*_args, **_kwargs):
        captured.append("failure")
        raise TimeoutError()
    monkeypatch.setattr(Opener, "open", fail)
    with pytest.raises(ProviderFailure) as error:
        TwilioProvider(settings).create_call(PHONE, "ambiguous-request")
    assert error.value.uncertain and captured.count("failure") == 1


def signature(settings, url, values):
    payload = url + "".join(k + values[k] for k in sorted(values))
    return base64.b64encode(hmac.new(settings.auth_token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


def test_signed_callback_route_checks_canonical_url_account_and_body_bounds(pilot, service, settings):
    telephony, _, call = ready_call(pilot, service)
    app = FastAPI()
    def operator():
        return service.resolve_actor("arjun")
    app.include_router(build_telephony_router(service, operator, telephony))
    route = "/telephony/twilio/" + call["call_id"] + "/answer"
    values = event(settings)
    with TestClient(app) as client:
        assert client.post(route, data=values).status_code == 403
        headers = {"X-Twilio-Signature": signature(settings, settings.public_url + route, values)}
        response = client.post(route, data=values, headers=headers)
        assert response.status_code == 200 and "Gather" in response.text
        tampered = dict(values, AccountSid="AC" + "e" * 32)
        assert client.post(route, data=tampered, headers=headers).status_code == 403
        assert client.post(route, content=b"a" * 16385, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 413
        assert not validate_signature(settings.auth_token, settings.public_url + route + "?step=1", values, headers["X-Twilio-Signature"])


@pytest.mark.parametrize("status,outcome", [("busy", "NO_ANSWER"), ("no-answer", "NO_ANSWER"),
    ("failed", "FAILED"), ("completed", "DISCONNECTED"), ("canceled", "DISCONNECTED")])
def test_terminal_dispatch_reply_finishes_action_before_callback(pilot, service, settings, monkeypatch, status, outcome):
    telephony, provider = pilot
    person = recipient(pilot, service)
    actor = service.resolve_actor("arjun")
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], actor)
    monkeypatch.setattr(provider, "create_call", lambda *_: {"sid": CALL, "account_sid": settings.account_sid, "status": status})
    call = telephony.start(action["action_id"], person["recipient_id"], "terminal-reply-" + status, actor, True)
    saved_action = next(a for a in service.actions() if a["action_id"] == action["action_id"])
    assert call["status"] == status and call["conversation_state"] == "ENDED" and call["outcome"] == outcome
    assert saved_action["status"] == "APPROVED" and saved_action["outcome"] == outcome
    turns = call["turns"]
    telephony.provider_status(call["call_id"], event(settings, CallStatus=status, SequenceNumber="0"))
    assert telephony.get(call["call_id"], actor)["turns"] == turns


@pytest.mark.parametrize("reply", [None, [], {"sid": None}, {"sid": CALL, "status": []},
    {"sid": CALL, "status": "queued", "account_sid": "AC" + "f" * 32}])
def test_malformed_dispatch_reply_stays_uncertain_and_cannot_redial(pilot, service, monkeypatch, reply):
    telephony, provider = pilot
    person = recipient(pilot, service)
    actor = service.resolve_actor("arjun")
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], actor)
    requests = []
    def malformed(*args):
        requests.append(args)
        return reply
    monkeypatch.setattr(provider, "create_call", malformed)
    with pytest.raises(ActionError) as failure:
        telephony.start(action["action_id"], person["recipient_id"], "malformed-provider-reply", actor, True)
    assert failure.value.code == "CALL_DISPATCH_UNCERTAIN"
    call = telephony.start(action["action_id"], person["recipient_id"], "malformed-provider-reply", actor, True)
    assert call["status"] == "DISPATCH_UNCERTAIN" and call["real_provider"] and not call["financial_execution"]
    assert "turns" in call and len(requests) == 1


@pytest.mark.parametrize("reply", [None, [], {"sid": None, "status": "pending"}])
def test_malformed_verification_reply_never_verifies_phone(pilot, service, monkeypatch, reply):
    telephony, provider = pilot
    monkeypatch.setattr(provider, "start_verification", lambda *_: reply)
    with pytest.raises(ActionError) as failure:
        telephony.request_verification("C0002", PHONE, "alternate", "Owner requested a live controlled test", True, service.resolve_actor("arjun"))
    assert failure.value.code == "VERIFICATION_UNCONFIRMED"
    saved = telephony.recipients("C0002", service.resolve_actor("arjun"))[0]
    assert saved["verification_status"] == "UNCERTAIN" and not saved["verified"]


def test_callback_winning_timeout_race_keeps_confirmed_terminal_state(pilot, service, settings, monkeypatch):
    telephony, provider = pilot
    person = recipient(pilot, service)
    actor = service.resolve_actor("arjun")
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], actor)
    provider.failure = ProviderFailure()
    original_db = service._db
    @contextmanager
    def callback_after_rollback(write=False):
        try:
            with original_db(write=write) as con:
                yield con
        except ProviderFailure:
            call_id = provider.calls[-1][1]
            values = event(settings, CallStatus="no-answer", SequenceNumber="3")
            telephony.callback_identity(call_id, values)
            telephony.provider_status(call_id, values)
            raise
    monkeypatch.setattr(service, "_db", callback_after_rollback)
    with pytest.raises(ActionError) as failure:
        telephony.start(action["action_id"], person["recipient_id"], "callback-timeout-race", actor, True)
    assert failure.value.code == "CALL_DISPATCH_UNCERTAIN"
    saved = telephony.calls(actor)[0]
    assert saved["provider_sid"] == CALL and saved["status"] == "no-answer" and saved["outcome"] == "NO_ANSWER"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("change", ["terminal", "consent"])
def test_cached_answer_cannot_restart_contact_after_stop(pilot, service, settings, change):
    telephony, _, call = ready_call(pilot, service)
    values = event(settings)
    assert "Gather" in telephony.conversation(call["call_id"], values)
    if change == "terminal":
        telephony.provider_status(call["call_id"], event(settings, CallStatus="completed", SequenceNumber="3"))
    else:
        service.revoke_consent("C0002", service.resolve_actor("meera"))
    response = telephony.conversation(call["call_id"], values)
    assert "Hangup" in response and "Gather" not in response
    audit = service.audit()
    assert "Hangup" in telephony.conversation(call["call_id"], values) and service.audit() == audit


@pytest.mark.parametrize("reply", [None, [], {}, {"sid": CALL, "status": []}])
def test_malformed_reconciliation_reply_is_unconfirmed(pilot, service, monkeypatch, reply):
    telephony, provider, call = ready_call(pilot, service)
    monkeypatch.setattr(provider, "get_call", lambda *_: reply)
    with pytest.raises(ActionError) as failure:
        telephony.reconcile(call["call_id"], service.resolve_actor("arjun"))
    assert failure.value.code == "PROVIDER_STATUS_UNCONFIRMED"
    assert telephony.get(call["call_id"], service.resolve_actor("arjun"))["status"] == "queued"


@pytest.mark.parametrize("change", ["recipient", "action"])
def test_dispatch_rechecks_durable_recipient_and_action_after_reservation(pilot, service, monkeypatch, change):
    telephony, provider = pilot
    person = recipient(pilot, service)
    actor = service.resolve_actor("arjun")
    action = service.recommend("C0002", service.resolve_actor("meera"))
    service.approve_action(action["action_id"], actor)
    original_db = service._db
    writes = 0
    @contextmanager
    def policy_changes_between_transactions(write=False):
        nonlocal writes
        if write:
            writes += 1
            if writes == 2:
                with original_db(write=True) as con:
                    if change == "recipient":
                        con.execute("UPDATE telephony_recipients SET verified_until=? WHERE recipient_id=?",
                                    (timestamp(utcnow() - timedelta(seconds=1)), person["recipient_id"]))
                    else:
                        con.execute("UPDATE actions SET status='COMPLETED',outcome='DECLINE' WHERE action_id=?", (action["action_id"],))
        with original_db(write=write) as con:
            yield con
    monkeypatch.setattr(service, "_db", policy_changes_between_transactions)
    with pytest.raises(ActionError):
        telephony.start(action["action_id"], person["recipient_id"], "changed-after-reservation", actor, True)
    assert not provider.calls and telephony.calls(actor)[0]["status"] == "canceled"
    saved_action = next(a for a in service.actions() if a["action_id"] == action["action_id"])
    assert saved_action["status"] == ("APPROVED" if change == "recipient" else "COMPLETED")


def test_mid_response_connection_reset_remains_uncertain(settings, monkeypatch):
    requests = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self, *_): raise ConnectionResetError("private provider details")
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Connection()
    monkeypatch.setattr("urllib.request.build_opener", lambda *_: Opener())
    with pytest.raises(ProviderFailure) as failure:
        TwilioProvider(settings).create_call(PHONE, "body-reset-request")
    assert failure.value.uncertain and len(requests) == 1 and "private provider details" not in str(failure.value)


def test_non_ascii_provider_signature_is_rejected(settings):
    assert not validate_signature(settings.auth_token, settings.public_url, {}, "\u00e9")
