"""Secret-free native CoCo submission preflight; model access is explicitly opt-in.

Skill discovery, local Python execution, and hook-shaped JSON are not counted
as genuine CoCo workflow execution. Keep native tool traces and the recording.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sqlite3
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from cloud.capabilities import cortex_path


WORKSPACE = Path(__file__).resolve().parents[1]
ISOLATED = WORKSPACE / ".local" / "submission-coco"
SKILLS = ("samvaad-evidence", "samvaad-generate", "samvaad-approved-runner")


def _native(binary, args, timeout=15):
    return subprocess.run([binary, *args], cwd=WORKSPACE, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _auth_metadata():
    target = Path.home() / ".snowflake" / "connections.toml"
    value = {}
    try:
        if target.is_file():
            value = tomllib.loads(target.read_text(encoding="utf-8")).get("samvaad_hackathon", {})
    except (OSError, ValueError):
        pass
    if not isinstance(value, dict):
        value = {}
    return {"named_connection_found": bool(value), "authenticator": value.get("authenticator", "snowflake"),
            "password_saved": bool(value.get("password")), "token_saved": bool(value.get("token")),
            "private_key_configured": bool(value.get("private_key") or value.get("private_key_file")),
            "first_run_settings_present": (Path.home() / ".snowflake" / "cortex" / "settings.json").is_file()}


def _isolated_status():
    target = ISOLATED / "samvaad.db"
    if not target.is_file():
        return {"prepared": False, "database_changed": False}
    # A read-only URI cannot initialize, seed, reset, or modify the demo database.
    con = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT action_id,status,outcome,execution_mode,attempts,completed_at,approval_role,action_code FROM actions WHERE customer_id='C0001' ORDER BY created_at DESC LIMIT 1").fetchone()
        return {"prepared": True, "database_changed": False,
                "fictional_customer_count": con.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
                "callback_action": dict(row) if row else None,
                "financial_change_enabled": False, "telephone_delivery_enabled": False}
    finally:
        con.close()


def _hook_observations():
    target = ISOLATED / "hook-events.jsonl"
    records = []
    if target.exists():
        try:
            if target.stat().st_size <= 1_000_000:
                for line in target.read_text(encoding="utf-8").splitlines()[-1000:]:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        records.append(value)
        except (OSError, ValueError):
            pass
    return {"observed_count": len(records),
            "observed_operations": sorted({r.get("operation") for r in records if r.get("operation") in {"ask", "recommend", "execute"}}),
            "blocked_count": sum(r.get("decision") == "block" for r in records),
            "native_runtime_verified": False,
            "limit": "Correlate observations with genuine CoCo tool trace and screen recording; hook input can be forged."}


def _model_smoke(binary, timeout=20):
    marker = "SAMVAAD_NATIVE_" + secrets.token_hex(8)
    result = {"attempted": True, "verified": False, "max_turns": 1, "tools_allowed": [], "mcp_enabled": False}
    try:
        response = _native(binary, ["exec", "Reply with exactly " + marker + " on one line. Do not use tools, files, SQL, or commands.",
                                    "-c", "samvaad_hackathon", "--max-turns", "1", "--effort", "minimal", "--private", "--no-mcp", "--blocked", "*"], timeout=timeout)
        raw = response.stdout + "\n" + response.stderr
        result["exit_code"] = response.returncode
        result["verified"] = response.returncode == 0 and marker in [line.strip() for line in response.stdout.splitlines()]
        result["response_sha256"] = hashlib.sha256(response.stdout.encode()).hexdigest()
        if not result["verified"]:
            result["blocker"] = "INTERACTIVE_ONBOARDING_REQUIRED" if "not configured" in raw else "AUTHENTICATION_REQUIRED" if any(
                word in raw.lower() for word in ("password", "authentication", "login", "mfa")) else "NATIVE_MODEL_RESPONSE_UNCONFIRMED"
    except subprocess.TimeoutExpired:
        result["blocker"] = "NATIVE_MODEL_TIMEOUT"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-auth-smoke", action="store_true", help="Explicitly make one native CoCo request: at most one turn, no tools/SQL/MCP, default 20-second timeout.")
    parser.add_argument("--auth-timeout", type=int, choices=(20, 45, 90), default=20, help="Bound the explicitly requested model smoke timeout; default 20 seconds.")
    parser.add_argument("--output", default="output/cloud/coco-submission-preflight.json")
    args = parser.parse_args(argv)
    binary = cortex_path()
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "native_executable_found": bool(binary),
              "native_version": None, "project_skills_discovered": [], "help_verified": False,
              "all_project_skills_discovered": [],
              "connection": _auth_metadata(), "isolated_demo": _isolated_status(), "hook_observations": _hook_observations(),
              "model_smoke": {"attempted": False, "verified": False}, "workflow_runtime_verified": False,
              "submission_video_complete": False, "credentials_printed": False}
    if binary:
        try:
            version = _native(binary, ["--version"])
            match = re.search(r"\bv?(\d+\.\d+\.\d+)\b", version.stdout)
            report["native_version"] = match.group(1) if match else None
            help_result = _native(binary, ["exec", "--help"])
            report["help_verified"] = help_result.returncode == 0 and all(flag in help_result.stdout for flag in ("--max-turns", "--blocked", "--private", "--no-mcp"))
            # Put the subcommand first: global flags before `skill list` enter
            # interactive startup in the installed 1.1.87 command dispatcher.
            discovery = _native(binary, ["skill", "list"])
            if discovery.returncode == 0:
                report["project_skills_discovered"] = [skill for skill in SKILLS if f"- {skill}:" in discovery.stdout]
                report["all_project_skills_discovered"] = [skill for skill in (*SKILLS, "samvaad-reset") if f"- {skill}:" in discovery.stdout]
            if args.run_auth_smoke:
                report["model_smoke"] = _model_smoke(binary, args.auth_timeout)
        except (OSError, subprocess.TimeoutExpired):
            report["native_metadata_blocker"] = "LOCAL_NATIVE_COMMAND_UNAVAILABLE"
    report["next_step"] = ("Use the existing private CoCo session to run the three modular capabilities and keep the actual native trace and recording. A Python CLI demonstration alone does not satisfy this gate." if report["connection"]["first_run_settings_present"] else "Finish the genuine CoCo wizard privately, then run the three modular capabilities and keep the actual native trace and recording. A Python CLI demonstration alone does not satisfy this gate.")
    path = (WORKSPACE / args.output).resolve()
    allowed = (WORKSPACE / "output").resolve()
    if not path.is_relative_to(allowed) or path.suffix != ".json":
        parser.error("Write the secret-free report only to a JSON file inside output/.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["native_executable_found"] and len(report["project_skills_discovered"]) == 3 else 2


if __name__ == "__main__":
    raise SystemExit(main())
