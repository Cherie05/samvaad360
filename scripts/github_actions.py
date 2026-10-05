"""Configure non-secret repository variables or read CI status via saved Git login."""
import argparse
import json
import os
import re
import subprocess

import requests


def session(owner):
    credential = subprocess.run(["git", "credential-manager", "get"],
                                input=f"protocol=https\nhost=github.com\nusername={owner}\n\n",
                                text=True, capture_output=True, timeout=30,
                                env={**os.environ, "GCM_INTERACTIVE": "never", "GIT_TERMINAL_PROMPT": "0"})
    values = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    if credential.returncode or not values.get("password"):
        raise SystemExit("GITHUB_PRIVATE_LOGIN_REQUIRED")
    client = requests.Session()
    client.headers.update({"Authorization": "Bearer " + values["password"], "Accept": "application/vnd.github+json",
                           "X-GitHub-Api-Version": "2022-11-28"})
    account = client.get("https://api.github.com/user", timeout=30)
    if account.status_code != 200 or account.json().get("login", "").lower() != owner.lower():
        raise SystemExit("GITHUB_ACCOUNT_CHECK_FAILED")
    return client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["configure", "status", "run"])
    parser.add_argument("--owner", default="Cherie05")
    parser.add_argument("--repo", default="samvaad360")
    parser.add_argument("--enable-deploy", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", args.owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", args.repo):
        raise SystemExit("INVALID_REPOSITORY_TARGET")
    client = session(args.owner)
    base = f"https://api.github.com/repos/{args.owner}/{args.repo}"
    if args.operation == "configure":
        for name, value in {"SNOWFLAKE_ACCOUNT": "ZYLTUKM-HU63768", "SAMVAAD_VIEWER": "ARUNVPP24",
                            "SAMVAAD_DEPLOY_ENABLED": "true" if args.enable_deploy else "false"}.items():
            response = client.get(base + "/actions/variables/" + name, timeout=30)
            if response.status_code == 404:
                response = client.post(base + "/actions/variables", json={"name": name, "value": value}, timeout=30)
                expected = 201
            elif response.status_code == 200:
                response = client.patch(base + "/actions/variables/" + name, json={"name": name, "value": value}, timeout=30)
                expected = 204
            else:
                raise SystemExit(f"GITHUB_VARIABLE_LOOKUP_FAILED_HTTP_{response.status_code}")
            if response.status_code != expected:
                raise SystemExit(f"GITHUB_VARIABLE_CONFIGURATION_FAILED_HTTP_{response.status_code}")
        print(json.dumps({"status": "VARIABLES_CONFIGURED", "deployment_enabled": args.enable_deploy, "personal_password_uploaded": False}))
    elif args.operation == "run":
        response = client.post(base + "/actions/workflows/snowflake.yml/dispatches", json={"ref": "main"}, timeout=30)
        if response.status_code != 204:
            raise SystemExit(f"WORKFLOW_DISPATCH_FAILED_HTTP_{response.status_code}")
        print("MAIN_BRANCH_WORKFLOW_REQUESTED")
    else:
        response = client.get(base + "/actions/runs", params={"per_page": 3}, timeout=30)
        if response.status_code != 200:
            raise SystemExit(f"CI_STATUS_LOOKUP_FAILED_HTTP_{response.status_code}")
        runs = []
        for run in response.json()["workflow_runs"]:
            jobs = client.get(base + f"/actions/runs/{run['id']}/jobs", timeout=30)
            result = {k: run[k] for k in ("id", "status", "conclusion", "head_sha", "html_url")}
            result["jobs"] = [{k: job[k] for k in ("id", "name", "status", "conclusion")} for job in jobs.json().get("jobs", [])] if jobs.status_code == 200 else []
            runs.append(result)
        print(json.dumps({"runs": runs}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, subprocess.SubprocessError):
        raise SystemExit("GITHUB_NETWORK_OR_CREDENTIAL_HELPER_FAILED")
