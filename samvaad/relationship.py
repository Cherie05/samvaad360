"""Private operational relationship intake, versioned synchronization and service cases.

This module composes LocalService rather than writing public demo snapshots.
Document review flags record a staff attestation; they do not perform KYC.
Portal links are short-lived customer-scoped capabilities, not identity proof.
"""
import hashlib
import json
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from samvaad.models import ActionError, DEMO_ACTORS
from samvaad.service import timestamp, utcnow


STAFF_ROLES = {"ANALYST", "MANAGER", "CREDIT", "ADMIN"}
INTAKE_ROLES = {"ANALYST", "ADMIN"}
CASE_CATEGORIES = {"SERVICE", "COMPLAINT", "HARDSHIP", "DOCUMENTS", "CONTACT_UPDATE"}
CASE_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
CASE_STATUSES = {"OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"}
RECORD_TYPES = {"customer", "loan", "payment", "interaction"}
LANGUAGES = {"English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Marathi", "Bengali"}
CUSTOMER_FIELDS = {"full_name", "city", "segment", "monthly_income", "preferred_language", "phone", "email",
                   "consent_calls", "consent_marketing", "dnd"}
ONBOARDING_FIELDS = CUSTOMER_FIELDS | {"identity_review", "document_review", "document_review_attested", "consent_reference"}


def _fail(code, message):
    raise ActionError(code, message)


def _text(value, field, maximum=200, *, required=False):
    if not isinstance(value, str):
        _fail("INVALID_FIELD", f"{field} must be text.")
    value = value.strip()
    if len(value) > maximum or (required and not value) or any(ord(c) < 32 and c not in "\n\t" for c in value):
        _fail("INVALID_FIELD", f"{field} is missing, too long, or contains control characters.")
    return value


def _number(value, field, maximum=1_000_000_000, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > maximum:
        _fail("INVALID_FIELD", f"{field} must be a finite nonnegative number within the supported limit.")
    if integer and int(value) != value:
        _fail("INVALID_FIELD", f"{field} must be a whole number.")
    return int(value) if integer else float(value)


def _boolean(value, field):
    if not isinstance(value, bool):
        _fail("INVALID_FIELD", f"{field} must be true or false.")
    return value


def _date(value, field, optional=False):
    if optional and value in (None, ""):
        return None
    value = _text(value, field, 40, required=True)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        _fail("INVALID_FIELD", f"{field} must use YYYY-MM-DD.")
    if parsed.isoformat() != value:
        _fail("INVALID_FIELD", f"{field} must use YYYY-MM-DD.")
    return value


def _instant(value, field, optional=False):
    if optional and value in (None, ""):
        return None
    value = _text(value, field, 80, required=True)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        _fail("INVALID_FIELD", f"{field} must be an ISO timestamp with a timezone.")


def _mapping(payload, allowed):
    if not isinstance(payload, dict) or not all(isinstance(k, str) for k in payload) or not payload.keys() <= allowed:
        _fail("INVALID_PAYLOAD", "The payload contains unsupported fields or is not an object.")


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _hash(payload):
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _key(value):
    value = _text(value, "idempotency_key", 100, required=True)
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,100}", value):
        _fail("INVALID_IDEMPOTENCY_KEY", "Use an 8-100 character stable request key.")
    return value


def normalize_customer(payload):
    """Validate a customer row without interpreting rich text or importing decisions."""
    _mapping(payload, ONBOARDING_FIELDS)
    result = {
        "full_name": _text(payload.get("full_name", ""), "full_name", 160, required=True),
        "city": _text(payload.get("city", ""), "city", 100),
        "segment": _text(payload.get("segment", "OTHER"), "segment", 40).upper(),
        "monthly_income": _number(payload.get("monthly_income", 0), "monthly_income", 100_000_000),
        "preferred_language": _text(payload.get("preferred_language", "English"), "preferred_language", 30),
        "phone": _text(payload.get("phone", ""), "phone", 20),
        "email": _text(payload.get("email", ""), "email", 254).lower(),
        "consent_calls": _boolean(payload.get("consent_calls", False), "consent_calls"),
        "consent_marketing": _boolean(payload.get("consent_marketing", False), "consent_marketing"),
        "dnd": _boolean(payload.get("dnd", False), "dnd"),
    }
    if result["segment"] not in {"SALARIED", "SELF_EMPLOYED", "OTHER", "RETAIL"}:
        _fail("INVALID_FIELD", "Choose a supported customer segment.")
    if result["preferred_language"] not in LANGUAGES:
        _fail("INVALID_FIELD", "Choose a supported preferred language.")
    if result["phone"] and not re.fullmatch(r"\+[1-9]\d{7,14}", result["phone"]):
        _fail("INVALID_FIELD", "phone must use international E.164 format.")
    if result["email"] and not re.fullmatch(r"[^\s@]{1,64}@[^\s@.]+(?:\.[^\s@.]+)+", result["email"]):
        _fail("INVALID_FIELD", "email must be a valid address.")
    if result["consent_calls"] and not result["phone"]:
        _fail("INVALID_FIELD", "A phone number is required when call consent is recorded.")
    if result["dnd"]:
        result["consent_calls"] = result["consent_marketing"] = False
    return result


def normalize_sync_record(payload):
    """One full source record; omitted customer preferences default to no consent."""
    if not isinstance(payload, dict):
        _fail("INVALID_PAYLOAD", "Each synchronization row must be an object.")
    kind = payload.get("record_type")
    if not isinstance(kind, str) or kind not in RECORD_TYPES:
        _fail("INVALID_RECORD_TYPE", "Choose customer, loan, payment, or interaction.")
    base = {"record_type", "source_record_id", "source_version"}
    fields = {
        "customer": CUSTOMER_FIELDS,
        "loan": {"customer_ref", "product", "principal", "outstanding", "interest_rate", "emi", "relationship_months", "current_dpd", "status", "disbursed_on"},
        "payment": {"loan_ref", "due_date", "paid_date", "amount_due", "amount_paid", "status"},
        "interaction": {"customer_ref", "channel", "text", "ts"},
    }[kind]
    _mapping(payload, base | fields)
    record_id = _text(payload.get("source_record_id", ""), "source_record_id", 120, required=True)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", record_id):
        _fail("INVALID_SOURCE_ID", "Source record IDs must use letters, digits, and ordinary reference separators.")
    result = {"record_type": kind, "source_record_id": record_id,
              "source_version": _number(payload.get("source_version"), "source_version", 2_147_483_647, integer=True)}
    if result["source_version"] < 1:
        _fail("INVALID_VERSION", "source_version must be a positive whole number.")
    data = {k: v for k, v in payload.items() if k in fields}
    if kind == "customer":
        result.update(normalize_customer(data))
    elif kind == "loan":
        result.update(customer_ref=_text(data.get("customer_ref", ""), "customer_ref", 120, required=True),
                      product=_text(data.get("product", "PERSONAL_LOAN"), "product", 80, required=True),
                      principal=_number(data.get("principal"), "principal"),
                      outstanding=_number(data.get("outstanding"), "outstanding"),
                      interest_rate=_number(data.get("interest_rate"), "interest_rate", 100),
                      emi=_number(data.get("emi"), "emi"),
                      relationship_months=_number(data.get("relationship_months", 0), "relationship_months", 1200, integer=True),
                      current_dpd=_number(data.get("current_dpd", 0), "current_dpd", 3650, integer=True),
                      status=_text(data.get("status", "ACTIVE"), "status", 20).upper(),
                      disbursed_on=_date(data.get("disbursed_on"), "disbursed_on"))
        if result["status"] not in {"ACTIVE", "CLOSED"} or result["outstanding"] > result["principal"]:
            _fail("INVALID_LOAN", "Use ACTIVE/CLOSED and outstanding no greater than principal.")
        if result["status"] == "CLOSED" and result["outstanding"] != 0:
            _fail("INVALID_LOAN", "A closed loan must have zero outstanding.")
    elif kind == "payment":
        result.update(loan_ref=_text(data.get("loan_ref", ""), "loan_ref", 120, required=True),
                      due_date=_date(data.get("due_date"), "due_date"),
                      paid_date=_date(data.get("paid_date"), "paid_date", optional=True),
                      amount_due=_number(data.get("amount_due"), "amount_due"),
                      amount_paid=_number(data.get("amount_paid", 0), "amount_paid"),
                      status=_text(data.get("status", "PENDING"), "status", 20).upper())
        if result["status"] not in {"PAID", "LATE", "BOUNCED", "PENDING"}:
            _fail("INVALID_PAYMENT", "Choose PAID, LATE, BOUNCED, or PENDING.")
        if result["status"] in {"PAID", "LATE"} and (not result["paid_date"] or result["amount_paid"] < result["amount_due"]):
            _fail("INVALID_PAYMENT", "A settled payment needs a paid date and sufficient paid amount.")
        if result["paid_date"] and result["paid_date"] < result["due_date"] and result["status"] == "LATE":
            _fail("INVALID_PAYMENT", "A late payment cannot precede its due date.")
    else:
        result.update(customer_ref=_text(data.get("customer_ref", ""), "customer_ref", 120, required=True),
                      channel=_text(data.get("channel", "CHAT"), "channel", 20).upper(),
                      text=_text(data.get("text", ""), "text", 20_000, required=True),
                      ts=_instant(data.get("ts"), "ts"))
        if result["channel"] not in {"CHAT", "EMAIL", "CALL_IN", "COMPLAINT"}:
            _fail("INVALID_INTERACTION", "Use CHAT, EMAIL, CALL_IN, or COMPLAINT.")
    return result


def _case_payload(payload, actor):
    _mapping(payload, {"category", "priority", "subject", "description", "due_at", "owner"})
    result = {"category": _text(payload.get("category", "SERVICE"), "category", 30).upper(),
              "priority": _text(payload.get("priority", "NORMAL"), "priority", 20).upper(),
              "subject": _text(payload.get("subject", ""), "subject", 160, required=True),
              "description": _text(payload.get("description", ""), "description", 3000, required=True),
              "due_at": _instant(payload.get("due_at"), "due_at", optional=True),
              "owner": _text(payload.get("owner", actor.user_id), "owner", 80, required=True)}
    if result["category"] not in CASE_CATEGORIES or result["priority"] not in CASE_PRIORITIES:
        _fail("INVALID_CASE", "Choose a supported case category and priority.")
    if result["owner"] not in DEMO_ACTORS or DEMO_ACTORS[result["owner"]].role not in STAFF_ROLES:
        _fail("INVALID_OWNER", "Assign the case to a known staff operator.")
    return result


class RelationshipService:
    """Atomic local CRM operations. API identity resolution remains outside this class."""

    def __init__(self, service):
        self.service = service
        with service._db(write=True) as con:
            statements = [
                """CREATE TABLE IF NOT EXISTS relationship_onboardings (
                onboarding_id TEXT PRIMARY KEY, payload TEXT NOT NULL,status TEXT NOT NULL,
                submitted_by TEXT NOT NULL,created_at TEXT NOT NULL,reviewed_by TEXT,reviewed_at TEXT,
                review_note TEXT,customer_id TEXT REFERENCES customers)""",
                """CREATE TABLE IF NOT EXISTS relationship_profiles (
                customer_id TEXT PRIMARY KEY REFERENCES customers,lifecycle_stage TEXT NOT NULL,
                owner TEXT NOT NULL,next_followup_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS relationship_cases (
                case_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers,category TEXT NOT NULL,
                priority TEXT NOT NULL,subject TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL,
                owner TEXT NOT NULL,due_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                created_by TEXT NOT NULL,resolution_note TEXT)""",
                """CREATE TABLE IF NOT EXISTS relationship_requests (
                operation TEXT NOT NULL,scope TEXT NOT NULL,request_key TEXT NOT NULL,payload_hash TEXT NOT NULL,
                response TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(operation,scope,request_key))""",
                """CREATE TABLE IF NOT EXISTS relationship_sources (
                source TEXT NOT NULL,record_type TEXT NOT NULL,source_record_id TEXT NOT NULL,
                source_version INTEGER NOT NULL,payload_hash TEXT NOT NULL,local_id TEXT NOT NULL,
                customer_id TEXT NOT NULL REFERENCES customers,updated_at TEXT NOT NULL,
                PRIMARY KEY(source,record_type,source_record_id))""",
                """CREATE TABLE IF NOT EXISTS relationship_sync_runs (
                run_id TEXT PRIMARY KEY,source TEXT NOT NULL,status TEXT NOT NULL,records TEXT NOT NULL,
                errors TEXT NOT NULL,summary TEXT NOT NULL,created_at TEXT NOT NULL,created_by TEXT NOT NULL,
                committed_at TEXT,committed_by TEXT)""",
                """CREATE TABLE IF NOT EXISTS relationship_portal_invites (
                invite_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers,
                token_hash TEXT UNIQUE NOT NULL,status TEXT NOT NULL,expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,created_by TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS relationship_onboarding_invites (
                invite_id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,status TEXT NOT NULL,
                expires_at TEXT NOT NULL,created_at TEXT NOT NULL,created_by TEXT NOT NULL,
                onboarding_id TEXT REFERENCES relationship_onboardings)""",
                """CREATE TABLE IF NOT EXISTS relationship_review_evidence (
                review_id TEXT PRIMARY KEY,kind TEXT NOT NULL,target_id TEXT NOT NULL,
                actor TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS relationship_outbox (
                event_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers,version INTEGER NOT NULL,
                event_hash TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,lease_token TEXT,lease_expires_at TEXT,last_error TEXT,sent_at TEXT,
                UNIQUE(customer_id,version))""",
                "CREATE INDEX IF NOT EXISTS relationship_case_customer ON relationship_cases(customer_id,created_at)",
                "CREATE INDEX IF NOT EXISTS relationship_outbox_claim ON relationship_outbox(status,created_at)",
            ]
            for statement in statements:
                con.execute(statement)

    def _auth(self, actor, roles=STAFF_ROLES):
        self.service._authorize(actor, roles)

    def _request(self, con, operation, scope, key, payload):
        key = _key(key)
        existing = con.execute("SELECT payload_hash,response FROM relationship_requests WHERE operation=? AND scope=? AND request_key=?",
                               (operation, scope, key)).fetchone()
        if existing:
            if existing["payload_hash"] != _hash(payload):
                _fail("IDEMPOTENCY_CONFLICT", "This request key belongs to a different payload.")
            return json.loads(existing["response"])
        return None

    def _remember(self, con, operation, scope, key, payload, response):
        con.execute("INSERT INTO relationship_requests VALUES (?,?,?,?,?,?)",
                    (operation, scope, key, _hash(payload), _canonical(response), timestamp()))

    def _profile(self, con, cid, actor=None):
        row = con.execute("SELECT * FROM relationship_profiles WHERE customer_id=?", (cid,)).fetchone()
        if row:
            return dict(row)
        return {"customer_id": cid, "lifecycle_stage": "ACTIVE_RELATIONSHIP" if con.execute(
            "SELECT 1 FROM loans WHERE customer_id=? AND status='ACTIVE'", (cid,)).fetchone() else "PROSPECT",
                "owner": actor.user_id if actor else "meera", "next_followup_at": None,
                "created_at": None, "updated_at": None}

    def _put_profile(self, con, cid, actor):
        previous = self._profile(con, cid, actor)
        active = con.execute("SELECT 1 FROM loans WHERE customer_id=? AND status='ACTIVE'", (cid,)).fetchone()
        next_due = con.execute("SELECT MIN(due_at) FROM relationship_cases WHERE customer_id=? AND status IN ('OPEN','IN_PROGRESS','WAITING_CUSTOMER')", (cid,)).fetchone()[0]
        con.execute("""INSERT INTO relationship_profiles VALUES (?,?,?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET
                       lifecycle_stage=excluded.lifecycle_stage,next_followup_at=excluded.next_followup_at,updated_at=excluded.updated_at""",
                    (cid, "ACTIVE_RELATIONSHIP" if active else "PROSPECT", previous["owner"], next_due,
                     previous["created_at"] or timestamp(), timestamp()))

    def _enqueue(self, con, cid, actor):
        self._put_profile(con, cid, actor)
        version = con.execute("SELECT COALESCE(MAX(version),0)+1 FROM relationship_outbox WHERE customer_id=?", (cid,)).fetchone()[0]
        payload = {**self.service._view(con, cid), "schema_version": 1, "customer_id": cid,
                   "relationship": {**self._profile(con, cid), "cases": self._cases(con, cid)}}
        con.execute("INSERT INTO relationship_outbox(event_id,customer_id,version,event_hash,payload,status,created_at) VALUES (?,?,?,?,?,'PENDING',?)",
                    (str(uuid4()), cid, version, _hash(payload), _canonical(payload), timestamp()))

    def _onboarding(self, con, oid):
        row = con.execute("SELECT * FROM relationship_onboardings WHERE onboarding_id=?", (oid,)).fetchone()
        if not row:
            _fail("ONBOARDING_NOT_FOUND", "The onboarding request does not exist.")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def status(self, actor):
        self._auth(actor)
        with self.service._db() as con:
            return {"storage": "Private local SQLite operational database", "public_snapshot_write_enabled": False,
                    "customers": con.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                    "pending_onboardings": con.execute("SELECT COUNT(*) FROM relationship_onboardings WHERE status='PENDING_REVIEW'").fetchone()[0],
                    "open_cases": con.execute("SELECT COUNT(*) FROM relationship_cases WHERE status IN ('OPEN','IN_PROGRESS','WAITING_CUSTOMER')").fetchone()[0],
                    "sync_runs": con.execute("SELECT COUNT(*) FROM relationship_sync_runs").fetchone()[0],
                    "pending_exports": con.execute("SELECT COUNT(*) FROM relationship_outbox WHERE status!='SENT'").fetchone()[0],
                    "kyc_verified": False, "automatic_external_sync_enabled": False}

    def list_onboardings(self, actor):
        self._auth(actor)
        with self.service._db() as con:
            return [self._onboarding(con, r[0]) for r in con.execute(
                "SELECT onboarding_id FROM relationship_onboardings ORDER BY created_at DESC LIMIT 500").fetchall()]

    def _onboarding_payload(self, payload):
        normalized = normalize_customer(payload)
        normalized.update(identity_review=_boolean(payload.get("identity_review", False), "identity_review"),
                          document_review=_boolean(payload.get("document_review", payload.get("document_review_attested", False)), "document_review"),
                          consent_reference=_text(payload.get("consent_reference", ""), "consent_reference", 500))
        if (normalized["consent_calls"] or normalized["consent_marketing"]) and not normalized["consent_reference"]:
            _fail("CONSENT_REFERENCE_REQUIRED", "Record the permission reference before enabling contact preferences.")
        return normalized

    def _create_onboarding(self, con, normalized, actor, submitted_by=None):
        oid = str(uuid4())
        con.execute("INSERT INTO relationship_onboardings(onboarding_id,payload,status,submitted_by,created_at) VALUES (?,?,'PENDING_REVIEW',?,?)",
                    (oid, _canonical(normalized), submitted_by or actor.user_id, timestamp()))
        self.service._log(con, "ONBOARDING_SUBMITTED", actor=submitted_by or actor.user_id, detail={"onboarding_id": oid})
        return self._onboarding(con, oid)

    def submit_onboarding(self, payload, actor, idempotency_key):
        self._auth(actor, INTAKE_ROLES)
        normalized = self._onboarding_payload(payload)
        with self.service._db(write=True) as con:
            prior = self._request(con, "onboarding", actor.user_id, idempotency_key, normalized)
            if prior:
                return self._onboarding(con, prior["onboarding_id"])
            result = self._create_onboarding(con, normalized, actor)
            self._remember(con, "onboarding", actor.user_id, idempotency_key, normalized, {"onboarding_id": result["onboarding_id"]})
            return result

    def review_onboarding(self, onboarding_id, decision, note, actor):
        self._auth(actor, {"MANAGER", "ADMIN"})
        if not isinstance(decision, str) or decision not in {"APPROVE", "REJECT"}:
            _fail("INVALID_DECISION", "Choose APPROVE or REJECT.")
        note = _text(note, "review_note", 1000, required=True)
        with self.service._db(write=True) as con:
            row = self._onboarding(con, onboarding_id)
            target = "APPROVED" if decision == "APPROVE" else "REJECTED"
            if row["status"] == target:
                return row
            if row["status"] != "PENDING_REVIEW":
                _fail("INVALID_STATE", "Only a pending onboarding can be reviewed.")
            if actor.user_id == row["submitted_by"] and actor.role != "ADMIN":
                _fail("REVIEWER_SEPARATION", "A separate reviewer must decide this onboarding.")
            cid = None
            if decision == "APPROVE":
                payload = row["payload"]
                if not payload["identity_review"] or not payload["document_review"]:
                    _fail("REVIEW_CHECKLIST_REQUIRED", "Record identity and document review attestations before approval; this is not automated KYC.")
                if con.execute("SELECT 1 FROM customers WHERE (?!='' AND phone=?) OR (?!='' AND lower(email)=?)",
                               (payload["phone"], payload["phone"], payload["email"], payload["email"])).fetchone():
                    _fail("DUPLICATE_CONTACT", "That contact is already linked to a customer; review the existing relationship instead.")
                cid = "CRM" + uuid4().hex[:20].upper()
                self._insert_customer(con, cid, payload)
                self._enqueue(con, cid, actor)
            con.execute("UPDATE relationship_onboardings SET status=?,reviewed_by=?,reviewed_at=?,review_note=?,customer_id=? WHERE onboarding_id=?",
                        (target, actor.user_id, timestamp(), note, cid, onboarding_id))
            self.service._log(con, "ONBOARDING_" + target, cid, actor=actor.user_id,
                              detail={"onboarding_id": onboarding_id, "document_review_attestation": decision == "APPROVE", "real_kyc_performed": False})
            return self._onboarding(con, onboarding_id)

    def _insert_customer(self, con, cid, payload):
        con.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (cid, payload["full_name"], payload["city"], payload["segment"], payload["monthly_income"],
                     payload["preferred_language"], payload["phone"], payload["email"], int(payload["consent_calls"]),
                     int(payload["consent_marketing"]), int(payload["dnd"])))

    def _cases(self, con, cid):
        return [dict(r) for r in con.execute("SELECT * FROM relationship_cases WHERE customer_id=? ORDER BY created_at DESC LIMIT 500", (cid,))]

    def customer_relationship(self, customer_id, actor):
        self._auth(actor)
        with self.service._db() as con:
            return {"customer360": self.service._view(con, customer_id), "relationship": self._profile(con, customer_id, actor),
                    "cases": self._cases(con, customer_id), "sources": [dict(r) for r in con.execute(
                        "SELECT source,record_type,source_record_id,source_version,updated_at FROM relationship_sources WHERE customer_id=?", (customer_id,))]}

    def _create_case(self, con, cid, normalized, actor, created_by=None):
        self.service._customer(con, cid)
        case_id = str(uuid4())
        now = timestamp()
        con.execute("INSERT INTO relationship_cases VALUES (?,?,?,?,?,?,'OPEN',?,?,?,?,?,NULL)",
                    (case_id, cid, normalized["category"], normalized["priority"], normalized["subject"], normalized["description"],
                     normalized["owner"], normalized["due_at"], now, now, created_by or actor.user_id))
        self.service._log(con, "RELATIONSHIP_CASE_OPENED", cid, actor=created_by or actor.user_id,
                          detail={"case_id": case_id, "category": normalized["category"], "priority": normalized["priority"]})
        if normalized["category"] in {"HARDSHIP", "COMPLAINT"}:
            iid = "CRM-CASE-" + case_id
            # Preserve actual inbound text. A selected support category is an
            # explicit human classification, never an invented job-loss fact.
            self.service._insert_interaction(con, iid, cid, "COMPLAINT",
                                             normalized["subject"] + "\n" + normalized["description"], ts=now)
            evidence = con.execute("SELECT intent,entities FROM interactions WHERE interaction_id=?", (iid,)).fetchone()
            entities = json.loads(evidence["entities"])
            entities.update(case_id=case_id, case_category=normalized["category"],
                            classification_source="customer-selected case" if created_by == "customer-portal" else "staff-entered case")
            intent = "financial hardship" if normalized["category"] == "HARDSHIP" else (
                "complaint about service or rate" if evidence["intent"] == "general query" else evidence["intent"])
            con.execute("UPDATE interactions SET intent=?,entities=?,extraction_version=? WHERE interaction_id=?",
                        (intent, _canonical(entities), "relationship-case-v1", iid))
            self._invalidate(con, cid, actor, require_review=True)
            self.service._log(con, "RELATIONSHIP_CASE_EVIDENCE_RECORDED", cid, actor=created_by or actor.user_id,
                              detail={"case_id": case_id, "interaction_id": iid, "new_approval_required": True})
        self._enqueue(con, cid, actor)
        return dict(con.execute("SELECT * FROM relationship_cases WHERE case_id=?", (case_id,)).fetchone())

    def add_case(self, customer_id, payload, actor, idempotency_key):
        self._auth(actor)
        normalized = _case_payload(payload, actor)
        scope = actor.user_id + ":" + customer_id
        with self.service._db(write=True) as con:
            previous = self._request(con, "case", scope, idempotency_key, normalized)
            if previous:
                return dict(con.execute("SELECT * FROM relationship_cases WHERE case_id=?", (previous["case_id"],)).fetchone())
            result = self._create_case(con, customer_id, normalized, actor)
            self._remember(con, "case", scope, idempotency_key, normalized, {"case_id": result["case_id"]})
            return result

    def update_case(self, case_id, status, note, actor):
        self._auth(actor)
        if not isinstance(status, str) or status not in CASE_STATUSES:
            _fail("INVALID_CASE_STATUS", "Choose a supported case status.")
        note = _text(note, "case_note", 1000, required=True)
        with self.service._db(write=True) as con:
            row = con.execute("SELECT * FROM relationship_cases WHERE case_id=?", (case_id,)).fetchone()
            if not row:
                _fail("CASE_NOT_FOUND", "The relationship case does not exist.")
            if row["status"] == "CLOSED" and (status != "CLOSED" or row["resolution_note"] != note):
                _fail("INVALID_STATE", "A closed case is immutable; create a follow-up case.")
            if row["status"] == status and row["resolution_note"] == note:
                return dict(row)
            if status == "CLOSED" and row["status"] not in {"RESOLVED", "CLOSED"}:
                _fail("INVALID_STATE", "Resolve a case before closing it.")
            con.execute("UPDATE relationship_cases SET status=?,resolution_note=?,updated_at=? WHERE case_id=?",
                        (status, note, timestamp(), case_id))
            self.service._log(con, "RELATIONSHIP_CASE_UPDATED", row["customer_id"], actor=actor.user_id,
                              detail={"case_id": case_id, "status": status})
            self._enqueue(con, row["customer_id"], actor)
            return dict(con.execute("SELECT * FROM relationship_cases WHERE case_id=?", (case_id,)).fetchone())

    def _source(self, source):
        source = _text(source, "source", 32, required=True).lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", source):
            _fail("INVALID_SOURCE", "Use a source name starting with a letter and containing letters, digits, underscores, or hyphens.")
        return source

    def link_source_customer(self, source, source_record_id, customer_id, actor, idempotency_key, note):
        """Record a reviewed cross-system identity binding, never a fuzzy merge."""
        self._auth(actor, {"MANAGER", "ADMIN"})
        source = self._source(source)
        source_record_id = _text(source_record_id, "source_record_id", 120, required=True)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", source_record_id):
            _fail("INVALID_SOURCE_ID", "Use a valid source customer reference.")
        note = _text(note, "mapping_review_note", 1000, required=True)
        request = {"source": source, "source_record_id": source_record_id, "customer_id": customer_id, "review_note": note}
        with self.service._db(write=True) as con:
            self.service._customer(con, customer_id)
            previous = self._request(con, "source-link", actor.user_id, idempotency_key, request)
            if previous:
                return previous
            existing = con.execute("SELECT * FROM relationship_sources WHERE source=? AND record_type='customer' AND source_record_id=?", (source, source_record_id)).fetchone()
            if existing and existing["customer_id"] != customer_id:
                _fail("SOURCE_OWNERSHIP_CONFLICT", "That source identity is already linked to another customer.")
            duplicate = con.execute("SELECT 1 FROM relationship_sources WHERE source=? AND record_type='customer' AND customer_id=? AND source_record_id!=?", (source, customer_id, source_record_id)).fetchone()
            if duplicate:
                _fail("SOURCE_IDENTITY_CONFLICT", "A customer already has another identity in this source; aliases require separate reconciliation.")
            if not existing:
                con.execute("INSERT INTO relationship_sources VALUES (?,'customer',?,0,?,?,?,?)", (source, source_record_id, _hash({"reviewed_mapping": customer_id}), customer_id, customer_id, timestamp()))
            result = {"source": source, "source_record_id": source_record_id, "customer_id": customer_id, "source_version": existing["source_version"] if existing else 0, "reviewed_binding": True}
            self._remember(con, "source-link", actor.user_id, idempotency_key, request, result)
            con.execute("INSERT INTO relationship_review_evidence VALUES (?, 'SOURCE_IDENTITY_LINK',?,?,?,?)",
                        (str(uuid4()), source + ":" + source_record_id, actor.user_id, note, timestamp()))
            self.service._log(con, "RELATIONSHIP_SOURCE_IDENTITY_LINKED", customer_id, actor=actor.user_id,
                              detail={"source": source, "source_record_id_hash": hashlib.sha256(source_record_id.encode()).hexdigest()})
            self._enqueue(con, customer_id, actor)
            return result

    def _sync_check(self, con, source, rows, row_numbers=None):
        errors, summary = [], {"insert": 0, "update": 0, "unchanged": 0, "records": len(rows),
                               "imported_contact_opt_in_granted": False}
        identities = {(r["record_type"], r["source_record_id"]): r for r in rows}
        contacts = {"phone": set(), "email": set()}
        if len(identities) != len(rows):
            errors.append({"row": 0, "code": "DUPLICATE_SOURCE_ROW", "message": "A source record occurs more than once in this batch."})
        for position, record in enumerate(rows):
            index = row_numbers[position] if row_numbers is not None else position + 1
            existing = con.execute("SELECT * FROM relationship_sources WHERE source=? AND record_type=? AND source_record_id=?",
                                   (source, record["record_type"], record["source_record_id"])).fetchone()
            if existing:
                if record["source_version"] < existing["source_version"]:
                    errors.append({"row": index, "code": "STALE_SOURCE_VERSION", "message": "This record is older than the committed source version."})
                elif record["source_version"] == existing["source_version"] and _hash(record) != existing["payload_hash"]:
                    errors.append({"row": index, "code": "SOURCE_VERSION_CONFLICT", "message": "The same source version already has different content."})
                elif record["source_version"] == existing["source_version"]:
                    summary["unchanged"] += 1
                else:
                    summary["update"] += 1
            else:
                summary["insert"] += 1
            kind = record["record_type"]
            if kind == "customer":
                own_id = existing["local_id"] if existing else ""
                if existing and existing["source_version"] == 0:
                    current = self.service._customer(con, own_id)
                    if any(record[field] and current[field] and record[field] != current[field] for field in ("phone", "email")):
                        errors.append({"row": index, "code": "SOURCE_CONTACT_BINDING_CONFLICT", "message": "A reviewed customer mapping has different contact details; reconcile identity before importing."})
                duplicate = con.execute("SELECT 1 FROM customers WHERE customer_id!=? AND ((?!='' AND phone=?) OR (?!='' AND lower(email)=?))",
                                        (own_id, record["phone"], record["phone"], record["email"], record["email"])).fetchone()
                if duplicate or any(record[field] and record[field] in contacts[field] for field in contacts):
                    errors.append({"row": index, "code": "DUPLICATE_CONTACT", "message": "A customer contact is already in use; resolve identity mapping before import."})
                for field in contacts:
                    if record[field]:
                        contacts[field].add(record[field])
                continue
            ref_kind, ref_value = ("loan", record["loan_ref"]) if kind == "payment" else ("customer", record["customer_ref"])
            reference = con.execute("SELECT local_id,customer_id FROM relationship_sources WHERE source=? AND record_type=? AND source_record_id=?",
                                    (source, ref_kind, ref_value)).fetchone()
            if not reference and (ref_kind, ref_value) not in identities:
                errors.append({"row": index, "code": "MISSING_REFERENCE", "message": "A required customer or loan reference is absent from this source and batch."})
            elif existing:
                expected = reference["customer_id"] if reference else self._local_id(source, "customer", ref_value)
                if kind == "payment" and not reference:
                    loan_record = identities[("loan", ref_value)]
                    customer_mapping = con.execute("SELECT local_id FROM relationship_sources WHERE source=? AND record_type='customer' AND source_record_id=?",
                                                   (source, loan_record["customer_ref"])).fetchone()
                    expected = customer_mapping[0] if customer_mapping else self._local_id(source, "customer", loan_record["customer_ref"])
                if existing["customer_id"] != expected:
                    errors.append({"row": index, "code": "SOURCE_OWNERSHIP_CONFLICT", "message": "A committed source record cannot move to another customer."})
                elif kind == "payment" and reference:
                    bound_loan = con.execute("SELECT loan_id FROM payments WHERE payment_id=?", (existing["local_id"],)).fetchone()
                    if bound_loan and bound_loan[0] != reference["local_id"]:
                        errors.append({"row": index, "code": "SOURCE_OWNERSHIP_CONFLICT", "message": "A committed payment cannot move to another loan."})
        return errors, summary

    @staticmethod
    def _local_id(source, kind, record_id):
        prefix = {"customer": "CRM", "loan": "CRM-L-", "payment": "CRM-P-", "interaction": "CRM-I-"}[kind]
        return prefix + uuid5(NAMESPACE_URL, f"samvaad360:{source}:{kind}:{record_id}").hex.upper()

    def _run(self, con, run_id, include_records=False):
        row = con.execute("SELECT * FROM relationship_sync_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            _fail("SYNC_RUN_NOT_FOUND", "The synchronization run does not exist.")
        result = dict(row)
        for key in ("errors", "summary"):
            result[key] = json.loads(result[key])
        if include_records:
            result["records"] = json.loads(result["records"])
        else:
            result.pop("records")
        return result

    def preview_sync(self, source, records, actor, idempotency_key):
        self._auth(actor, INTAKE_ROLES)
        source = self._source(source)
        if not isinstance(records, list) or not 1 <= len(records) <= 200:
            _fail("INVALID_BATCH", "Provide a batch of 1-200 records.")
        # Bound serialized input before persistence; never accept arbitrary metadata.
        try:
            if len(_canonical(records).encode("utf-8")) > 2_000_000:
                _fail("INVALID_BATCH", "The batch exceeds the two-megabyte limit.")
        except (ValueError, TypeError):
            _fail("INVALID_BATCH", "The batch must contain finite JSON values.")
        normalized, errors, row_numbers = [], [], []
        for index, record in enumerate(records, 1):
            try:
                normalized.append(normalize_sync_record(record))
                row_numbers.append(index)
            except ActionError as error:
                errors.append({"row": index, "code": error.code, "message": error.message})
        request = {"source": source, "records": records}
        with self.service._db(write=True) as con:
            previous = self._request(con, "sync-preview", actor.user_id, idempotency_key, request)
            if previous:
                return self._run(con, previous["run_id"])
            relation_errors, summary = self._sync_check(con, source, normalized, row_numbers)
            errors.extend(relation_errors)
            summary["records"] = len(records)
            run_id = str(uuid4())
            con.execute("INSERT INTO relationship_sync_runs VALUES (?,?,?,?,?,?,?,?,NULL,NULL)",
                        (run_id, source, "INVALID" if errors else "VALIDATED", _canonical(normalized), _canonical(errors),
                         _canonical(summary), timestamp(), actor.user_id))
            self._remember(con, "sync-preview", actor.user_id, idempotency_key, request, {"run_id": run_id})
            self.service._log(con, "RELATIONSHIP_SYNC_PREVIEW", actor=actor.user_id,
                              detail={"run_id": run_id, "source": source, "record_count": len(records), "error_count": len(errors)})
            return self._run(con, run_id)

    def list_sync_runs(self, actor):
        self._auth(actor)
        with self.service._db() as con:
            return [self._run(con, r[0]) for r in con.execute("SELECT run_id FROM relationship_sync_runs ORDER BY created_at DESC LIMIT 100").fetchall()]

    def sync_run(self, run_id, actor):
        self._auth(actor)
        with self.service._db() as con:
            return self._run(con, run_id)

    def _invalidate(self, con, cid, actor, require_review=False):
        con.execute("UPDATE actions SET status='CANCELLED',outcome='EVIDENCE_CHANGED' WHERE customer_id=? AND status IN ('PENDING_APPROVAL','APPROVED')", (cid,))
        con.execute("UPDATE offers SET status='REVOKED' WHERE customer_id=? AND status NOT IN ('ACCEPTED','DECLINED','REVOKED')", (cid,))
        self.service._log(con, "RELATIONSHIP_EVIDENCE_CHANGED", cid, actor=actor.user_id, detail={"fresh_approval_required": True})
        require_review = require_review or bool(con.execute("SELECT 1 FROM relationship_cases WHERE customer_id=? AND category IN ('HARDSHIP','COMPLAINT') AND status IN ('OPEN','IN_PROGRESS','WAITING_CUSTOMER')", (cid,)).fetchone())
        decision = self.service._view(con, cid)["current_decision"]
        if decision["action_code"] != "NO_ACTION":
            # _queue reuses recent unchanged terms even when evidence changed.
            # Persist a new decision after invalidation so its approval is fresh.
            aid, now = str(uuid4()), timestamp()
            automatic = decision["approval_role"] == "AUTO" and not require_review
            status = "APPROVED" if automatic else "PENDING_APPROVAL"
            approval_role = "MANAGER" if require_review and decision["approval_role"] == "AUTO" else decision["approval_role"]
            con.execute("""INSERT INTO actions(action_id,customer_id,action_code,channel,approval_role,offer,rationale,
                evidence_ids,reason_codes,script,status,created_at,catalogue_version,approved_by,approved_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (aid, cid, decision["action_code"], decision["channel"], approval_role,
                         _canonical(decision["offer"]), decision["rationale"], _canonical(decision["evidence_ids"]),
                         _canonical(decision["reason_codes"]), decision["script"], status, now, decision["catalogue_version"],
                         "service-policy" if status == "APPROVED" else None, now if status == "APPROVED" else None))
            self.service._log(con, "NBA_QUEUED", cid, aid, actor.user_id,
                              {"action": decision["action_code"], "status": status, "fresh_evidence_approval": True})

    def _revoke(self, con, cid, actor):
        self.service._revoke(con, cid, actor)
        con.execute("UPDATE offers SET status='REVOKED' WHERE customer_id=? AND status NOT IN ('ACCEPTED','DECLINED')", (cid,))
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='telephony_recipients'").fetchone():
            con.execute("UPDATE telephony_recipients SET status='REVOKED' WHERE customer_id=?", (cid,))

    def commit_sync(self, run_id, actor):
        self._auth(actor, INTAKE_ROLES)
        with self.service._db(write=True) as con:
            run = self._run(con, run_id, include_records=True)
            if run["status"] == "COMMITTED":
                return self._run(con, run_id)
            if run["status"] != "VALIDATED":
                _fail("SYNC_VALIDATION_REQUIRED", "Correct invalid rows and create a new validated preview before committing.")
            errors, summary = self._sync_check(con, run["source"], run["records"])
            if errors:
                _fail("SYNC_CHANGED_SINCE_PREVIEW", "Committed source versions changed after preview; create a new preview.")
            affected = set()
            for record in sorted(run["records"], key=lambda r: ("customer", "loan", "payment", "interaction").index(r["record_type"])):
                existing = con.execute("SELECT * FROM relationship_sources WHERE source=? AND record_type=? AND source_record_id=?",
                                       (run["source"], record["record_type"], record["source_record_id"])).fetchone()
                if existing and record["source_version"] == existing["source_version"]:
                    continue
                cid, local_id = self._apply_record(con, run["source"], record, existing, actor)
                con.execute("""INSERT INTO relationship_sources VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(source,record_type,source_record_id) DO UPDATE SET source_version=excluded.source_version,
                    payload_hash=excluded.payload_hash,updated_at=excluded.updated_at""",
                            (run["source"], record["record_type"], record["source_record_id"], record["source_version"],
                             _hash(record), local_id, cid, timestamp()))
                affected.add(cid)
            for cid in affected:
                self._invalidate(con, cid, actor)
                self._enqueue(con, cid, actor)
            summary.update(affected_customers=len(affected))
            con.execute("UPDATE relationship_sync_runs SET status='COMMITTED',summary=?,committed_at=?,committed_by=? WHERE run_id=?",
                        (_canonical(summary), timestamp(), actor.user_id, run_id))
            self.service._log(con, "RELATIONSHIP_SYNC_COMMITTED", actor=actor.user_id,
                              detail={"run_id": run_id, "source": run["source"], "affected_customers": len(affected)})
            return self._run(con, run_id)

    def _apply_record(self, con, source, row, existing, actor):
        kind = row["record_type"]
        local_id = existing["local_id"] if existing else self._local_id(source, kind, row["source_record_id"])
        if kind == "customer":
            cid = local_id
            data = {k: row[k] for k in CUSTOMER_FIELDS}
            if existing:
                current = self.service._customer(con, cid)
                data["consent_calls"] = bool(current["consent_calls"] and data["consent_calls"])
                data["consent_marketing"] = bool(current["consent_marketing"] and data["consent_marketing"])
                data["dnd"] = bool(current["dnd"] or data["dnd"])
                if current["phone"] != data["phone"]:
                    data["consent_calls"] = False
                if current["phone"] != data["phone"] or current["email"] != data["email"]:
                    data["consent_marketing"] = False
                if data["dnd"] or not data["consent_calls"]:
                    self._revoke(con, cid, actor)
                    data["consent_calls"] = data["consent_marketing"] = False
                if current["phone"] != data["phone"] and con.execute("SELECT 1 FROM sqlite_master WHERE name='telephony_recipients'").fetchone():
                    con.execute("UPDATE telephony_recipients SET status='REVOKED' WHERE customer_id=?", (cid,))
                values = [data[k] for k in ("full_name", "city", "segment", "monthly_income", "preferred_language", "phone", "email", "consent_calls", "consent_marketing", "dnd")]
                con.execute("UPDATE customers SET full_name=?,city=?,segment=?,monthly_income=?,preferred_language=?,phone=?,email=?,consent_calls=?,consent_marketing=?,dnd=? WHERE customer_id=?", (*values, cid))
            else:
                if con.execute("SELECT 1 FROM customers WHERE (?!='' AND phone=?) OR (?!='' AND lower(email)=?)",
                               (data["phone"], data["phone"], data["email"], data["email"])).fetchone():
                    _fail("DUPLICATE_CONTACT", "A source customer contact already exists; resolve identity mapping before import.")
                # Contact permission in a source file is not verified opt-in.
                # New source relationships start suppressed until reviewed intake.
                data["consent_calls"] = data["consent_marketing"] = False
                self._insert_customer(con, cid, data)
        elif kind == "loan":
            reference = con.execute("SELECT local_id FROM relationship_sources WHERE source=? AND record_type='customer' AND source_record_id=?", (source, row["customer_ref"])).fetchone()
            if not reference:
                _fail("MISSING_REFERENCE", "A source customer reference could not be resolved.")
            cid = reference[0]
            values = (local_id, cid, row["product"], row["principal"], row["outstanding"], row["interest_rate"], row["emi"], row["relationship_months"], row["current_dpd"], row["status"], row["disbursed_on"])
            con.execute("""INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(loan_id) DO UPDATE SET
                product=excluded.product,principal=excluded.principal,outstanding=excluded.outstanding,interest_rate=excluded.interest_rate,
                emi=excluded.emi,relationship_months=excluded.relationship_months,current_dpd=excluded.current_dpd,status=excluded.status,
                disbursed_on=excluded.disbursed_on""", values)
        elif kind == "payment":
            reference = con.execute("SELECT local_id,customer_id FROM relationship_sources WHERE source=? AND record_type='loan' AND source_record_id=?", (source, row["loan_ref"])).fetchone()
            if not reference:
                _fail("MISSING_REFERENCE", "A source loan reference could not be resolved.")
            cid = reference["customer_id"]
            if existing:
                previous_loan = con.execute("SELECT loan_id FROM payments WHERE payment_id=?", (local_id,)).fetchone()[0]
                if previous_loan != reference["local_id"]:
                    _fail("SOURCE_OWNERSHIP_CONFLICT", "An existing payment cannot move to another loan.")
            con.execute("""INSERT INTO payments VALUES (?,?,?,?,?,?,?) ON CONFLICT(payment_id) DO UPDATE SET
                due_date=excluded.due_date,paid_date=excluded.paid_date,amount_due=excluded.amount_due,amount_paid=excluded.amount_paid,status=excluded.status""",
                        (local_id, reference["local_id"], row["due_date"], row["paid_date"], row["amount_due"], row["amount_paid"], row["status"]))
        else:
            reference = con.execute("SELECT local_id FROM relationship_sources WHERE source=? AND record_type='customer' AND source_record_id=?", (source, row["customer_ref"])).fetchone()
            if not reference:
                _fail("MISSING_REFERENCE", "A source customer reference could not be resolved.")
            cid = reference[0]
            if existing:
                con.execute("DELETE FROM interactions WHERE interaction_id=?", (local_id,))
            self.service._insert_interaction(con, local_id, cid, row["channel"], row["text"], simulated=False, ts=row["ts"])
        return cid, local_id

    def issue_portal_invite(self, customer_id, actor, idempotency_key):
        self._auth(actor)
        with self.service._db(write=True) as con:
            self.service._customer(con, customer_id)
            prior = self._request(con, "portal-invite", actor.user_id, idempotency_key, {"customer_id": customer_id})
            if prior:
                return {**prior, "token": None, "replayed": True, "message": "For security the original link token is shown only when created; issue a new invitation if needed."}
            since = timestamp(utcnow() - timedelta(days=1))
            if con.execute("SELECT COUNT(*) FROM relationship_portal_invites WHERE customer_id=? AND created_at>=?", (customer_id, since)).fetchone()[0] >= 5:
                _fail("INVITE_RATE_LIMIT", "At most five portal invitations per customer per day are permitted.")
            con.execute("UPDATE relationship_portal_invites SET status='REVOKED' WHERE customer_id=? AND status='ACTIVE'", (customer_id,))
            token = secrets.token_urlsafe(32)
            invite_id, expires = str(uuid4()), timestamp(utcnow() + timedelta(hours=24))
            con.execute("INSERT INTO relationship_portal_invites VALUES (?,?,?,'ACTIVE',?,?,?)",
                        (invite_id, customer_id, hashlib.sha256(token.encode()).hexdigest(), expires, timestamp(), actor.user_id))
            result = {"invite_id": invite_id, "customer_id": customer_id, "expires_at": expires, "purpose": "CUSTOMER"}
            self._remember(con, "portal-invite", actor.user_id, idempotency_key, {"customer_id": customer_id}, result)
            self.service._log(con, "RELATIONSHIP_PORTAL_INVITE_CREATED", customer_id, actor=actor.user_id,
                              detail={"invite_id": invite_id, "expires_at": expires, "identity_verified": False})
            return {**result, "token": token, "replayed": False}

    def issue_onboarding_invite(self, actor, idempotency_key):
        self._auth(actor, INTAKE_ROLES)
        with self.service._db(write=True) as con:
            prior = self._request(con, "onboarding-invite", actor.user_id, idempotency_key, {})
            if prior:
                return {**prior, "token": None, "replayed": True}
            since = timestamp(utcnow() - timedelta(days=1))
            if con.execute("SELECT COUNT(*) FROM relationship_onboarding_invites WHERE created_by=? AND created_at>=?", (actor.user_id, since)).fetchone()[0] >= 50:
                _fail("INVITE_RATE_LIMIT", "At most fifty applicant invitations per staff operator per day are permitted.")
            token = secrets.token_urlsafe(32)
            invite_id, expires = str(uuid4()), timestamp(utcnow() + timedelta(hours=24))
            con.execute("INSERT INTO relationship_onboarding_invites VALUES (?,?,'ACTIVE',?,?,?,NULL)",
                        (invite_id, hashlib.sha256(token.encode()).hexdigest(), expires, timestamp(), actor.user_id))
            result = {"invite_id": invite_id, "customer_id": None, "expires_at": expires, "purpose": "ONBOARDING"}
            self._remember(con, "onboarding-invite", actor.user_id, idempotency_key, {}, result)
            self.service._log(con, "RELATIONSHIP_APPLICANT_INVITE_CREATED", actor=actor.user_id, detail={"invite_id": invite_id, "expires_at": expires})
            return {**result, "token": token, "replayed": False}

    def _portal(self, con, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", token):
            _fail("PORTAL_UNAVAILABLE", "This service link is unavailable or expired.")
        row = con.execute("SELECT * FROM relationship_portal_invites WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        purpose = "CUSTOMER"
        if not row:
            row = con.execute("SELECT * FROM relationship_onboarding_invites WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            purpose = "ONBOARDING"
        if not row or row["status"] != "ACTIVE" or datetime.fromisoformat(row["expires_at"]) <= utcnow():
            _fail("PORTAL_UNAVAILABLE", "This service link is unavailable or expired.")
        return {**dict(row), "purpose": purpose}

    def _portal_view(self, con, invite):
        if invite["purpose"] == "ONBOARDING":
            application = self._onboarding(con, invite["onboarding_id"]) if invite["onboarding_id"] else None
            return {"purpose": "ONBOARDING", "customer_id": application["customer_id"] if application else None,
                    "onboarding_id": invite["onboarding_id"], "application_status": application["status"] if application else "NOT_SUBMITTED",
                    "given_name": application["payload"]["full_name"].split()[0] if application else None,
                    "expires_at": invite["expires_at"], "identity_verified": False, "financial_edits_enabled": False}
        customer = self.service._customer(con, invite["customer_id"])
        phone, email = customer["phone"] or "", customer["email"] or ""
        return {"purpose": "CUSTOMER", "customer_id": invite["customer_id"], "given_name": customer["full_name"].split()[0],
                "full_name": customer["full_name"], "city": customer["city"], "language": customer["preferred_language"],
                "contact": {"phone_masked": "••••" + phone[-4:] if phone else "Not recorded",
                            "email_masked": email[:1] + "•••@" + email.split("@")[-1] if email else "Not recorded",
                            "preferred_language": customer["preferred_language"], "consent_calls": customer["consent_calls"],
                            "consent_marketing": customer["consent_marketing"], "dnd": customer["dnd"]},
                "cases": [{k: case[k] for k in ("case_id", "category", "subject", "status", "created_at", "updated_at")} for case in self._cases(con, invite["customer_id"])],
                "expires_at": invite["expires_at"], "financial_edits_enabled": False, "identity_verified": False}

    def portal_view(self, token):
        with self.service._db() as con:
            return self._portal_view(con, self._portal(con, token))

    def portal_submit(self, token, payload, idempotency_key):
        if isinstance(payload, dict) and payload.get("request_type") == "APPLY":
            return self._portal_apply(token, payload, idempotency_key)
        _mapping(payload, {"request_type", "category", "subject", "description", "consent_calls", "consent_marketing", "dnd", "preferred_language"})
        kind = payload.get("request_type")
        if not isinstance(kind, str) or kind not in {"CASE", "CONTACT_PREFERENCES", "OPT_OUT"}:
            _fail("INVALID_PORTAL_REQUEST", "Choose a service request, preference reduction, or opt-out.")
        if kind == "CASE" and not payload.keys() <= {"request_type", "category", "subject", "description"}:
            _fail("INVALID_PORTAL_REQUEST", "A service request cannot also edit contact preferences.")
        if kind == "OPT_OUT" and payload.keys() != {"request_type"}:
            _fail("INVALID_PORTAL_REQUEST", "Opt-out does not accept additional fields.")
        if kind == "CONTACT_PREFERENCES" and not payload.keys() <= {"request_type", "consent_calls", "consent_marketing", "dnd", "preferred_language"}:
            _fail("INVALID_PORTAL_REQUEST", "A preference request cannot contain service-case fields.")
        actor = DEMO_ACTORS["meera"]
        with self.service._db(write=True) as con:
            invite = self._portal(con, token)
            if invite["purpose"] != "CUSTOMER":
                _fail("PORTAL_SCOPE_REQUIRED", "This invitation permits applicant intake only.")
            previous = self._request(con, "portal-submit", invite["invite_id"], idempotency_key, payload)
            if previous:
                return {**previous, "replayed": True}
            cid = invite["customer_id"]
            case_requests = sum(json.loads(r[0]).get("request_type") == "CASE" for r in con.execute(
                "SELECT response FROM relationship_requests WHERE operation='portal-submit' AND scope=?", (invite["invite_id"],)))
            if kind == "CASE" and case_requests >= 20:
                _fail("PORTAL_REQUEST_LIMIT", "This service link has reached its request limit; contact your officer.")
            if kind == "CASE":
                normalized = _case_payload({k: v for k, v in payload.items() if k != "request_type"}, actor)
                result = {"request_type": kind, "case": self._create_case(con, cid, normalized, actor, created_by="customer-portal")}
                result["case"] = {k: result["case"][k] for k in ("case_id", "category", "status", "subject", "created_at")}
            else:
                current = self.service._customer(con, cid)
                changed = False
                if kind == "CONTACT_PREFERENCES":
                    for key in ("consent_calls", "consent_marketing", "dnd"):
                        if key in payload:
                            value = _boolean(payload[key], key)
                            if key == "dnd" and current[key] and not value or key != "dnd" and value and not current[key]:
                                _fail("CONSENT_REACTIVATION_BLOCKED", "Re-enabling contact needs a separately verified consent workflow.")
                    language = payload.get("preferred_language", current["preferred_language"])
                    if "preferred_language" in payload and (not isinstance(language, str) or language not in LANGUAGES):
                        _fail("INVALID_FIELD", "Choose a supported language.")
                    calls = payload.get("consent_calls", current["consent_calls"])
                    marketing = payload.get("consent_marketing", current["consent_marketing"])
                    dnd = payload.get("dnd", current["dnd"])
                    if dnd:
                        calls = marketing = False
                    if not calls or dnd:
                        marketing = False
                    changed = (calls, marketing, dnd, language) != (current["consent_calls"], current["consent_marketing"], current["dnd"], current["preferred_language"])
                    if changed:
                        con.execute("UPDATE customers SET consent_calls=?,consent_marketing=?,dnd=?,preferred_language=? WHERE customer_id=?", (calls, marketing, dnd, language, cid))
                        if not calls or dnd:
                            self._revoke(con, cid, actor)
                        elif not marketing:
                            con.execute("UPDATE actions SET status='CANCELLED' WHERE customer_id=? AND action_code='TOPUP_PREAPPROVAL_CALL' AND status IN ('PENDING_APPROVAL','APPROVED')", (cid,))
                            con.execute("UPDATE offers SET status='REVOKED' WHERE customer_id=? AND offer_type='TOPUP' AND status NOT IN ('ACCEPTED','DECLINED')", (cid,))
                else:
                    changed = bool(current["consent_calls"] or current["consent_marketing"])
                    if changed:
                        self._revoke(con, cid, actor)
                if changed:
                    self._enqueue(con, cid, actor)
                    self.service._log(con, "RELATIONSHIP_PORTAL_PREFERENCES", cid, actor="customer-portal", detail={"request_type": kind})
                result = {"request_type": kind, "contact": self._portal_view(con, invite)["contact"]}
                if not changed:
                    # An unchanged withdrawal is a read-only acknowledgement.
                    # Preserve bindings for actual writes while fresh no-op
                    # keys cannot grow the durable request table indefinitely.
                    return {**result, "replayed": False, "unchanged": True}
            self._remember(con, "portal-submit", invite["invite_id"], idempotency_key, payload, result)
            return {**result, "replayed": False}

    def _portal_apply(self, token, payload, idempotency_key):
        # Applicants cannot attest their own staff identity/document review.
        _mapping(payload, CUSTOMER_FIELDS | {"request_type", "consent_reference"})
        application_payload = {k: v for k, v in payload.items() if k != "request_type"}
        normalized = self._onboarding_payload(application_payload)
        with self.service._db(write=True) as con:
            invite = self._portal(con, token)
            if invite["purpose"] != "ONBOARDING":
                _fail("PORTAL_SCOPE_REQUIRED", "This invitation does not permit applicant intake.")
            previous = self._request(con, "portal-apply", invite["invite_id"], idempotency_key, normalized)
            if previous:
                return {**previous, "replayed": True}
            if invite["onboarding_id"]:
                _fail("APPLICATION_ALREADY_SUBMITTED", "This invitation already has an application; contact your reviewer for corrections.")
            actor = DEMO_ACTORS.get(invite["created_by"])
            self._auth(actor, INTAKE_ROLES)
            application = self._create_onboarding(con, normalized, actor, submitted_by="applicant-portal")
            con.execute("UPDATE relationship_onboarding_invites SET onboarding_id=? WHERE invite_id=?", (application["onboarding_id"], invite["invite_id"]))
            result = {"request_type": "APPLY", "onboarding_id": application["onboarding_id"], "status": application["status"], "customer_id": None}
            self._remember(con, "portal-apply", invite["invite_id"], idempotency_key, normalized, result)
            return {**result, "replayed": False}

    def attest_onboarding(self, onboarding_id, identity_review, document_review, note, actor):
        """Staff checklist for an applicant-submitted request, without auto-approval."""
        self._auth(actor, {"MANAGER", "ADMIN"})
        identity_review = _boolean(identity_review, "identity_review")
        document_review = _boolean(document_review, "document_review")
        note = _text(note, "review_note", 1000, required=True)
        with self.service._db(write=True) as con:
            request = self._onboarding(con, onboarding_id)
            if request["status"] != "PENDING_REVIEW":
                _fail("INVALID_STATE", "Only a pending application can receive review attestations.")
            payload = request["payload"]
            payload.update(identity_review=identity_review, document_review=document_review)
            con.execute("UPDATE relationship_onboardings SET payload=? WHERE onboarding_id=?", (_canonical(payload), onboarding_id))
            con.execute("INSERT INTO relationship_review_evidence VALUES (?, 'ONBOARDING_CHECKLIST',?,?,?,?)",
                        (str(uuid4()), onboarding_id, actor.user_id, note, timestamp()))
            self.service._log(con, "ONBOARDING_REVIEW_ATTESTED", actor=actor.user_id,
                              detail={"onboarding_id": onboarding_id, "identity_review": identity_review, "document_review": document_review, "real_kyc_performed": False})
            return self._onboarding(con, onboarding_id)

    def claim_outbox(self, actor, limit=50, lease_seconds=60):
        self._auth(actor, {"ADMIN", "AUTOMATION"})
        limit = _number(limit, "limit", 100, integer=True)
        lease_seconds = _number(lease_seconds, "lease_seconds", 900, integer=True)
        if limit < 1 or lease_seconds < 30:
            _fail("INVALID_LEASE", "Use 1-100 events and a lease between 30 and 900 seconds.")
        now = timestamp()
        with self.service._db(write=True) as con:
            rows = con.execute("""SELECT e.* FROM relationship_outbox e WHERE
                (e.status IN ('PENDING','RETRY') OR (e.status='IN_FLIGHT' AND e.lease_expires_at<=?))
                AND NOT EXISTS (SELECT 1 FROM relationship_outbox earlier WHERE earlier.customer_id=e.customer_id
                    AND earlier.version<e.version AND earlier.status!='SENT') ORDER BY e.created_at,e.version LIMIT ?""", (now, limit)).fetchall()
            results = []
            for row in rows:
                token, expires = secrets.token_urlsafe(24), timestamp(utcnow() + timedelta(seconds=lease_seconds))
                con.execute("UPDATE relationship_outbox SET status='IN_FLIGHT',attempts=attempts+1,lease_token=?,lease_expires_at=? WHERE event_id=?", (token, expires, row["event_id"]))
                results.append({"event_id": row["event_id"], "customer_id": row["customer_id"], "version": row["version"],
                                "event_hash": row["event_hash"], "payload": json.loads(row["payload"]),
                                "lease_token": token, "lease_expires_at": expires})
            return results

    def complete_outbox(self, event_id, lease_token, actor, error=None):
        self._auth(actor, {"ADMIN", "AUTOMATION"})
        if not isinstance(lease_token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32}", lease_token):
            _fail("OUTBOX_LEASE_REQUIRED", "The active export lease is required.")
        with self.service._db(write=True) as con:
            row = con.execute("SELECT * FROM relationship_outbox WHERE event_id=?", (event_id,)).fetchone()
            if not row or row["status"] != "IN_FLIGHT" or not secrets.compare_digest(row["lease_token"] or "", lease_token) or row["lease_expires_at"] <= timestamp():
                _fail("OUTBOX_LEASE_EXPIRED", "The export lease is unavailable or expired; reclaim the event before acknowledging it.")
            # Store codes only. Driver exceptions often contain SQL, credentials, or PII.
            safe_error = error if isinstance(error, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error) else "EXPORT_FAILED"
            con.execute("UPDATE relationship_outbox SET status=?,lease_token=NULL,lease_expires_at=NULL,last_error=?,sent_at=? WHERE event_id=?",
                        ("SENT" if error is None else "RETRY", None if error is None else safe_error, timestamp() if error is None else None, event_id))
            self.service._log(con, "RELATIONSHIP_EXPORT_" + ("ACKNOWLEDGED" if error is None else "RETRY"), row["customer_id"], actor=actor.user_id,
                              detail={"event_id": event_id, "version": row["version"], "error_code": None if error is None else safe_error})
            return {"event_id": event_id, "customer_id": row["customer_id"], "version": row["version"], "status": "SENT" if error is None else "RETRY"}

    def outbox_status(self, actor):
        self._auth(actor, STAFF_ROLES | {"AUTOMATION"})
        with self.service._db() as con:
            counts = dict(con.execute("SELECT status,COUNT(*) FROM relationship_outbox GROUP BY status").fetchall())
            return {"counts": counts, "events": [dict(r) for r in con.execute(
                "SELECT event_id,customer_id,version,status,attempts,created_at,sent_at,last_error FROM relationship_outbox ORDER BY created_at DESC LIMIT 100")]}
