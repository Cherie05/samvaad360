"""Credential boundary and safe local setup, not a successful cloud login."""
import json
import tomllib

import pytest

from cloud.config import CloudConfig, CloudError, connect
from cloud.setup import configure


def setup_args(tmp_path):
    return dict(account="testorg-testaccount", user="test_login", warehouse="TEST_WH",
                connections_path=tmp_path / "private/connections.toml", project_path=tmp_path / "project/cloud.toml")


def test_default_setup_is_a_plan_and_does_not_create_private_files(tmp_path):
    args = setup_args(tmp_path)
    report = configure(**args)
    assert report["status"] == "SETUP_PLAN"
    assert not report["cloud_contacted"] and not report["password_stored"]
    assert not args["connections_path"].exists() and not args["project_path"].exists()


def test_setup_preserves_other_connections_and_stores_no_credentials(tmp_path):
    args = setup_args(tmp_path)
    path = args["connections_path"]
    path.parent.mkdir()
    original = b'# User comment\n[other]\naccount="other-account"\npassword="test-only-sensitive-value"\n'
    path.write_bytes(original)
    configure(**args, apply=True)
    assert path.read_bytes().startswith(original)
    details = tomllib.loads(path.read_text())["samvaad_demo"]
    assert details["authenticator"] == "username_password_mfa"
    assert set(details) == {"account", "user", "warehouse", "authenticator"}
    assert tomllib.loads(args["project_path"].read_text())["snowflake"]["database"] == "SAMVAAD_STAGING"
    before = path.read_bytes()
    configure(**args, apply=True)
    assert path.read_bytes() == before


def test_conflicting_private_connection_never_overwrites_or_discloses_it(tmp_path):
    args = setup_args(tmp_path)
    path = args["connections_path"]
    path.parent.mkdir()
    original = b'[samvaad_demo]\npassword="secret-kept-private"\n'
    path.write_bytes(original)
    with pytest.raises(CloudError) as error:
        configure(**args, apply=True)
    assert error.value.code == "CONNECTION_EXISTS" and "secret-kept-private" not in str(error.value)
    assert path.read_bytes() == original and not args["project_path"].exists()


def test_conflicting_project_config_blocks_both_file_writes(tmp_path):
    args = setup_args(tmp_path)
    project = args["project_path"]
    project.parent.mkdir()
    original = '[snowflake]\nconnection_name="production"\nwarehouse="LIVE_WH"\ndatabase="LIVE_DB"\n'
    project.write_text(original)
    with pytest.raises(CloudError) as error:
        configure(**args, apply=True)
    assert error.value.code == "PROJECT_CONFIG_EXISTS"
    assert not args["connections_path"].exists() and project.read_text() == original


@pytest.mark.parametrize("value", ["https://test.snowflakecomputing.com", "test.snowflakecomputing.com", "x; DROP DATABASE DB", "a\nb", ""])
def test_setup_rejects_urls_and_injected_account_values(tmp_path, value):
    args = setup_args(tmp_path)
    args["account"] = value
    with pytest.raises(CloudError) as error:
        configure(**args, apply=True)
    assert error.value.code == "INVALID_ACCOUNT" and not args["connections_path"].exists()


def test_browser_auth_is_explicit_sso_and_blank_template_can_be_filled(tmp_path):
    args = setup_args(tmp_path)
    project = args["project_path"]
    project.parent.mkdir()
    project.write_text('[snowflake]\nconnection_name=""\nwarehouse=""\ndatabase="SAMVAAD_DB"\n')
    report = configure(**args, auth="externalbrowser", role="TEST_ROLE", apply=True)
    assert report["sso_required"]
    connection = tomllib.loads(args["connections_path"].read_text())["samvaad_demo"]
    assert connection["authenticator"] == "externalbrowser" and connection["role"] == "TEST_ROLE"


def test_password_prompt_rejects_noninteractive_input_before_login(monkeypatch):
    import sys
    import snowflake.connector
    import getpass
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(getpass, "getpass", lambda _: pytest.fail("Must not read a noninteractive password"))
    monkeypatch.setattr(snowflake.connector, "connect", lambda **kwargs: pytest.fail("Must not connect"))
    with pytest.raises(CloudError) as error:
        connect(CloudConfig("test", "TEST_DB", "TEST_WH"), prompt_password=True)
    assert error.value.code == "INTERACTIVE_TERMINAL_REQUIRED"


def test_interactive_password_is_not_persisted_or_exposed_on_provider_failure(monkeypatch, tmp_path):
    import sys
    import snowflake.connector
    import getpass
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "123456" if "MFA" in prompt else "only-in-memory-test-password")
    seen = {}
    def failed(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("provider exposed only-in-memory-test-password")
    monkeypatch.setattr(snowflake.connector, "connect", failed)
    with pytest.raises(CloudError) as error:
        connect(CloudConfig("test", "TEST_DB", "TEST_WH"), prompt_password=True)
    assert seen["password"] == "only-in-memory-test-password"
    assert seen["authenticator"] == "username_password_mfa"
    assert seen["passcode"] == "123456"
    assert "only-in-memory-test-password" not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_optional_mfa_code_can_be_empty_without_sending_an_empty_code(monkeypatch):
    import sys
    import snowflake.connector
    import getpass
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "" if "MFA" in prompt else "test-only-password")
    seen = {}
    marker = object()
    def connected(**kwargs):
        seen.update(kwargs)
        return marker
    monkeypatch.setattr(snowflake.connector, "connect", connected)
    assert connect(CloudConfig("test", "TEST_DB", "TEST_WH"), prompt_password=True) is marker
    assert "passcode" not in seen and seen["password"] == "test-only-password"


def test_connected_doctor_fails_if_selected_warehouse_is_not_visible(monkeypatch, capsys):
    from cloud.cli import main
    report = dict(connector_installed=True, configured_connection=True, named_connection_found=True,
                  existing_warehouse_selected=True, cloud_metadata_checked=True, selected_warehouse_visible=False)
    monkeypatch.setattr("cloud.cli.metadata_report", lambda config: report)
    assert main(["doctor", "--connect"]) == 2
    assert json.loads(capsys.readouterr().out)["selected_warehouse_visible"] is False


def test_existing_primary_directory_does_not_discover_fallback_connections(tmp_path, monkeypatch):
    from cloud.capabilities import connection_names
    primary = tmp_path / "primary"
    primary.mkdir()
    monkeypatch.setenv("SNOWFLAKE_HOME", str(primary))
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    (fallback / "connections.toml").write_text('[wrong_fallback]\naccount="test-test"\n')
    import platformdirs
    monkeypatch.setattr(platformdirs.PlatformDirs, "user_config_path", property(lambda self: fallback))
    assert connection_names() == []
