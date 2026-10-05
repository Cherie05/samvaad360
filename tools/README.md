# Local developer CLI

Use the project's virtual environment from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m tools.cli seed
.\.venv\Scripts\python.exe -m tools.cli check
.\.venv\Scripts\python.exe -m tools.cli status
.\.venv\Scripts\python.exe -m tools.cli recommend C0001
.\.venv\Scripts\python.exe -m tools.cli approve ACTION_ID --as arjun
.\.venv\Scripts\python.exe -m tools.cli execute ACTION_ID --outcome ACCEPT
.\.venv\Scripts\python.exe -m tools.cli ask "Why might this customer leave?" --customer-id C0001
.\.venv\Scripts\python.exe -m tools.cli reset --confirm RESET-LOCAL-DEMO
```

Replace sample IDs with IDs returned by `status`. Retention requires manager `arjun`; top-up requires credit officer `kavya`. `approve --as` is explicit manual identity simulation for the local developer demo. It is not production authentication. The approved-action automation skill only executes as `local-runner`, does not accept an approver/role, and cannot skip the service's approval checks. No `--force` option exists.

Execution records a synthetic outcome. Nothing is sent externally. `reset` clears and reseeds synthetic local data, invalidating old offer links and action IDs. Read-only `check` is a smoke check; the tests verify policy behavior separately.
