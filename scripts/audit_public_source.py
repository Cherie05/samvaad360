"""Pattern-based publication check; report categories/paths, never secret values."""
import json
import re
import subprocess
from pathlib import Path

from cloud.config import WORKSPACE


PATTERNS = {
    "private_key_material": re.compile(rb"-----BEGIN (?:ENCRYPTED |RSA |EC )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "aws_access_key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt_material": re.compile(rb"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{20,}\b"),
}


def git(*args):
    return subprocess.run(["git", *args], cwd=WORKSPACE, capture_output=True, check=True).stdout


def main():
    findings = []
    objects = {}
    for line in git("rev-list", "--objects", "--all").decode("utf-8").splitlines():
        sha, _, name = line.partition(" ")
        objects[sha] = name or sha
    records = subprocess.run(["git", "cat-file", "--batch"], cwd=WORKSPACE,
        input=("\n".join(objects) + "\n").encode(), capture_output=True, check=True).stdout
    offset = historical = 0
    while offset < len(records):
        end = records.index(b"\n", offset)
        sha, kind, size = records[offset:end].decode().split()
        offset = end + 1
        content = records[offset:offset + int(size)]
        offset += int(size) + 1
        if kind != "blob" or b"\0" in content:
            continue
        historical += 1
        for category, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append({"scope": "history", "object": sha, "path": objects[sha], "category": category})
    paths = set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")) - {""}
    working = 0
    for name in sorted(paths):
        if name.startswith((".local/", "output/", ".venv/")) or Path(name).suffix.lower() in {".key", ".pem", ".p8", ".db"} or name.endswith("secrets.toml"):
            findings.append({"scope": "working", "path": name, "category": "private_artifact"})
        path = WORKSPACE / name
        if not path.is_file():
            continue
        content = path.read_bytes()
        if b"\0" in content:
            continue
        working += 1
        for category, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append({"scope": "working", "path": name, "category": category})
    report = {"history_text_blobs_scanned": historical, "working_files_scanned": working,
              "findings": findings, "scope": "Pattern-based source/history credential check; not a proof that all possible secrets are absent"}
    target = WORKSPACE / "output/cloud/public-source-audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
