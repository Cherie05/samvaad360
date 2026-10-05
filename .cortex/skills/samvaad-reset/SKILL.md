---
name: samvaad-reset
description: Restore synthetic local Samvaad demo fixtures when the user explicitly requests a reset.
---

Use this skill only when the user explicitly requests resetting the local demo data.

Run `python -m tools.cli reset --confirm RESET-LOCAL-DEMO`, then `python -m tools.cli check`.

This removes prior synthetic actions, responses, offers, and audit history and invalidates their invitation links. It must affect only the configured local demo SQLite database. Do not delete directories, edit cloud data, change production connections, or reset a cloud account. Report the fresh fixture count and smoke-check result. Do not claim that the complete test suite ran unless it actually ran.
