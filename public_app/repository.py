"""Public read adapter and per-visit review simulation.

The server authenticates to Snowflake. Anonymous visitors never receive a
credential or access the private staff review ledger. No AI calls or writes
are admitted by this adapter.
"""
from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import datetime, timezone

from cloud.demo_app.demo_repository import DemoError, DemoRepository, decision_hash

ACCOUNT = "ZYLTUKM-HU63768"
DATABASE = "SAMVAAD_STAGING"
PUBLIC_SCHEMA = "PUBLIC_DEMO"
WAREHOUSE = "SAMVAAD_XS"
SERVICE_USER = "SAMVAAD_PUBLIC_SERVICE"
READER_ROLE = "SAMVAAD_PUBLIC_READONLY"
IDENTITY_SQL = (
    "SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS ACCOUNT, "
    "CURRENT_USER() AS LOGIN, CURRENT_ROLE() AS ROLE, CURRENT_WAREHOUSE() AS WAREHOUSE"
)


def allowed_reads():
    raw = f'"{DATABASE}"."{PUBLIC_SCHEMA}"'
    return {
        f'SELECT PAYLOAD FROM {raw}."CUSTOMERS" ORDER BY CUSTOMER_ID LIMIT 101': 0,
        f'SELECT PAYLOAD FROM {raw}."LOANS" WHERE CUSTOMER_ID=? ORDER BY LOAN_ID LIMIT 100': 1,
        f'SELECT P.PAYLOAD FROM {raw}."PAYMENTS" P JOIN {raw}."LOANS" L '
        "ON P.LOAN_ID=L.LOAN_ID WHERE L.CUSTOMER_ID=? ORDER BY P.PAYMENT_ID LIMIT 1000": 1,
        f'SELECT INTERACTION_ID,CHANNEL,TS,TEXT,EVIDENCE_TEXT,OFFLINE_SIGNALS '
        f'FROM {raw}."INTERACTIONS" WHERE CUSTOMER_ID=? ORDER BY TS DESC LIMIT 100': 1,
        **portfolio_reads(),
    }


def portfolio_reads():
    raw = f'"{DATABASE}"."{PUBLIC_SCHEMA}"'
    return {
        f'SELECT PAYLOAD FROM {raw}."LOANS" ORDER BY LOAN_ID LIMIT 201': 0,
        f'SELECT PAYLOAD FROM {raw}."PAYMENTS" ORDER BY PAYMENT_ID LIMIT 2001': 0,
        f'SELECT CUSTOMER_ID,INTERACTION_ID,CHANNEL,TS,TEXT,EVIDENCE_TEXT,OFFLINE_SIGNALS '
        f'FROM {raw}."INTERACTIONS" ORDER BY TS DESC LIMIT 501': 0,
    }


class _Row(dict):
    def as_dict(self):
        return dict(self)


class ReadSession:
    """The small Snowpark-shaped read interface used by the domain adapter."""

    def __init__(self, connection):
        self.connection = connection
        self.lock = threading.RLock()

    def sql(self, query, params=None):
        params = params or []
        expected = allowed_reads().get(query)
        if expected is None or len(params) != expected:
            raise DemoError("This public reader accepts only the reviewed synthetic-data queries.")
        if any(not isinstance(p, str) or len(p) > 20 for p in params):
            raise DemoError("Select a supported customer profile.")

        session = self

        class Query:
            def collect(self):
                with session.lock, session.connection.cursor() as cursor:
                    cursor.execute(query, params)
                    columns = [item[0].upper() for item in cursor.description]
                    return [_Row(zip(columns, values)) for values in cursor.fetchall()]

        return Query()


class PublicReader(DemoRepository):
    is_live = True

    def __init__(self, session):
        # This is a server-side synthetic reader label, never a staff identity.
        super().__init__(session, {"database": DATABASE, "allowed_viewers": ["PUBLIC_SYNTHETIC_READER"]},
                         "PUBLIC_SYNTHETIC_READER")

    def table(self, schema, name):
        if schema != "RAW" or name not in {"CUSTOMERS", "LOANS", "PAYMENTS", "INTERACTIONS"}:
            raise DemoError("The public reader cannot access private application tables.")
        return f'"{DATABASE}"."{PUBLIC_SCHEMA}"."{name}"'

    def cortex_signals(self, customer_id):
        self.customer360(customer_id)
        return []

    def portfolio_profiles(self):
        """Build the bounded 20-person work queue with four reads, not N+1 queries."""
        from samvaad.engine import CATALOGUE, compute_metrics, decide_customer
        customers = self.customers()
        queries = list(portfolio_reads())
        loans, payments, interactions = [self.rows(query) for query in queries]
        if len(loans) > 200 or len(payments) > 2000 or len(interactions) > 500:
            raise DemoError("This portfolio exceeds the public demonstration limits.")
        def document(row):
            payload = row["PAYLOAD"]
            return json.loads(payload) if isinstance(payload, str) else dict(payload)
        loans, payments = [document(r) for r in loans], [document(r) for r in payments]
        by_customer = {c["customer_id"]: [] for c in customers}
        for row in interactions:
            if row["CUSTOMER_ID"] not in by_customer:
                raise DemoError("The public interaction snapshot has an unexpected customer scope.")
            signals = json.loads(row["OFFLINE_SIGNALS"]) if isinstance(row["OFFLINE_SIGNALS"], str) else dict(row["OFFLINE_SIGNALS"])
            by_customer[row["CUSTOMER_ID"]].append({"interaction_id": row["INTERACTION_ID"],
                "customer_id": row["CUSTOMER_ID"], "channel": row["CHANNEL"], "ts": str(row["TS"]),
                "text": row["TEXT"], "evidence_text": row["EVIDENCE_TEXT"], "intent": signals["intent"],
                "sentiment": signals["sentiment"], "entities": signals["entities"]})
        reference = datetime.fromisoformat(self.reference.replace("Z", "+00:00")) if not self.is_live else datetime.now(timezone.utc)
        result = []
        for customer in customers:
            cid = customer["customer_id"]
            customer_loans = [l for l in loans if l["customer_id"] == cid]
            loan_ids = {l["loan_id"] for l in customer_loans}
            customer_payments = [p for p in payments if p["loan_id"] in loan_ids]
            customer_interactions = by_customer[cid]
            metrics = compute_metrics(customer, customer_loans, customer_payments, customer_interactions, reference)
            result.append({"customer": customer, "loans": customer_loans, "payments": customer_payments,
                "interactions": customer_interactions, "metrics": metrics,
                "decision": decide_customer(customer, metrics, customer_interactions, CATALOGUE)})
        return result

    def reviews(self, customer_id=None):
        raise DemoError("The public website cannot read the private staff review queue.")

    def request_review(self, customer_id):
        raise DemoError("Use the isolated public review simulation.")

    def review(self, request_id, outcome, note):
        raise DemoError("The public website cannot update staff approvals.")

    def answer(self, customer_id, question, *, cortex=False):
        if cortex:
            raise DemoError("Live AI requests are disabled on the anonymous public demo.")
        return super().answer(customer_id, question, cortex=False)


class SnapshotReader(PublicReader):
    """Clearly labelled, approved fictional fallback when the trial is offline."""
    is_live = False

    def __init__(self, path):
        from cloud.fixtures import read_bundle
        from samvaad.signals import extract_signals

        bundle = read_bundle(path)
        data = bundle["data"]
        self.reference = bundle["reference"]

        class SnapshotSession:
            def sql(self, query, params=None):
                params = params or []
                if query not in allowed_reads() or len(params) != allowed_reads()[query]:
                    raise DemoError("Only the approved fictional fallback is available.")
                if '"CUSTOMERS"' in query:
                    rows = [{"PAYLOAD": json.dumps(c)} for c in data["customers"]]
                elif '"PAYMENTS"' in query:
                    loans = {l["loan_id"] for l in data["loans"] if not params or l["customer_id"] == params[0]}
                    rows = [{"PAYLOAD": json.dumps(p)} for p in data["payments"] if p["loan_id"] in loans]
                elif '"LOANS"' in query:
                    rows = [{"PAYLOAD": json.dumps(l)} for l in data["loans"] if not params or l["customer_id"] == params[0]]
                else:
                    rows = []
                    for i in data["interactions"]:
                        if not params or i["customer_id"] == params[0]:
                            signals = extract_signals(i["text"])
                            rows.append({"CUSTOMER_ID": i["customer_id"], "INTERACTION_ID": i["interaction_id"], "CHANNEL": i["channel"],
                                "TS": i["ts"], "TEXT": i["text"], "EVIDENCE_TEXT": signals["evidence_text"],
                                "OFFLINE_SIGNALS": json.dumps(signals)})
                    rows.sort(key=lambda row: row["TS"], reverse=True)
                return type("SnapshotQuery", (), {"collect": lambda _: [_Row(r) for r in rows]})()
        super().__init__(SnapshotSession())

    def customer360(self, customer_id):
        from samvaad.engine import CATALOGUE, compute_metrics, decide_customer
        view = super().customer360(customer_id)
        reference = datetime.fromisoformat(self.reference.replace("Z", "+00:00"))
        view["metrics"] = compute_metrics(view["customer"], view["loans"], view["payments"], view["interactions"], reference)
        view["decision"] = decide_customer(view["customer"], view["metrics"], view["interactions"], CATALOGUE)
        return view

    def answer(self, customer_id, question, *, cortex=False):
        result = super().answer(customer_id, question, cortex=cortex)
        if result["provider"] != "Policy boundary":
            result["provider"] = "Bundled synthetic snapshot + deterministic evidence summary"
        return result


def connect_reader(values, *, connector=None):
    """Verify the account, service principal and reader role before data reads."""
    expected = {"account": ACCOUNT, "user": SERVICE_USER, "role": READER_ROLE,
                "warehouse": WAREHOUSE, "database": DATABASE}
    if any(str(values.get(k, "")).upper() != v for k, v in expected.items()):
        raise DemoError("Public website connection settings do not match the reviewed deployment.")
    pem, passphrase = values.get("private_key"), values.get("private_key_passphrase")
    if not isinstance(pem, str) or not isinstance(passphrase, str) or not passphrase:
        raise DemoError("Configure the dedicated public reader credentials in hosting secrets.")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = serialization.load_pem_private_key(pem.encode(), password=passphrase.encode())
    if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
        raise DemoError("Use the reviewed RSA service key.")
    der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    if connector is None:
        import snowflake.connector
        connector = snowflake.connector.connect
    connection = connector(
        **expected, private_key=der, authenticator="SNOWFLAKE_JWT", paramstyle="qmark",
        login_timeout=20, network_timeout=30, client_session_keep_alive=False,
        session_parameters={"QUERY_TAG": "samvaad-public-synthetic-reader", "STATEMENT_TIMEOUT_IN_SECONDS": 30},
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(IDENTITY_SQL)
            names = [field[0].upper() for field in cursor.description]
            identity = dict(zip(names, cursor.fetchone()))
        target = {"ACCOUNT": ACCOUNT, "LOGIN": SERVICE_USER, "ROLE": READER_ROLE, "WAREHOUSE": WAREHOUSE}
        if any(str(identity.get(k, "")).upper() != v for k, v in target.items()):
            raise DemoError("The connected identity is not the dedicated public website reader.")
        return PublicReader(ReadSession(connection))
    except Exception:
        connection.close()
        raise


class ReviewSandbox:
    """Session-local fictional reviews; no database mutation or execution."""

    def __init__(self, state, reader):
        self.state, self.reader = state, reader

    def request(self, customer_id):
        decision = self.reader.customer360(customer_id)["decision"]
        if decision["action_code"] == "NO_ACTION":
            raise DemoError("Consent or policy prevents this recommendation from entering review.")
        fingerprint = decision_hash(decision)
        prior = next((r for r in self.state if r["customer_id"] == customer_id
                      and r["fingerprint"] == fingerprint and r["status"] == "PENDING_SIMULATION"), None)
        if prior:
            return prior["id"]
        if len(self.state) >= 25:
            raise DemoError("This visit has reached its 25-record simulation limit.")
        record = {"id": uuid.uuid4().hex, "customer_id": customer_id,
                  "decision": copy.deepcopy(decision), "fingerprint": fingerprint,
                  "status": "PENDING_SIMULATION", "note": "", "created_at": datetime.now(timezone.utc).isoformat()}
        self.state.append(record)
        return record["id"]

    def review(self, request_id, outcome, note):
        if outcome not in {"APPROVED_IN_SIMULATION", "REJECTED_IN_SIMULATION"}:
            raise DemoError("Choose a supported simulation outcome.")
        if not isinstance(note, str) or not 5 <= len(note.strip()) <= 500:
            raise DemoError("Enter a fictional review note of 5–500 characters.")
        record = next((r for r in self.state if r["id"] == request_id), None)
        if not record or record["status"] != "PENDING_SIMULATION":
            raise DemoError("This simulation record is unavailable or has already been reviewed.")
        if outcome == "APPROVED_IN_SIMULATION":
            current = self.reader.customer360(record["customer_id"])["decision"]
            if current["action_code"] == "NO_ACTION" or decision_hash(current) != record["fingerprint"]:
                raise DemoError("The recommendation or consent changed. Request a fresh review.")
        record.update(status=outcome, note=note.strip(), reviewed_at=datetime.now(timezone.utc).isoformat())

    def export(self):
        return json.dumps({"mode": "public-session-simulation", "financial_execution": False,
                           "records": self.state}, indent=2, ensure_ascii=False)
