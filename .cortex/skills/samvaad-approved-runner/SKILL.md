---
name: samvaad-approved-runner
description: Execute one explicitly approved Samvaad local action through the guarded automation CLI.
---

Use this skill only when the user supplies a concrete action ID to execute.

1. Run `python -m tools.cli status` and locate exactly that action.
2. If its required approval has not been recorded, report the pending role and stop execution. Never approve it yourself or use `approve --as`.
3. Execute one command: `python -m tools.cli execute ACTION_ID --mode simulate --outcome ACCEPT`. Use a different supported synthetic outcome only when requested by the user. Do not chain shell commands.
4. Report the actual service result, execution mode, audit status, and synthetic delivery/outcome. If blocked, preserve the error and explain the required operator action.

The fixed executor identity is `local-runner`. Do not pass `--force`, role overrides, approval bypasses, or caller-selected actor IDs. Do not edit SQLite, approval records, consent, action caps, or timestamps to make an action eligible. Do not call external send services. Hook checks are supplemental; service policy checks always decide eligibility. Repeating execution must use the same action ID and rely on idempotency rather than generating a duplicate action.
