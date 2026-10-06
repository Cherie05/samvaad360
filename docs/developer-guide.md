# Samvaad 360 developer guide

Technical setup, runtime boundaries and development verification. For the judge overview, see the [project README](../README.md); for portal fields and outstanding artifacts, see the [submission guide](submission-guide.md).

A local lending Customer 360 and Next Best Action web application based on `Samvaad360_PRD.pdf`. It combines repayment facts with emails, chats and call transcripts, then routes an evidence-backed action to its designated reviewer. It now includes a working local voice lab with speech output, speech recognition and persisted conversations. Data, offers and contacts are synthetic; real phone calls are disabled.

## Public website

**[Open the public website](https://samvaad360.streamlit.app/)** · **[Public source](https://github.com/Cherie05/samvaad360)**

The live command center passes **557 tests in GitHub** and **20 independent hosted-browser workflow checks** using Snowflake. Its six workspaces add portfolio priorities, an omnichannel journey, policy explanations, a what-if studio, a review-to-conversation flow and Customer hub. Actual borrower hardship and opt-out produce visible before/after decisions and protect further contact in that visit. See [the product and production plan](product-production-plan.md).

The anonymous website is deployed on free Streamlit Community Cloud hosting with a genuine Snowflake backend. Its dedicated reader retrieves 20 fictional customers from `SAMVAAD_STAGING.PUBLIC_DEMO`; public reviews and conversations simulate a workflow within each visit. The hosted checks cover live data, review gates, adaptive conversations, evidence scope, visitor isolation, consent restrictions and mobile layout. Browser speech controls work; audible playback depends on the visitor's browser and was not independently verified. See [deployment and verification](public-website-deployment.md). Snowflake queries use trial credits; hosting is free. A clearly labelled fictional backup keeps the demo browsable if the trial is unavailable.

The enterprise extension adds exposure/action charts, a repayment/conversation timeline, retention-rule contributions, data-quality coverage, four-context policy comparison and downloadable decision evidence. After snapshot warm-up, visitor workflows use memory. Refreshes reserve five application statements—one identity check and four portfolio reads—with host-local limits of eight per UTC hour and 64 per day. Community Cloud admission is shared because its reported IP is untrusted; genuine per-IP enforcement requires the prepared managed gateway. These counters are not billed-credit meters or durable across host replacement. See [the enterprise release plan](enterprise-release-plan.md).

Telephone calling now has a genuine Twilio API integration and staff-only controls for existing or additional verified numbers. It is disabled until the provider, HTTPS API, permitted recipients and staff login are configured. The service validates signed callbacks and current approvals, holds uncertain dispatches instead of redialing, and stores controlled-pilot outcomes in SQLite. No real call or SMS has been sent, and production readiness remains false. See [real telephone setup](real-telephony-pilot.md).

## Customer onboarding and synchronization

The relationship extension adds a sixth **Customer hub** public workspace and a sixth **Relationship hub** private local workspace. The public hub rehearses fictional onboarding, source imports and service requests within that visit. Its new relationships can be inspected through Customer 360 and the evidence workspaces, without adding contacts to the shared Snowflake dataset. The published extension passes 20 hosted-browser checks; its separate private local relationship journey passes six browser checks.

The private hub/API persist applicant invitations, intake, staff identity/document attestations, manager review, customer records, reviewed source-ID links, bounded CSV/JSON preview/commit, service cases and customer preference withdrawals. An applicant can complete their own limited form at an expiring `/portal/{token}` link. Existing-customer links permit scoped requests and opt-out, without exposing balances or performing financial changes. Staff review flags are attestations; no external KYC result is fabricated.

**The current 20 Snowflake customers are seeded fictional records, not an automatically synced lender CRM.** The new private import adapter validates source IDs, increasing versions and customer/loan references before changing the operational SQLite database. Existing customers can be linked explicitly to lender source IDs, so their imported loans and conversations remain in the same relationship. Replayed records do not create duplicates, and materially changed evidence requires fresh action review.

A transactional outbox and genuine optional Snowflake worker project private customer state into `SAMVAAD_STAGING.RELATIONSHIP`, using a dedicated writer role and bounded manual batches. Its private credentials/schema are not activated; default inspection makes no connection. It never publishes real contacts into `PUBLIC_DEMO`. Continuous LMS/CRM ingestion, production identity and PostgreSQL remain deployment work. See [the end-to-end customer relationship plan](customer-relationship-plan.md).

## Hackathon cloud account setup

The separate Snowflake-hosted demo is packaged for `ZYLTUKM-HU63768` / `ARUNVPP24`. Run this from the workspace in your own PowerShell terminal; enter password/MFA only in its hidden local prompts:

```powershell
.\.venv\Scripts\python.exe -m scripts.trial_cloud_setup --account 'ZYLTUKM-HU63768' --user 'ARUNVPP24' --apply
```

It provisions a scoped role, X-Small warehouse, five-credit daily warehouse monitor, synthetic analytical data and a private warehouse-runtime Streamlit website. Its Python/Snowpark backend saves demo reviews to Snowflake. Cortex answers are optional and bounded; financial execution and telephone audio remain separate. Omitting `--apply` only regenerates the offline package.

The [GitHub deployment](github-deployment.md) passes **557 tests**, authenticates with a temporary Snowflake identity, updates the private **SAMVAAD360** app, and verifies its live files and 20-customer count. The source repository is public with owner authorization. The owner confirms all four main tabs load, a review request saves and its reviewer note appears. Explicit Python 3.11.15, Streamlit 1.52.2 and Snowpark 1.55.0 pins fixed hosted startup in this account. Select role **SAMVAAD_HACKATHON**, then **Projects > Streamlit > SAMVAAD360**. One synthetic Cortex model request returned `OK`; customer-answer quality and CoCo account/model/skill/hook execution remain unverified. See the [end-to-end hackathon guide](hackathon-cloud-setup.md), [startup repair](cloud-startup-repair.md) and [runtime advisory review](cloud-runtime-advisories.md). The older supported warehouse Streamlit version retains two upstream advisories with documented scope; the patched local runtime's clean scan does not cover that cloud version. Production remains blocked as described in [readiness](production-readiness.md).

## Frontend, backend and database

| Part | Technology | Code / runtime |
| --- | --- | --- |
| Anonymous public frontend/backend | Streamlit 1.65.0, Python 3.11 and Snowflake Connector 4.8.0 | `public_app/`; https://samvaad360.streamlit.app/ |
| Public analytical database | Read-only fictional snapshots in Snowflake | `SAMVAAD_STAGING.PUBLIC_DEMO`; dedicated service-key connection verified |
| Staff browser frontend | Streamlit 1.65+ and local CSS/system fonts | `app/streamlit_app.py`, `app/voice_ui.py`; http://127.0.0.1:8501 |
| Application backend | Python domain service, bounded rules and evidence answers | `samvaad/service.py`, `engine.py`, `signals.py`, `knowledge.py` |
| REST API and customer invitation pages | FastAPI and Uvicorn | `webhook/main.py`, `voice_routes.py`; http://127.0.0.1:8000/docs |
| Customer relationship portal | Streamlit staff hub, FastAPI scoped HTML/API, versioned CSV/JSON adapter | `app/relationship_ui.py`, `webhook/relationship_routes.py`, `samvaad/relationship.py` |
| Local operational database | SQLite, WAL, transactional writes and enforced keys | `.local/samvaad.db`; shared by frontend, API and CLI |
| Private relationship analytics sync | Leased outbox and parameterized Snowflake version/hash projection | `cloud/relationship_sync.py`; `scripts/relationship_sync.py --apply` only after separate private configuration |
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

The lock file captures the installed Windows/Python 3.11 environment, including optional cloud, voice and development tools. For a smaller install, `requirements.txt` is the web runtime, `requirements-dev.txt` adds tests, and `requirements-voice.txt`, `requirements-cloud.txt` and `requirements-browser.txt` are optional. Voice model provisioning is an explicit network download; runtime transcription loads local files only. No personal voice recording or paid speech API is needed for the local voice lab. Local SQLite mode uses no Snowflake credits; a public-app preview configured with the Snowflake reader does consume credits for protected refreshes.

## Rehearse the product

1. **Customer 360:** Ananya C0002 is initially selected. Inspect loans, the foreclosure email, and the competitor offer. Ask why she might leave and follow the evidence citations.
2. **Retention:** In Approvals, select Ananya's rate review. Meera cannot approve. Switch to Arjun and approve the capped 100 bps proposal. Use either simulated execution or Voice lab for this approved action. Action history records the approver and outcome.
3. **Top-up:** Select Imran C0003 and switch to Kavya to approve the capped conditional invitation. Simulate acceptance or complete a voice conversation. The resulting local invitation expires after 72 hours; interest never disburses a loan.
4. **Hardship:** Select Ravi C0001. His job-loss evidence and DPD lead to a supportive callback, with no financial offer. The seeded nonfinancial action is already approved.
5. **Voice lab:** Select Ravi, open Voice lab, and start a local session. Submit `Yes, you may continue`, then `Yes, I am the account holder`, then `Please arrange an officer callback`. Hear/download the lender WAV and export the speaker-labelled transcript. The two affirmative gates are synthetic verbal checks, not production KYC.
6. **Microphone / WAV:** In an active voice session select this input, record fictional borrower speech or upload a PCM WAV (60 seconds / 10 MB maximum), transcribe locally, review the text, and explicitly submit it. Text input remains available. Browser microphone permission is required.
7. **New evidence:** For Kabir C0007 generate a reminder, then add `Customer: I lost my job and cannot pay my EMI. Please help.` The decision changes to hardship support and replaces the old recommendation. New hardship during a voice conversation also suppresses financial invitations.
8. **Consent:** Record an opt-out or say `Do not call me again` in a local session. Consent changes persist and affected contacts are cancelled. Negative and conditional replies do not count as acceptance.
9. **Relationship hub:** Create an applicant intake as Meera or issue its private form link. As Arjun, record review attestations, approve the prospect and link the lender source ID. Switch to Meera or the local admin to preview/commit fictional loan, payment and conversation rows, then inspect the same customer in Customer 360. Add and resolve a service case; issue a customer link and withdraw contact through its form. See the [acceptance workflow](customer-relationship-plan.md#a-complete-acceptance-workflow) for source version/replay checks.

The operator selector simulates identities on this laptop; production login is pending. The assistant can queue a recommendation but cannot approve it. A voice outcome records a synthetic customer preference; it does not change loan terms.

## Checks and reset

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=output/local-test-results.xml
.\.venv\Scripts\python.exe -m tools.cli check
```

[GitHub run 37483107870](https://github.com/Cherie05/samvaad360/actions/runs/37483107870) passed **557 tests in 81.51 seconds** for source `7a619e718508777ee491bcf78309b0b2a8f0d7c3`. Deployment job `112337447935` succeeded, confirming 20 customers and `LIVE_VERSION_READY`. Local validation passed **555 tests in 78.18 seconds** in the full suite, followed by a **14-test targeted pass** including two additional engine fact cases. CI covers the complete 557-test suite. Coverage includes relationship onboarding/source linkage/versioned imports, scoped customer forms, hardship evidence, public-reader isolation, admission/query budgets, signed telephone callbacks, uncertain dispatch recovery and deployment guards. Tests use isolated databases and carrier/Snowflake transport doubles; they do not establish actual phone delivery or private relationship cloud delivery. The actual API/audio and browser rehearsals below deliberately change the interactive synthetic demo and need fresh approved actions:

```powershell
.\.venv\Scripts\python.exe scripts/voice_runtime_check.py --confirm TEST-LOCAL-DEMO
.\.venv\Scripts\python.exe scripts/browser_check.py --confirm TEST-LOCAL-DEMO
```

Restore only the synthetic demo after rehearsals:

```powershell
.\.venv\Scripts\python.exe -m tools.cli reset --confirm RESET-LOCAL-DEMO
```

Reset removes actions, invitations, audit events and voice sessions, then reseeds fixtures. Old invitation links become invalid. See [build status](../BUILD_STATUS.md) and [verification evidence](local-verification.md) for actual results.

## Cloud and automated telecalling

The [cloud setup guide](cloud-setup.md) includes doctor/export/deploy/load/enrichment commands and reviewed SQL plans. The connector and CoCo executable are installed; the `samvaad_hackathon` connection stores metadata without a password. The separate hosted demo is working, while the local application's full operational cloud repository remains unimplemented.

The [production readiness audit](production-readiness.md) records verified fixes and remaining release blockers. Production is not ready. Synthetic Snowflake staging is deployed and its startup is verified by the owner. The setup helper stores metadata only; native password and MFA are entered privately during owner setup. Subsequent GitHub releases use OIDC. Current trial expiry/credit entitlements still need an account check.

For a standard Snowflake trial, keep production action/consent/session state in PostgreSQL and use Snowflake for Customer 360/Cortex analytics. Standard Snowflake table keys are unenforced and hybrid tables are unavailable in standard trials. The PostgreSQL adapter remains to be implemented. Standard trial credits also do not establish CoCo access; verify a paid or dedicated CoCo trial account.

The [self-hosted telecalling plan](telecalling-plan.md) specifies Asterisk ARI, a durable worker, local Whisper recognition, a stock neural voice, human handoff and a licensed SIP trunk. Parler Mini v1 is the provisional production voice candidate. Its complete tokenizer/codec/runtime bundle still needs a pinned license review and target-hardware benchmark; the installed Windows voice is only the local lab provider. See the [voice license review](voice-license-review.md) and [deployment scaffold](../infra/voice/README.md).

Production identity, carrier delivery, Hindi/accent quality checks, full Snowflake/Cortex application integration, and real CoCo execution remain pending. The Twilio pilot uses stock provider speech; PBX integration and neural voice assets belong to the optional self-hosted path. Insurance claims are an additional domain; this release implements the lender PRD. The [submission guide](submission-guide.md) records the challenge fit, participant-provided timing and remaining CoCo requirements; local operation alone does not establish Snowflake/CoCo eligibility.
# GitHub deployment

Source and deployment workflow: [public repository](https://github.com/Cherie05/samvaad360). See [the GitHub deployment guide](github-deployment.md) for completed Snowflake OIDC setup and subsequent releases. [The verified release](https://github.com/Cherie05/samvaad360/actions/runs/37483107870) passed 557 tests and private app deployment; the owner separately confirmed private hosted startup. Ordinary code pushes to `main` test and deploy automatically.
