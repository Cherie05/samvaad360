"""Prepare restricted public-demo snapshots and a dedicated key-pair reader.

Requires owner authentication in a visible private terminal. Owner password/MFA
are never saved. The generated service key is saved only in an ignored,
access-restricted local folder for upload to hosting secrets.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import tomllib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from cloud.config import CloudError, WORKSPACE
from cloud.runtime_repair import safe_error
from cloud.trial import authenticate, _named_rows
from public_app.repository import (
    ACCOUNT, DATABASE, PUBLIC_SCHEMA, READER_ROLE, SERVICE_USER, WAREHOUSE,
    IDENTITY_SQL, connect_reader,
)

TABLES = ("CUSTOMERS", "LOANS", "PAYMENTS", "INTERACTIONS")
OWNER = "ARUNVPP24"


def verify_portfolio(cursor, schema):
    if schema not in {"RAW", PUBLIC_SCHEMA}:
        raise CloudError("INVALID_PUBLIC_SOURCE", "Use only the reviewed synthetic schemas.")
    cursor.execute(f'SELECT CUSTOMER_ID, PAYLOAD FROM "{DATABASE}"."{schema}"."CUSTOMERS" '
                   "ORDER BY CUSTOMER_ID LIMIT 101")
    rows = cursor.fetchall()
    if {row[0] for row in rows} != {f"C{i:04}" for i in range(1, 21)} or len(rows) != 20:
        raise CloudError("SYNTHETIC_FIXTURE_MISMATCH", "The public snapshot requires the 20 approved fictional customers.")
    for cid, payload in rows:
        customer = json.loads(payload) if isinstance(payload, str) else payload
        if (customer.get("customer_id") != cid or customer.get("email") != cid.lower() + "@example.invalid"
                or customer.get("phone") != "******0000"):
            raise CloudError("SYNTHETIC_FIXTURE_MISMATCH", "Only fictional contact details may be published.")


def service_material(folder):
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        principal = os.environ["USERDOMAIN"] + "\\" + os.environ["USERNAME"]
        result = subprocess.run(["icacls", str(folder), "/inheritance:r", "/grant:r", principal + ":(OI)(CI)F"],
                                capture_output=True, timeout=20)
        if result.returncode:
            raise CloudError("PRIVATE_DIRECTORY_REQUIRED", "Could not restrict access to the service-key folder.")
    else:
        folder.chmod(0o700)
    path = folder / "secrets.toml"
    if path.exists():
        values = tomllib.loads(path.read_text(encoding="utf-8"))["snowflake"]
        key = serialization.load_pem_private_key(values["private_key"].encode(),
                                                password=values["private_key_passphrase"].encode())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        password = secrets.token_urlsafe(48)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.BestAvailableEncryption(password.encode())).decode()
        values = {"account": ACCOUNT, "user": SERVICE_USER, "role": READER_ROLE,
                  "warehouse": WAREHOUSE, "database": DATABASE, "private_key_passphrase": password,
                  "private_key": pem}
        body = "[snowflake]\n" + "".join(f'{k} = {json.dumps(v)}\n' for k, v in values.items())
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        if os.name != "nt":
            path.chmod(0o600)
    public_der = key.public_key().public_bytes(serialization.Encoding.DER,
                                               serialization.PublicFormat.SubjectPublicKeyInfo)
    public_key = base64.b64encode(public_der).decode()
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(public_der).digest()).decode()
    return values, public_key, fingerprint


def reader_grants():
    role = f'"{READER_ROLE}"'
    grants = [f'GRANT USAGE ON DATABASE "{DATABASE}" TO ROLE {role}',
              f'GRANT USAGE ON SCHEMA "{DATABASE}"."{PUBLIC_SCHEMA}" TO ROLE {role}',
              f'GRANT USAGE ON WAREHOUSE "{WAREHOUSE}" TO ROLE {role}']
    grants += [f'GRANT SELECT ON TABLE "{DATABASE}"."{PUBLIC_SCHEMA}"."{name}" TO ROLE {role}'
               for name in TABLES]
    return grants


def verify_reader_grants(cursor):
    allowed = {("USAGE", "DATABASE", DATABASE), ("USAGE", "SCHEMA", f"{DATABASE}.{PUBLIC_SCHEMA}"),
               ("USAGE", "WAREHOUSE", WAREHOUSE)}
    allowed |= {("SELECT", "TABLE", f"{DATABASE}.{PUBLIC_SCHEMA}.{name}") for name in TABLES}
    rows = _named_rows(cursor, f'SHOW GRANTS TO ROLE "{READER_ROLE}"')
    observed = {(str(r["privilege"]).upper(), str(r["granted_on"]).upper(), str(r["name"]).replace('"', '').upper())
                for r in rows}
    if not observed.issubset(allowed):
        raise CloudError("PUBLIC_ROLE_CONFLICT", "The reader role has unexpected privileges; no credentials may be published.")


def provision(cursor, report, public_key, fingerprint, save):
    cursor.execute(IDENTITY_SQL)
    identity = dict(zip([c[0].upper() for c in cursor.description], cursor.fetchone()))
    if identity.get("ACCOUNT") != ACCOUNT or identity.get("LOGIN") != OWNER or identity.get("ROLE") != "ACCOUNTADMIN":
        raise CloudError("WRONG_ACCOUNT_USER_OR_ROLE", "Use the expected account owner; no cloud resources were changed.")
    verify_portfolio(cursor, "RAW")
    roles = _named_rows(cursor, f"SHOW ROLES LIKE '{READER_ROLE}'")
    users = _named_rows(cursor, f"SHOW USERS LIKE '{SERVICE_USER}'")
    existing_role = any(r.get("name") == READER_ROLE for r in roles)
    existing_user = any(r.get("name") == SERVICE_USER for r in users)
    if existing_role and not report.get("role_created"):
        raise CloudError("PUBLIC_ROLE_EXISTS", "An existing reader role was preserved; inspect it before continuing.")
    if existing_user and not report.get("user_creation_started"):
        raise CloudError("PUBLIC_USER_EXISTS", "An existing service user's authentication was preserved.")
    if existing_role:
        verify_reader_grants(cursor)
    if existing_user:
        attributes = _named_rows(cursor, f'DESCRIBE USER "{SERVICE_USER}"')
        actual = next((r.get("value") for r in attributes if str(r.get("property", "")).upper() == "RSA_PUBLIC_KEY_FP"), None)
        if actual != fingerprint:
            raise CloudError("PUBLIC_KEY_CONFLICT", "The existing service key differs; no authentication was overwritten.")
    schemas = _named_rows(cursor, f'SHOW SCHEMAS LIKE \'{PUBLIC_SCHEMA}\' IN DATABASE "{DATABASE}"')
    if any(r.get("name") == PUBLIC_SCHEMA for r in schemas) and not report.get("schema_created"):
        raise CloudError("PUBLIC_SCHEMA_EXISTS", "An existing public schema was preserved; no tables were replaced.")
    if not report.get("schema_created"):
        cursor.execute(f'CREATE SCHEMA "{DATABASE}"."{PUBLIC_SCHEMA}" COMMENT=\'Approved fictional public demo snapshots\'')
        report["schema_created"] = True
        save()
    for table in TABLES:
        if table not in report.setdefault("cloned_tables", []):
            cursor.execute(f'CREATE TABLE "{DATABASE}"."{PUBLIC_SCHEMA}"."{table}" '
                           f'CLONE "{DATABASE}"."RAW"."{table}"')
            report["cloned_tables"].append(table)
            save()
    verify_portfolio(cursor, PUBLIC_SCHEMA)
    if not existing_role:
        cursor.execute(f'CREATE ROLE "{READER_ROLE}" COMMENT=\'Read-only fictional public website\'')
        report["role_created"] = True
        save()
    for query in reader_grants():
        cursor.execute(query)
    verify_reader_grants(cursor)
    if not existing_user:
        report["user_creation_started"] = True
        save()
        cursor.execute(f'CREATE USER "{SERVICE_USER}" TYPE=SERVICE '
                       f"DEFAULT_ROLE='{READER_ROLE}' DEFAULT_WAREHOUSE='{WAREHOUSE}' "
                       f"RSA_PUBLIC_KEY='{public_key}' COMMENT='Samvaad360 public synthetic reader'")
        report["user_created"] = True
        save()
    cursor.execute(f'GRANT ROLE "{READER_ROLE}" TO USER "{SERVICE_USER}"')
    user_grants = _named_rows(cursor, f'SHOW GRANTS TO USER "{SERVICE_USER}"')
    if any(r.get("role") not in {READER_ROLE, "PUBLIC"} for r in user_grants):
        raise CloudError("PUBLIC_USER_ROLE_CONFLICT", "The service user has an unexpected role; inspect it before deployment.")


def main():
    folder = WORKSPACE / ".local/public-cloud"
    target = WORKSPACE / "output/cloud/public-setup.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    report = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    report.update(account=ACCOUNT, service_user=SERVICE_USER, role=READER_ROLE, schema=PUBLIC_SCHEMA,
                  status="WAITING_FOR_PRIVATE_LOGIN", owner_password_saved=False, billing_changed=False,
                  website_published=False, live_ai_enabled=False)
    def save():
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    save()
    try:
        values, public_key, fingerprint = service_material(folder)
        report["public_key_fingerprint"] = fingerprint
        save()
        print("Connects a public website to four approved fictional Snowflake table snapshots.\n"
              "Enter the owner password and MFA privately here. They are hidden and never saved.", flush=True)
        with authenticate(ACCOUNT, OWNER) as connection:
            with connection.cursor() as cursor:
                provision(cursor, report, public_key, fingerprint, save)
        reader = connect_reader(values)
        count = len(reader.customers())
        reader.session.connection.close()
        if count != 20:
            raise CloudError("PUBLIC_READ_CHECK_FAILED", "The service connection did not return the expected demo customers.")
        report.update(status="PUBLIC_BACKEND_VERIFIED", customer_count=count, key_pair_login_verified=True,
                      service_secrets_path=".local/public-cloud/secrets.toml",
                      next="Create the public app on Streamlit Community Cloud and paste the service settings privately into hosting Secrets.")
        save()
        print("Public website backend connected: 20 fictional customers.\n"
              "Service settings saved privately. No owner password was saved. Return to the chat.", flush=True)
        return 0
    except Exception as error:
        report.update(status="PUBLIC_SETUP_INCOMPLETE", error=safe_error(error))
        save()
        print("Setup did not finish. Share only the status/error code, never credentials.", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
