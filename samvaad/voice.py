"""Persistent, bounded local voice conversations for already-approved actions.

This is an actual conversation workflow, not a telephone dialer or generative
underwriter. The production media/identity boundary is documented separately.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta
from uuid import uuid4

from samvaad.models import Actor, ActionError
from samvaad.service import timestamp, utcnow
from samvaad.signals import extract_signals


class VoiceService:
    def __init__(self, service):
        if not service.is_demo:
            raise ActionError("VOICE_DEPLOYMENT_PENDING", "A production voice worker must be configured separately.")
        self.service = service
        with service._db(write=True) as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
              session_id TEXT PRIMARY KEY, action_id TEXT NOT NULL REFERENCES actions ON DELETE CASCADE,
              customer_id TEXT NOT NULL REFERENCES customers ON DELETE CASCADE,
              state TEXT NOT NULL, identity_confirmed INTEGER NOT NULL DEFAULT 0,
              permission_granted INTEGER NOT NULL DEFAULT 0, outcome TEXT,
              started_at TEXT NOT NULL, ended_at TEXT, mode TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS voice_one_active_action
              ON voice_sessions(action_id) WHERE ended_at IS NULL;
            CREATE TABLE IF NOT EXISTS voice_turns (
              session_id TEXT NOT NULL REFERENCES voice_sessions ON DELETE CASCADE,
              seq INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, ts TEXT NOT NULL,
              PRIMARY KEY(session_id,seq));
            CREATE TABLE IF NOT EXISTS voice_events (
              session_id TEXT NOT NULL REFERENCES voice_sessions ON DELETE CASCADE,
              event_id TEXT NOT NULL, text TEXT NOT NULL, payload_hash TEXT,
              PRIMARY KEY(session_id,event_id));
            """)
            # executescript commits the initial transaction; reacquire the
            # writer lock so concurrent startup cannot race this schema change.
            con.execute("BEGIN IMMEDIATE")
            # Older local databases kept raw event payloads. New events use only
            # their fingerprint; exact legacy replays migrate that one payload.
            if "payload_hash" not in {row["name"] for row in con.execute("PRAGMA table_info(voice_events)")}:
                con.execute("ALTER TABLE voice_events ADD COLUMN payload_hash TEXT")

    def _get(self, con, sid):
        row = con.execute("SELECT * FROM voice_sessions WHERE session_id=?", (sid,)).fetchone()
        if not row:
            raise ActionError("VOICE_NOT_FOUND", "The voice session does not exist.")
        value = dict(row)
        value["identity_confirmed"] = bool(value["identity_confirmed"])
        value["permission_granted"] = bool(value["permission_granted"])
        value["turns"] = [dict(r) for r in con.execute("SELECT seq,role,text,ts FROM voice_turns WHERE session_id=? ORDER BY seq", (sid,))]
        return value

    def get(self, session_id):
        with self.service._db() as con:
            return self._get(con, session_id)

    def sessions(self, customer_id=None):
        with self.service._db() as con:
            rows = con.execute("SELECT session_id FROM voice_sessions " + ("WHERE customer_id=? " if customer_id else "") + "ORDER BY started_at DESC", (customer_id,) if customer_id else ())
            return [self._get(con, row[0]) for row in rows.fetchall()]

    def available_actions(self, customer_id):
        with self.service._db() as con:
            actions = [self.service._action(con, r[0]) for r in con.execute("SELECT action_id FROM actions WHERE customer_id=? AND status='APPROVED' ORDER BY created_at DESC", (customer_id,)).fetchall()]
            available = []
            for action in actions:
                try:
                    self.service._validate_current(con, action)
                    if action["attempts"] < 3 and (not action["last_attempt_at"] or utcnow() - datetime.fromisoformat(action["last_attempt_at"]) >= timedelta(hours=4)):
                        available.append(action)
                except ActionError:
                    continue
            return available

    def _say(self, con, sid, role, text):
        seq = con.execute("SELECT COALESCE(MAX(seq),0)+1 FROM voice_turns WHERE session_id=?", (sid,)).fetchone()[0]
        con.execute("INSERT INTO voice_turns VALUES (?,?,?,?,?)", (sid, seq, role, text, timestamp()))

    def start(self, action_id, actor):
        self.service._authorize(actor, {"AUTOMATION"})
        with self.service._db(write=True) as con:
            existing = con.execute("SELECT session_id FROM voice_sessions WHERE action_id=? AND ended_at IS NULL", (action_id,)).fetchone()
            if existing:
                action = self.service._action(con, action_id)
                self.service._validate_current(con, action)
                return self._get(con, existing[0])
            action = self.service._action(con, action_id)
            if action["status"] != "APPROVED":
                raise ActionError("APPROVAL_REQUIRED", "Approve this action before starting a voice session.")
            self.service._validate_current(con, action)
            if action["attempts"] >= 3:
                raise ActionError("ATTEMPTS_EXHAUSTED", "The three-attempt limit has been reached.")
            if action["last_attempt_at"] and utcnow() - datetime.fromisoformat(action["last_attempt_at"]) < timedelta(hours=4):
                raise ActionError("RETRY_TOO_SOON", "Wait four hours before another contact attempt.")
            sid = str(uuid4())
            con.execute("UPDATE actions SET status='EXECUTING',attempts=attempts+1,last_attempt_at=?,execution_mode='voice-lab' WHERE action_id=? AND status='APPROVED'", (timestamp(), action_id))
            con.execute("INSERT INTO voice_sessions VALUES (?,?,?,?,?,?,?,?,?,?)", (sid, action_id, action["customer_id"], "AWAIT_PERMISSION", 0, 0, None, timestamp(), None, "LOCAL_VOICE_LAB"))
            self._say(con, sid, "lender", "Hello. I am Samvaad, an automated assistant for the fictional DemoLend lender. This is a local test, not a real phone call. With your permission we will save a transcript. Is now a good time, and may we continue?")
            self.service._log(con, "VOICE_SESSION_STARTED", action["customer_id"], action_id, actor.user_id, {"session_id": sid, "mode": "LOCAL_VOICE_LAB", "real_call_placed": False})
            return self._get(con, sid)

    def _finish(self, con, session, outcome, actor, closing, preserve_action=False):
        sid = session["session_id"]
        action = self.service._action(con, session["action_id"])
        # An external opt-out may have cancelled the action while this session
        # was open. It still closes the session, without undoing the opt-out.
        if preserve_action:
            outcome = action.get("outcome") or outcome
        elif action["status"] == "CANCELLED":
            outcome = "OPT_OUT" if action["outcome"] == "OPT_OUT" else "CALLBACK"
        else:
            if outcome == "ACCEPT" and action["approval_role"] in {"MANAGER", "CREDIT"}:
                self.service._validate_current(con, action)
                self.service._create_offer(con, action)
            self.service._record_response(con, action["action_id"], outcome, "voice:" + sid, actor)
        self._say(con, sid, "lender", closing)
        con.execute("UPDATE voice_sessions SET state='ENDED',outcome=?,ended_at=? WHERE session_id=?", (outcome, timestamp(), sid))
        session = self._get(con, sid)
        # Only borrower-labelled utterances are interpreted as customer signals.
        # Lender speech is retained for audit but excluded by signal extraction.
        if session["permission_granted"] and session["identity_confirmed"]:
            transcript = "\n".join(("Customer: " if t["role"] == "borrower" else "Agent: ") + t["text"] for t in session["turns"])
            self.service._insert_interaction(con, "VOICE-" + sid, action["customer_id"], "CALL_IN", transcript, simulated=True)
        self.service._log(con, "VOICE_SESSION_ENDED", action["customer_id"], action["action_id"], actor.user_id, {"session_id": sid, "outcome": outcome, "synthetic": True, "transcript_saved": bool(session["permission_granted"] and session["identity_confirmed"])})
        return session

    def _proposal(self, action):
        code, offer = action["action_code"], action["offer"]
        if code == "RETENTION_RATE_MATCH_CALL":
            return f"Your manager-approved synthetic proposal is a rate reduction of {offer.get('rate_cut_bps', 0)} basis points. This does not change your loan and may not match another lender's offer. Would you like to record interest, decline, or ask an officer to call back?"
        if code == "TOPUP_PREAPPROVAL_CALL":
            return f"Your credit-approved synthetic invitation is for up to {offer.get('amount', 0):,.0f} rupees, subject to document and eligibility checks. It is not a disbursement or a guaranteed loan. Would you like to record interest, decline, or speak with an officer?"
        if code == "HARDSHIP_RESTRUCTURE_CALL":
            return "I understand you may need repayment support. I can request an officer callback to discuss available options. No EMI break or restructuring is promised. Would you like that callback?"
        return "I can record a request for a respectful repayment reminder or an officer callback. Would you like a callback, or have you already paid?"

    def _hardship_mentioned(self, con, sid):
        utterances = [r[0] for r in con.execute("SELECT text FROM voice_turns WHERE session_id=? AND role='borrower'", (sid,))]
        return any(extract_signals("Customer: " + text)["intent"] == "financial hardship" for text in utterances)

    def turn(self, session_id, text, event_id, actor):
        self.service._authorize(actor, {"AUTOMATION"})
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ActionError("INVALID_VOICE_TURN", "Provide a borrower utterance of 1-4,000 characters.")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 100:
            raise ActionError("INVALID_EVENT", "Provide a bounded turn event ID.")
        text = text.strip()
        payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        low = text.lower().replace("’", "'")
        with self.service._db(write=True) as con:
            session = self._get(con, session_id)
            prior = con.execute("SELECT text,payload_hash FROM voice_events WHERE session_id=? AND event_id=?", (session_id, event_id)).fetchone()
            if prior:
                previous_hash = prior[1] or hashlib.sha256(prior[0].encode("utf-8")).hexdigest()
                if previous_hash != payload_hash:
                    raise ActionError("EVENT_CONFLICT", "This voice event was already used for another utterance.")
                if prior[0] or not prior[1]:
                    con.execute("UPDATE voice_events SET text='',payload_hash=? WHERE session_id=? AND event_id=?", (payload_hash, session_id, event_id))
                return session
            if session["state"] == "ENDED":
                raise ActionError("VOICE_ENDED", "This session has ended.")
            action = self.service._action(con, session["action_id"])
            customer = self.service._customer(con, session["customer_id"])
            con.execute("INSERT INTO voice_events (session_id,event_id,text,payload_hash) VALUES (?,?,'',?)", (session_id, event_id, payload_hash))
            if re.search(r"stop (?:calling|contact)|do not (?:call|contact)|don't (?:call|contact)|unsubscribe|opt[ -]?out|remove my number|no more calls", low):
                if session["permission_granted"]:
                    self._say(con, session_id, "borrower", text)
                return self._finish(con, session, "OPT_OUT", actor, "I have recorded your opt-out. Further demo contact is blocked. Goodbye.")
            if action["status"] != "EXECUTING" or not customer["consent_calls"] or customer["dnd"]:
                outcome = "OPT_OUT" if not customer["consent_calls"] else action.get("outcome") or "CALLBACK"
                return self._finish(con, session, outcome, actor, "This conversation has stopped because the action or contact permission changed. No new preference has been inferred.", preserve_action=action["status"] != "EXECUTING")
            if session["permission_granted"]:
                self._say(con, session_id, "borrower", text)
            if session["state"] == "AWAIT_PERMISSION":
                if re.search(r"\bno\b|\bnot\b|don't|disagree|decline|refuse|busy|later", low):
                    return self._finish(con, session, "CALLBACK", actor, "We will stop here. No financial offer has been discussed. Goodbye.")
                if re.search(r"\byes\b|go ahead|agree|continue|okay|\bok\b", low):
                    con.execute("UPDATE voice_sessions SET state='AWAIT_IDENTITY',permission_granted=1 WHERE session_id=?", (session_id,))
                    self._say(con, session_id, "borrower", text)
                    self._say(con, session_id, "lender", "Thank you. For this synthetic test, please confirm you are the account holder. This verbal confirmation is a demo gate, not production identity verification.")
                elif extract_signals("Customer: " + text)["intent"] == "financial hardship":
                    return self._finish(con, session, "CALLBACK", actor, "You mentioned repayment hardship. I will stop and record an officer review request without saving your unconsented speech or discussing a financial invitation.")
                else:
                    self._say(con, session_id, "lender", "Please say yes to continue and save a transcript, or no to stop.")
            elif session["state"] == "AWAIT_IDENTITY":
                if re.search(r"\bno\b|\bnot\b|don't|wrong (?:number|person)", low):
                    return self._finish(con, session, "CALLBACK", actor, "Thank you. I will stop without discussing account details.")
                if re.search(r"\byes\b|i am (?:the )?account holder|this is (?:me|the account holder)|speaking", low):
                    self.service._validate_current(con, action)
                    con.execute("UPDATE voice_sessions SET state='ACTIVE',identity_confirmed=1 WHERE session_id=?", (session_id,))
                    if action["approval_role"] in {"MANAGER", "CREDIT"} and self._hardship_mentioned(con, session_id):
                        return self._finish(con, self._get(con, session_id), "CALLBACK", actor, "You mentioned repayment hardship. I will record a request for an officer to discuss support, rather than a financial invitation. No changed loan terms are promised.")
                    self._say(con, session_id, "lender", self._proposal(action))
                else:
                    self._say(con, session_id, "lender", "Please confirm you are the account holder, or say no to stop. I cannot discuss terms before that confirmation.")
            else:
                self.service._validate_current(con, action)
                if self._hardship_mentioned(con, session_id):
                    return self._finish(con, session, "CALLBACK", actor, "You mentioned repayment hardship. An officer review request is recorded. I will not create a financial invitation from this conversation.")
                if re.search(r"human|real person|\bagent\b|\bofficer\b|\bmanager\b|call(?: me)? back|callback|call later", low):
                    return self._finish(con, session, "CALLBACK", actor, "An officer callback request is recorded in this local test. No real call is scheduled or placed.")
                if re.search(r"already paid|payment (?:is )?done|i have paid", low):
                    return self._finish(con, session, "ALREADY_PAID", actor, "Your reported payment is recorded for review. I have not changed the verified payment records.")
                if re.search(r"\bno\b|decline|\buninterested\b|not interested|don't want|do not want|(?:not|don'?t|do not|cannot|can't|won't|will not|never)\s+(?:\w+\s+){0,2}(?:accept|agree|proceed|interested|go ahead)", low):
                    return self._finish(con, session, "DECLINE", actor, "Your decline is recorded. No loan terms have changed.")
                if re.search(r"bypass|ignore.*(?:rules|approval)|override|\bif\b|\bonly\b|\binstead\b|\bbut\b|increase|reduce|change.*(?:amount|rate|terms)|different (?:amount|rate|terms)", low):
                    self._say(con, session_id, "lender", "I cannot negotiate or authorize different terms. I can record interest only in the stored approved proposal, or request an officer callback.")
                    return self._get(con, session_id)
                if re.search(r"\byes\b|interested|accept|go ahead|please proceed", low):
                    outcome = "ACCEPT" if action["approval_role"] in {"MANAGER", "CREDIT"} else "CALLBACK"
                    return self._finish(con, session, outcome, actor, "Your interest is recorded and a local synthetic invitation is available in Action history. No real loan, rate change, or message was created." if outcome == "ACCEPT" else "Your officer callback request is recorded. No financial terms were changed.")
                if len(session["turns"]) >= 18:
                    return self._finish(con, session, "CALLBACK", actor, "I will stop and record a request for an officer to review your question.")
                self._say(con, session_id, "lender", "I can discuss only the stored approved proposal. I cannot negotiate new terms or approve a different amount. Please say interested, decline, callback, or stop calling.")
            return self._get(con, session_id)

    def end(self, session_id, actor, outcome="CALLBACK"):
        self.service._authorize(actor, {"AUTOMATION"})
        if outcome not in {"CALLBACK", "NO_ANSWER", "OPT_OUT"}:
            raise ActionError("INVALID_OUTCOME", "End a session with callback, no answer, or opt-out.")
        with self.service._db(write=True) as con:
            session = self._get(con, session_id)
            if session["state"] == "ENDED":
                return session
            return self._finish(con, session, outcome, actor, "The local voice test has ended. No real contact was placed.")
