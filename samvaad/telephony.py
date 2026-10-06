"""Genuine Twilio transport and durable, guarded controlled-pilot phone calls.

Provider requests are never replaced with simulated success. The default is
disabled. SQLite and existing local operator identities support a controlled
pilot; they do not constitute a multi-tenant production deployment.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from public_app.calling import _CONDITIONAL, _DECLINE, _HUMAN, _OPT_OUT, _positive
from samvaad.models import ActionError
from samvaad.service import timestamp, utcnow
from samvaad.signals import extract_signals

CALL_SID = re.compile(r"^CA[0-9a-fA-F]{32}$")
STAFF_ROLES = {"MANAGER", "CREDIT", "ADMIN"}
TERMINAL = {"completed", "failed", "busy", "no-answer", "canceled"}


def e164(value):
    if not isinstance(value, str) or not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
        raise ActionError("INVALID_PHONE", "Use an E.164 number, including country code; masked demo numbers cannot be called.")
    return value


@dataclass(frozen=True)
class TelephonySettings:
    enabled: bool = False
    account_sid: str = ""
    auth_token: str = field(default="", repr=False)
    api_key_sid: str = ""
    api_key_secret: str = field(default="", repr=False)
    verify_service_sid: str = ""
    from_number: str = ""
    public_url: str = ""
    permitted_prefixes: tuple = ()
    authorised_test_numbers: tuple = ()
    timezone: str = "Asia/Kolkata"
    start_hour: int = 9
    end_hour: int = 19
    max_calls_per_day: int = 10
    max_verifications_per_day: int = 20
    time_limit: int = 180

    @classmethod
    def from_env(cls):
        return cls(enabled=os.getenv("SAMVAAD_TELEPHONY_ENABLED", "false").lower() == "true",
                   account_sid=os.getenv("SAMVAAD_TWILIO_ACCOUNT_SID", ""),
                   auth_token=os.getenv("SAMVAAD_TWILIO_AUTH_TOKEN", ""),
                   api_key_sid=os.getenv("SAMVAAD_TWILIO_API_KEY_SID", ""),
                   api_key_secret=os.getenv("SAMVAAD_TWILIO_API_KEY_SECRET", ""),
                   verify_service_sid=os.getenv("SAMVAAD_TWILIO_VERIFY_SERVICE_SID", ""),
                   from_number=os.getenv("SAMVAAD_TWILIO_FROM_NUMBER", ""),
                   public_url=os.getenv("SAMVAAD_TELEPHONY_PUBLIC_URL", "").rstrip("/"),
                   permitted_prefixes=tuple(p.strip() for p in os.getenv("SAMVAAD_TELEPHONY_PERMITTED_PREFIXES", "").split(",") if p.strip()),
                   authorised_test_numbers=tuple(p.strip() for p in os.getenv("SAMVAAD_TELEPHONY_AUTHORIZED_TEST_NUMBERS", "").split(",") if p.strip()))

    def require(self):
        parsed = urllib.parse.urlsplit(self.public_url)
        valid = (self.enabled and re.fullmatch(r"AC[0-9a-fA-F]{32}", self.account_sid)
                 and len(self.auth_token) >= 20 and re.fullmatch(r"VA[0-9a-fA-F]{32}", self.verify_service_sid)
                 and parsed.scheme == "https" and parsed.hostname and parsed.hostname not in {"localhost", "127.0.0.1"}
                 and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                 and not parsed.path and self.permitted_prefixes and self.authorised_test_numbers
                 and all(re.fullmatch(r"\+[1-9][0-9]{7,14}", p) for p in self.authorised_test_numbers)
                 and all(re.fullmatch(r"\+[1-9][0-9]{0,3}", p) for p in self.permitted_prefixes)
                 and 0 <= self.start_hour < self.end_hour <= 24 and 1 <= self.max_calls_per_day <= 100
                 and 1 <= self.max_verifications_per_day <= 100 and 30 <= self.time_limit <= 600)
        if not valid or bool(self.api_key_sid) != bool(self.api_key_secret):
            raise ActionError("TELEPHONY_NOT_CONFIGURED", "Live calling is disabled until the provider, owned caller number, HTTPS API and destination policy are configured.")
        if self.api_key_sid and not re.fullmatch(r"SK[0-9a-fA-F]{32}", self.api_key_sid):
            raise ActionError("TELEPHONY_NOT_CONFIGURED", "Configure a valid provider API key privately.")
        e164(self.from_number)
        ZoneInfo(self.timezone)

    def number_allowed(self, number):
        e164(number)
        if number not in self.authorised_test_numbers or not any(number.startswith(prefix) for prefix in self.permitted_prefixes):
            raise ActionError("DESTINATION_BLOCKED", "This destination is outside the configured calling policy.")


class ProviderFailure(Exception):
    def __init__(self, uncertain=True):
        self.uncertain = uncertain
        super().__init__("Provider operation could not be confirmed." if uncertain else "Provider rejected the operation.")


class TwilioProvider:
    """HTTPS API adapter with bounded requests and no automatic write retries."""
    def __init__(self, settings):
        self.settings = settings

    def _request(self, host, path, data=None):
        self.settings.require()
        username = self.settings.api_key_sid or self.settings.account_sid
        secret = self.settings.api_key_secret or self.settings.auth_token
        authorization = base64.b64encode((username + ":" + secret).encode()).decode()
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        request = urllib.request.Request("https://" + host + path, data=body, headers={
            "Authorization": "Basic " + authorization, "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"}, method="POST" if body is not None else "GET")
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *_args, **_kwargs):
                    return None
            # Provider endpoints are fixed HTTPS origins; never forward an
            # Authorization header to a redirect destination.
            opener = urllib.request.build_opener(NoRedirect())
            with opener.open(request, timeout=12) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ProviderFailure()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ProviderFailure()
            return value
        except urllib.error.HTTPError as exc:
            # Never expose provider response bodies: they can contain PII.
            raise ProviderFailure(uncertain=exc.code >= 500) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, ValueError):
            raise ProviderFailure() from None

    def start_verification(self, number):
        return self._request("verify.twilio.com", f"/v2/Services/{self.settings.verify_service_sid}/Verifications",
                             {"To": number, "Channel": "sms"})

    def check_verification(self, verification_sid, code):
        return self._request("verify.twilio.com", f"/v2/Services/{self.settings.verify_service_sid}/VerificationCheck",
                             {"VerificationSid": verification_sid, "Code": code})

    def create_call(self, number, call_id):
        base = self.settings.public_url + "/telephony/twilio/" + call_id
        return self._request("api.twilio.com", f"/2010-04-01/Accounts/{self.settings.account_sid}/Calls.json", {
            "To": number, "From": self.settings.from_number, "Url": base + "/answer", "Method": "POST",
            "StatusCallback": base + "/status", "StatusCallbackMethod": "POST",
            "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
            "Timeout": 25, "TimeLimit": self.settings.time_limit, "Record": "false"})

    def get_call(self, sid):
        if not CALL_SID.fullmatch(sid):
            raise ActionError("INVALID_PROVIDER_CALL", "Invalid provider call identifier.")
        return self._request("api.twilio.com", f"/2010-04-01/Accounts/{self.settings.account_sid}/Calls/{sid}.json")

    def cancel_call(self, sid):
        if not CALL_SID.fullmatch(sid):
            raise ActionError("INVALID_PROVIDER_CALL", "Invalid provider call identifier.")
        return self._request("api.twilio.com", f"/2010-04-01/Accounts/{self.settings.account_sid}/Calls/{sid}.json", {"Status": "completed"})


def validate_signature(token, canonical_url, values, signature):
    if not signature or not isinstance(signature, str) or not signature.isascii():
        return False
    material = canonical_url + "".join(key + values[key] for key in sorted(values))
    expected = base64.b64encode(hmac.new(token.encode(), material.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


class TelephonyService:
    def __init__(self, service, settings=None, provider=None):
        self.service = service
        self.settings = settings or TelephonySettings.from_env()
        self.provider = provider or TwilioProvider(self.settings)
        with service._db(write=True) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS telephony_recipients (
              recipient_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers ON DELETE CASCADE,
              phone TEXT NOT NULL,source TEXT NOT NULL,consent_note TEXT NOT NULL,requested_by TEXT NOT NULL,
              status TEXT NOT NULL,verification_sid TEXT,created_at TEXT NOT NULL,verified_at TEXT,verified_until TEXT,
              attempts INTEGER NOT NULL DEFAULT 0)""")
            con.execute("""CREATE TABLE IF NOT EXISTS telephony_calls (
              call_id TEXT PRIMARY KEY,action_id TEXT NOT NULL REFERENCES actions ON DELETE CASCADE,
              recipient_id TEXT NOT NULL REFERENCES telephony_recipients,customer_id TEXT NOT NULL,
              idempotency_key TEXT NOT NULL UNIQUE,requested_by TEXT NOT NULL,status TEXT NOT NULL,
              provider_sid TEXT UNIQUE,conversation_state TEXT NOT NULL,permission_granted INTEGER NOT NULL DEFAULT 0,
              identity_confirmed INTEGER NOT NULL DEFAULT 0,step INTEGER NOT NULL DEFAULT 0,
              outcome TEXT,created_at TEXT NOT NULL,ended_at TEXT,provider_sequence INTEGER NOT NULL DEFAULT -1)""")
            con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS telephony_one_open_action ON telephony_calls(action_id)
              WHERE status NOT IN ('completed','failed','busy','no-answer','canceled')""")
            con.execute("""CREATE TABLE IF NOT EXISTS telephony_events (
              call_id TEXT NOT NULL REFERENCES telephony_calls ON DELETE CASCADE,event_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL,response TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(call_id,event_id))""")
            con.execute("""CREATE TABLE IF NOT EXISTS telephony_turns (
              call_id TEXT NOT NULL REFERENCES telephony_calls ON DELETE CASCADE,seq INTEGER NOT NULL,
              speaker TEXT NOT NULL,text TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(call_id,seq))""")

    def _staff(self, actor):
        self.service._authorize(actor, STAFF_ROLES)

    def status(self):
        try:
            self.settings.require()
            configured = True
        except (ActionError, ValueError, KeyError):
            configured = False
        return {"provider": "Twilio Programmable Voice + Verify", "live_calling_configured": configured,
                "pilot_ready": configured, "production_ready": False,
                "provider_connection_verified": False, "storage": "SQLite transactional controlled pilot",
                "enterprise_ready": False, "mock_transport": False,
                "production_gates": ["PostgreSQL workflow store", "enterprise identity and customer scope",
                                     "strong borrower identity", "carrier and commercial voice terms", "live provider rehearsal"]}

    @staticmethod
    def _recipient_public(record):
        value = dict(record)
        value["phone"] = "***" + value["phone"][-4:]
        value["phone_masked"] = value["phone"]
        value["verified"] = value["status"] == "VERIFIED" and bool(value["verified_until"]) and datetime.fromisoformat(value["verified_until"]) > utcnow()
        value["verification_status"] = value["status"]
        value.pop("verification_sid", None)
        value.pop("consent_note", None)
        return value

    def recipients(self, customer_id, actor):
        self._staff(actor)
        with self.service._db() as con:
            self.service._customer(con, customer_id)
            return [self._recipient_public(r) for r in con.execute(
                "SELECT * FROM telephony_recipients WHERE customer_id=? ORDER BY created_at DESC LIMIT 100", (customer_id,))]

    def request_verification(self, customer_id, phone, source, consent_note, verification_requested, actor):
        self._staff(actor)
        self.settings.require()
        self.settings.number_allowed(phone)
        if source not in {"primary", "alternate"} or not verification_requested or not isinstance(consent_note, str) or not 10 <= len(consent_note.strip()) <= 500:
            raise ActionError("RECIPIENT_CONSENT_REQUIRED", "Record the number owner's requested verification and calling purpose.")
        rid = uuid4().hex
        with self.service._db(write=True) as con:
            customer = self.service._customer(con, customer_id)
            if not customer["consent_calls"] or customer["dnd"]:
                raise ActionError("CONSENT_REQUIRED", "Current customer calling consent is required.")
            if source == "primary" and customer["phone"] != phone:
                raise ActionError("PRIMARY_PHONE_MISMATCH", "The primary number must match the customer's registered E.164 number. Use an explicitly authorised alternate number otherwise.")
            recent = timestamp(utcnow() - timedelta(days=1))
            if con.execute("SELECT COUNT(*) FROM telephony_recipients WHERE created_at>=?", (recent,)).fetchone()[0] >= self.settings.max_verifications_per_day:
                raise ActionError("VERIFICATION_LIMIT", "The daily verification budget has been reached.")
            if con.execute("SELECT COUNT(*) FROM telephony_recipients WHERE phone=? AND created_at>=?", (phone, recent)).fetchone()[0] >= 3:
                raise ActionError("VERIFICATION_LIMIT", "This number's daily verification limit has been reached.")
            con.execute("INSERT INTO telephony_recipients VALUES (?,?,?,?,?,?,'REQUESTING',NULL,?,NULL,NULL,0)",
                        (rid, customer_id, phone, source, consent_note.strip(), actor.user_id, timestamp()))
        try:
            result = self.provider.start_verification(phone)
            if not isinstance(result, dict):
                raise ProviderFailure()
            sid = result.get("sid", "")
            if not isinstance(sid, str) or not re.fullmatch(r"VE[0-9a-fA-F]{32}", sid) or result.get("status") != "pending" or result.get("to") != phone or result.get("service_sid") != self.settings.verify_service_sid:
                raise ProviderFailure()
        except ProviderFailure as exc:
            with self.service._db(write=True) as con:
                con.execute("UPDATE telephony_recipients SET status=? WHERE recipient_id=?",
                            ("UNCERTAIN" if exc.uncertain else "FAILED", rid))
            raise ActionError("VERIFICATION_UNCONFIRMED", "Verification delivery is unconfirmed. No number has been marked verified; inspect the provider before retrying.") from None
        with self.service._db(write=True) as con:
            con.execute("UPDATE telephony_recipients SET status='PENDING',verification_sid=? WHERE recipient_id=?", (sid, rid))
            self.service._log(con, "PHONE_VERIFICATION_REQUESTED", customer_id, actor=actor.user_id, detail={"recipient_id": rid, "source": source})
            return self._recipient_public(con.execute("SELECT * FROM telephony_recipients WHERE recipient_id=?", (rid,)).fetchone())

    def verify(self, recipient_id, code, actor):
        self._staff(actor)
        self.settings.require()
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{4,10}", code):
            raise ActionError("INVALID_VERIFICATION_CODE", "Enter the code received by the authorised number owner.")
        with self.service._db(write=True) as con:
            row = con.execute("SELECT * FROM telephony_recipients WHERE recipient_id=?", (recipient_id,)).fetchone()
            if not row:
                raise ActionError("RECIPIENT_NOT_FOUND", "The recipient is unavailable.")
            customer = self.service._customer(con, row["customer_id"])
            if not customer["consent_calls"] or customer["dnd"]:
                raise ActionError("CONSENT_REQUIRED", "Calling permission was withdrawn.")
            if row["status"] != "PENDING" or row["attempts"] >= 5 or utcnow() - datetime.fromisoformat(row["created_at"]) > timedelta(minutes=10):
                raise ActionError("VERIFICATION_EXPIRED", "Request a fresh verification after reviewing the previous delivery.")
            con.execute("UPDATE telephony_recipients SET attempts=attempts+1 WHERE recipient_id=?", (recipient_id,))
        try:
            result = self.provider.check_verification(row["verification_sid"], code)
            if not isinstance(result, dict):
                raise ProviderFailure()
        except ProviderFailure:
            raise ActionError("VERIFICATION_UNCONFIRMED", "The provider could not confirm verification. The number remains unverified.") from None
        if (result.get("status") != "approved" or result.get("sid") != row["verification_sid"]
                or result.get("to") != row["phone"] or result.get("service_sid") != self.settings.verify_service_sid):
            raise ActionError("VERIFICATION_FAILED", "The provider did not approve this number's verification.")
        with self.service._db(write=True) as con:
            customer = self.service._customer(con, row["customer_id"])
            if not customer["consent_calls"] or customer["dnd"]:
                raise ActionError("CONSENT_REQUIRED", "Calling permission was withdrawn during verification.")
            con.execute("UPDATE telephony_recipients SET status='VERIFIED',verified_at=?,verified_until=? WHERE recipient_id=? AND status='PENDING'",
                        (timestamp(), timestamp(utcnow() + timedelta(days=30)), recipient_id))
            self.service._log(con, "PHONE_VERIFIED", row["customer_id"], actor=actor.user_id, detail={"recipient_id": recipient_id})
            return self._recipient_public(con.execute("SELECT * FROM telephony_recipients WHERE recipient_id=?", (recipient_id,)).fetchone())

    def _call(self, con, call_id):
        row = con.execute("SELECT * FROM telephony_calls WHERE call_id=?", (call_id,)).fetchone()
        if not row:
            raise ActionError("CALL_NOT_FOUND", "The call does not exist.")
        return dict(row)

    def get(self, call_id, actor):
        self._staff(actor)
        with self.service._db() as con:
            return self._call_public(con, call_id)

    def _call_public(self, con, call_id):
        value = self._call(con, call_id)
        value["turns"] = [dict(r) for r in con.execute("SELECT seq,speaker,text,created_at FROM telephony_turns WHERE call_id=? ORDER BY seq", (call_id,))]
        value.update(real_provider=True, financial_execution=False)
        return value

    def calls(self, actor):
        self._staff(actor)
        with self.service._db() as con:
            return [dict(r) for r in con.execute("SELECT * FROM telephony_calls ORDER BY created_at DESC LIMIT 100")]

    def _check_call(self, con, action, recipient):
        self.service._validate_current(con, action)
        if (recipient["customer_id"] != action["customer_id"] or recipient["status"] != "VERIFIED"
                or datetime.fromisoformat(recipient["verified_until"]) <= utcnow()):
            raise ActionError("VERIFIED_RECIPIENT_REQUIRED", "A current verified recipient belonging to this customer is required.")
        self.settings.number_allowed(recipient["phone"])
        local_hour = utcnow().astimezone(ZoneInfo(self.settings.timezone)).hour
        if not self.settings.start_hour <= local_hour < self.settings.end_hour:
            raise ActionError("CALLING_WINDOW_CLOSED", "Live calls are outside the configured respectful contact window.")

    def start(self, action_id, recipient_id, idempotency_key, actor, acknowledged_live_call=False):
        self._staff(actor)
        self.settings.require()
        if acknowledged_live_call is not True:
            raise ActionError("LIVE_CALL_ACKNOWLEDGEMENT_REQUIRED", "Explicitly acknowledge the real carrier call to the authorised pilot recipient.")
        if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{16,100}", idempotency_key):
            raise ActionError("INVALID_IDEMPOTENCY_KEY", "Provide a stable request key of 16–100 characters.")
        cid = uuid4().hex
        with self.service._db(write=True) as con:
            prior = con.execute("SELECT * FROM telephony_calls WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if prior:
                if prior["action_id"] != action_id or prior["recipient_id"] != recipient_id:
                    raise ActionError("IDEMPOTENCY_CONFLICT", "That request key belongs to a different call.")
                return self._call_public(con, prior["call_id"])
            action = self.service._action(con, action_id)
            recipient = con.execute("SELECT * FROM telephony_recipients WHERE recipient_id=?", (recipient_id,)).fetchone()
            if not recipient:
                raise ActionError("VERIFIED_RECIPIENT_REQUIRED", "Verify an authorised customer number before calling.")
            if action["status"] != "APPROVED":
                raise ActionError("APPROVAL_REQUIRED", "The current action must be approved before a live pilot call.")
            self._check_call(con, action, recipient)
            if action["attempts"] >= 3:
                raise ActionError("ATTEMPTS_EXHAUSTED", "The action's three-attempt limit has been reached.")
            if action["last_attempt_at"] and utcnow() - datetime.fromisoformat(action["last_attempt_at"]) < timedelta(hours=4):
                raise ActionError("RETRY_TOO_SOON", "Wait four hours before another call attempt.")
            if con.execute("SELECT COUNT(*) FROM telephony_calls WHERE created_at>=?", (timestamp(utcnow() - timedelta(days=1)),)).fetchone()[0] >= self.settings.max_calls_per_day:
                raise ActionError("CALL_BUDGET_REACHED", "The daily live-call budget has been reached.")
            con.execute("INSERT INTO telephony_calls(call_id,action_id,recipient_id,customer_id,idempotency_key,requested_by,status,conversation_state,created_at) VALUES (?,?,?,?,?,?,'DISPATCHING','AWAIT_PERMISSION',?)",
                        (cid, action_id, recipient_id, action["customer_id"], idempotency_key, actor.user_id, timestamp()))
            con.execute("UPDATE actions SET status='EXECUTING',attempts=attempts+1,last_attempt_at=?,execution_mode='twilio-live-pilot' WHERE action_id=?", (timestamp(), action_id))
            self.service._log(con, "REAL_CALL_DISPATCH_RESERVED", action["customer_id"], action_id, actor.user_id, {"call_id": cid, "recipient_id": recipient_id})
        # Reservation commits before network I/O. A crash here leaves an
        # uncertain dispatch that must be reconciled, never blindly redialed.
        try:
            with self.service._db(write=True) as con:
                action = self.service._action(con, action_id)
                recipient = con.execute("SELECT * FROM telephony_recipients WHERE recipient_id=?", (recipient_id,)).fetchone()
                if action["status"] != "EXECUTING" or not recipient:
                    raise ActionError("CALL_POLICY_CHANGED", "The reserved action or recipient changed before dispatch.")
                self._check_call(con, action, recipient)
                result = self.provider.create_call(recipient["phone"], cid)
                if not isinstance(result, dict):
                    raise ProviderFailure()
                sid = result.get("sid", "")
                status = result.get("status")
                if (not isinstance(sid, str) or not CALL_SID.fullmatch(sid) or result.get("account_sid") != self.settings.account_sid
                        or not isinstance(status, str) or status not in {"queued", "ringing", "in-progress", *TERMINAL}):
                    raise ProviderFailure()
                con.execute("UPDATE telephony_calls SET status=?,provider_sid=? WHERE call_id=?", (status, sid, cid))
                if status in TERMINAL:
                    self._finish(con, self._call(con, cid), self._terminal_outcome(status), "The carrier call ended.")
                self.service._log(con, "REAL_CALL_PROVIDER_ACCEPTED", action["customer_id"], action_id, actor.user_id, {"call_id": cid, "provider_sid": sid})
        except ProviderFailure as exc:
            with self.service._db(write=True) as con:
                # A signed callback can win the lock after the provider request
                # fails. Its accepted SID/status is stronger evidence than a
                # timeout and must never be overwritten by uncertainty.
                changed = con.execute("UPDATE telephony_calls SET status=? WHERE call_id=? AND provider_sid IS NULL AND status='DISPATCHING'",
                                      ("DISPATCH_UNCERTAIN" if exc.uncertain else "failed", cid)).rowcount
                if changed and not exc.uncertain:
                    con.execute("UPDATE actions SET status=CASE WHEN attempts>=3 THEN 'EXHAUSTED' ELSE 'APPROVED' END WHERE action_id=? AND status='EXECUTING'", (action_id,))
            raise ActionError("CALL_DISPATCH_UNCERTAIN" if exc.uncertain else "CALL_PROVIDER_REJECTED",
                              "The provider result is unconfirmed; inspect and reconcile this request before retrying." if exc.uncertain else "The provider rejected the call. No accepted call identifier was returned.") from None
        except ActionError:
            with self.service._db(write=True) as con:
                con.execute("UPDATE telephony_calls SET status='canceled',outcome='POLICY_CHANGED' WHERE call_id=?", (cid,))
                con.execute("UPDATE actions SET status=CASE WHEN attempts>=3 THEN 'EXHAUSTED' ELSE 'APPROVED' END WHERE action_id=? AND status='EXECUTING'", (action_id,))
            raise
        return self.get(cid, actor)

    def reconcile(self, call_id, actor):
        self._staff(actor)
        self.settings.require()
        value = self.get(call_id, actor)
        if not value["provider_sid"]:
            raise ActionError("RECONCILIATION_REQUIRED", "No provider SID is known. Inspect Twilio call logs and this callback URL; automatic redial is blocked.")
        try:
            result = self.provider.get_call(value["provider_sid"])
            if (not isinstance(result, dict) or not isinstance(result.get("status"), str)
                    or result["status"] not in {"queued", "initiated", "ringing", "in-progress", *TERMINAL}):
                raise ProviderFailure()
        except ProviderFailure:
            raise ActionError("PROVIDER_STATUS_UNCONFIRMED", "The provider could not confirm call status.") from None
        if result.get("sid") != value["provider_sid"] or result.get("account_sid") != self.settings.account_sid:
            raise ActionError("PROVIDER_STATUS_UNCONFIRMED", "The provider identity did not match this call.")
        self.provider_status(call_id, {"CallSid": value["provider_sid"], "CallStatus": result["status"]})
        return self.get(call_id, actor)

    def cancel(self, call_id, actor):
        self._staff(actor)
        self.settings.require()
        value = self.get(call_id, actor)
        if value["status"] in TERMINAL:
            return value
        if not value["provider_sid"]:
            raise ActionError("RECONCILIATION_REQUIRED", "An uncertain dispatch must be reconciled before cancellation can be confirmed.")
        try:
            result = self.provider.cancel_call(value["provider_sid"])
            if not isinstance(result, dict):
                raise ProviderFailure()
        except ProviderFailure:
            raise ActionError("CANCEL_UNCONFIRMED", "Call cancellation was not confirmed; inspect the provider.") from None
        if (result.get("sid") != value["provider_sid"] or result.get("account_sid") != self.settings.account_sid
                or not isinstance(result.get("status"), str) or result["status"] not in TERMINAL):
            raise ActionError("CANCEL_UNCONFIRMED", "The provider did not confirm a terminal call state.")
        self.provider_status(call_id, {"CallSid": value["provider_sid"], "CallStatus": result["status"]})
        return self.get(call_id, actor)

    def callback_identity(self, call_id, values):
        if values.get("AccountSid") != self.settings.account_sid or not CALL_SID.fullmatch(values.get("CallSid", "")):
            raise ActionError("INVALID_PROVIDER_CALLBACK", "Provider callback identity does not match.")
        with self.service._db(write=True) as con:
            call = self._call(con, call_id)
            if call["provider_sid"] and call["provider_sid"] != values["CallSid"]:
                raise ActionError("INVALID_PROVIDER_CALLBACK", "Provider call does not match this request.")
            if not call["provider_sid"]:
                phone = con.execute("SELECT phone FROM telephony_recipients WHERE recipient_id=?", (call["recipient_id"],)).fetchone()[0]
                if values.get("To") != phone or values.get("From") != self.settings.from_number:
                    raise ActionError("INVALID_PROVIDER_CALLBACK", "Provider destination does not match the reserved call.")
                con.execute("UPDATE telephony_calls SET provider_sid=? WHERE call_id=?", (values["CallSid"], call_id))

    @staticmethod
    def _say(con, call_id, speaker, text):
        seq = con.execute("SELECT COALESCE(MAX(seq),0)+1 FROM telephony_turns WHERE call_id=?", (call_id,)).fetchone()[0]
        con.execute("INSERT INTO telephony_turns VALUES (?,?,?,?,?)", (call_id, seq, speaker, text, timestamp()))

    def _xml(self, call, text, ended=False):
        root = ET.Element("Response")
        if ended:
            ET.SubElement(root, "Say", {"language": "en-US", "voice": "woman"}).text = text
            ET.SubElement(root, "Hangup")
        else:
            action = self.settings.public_url + f"/telephony/twilio/{call['call_id']}/turn?step={call['step']}"
            gather = ET.SubElement(root, "Gather", {"input": "speech dtmf", "numDigits": "1", "timeout": "5",
                "speechTimeout": "auto", "language": "en-IN", "action": action, "method": "POST", "actionOnEmptyResult": "true"})
            ET.SubElement(gather, "Say", {"language": "en-US", "voice": "woman"}).text = text
        return ET.tostring(root, encoding="unicode")

    def _finish(self, con, call, outcome, text):
        self._say(con, call["call_id"], "lender", text)
        con.execute("UPDATE telephony_calls SET conversation_state='ENDED',outcome=?,ended_at=? WHERE call_id=?", (outcome, timestamp(), call["call_id"]))
        if outcome == "OPT_OUT":
            self.service._revoke(con, call["customer_id"], self.service.resolve_actor("local-runner"))
            con.execute("UPDATE telephony_recipients SET status='REVOKED' WHERE customer_id=?", (call["customer_id"],))
        elif outcome in {"NO_ANSWER", "DISCONNECTED", "FAILED"}:
            con.execute("UPDATE actions SET status=CASE WHEN attempts>=3 THEN 'EXHAUSTED' ELSE 'APPROVED' END,outcome=? WHERE action_id=? AND status='EXECUTING'", (outcome, call["action_id"]))
        elif outcome in {"POLICY_CHANGED", "CONTACT_SUPPRESSED"}:
            con.execute("UPDATE actions SET status='CANCELLED',outcome=?,completed_at=? WHERE action_id=? AND status='EXECUTING'", (outcome, timestamp(), call["action_id"]))
        else:
            con.execute("UPDATE actions SET status='COMPLETED',outcome=?,completed_at=? WHERE action_id=? AND status='EXECUTING'", (outcome, timestamp(), call["action_id"]))
        if call["permission_granted"] and call["identity_confirmed"]:
            transcript = "\n".join(("Customer: " if r["speaker"] == "borrower" else "Agent: ") + r["text"]
                                    for r in con.execute("SELECT * FROM telephony_turns WHERE call_id=? ORDER BY seq", (call["call_id"],)))
            self.service._insert_interaction(con, "TEL-" + call["call_id"], call["customer_id"], "CALL_IN", transcript, simulated=False)
        self.service._log(con, "REAL_CALL_CONVERSATION_ENDED", call["customer_id"], call["action_id"], "telephony-webhook", {"call_id": call["call_id"], "outcome": outcome, "financial_execution": False})
        return self._xml(call, text, ended=True)

    def _proposal(self, action):
        # OTP proves phone possession, and spoken yes is only a pilot gate.
        # Strong borrower/account identity is not implemented, so phone calls
        # never disclose account balances, financial amounts, or rates.
        if action["approval_role"] in {"MANAGER", "CREDIT"}:
            return "An officer can discuss the reviewed proposal with you after secure account verification. This pilot will not disclose financial amounts, balances or rates, and does not issue a loan or change a rate. Say interested or press 1 to request that review, decline or press 2, or officer or press 3."
        return "An officer can review repayment support or a reported payment with you. No relief terms are promised. Say officer or press 3 for a handoff request, or decline or press 2."

    def conversation(self, call_id, values, step=None):
        event_id = "answer" if step is None else "turn:" + str(step)
        fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        with self.service._db(write=True) as con:
            call = self._call(con, call_id)
            prior = con.execute("SELECT * FROM telephony_events WHERE call_id=? AND event_id=?", (call_id, event_id)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise ActionError("CALLBACK_EVENT_CONFLICT", "That callback step was already used.")
                # Replaying a cached Gather must not restart contact after a
                # hangup or a subsequent withdrawal of calling permission.
                if "<Hangup" not in prior["response"]:
                    customer = self.service._customer(con, call["customer_id"])
                    if call["conversation_state"] == "ENDED" or call["status"] in TERMINAL:
                        return self._xml(call, "This conversation has ended. Goodbye.", ended=True)
                    if not customer["consent_calls"] or customer["dnd"]:
                        return self._finish(con, call, "CONTACT_SUPPRESSED", "Contact permission changed. We will stop now. Goodbye.")
                return prior["response"]
            action = self.service._action(con, call["action_id"])
            customer = self.service._customer(con, call["customer_id"])
            if call["conversation_state"] == "ENDED" or call["status"] in TERMINAL:
                xml = self._xml(call, "This conversation has ended. Goodbye.", ended=True)
            elif step is not None and step != call["step"]:
                raise ActionError("INVALID_CALLBACK_STEP", "This conversation step is unavailable.")
            elif step is None:
                try:
                    self.service._validate_current(con, action)
                    text = "Hello. I am Samvaad, an automated assistant. This is a live technology pilot with demonstration financial terms. May we continue and save a transcript? Say yes or press 1, no or press 2. To stop future contact, say stop calling or press 9."
                    self._say(con, call_id, "lender", text)
                    xml = self._xml(call, text)
                except ActionError:
                    xml = self._finish(con, call, "POLICY_CHANGED", "The contact policy changed, so this call will stop. Goodbye.")
            else:
                text = values.get("SpeechResult", "").strip()
                digits = values.get("Digits", "")
                if len(text) > 1000 or digits not in {"", "1", "2", "3", "9"}:
                    raise ActionError("INVALID_CALL_INPUT", "The provider supplied unsupported input.")
                low = text.lower().replace("\u2019", "'")
                if call["permission_granted"] and text:
                    self._say(con, call_id, "borrower", text)
                if digits == "9" or _OPT_OUT.search(low):
                    xml = self._finish(con, call, "OPT_OUT", "Your contact opt-out has been recorded. Further contact is blocked. Goodbye.")
                elif not customer["consent_calls"] or customer["dnd"]:
                    xml = self._finish(con, call, "CONTACT_SUPPRESSED", "Contact permission changed. We will stop now. Goodbye.")
                elif extract_signals("Customer: " + text)["intent"] == "financial hardship":
                    xml = self._finish(con, call, "HARDSHIP_HANDOFF", "You mentioned financial hardship. I will record a supportive officer review request and stop this proposal. No relief or new credit is promised.")
                elif digits == "3" or _HUMAN.search(low):
                    xml = self._finish(con, call, "HUMAN_HANDOFF", "An officer review request is recorded. This pilot does not bridge to a staffed queue. Goodbye.")
                else:
                    try:
                        self.service._validate_current(con, action)
                        if call["step"] >= 11:
                            xml = self._finish(con, call, "HUMAN_HANDOFF", "The conversation limit has been reached. An officer review request is recorded. Goodbye.")
                        elif call["conversation_state"] == "AWAIT_PERMISSION":
                            if digits == "2" or _DECLINE.search(low) or re.search(r"\b(?:not|don't|cannot)\b", low):
                                xml = self._finish(con, call, "PERMISSION_DECLINED", "We will stop without discussing account terms. Goodbye.")
                            elif digits == "1" or _positive(low, "AWAIT_PERMISSION"):
                                call.update(permission_granted=1, conversation_state="AWAIT_IDENTITY")
                                if text:
                                    self._say(con, call_id, "borrower", text)
                                xml = self._next(con, call, "Please confirm you are the registered account holder: say yes or press 1, or no or press 2. This verbal pilot confirmation is not strong identity verification.")
                            else:
                                xml = self._next(con, call, "Please say yes or press 1 to continue with a transcript, or no or press 2 to stop.")
                        elif call["conversation_state"] == "AWAIT_IDENTITY":
                            if digits == "2" or _DECLINE.search(low) or re.search(r"\bnot\b|wrong (?:person|number)", low):
                                xml = self._finish(con, call, "IDENTITY_NOT_CONFIRMED", "I will stop without discussing account details. Goodbye.")
                            elif digits == "1" or _positive(low, "AWAIT_IDENTITY"):
                                call.update(identity_confirmed=1, conversation_state="ACTIVE")
                                xml = self._next(con, call, self._proposal(action))
                            else:
                                xml = self._next(con, call, "Confirm you are the registered account holder or press 2 to stop. Account details remain undisclosed.")
                        elif digits == "2" or _DECLINE.search(low):
                            xml = self._finish(con, call, "DECLINED", "Your decline has been recorded. No loan terms were changed. Goodbye.")
                        elif _CONDITIONAL.search(low) or re.search(r"\d", low):
                            xml = self._next(con, call, "I cannot negotiate different terms or treat conditional interest as acceptance. Say interested in the reviewed proposal or ask an officer.")
                        elif digits == "1" or _positive(low, "ACTIVE"):
                            xml = self._finish(con, call, "INTEREST_RECORDED" if action["approval_role"] in {"MANAGER", "CREDIT"} else "HUMAN_HANDOFF",
                                               "Your preference is recorded for officer review. No real loan, rate change or financial link was created. Goodbye.")
                        else:
                            xml = self._next(con, call, "Say interested or press 1, decline or press 2, officer or press 3, or stop calling or press 9.")
                    except ActionError:
                        xml = self._finish(con, call, "POLICY_CHANGED", "The reviewed proposal or permission changed. An officer must review it before further discussion. Goodbye.")
            con.execute("INSERT INTO telephony_events VALUES (?,?,?,?,?)", (call_id, event_id, fingerprint, xml, timestamp()))
            return xml

    def _next(self, con, call, text):
        call["step"] += 1
        con.execute("UPDATE telephony_calls SET conversation_state=?,permission_granted=?,identity_confirmed=?,step=? WHERE call_id=?", (call["conversation_state"], call["permission_granted"], call["identity_confirmed"], call["step"], call["call_id"]))
        self._say(con, call["call_id"], "lender", text)
        return self._xml(call, text)

    @staticmethod
    def _terminal_outcome(status):
        return "NO_ANSWER" if status in {"busy", "no-answer"} else "FAILED" if status == "failed" else "DISCONNECTED"

    def provider_status(self, call_id, values):
        status = values.get("CallStatus")
        if status not in {"queued", "initiated", "ringing", "in-progress", *TERMINAL}:
            raise ActionError("INVALID_CALL_STATUS", "Unsupported provider call status.")
        with self.service._db(write=True) as con:
            call = self._call(con, call_id)
            if values.get("CallSid") != call["provider_sid"]:
                raise ActionError("INVALID_PROVIDER_CALLBACK", "Provider call does not match this request.")
            sequence = values.get("SequenceNumber")
            if sequence is not None:
                if not re.fullmatch(r"\d{1,9}", str(sequence)):
                    raise ActionError("INVALID_PROVIDER_CALLBACK", "Invalid callback sequence.")
                sequence = int(sequence)
                if sequence <= call["provider_sequence"]:
                    return
            if call["status"] in TERMINAL:
                if call["conversation_state"] != "ENDED":
                    self._finish(con, call, self._terminal_outcome(call["status"]), "The carrier call ended.")
                return
            con.execute("UPDATE telephony_calls SET status=?,provider_sequence=? WHERE call_id=?", (status, sequence if sequence is not None else call["provider_sequence"], call_id))
            if status in TERMINAL and call["conversation_state"] != "ENDED":
                self._finish(con, call, self._terminal_outcome(status), "The carrier call ended.")
            self.service._log(con, "REAL_CALL_PROVIDER_STATUS", call["customer_id"], call["action_id"], "telephony-webhook", {"call_id": call_id, "status": status})
