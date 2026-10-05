"""Private, bounded diagnosis and environment-only repair of the deployed demo.

The interactive worker retains its authenticated connection briefly while the
developer examines a credential-free report. Its command inbox accepts only a
catalog-validated package selection or an exit command; never arbitrary SQL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

from cloud.config import CloudConfig, CloudError, WORKSPACE, identifier
from cloud.trial import APP, ROLE, authenticate, _named_rows

SUPPORTED = frozenset({"1.52.2", "1.52.1", "1.52.0", "1.51.0", "1.50.0",
                       "1.49.1", "1.48.0", "1.47.0", "1.46.1", "1.45.1",
                       "1.45.0", "1.44.1", "1.44.0", "1.42.0"})


def safe_error(error):
    # Inspect provider text solely to classify it. Never write it to reports.
    message = str(error).lower()
    category = "PROVIDER_ERROR"
    if getattr(error, "errno", None) == 253005:
        category = "LOCAL_DOWNLOAD_PATH_INVALID"
    elif "terms" in message or "anaconda is not enabled" in message:
        category = "PACKAGE_TERMS_OR_ENABLEMENT_REQUIRED"
    elif "permission" in message or "privilege" in message or "access control" in message:
        category = "INSUFFICIENT_PRIVILEGES"
    elif "package" in message or "dependenc" in message:
        category = "PACKAGE_RESOLUTION_FAILED"
    return {"category": error.code if isinstance(error, CloudError) else category,
            "type": type(error).__name__, "errno": getattr(error, "errno", None),
            "sqlstate": getattr(error, "sqlstate", None)}


def resolve(cursor, streamlit_version=None, snowpark_version=None, *, python_constraint="3.11.*"):
    values = ["python==" + python_constraint,
              "streamlit" + ("==" + streamlit_version if streamlit_version else ""),
              "snowflake-snowpark-python" + ("==" + snowpark_version if snowpark_version else "")]
    specification = "(" + ", ".join("'" + value + "'" for value in values) + ")"
    try:
        cursor.execute("SELECT SYSTEM$RESOLVE_PYTHON_PACKAGES(%s, %s)", ("3.11", specification))
        raw = cursor.fetchone()[0]
        packages = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
            raise CloudError("UNEXPECTED_RESOLVER_RESULT", "Package resolver did not return a package list.")
        return {"ok": True, "packages": packages}
    except Exception as error:
        return {"ok": False, "error": safe_error(error)}


def diagnose(connection, config, *, account, user):
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME(), CURRENT_USER(), CURRENT_ROLE(), CURRENT_REGION()")
        actual_account, actual_user, role, region = cursor.fetchone()
        if str(actual_account).upper() != account.upper() or actual_user != user or role != ROLE:
            raise CloudError("WRONG_ACCOUNT_USER_OR_ROLE", "The repair connection must match the deployed account, viewer and dedicated owner role.")
        cursor.execute("USE SECONDARY ROLES NONE")
        cursor.execute("USE WAREHOUSE " + identifier(config.warehouse))
        cursor.execute("USE DATABASE " + identifier(config.database))
        cursor.execute("USE SCHEMA APP")
        app = _named_rows(cursor, f"DESCRIBE STREAMLIT {config.object('APP', APP)}")
        catalog = _named_rows(cursor, f"SELECT PACKAGE_NAME, VERSION FROM {identifier(config.database)}.INFORMATION_SCHEMA.PACKAGES WHERE LANGUAGE='python' AND PACKAGE_NAME IN ('streamlit','snowflake-snowpark-python') ORDER BY PACKAGE_NAME, VERSION")
        versions = {name: sorted({r["version"] for r in catalog if r["package_name"] == name})
                    for name in ("streamlit", "snowflake-snowpark-python")}
        metadata_fields = ("name", "query_warehouse", "runtime_name", "default_packages", "user_packages", "live_version_location_uri", "last_version_name")
        metadata = [{k: row[k] for k in metadata_fields if k in row} for row in app]
        cursor.execute(f"SELECT COUNT(*) FROM {config.object('CORE', 'CUSTOMER_360')}")
        customers = cursor.fetchone()[0]
        original = resolve(cursor, "1.52.2", python_constraint="3.11")
        corrected_python = resolve(cursor, "1.52.2")
        default = resolve(cursor)
        return {"status": "DIAGNOSED_WAITING_FOR_ENVIRONMENT_SELECTION", "account": actual_account,
                "user": actual_user, "role": role, "region": region, "app": metadata,
                "catalog": versions, "original_packages": original,
                "python_patch_range_packages": corrected_python, "unpinned_packages": default,
                "customer_count": customers, "hosted_browser_verified": False,
                "production_ready": False, "credentials_saved": False}


def selection(command, report):
    if not isinstance(command, dict) or set(command) != {"operation", "streamlit_version", "snowpark_version"} or command["operation"] != "set_environment":
        raise CloudError("INVALID_REPAIR_COMMAND", "Only a validated environment selection is accepted.")
    st_version, sp_version = command["streamlit_version"], command["snowpark_version"]
    if not isinstance(st_version, str) or st_version not in SUPPORTED or st_version not in report["catalog"]["streamlit"]:
        raise CloudError("UNSUPPORTED_STREAMLIT_VERSION", "Select a documented warehouse Streamlit version present in this account's catalog.")
    if not isinstance(sp_version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", sp_version) or sp_version not in report["catalog"]["snowflake-snowpark-python"]:
        raise CloudError("UNSUPPORTED_SNOWPARK_VERSION", "Select an exact Snowpark version from this account's catalog.")
    return st_version, sp_version


def download_uri(path):
    # The connector normalizes /C:/ paths for PUT, but not for GET. Its GET
    # destination must be file://C:/... rather than file:///C:/... on Windows.
    path = Path(path).resolve()
    uri = "file://" + path.as_posix() if os.name == "nt" else path.as_uri()
    return uri.replace("'", "''") + "/"


def repair(connection, config, folder, command, report):
    st_version, sp_version = selection(command, report)
    with connection.cursor() as cursor:
        resolved = resolve(cursor, st_version, sp_version)
        if not resolved["ok"]:
            return {**report, "status": "REPAIR_BLOCKED_BY_PACKAGE_RESOLVER", "selected_packages": resolved}
        # Keep the object and every other app file. No table DDL/DML or grants.
        app_uri = f"snow://streamlit/{config.database.upper()}.APP.{APP}/versions/live/"
        backup = folder / "before"
        backup.mkdir(exist_ok=True)
        cursor.execute(f"GET '{app_uri}environment.yml' '{download_uri(backup)}'")
        original = backup / "environment.yml"
        if not original.is_file():
            raise CloudError("ENVIRONMENT_BACKUP_FAILED", "The live environment was not backed up; it was not overwritten.")
        target = folder / "environment.yml"
        target.write_text("name: samvaad-hackathon\nchannels:\n  - snowflake\ndependencies:\n  - python=3.11.*\n"
                          f"  - streamlit={st_version}\n  - snowflake-snowpark-python={sp_version}\n", encoding="utf-8")
        cursor.execute(f"PUT '{target.as_uri()}' '{app_uri}' AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        verification = folder / "after"
        verification.mkdir(exist_ok=True)
        cursor.execute(f"GET '{app_uri}environment.yml' '{download_uri(verification)}'")
        if not (verification / "environment.yml").is_file() or (verification / "environment.yml").read_bytes() != target.read_bytes():
            raise CloudError("ENVIRONMENT_READBACK_FAILED", "The live environment read-back differs from the selected environment. Inspect the recorded backup before further changes.")
        uploaded = _named_rows(cursor, f"DESCRIBE STREAMLIT {config.object('APP', APP)}")
        cursor.execute(f"ALTER STREAMLIT {config.object('APP', APP)} COMMIT")
        cursor.execute(f"SELECT COUNT(*) FROM {config.object('CORE', 'CUSTOMER_360')}")
        if cursor.fetchone()[0] != report["customer_count"]:
            raise CloudError("CUSTOMER_COUNT_CHANGED", "Customer counts changed during the repair; inspect concurrent cloud work.")
        return {**report, "status": "ENVIRONMENT_REPAIRED_HOSTED_CHECK_PENDING", "selected_packages": resolved,
                "streamlit_version": st_version, "snowpark_version": sp_version,
                "python_constraint": "3.11.*", "environment_readback_verified": True,
                "environment_before_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
                "environment_after_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "live_version_present": bool(uploaded and uploaded[0].get("live_version_location_uri")),
                "changed_files": ["environment.yml"], "customer_data_reloaded": False,
                "next": "Refresh the hosted app in Snowsight, then verify its four tabs."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--database", default="SAMVAAD_STAGING")
    parser.add_argument("--warehouse", default="SAMVAAD_XS")
    args = parser.parse_args(argv)
    folder = WORKSPACE / "output/cloud/runtime-repair"
    folder.mkdir(parents=True, exist_ok=True)
    inbox, target = folder / "command.json", folder / "result.json"
    # Never replay a command left from a prior connection.
    inbox.unlink(missing_ok=True)
    report = {"status": "WAITING_FOR_PRIVATE_LOGIN", "credentials_saved": False,
              "hosted_browser_verified": False, "production_ready": False}
    def save():
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(target)
    save()
    try:
        config = CloudConfig("samvaad_hackathon", args.database, args.warehouse)
        print("Diagnosing the hosted Python environment. Enter credentials only in this private terminal.", flush=True)
        with authenticate(args.account, args.user, skip_bootstrap=True) as connection:
            report = diagnose(connection, config, account=args.account, user=args.user)
            save()
            print("Package diagnostics saved. Keep this terminal open while the environment repair is selected.\nPasswords/MFA are not saved. The connection closes automatically after 15 minutes.", flush=True)
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                if inbox.is_file():
                    if inbox.stat().st_size > 4096:
                        raise CloudError("INVALID_REPAIR_COMMAND", "The repair command is too large.")
                    command = json.loads(inbox.read_text(encoding="utf-8"))
                    inbox.unlink()
                    if command == {"operation": "exit"}:
                        report["status"] = "DIAGNOSTICS_COMPLETE_NO_CHANGES"
                    else:
                        try:
                            report = repair(connection, config, folder, command, report)
                        except Exception as error:
                            report.update(status="REPAIR_FAILED_CONNECTION_OPEN", error=safe_error(error))
                            save()
                            print("Repair did not finish; connection remains open for a corrected bounded attempt. No credentials are saved.", flush=True)
                            continue
                    save()
                    print(report["status"], flush=True)
                    return 0 if "REPAIRED" in report["status"] or "NO_CHANGES" in report["status"] else 2
                time.sleep(0.5)
            report["status"] = "DIAGNOSTICS_COMPLETE_CONNECTION_CLOSED"
            save()
            return 0
    except Exception as error:
        report.update(status="REPAIR_INCOMPLETE", error=safe_error(error))
        save()
        print("Repair incomplete. Share only the status/error code, never credentials.", flush=True)
        return 2
