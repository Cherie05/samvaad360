"""Strict non-secret configuration and safe Snowflake identifier rendering."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]


class CloudError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        raise CloudError("INVALID_IDENTIFIER", "Use one unquoted SQL identifier containing letters, digits, or underscores.")
    return '"' + value.upper() + '"'


def connection_name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value):
        raise CloudError("CONNECTION_REQUIRED", "Configure a named Snowflake connection before attempting a cloud operation.")
    return value


@dataclass(frozen=True)
class CloudConfig:
    connection_name: str = ""
    database: str = "SAMVAAD_DB"
    warehouse: str = ""

    def __post_init__(self):
        identifier(self.database)
        if self.warehouse:
            identifier(self.warehouse)
        if self.connection_name:
            connection_name(self.connection_name)

    def require_connection(self):
        connection_name(self.connection_name)

    def require_warehouse(self):
        if not self.warehouse:
            raise CloudError("WAREHOUSE_REQUIRED", "Choose an existing warehouse in .local/cloud.toml. These tools never create a warehouse.")
        identifier(self.warehouse)

    def object(self, schema: str, name: str) -> str:
        return ".".join(identifier(part) for part in (self.database, schema, name))


def read_config(path: str | Path | None = None) -> CloudConfig:
    target = Path(path or os.getenv("SAMVAAD_CLOUD_CONFIG", str(WORKSPACE / ".local" / "cloud.toml")))
    values = {}
    if target.exists():
        try:
            document = tomllib.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CloudError("INVALID_CONFIG", "Cloud configuration could not be read as TOML.") from exc
        if set(document) != {"snowflake"} or not isinstance(document.get("snowflake"), dict):
            raise CloudError("INVALID_CONFIG", "Cloud config must contain only a [snowflake] section.")
        values = document["snowflake"]
        if not set(values).issubset({"connection_name", "database", "warehouse"}):
            raise CloudError("INVALID_CONFIG", "Cloud config accepts only connection_name, database, and warehouse; keep credentials in private Snowflake configuration.")
    return CloudConfig(
        connection_name=os.getenv("SAMVAAD_SNOWFLAKE_CONNECTION", values.get("connection_name", "")),
        database=os.getenv("SAMVAAD_SNOWFLAKE_DATABASE", values.get("database", "SAMVAAD_DB")),
        warehouse=os.getenv("SAMVAAD_SNOWFLAKE_WAREHOUSE", values.get("warehouse", "")),
    )


def connect(config: CloudConfig, *, prompt_password: bool = False):
    config.require_connection()
    try:
        import snowflake.connector
    except ImportError as exc:
        raise CloudError("CONNECTOR_MISSING", "Install optional requirements-cloud.txt before connecting to Snowflake.") from exc
    authentication = {}
    if prompt_password:
        import sys
        import getpass
        if not sys.stdin.isatty():
            raise CloudError("INTERACTIVE_TERMINAL_REQUIRED", "Run --prompt-password yourself in a local terminal. Passwords are never accepted in chat, arguments, or redirected input.")
        password = getpass.getpass("Snowflake password (hidden; not stored): ")
        if not password:
            raise CloudError("PASSWORD_REQUIRED", "No password was entered. No connection was attempted.")
        authentication = {"password": password, "authenticator": "username_password_mfa"}
        passcode = getpass.getpass("MFA authenticator-app code (hidden; Enter if your account does not require one): ").strip()
        if passcode:
            authentication["passcode"] = passcode
    try:
        return snowflake.connector.connect(
            connection_name=config.connection_name,
            login_timeout=20, network_timeout=30,
            session_parameters={"QUERY_TAG": "samvaad-cloud-preparation", "STATEMENT_TIMEOUT_IN_SECONDS": 60},
            **authentication,
        )
    except Exception as exc:
        raise CloudError("CONNECTION_FAILED", "The configured Snowflake connection could not be established. Verify its private credentials, MFA, network access, and account enablement.") from exc
