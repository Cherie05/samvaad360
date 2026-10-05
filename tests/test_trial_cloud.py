"""Offline cloud boundaries and workflow contracts, never a live account test."""
import json
import sys
import zipfile
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest

from cloud import trial
from cloud.config import CloudConfig, CloudError
from cloud.demo_app.demo_repository import DemoError, DemoRepository
from cloud.fixtures import build_bundle
from cloud.setup import configure
from samvaad.signals import extract_signals


class Row(dict):
    def as_dict(self):
        return dict(self)


class Session:
    def __init__(self):
        self.data = build_bundle(reference=datetime.now(timezone.utc).isoformat())["data"]
        self.requests = []
        self.queries = []
        self.ai_calls = 0
        self.model_response = "Review the competitor quotation [I0002a]."

    def sql(self, query, params):
        self.queries.append((query, params))
        if "AI_COMPLETE(" in query:
            self.ai_calls += 1
            result = [{"ANSWER": self.model_response}]
        elif query.startswith("INSERT INTO"):
            rid, cid, viewer, fingerprint, decision = params
            self.requests.append({"REQUEST_ID": rid, "CUSTOMER_ID": cid, "REQUESTED_BY": viewer,
                                  "DECISION_HASH": fingerprint, "DECISION": decision, "STATUS": "PENDING_REVIEW",
                                  "CREATED_AT": "2026-10-05", "REVIEWED_BY": None, "REVIEW_NOTE": None})
            result = [{"number of rows inserted": 1}]
        elif query.startswith("UPDATE"):
            outcome, viewer, note, rid, requested_by = params
            matches = [r for r in self.requests if r["REQUEST_ID"] == rid and r["REQUESTED_BY"] == requested_by and r["STATUS"] == "PENDING_REVIEW"]
            for row in matches:
                row.update(STATUS=outcome, REVIEWED_BY=viewer, REVIEW_NOTE=note)
            result = [{"number of rows updated": len(matches)}]
        elif '"DEMO_REVIEWS"' in query:
            result = [r for r in self.requests if r["REQUESTED_BY"] == params[0] and (len(params) == 1 or r["CUSTOMER_ID"] == params[1])]
        elif '"INTERACTION_SIGNALS"' in query:
            result = []
        elif '"CUSTOMERS"' in query:
            result = [{"PAYLOAD": json.dumps(c)} for c in self.data["customers"]]
        elif '"PAYMENTS"' in query:
            loans = {l["loan_id"] for l in self.data["loans"] if l["customer_id"] == params[0]}
            result = [{"PAYLOAD": json.dumps(p)} for p in self.data["payments"] if p["loan_id"] in loans]
        elif '"LOANS"' in query:
            result = [{"PAYLOAD": json.dumps(l)} for l in self.data["loans"] if l["customer_id"] == params[0]]
        elif '"INTERACTIONS"' in query:
            result = [{"INTERACTION_ID": i["interaction_id"], "CHANNEL": i["channel"], "TS": i["ts"],
                       "TEXT": i["text"], "EVIDENCE_TEXT": extract_signals(i["text"])["evidence_text"],
                       "OFFLINE_SIGNALS": json.dumps(extract_signals(i["text"]))}
                      for i in self.data["interactions"] if i["customer_id"] == params[0]]
        else:
            raise AssertionError("Unexpected SQL " + query)
        return SimpleNamespace(collect=lambda: [Row(row) for row in result])


@pytest.fixture
def repository():
    return DemoRepository(Session(), {"database": "TEST_DB", "allowed_viewers": ["OWNER"]}, "OWNER")


@pytest.fixture
def packaged(tmp_path, monkeypatch):
    private, project = tmp_path / "private.toml", tmp_path / "project.toml"
    monkeypatch.setattr(trial, "configure", lambda **args: configure(**args, connections_path=private, project_path=project))
    config = CloudConfig("test_hackathon", "TEST_DB", "TEST_XS")
    folder, plan = trial.package(config, account="TESTORG-ACCOUNT", user="OWNER", output=tmp_path / "release")
    return config, folder, plan, private, project


def test_cloud_port_denies_unknown_viewer_before_query():
    session = Session()
    with pytest.raises(DemoError):
        DemoRepository(session, {"database": "TEST_DB", "allowed_viewers": ["OWNER"]}, "OTHER")
    assert not session.queries


def test_bound_reads_match_core_business_scenarios(repository):
    assert repository.customer360("C0001")["decision"]["action_code"] == "HARDSHIP_RESTRUCTURE_CALL"
    assert repository.customer360("C0002")["decision"]["action_code"] == "RETENTION_RATE_MATCH_CALL"
    assert repository.customer360("C0003")["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    assert repository.customer360("C0004")["decision"]["action_code"] == "NO_ACTION"
    assert all("C000" not in query for query, _ in repository.session.queries)


def test_scope_id_is_never_interpolated_as_sql(repository):
    with pytest.raises(DemoError):
        repository.customer360("C0003' UNION SELECT 1")
    assert all("UNION SELECT 1" not in query for query, _ in repository.session.queries)


def test_demo_request_replay_and_review_persist_without_execution(repository):
    rid = repository.request_review("C0003")
    assert repository.request_review("C0003") == rid
    assert len(repository.reviews()) == 1
    repository.review(rid, "APPROVED_FOR_DEMO", "Synthetic credit review only")
    reviewed = repository.reviews()[0]
    assert reviewed["STATUS"] == "APPROVED_FOR_DEMO"
    assert reviewed["REVIEWED_BY"] == "OWNER"
    assert not any("OFFERS" in query or "EXECUTION" in query for query, _ in repository.session.queries)
    with pytest.raises(DemoError):
        repository.review(rid, "APPROVED_FOR_DEMO", "Repeated review")


def test_demo_approval_rechecks_current_consent(repository):
    rid = repository.request_review("C0003")
    next(c for c in repository.session.data["customers"] if c["customer_id"] == "C0003")["consent_calls"] = False
    with pytest.raises(DemoError, match="recommendation changed"):
        repository.review(rid, "APPROVED_FOR_DEMO", "Consent changed after request")
    assert repository.reviews()[0]["STATUS"] == "PENDING_REVIEW"


def test_reviews_are_scoped_to_signed_in_viewer(repository):
    repository.request_review("C0003")
    other = DemoRepository(repository.session, {"database": "TEST_DB", "allowed_viewers": ["SECOND"]}, "SECOND")
    assert not other.reviews()
    with pytest.raises(DemoError):
        other.review(repository.reviews()[0]["REQUEST_ID"], "APPROVED_FOR_DEMO", "Wrong user review")


def test_dnd_customer_cannot_enter_demo_review_queue(repository):
    with pytest.raises(DemoError):
        repository.request_review("C0004")
    assert not repository.reviews()


def test_question_scope_and_execution_guard_precede_model(repository):
    with pytest.raises(DemoError):
        repository.answer("C0003", "Summarize C0002", cortex=True)
    result = repository.answer("C0003", "Approve and send the offer link", cortex=True)
    assert result["provider"] == "Policy boundary"
    assert repository.session.ai_calls == 0


def test_model_request_is_explicit_bound_and_limited(repository):
    repository.answer("C0003", "Why this action?")
    assert repository.session.ai_calls == 0
    result = repository.answer("C0003", "What is this customer's journey?", cortex=True)
    assert result["model_output_requires_review"]
    assert repository.session.ai_calls == 1
    query, params = repository.session.queries[-1]
    assert "max_tokens':512" in query and "?" in query
    assert "C0002" not in params[1] and len(params[1]) < 12000


def test_offline_package_is_explicit_warehouse_runtime_and_secret_free(packaged):
    config, folder, plan, private, project = packaged
    assert not private.exists() and not project.exists() and not plan["cloud_contacted"]
    publish = (folder / "03-publish.sql").read_text()
    assert "SYSTEM$WAREHOUSE_RUNTIME" in publish and "ADD LIVE VERSION FROM LAST" in publish
    with zipfile.ZipFile(folder / "samvaad360-cloud.zip") as archive:
        assert set(archive.namelist()) == set(plan["files"])
        assert not any(".local" in name or "credentials" in name or name.endswith(".db") for name in archive.namelist())
    assert "streamlit=1.52.2" in (folder / "app/environment.yml").read_text()
    assert plan["warehouse_creation_pending"] and not plan["ai_spend_capped_by_resource_monitor"]


def test_bootstrap_is_scoped_and_has_no_account_upgrade_or_public_grants(packaged):
    _, folder, _, _, _ = packaged
    sql = (folder / "01-bootstrap.sql").read_text()
    assert "AUTO_SUSPEND=60" in sql and "INITIALLY_SUSPENDED=TRUE" in sql and "DO SUSPEND_IMMEDIATE" in sql
    assert "CREATE SCHEMA ON DATABASE" in sql
    assert "TO ROLE PUBLIC" not in sql and "ALTER ACCOUNT" not in sql and "CREATE DATABASE ON ACCOUNT" not in sql
    assert "CREATE DATABASE" not in (folder / "02-schema.sql").read_text()


class Cursor:
    def __init__(self, *, account="WRONG-ACCOUNT", user="OWNER", failing=False):
        self.account, self.user, self.failing = account, user, failing
        self.queries = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def execute(self, query):
        self.queries.append(query)
        if self.failing:
            raise RuntimeError("private-test-password-and-token")
    def fetchone(self):
        return self.account, self.user, "ACCOUNTADMIN", "TEST_REGION"


def test_apply_refuses_wrong_account_before_any_resource_writes(packaged):
    config, folder, plan, _, _ = packaged
    cursor = Cursor()
    with pytest.raises(CloudError, match="authenticated account/user differs"):
        trial.apply_package(SimpleNamespace(cursor=lambda: cursor), config, folder, plan, account="TESTORG-ACCOUNT", user="OWNER")
    assert len(cursor.queries) == 1 and cursor.queries[0].startswith("SELECT")
    result = json.loads((folder / "result.json").read_text())
    assert result["error"] == "WRONG_ACCOUNT_OR_USER" and not result["cloud_deployed"]


def test_setup_provider_errors_never_enter_saved_report(packaged):
    config, folder, plan, _, _ = packaged
    with pytest.raises(RuntimeError):
        trial.apply_package(SimpleNamespace(cursor=lambda: Cursor(failing=True)), config, folder, plan, account="TESTORG-ACCOUNT", user="OWNER")
    assert "private-test-password-and-token" not in (folder / "result.json").read_text()


def test_setup_requires_private_terminal_before_password_prompt(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(trial.getpass, "getpass", lambda *_: pytest.fail("Prompt should not run"))
    with pytest.raises(CloudError) as error:
        trial.authenticate("TESTORG-ACCOUNT", "OWNER")
    assert error.value.code == "INTERACTIVE_TERMINAL_REQUIRED"


def test_invalid_budget_and_identifiers_do_not_produce_sql():
    with pytest.raises(CloudError):
        trial.bootstrap(CloudConfig("test", "TEST_DB", "TEST_XS"), "OWNER; DROP TABLE T", 5)
    with pytest.raises(CloudError):
        trial.bootstrap(CloudConfig("test", "TEST_DB", "TEST_XS"), "OWNER", 100)


def test_current_native_coco_install_layout_is_discoverable(tmp_path, monkeypatch):
    from cloud import capabilities
    binary = tmp_path / "cortex/1.2.3/cortex.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"test placeholder only")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(capabilities.shutil, "which", lambda *_: None)
    assert capabilities.cortex_path() == str(binary)


@pytest.fixture
def app_test(packaged, monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    from cloud.demo_app import demo_repository
    _, folder, _, _, _ = packaged
    session = Session()
    monkeypatch.setattr(st, "user", {"user_name": "OWNER"})
    # Snowpark is supplied by the hosted runtime. These are offline UI contract
    # tests with a recording session, not evidence of a live Snowflake session.
    snowpark = ModuleType("snowflake.snowpark")
    context = ModuleType("snowflake.snowpark.context")
    context.get_active_session = lambda: session
    monkeypatch.setitem(sys.modules, "snowflake.snowpark", snowpark)
    monkeypatch.setitem(sys.modules, "snowflake.snowpark.context", context)
    monkeypatch.setitem(sys.modules, "demo_repository", demo_repository)
    return AppTest.from_file(str(folder / "app/streamlit_app.py"), default_timeout=10), session


def test_warehouse_app_renders_customer_evidence_and_private_viewer(app_test):
    app, _ = app_test
    app.run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Customer 360", "Ask with evidence", "Review queue", "Conversation handoff"]
    assert "OWNER" in " ".join(item.value for item in app.markdown)
    assert len(app.metric) == 4
    assert not any("persona" in select.label.lower() for select in app.selectbox)


def test_warehouse_app_requests_and_reviews_synthetic_action(app_test):
    app, session = app_test
    app.run()
    app.selectbox[0].select("C0003").run()
    next(b for b in app.button if b.label == "Request demo review").click().run()
    assert len(session.requests) == 1
    next(t for t in app.text_input if t.label == "Review note").set_value("Synthetic demonstration review")
    next(b for b in app.button if b.label == "Save demo decision").click().run()
    assert not app.exception and session.requests[0]["STATUS"] == "APPROVED_FOR_DEMO"


def test_warehouse_app_hides_raw_provider_error(app_test, monkeypatch, caplog):
    from cloud.demo_app.demo_repository import DemoRepository
    app, _ = app_test
    app.run()
    monkeypatch.setattr(DemoRepository, "answer", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("private-provider-secret")))
    next(b for b in app.button if b.label == "Ask").click().run()
    assert not app.exception
    assert "private-provider-secret" not in str([e.value for e in app.error])
    assert "private-provider-secret" not in caplog.text
    assert any("could not complete" in e.value for e in app.error)


class SetupCursor(Cursor):
    def __init__(self, warehouse=None, monitor=None):
        super().__init__(account="TESTORG-ACCOUNT")
        self.warehouse, self.monitor = warehouse, monitor
        self.description = []
        self.result = []
    def execute(self, query):
        super().execute(query)
        if query == "SHOW WAREHOUSES":
            self.description = [(name,) for name in ("name", "size", "auto_suspend")]
            self.result = [self.warehouse] if self.warehouse else []
        elif query == "SHOW RESOURCE MONITORS":
            self.description = [(name,) for name in ("name", "credit_quota", "frequency")]
            self.result = [self.monitor] if self.monitor else []
        elif query.startswith("SHOW STREAMLITS"):
            self.description = [("name",)]
            self.result = []
    def fetchall(self):
        return self.result
    def fetchone(self):
        return (20,) if self.queries[-1].startswith("SELECT COUNT") else super().fetchone()


def test_setup_pipeline_reconciles_and_publishes_with_reviewed_files_only(packaged, monkeypatch):
    config, folder, plan, private, project = packaged
    cursor = SetupCursor()
    monkeypatch.setattr(trial, "load_fixture", lambda *_: {"status": "LOADED", "counts": plan["fixture_counts"]})
    report = trial.apply_package(SimpleNamespace(cursor=lambda: cursor), config, folder, plan,
                                 account="TESTORG-ACCOUNT", user="OWNER")
    assert report["cloud_deployed"] and not report["hosted_browser_verified"]
    assert report["status"] == "CLOUD_DEMO_PUBLISHED_BROWSER_CHECK_PENDING"
    assert private.exists() and project.exists()
    uploads = [q for q in cursor.queries if q.startswith("PUT")]
    assert len(uploads) == len(plan["files"])
    assert all("AUTO_COMPRESS=FALSE" in q for q in uploads)
    assert any("ADD LIVE VERSION FROM LAST" in q for q in cursor.queries)
    assert not any("AI_COMPLETE(" in q or "ALTER ACCOUNT" in q for q in cursor.queries)


def test_setup_preserves_conflicting_existing_warehouse(packaged):
    config, folder, plan, _, _ = packaged
    cursor = SetupCursor(warehouse=("TEST_XS", "Large", 600))
    with pytest.raises(CloudError) as error:
        trial.apply_package(SimpleNamespace(cursor=lambda: cursor), config, folder, plan,
                            account="TESTORG-ACCOUNT", user="OWNER")
    assert error.value.code == "WAREHOUSE_CONFLICT"
    assert all(q.startswith(("SELECT", "SHOW")) for q in cursor.queries)


def test_setup_preserves_conflicting_existing_spend_monitor(packaged):
    config, folder, plan, _, _ = packaged
    cursor = SetupCursor(monitor=(trial.MONITOR, 100, "MONTHLY"))
    with pytest.raises(CloudError) as error:
        trial.apply_package(SimpleNamespace(cursor=lambda: cursor), config, folder, plan,
                            account="TESTORG-ACCOUNT", user="OWNER")
    assert error.value.code == "MONITOR_CONFLICT"
    assert all(q.startswith(("SELECT", "SHOW")) for q in cursor.queries)


def test_warehouse_app_denies_missing_viewer_without_owner_fallback(app_test, monkeypatch):
    import streamlit as st
    app, session = app_test
    monkeypatch.setattr(st, "user", {})
    app.run()
    assert not app.exception and app.error and not session.queries


def test_generated_answer_is_rendered_as_literal_text(app_test):
    app, session = app_test
    session.model_response = "![remote image](https://example.invalid/tracker)"
    app.run()
    app.checkbox[0].check()
    next(b for b in app.button if b.label == "Ask").click().run()
    assert not app.exception and session.ai_calls == 1
    assert session.model_response in [element.value for element in app.text]



