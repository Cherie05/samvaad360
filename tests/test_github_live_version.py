import pytest

from cloud.config import CloudConfig
from scripts.ensure_github_live_version import ensure


CONFIG = CloudConfig("test", "TEST_DB", "TEST_XS")
IDENTITY = {"ok": True, "rows": [{"ACCOUNT": "TESTORG-ACCOUNT", "ROLE": "SAMVAAD_HACKATHON"}]}


def test_live_recovery_refuses_wrong_account_before_any_app_change():
    calls = []
    def execute(sql):
        calls.append(sql)
        return {"ok": True, "rows": [{"ACCOUNT": "WRONG-ACCOUNT", "ROLE": "SAMVAAD_HACKATHON"}]}
    with pytest.raises(ValueError, match="WRONG_ACCOUNT_OR_ROLE"):
        ensure("TESTORG-ACCOUNT", CONFIG, execute)
    assert len(calls) == 1 and calls[0].startswith("SELECT CURRENT_")


def test_existing_live_edits_are_preserved_without_commit_abort_or_recreate():
    calls = []
    def execute(sql):
        calls.append(sql)
        return IDENTITY if sql.startswith("SELECT") else {"ok": True, "rows": [{"name": "streamlit_app.py"}]}
    assert ensure("TESTORG-ACCOUNT", CONFIG, execute) == {"ready": True, "created": False}
    assert len(calls) == 2 and calls[1].startswith("GET ")


@pytest.mark.parametrize("missing_code", ["099108", "099112"])
def test_only_known_missing_version_error_allows_recovery(missing_code):
    calls = []
    def execute(sql):
        calls.append(sql)
        if sql.startswith("SELECT"):
            return IDENTITY
        if len(calls) == 2:
            return {"ok": False, "codes": [missing_code]}
        return {"ok": True, "rows": []}
    assert ensure("TESTORG-ACCOUNT", CONFIG, execute)["created"]
    assert calls[2] == 'ALTER STREAMLIT "TEST_DB"."APP"."SAMVAAD360" ADD LIVE VERSION FROM LAST'
    assert not any(word in sql for sql in calls for word in ("ABORT", "DROP ", "CREATE ", "DELETE ", "GRANT "))
    calls.clear()
    def denied(sql):
        calls.append(sql)
        return IDENTITY if sql.startswith("SELECT") else {"ok": False, "codes": ["002003"]}
    with pytest.raises(ValueError, match="LIVE_VERSION_INSPECTION_FAILED"):
        ensure("TESTORG-ACCOUNT", CONFIG, denied)
    assert len(calls) == 2
