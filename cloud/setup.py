"""Create credential-free local connection metadata; never log in or provision."""
import json
import re
import tomllib
from pathlib import Path

from cloud.config import CloudConfig, CloudError, WORKSPACE, connection_name, identifier


def private_connection_path():
    try:
        from snowflake.connector.constants import CONNECTIONS_FILE
    except ImportError as exc:
        raise CloudError("CONNECTOR_MISSING", "Install requirements-cloud.txt before configuring a connection.") from exc
    return Path(CONNECTIONS_FILE)


def configure(*, account, user, warehouse, auth="password-mfa", name="samvaad_demo",
              database="SAMVAAD_STAGING", role=None, apply=False,
              connections_path=None, project_path=None):
    connection_name(name)
    if not isinstance(account, str) or not re.fullmatch(r"[A-Za-z0-9_]+-[A-Za-z0-9_-]+", account):
        raise CloudError("INVALID_ACCOUNT", "Copy the organization-account identifier from Snowsight, without a URL or domain suffix.")
    if not isinstance(user, str) or not user.strip() or len(user) > 255 or any(ord(c) < 32 for c in user):
        raise CloudError("INVALID_USER", "Provide your non-secret Snowflake login name.")
    if auth not in {"password-mfa", "externalbrowser"}:
        raise CloudError("INVALID_AUTH", "Choose password-mfa for native login or externalbrowser for configured SSO.")
    config = CloudConfig(name, database, warehouse)
    config.require_warehouse()
    details = {"account": account, "user": user, "warehouse": warehouse,
               "authenticator": "username_password_mfa" if auth == "password-mfa" else "externalbrowser"}
    if role:
        identifier(role)
        details["role"] = role
    private = Path(connections_path) if connections_path else private_connection_path()
    project = Path(project_path) if project_path else WORKSPACE / ".local/cloud.toml"
    try:
        existing_bytes = private.read_bytes() if private.exists() else b""
        existing = tomllib.loads(existing_bytes.decode("utf-8"))
        project_bytes = project.read_bytes() if project.exists() else b""
        project_document = tomllib.loads(project_bytes.decode("utf-8")) if project_bytes else {}
    except (OSError, UnicodeError, ValueError) as exc:
        raise CloudError("INVALID_CONFIG", "Existing connection configuration is unreadable. Repair it privately; its contents were not printed.") from exc
    if name in existing and existing[name] != details:
        raise CloudError("CONNECTION_EXISTS", "That connection already has different settings. Choose a new name; existing entries are never replaced.")
    settings = {"connection_name": name, "database": database, "warehouse": warehouse}
    if project_document:
        if set(project_document) != {"snowflake"} or not isinstance(project_document["snowflake"], dict):
            raise CloudError("PROJECT_CONFIG_EXISTS", "Review the existing project cloud configuration before changing it.")
        values = project_document["snowflake"]
        blank_template = (set(values) <= set(settings) and not values.get("connection_name") and not values.get("warehouse"))
        if values != settings and not blank_template:
            raise CloudError("PROJECT_CONFIG_EXISTS", "The project already references a different connection. Existing configured values are not overwritten.")
    table = lambda title, values: "[" + title + "]\n" + "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items())
    private_addition = table(json.dumps(name), details).encode("utf-8")
    project_content = "# Non-secret staging configuration; passwords are prompted locally.\n" + table("snowflake", settings)
    report = {"status": "CONFIGURED" if apply else "SETUP_PLAN", "connection_name": name,
              "account": account, "user": user, "warehouse": warehouse, "database": database,
              "auth": auth, "private_connections_path": str(private), "project_config_path": str(project),
              "password_stored": False, "cloud_contacted": False, "cloud_deployed": False,
              "sso_required": auth == "externalbrowser"}
    if not apply:
        return report
    private.parent.mkdir(parents=True, exist_ok=True)
    project.parent.mkdir(parents=True, exist_ok=True)
    # Append rather than rewrite a user's private file, preserving its existing
    # contents and ACL. Refuse changes that occurred after the initial read.
    if name not in existing:
        if private.exists():
            with private.open("r+b") as handle:
                if handle.read() != existing_bytes:
                    raise CloudError("CONFIG_CHANGED", "Connection configuration changed during setup. Retry after reviewing it.")
                handle.write(b"\n" + private_addition)
        else:
            import os
            descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(private_addition)
    if project.exists() and project.read_bytes() != project_bytes:
        raise CloudError("CONFIG_CHANGED", "Project configuration changed during setup. The named connection was preserved; review project settings.")
    project.write_text(project_content, encoding="utf-8")
    return report
