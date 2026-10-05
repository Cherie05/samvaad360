"""Launch and supervise only this workspace's local demo processes.

The stop script communicates with an authenticated loopback control server;
it never kills a process by trusting a stale PID file.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

WORKSPACE = Path(__file__).resolve().parents[1]
LOCAL = WORKSPACE / ".local"
STATE_FILE = LOCAL / "runtime.json"
USERS = ("meera", "farah", "arjun", "kavya", "local-runner", "demo-admin")


def _request(port: int, route: str, token: str, method: str = "GET"):
    request = Request(f"http://127.0.0.1:{port}{route}", headers={"Authorization": f"Bearer {token}"}, method=method)
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read())


def _existing_run():
    if not STATE_FILE.exists():
        return None
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if Path(state["workspace"]).resolve() != WORKSPACE:
            raise RuntimeError("Local runtime state refers to a different workspace.")
        remote = _request(int(state["control_port"]), "/state", state["control_token"])
        if remote.get("run_id") == state.get("run_id") and remote.get("workspace") == str(WORKSPACE):
            return state
    except (OSError, ValueError, KeyError, URLError):
        return None
    return None


def _ensure_tokens():
    path = LOCAL / "api-tokens.json"
    if path.exists():
        return
    # Token-to-fixed-user configuration is private, random, and never printed.
    mapping = {secrets.token_urlsafe(32): user for user in USERS}
    path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def _acquire_lock():
    handle = (LOCAL / "supervisor.lock").open("a+")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write("0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _run() -> int:
    existing = _existing_run()
    if existing:
        print("Samvaad is already running in this workspace: http://127.0.0.1:8501", flush=True)
        return 0
    if not (WORKSPACE / "app" / "streamlit_app.py").exists():
        print("Missing app/streamlit_app.py. Finish the application before starting.", file=sys.stderr)
        return 1
    _ensure_tokens()
    stop_event = threading.Event()
    run_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
    children: list[subprocess.Popen] = []
    log_handles = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(WORKSPACE) + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    environment["PYTHONUNBUFFERED"] = "1"
    environment["SAMVAAD_API_TOKEN_FILE"] = str(LOCAL / "api-tokens.json")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _authorized(self):
            return secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

        def _reply(self, code, value):
            data = json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._authorized() or self.path != "/state":
                self._reply(404, {"error": "not_found"})
                return
            self._reply(200, {"run_id": run_id, "workspace": str(WORKSPACE), "pid": os.getpid()})

        def do_POST(self):
            if not self._authorized() or self.path != "/stop":
                self._reply(404, {"error": "not_found"})
                return
            self._reply(200, {"status": "stopping", "run_id": run_id})
            stop_event.set()

    control = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=control.serve_forever, daemon=True)
    thread.start()
    state = {"workspace": str(WORKSPACE), "run_id": run_id, "pid": os.getpid(), "control_port": control.server_port, "control_token": token, "children": []}

    def stop_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)
    try:
        seed = subprocess.run([sys.executable, "-m", "tools.cli", "seed"], cwd=WORKSPACE, env=environment, capture_output=True, text=True, creationflags=flags)
        if seed.returncode:
            print("Local seed failed:\n" + seed.stderr + seed.stdout, file=sys.stderr, flush=True)
            return 1
        launch = [
            ("api", [sys.executable, "-m", "uvicorn", "webhook.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"]),
            ("streamlit", [sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py", "--server.address", "127.0.0.1", "--server.port", "8501", "--server.headless", "true", "--browser.gatherUsageStats", "false"]),
        ]
        for name, command in launch:
            handle = (LOCAL / f"{name}.log").open("a", encoding="utf-8")
            log_handles.append(handle)
            process = subprocess.Popen(command, cwd=WORKSPACE, env=environment, stdout=handle, stderr=subprocess.STDOUT, creationflags=flags)
            children.append(process)
            state["children"].append({"name": name, "pid": process.pid})
        STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            STATE_FILE.chmod(0o600)
        print("Samvaad local demo starting at http://127.0.0.1:8501", flush=True)
        print("API: http://127.0.0.1:8000/docs · Logs: .local/api.log and .local/streamlit.log", flush=True)
        print("Stop safely with python scripts/stop_local.py or Ctrl+C.", flush=True)
        while not stop_event.wait(0.5):
            for process in children:
                code = process.poll()
                if code is not None:
                    print(f"Local child process exited with code {code}. See .local logs.", file=sys.stderr, flush=True)
                    stop_event.set()
                    return 1
        return 0
    finally:
        # Popen instances refer only to processes created by this supervisor.
        for process in children:
            if process.poll() is None:
                process.terminate()
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        control.shutdown()
        control.server_close()
        for handle in log_handles:
            handle.close()
        if STATE_FILE.exists():
            try:
                if json.loads(STATE_FILE.read_text(encoding="utf-8")).get("run_id") == run_id:
                    STATE_FILE.unlink()
            except (OSError, ValueError):
                pass


def main() -> int:
    LOCAL.mkdir(exist_ok=True)
    lock = _acquire_lock()
    if lock is None:
        print("Samvaad is already starting or running for this workspace. App: http://127.0.0.1:8501", flush=True)
        return 0
    try:
        return _run()
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())
