"""Public deployment boundaries and anonymous website workflow checks."""
import json
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from cloud.config import CloudError, WORKSPACE
from public_app import repository as public
from public_app import security as public_security
from scripts import setup_public_cloud as setup
from samvaad.signals import extract_signals
from test_trial_cloud import Session


class Connection:
    def __init__(self, identity=None):
        self.identity = identity or {"ACCOUNT": public.ACCOUNT, "LOGIN": public.SERVICE_USER,
                                     "ROLE": public.READER_ROLE, "WAREHOUSE": public.WAREHOUSE}
        self.session = Session()
        self.calls = []
        self.closed = False

    def close(self):
        self.closed = True

    def cursor(self):
        connection = self
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def execute(self, sql, params=None):
                connection.calls.append((sql, params))
                if sql == public.IDENTITY_SQL:
                    self.description = [(k,) for k in connection.identity]
                    self.result = [list(connection.identity.values())]
                elif sql in public.portfolio_reads():
                    data = connection.session.data
                    if '"LOANS"' in sql:
                        rows = [{"PAYLOAD": json.dumps(l)} for l in data["loans"]]
                    elif '"PAYMENTS"' in sql:
                        rows = [{"PAYLOAD": json.dumps(p)} for p in data["payments"]]
                    else:
                        rows = [{"CUSTOMER_ID": i["customer_id"], "INTERACTION_ID": i["interaction_id"],
                            "CHANNEL": i["channel"], "TS": i["ts"], "TEXT": i["text"],
                            "EVIDENCE_TEXT": extract_signals(i["text"])["evidence_text"],
                            "OFFLINE_SIGNALS": json.dumps(extract_signals(i["text"]))} for i in data["interactions"]]
                    self.description = [(k,) for k in rows[0]]
                    self.result = [list(row.values()) for row in rows]
                else:
                    rows = connection.session.sql(sql, params or []).collect()
                    self.description = [(k,) for k in rows[0]] if rows else []
                    self.result = [list(row.values()) for row in rows]
            def fetchone(self): return self.result[0]
            def fetchall(self): return self.result
        return Cursor()


@pytest.fixture
def reader():
    return public.PublicReader(public.ReadSession(Connection()))


@pytest.fixture
def key_settings(tmp_path, monkeypatch):
    # Real ephemeral test key; never checked into source or printed.
    monkeypatch.setattr(setup.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0))
    return setup.service_material(tmp_path / "private")


def test_public_key_connection_verifies_principal_before_reads(key_settings):
    values, _, _ = key_settings
    connection = Connection()
    captured = {}
    def connector(**settings):
        captured.update(settings)
        return connection
    reader = public.connect_reader(values, connector=connector)
    assert captured["paramstyle"] == "qmark" and captured["authenticator"] == "SNOWFLAKE_JWT"
    assert "password" not in captured and captured["client_session_keep_alive"] is False
    assert connection.calls[0][0] == public.IDENTITY_SQL
    assert len(reader.customers()) == 20


def test_wrong_cloud_identity_closes_connection_without_customer_reads(key_settings):
    values, _, _ = key_settings
    connection = Connection({"ACCOUNT": "OTHER-ACCOUNT", "LOGIN": public.SERVICE_USER,
                             "ROLE": public.READER_ROLE, "WAREHOUSE": public.WAREHOUSE})
    with pytest.raises(public.DemoError):
        public.connect_reader(values, connector=lambda **_: connection)
    assert connection.closed and len(connection.calls) == 1


def test_private_operator_or_account_settings_are_rejected_before_connect(key_settings):
    values, _, _ = key_settings
    values["user"] = "ARUNVPP24"
    with pytest.raises(public.DemoError):
        public.connect_reader(values, connector=lambda **_: pytest.fail("Must not connect"))


@pytest.mark.parametrize("query", [
    'SELECT * FROM "SAMVAAD_STAGING"."APP"."DEMO_REVIEWS"',
    "SELECT AI_COMPLETE('llama3.3-70b', 'hello')",
    "SELECT 1; DROP TABLE CUSTOMERS", "INSERT INTO CUSTOMERS VALUES (1)",
])
def test_public_adapter_denies_unreviewed_sql_before_execution(reader, query):
    with pytest.raises(public.DemoError):
        reader.rows(query)
    assert not reader.session.connection.calls


def test_public_reads_use_only_the_synthetic_snapshot_and_match_journeys(reader):
    expected = {"C0001": "HARDSHIP_RESTRUCTURE_CALL", "C0002": "RETENTION_RATE_MATCH_CALL",
                "C0003": "TOPUP_PREAPPROVAL_CALL", "C0004": "NO_ACTION"}
    for cid, action in expected.items():
        assert reader.customer360(cid)["decision"]["action_code"] == action
    assert all('"PUBLIC_DEMO"' in sql and '"RAW"' not in sql for sql, _ in reader.session.connection.calls)
    with pytest.raises(public.DemoError):
        reader.answer("C0003", "Why this action?", cortex=True)
    with pytest.raises(public.DemoError):
        reader.reviews()


def test_public_portfolio_uses_four_bounded_reads_and_preserves_decisions(reader):
    profiles = reader.portfolio_profiles()
    calls = reader.session.connection.calls
    assert len(profiles) == 20 and len(calls) == 4
    assert all(q.startswith("SELECT") and '"PUBLIC_DEMO"' in q and "LIMIT" in q for q, _ in calls)
    assert profiles[0]["decision"]["action_code"] == "HARDSHIP_RESTRUCTURE_CALL"
    assert profiles[1]["decision"]["action_code"] == "RETENTION_RATE_MATCH_CALL"
    assert profiles[2]["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    assert profiles[3]["decision"]["action_code"] == "NO_ACTION"


def test_anonymous_review_simulation_is_isolated_and_never_writes(reader):
    first, second = public.ReviewSandbox([], reader), public.ReviewSandbox([], reader)
    rid = first.request("C0003")
    assert first.request("C0003") == rid
    with pytest.raises(public.DemoError):
        second.review(rid, "APPROVED_IN_SIMULATION", "Another visitor cannot approve")
    first.review(rid, "APPROVED_IN_SIMULATION", "Fictional simulation only")
    assert first.state[0]["status"] == "APPROVED_IN_SIMULATION" and second.state == []
    assert json.loads(first.export())["financial_execution"] is False
    assert all(sql.startswith("SELECT") for sql, _ in reader.session.connection.calls)


def test_simulation_rechecks_current_consent_and_denies_dnd(reader):
    sandbox = public.ReviewSandbox([], reader)
    with pytest.raises(public.DemoError):
        sandbox.request("C0004")
    rid = sandbox.request("C0003")
    next(c for c in reader.session.connection.session.data["customers"] if c["customer_id"] == "C0003")["consent_calls"] = False
    with pytest.raises(public.DemoError):
        sandbox.review(rid, "APPROVED_IN_SIMULATION", "Consent changed before simulation")
    assert sandbox.state[0]["status"] == "PENDING_SIMULATION"


def test_public_service_material_is_encrypted_reused_and_toml_round_trips(tmp_path, key_settings, monkeypatch):
    values, public_key, fingerprint = key_settings
    assert values["private_key"].startswith("-----BEGIN ENCRYPTED PRIVATE KEY-----")
    assert fingerprint.startswith("SHA256:") and public_key
    monkeypatch.setattr(setup.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0))
    again = setup.service_material(tmp_path / "private")
    assert again == key_settings


def test_public_role_grants_do_not_include_staff_data_writes_ai_or_administration():
    grants = setup.reader_grants()
    assert len(grants) == 7
    assert all(q.startswith(("GRANT SELECT", "GRANT USAGE")) for q in grants)
    assert not any(x in "\n".join(grants) for x in ['"RAW"', '"APP"', '"AI"', "CORTEX", "TO ROLE PUBLIC", "OWNERSHIP"])


class AdminCursor:
    def __init__(self, *, wrong_account=False, existing_role=False, existing_user=False):
        self.queries = []
        self.connection = Connection()
        self.existing_role, self.existing_user = existing_role, existing_user
        self.identity = {"ACCOUNT": "WRONG-ACCOUNT" if wrong_account else public.ACCOUNT,
                         "LOGIN": setup.OWNER, "ROLE": "ACCOUNTADMIN", "WAREHOUSE": None}
    def execute(self, query):
        self.queries.append(query)
        if query == public.IDENTITY_SQL:
            rows = [self.identity]
        elif query.startswith("SELECT CUSTOMER_ID, PAYLOAD"):
            rows = [{"CUSTOMER_ID": c["customer_id"], "PAYLOAD": json.dumps(c)}
                    for c in self.connection.session.data["customers"]]
        elif query.startswith("SHOW ROLES"):
            rows = [{"name": public.READER_ROLE}] if self.existing_role else []
        elif query.startswith("SHOW USERS"):
            rows = [{"name": public.SERVICE_USER}] if self.existing_user else []
        elif query.startswith("SHOW GRANTS TO USER"):
            rows = [{"role": public.READER_ROLE}]
        else:
            rows = []
        self.description = [(k,) for k in rows[0]] if rows else []
        self.result = [list(row.values()) for row in rows]
    def fetchone(self): return self.result[0]
    def fetchall(self): return self.result


@pytest.mark.parametrize("options,code", [({"wrong_account": True}, "WRONG_ACCOUNT_USER_OR_ROLE"),
    ({"existing_role": True}, "PUBLIC_ROLE_EXISTS"), ({"existing_user": True}, "PUBLIC_USER_EXISTS")])
def test_public_setup_preserves_unrelated_resources_and_authentication(options, code):
    cursor = AdminCursor(**options)
    with pytest.raises(CloudError) as error:
        setup.provision(cursor, {}, "test-public-key", "test-fingerprint", lambda: None)
    assert error.value.code == code
    assert all(q.startswith(("SELECT", "SHOW")) for q in cursor.queries)


def test_public_setup_creates_four_snapshots_without_replacing_staff_tables():
    cursor, report = AdminCursor(), {}
    setup.provision(cursor, report, "test-public-key", "test-fingerprint", lambda: None)
    clones = [q for q in cursor.queries if q.startswith("CREATE TABLE")]
    assert len(clones) == 4 and all('"PUBLIC_DEMO"' in q and " CLONE " in q for q in clones)
    assert not any("DROP" in q or "OR REPLACE" in q or q.startswith("ALTER USER") for q in cursor.queries)
    assert report["cloned_tables"] == list(setup.TABLES) and report["user_created"]


@pytest.fixture
def public_ui(reader, monkeypatch, tmp_path):
    st.cache_data.clear()
    st.cache_resource.clear()
    monkeypatch.setattr(st, "secrets", {"snowflake": {}})
    # Streamlit cache reset must never reset production spend counters. Give
    # each UI test an isolated host store rather than using the runtime budget.
    guard_type = public_security.PublicGuard
    monkeypatch.setattr(public_security, "PublicGuard", lambda: guard_type(tmp_path / "public-guard.db"))
    monkeypatch.setattr(public, "connect_reader", lambda *_a, **_k: reader)
    yield AppTest.from_file(str(WORKSPACE / "public_app/streamlit_app.py"), default_timeout=10), reader
    st.cache_data.clear()
    st.cache_resource.clear()


def test_anonymous_website_renders_and_runs_review_simulation(public_ui):
    app, reader = public_ui
    app.run()
    assert not app.exception and len(app.tabs) == 5
    assert not any("Signed in" in str(m.value) for m in app.markdown)
    app.session_state["workspace_tabs"] = "Customer 360"
    next(s for s in app.selectbox if s.label == "Customer").select("C0003").run()
    next(b for b in app.button if b.label == "Add to review queue").click().run()
    next(t for t in app.text_input if t.label == "Review note").set_value("Public synthetic workflow check")
    next(b for b in app.button if b.label == "Save review decision").click().run()
    assert not app.exception and app.session_state["public_reviews"][0]["status"] == "APPROVED_IN_SIMULATION"
    assert not reader.session.connection.session.requests


def test_public_ui_hides_provider_messages_and_private_credentials(public_ui, monkeypatch, caplog):
    app, reader = public_ui
    app.run()
    app.session_state["workspace_tabs"] = "Evidence desk"
    app.run()
    monkeypatch.setattr(public.GuardedSnapshotReader, "answer", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("PRIVATE_PROVIDER_CREDENTIAL")))
    next(b for b in app.button if b.label == "Find the evidence").click().run()
    assert not app.exception and app.error
    assert "PRIVATE_PROVIDER_CREDENTIAL" not in caplog.text + " ".join(e.value for e in app.error)


def test_fallback_is_validated_fictional_and_labelled_as_an_offline_source():
    reader = public.SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")
    assert not reader.is_live and len(reader.customers()) == 20
    assert reader.customer360("C0003")["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    result = reader.answer("C0003", "What is the next action?")
    assert result["provider"].startswith("Bundled synthetic snapshot")
    assert result["evidence"]


def test_fallback_rejects_a_changed_or_real_contact_bundle(tmp_path):
    document = json.loads((WORKSPACE / "public_app/synthetic_snapshot.json").read_text(encoding="utf-8"))
    document["data"]["customers"][0]["email"] = "actual-person@example.com"
    file = tmp_path / "changed.json"
    file.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CloudError):
        public.SnapshotReader(file)


def test_unavailable_backend_renders_an_explicit_offline_website(public_ui, monkeypatch, caplog):
    app, _ = public_ui
    monkeypatch.setattr(public, "connect_reader", lambda *_: (_ for _ in ()).throw(RuntimeError("PRIVATE_PROVIDER_CREDENTIAL")))
    app.run()
    assert not app.exception and len(app.tabs) == 5
    assert any("bundled fictional snapshot" in e.value for e in app.warning)
    assert "PRIVATE_PROVIDER_CREDENTIAL" not in caplog.text
