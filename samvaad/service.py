"""Persistent local Customer 360 service with authoritative workflow controls.

SQLite is the development database. It uses atomic transactions and enforced
keys for local correctness. A Snowflake adapter will need equivalent guarantees;
we do not imply standard Snowflake table keys enforce uniqueness.
"""
import functools
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from samvaad.engine import CATALOGUE, compute_metrics, decide_customer
from samvaad.fixtures import generate_fixture
from samvaad.models import Actor, ActionError, DEMO_ACTORS
from samvaad.signals import extract_signals

JSON_FIELDS = {"entities", "offer", "evidence_ids", "reason_codes", "detail", "terms"}
BOOL_FIELDS = {"consent_calls", "consent_marketing", "dnd", "active"}
OUTCOMES = {"ACCEPT", "DECLINE", "CALLBACK", "OPT_OUT", "NO_ANSWER", "ALREADY_PAID", "FAILED"}


def utcnow():
    return datetime.now(timezone.utc)


def timestamp(value=None):
    return (value or utcnow()).isoformat()


def _decode(row):
    if row is None:
        return None
    result = dict(row)
    for key in JSON_FIELDS & result.keys():
        result[key] = json.loads(result[key]) if result[key] else ({} if key not in {"evidence_ids", "reason_codes"} else [])
    for key in BOOL_FIELDS & result.keys():
        result[key] = bool(result[key])
    return result


def guarded(method):
    """Persist denied-operation evidence after the failing transaction rolls back."""
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except ActionError as error:
            actor = kwargs.get("actor") or next((v for v in args if isinstance(v, Actor)), None)
            target = args[0] if args and isinstance(args[0], str) else None
            with self._db(write=True) as con:
                action = con.execute("SELECT customer_id FROM actions WHERE action_id=?", (target,)).fetchone()
                cid = action[0] if action else (target if target and target.startswith("C") else None)
                self._log(con, "ACTION_BLOCKED", cid, target if action else None,
                          actor.user_id if isinstance(actor, Actor) else "unresolved",
                          {"operation": method.__name__, "code": error.code, "reason": error.message})
            raise
    return wrapped


class LocalService:
    backend_label = "Local SQLite · offline analysis"
    is_demo = True

    def __init__(self, db_path: str | Path = ".local/samvaad.db", *, seed: bool = True):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.public_base_url = os.getenv("SAMVAAD_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        self._initialize()
        if seed:
            with self._db() as con:
                empty = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0
            if empty:
                self.seed_demo(DEMO_ACTORS["demo-admin"])

    @contextmanager
    def _db(self, write=False):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        if write:
            con.execute("BEGIN IMMEDIATE")
        try:
            yield con
            if write:
                con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self):
        with self._db() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
              customer_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, city TEXT, segment TEXT,
              monthly_income REAL, preferred_language TEXT, phone TEXT, email TEXT,
              consent_calls INTEGER NOT NULL, consent_marketing INTEGER NOT NULL, dnd INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS loans (
              loan_id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers, product TEXT,
              principal REAL, outstanding REAL, interest_rate REAL, emi REAL, relationship_months INTEGER,
              current_dpd INTEGER, status TEXT, disbursed_on TEXT);
            CREATE TABLE IF NOT EXISTS payments (
              payment_id TEXT PRIMARY KEY, loan_id TEXT REFERENCES loans, due_date TEXT, paid_date TEXT,
              amount_due REAL, amount_paid REAL, status TEXT);
            CREATE TABLE IF NOT EXISTS interactions (
              interaction_id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers, channel TEXT,
              ts TEXT, text TEXT, intent TEXT, sentiment REAL, entities TEXT, evidence_text TEXT,
              extraction_version TEXT, source_hash TEXT, simulated INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS catalogue (
              action_code TEXT PRIMARY KEY, title TEXT, priority INTEGER NOT NULL, approval_role TEXT,
              channel TEXT, active INTEGER, max_rate_cut_bps INTEGER, max_topup_amount REAL, version INTEGER);
            CREATE TABLE IF NOT EXISTS actions (
              action_id TEXT PRIMARY KEY, customer_id TEXT REFERENCES customers, action_code TEXT,
              channel TEXT, approval_role TEXT, offer TEXT, rationale TEXT, evidence_ids TEXT, reason_codes TEXT,
              script TEXT, status TEXT, attempts INTEGER DEFAULT 0, created_at TEXT, approved_at TEXT,
              approved_by TEXT, outcome TEXT, execution_mode TEXT, last_attempt_at TEXT,
              catalogue_version INTEGER, approval_note TEXT, completed_at TEXT);
            CREATE INDEX IF NOT EXISTS action_customer_time ON actions(customer_id, created_at);
            CREATE TABLE IF NOT EXISTS offers (
              offer_id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, action_id TEXT UNIQUE REFERENCES actions,
              customer_id TEXT REFERENCES customers, offer_type TEXT, amount REAL, rate_cut_bps INTEGER,
              terms TEXT, status TEXT, expires_at TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS response_events (
              event_id TEXT PRIMARY KEY, action_id TEXT REFERENCES actions, outcome TEXT, ts TEXT);
            CREATE TABLE IF NOT EXISTS audit_log (
              log_id TEXT PRIMARY KEY, ts TEXT, customer_id TEXT, action_id TEXT, event TEXT, detail TEXT, actor TEXT);
            """)

    def resolve_actor(self, user_id: str) -> Actor:
        if user_id not in DEMO_ACTORS:
            raise ActionError("UNKNOWN_ACTOR", "Unknown local demo operator.")
        return DEMO_ACTORS[user_id]

    def _authorize(self, actor: Actor | None, roles=None):
        if not isinstance(actor, Actor) or DEMO_ACTORS.get(actor.user_id) != actor:
            raise ActionError("FORBIDDEN", "The operator identity and role are not authorized.")
        if roles is not None and actor.role not in roles:
            raise ActionError("FORBIDDEN", "This operator cannot perform that operation.")

    def _log(self, con, event, cid=None, action_id=None, actor="service", detail=None):
        con.execute("INSERT INTO audit_log VALUES (?,?,?,?,?,?,?)",
                    (str(uuid4()), timestamp(), cid, action_id, event, json.dumps(detail or {}), actor))

    def _customer(self, con, cid):
        customer = _decode(con.execute("SELECT * FROM customers WHERE customer_id=?", (cid,)).fetchone())
        if not customer:
            raise ActionError("CUSTOMER_NOT_FOUND", "The customer does not exist.")
        customer.update(id=cid, name=customer["full_name"], income=customer["monthly_income"], language=customer["preferred_language"])
        return customer

    def _action(self, con, aid):
        action = _decode(con.execute("SELECT a.*,c.full_name customer_name FROM actions a JOIN customers c USING(customer_id) WHERE action_id=?", (aid,)).fetchone())
        if not action:
            raise ActionError("ACTION_NOT_FOUND", "The action does not exist.")
        return action

    def _view(self, con, cid):
        customer = self._customer(con, cid)
        loans = [_decode(r) for r in con.execute("SELECT * FROM loans WHERE customer_id=? ORDER BY status,loan_id", (cid,))]
        payments = [_decode(r) for r in con.execute("SELECT p.* FROM payments p JOIN loans l USING(loan_id) WHERE customer_id=? ORDER BY due_date,payment_id", (cid,))]
        interactions = [_decode(r) for r in con.execute("SELECT * FROM interactions WHERE customer_id=? ORDER BY ts DESC,interaction_id", (cid,))]
        metrics = compute_metrics(customer, loans, payments, interactions)
        catalogue = [_decode(r) for r in con.execute("SELECT * FROM catalogue")]
        # Display bounded sizing even before there is a queued recommendation.
        topup_cap = next((c["max_topup_amount"] for c in catalogue if c["action_code"] == "TOPUP_PREAPPROVAL_CALL"), 0)
        metrics["topup_amount"] = min(metrics["topup_amount"], topup_cap or 0)
        recommendation = decide_customer(customer, metrics, interactions, catalogue)
        latest = con.execute("SELECT action_id FROM actions WHERE customer_id=? ORDER BY created_at DESC LIMIT 1", (cid,)).fetchone()
        action = self._action(con, latest[0]) if latest else None
        return {"customer": customer, "metrics": metrics, "loans": loans, "payments": payments,
                "interactions": interactions, "recommendation": action or recommendation,
                "current_decision": recommendation, "provider": self.backend_label}

    def customer360(self, customer_id):
        with self._db() as con:
            return self._view(con, customer_id)

    def list_customers(self, search=""):
        with self._db() as con:
            rows = con.execute("SELECT customer_id FROM customers WHERE full_name LIKE ? OR customer_id LIKE ? OR city LIKE ? ORDER BY customer_id",
                               (f"%{search}%", f"%{search}%", f"%{search}%"))
            return [self._customer(con, r[0]) for r in rows.fetchall()]

    def portfolio(self):
        with self._db() as con:
            views = [self._view(con, r[0]) for r in con.execute("SELECT customer_id FROM customers").fetchall()]
            states = dict(con.execute("SELECT status,COUNT(*) FROM actions GROUP BY status").fetchall())
            mix = dict(con.execute("SELECT action_code,COUNT(*) FROM actions GROUP BY action_code").fetchall())
            return {"customers": len(views), "total_customers": len(views),
                    "active_loans": sum(v["metrics"]["active_loans"] for v in views),
                    "total_outstanding": sum(v["metrics"]["total_outstanding"] for v in views),
                    "past_due": sum(v["metrics"]["dpd"] > 0 for v in views),
                    "at_risk": sum(v["metrics"]["churn_risk"] >= .6 or v["metrics"]["collections_risk"] >= .4 for v in views),
                    "topup_eligible": sum(v["metrics"]["topup_eligible"] for v in views),
                    "pending_approvals": states.get("PENDING_APPROVAL", 0), "approved_actions": states.get("APPROVED", 0),
                    "completed_actions": states.get("COMPLETED", 0), "action_mix": mix}

    def actions(self, status=None):
        with self._db() as con:
            ids = con.execute("SELECT action_id FROM actions " + ("WHERE status=? " if status else "") + "ORDER BY created_at DESC",
                              (status,) if status else ()).fetchall()
            return [self._action(con, row[0]) for row in ids]

    def catalogue(self):
        with self._db() as con:
            return [_decode(r) for r in con.execute("SELECT * FROM catalogue ORDER BY priority")]

    def _queue(self, con, cid, actor):
        view = self._view(con, cid)
        decision = view["current_decision"]
        if decision["action_code"] == "NO_ACTION":
            superseded = con.execute("SELECT action_id FROM actions WHERE customer_id=? AND status IN ('PENDING_APPROVAL','APPROVED')", (cid,)).fetchall()
            for row in superseded:
                con.execute("UPDATE actions SET status='CANCELLED' WHERE action_id=?", (row[0],))
                self._log(con, "RECOMMENDATION_SUPERSEDED", cid, row[0], actor.user_id,
                          {"reason": "Customer no longer has an eligible action", "current_reason_codes": decision["reason_codes"]})
            return {**decision, "customer_id": cid, "customer_name": view["customer"]["full_name"], "status": "NO_ACTION"}
        recent = con.execute("SELECT action_id FROM actions WHERE customer_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 1",
                             (cid, timestamp(utcnow() - timedelta(days=7)))).fetchone()
        if recent:
            existing = self._action(con, recent[0])
            changed = (existing["catalogue_version"] != decision["catalogue_version"]
                       or existing["action_code"] != decision["action_code"] or existing["offer"] != decision["offer"])
            if changed and existing["status"] in {"PENDING_APPROVAL", "APPROVED", "BLOCKED", "CANCELLED"}:
                con.execute("UPDATE actions SET status='CANCELLED' WHERE action_id=?", (existing["action_id"],))
                self._log(con, "RECOMMENDATION_SUPERSEDED", cid, existing["action_id"], actor.user_id,
                          {"reason": "Current evidence, eligibility, or catalogue terms changed", "new_approval_required": True})
            else:
                return existing
        aid = str(uuid4())
        status = "APPROVED" if decision["approval_role"] == "AUTO" else "PENDING_APPROVAL"
        con.execute("""INSERT INTO actions (action_id,customer_id,action_code,channel,approval_role,offer,rationale,
                       evidence_ids,reason_codes,script,status,created_at,catalogue_version,approved_by,approved_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (aid, cid, decision["action_code"], decision["channel"], decision["approval_role"], json.dumps(decision["offer"]),
                     decision["rationale"], json.dumps(decision["evidence_ids"]), json.dumps(decision["reason_codes"]), decision["script"],
                     status, timestamp(), decision["catalogue_version"], "service-policy" if status == "APPROVED" else None,
                     timestamp() if status == "APPROVED" else None))
        self._log(con, "NBA_QUEUED", cid, aid, actor.user_id, {"action": decision["action_code"], "status": status, "offer": decision["offer"]})
        if status == "APPROVED":
            self._log(con, "ACTION_AUTO_APPROVED", cid, aid, "service-policy", {"scope": "nonfinancial service contact"})
        return self._action(con, aid)

    @guarded
    def recommend(self, customer_id, actor):
        self._authorize(actor, {"ANALYST", "MANAGER", "CREDIT", "ADMIN", "AUTOMATION"})
        with self._db(write=True) as con:
            return self._queue(con, customer_id, actor)

    def queue_all(self, actor):
        self._authorize(actor)
        with self._db(write=True) as con:
            return [self._queue(con, r[0], actor) for r in con.execute("SELECT customer_id FROM customers").fetchall()]

    def _validate_current(self, con, action):
        if utcnow() - datetime.fromisoformat(action["created_at"]) > timedelta(days=7):
            raise ActionError("ACTION_EXPIRED", "This recommendation expired. Generate a fresh action.")
        view = self._view(con, action["customer_id"])
        if not view["customer"]["consent_calls"] or view["customer"]["dnd"]:
            raise ActionError("CONSENT_REQUIRED", "Contact is blocked by current consent or DND preferences.")
        decision = view["current_decision"]
        if action["action_code"] == "TOPUP_PREAPPROVAL_CALL" and not view["customer"]["consent_marketing"]:
            raise ActionError("CONSENT_REQUIRED", "Marketing consent is required for the top-up invitation.")
        if decision["action_code"] != action["action_code"]:
            raise ActionError("NOT_ELIGIBLE", "The customer no longer qualifies for this action.")
        if decision.get("catalogue_version") != action["catalogue_version"] or decision["offer"] != action["offer"]:
            raise ActionError("STALE_APPROVAL", "The policy or offer changed. Cancel this action and obtain a fresh approval.")
        source_ids = {i["interaction_id"] for i in view["interactions"]}
        if not set(action["evidence_ids"]).issubset(source_ids):
            raise ActionError("INVALID_EVIDENCE", "The recommendation references missing evidence.")

    @guarded
    def approve_action(self, action_id, actor, decision="APPROVE", note=""):
        self._authorize(actor)
        if decision not in {"APPROVE", "REJECT"}:
            raise ActionError("INVALID_DECISION", "Choose APPROVE or REJECT.")
        with self._db(write=True) as con:
            action = self._action(con, action_id)
            if actor.role != action["approval_role"]:
                raise ActionError("FORBIDDEN", f"This action requires a {action['approval_role']} approver.")
            destination = "APPROVED" if decision == "APPROVE" else "REJECTED"
            if action["status"] == destination:
                return action
            if action["status"] != "PENDING_APPROVAL":
                raise ActionError("INVALID_STATE", "Only a pending recommendation can be approved or rejected.")
            self._validate_current(con, action)
            con.execute("UPDATE actions SET status=?,approved_by=?,approved_at=?,approval_note=? WHERE action_id=? AND status='PENDING_APPROVAL'",
                        (destination, actor.user_id, timestamp(), note[:1000], action_id))
            self._log(con, "ACTION_APPROVED" if decision == "APPROVE" else "ACTION_REJECTED", action["customer_id"], action_id,
                      actor.user_id, {"note": note[:1000], "offer": action["offer"]})
            return self._action(con, action_id)

    def _create_offer(self, con, action):
        existing = con.execute("SELECT token FROM offers WHERE action_id=?", (action["action_id"],)).fetchone()
        if existing:
            return existing[0]
        token = secrets.token_urlsafe(32)
        offer = action["offer"]
        con.execute("INSERT INTO offers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), token, action["action_id"], action["customer_id"],
                     "TOPUP" if action["action_code"] == "TOPUP_PREAPPROVAL_CALL" else "RATE_CUT",
                     offer.get("amount"), offer.get("rate_cut_bps"), json.dumps({**offer, "synthetic": True,
                     "disclosure": "Fictional conditional invitation. No real loan or rate change is offered."}),
                     "CREATED", timestamp(utcnow() + timedelta(hours=72)), timestamp()))
        self._log(con, "LINK_CREATED", action["customer_id"], action["action_id"], "local-runner", {"synthetic": True, "expires_in_hours": 72})
        return token

    @guarded
    def execute_action(self, action_id, actor, mode="simulate", outcome="ACCEPT", now=None):
        self._authorize(actor, {"AUTOMATION"})
        if mode != "simulate":
            raise ActionError("LIVE_NOT_CONFIGURED", "Live delivery is pending. Local testing uses simulated contact and a real local offer page.")
        if outcome not in OUTCOMES:
            raise ActionError("INVALID_OUTCOME", "Unsupported customer-response outcome.")
        effective_now = now or utcnow()
        if effective_now.tzinfo is None:
            effective_now = effective_now.replace(tzinfo=timezone.utc)
        with self._db(write=True) as con:
            action = self._action(con, action_id)
            if action["status"] == "COMPLETED":
                return action
            if action["status"] != "APPROVED":
                raise ActionError("APPROVAL_REQUIRED", "An approved action is required before execution.")
            self._validate_current(con, action)
            if action["attempts"] >= 3:
                raise ActionError("ATTEMPTS_EXHAUSTED", "The maximum of three attempts has been reached.")
            if action["last_attempt_at"] and effective_now - datetime.fromisoformat(action["last_attempt_at"]) < timedelta(hours=4):
                raise ActionError("RETRY_TOO_SOON", "Wait at least four hours before another contact attempt.")
            con.execute("UPDATE actions SET status='EXECUTING',attempts=attempts+1,last_attempt_at=?,execution_mode=? WHERE action_id=? AND status='APPROVED'",
                        (timestamp(effective_now), mode, action_id))
            action = self._action(con, action_id)
            self._log(con, "EXECUTION_STARTED", action["customer_id"], action_id, actor.user_id,
                      {"mode": mode, "attempt": action["attempts"]})
            if outcome not in {"NO_ANSWER", "FAILED", "OPT_OUT", "DECLINE"} and action["approval_role"] in {"MANAGER", "CREDIT"}:
                self._create_offer(con, action)
                con.execute("UPDATE offers SET status='SIMULATED_DELIVERY' WHERE action_id=?", (action_id,))
                self._log(con, "DELIVERY_SIMULATED", action["customer_id"], action_id, actor.user_id,
                          {"channel": action["channel"], "real_email_sent": False})
            self._apply_response(con, action, outcome, f"simulation:{action_id}:{action['attempts']}", actor)
            return self._action(con, action_id)

    def _apply_response(self, con, action, outcome, event_id, actor):
        if not event_id or len(event_id) > 200:
            raise ActionError("INVALID_EVENT", "A bounded event ID is required.")
        seen = con.execute("SELECT action_id,outcome FROM response_events WHERE event_id=?", (event_id,)).fetchone()
        if seen:
            if seen[0] != action["action_id"] or seen[1] != outcome:
                raise ActionError("EVENT_CONFLICT", "That event ID was already used for a different response.")
            return
        con.execute("INSERT INTO response_events VALUES (?,?,?,?)", (event_id, action["action_id"], outcome, timestamp()))
        if outcome in {"NO_ANSWER", "FAILED"}:
            new_state = "EXHAUSTED" if action["attempts"] >= 3 else "APPROVED"
        elif outcome == "OPT_OUT":
            new_state = "CANCELLED"
            self._revoke(con, action["customer_id"], actor)
        else:
            new_state = "COMPLETED"
        con.execute("UPDATE actions SET status=?,outcome=?,completed_at=? WHERE action_id=?",
                    (new_state, outcome, timestamp() if new_state in {"COMPLETED", "CANCELLED", "EXHAUSTED"} else None, action["action_id"]))
        if outcome == "ACCEPT":
            con.execute("UPDATE offers SET status='ACCEPTED' WHERE action_id=?", (action["action_id"],))
        elif outcome == "DECLINE":
            con.execute("UPDATE offers SET status='DECLINED' WHERE action_id=?", (action["action_id"],))
        self._log(con, "CUSTOMER_RESPONSE", action["customer_id"], action["action_id"], actor.user_id,
                  {"outcome": outcome, "event_id": event_id, "mode": action.get("execution_mode")})
        event = {"HARDSHIP_RESTRUCTURE_CALL": "RESTRUCTURE_REVIEW_REQUESTED",
                 "RETENTION_RATE_MATCH_CALL": "RATE_OFFER_ACCEPTED",
                 "TOPUP_PREAPPROVAL_CALL": "PREAPPROVAL_LINK_CREATED"}.get(action["action_code"], "PAYMENT_REVIEW_REQUESTED")
        if outcome == "ACCEPT":
            self._log(con, event, action["customer_id"], action["action_id"], actor.user_id, {"synthetic": True})
        text = f"Simulated outcome: {outcome}. No recorded borrower speech or inferred customer sentiment."
        self._insert_interaction(con, f"OUT-{event_id}", action["customer_id"], "ACTION_OUTCOME", text, simulated=True)
        if new_state in {"COMPLETED", "CANCELLED", "EXHAUSTED"}:
            self._log(con, "ACTION_" + new_state, action["customer_id"], action["action_id"], actor.user_id, {"outcome": outcome})

    @guarded
    def record_response(self, action_id, outcome, event_id, actor):
        self._authorize(actor, {"AUTOMATION"})
        if outcome not in OUTCOMES:
            raise ActionError("INVALID_OUTCOME", "Unsupported response.")
        with self._db(write=True) as con:
            return self._record_response(con, action_id, outcome, event_id, actor)

    def _record_response(self, con, action_id, outcome, event_id, actor):
        """Record one response inside the caller's existing write transaction."""
        if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
            raise ActionError("INVALID_EVENT", "A bounded event ID is required.")
        action = self._action(con, action_id)
        previous = con.execute("SELECT action_id,outcome FROM response_events WHERE event_id=?", (event_id,)).fetchone()
        if previous:
            if previous[0] != action_id or previous[1] != outcome:
                raise ActionError("EVENT_CONFLICT", "That event ID was already used for a different response.")
            return action
        if action["attempts"] == 0 or action["status"] not in {"EXECUTING", "COMPLETED", "APPROVED", "EXHAUSTED"}:
            raise ActionError("INVALID_STATE", "A response requires an executed action.")
        if action["status"] == "COMPLETED" and action["outcome"] == outcome:
            # Preserve the event binding even when the effective preference is
            # unchanged, so that reusing it for another outcome cannot succeed.
            con.execute("INSERT INTO response_events VALUES (?,?,?,?)", (event_id, action_id, outcome, timestamp()))
            return action
        # Preference changes do not run another delivery or underwriting decision.
        self._apply_response(con, action, outcome, event_id, actor)
        return self._action(con, action_id)

    def _revoke(self, con, cid, actor):
        self._customer(con, cid)
        con.execute("UPDATE customers SET consent_calls=0,consent_marketing=0 WHERE customer_id=?", (cid,))
        con.execute("UPDATE actions SET status='CANCELLED',outcome='OPT_OUT' WHERE customer_id=? AND status IN ('PENDING_APPROVAL','APPROVED','EXECUTING')", (cid,))
        self._log(con, "OPTED_OUT", cid, None, actor.user_id, {"scope": "all demo contact", "pending_actions_cancelled": True})

    @guarded
    def revoke_consent(self, customer_id, actor):
        self._authorize(actor)
        with self._db(write=True) as con:
            self._revoke(con, customer_id, actor)
            return self._customer(con, customer_id)

    def _offer(self, row):
        offer = _decode(row)
        if offer:
            offer["url"] = offer["offer_url"] = self.public_base_url + "/offer/" + offer["token"]
            offer["synthetic"] = True
        return offer

    def offers(self, customer_id=None):
        with self._db() as con:
            rows = con.execute("SELECT o.*,c.full_name customer_name FROM offers o JOIN customers c USING(customer_id) "
                               + ("WHERE customer_id=? " if customer_id else "") + "ORDER BY created_at DESC",
                               (customer_id,) if customer_id else ())
            return [self._offer(row) for row in rows]

    def _lookup_offer(self, con, token, now=None):
        offer = self._offer(con.execute("SELECT o.*,c.full_name customer_name FROM offers o JOIN customers c USING(customer_id) WHERE token=?", (token,)).fetchone())
        if not offer:
            raise ActionError("OFFER_NOT_FOUND", "The invitation does not exist.")
        current = now or utcnow()
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if datetime.fromisoformat(offer["expires_at"]) <= current:
            raise ActionError("OFFER_EXPIRED", "This invitation has expired.")
        return offer

    def _check_offer_consent(self, con, offer):
        customer = self._customer(con, offer["customer_id"])
        if not customer["consent_calls"] or not customer["consent_marketing"] and offer["offer_type"] == "TOPUP":
            raise ActionError("OFFER_REVOKED", "The invitation was withdrawn after consent changed.")

    def get_offer(self, token, now=None):
        with self._db() as con:
            offer = self._lookup_offer(con, token, now=now)
            self._check_offer_consent(con, offer)
            return offer

    def respond_to_offer(self, token, outcome, event_id):
        """Atomically apply a capability-scoped, synthetic invitation response.

        The opaque token never becomes an audit target. A replay of an exact
        event is permitted after opt-out, but expiration always wins.
        """
        if outcome not in {"ACCEPT", "DECLINE", "CALLBACK", "OPT_OUT"}:
            raise ActionError("INVALID_OUTCOME", "Unsupported invitation response.")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
            raise ActionError("INVALID_EVENT", "A bounded event ID is required.")
        actor = self.resolve_actor("local-runner")
        with self._db(write=True) as con:
            offer = self._lookup_offer(con, token)
            previous = con.execute("SELECT action_id,outcome FROM response_events WHERE event_id=?", (event_id,)).fetchone()
            if previous:
                if previous[0] != offer["action_id"] or previous[1] != outcome:
                    raise ActionError("EVENT_CONFLICT", "That event ID was already used for a different response.")
                return {"offer": offer, "action": self._action(con, offer["action_id"]), "replayed": True}
            self._check_offer_consent(con, offer)
            action = self._record_response(con, offer["action_id"], outcome, event_id, actor)
            if outcome == "OPT_OUT":
                con.execute("UPDATE offers SET status='REVOKED' WHERE customer_id=?", (offer["customer_id"],))
            offer = self._lookup_offer(con, token)
            return {"offer": offer, "action": action, "replayed": False}

    def audit(self, customer_id=None, action_id=None):
        predicates, params = [], []
        for name, value in [("customer_id", customer_id), ("action_id", action_id)]:
            if value:
                predicates.append(name + "=?")
                params.append(value)
        with self._db() as con:
            rows = con.execute("SELECT * FROM audit_log " + ("WHERE " + " AND ".join(predicates) if predicates else "") + " ORDER BY ts DESC, rowid DESC", params)
            return [_decode(r) for r in rows]

    @guarded
    def update_catalogue(self, action_code, actor, **changes):
        self._authorize(actor, {"ADMIN"})
        allowed = {"priority", "max_rate_cut_bps", "max_topup_amount", "active"}
        if not changes or not changes.keys() <= allowed:
            raise ActionError("INVALID_CATALOGUE", "Only priority, limits, and active state may be changed.")
        if any(value is None or isinstance(value, (dict, list)) or not isinstance(value, (int, float, bool)) or value < 0 for value in changes.values()):
            raise ActionError("INVALID_CATALOGUE", "Catalogue limits must be nonnegative numbers.")
        with self._db(write=True) as con:
            existing = con.execute("SELECT * FROM catalogue WHERE action_code=?", (action_code,)).fetchone()
            if not existing:
                raise ActionError("ACTION_NOT_FOUND", "Unknown catalogue action.")
            assignment = ",".join(f"{key}=?" for key in changes)
            con.execute(f"UPDATE catalogue SET {assignment},version=version+1 WHERE action_code=?", (*changes.values(), action_code))
            self._log(con, "CATALOGUE_CHANGED", actor=actor.user_id, detail={"action_code": action_code, "changes": changes})
            return _decode(con.execute("SELECT * FROM catalogue WHERE action_code=?", (action_code,)).fetchone())

    def _insert_interaction(self, con, iid, cid, channel, text, simulated=False, ts=None):
        signals = extract_signals(text)
        # Execution metadata contains no customer utterance; never analyze it as speech.
        if channel == "ACTION_OUTCOME":
            signals.update(intent="general query", sentiment=0, entities={})
        con.execute("INSERT OR IGNORE INTO interactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (iid, cid, channel, ts or timestamp(), text, signals["intent"], signals["sentiment"],
                     json.dumps(signals["entities"]), signals["evidence_text"], signals["extraction_version"], signals["source_hash"], int(simulated)))

    @guarded
    def add_interaction(self, customer_id, text, channel="CHAT", actor=None):
        self._authorize(actor, {"ANALYST", "ADMIN"})
        if not text.strip() or len(text) > 20000 or channel not in {"CHAT", "EMAIL", "CALL_IN", "COMPLAINT"}:
            raise ActionError("INVALID_INTERACTION", "Provide a valid channel and a conversation of 1-20,000 characters.")
        with self._db(write=True) as con:
            self._customer(con, customer_id)
            iid = "I-" + str(uuid4())
            self._insert_interaction(con, iid, customer_id, channel, text)
            self._log(con, "INTERACTION_ADDED", customer_id, actor=actor.user_id, detail={"interaction_id": iid, "channel": channel})
            return _decode(con.execute("SELECT * FROM interactions WHERE interaction_id=?", (iid,)).fetchone())

    @guarded
    def seed_demo(self, actor, customers=20):
        self._authorize(actor, {"ADMIN"})
        fixture = generate_fixture(customers)
        with self._db(write=True) as con:
            if con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]:
                return {"status": "ALREADY_SEEDED", "customers": con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]}
            for table in ("customers", "loans", "payments"):
                for row in fixture[table]:
                    columns = list(row)
                    con.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(row.values()))
            for row in fixture["interactions"]:
                self._insert_interaction(con, row["interaction_id"], row["customer_id"], row["channel"], row["text"], ts=row["ts"])
            for row in CATALOGUE:
                con.execute(f"INSERT INTO catalogue ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))
            self._log(con, "DEMO_SEEDED", actor=actor.user_id, detail={"customers": len(fixture["customers"]), "synthetic": True})
            for cid in ("C0001", "C0002", "C0003"):
                self._queue(con, cid, actor)
        return {"status": "SEEDED", "customers": len(fixture["customers"])}

    @guarded
    def reset_demo(self, actor):
        self._authorize(actor, {"ADMIN"})
        with self._db(write=True) as con:
            for table in ("response_events", "offers", "actions", "interactions", "payments", "loans", "customers", "catalogue", "audit_log"):
                con.execute("DELETE FROM " + table)
        return self.seed_demo(actor)

    def ask(self, question, customer_id=None, actor=None):
        self._authorize(actor or DEMO_ACTORS["meera"])
        from samvaad.knowledge import answer_question
        return answer_question(self, question, customer_id, actor or DEMO_ACTORS["meera"])

    def local_time(self):
        return utcnow().astimezone(ZoneInfo("Asia/Kolkata")).isoformat()
