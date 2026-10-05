"""New-account hackathon setup and an explicit warehouse-runtime app release.

Plan mode is offline. Apply requires private authentication in a local terminal.
No billing, account allowlists, cross-region inference or public grants change.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

from cloud.config import CloudConfig, CloudError, WORKSPACE, identifier
from cloud.fixtures import build_bundle, canonical, load_fixture
from cloud.setup import configure
from cloud.sql_assets import render, statements

ROLE = "SAMVAAD_HACKATHON"
WAREHOUSE = "SAMVAAD_XS"
MONITOR = "SAMVAAD_DAILY_LIMIT"
APP = "SAMVAAD360"


def bootstrap(config, user, quota):
    if isinstance(quota, bool) or not isinstance(quota, int) or not 1 <= quota <= 10:
        raise CloudError("INVALID_BUDGET", "Choose a daily warehouse quota of 1–10 credits; it does not cap AI or total account spend.")
    values = {"DB": identifier(config.database), "WH": identifier(config.warehouse),
              "ROLE": identifier(ROLE), "LOGIN": identifier(user),
              "MONITOR": identifier(MONITOR), "QUOTA": str(quota)}
    text = (WORKSPACE / "cloud/sql/000_trial_bootstrap.sql").read_text(encoding="utf-8")
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda match: values[match[1]], text)


def package(config, *, account, user, quota=5, output=None):
    # Reuse the credential-free setup validation without writing configuration.
    setup = configure(account=account, user=user, warehouse=config.warehouse,
                      name=config.connection_name, database=config.database, role=ROLE)
    folder = Path(output or WORKSPACE / "output/cloud/trial").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    release = folder / "app"
    release.mkdir(exist_ok=True)
    source = WORKSPACE / "cloud/demo_app"
    for name in ("streamlit_app.py", "demo_repository.py", "environment.yml"):
        shutil.copyfile(source / name, release / name)
    shutil.copyfile(WORKSPACE / "samvaad/engine.py", release / "domain_engine.py")
    settings = {"database": config.database, "account": account,
                "allowed_viewers": [user], "cortex_model": "llama3.3-70b",
                "synthetic_only": True, "external_delivery": False}
    (release / "demo_settings.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    (release / "README.md").write_text(
        "# Samvaad 360 cloud hackathon demo\n\n"
        "Private Snowflake-hosted Customer 360, bounded optional Cortex answers and a synthetic review ledger. "
        "The review ledger does not execute loans, change premiums, send invitations or place calls. "
        "Only allowlisted Snowsight viewers can load data. No secrets, local database or voice weights are included. "
        "Warehouse runtime / Python 3.11 / Streamlit 1.52.2.\n", encoding="utf-8")
    names = ("streamlit_app.py", "demo_repository.py", "environment.yml", "domain_engine.py", "demo_settings.json", "README.md")
    hashes = {name: hashlib.sha256((release / name).read_bytes()).hexdigest() for name in names}
    release_hash = hashlib.sha256(canonical(hashes).encode()).hexdigest()
    with zipfile.ZipFile(folder / "samvaad360-cloud.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(release / name, arcname=name)
    fixture = build_bundle()
    (folder / "fixtures.json").write_text(canonical(fixture) + "\n", encoding="utf-8")
    initial_sql = bootstrap(config, user, quota)
    (folder / "01-bootstrap.sql").write_text(initial_sql, encoding="utf-8")
    # Bootstrap already creates the database as ACCOUNTADMIN, while the app
    # role receives only USAGE/CREATE SCHEMA, not account-wide CREATE DATABASE.
    schema_statements = statements(render("schema", config))[1:]
    schema_sql = ";\n".join(schema_statements) + ";\n" + render("views", config)
    review_sql = (WORKSPACE / "cloud/sql/005_demo_reviews.sql").read_text(encoding="utf-8").replace("{{DB}}", identifier(config.database))
    (folder / "02-schema.sql").write_text(schema_sql + "\n" + review_sql, encoding="utf-8")
    stage = config.object("APP", "RELEASES") + "/release_" + release_hash[:16]
    create_sql = (f"CREATE STREAMLIT {config.object('APP', APP)}\n FROM '@{stage}'\n MAIN_FILE='streamlit_app.py'\n"
                  f" RUNTIME_NAME='SYSTEM$WAREHOUSE_RUNTIME'\n QUERY_WAREHOUSE={identifier(config.warehouse)}\n"
                  " TITLE='Samvaad 360';\n"
                  f"ALTER STREAMLIT {config.object('APP', APP)} ADD LIVE VERSION FROM LAST;\n")
    (folder / "03-publish.sql").write_text(create_sql, encoding="utf-8")
    report = {"status": "OFFLINE_PACKAGE_READY", "account": account, "user": user,
              "warehouse": config.warehouse, "warehouse_creation_pending": True,
              "database": config.database, "app": APP, "role": ROLE,
              "daily_warehouse_credit_quota": quota, "ai_spend_capped_by_resource_monitor": False,
              "release_sha256": release_hash, "files": hashes, "stage": stage,
              "fixture_counts": fixture["counts"], "fixture_sha256": fixture["sha256"],
              "private_setup": setup, "cloud_contacted": False, "cloud_deployed": False,
              "hosted_browser_verified": False, "hackathon_activation": "Owner reports organizer activation link; privileges still require a live check",
              "completed_steps": [], "production_ready": False, "real_calls_enabled": False}
    (folder / "plan.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return folder, report


def authenticate(account, user, *, skip_bootstrap=False):
    if not sys.stdin.isatty():
        raise CloudError("INTERACTIVE_TERMINAL_REQUIRED", "Run cloud setup in your own local terminal. Password/MFA values are not accepted in chat or arguments.")
    import snowflake.connector
    password = getpass.getpass("Snowflake password (hidden; not saved): ")
    if not password:
        raise CloudError("PASSWORD_REQUIRED", "No password was entered; no connection was attempted.")
    code = getpass.getpass("Authenticator-app MFA code (hidden; Enter if not required): ").strip()
    options = {"account": account, "user": user, "password": password,
               "authenticator": "username_password_mfa", "role": ROLE if skip_bootstrap else "ACCOUNTADMIN",
               "login_timeout": 30, "network_timeout": 60,
               "session_parameters": {"QUERY_TAG": "samvaad-hackathon-setup", "STATEMENT_TIMEOUT_IN_SECONDS": 60}}
    if code:
        options["passcode"] = code
    try:
        return snowflake.connector.connect(**options)
    except Exception as error:
        raise CloudError("CONNECTION_FAILED", "Private login did not complete. Check password/MFA and account-owner access in Snowsight; nothing was provisioned by this attempt.") from error


def _named_rows(cursor, sql):
    cursor.execute(sql)
    columns = [c[0].lower() for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def apply_package(connection, config, folder, plan, *, account, user, skip_bootstrap=False):
    progress = {**plan, "status": "STARTED", "cloud_contacted": True, "completed_steps": []}
    target = folder / "result.json"
    def save():
        target.write_text(json.dumps(progress, indent=2, default=str) + "\n", encoding="utf-8")
    save()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME(), CURRENT_USER(), CURRENT_ROLE(), CURRENT_REGION()")
            actual_account, actual_user, role, region = cursor.fetchone()
            if str(actual_account).upper() != account.upper() or str(actual_user) != user:
                raise CloudError("WRONG_ACCOUNT_OR_USER", "The authenticated account/user differs from the reviewed setup plan; no resources were created.")
            progress["session"] = {"account": actual_account, "user": actual_user, "initial_role": role, "region": region}
            progress["completed_steps"].append("private_authentication_and_account_check")
            # An existing large or differently configured warehouse is not
            # silently adopted or resized by a setup for a new account.
            existing = [r for r in _named_rows(cursor, "SHOW WAREHOUSES") if r["name"].upper() == config.warehouse.upper()]
            if existing and (existing[0].get("size") != "X-Small" or str(existing[0].get("auto_suspend")) != "60"):
                raise CloudError("WAREHOUSE_CONFLICT", "The planned warehouse already has different size/suspend settings. Review it privately before rerunning setup.")
            if not skip_bootstrap:
                monitors = [r for r in _named_rows(cursor, "SHOW RESOURCE MONITORS") if r["name"].upper() == MONITOR]
                if monitors and (float(monitors[0].get("credit_quota", 0)) != plan["daily_warehouse_credit_quota"]
                                 or str(monitors[0].get("frequency", "")).upper() != "DAILY"):
                    raise CloudError("MONITOR_CONFLICT", "The planned resource monitor already has different quota/frequency settings. Existing limits were preserved.")
                for statement in statements((folder / "01-bootstrap.sql").read_text(encoding="utf-8")):
                    cursor.execute(statement)
            else:
                cursor.execute("USE ROLE " + identifier(ROLE))
                cursor.execute("USE SECONDARY ROLES NONE")
            cursor.execute("USE WAREHOUSE " + identifier(config.warehouse))
            progress["warehouse_creation_pending"] = False
            progress["completed_steps"].append("warehouse_role_monitor_and_database")
            save()
            for statement in statements((folder / "02-schema.sql").read_text(encoding="utf-8")):
                cursor.execute(statement)
            progress["completed_steps"].append("analytical_schema_views_and_demo_ledger")
            save()
        fixture = json.loads((folder / "fixtures.json").read_text(encoding="utf-8"))
        progress["fixture_import"] = load_fixture(connection, config, fixture)
        progress["completed_steps"].append("synthetic_fixture_import_reconciled")
        save()
        with connection.cursor() as cursor:
            rows = _named_rows(cursor, f"SHOW STREAMLITS IN SCHEMA {identifier(config.database)}.APP")
            if any(r["name"].upper() == APP for r in rows):
                raise CloudError("APP_ALREADY_EXISTS", "The app already exists. Open it in Projects > Streamlit; this setup does not replace a prior app silently.")
            for name, expected_hash in plan["files"].items():
                source = folder / "app" / name
                if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
                    raise CloudError("RELEASE_CHANGED", "A packaged app file changed after planning. Regenerate and review the package.")
                uri = source.as_uri().replace("'", "''")
                cursor.execute(f"PUT '{uri}' @{plan['stage']} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
            progress["completed_steps"].append("reviewed_app_files_uploaded")
            save()
            for statement in statements((folder / "03-publish.sql").read_text(encoding="utf-8")):
                cursor.execute(statement)
            cursor.execute(f"SELECT COUNT(*) FROM {config.object('CORE', 'CUSTOMER_360')}")
            if cursor.fetchone()[0] != fixture["counts"]["customers"]:
                raise CloudError("VIEW_RECONCILIATION_FAILED", "Customer 360 row counts differ. Review the cloud tables before using the demo.")
            progress["cloud_deployed"] = True
            progress["completed_steps"].append("streamlit_live_version_and_customer360_count")
        configure(account=account, user=user, warehouse=config.warehouse, database=config.database,
                  name=config.connection_name, role=ROLE, apply=True)
        progress["completed_steps"].append("credential_free_local_connection_saved")
        progress["status"] = "CLOUD_DEMO_PUBLISHED_BROWSER_CHECK_PENDING"
        progress["next"] = "Snowsight: Projects > Streamlit > SAMVAAD360. Use SAMVAAD_HACKATHON and verify the four demo tabs. Cortex/model access and CoCo still need their own runtime checks."
        save()
        return progress
    except Exception as error:
        progress["status"] = "SETUP_INCOMPLETE"
        progress["error"] = error.code if isinstance(error, CloudError) else type(error).__name__
        progress["message"] = error.message if isinstance(error, CloudError) else "A cloud step failed. Completed steps remain recorded; DDL is not rolled back as a whole. Inspect privileges and account capabilities privately."
        save()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--warehouse", default=WAREHOUSE)
    parser.add_argument("--database", default="SAMVAAD_STAGING")
    parser.add_argument("--connection-name", default="samvaad_hackathon")
    parser.add_argument("--daily-credits", type=int, default=5)
    parser.add_argument("--output", default=None)
    parser.add_argument("--apply", action="store_true", help="Privately authenticate, provision and publish the synthetic cloud demo")
    parser.add_argument("--skip-bootstrap", action="store_true", help="Use the already provisioned SAMVAAD_HACKATHON role")
    args = parser.parse_args(argv)
    try:
        config = CloudConfig(args.connection_name, args.database, args.warehouse)
        folder, report = package(config, account=args.account, user=args.user, quota=args.daily_credits, output=args.output)
        if args.apply:
            print("Setting up the synthetic hackathon demo. No payment method, upgrade, outbound calls or account-wide AI settings will change.", flush=True)
            with authenticate(args.account, args.user, skip_bootstrap=args.skip_bootstrap) as connection:
                report = apply_package(connection, config, folder, report, account=args.account, user=args.user, skip_bootstrap=args.skip_bootstrap)
        print(json.dumps(report, indent=2, default=str))
        return 0
    except CloudError as error:
        print(json.dumps({"status": "BLOCKED", "error": error.code, "message": error.message}))
        return 2
    except Exception as error:
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__, "message": "Cloud setup did not finish. Review the saved credential-free result and account capabilities; provider exceptions were not printed."}))
        return 2

