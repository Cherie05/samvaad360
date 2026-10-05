"""Inspect hosted package metadata and exercise temporary Python UDFs via OIDC CLI."""
import json
import os
import re
import subprocess
from pathlib import Path

from cloud.config import CloudConfig


def query(sql):
    command = ["snow", "sql", "-x", "--format", "JSON", "-q", sql]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "CLIENT_TIMEOUT"}
    if result.returncode:
        # Never print arbitrary provider output or authentication diagnostics.
        message = result.stderr + result.stdout
        category = "SQL_FAILED"
        if "Packages not found" in message:
            category = "PACKAGE_NOT_FOUND"
        elif "specified packages" in message:
            category = "PACKAGE_COMPILATION_FAILED"
        elif "privilege" in message.lower() or "not authorized" in message.lower():
            category = "PRIVILEGE_OR_OBJECT_UNAVAILABLE"
        codes = re.findall(r"\b\d{6}\b", message)
        return {"ok": False, "error": category, "codes": sorted(set(codes))[:8]}
    try:
        # CLI multi-statement results can contain separate JSON documents.
        remaining, rows = result.stdout.strip(), []
        decoder = json.JSONDecoder()
        while remaining:
            value, offset = decoder.raw_decode(remaining)
            rows.extend(value if isinstance(value, list) else [value])
            remaining = remaining[offset:].strip()
        return {"ok": True, "rows": rows}
    except ValueError:
        return {"ok": False, "error": "UNEXPECTED_CLI_OUTPUT"}


def probes(config):
    prefix = "USE SECONDARY ROLES NONE; ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS=60; "
    catalog = config.object("INFORMATION_SCHEMA", "PACKAGES")
    queries = {
        "native_app": "DESCRIBE STREAMLIT " + config.object("APP", "SAMVAAD_RUNTIME_CHECK"),
        "main_app": "DESCRIBE STREAMLIT " + config.object("APP", "SAMVAAD360"),
        "python_catalog": f"SELECT DISTINCT PACKAGE_NAME, VERSION FROM {catalog} WHERE PACKAGE_NAME='python' AND (VERSION LIKE '3.11%' OR VERSION LIKE '3.10%') ORDER BY VERSION",
    }
    for name, runtime, libraries in (("python311", "3.11", False),
                                      ("python311_libraries", "3.11", True),
                                      ("python310", "3.10", False)):
        packages = " PACKAGES=('streamlit==1.52.2', 'snowflake-snowpark-python')" if libraries else ""
        body = "import platform, json\ndef run():\n    data = {'python': platform.python_version()}\n"
        if libraries:
            body += "    import streamlit\n    from importlib.metadata import version\n    data.update(streamlit=streamlit.__version__, snowpark=version('snowflake-snowpark-python'))\n"
        body += "    return json.dumps(data)\n"
        function = config.object("APP", "SAMVAAD_RUNTIME_PROBE")
        queries[name] = (f"CREATE TEMPORARY FUNCTION {function}() RETURNS VARCHAR LANGUAGE PYTHON "
                         f"RUNTIME_VERSION='{runtime}'{packages} HANDLER='run' AS $${body}$$; "
                         f"SELECT {function}() AS RUNTIME_RESULT")
    return {name: prefix + sql for name, sql in queries.items()}


def diagnose(account, config, execute=query):
    identity = execute("SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS ACCOUNT, "
                       "CURRENT_ROLE() AS ROLE, CURRENT_REGION() AS REGION, CURRENT_VERSION() AS SERVER_VERSION")
    if not identity.get("ok") or len(identity.get("rows", [])) != 1:
        raise ValueError("IDENTITY_CHECK_FAILED")
    row = {k.upper(): v for k, v in identity["rows"][0].items()}
    if str(row.get("ACCOUNT", "")).upper() != account.upper() or row.get("ROLE") != "SAMVAAD_HACKATHON":
        raise ValueError("WRONG_ACCOUNT_OR_ROLE")
    report = {"identity": row, "checks": {}}
    for name, sql in probes(config).items():
        result = execute(sql)
        if name.endswith("app") and result.get("ok"):
            fields = {"name", "runtime_name", "default_packages", "user_packages", "query_warehouse", "main_file"}
            result["rows"] = [{k: v for k, v in item.items() if k.lower() in fields} for item in result["rows"]]
        report["checks"][name] = result
    return report


def main():
    config = CloudConfig("github_oidc", os.environ["SNOWFLAKE_DATABASE"], os.environ["SNOWFLAKE_WAREHOUSE"])
    report = diagnose(os.environ["SNOWFLAKE_ACCOUNT"], config)
    folder = Path("output/cloud")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "github-runtime-diagnosis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RUNTIME_DIAGNOSIS " + json.dumps(report, separators=(",", ":")))


if __name__ == "__main__":
    main()
