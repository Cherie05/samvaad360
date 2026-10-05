"""Build the six-file app release and an existing-app update script offline."""
import argparse
import hashlib
from pathlib import Path

from cloud.config import CloudConfig, identifier
from cloud.trial import APP, ROLE, package


def build(*, account, viewer, database="SAMVAAD_STAGING", warehouse="SAMVAAD_XS", output=None, mode="app"):
    if mode not in {"app", "runtime-check", "runtime-pinned-check"}:
        raise ValueError("Choose app, runtime-check or runtime-pinned-check release mode.")
    config = CloudConfig("samvaad_hackathon", database, warehouse)
    folder, plan = package(config, account=account, user=viewer, output=output, isolated_metadata=True)
    # configure() called by package validates account/viewer and identifier()
    # validates SQL object names before any SQL literals are generated here.
    app_uri = f"snow://streamlit/{database.upper()}.APP.{APP}/versions/live/"
    sql = [f"USE ROLE {identifier(ROLE)}", "USE SECONDARY ROLES NONE",
           f"USE WAREHOUSE {identifier(warehouse)}", f"USE DATABASE {identifier(database)}", "USE SCHEMA APP",
           "EXECUTE IMMEDIATE $$\nDECLARE\n wrong_target EXCEPTION (-20001, 'Deployment account or role differs from the release target.');\nBEGIN\n"
           f" IF (UPPER(CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME()) <> '{account.upper()}' OR CURRENT_ROLE() <> '{ROLE}') THEN\n"
           "  RAISE wrong_target;\n END IF;\nEND;\n$$",
           f"DESCRIBE STREAMLIT {config.object('APP', APP)}"]
    if mode == "app":
        for name in plan["files"]:
            local_uri = (folder / "app" / name).as_uri().replace("'", "''")
            sql.append(f"PUT '{local_uri}' '{app_uri}' AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        sql.append(f"ALTER STREAMLIT {config.object('APP', APP)} COMMIT")
    else:
        # No custom environment or customer reads: isolate native startup.
        check = folder / mode
        check.mkdir(exist_ok=True)
        source = check / "streamlit_app.py"
        source.write_text('import platform\nfrom importlib.metadata import version, PackageNotFoundError\nimport streamlit as st\n'
                          'st.title("Samvaad native runtime check")\n'
                          'def installed(name):\n    try:\n        return version(name)\n    except PackageNotFoundError:\n        return "not installed"\n'
                          'st.json({"python": platform.python_version(), "streamlit": st.__version__, "snowpark": installed("snowflake-snowpark-python")})\n'
                          'st.success("Snowflake default app runtime started successfully.")\n', encoding="utf-8")
        files = [source]
        diagnostic = "SAMVAAD_RUNTIME_CHECK"
        if mode == "runtime-pinned-check":
            # This account's actual catalog and successful temporary UDF
            # verified this full package combination on 5 October 2026.
            environment = check / "environment.yml"
            environment.write_text("name: samvaad-pinned-runtime-check\nchannels:\n  - snowflake\ndependencies:\n  - python=3.11.15\n  - streamlit=1.52.2\n  - snowflake-snowpark-python=1.55.0\n", encoding="utf-8")
            files.append(environment)
            diagnostic = "SAMVAAD_PINNED_RUNTIME_CHECK"
        stage = config.object("APP", "RELEASES") + "/runtime_check_" + hashlib.sha256(b"".join(file.read_bytes() for file in files)).hexdigest()[:16]
        for file in files:
            sql.append(f"PUT '{file.as_uri()}' @{stage} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        sql.append(f"CREATE OR REPLACE STREAMLIT {config.object('APP', diagnostic)} FROM '@{stage}' MAIN_FILE='streamlit_app.py' RUNTIME_NAME='SYSTEM$WAREHOUSE_RUNTIME' QUERY_WAREHOUSE={identifier(warehouse)} TITLE='Samvaad runtime check'")
        sql.append(f"ALTER STREAMLIT {config.object('APP', diagnostic)} ADD LIVE VERSION FROM LAST")
    sql.append(f"SELECT COUNT(*) AS CUSTOMERS FROM {config.object('CORE', 'CUSTOMER_360')}")
    path = folder / "04-release.sql"
    path.write_text(";\n".join(sql) + ";\n", encoding="utf-8")
    return path, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--viewer", required=True)
    parser.add_argument("--database", default="SAMVAAD_STAGING")
    parser.add_argument("--warehouse", default="SAMVAAD_XS")
    parser.add_argument("--output", default="output/cloud/github")
    parser.add_argument("--mode", choices=["app", "runtime-check", "runtime-pinned-check"], default="app")
    args = parser.parse_args()
    path, plan = build(**vars(args))
    count = {"runtime-check": 1, "runtime-pinned-check": 2}.get(args.mode, len(plan["files"]))
    print(f"Prepared {count} allowlisted {args.mode} files. Release script: {path}")


if __name__ == "__main__":
    main()
