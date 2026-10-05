import pytest

from cloud.config import CloudError
from scripts.package_github_release import build


@pytest.fixture(autouse=True)
def never_read_private_connection_profile(monkeypatch):
    from cloud import setup
    monkeypatch.setattr(setup, "private_connection_path", lambda: pytest.fail("CI packaging must not inspect a private connector profile or require the connector installation."))


def test_github_app_update_never_runs_bootstrap_or_reloads_customer_data(tmp_path):
    path, plan = build(account="TESTORG-ACCOUNT", viewer="OWNER", output=tmp_path)
    sql = path.read_text()
    assert "CURRENT_ORGANIZATION_NAME()" in sql and "wrong_target" in sql
    assert sql.index("RAISE wrong_target") < sql.index("PUT ")
    assert sql.count("PUT ") == len(plan["files"]) == 6
    assert "CREATE " not in sql and "GRANT " not in sql and "DELETE " not in sql and "INSERT " not in sql
    assert "COMMIT" in sql and "SAMVAAD360/versions/live/" in sql


def test_runtime_diagnostic_has_no_environment_pins_or_customer_queries(tmp_path):
    path, _ = build(account="TESTORG-ACCOUNT", viewer="OWNER", output=tmp_path, mode="runtime-check")
    sql = path.read_text()
    assert "CREATE OR REPLACE STREAMLIT" in sql and "SAMVAAD_RUNTIME_CHECK" in sql
    assert sql.count("PUT ") == 1 and "environment.yml" not in sql
    source = (tmp_path / "runtime-check/streamlit_app.py").read_text()
    assert "st.__version__" in source and "get_active_session" not in source and "repository" not in source
    assert not (tmp_path / "runtime-check/environment.yml").exists()


def test_github_target_cannot_inject_sql_or_another_operation(tmp_path):
    with pytest.raises(CloudError):
        build(account="TESTORG-ACCOUNT'; DROP DATABASE D", viewer="OWNER", output=tmp_path)
    with pytest.raises(ValueError):
        build(account="TESTORG-ACCOUNT", viewer="OWNER", output=tmp_path, mode="wipe-data")


def test_pinned_runtime_check_is_separate_from_the_main_and_default_apps(tmp_path):
    path, _ = build(account="TESTORG-ACCOUNT", viewer="OWNER", output=tmp_path, mode="runtime-pinned-check")
    sql = path.read_text()
    assert sql.count("PUT ") == 2 and "SAMVAAD_PINNED_RUNTIME_CHECK" in sql
    assert 'ALTER STREAMLIT "SAMVAAD_STAGING"."APP"."SAMVAAD_RUNTIME_CHECK"' not in sql
    assert "SAMVAAD360/versions/live/" not in sql
    assert not any(word in sql for word in ("GRANT ", "INSERT ", "DELETE ", "UPDATE "))
    environment = (tmp_path / "runtime-pinned-check/environment.yml").read_text()
    assert "python=3.11.15" in environment and "snowflake-snowpark-python=1.55.0" in environment
