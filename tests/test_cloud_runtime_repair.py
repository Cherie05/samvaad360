import json
from types import SimpleNamespace

import pytest

from cloud.config import CloudConfig, CloudError
from cloud.runtime_repair import diagnose, download_uri, repair, resolve, safe_error, selection


def report():
    return {"catalog": {"streamlit": ["1.52.2", "1.42.0", "1.65.0"],
                        "snowflake-snowpark-python": ["1.43.0"]}, "customer_count": 20}


def test_selection_refuses_arbitrary_commands_and_unsupported_versions():
    for command in ({"operation": "sql", "query": "DROP DATABASE"},
                    {"operation": "set_environment", "streamlit_version": "1.65.0", "snowpark_version": "1.43.0"},
                    {"operation": "set_environment", "streamlit_version": "1.52.2", "snowpark_version": "1.43.0'--"}):
        with pytest.raises(CloudError):
            selection(command, report())


def test_resolver_uses_bound_values_and_only_reports_classified_errors():
    class Cursor:
        def execute(self, query, params):
            assert query == "SELECT SYSTEM$RESOLVE_PYTHON_PACKAGES(%s, %s)"
            assert params == ("3.11", "('python==3.11.*', 'streamlit==1.52.2', 'snowflake-snowpark-python==1.43.0')")
            raise RuntimeError("packages failed; private-token")
    result = resolve(Cursor(), "1.52.2", "1.43.0")
    assert not result["ok"] and result["error"]["category"] == "PACKAGE_RESOLUTION_FAILED"
    assert "private-token" not in json.dumps(result)


def test_safe_errors_hide_provider_text_but_keep_codes():
    error = RuntimeError("External Offerings Terms required; private-token")
    error.errno, error.sqlstate = 123, "XX000"
    assert safe_error(error) == {"category": "PACKAGE_TERMS_OR_ENABLEMENT_REQUIRED", "type": "RuntimeError", "errno": 123, "sqlstate": "XX000"}


class Cursor:
    description = []
    def __init__(self, folder, account="TESTORG-ACCOUNT", role="SAMVAAD_HACKATHON"):
        self.folder, self.account, self.role = folder, account, role
        self.queries = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, query, params=None):
        self.queries.append(query)
        if query.startswith("SELECT CURRENT_"):
            self.rows = [(self.account, "OWNER", self.role, "TEST_REGION")]
        elif "SYSTEM$RESOLVE_PYTHON_PACKAGES" in query:
            self.rows = [(json.dumps(["streamlit==1.52.2", "snowflake-snowpark-python==1.43.0"]),)]
        elif "INFORMATION_SCHEMA.PACKAGES" in query:
            self.description = [("PACKAGE_NAME",), ("VERSION",)]
            self.rows = [("streamlit", "1.52.2"), ("snowflake-snowpark-python", "1.43.0")]
        elif query.startswith("DESCRIBE STREAMLIT"):
            self.description = [("name",), ("live_version_location_uri",)]
            self.rows = [("SAMVAAD360", "snow://streamlit/TEST_DB.APP.SAMVAAD360/versions/live/")]
        elif query.startswith("SELECT COUNT"):
            self.rows = [(20,)]
        elif query.startswith("GET "):
            if "after" in query:
                (self.folder / "after/environment.yml").write_bytes((self.folder / "environment.yml").read_bytes())
            else:
                (self.folder / "before/environment.yml").write_text("original environment\n")
        elif query.startswith("PUT ") or query.startswith("USE ") or query.startswith("ALTER STREAMLIT"):
            self.rows = []
        else:
            raise AssertionError(query)
    def fetchone(self):
        return self.rows[0]
    def fetchall(self):
        return self.rows


def test_wrong_account_is_refused_before_any_resource_change(tmp_path):
    cursor = Cursor(tmp_path, account="WRONG-ACCOUNT")
    with pytest.raises(CloudError, match="must match"):
        diagnose(SimpleNamespace(cursor=lambda: cursor), CloudConfig("test", "TEST_DB", "TEST_XS"), account="TESTORG-ACCOUNT", user="OWNER")
    assert len(cursor.queries) == 1


def test_repair_preserves_object_and_data_and_pins_resolved_versions(tmp_path):
    cursor = Cursor(tmp_path)
    connection = SimpleNamespace(cursor=lambda: cursor)
    result = repair(connection, CloudConfig("test", "TEST_DB", "TEST_XS"), tmp_path,
                    {"operation": "set_environment", "streamlit_version": "1.52.2", "snowpark_version": "1.43.0"}, report())
    assert result["status"] == "ENVIRONMENT_REPAIRED_HOSTED_CHECK_PENDING"
    assert result["changed_files"] == ["environment.yml"] and not result["customer_data_reloaded"]
    assert (tmp_path / "before/environment.yml").read_text() == "original environment\n"
    assert "snowflake-snowpark-python=1.43.0" in (tmp_path / "environment.yml").read_text()
    assert "python=3.11.*" in (tmp_path / "environment.yml").read_text()
    assert result["environment_readback_verified"]
    assert any(query.startswith("GET ") for query in cursor.queries)
    assert any(query.startswith("PUT ") for query in cursor.queries)
    assert not any(word in query for query in cursor.queries for word in ("CREATE ", "DROP ", "DELETE ", "INSERT ", "GRANT "))


def test_failed_resolver_prevents_live_file_mutation(tmp_path):
    class Failed(Cursor):
        def execute(self, query, params=None):
            if "SYSTEM$RESOLVE_PYTHON_PACKAGES" in query:
                self.queries.append(query)
                raise RuntimeError("specified packages cannot resolve")
            return super().execute(query, params)
    cursor = Failed(tmp_path)
    result = repair(SimpleNamespace(cursor=lambda: cursor), CloudConfig("test", "TEST_DB", "TEST_XS"), tmp_path,
                    {"operation": "set_environment", "streamlit_version": "1.52.2", "snowpark_version": "1.43.0"}, report())
    assert result["status"] == "REPAIR_BLOCKED_BY_PACKAGE_RESOLVER"
    assert not any(query.startswith(("GET ", "PUT ", "ALTER ")) for query in cursor.queries)


def test_windows_download_destination_does_not_have_drive_prefix_slash(tmp_path):
    from pathlib import Path
    import os
    value = download_uri(tmp_path)
    if os.name == "nt":
        assert value.startswith("file://" + Path(tmp_path).drive)
        assert not value.startswith("file:///")
    else:
        assert value.startswith("file:///")


def test_diagnostic_probes_the_exact_original_python_constraint(tmp_path):
    cursor = Cursor(tmp_path)
    original_execute = cursor.execute
    constraints = []
    def recording(query, params=None):
        if "SYSTEM$RESOLVE_PYTHON_PACKAGES" in query:
            constraints.append(params[1])
        return original_execute(query, params)
    cursor.execute = recording
    diagnose(SimpleNamespace(cursor=lambda: cursor), CloudConfig("test", "TEST_DB", "TEST_XS"), account="TESTORG-ACCOUNT", user="OWNER")
    assert constraints[0] == "('python==3.11', 'streamlit==1.52.2', 'snowflake-snowpark-python')"
    assert constraints[1] == "('python==3.11.*', 'streamlit==1.52.2', 'snowflake-snowpark-python')"
