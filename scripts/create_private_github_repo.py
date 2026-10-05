"""Create an explicitly requested private repository using Git's saved login.

Git Credential Manager supplies credentials in memory. Neither credentials nor
the complete provider response are printed or written into the workspace.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--name", default="samvaad360")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", args.owner) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", args.name):
        raise SystemExit("INVALID_REPOSITORY_TARGET")
    result_path = Path("output/cloud/github-repository.json")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    credential = subprocess.run(["git", "credential-manager", "get"],
                                input=f"protocol=https\nhost=github.com\nusername={args.owner}\n\n",
                                text=True, capture_output=True, timeout=30,
                                env={**os.environ, "GCM_INTERACTIVE": "never", "GIT_TERMINAL_PROMPT": "0"})
    fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    token = fields.get("password")
    if credential.returncode or not token:
        raise SystemExit("GITHUB_PRIVATE_LOGIN_REQUIRED")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    account = requests.get("https://api.github.com/user", headers=headers, timeout=30)
    if account.status_code != 200 or account.json().get("login", "").lower() != args.owner.lower():
        raise SystemExit("GITHUB_ACCOUNT_CHECK_FAILED")
    # Never silently adopt or overwrite another repository's existing history.
    existing = requests.get(f"https://api.github.com/repos/{args.owner}/{args.name}", headers=headers, timeout=30)
    if existing.status_code != 404:
        raise SystemExit("REPOSITORY_NAME_EXISTS_OR_LOOKUP_FAILED")
    created = requests.post("https://api.github.com/user/repos", headers=headers,
                            json={"name": args.name, "private": True, "auto_init": False,
                                  "description": "Samvaad 360: Customer 360 and governed next best action hackathon demonstration"}, timeout=30)
    if created.status_code != 201:
        raise SystemExit(f"PRIVATE_REPOSITORY_CREATE_FAILED_HTTP_{created.status_code}")
    repository = created.json()
    if not repository.get("private") or repository.get("owner", {}).get("login", "").lower() != args.owner.lower():
        raise SystemExit("CREATED_REPOSITORY_SCOPE_CHECK_FAILED")
    result = {"status": "PRIVATE_REPOSITORY_CREATED", "private": True,
              "full_name": repository["full_name"], "url": repository["html_url"],
              "clone_url": repository["clone_url"], "credentials_saved": False}
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (requests.RequestException, subprocess.SubprocessError):
        raise SystemExit("GITHUB_SETUP_NETWORK_OR_CREDENTIAL_HELPER_FAILED")
