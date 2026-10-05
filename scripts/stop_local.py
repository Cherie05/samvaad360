"""Stop only the authenticated supervisor for this resolved workspace."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

WORKSPACE = Path(__file__).resolve().parents[1]
STATE_FILE = WORKSPACE / ".local" / "runtime.json"


def main() -> int:
    if not STATE_FILE.exists():
        print("No managed Samvaad process is recorded for this workspace.")
        return 0
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if Path(state["workspace"]).resolve() != WORKSPACE:
            raise ValueError("Runtime workspace does not match this stop script.")
        port = int(state["control_port"])
        if not 1 <= port <= 65535:
            raise ValueError("Invalid local control port.")
        root = f"http://127.0.0.1:{port}"
        headers = {"Authorization": "Bearer " + state["control_token"]}
        with urlopen(Request(root + "/state", headers=headers), timeout=3) as response:
            live = json.loads(response.read())
        if live.get("run_id") != state.get("run_id") or live.get("workspace") != str(WORKSPACE):
            raise ValueError("Authenticated supervisor identity does not match the local runtime record.")
        with urlopen(Request(root + "/stop", headers=headers, method="POST"), timeout=3) as response:
            result = json.loads(response.read())
        if result.get("run_id") != state.get("run_id"):
            raise ValueError("Stop response identity mismatch.")
        deadline = time.monotonic() + 15
        while STATE_FILE.exists() and time.monotonic() < deadline:
            time.sleep(0.25)
        if STATE_FILE.exists():
            print("Supervisor accepted stop; cleanup is still pending. Check .local logs.")
            return 1
        print("Stopped this workspace's Samvaad API and Streamlit processes.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, URLError) as exc:
        print(f"No matching live supervisor could be verified: {exc}. No process was terminated.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
