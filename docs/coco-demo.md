# Genuine CoCo workflow for the submission recording

**Verified on 6 October 2026:** the owner's native CoCo 1.1.87 session invoked evidence, generate and approved runner through actual local CLI tools. Returned output matches isolated SQLite state: action `e2e19413-c7b0-4583-af6b-f52199122e66`, `COMPLETED`, `CALLBACK`, `simulate`, one attempt, completed at `2026-10-06T16:23:35.422079+00:00`. The participant recorded a fresh safe idempotent rerun; the [final 3:42 silent video](https://github.com/Cherie05/samvaad360/releases/download/hackathon-submission-2026/Samvaad360_CoCo_Submission.mp4) combines it with the actual public website UI. No duplicate or new telephone call is claimed. An earlier separate bounded authentication probe failed to return a response; the later actual interactive session establishes the workflow.

## Private setup

From this repository in PowerShell, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File scripts/start_submission_coco.ps1
```

The helper adds the project interpreter to this terminal's PATH, initializes a separate fictional SQLite database at `.local/submission-coco/samvaad.db`, and starts the installed native CoCo. It preserves existing application data. No password, MFA code or token is collected or saved by the helper. Finish the genuine wizard privately, choose `samvaad_hackathon`, and confirm the conversation opens. Keep credentials out of recordings and chat.

The helper's `-PrepareOnly` option creates only this isolated environment and stops before any Snowflake or model request. Native discovery uses the exact subcommand `cortex skill list`. On installed 1.1.87, adding a global startup flag before `skill list` invokes interactive startup instead; that alternative does not test discovery.

Project skills and hooks follow the [official extensibility interfaces](https://docs.snowflake.com/en/user-guide/cortex-code/extensibility). Account eligibility and the first-run wizard are described in [the native CoCo setup guide](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli). The account must be enabled for CoCo; ordinary Snowflake SQL access alone is insufficient.

## Bounded authentication check

```powershell
.venv\Scripts\python.exe -m scripts.coco_submission_check
```

This command checks installed help/version and native project discovery, then reads isolated database metadata without modifying it. It does not call a model. The preflight deliberately keeps `workflow_runtime_verified=false`: a discovered skill or a hook-shaped log cannot prove that CoCo ran it.

After private login, an explicitly requested model smoke can run one native turn with all tools blocked, no MCP and no SQL:

```powershell
.venv\Scripts\python.exe -m scripts.coco_submission_check --run-auth-smoke --auth-timeout 90
```

The timeout is bounded at 20, 45 or 90 seconds. The script checks an unpredictable exact response marker, prints no provider diagnostics or credentials, and does not claim skill/hook execution from that response. A timeout remains unverified. If another OAuth authentication is requested, complete it privately before screen recording; do not copy credentials into CLI arguments or use the public website reader credentials.

## Three capabilities in one real workflow

Use **C0001, Ravi**, in the isolated dataset. Its hardship callback has a nonfinancial service-policy approval. This avoids asking the assistant to impersonate a financial approver. Read its concrete action ID from the preflight's `isolated_demo.callback_action.action_id`; the runner requires that explicit ID.

In the actual CoCo conversation, submit the following prompt, replacing the bracketed ID:

```text
Demonstrate these three project skills for fictional customer C0001 in the configured isolated local database:
1. $samvaad-evidence: explain why a supportive callback is appropriate, showing the actual cited evidence.
2. $samvaad-generate: generate the guarded recommendation for C0001 and report its actual action ID, policy and status.
3. $samvaad-approved-runner: execute action [EXACT_ACTION_ID] in simulate mode with outcome CALLBACK.
Use the actual tools.cli commands, one command at a time, and display each returned result.
Do not approve anything, reset data, alter consent or timestamps, execute SQL, read credentials, write files, send messages, or call a carrier.
Finish with the actual stored outcome and state; never invent a successful tool result.
```

`samvaad-evidence` reads a grounded answer; `samvaad-generate` queues or reuses a policy decision; `samvaad-approved-runner` executes the concrete approved action as the fixed automation principal. The fourth project skill, `samvaad-reset`, remains optional and requires an explicit request. It is not part of this recording workflow.

The backend is real local persistence with synthetic fixtures. Delivery is explicitly simulated. No borrower is dialed, no financial transaction occurs, and the deterministic domain rules are separate from CoCo's model orchestration. The live public website's genuine Snowflake snapshots are a different part of the demonstration; an anonymous visit-local approval cannot authorize the local CLI.

## Evidence and recording checks

Show the real native CoCo **input → tool processing → output**, including the three capability names, returned citations, concrete action ID and final `COMPLETED`/`CALLBACK` state. Capture a fresh live process or the user's actual authenticated terminal; a Python-only run or fabricated/archived terminal text does not establish native execution. The final recording is a fresh CoCo tool run against the existing completed action and explicitly demonstrates idempotency.

The project `PreToolUse` hook optionally records bounded metadata at `.local/submission-coco/hook-events.jsonl`. It stores operation, allow/block decision, timestamp and hashes of command/session, never raw prompts, transcripts, secrets or command arguments. Correlate the observed `ask`, `recommend` and `execute` calls with the native CLI tool trace. These files alone are forgeable and do not prove runtime execution. The application service remains the authority for role, consent, eligibility and idempotency. The project hook is advisory; native hook fail-closed enforcement and a general shell sandbox are not claimed. An earlier chained-command observation was marked blocked by the hook but the legitimate approved simulation completed at the service; the recorded rerun uses standalone commands.

Record after authentication so account login pages and private credentials are excluded. Keep the final combined video within the portal's **3–5 minutes**, and verify its accessible published link. Re-run the preflight to inspect the stored action and observed hook metadata, then retain a sanitized verification summary with the source commit and native version. A successful model nonce, discovered skills, actual tool/hook execution, persistent result and published video are separate evidence items.

The [CLI reference](https://docs.snowflake.com/en/user-guide/cortex-code/cli-reference) documents bounded batch execution and noninteractive permission behavior. Choose standard mode for this workflow: code mode's reduced tool set does not demonstrate these project skills. Allow only the required local commands and skill reads; leave SQL, write/edit, web and external integrations unavailable during a bounded recording run.
