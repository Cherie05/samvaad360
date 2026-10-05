# Samvaad 360 frontend

The local frontend is a Streamlit browser application. It calls the shared
`samvaad` Python service directly; the separate FastAPI service handles demo
offer links and its authenticated API. Customer data, the action queue, offers,
and audit events are stored in the configured local SQLite database.

From the repository root, using the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Visit `http://127.0.0.1:8501`. Run the offer service separately to open generated
offer links. See the root README for the full local launch commands.

## Working screens

- **Customer 360:** customer search, active-loan facts, interaction timeline,
  conversation signals, recommendation evidence, proposed terms, and opt-out.
  Analysts can add synthetic email/chat/call/complaint text, inspect the
  recalculated offline signals, and refresh the next best action.
- **Approvals & execution:** role-specific approval, rejection, and approved
  simulated execution using the separate local automation identity.
- **Ask Samvaad:** offline answers scoped to one customer or the portfolio,
  conversation citations, provider labels, and per-scope chat history.
- **Action history:** action state, outcome, generated offer links, and audit.
- **Voice lab:** a persisted automated lender/borrower conversation for an
  approved action. Local permission and account-holder confirmation gates
  precede any offer terms. Enter fictional borrower text, record a microphone
  response, or upload a WAV; review recognized text before submitting it.
  Listen to/download the generated lender speech and export the transcript.

Meera and Farah are analysts. Arjun approves retention offers. Kavya approves
top-up invitations. This local role selector is a demo simulation, not an
authentication system. The backend validates each known demo identity and role.
The demo runner does not approve actions on behalf of another operator.

All displayed interactions and financial policies are synthetic. The local
assistant is deterministic and offline. Contact outcomes are simulated. The
interface makes these limitations visible throughout the workflow.

The voice lab uses Windows' installed SAPI voice for lender playback. Optional
local Whisper recognition must be installed and its model provisioned before
audio transcription is enabled. The verbal identity gate is a local simulation,
not KYC. No telephone call is placed. The production stock neural voice remains
separate until its license review, integration, and latency benchmark pass;
personal recordings are not required.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest app/test_app.py -q
```

The AppTest checks use a temporary SQLite database, exercise approval controls
and simulated execution, verify that a credit-approved top-up creates an
expiring offer, and show that new hardship evidence supersedes a queued reminder.
Voice UI tests exercise permission and identity gates, acceptance, opt-out,
human escalation, microphone controls, and operator stop. Platform speech and
recognition are mocked in these UI tests; real audio adapters need their own
verification. The tests do not modify the interactive demo database.

## Later Snowflake migration

`environment.yml` records the intended Streamlit-in-Snowflake dependencies.
The current implementation is local and has not been deployed to Snowflake.
A cloud adapter and trusted operator mapping must be verified before enabling
cloud operation. The frontend has no fallback manager identity. The service
factory must select the cloud adapter and supply `is_demo=False`, viewer-to-role
mapping, and the same service contract. Upload the package and CSS alongside
the Streamlit entry point when preparing the cloud deployment.
