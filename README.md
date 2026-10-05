# Samvaad 360

A local lending Customer 360 and Next Best Action web application based on `Samvaad360_PRD.pdf`. It combines repayment facts with emails, chats and call transcripts, then routes an evidence-backed action to its designated reviewer. It now includes a working local voice lab with speech output, speech recognition and persisted conversations. Data, offers and contacts are synthetic; real phone calls are disabled.

## Public website

**[Open the public website](https://samvaad360.streamlit.app/)** · **[Public source](https://github.com/Cherie05/samvaad360)**

The command-center redesign passes **283 local tests** and **11 real-browser workflow checks** using Snowflake. It adds portfolio priorities, an omnichannel journey, policy explanations, a what-if studio and a review-to-conversation flow with browser voice controls. Actual borrower hardship and opt-out produce visible before/after decisions and protect further contact in that visit. Its hosted release is being verified. See [the product and production plan](docs/product-production-plan.md).

The anonymous website is deployed on free Streamlit Community Cloud hosting with a genuine Snowflake backend. Its dedicated reader retrieves 20 fictional customers from `SAMVAAD_STAGING.PUBLIC_DEMO`; public reviews simulate a workflow within each visit. All 239 tests pass in GitHub. Six independent browser checks pass against the hosted website without login, including a live Snowflake source, review simulation and visitor isolation. See [deployment and verification](docs/public-website-deployment.md). Snowflake queries use trial credits; hosting is free. A clearly labelled fictional backup keeps the demo browsable if the trial is unavailable.

## Hackathon cloud account setup

The separate Snowflake-hosted demo is packaged for `ZYLTUKM-HU63768` / `ARUNVPP24`. Run this from the workspace in your own PowerShell terminal; enter password/MFA only in its hidden local prompts:

```powershell
.\.venv\Scripts\python.exe -m scripts.trial_cloud_setup --account 'ZYLTUKM-HU63768' --user 'ARUNVPP24' --apply
```

It provisions a scoped role, X-Small warehouse, five-credit daily warehouse monitor, synthetic analytical data and a private warehouse-runtime Streamlit website. Its Python/Snowpark backend saves demo reviews to Snowflake. Cortex answers are optional and bounded; financial execution and telephone audio remain separate. Omitting `--apply` only regenerates the offline package.

The [GitHub deployment](docs/github-deployment.md) passes **239 tests**, authenticates with a temporary Snowflake identity, updates the private **SAMVAAD360** app, and verifies its live files and 20-customer count. The source repository is public with owner authorization. The owner confirms all four main tabs load, a review request saves and its reviewer note appears. Explicit Python 3.11.15, Streamlit 1.52.2 and Snowpark 1.55.0 pins fixed hosted startup in this account. Select role **SAMVAAD_HACKATHON**, then **Projects > Streamlit > SAMVAAD360**. One synthetic Cortex model request returned `OK`; customer-answer quality and CoCo account/model/skill/hook execution remain unverified. See the [end-to-end hackathon guide](docs/hackathon-cloud-setup.md), [startup repair](docs/cloud-startup-repair.md) and [runtime advisory review](docs/cloud-runtime-advisories.md). The older supported warehouse Streamlit version retains two upstream advisories with documented scope; the patched local runtime's clean scan does not cover that cloud version. Production remains blocked as described in [readiness](docs/production-readiness.md).

## Frontend, backend and database

| Part | Technology | Code / runtime |
| --- | --- | --- |
| Anonymous public frontend/backend | Streamlit 1.65.0, Python 3.11 and Snowflake Connector 4.8.0 | `public_app/`; https://samvaad360.streamlit.app/ |
| Public analytical database | Read-only fictional snapshots in Snowflake | `SAMVAAD_STAGING.PUBLIC_DEMO`; dedicated service-key connection verified |
| Staff browser frontend | Streamlit 1.65+ and local CSS/system fonts | `app/streamlit_app.py`, `app/voice_ui.py`; http://127.0.0.1:8501 |
| Application backend | Python domain service, bounded rules and evidence answers | `samvaad/service.py`, `engine.py`, `signals.py`, `knowledge.py` |
| REST API and customer invitation pages | FastAPI and Uvicorn | `webhook/main.py`, `voice_routes.py`; http://127.0.0.1:8000/docs |
| Local operational database | SQLite, WAL, transactional writes and enforced keys | `.local/samvaad.db`; shared by frontend, API and CLI |
| Voice conversation engine | Persisted permission/identity/dialogue states | `samvaad/voice.py` |
| Local audio | Installed Windows SAPI voice; faster-whisper CPU INT8 recognition | `samvaad/voice_audio.py`; pinned model in `.local/models/whisper-base` |
| Automation | Python CLI and prepared CoCo skills/hook | `tools/cli.py`, `.cortex/`; actual CoCo runtime remains unverified |
| Cloud analytical demo | Snowflake connector, schema/views, bounded Cortex jobs and fixture importer | `cloud/`, `scripts/cloud_*.py`; synthetic data loaded in `SAMVAAD_STAGING`; model connection check passed |
| Private cloud frontend | Streamlit 1.52.2 inside Snowsight | `cloud/demo_app/streamlit_app.py`; `SAMVAAD360` |
| Private cloud backend | Python 3.11.15 domain engine and Snowpark 1.55.0 | `cloud/demo_app/demo_repository.py`; calls Snowflake from the hosted app |
| Cloud database and demo reviews | Snowflake standard tables and Customer 360 views | `SAMVAAD_STAGING`, with RAW, CORE, AI and APP schemas |

Streamlit calls the shared Python service directly. FastAPI exposes the same domain rules for integrations and invitation pages. The UI does not require an HTTP request for each screen.

## Start locally on Windows

The environment, optional voice packages and recognition model are already installed here:

```powershell
cd C:\Users\arunv\Documents\coco-snowflake
.\scripts\run_local.ps1
```

Open **http://127.0.0.1:8501**. The supervisor starts both services, seeds 20 fictional customers, creates private API tokens, and keeps logs in `.local/`. Stop only these supervised services with:

```powershell
.\scripts\stop_local.ps1
```

For a fresh checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe scripts/provision_voice.py --download
```

The lock file captures the installed Windows/Python 3.11 environment, including optional cloud, voice and development tools. For a smaller install, `requirements.txt` is the web runtime, `requirements-dev.txt` adds tests, and `requirements-voice.txt`, `requirements-cloud.txt` and `requirements-browser.txt` are optional. Voice model provisioning is an explicit network download; runtime transcription loads local files only. No personal voice recording or paid speech API is needed. No Snowflake credits are used locally.

## Rehearse the product

1. **Customer 360:** Ananya C0002 is initially selected. Inspect loans, the foreclosure email, and the competitor offer. Ask why she might leave and follow the evidence citations.
2. **Retention:** In Approvals, select Ananya's rate review. Meera cannot approve. Switch to Arjun and approve the capped 100 bps proposal. Use either simulated execution or Voice lab for this approved action. Action history records the approver and outcome.
3. **Top-up:** Select Imran C0003 and switch to Kavya to approve the capped conditional invitation. Simulate acceptance or complete a voice conversation. The resulting local invitation expires after 72 hours; interest never disburses a loan.
4. **Hardship:** Select Ravi C0001. His job-loss evidence and DPD lead to a supportive callback, with no financial offer. The seeded nonfinancial action is already approved.
5. **Voice lab:** Select Ravi, open Voice lab, and start a local session. Submit `Yes, you may continue`, then `Yes, I am the account holder`, then `Please arrange an officer callback`. Hear/download the lender WAV and export the speaker-labelled transcript. The two affirmative gates are synthetic verbal checks, not production KYC.
6. **Microphone / WAV:** In an active voice session select this input, record fictional borrower speech or upload a PCM WAV (60 seconds / 10 MB maximum), transcribe locally, review the text, and explicitly submit it. Text input remains available. Browser microphone permission is required.
7. **New evidence:** For Kabir C0007 generate a reminder, then add `Customer: I lost my job and cannot pay my EMI. Please help.` The decision changes to hardship support and replaces the old recommendation. New hardship during a voice conversation also suppresses financial invitations.
8. **Consent:** Record an opt-out or say `Do not call me again` in a local session. Consent changes persist and affected contacts are cancelled. Negative and conditional replies do not count as acceptance.

The operator selector simulates identities on this laptop; production login is pending. The assistant can queue a recommendation but cannot approve it. A voice outcome records a synthetic customer preference; it does not change loan terms.

## Checks and reset

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=output/local-test-results.xml
.\.venv\Scripts\python.exe -m tools.cli check
```

The latest GitHub full suite passes 239 tests, including local UI, public-reader isolation, cloud-port and deployment guards. Tests use isolated temporary databases. The actual API/audio and browser rehearsals below deliberately change the interactive synthetic demo and need fresh approved actions:

```powershell
.\.venv\Scripts\python.exe scripts/voice_runtime_check.py --confirm TEST-LOCAL-DEMO
.\.venv\Scripts\python.exe scripts/browser_check.py --confirm TEST-LOCAL-DEMO
```

Restore only the synthetic demo after rehearsals:

```powershell
.\.venv\Scripts\python.exe -m tools.cli reset --confirm RESET-LOCAL-DEMO
```

Reset removes actions, invitations, audit events and voice sessions, then reseeds fixtures. Old invitation links become invalid. See [build status](BUILD_STATUS.md) and [verification evidence](docs/local-verification.md) for actual results.

## Cloud and automated telecalling

The [cloud setup guide](docs/cloud-setup.md) includes doctor/export/deploy/load/enrichment commands and reviewed SQL plans. The connector and CoCo executable are installed; the `samvaad_hackathon` connection stores metadata without a password. The separate hosted demo is working, while the local application's full operational cloud repository remains unimplemented.

The [production readiness audit](docs/production-readiness.md) records verified fixes and remaining release blockers. Production is not ready. Synthetic Snowflake staging is deployed and its startup is verified by the owner. The setup helper stores metadata only; native password and MFA are entered privately during owner setup. Subsequent GitHub releases use OIDC. Current trial expiry/credit entitlements still need an account check.

For a standard Snowflake trial, keep production action/consent/session state in PostgreSQL and use Snowflake for Customer 360/Cortex analytics. Standard Snowflake table keys are unenforced and hybrid tables are unavailable in standard trials. The PostgreSQL adapter remains to be implemented. Standard trial credits also do not establish CoCo access; verify a paid or dedicated CoCo trial account.

The [self-hosted telecalling plan](docs/telecalling-plan.md) specifies Asterisk ARI, a durable worker, local Whisper recognition, a stock neural voice, human handoff and a licensed SIP trunk. Parler Mini v1 is the provisional production voice candidate. Its complete tokenizer/codec/runtime bundle still needs a pinned license review and target-hardware benchmark; the installed Windows voice is only the local lab provider. See the [voice license review](docs/voice-license-review.md) and [deployment scaffold](infra/voice/README.md).

Production identity, PBX integration, carrier delivery, Hindi/accent quality checks, full Snowflake/Cortex application integration, and real CoCo execution remain pending. Insurance claims are an additional domain; this release implements the lender PRD. The [original build plan](output/Samvaad360_Build_Plan.md) records hackathon fit and published timing; local operation alone does not establish Snowflake/CoCo eligibility.
# GitHub deployment

Source and deployment workflow: [public repository](https://github.com/Cherie05/samvaad360). See [the GitHub deployment guide](docs/github-deployment.md) for the completed Snowflake OIDC setup and subsequent releases. [The verified release](https://github.com/Cherie05/samvaad360/actions/runs/37346926875) passed 239 tests; the owner separately confirmed private hosted startup. Ordinary code pushes to `main` test and deploy automatically.

