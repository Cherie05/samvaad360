import subprocess
from types import SimpleNamespace

import pytest

from cloud.config import CloudConfig
from scripts.diagnose_github_runtime import diagnose, probes, query


def test_wrong_account_stops_before_any_diagnostic_function_creation():
    calls = []
    def execute(sql):
        calls.append(sql)
        return {"ok": True, "rows": [{"ACCOUNT": "WRONG-ACCOUNT", "ROLE": "SAMVAAD_HACKATHON"}]}
    with pytest.raises(ValueError, match="WRONG_ACCOUNT_OR_ROLE"):
        diagnose("TESTORG-ACCOUNT", CloudConfig("test", "TEST_DB", "TEST_XS"), execute)
    assert len(calls) == 1 and calls[0].startswith("SELECT CURRENT_")


def test_runtime_probes_are_temporary_and_do_not_modify_data_or_package_policies():
    queries = probes(CloudConfig("test", "TEST_DB", "TEST_XS"))
    for sql in queries.values():
        assert not any(word in sql for word in ("INSERT ", "UPDATE ", "DELETE ", "GRANT ", "ALTER STREAMLIT", "CREATE OR REPLACE", "ACCOUNTADMIN"))
    udf = queries["python311_libraries"]
    assert "CREATE TEMPORARY FUNCTION" in udf and "RUNTIME_VERSION='3.11'" in udf
    assert "PACKAGES=('streamlit==1.52.2', 'snowflake-snowpark-python')" in udf
    assert "python==" not in udf


def test_provider_errors_are_classified_and_multistatement_json_is_supported(monkeypatch):
    def failed(command, **kwargs):
        assert command[:5] == ["snow", "sql", "-x", "--format", "JSON"]
        return SimpleNamespace(returncode=1, stdout="", stderr="100357 Packages not found; private-token")
    monkeypatch.setattr(subprocess, "run", failed)
    assert query("SELECT 1") == {"ok": False, "error": "PACKAGE_NOT_FOUND", "codes": ["100357"]}
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout='[{"status":"created"}]\n[{"RUNTIME_RESULT":"3.11.15"}]'))
    assert query("SELECT 1")["rows"][-1] == {"RUNTIME_RESULT": "3.11.15"}
