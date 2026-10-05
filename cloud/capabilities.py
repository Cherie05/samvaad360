"""Read-only discovery; never prints credential dictionaries or provider errors."""

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from cloud.config import CloudConfig, WORKSPACE, connect, identifier


def connection_names() -> list[str]:
    home = Path(os.getenv("SNOWFLAKE_HOME", str(Path.home() / ".snowflake"))).expanduser()
    # The connector selects by directory existence, not by file existence.
    # A missing file inside an existing ~/.snowflake must not reveal fallback
    # connections that the connector itself would never load.
    if home.exists():
        target = home / "connections.toml"
    else:
        try:
            from platformdirs import PlatformDirs
            target = Path(PlatformDirs("snowflake", appauthor=False).user_config_path) / "connections.toml"
        except ImportError:
            target = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "snowflake" / "connections.toml"
    if not target.exists():
        return []
    try:
        document = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted(key for key, value in document.items() if isinstance(value, dict))


def cortex_path() -> str | None:
    found = shutil.which("cortex")
    if found:
        return found
    root = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "cortex"
    candidate = root / "cortex.exe"
    if candidate.is_file():
        return str(candidate)
    # The current native installer puts the executable under a version folder.
    candidates = [item for item in root.glob("*/cortex.exe") if item.is_file()]
    return str(max(candidates, key=lambda item: item.stat().st_mtime)) if candidates else None



def offline_report(config: CloudConfig) -> dict:
    try:
        connector_version = importlib.metadata.version("snowflake-connector-python")
    except importlib.metadata.PackageNotFoundError:
        connector_version = None
    available = connection_names()
    return {
        "cloud_deployed": False, "application_backend": "local SQLite; SnowflakeService not implemented",
        "connector_installed": connector_version is not None, "connector_version": connector_version,
        "configured_connection": bool(config.connection_name), "named_connection_found": config.connection_name in available,
        "available_connection_names": available, "existing_warehouse_selected": bool(config.warehouse),
        "coco_executable_found": cortex_path() is not None, "cloud_metadata_checked": False,
        "hybrid_tables": "Account-dependent; unavailable in standard trial accounts. No hybrid workflow deployed.",
        "coco_trial_requirement": "Paid or dedicated CoCo trial account; standard Snowflake trial is unsupported.",
    }


def metadata_report(config: CloudConfig, *, prompt_password: bool = False) -> dict:
    report = offline_report(config)
    with (connect(config, prompt_password=True) if prompt_password else connect(config)) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT CURRENT_ACCOUNT(),CURRENT_REGION(),CURRENT_ROLE(),CURRENT_WAREHOUSE(),CURRENT_VERSION()")
            account, region, role, warehouse, version = cursor.fetchone()
            report.update({"cloud_metadata_checked": True, "account": account, "region": region, "role": role, "session_warehouse": warehouse, "snowflake_version": version})
            checks = {
                "warehouses": "SHOW WAREHOUSES",
                "cortex_models": "SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS",
                "cortex_search_services": f"SHOW CORTEX SEARCH SERVICES IN DATABASE {identifier(config.database)}",
            }
            for name, query in checks.items():
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    report[name] = {"visible_count": len(rows), "metadata_access": True}
                    if name == "warehouses":
                        columns = [item[0].lower() for item in cursor.description]
                        index = columns.index("name")
                        report["selected_warehouse_visible"] = any(str(row[index]).upper() == config.warehouse.upper() for row in rows)
                except Exception as exc:
                    report[name] = {"metadata_access": False, "error_type": type(exc).__name__, "error_code": getattr(exc, "errno", None)}
        finally:
            cursor.close()
    return report


def coco_report(config: CloudConfig, *, run_smoke: bool = False) -> dict:
    executable = cortex_path()
    report = {"executable_found": bool(executable), "version": None, "help_verified": False, "model_smoke_attempted": False, "model_smoke_verified": False, "project_skills_runtime_verified": False, "project_hook_runtime_verified": False}
    if not executable:
        report["blocker"] = "CoCo CLI executable is not installed or discoverable."
        return report
    try:
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=15, cwd=WORKSPACE)
        match = re.search(r"\bv?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)\b", version.stdout + "\n" + version.stderr)
        report["version"] = match.group(1) if match else None
        help_result = subprocess.run([executable, "--help"], capture_output=True, text=True, timeout=15, cwd=WORKSPACE)
        required = ("--print", "--connection", "--max-turns", "--private", "--mode", "--disallowed-tools")
        report["help_verified"] = help_result.returncode == 0 and all(flag in help_result.stdout for flag in required)
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["blocker"] = "Local CoCo version/help check failed: " + type(exc).__name__
        return report
    if not run_smoke:
        report["blocker"] = "Account/model smoke was not requested; use --run-smoke after configuring an enabled CoCo connection."
        return report
    config.require_connection()
    if not report["help_verified"]:
        report["blocker"] = "Installed CoCo help does not advertise all required smoke flags. Update or review CLI compatibility."
        return report
    import secrets
    nonce = "SAMVAAD_SMOKE_" + secrets.token_hex(12)
    command = [executable, "--connection", config.connection_name, "--mode", "code", "--max-turns", "1", "--private", "--disallowed-tools", "*", "--print", f"Reply with exactly {nonce} on one line. Do not use tools, read files, execute commands, or query account data."]
    report["model_smoke_attempted"] = True
    try:
        result = subprocess.run(command, cwd=WORKSPACE, capture_output=True, text=True, timeout=60)
        report["exit_code"] = result.returncode
        report["model_smoke_verified"] = result.returncode == 0 and nonce in [line.strip() for line in result.stdout.splitlines()]
        if not report["model_smoke_verified"]:
            report["blocker"] = "CoCo did not return the exact smoke marker successfully. Check its private authentication/model session; provider output was not printed."
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["blocker"] = "CoCo model smoke failed: " + type(exc).__name__
    report["scope"] = "Model authentication only; code mode disables skills. No project skill or runtime hook verification is claimed."
    return report
