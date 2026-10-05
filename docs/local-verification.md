# Local verification and reproducible checks

The application runs on this laptop: Streamlit frontend, shared Python domain service, FastAPI integration/invitation boundary, SQLite state and a persisted voice lab. Contacts and borrower data are synthetic. Local audio uses actual installed SAPI speech and local CPU Whisper recognition; carrier telephony is disabled.

## Automated gate

```powershell
cd C:\Users\arunv\Documents\coco-snowflake
.\.venv\Scripts\python.exe -m pytest -q --junitxml=output/local-test-results.xml
.\.venv\Scripts\python.exe -m tools.cli check
.\.venv\Scripts\python.exe -m pip check
```

Tests use temporary databases and test-only tokens. They do not reset the interactive demo or consume Snowflake credits. The CLI check verifies fixture/identity sanity; it is not a substitute for behavioral tests.

| Area | Verified behavior |
| --- | --- |
| Data and decisions | 20 scoped customers, active obligations reconciled, hardship before growth, evidence hashes and policy caps |
| Text evidence | Negation, borrower/agent separation, noisy hardship, competitor entities and citations |
| Authorization | Fixed identities and approver roles; body impersonation, approval and delivery bypass denied |
| Actions | Stale/expired approval denied; atomic claims, competing workers, retry gaps and exhaustion |
| Consent and invitations | Opt-out persists; scoped tokens, expiry, escaped text, atomic replay and concurrent responses |
| Assistant and ingestion | Supported customer/portfolio questions, dated windows, new hardship changes the recommendation |
| Voice | Permission and verbal demo identity gates, bounded approved terms, persistent turns, duplicate events and one active session |
| Voice outcomes | Opt-out before financial dialogue, negative/conditional acceptance rejected, hardship suppresses offers, external action outcome preserved |
| Voice API/audio bounds | Authentication, runner role, impersonation rejection, PCM/duration/size limits, reviewed transcript submission |
| Frontend | Twelve AppTests using real service/database, including sanitized-error checks; audio providers mocked only in those UI tests |
| Cloud preparation | 38 offline tests for config/setup conflicts, hidden credential input, deterministic fixtures, checksums, bound values, rollback and CLI behavior |
| Automation guard | Hook contract and blocked execution tests; actual CoCo runtime is still pending |

The 15 PRD golden questions remain in `tests/golden_questions.json`. Their presence is not a claim of unrestricted natural-language coverage or fifteen cloud answers.

## Actual runtime rehearsals

Start both services with `.\scripts\run_local.ps1`. The site is at http://127.0.0.1:8501 and API at http://127.0.0.1:8000/docs. Private tokens remain in `.local/api-tokens.json`; the checks read them without printing them.

The following scripts deliberately mutate only local synthetic data. Voice rehearsal needs Ravi's fresh approved callback; browser rehearsal needs Ananya's fresh pending rate review. Reset between repeated rehearsals:

```powershell
.\.venv\Scripts\python.exe -m tools.cli reset --confirm RESET-LOCAL-DEMO
.\.venv\Scripts\python.exe scripts/voice_runtime_check.py --confirm TEST-LOCAL-DEMO
.\.venv\Scripts\python.exe scripts/browser_check.py --confirm TEST-LOCAL-DEMO
```

The browser script uses a fresh isolated headless browser context, without accessing a signed-in user profile. It checks manager approval, the voice conversation, actual audio elements, a generated invitation and callback form, scoped assistant evidence and mobile overflow. PNG inspection is a separate visual check. The in-app Browser plugin could not initialize; the isolated installed Chromium browser provides the fallback rehearsal.

After rehearsal, reset the synthetic database again. Old invitation links stop working; voice sessions, actions and audit events are cleared and fixtures are reseeded. To stop only the supervised processes, use `.\scripts\stop_local.ps1`.

## Recorded results

| Check | Actual result |
| --- | --- |
| Current full automated suite | **175 passed in 47.44 seconds**, 5 October 2026 IST; `output/local-test-results.xml` and `output/production-readiness-tests.xml`. One nonblocking Starlette test-client deprecation warning. |
| Package compatibility and CLI sanity | Passed: no broken requirements; 20 customers, no fixture/identity errors, external delivery disabled |
| Initial localhost application/API rehearsal | **7 checks passed**; health/auth, Ananya retention, Imran credit invitation/opt-out, Ravi callback and Kabir ingestion. `output/local-runtime-check.json` |
| Actual localhost voice and audio rehearsal | **5 checks passed**; authenticated status, real SAPI WAV, real Whisper recognition, persisted Ravi callback and exact replay with no hardship invitation. `output/local-voice-runtime-check.json` |
| Audio smoke | Synthetic phrase recognized exactly after normalization. Latest speech/ASR HTTP round trip: 14.049 seconds during development verification; earlier standalone ASR: 3.388 seconds. Single generated sample, not an accuracy or production latency benchmark. |
| Current browser visual/workflow check | **6 checks passed** in a fresh isolated browser; 8 saved PNG views inspected. `output/local-browser-check.json` and `output/screenshots/`. Active tabs persist and no duplicate controls remain after voice turns. |
| Fresh interactive state | Passed: 20 customers, 3 seeded actions (2 pending, 1 approved), no offers/voice sessions, and both service health endpoints passed. `output/local-final-state.json`. |
| Cloud capability discovery | Connector installed; no configured account/warehouse or CoCo CLI; no account contacted. `output/cloud/capabilities.json` |
| Known Python dependency advisories | Zero findings across 101 distributions after targeted pip/setuptools updates; no skips. This is not an application/OS/model security certification. `output/production-dependency-audit.json` |

## Production gates

The current suite demonstrates local workflow behavior, not real underwriting eligibility, churn accuracy, phone call quality or cloud compatibility. Cloud SQL and imports need actual account acceptance; the service still has no complete cloud adapter. Preserve authorization/transaction tests when adding PostgreSQL operational state and Snowflake/Cortex analytical providers. Configure trusted operator/worker identities before deployment.

The provisional neural voice bundle needs pinned license/notice review and a hardware/audio benchmark. A PBX adapter, durable worker, human handoff, licensed trunk and applicable calling-policy checks are not implemented. Refer to [cloud setup](cloud-setup.md), [telecalling plan](telecalling-plan.md), [voice license review](voice-license-review.md) and [build status](../BUILD_STATUS.md).
