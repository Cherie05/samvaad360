# Samvaad 360 product and production plan

Updated **6 October 2026, IST**. The redesigned prototype is live at [samvaad360.streamlit.app](https://samvaad360.streamlit.app/); its source is [Cherie05/samvaad360](https://github.com/Cherie05/samvaad360). The release passed **11 independent hosted-browser checks**, using the live Snowflake source and 20 fictional customers. [GitHub run 37365585311](https://github.com/Cherie05/samvaad360/actions/runs/37365585311) passed tests and deployment for source `0d78eb7d7d0d355e933d2bf31955dc2deb569eca`. This document separates that shipped prototype from the production work still required. See [build status](../BUILD_STATUS.md) for release evidence.

## Product focus

The implemented extension adds portfolio exposure and intervention charts, a repayment/conversation timeline, explicit retention-rule contributions, governance coverage, a four-context comparison and a downloadable decision evidence packet. Shared hourly Snowflake snapshots now enforce application-query budgets and visitor throttling. A genuine Twilio telephone transport and staff-only existing/additional-number controls are prepared but unconfigured. See [the enterprise implementation and release plan](enterprise-release-plan.md) for current protection scope, carrier activation and remaining production gates.

Build a lender officer's workbench that answers three practical questions: **Who needs attention, what should we do, and what changed after the conversation?** Combine loan and repayment facts with borrower emails, chats and call transcripts. Give each recommendation a reason, source evidence, required reviewer and contact policy.

The distinctive demonstration is a complete loop:

**Customer evidence → policy decision → reviewed conversation → new borrower evidence → revised action.**

An attractive dashboard makes that loop understandable. The underlying evidence and policy adaptation make it useful. There is no guarantee of winning. The official rubric assigns **40% to technical execution, 30% to real-world relevance and 30% to solution completeness**. The chosen challenge asks for structured and unstructured customer touchpoints, including call transcripts, and a next-best-action recommendation. [Official hackathon page](https://hack2skill.com/event/cococlihack-gccedition/)

The owner's participant portal lists **6 October 2026, 11:59 PM IST** as its submission deadline. The public event page still lists an earlier prototype window; this document does not claim the extension was independently verified. Prioritise a working, accurately described lender journey and the required submission artifacts. Insurance claims and validated underwriting models are later domain releases.

## How the existing application works

| Component | Implemented baseline | Boundary |
| --- | --- | --- |
| Public frontend and backend | Streamlit/Python in `public_app/streamlit_app.py`, hosted on Community Cloud | The Python process renders the UI and runs the domain service; a separate REST server is not required for this prototype. |
| Public database connection | Dedicated Snowflake service-key reader; four fictional snapshot tables in `SAMVAAD_STAGING.PUBLIC_DEMO` | Fixed bound read queries; 20 fictional customers. The public identity cannot save staff approvals or change financial terms. |
| Public review state | Browser-visit Streamlit session state | A simulated review belongs to that visit. It is not a durable staff decision or a Snowflake ledger write. |
| Public Call studio | Bounded visit-local conversations with permission/fictional identity gates, borrower replies, outcome export and hardship/opt-out adaptation | A current approved simulation review is required. Browser speech controls are optional; actual audible playback was not established by the browser checks. No microphone capture, telephone call or database write is represented. |
| Scenario comparison | New context is evaluated on a copy of the customer view using the shared decision rules | Before/after results are reversible simulations. They do not overwrite the shared Snowflake customer or payment records. |
| Evidence and recommendations | Shared Python rules and evidence summaries in `samvaad/` | Illustrative policy scores and affordability checks, rather than validated churn probabilities or real credit decisions. Public answers do not invoke Cortex. |
| Private operator demonstration | Separate Streamlit app inside Snowflake; Snowpark-backed reads and demo review records | Owner-authenticated demo reviews persist in Snowflake. This is separate from public session state and from the full production operational service. |
| Local staff application and API | Streamlit staff UI, FastAPI integration endpoints and transactional SQLite demo state | Development identities and synthetic data; the full operational cloud repository remains pending. |
| Local voice lab | Bounded persisted conversations, installed Windows speech synthesis and pinned local Whisper recognition | Tested local speech is not a carrier call, production identity verification or a portable production voice deployment. |

If Snowflake is unavailable, the public app can use its checked fictional bundle and displays the actual source. Backup results must not be presented as live Snowflake or Cortex responses. Free website hosting does not make database queries or future phone calls free. Trial expiry can suspend Snowflake even when a balance remains. [Snowflake trial conditions](https://docs.snowflake.com/en/user-guide/admin-trial-account)

## Shipped prototype experience

Five workspaces now expose the workflow:

1. **Command center:** portfolio counts, a prioritised case queue and guided hardship, retention, top-up and contact-restriction examples. Counts describe the fictional portfolio; estimated interest differences are illustrative, not recovered revenue.
2. **Customer 360:** customer summary, repayment facts, interaction timeline, readable action/offer fields and policy checks. A before/after scenario comparison shows how new context changes the recommendation.
3. **Evidence desk:** scoped customer questions and source excerpts supporting deterministic answers and recommendations. Public answers do not trigger a Cortex request.
4. **Review queue:** pending/completed simulated reviews with a decision, note and export. Anonymous decisions remain isolated between visits and are distinct from real staff approvals.
5. **Call studio:** a fictional borrower/lender conversation with permission and account-holder confirmation, typed or suggested replies, optional click-to-play browser speech, opt-out and officer-handoff outcomes. New hardship stops an earlier growth invitation, exposes the added evidence and revised decision, and puts further contact on hold for that visit. A conversation record can be exported.

The redesigned forest/off-white interface uses readable cards, status labels, clear primary actions, empty-state guidance and a mobile layout. The current release passed hosted workflow and mobile checks. Browser voice controls and text fallback were inspected; audible playback, speech quality and assistive-technology coverage still require their own checks.

New utterances and demonstration outcomes stay in the visitor's simulation. The public reader cannot update the shared fictional snapshots or another visitor's review. A browser conversation and its optional speech preview are a rehearsal: no real telephone call, delivered invitation or financial change occurs.

## A strong judge journey

**Kabir C0007: a recommendation that adapts.** In Customer 360, start with his overdue-payment facts and gentle reminder. Choose the new-hardship scenario and compare the actions, or use the statement "I lost my job and cannot pay my EMI. Please help" in a reviewed Call studio rehearsal. Show the new fictional interaction and the policy switch to supportive hardship contact. His existing overdue status matters: the current hardship action requires both hardship evidence and DPD between 1 and 60. The comparison and call outcome remain visit-local; no payment break or changed loan terms are promised.

**Imran C0003: growth that stops when circumstances change.** Inspect his repayment history and top-up-interest evidence, then review the conditional invitation in the simulation. During the conversation introduce new repayment hardship. Stop the growth invitation and record an officer-review/callback outcome. His DPD is zero, so the existing engine must not invent a hardship-action recommendation whose overdue-payment condition is unmet. Show the actual resulting policy decision.

**Neha C0004: consent wins over opportunity.** Show the contact restriction and blocked action. In a permitted fictional conversation, demonstrate that an opt-out ends contact and prevents later simulated contact for that visit.

These implemented cases establish traceable synthetic behaviour; they do not prove real-world churn reduction, revenue uplift or underwriting quality. The hosted release verified that new hardship closes an earlier growth conversation and blocks its continuation. Real borrower authentication and live telephone delivery are separate production gates.

The supplied portal additionally requires a **3–5 minute video**, one working CoCo CLI workflow with **Input → Processing → Output**, and **2–3 modular capabilities**, plus the organizer-template PDF under 5 MB. Local CoCo 1.1.87 and discovery of all three `.cortex/` project skills are verified. Actual account/model access, skill invocation and hook execution remain unverified, and the recording and PDF remain pending. A successful Cortex SQL connection test is separate evidence. Show evidence inspection, recommendation generation and an explicitly approved simulated execution; never let the assistant approve its own financial proposal. These prepared skills target the local operational demo; a public simulated review does not approve a local CLI action. [CoCo CLI documentation](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli)

## Recommended production architecture

Keep the current Streamlit website as the live synthetic prototype. A React/Next.js TypeScript frontend is an optional later migration for a richer staff console and borrower portal; it is not needed to keep this prototype online.

```mermaid
flowchart LR
    Staff[Authenticated staff console] --> API[FastAPI policy and workflow service]
    Borrower[Authenticated borrower portal] --> API
    API --> PG[PostgreSQL operational database]
    PG --> Outbox[Transactional outbox]
    Outbox --> Worker[Durable conversation and delivery worker]
    Worker --> PBX[Private Asterisk ARI service]
    PBX --> SIP[Contracted SIP trunk]
    SIP --> Phone[Permitted customer destination]
    PBX --> Speech[Self-hosted ASR and TTS]
    Speech --> Worker
    Worker --> PG
    PG --> Ingest[Scoped analytical ingestion]
    Ingest --> SF[Snowflake Customer 360 and transcripts]
    API --> SF
    SF --> AI[Bounded Cortex enrichment and answers]
```

| Layer | Production choice and responsibility |
| --- | --- |
| Frontend | Retain Streamlit for an initial authenticated staff pilot; optionally move to React/Next.js for the full console. Browsers call the application API and never hold database, model-provider or PBX credentials. |
| Application backend | FastAPI plus the shared Python policy/conversation modules. Enforce authenticated roles, customer scope, current consent, reviewed terms, expiry and replay checks on the server. |
| Operational database | PostgreSQL for tenants, staff assignments, consent versions, approvals, actions, outbox jobs, call events, callback requests and deliveries. Make review/action/outbox changes atomic. |
| Worker | Claim outbox jobs with leases and retries. Use a durable event ID to deduplicate repeated or reordered events. Reconcile an ambiguous dial request with the PBX before retrying. Redis may assist admission limits or caching; PostgreSQL remains the authoritative state. |
| Analytics and AI | Snowflake for governed customer facts, interactions, lineage and outcome analytics. Use scoped service identities/views and tenant/customer filters. Bound Cortex requests, timeouts and spend; treat retrieved text as evidence, not executable instructions. |
| Audio and recordings | Private object storage with access controls, authorized recording state, retention/deletion and audited retrieval. Store references in PostgreSQL; do not expose recordings through anonymous public links. |
| Voice and telephony | Separate self-hosted ASR/TTS processes, a private Asterisk process controlled through an adapter, and a contracted SIP trunk for external calls. Production voice assets and carrier delivery are still dependencies. |

Derive staff roles from trusted login: agent, manager, credit reviewer, tenant administrator and a distinct automation principal. An agent can propose; the designated reviewer can approve; the worker can execute only the approved frozen proposal. Enforce tenant and assigned-customer scope on every read, review, transcript and export. Borrower account access requires a separately approved authentication flow. A spoken "yes" is only a synthetic demo gate.

## Delivery phases and release checks

| Phase | Deliverable | Required release evidence |
| --- | --- | --- |
| 0 — Public prototype refresh | Shipped officer workbench, readable journey/evidence, Call studio rehearsal and policy adaptation | **Verified:** 11 hosted-browser checks, live Snowflake source, 20 fictional customers and successful test/deployment run for `0d78eb7`. Browser speech controls/text fallback are present; audible playback is not verified. Real calls and database writes remain disabled. |
| 1 — Operational cloud staging | PostgreSQL repository, FastAPI contracts, versioned approvals/consent and transactional outbox | Concurrent approval/claim tests, stale-consent denial, replay/conflict handling, crash/retry recovery and data reconciliation against the existing synthetic domain behaviour. |
| 2 — Trusted staff pilot | Login, server-derived roles, tenant/customer scopes, secret management and audit access | Wrong-role and cross-customer/tenant tests fail safely; authenticated exports are scoped; secrets rotate; HTTPS, request limits, backup restoration and deletion are rehearsed. |
| 3 — Scoped analytics and AI | Ingested interactions/outcomes, grounded Cortex enrichment and evidence answers | Confirm source lineage, borrower/assistant speaker separation, customer isolation, answer-quality evaluation, bounded query/model use and visible stale/unavailable-data behaviour. |
| 4 — Self-hosted voice and SIP lab | Pinned speech assets, ASR/TTS worker, Asterisk adapter and private softphone conversation | Asset/license inventory and notices reviewed; measured speech quality and latency; test silence, noisy audio, financial numbers, interruption, opt-out, human handoff and PBX event reconciliation. No external dialing in this phase. |
| 5 — Controlled carrier pilot | Contracted trunk, allocated calling identity and approved test destinations | Lender/carrier approve purpose, recipients, calling policy, recording and borrower authentication. Verify actual answer/hangup/audio/transfer events and suppress duplicate origination. Use explicitly permitted test recipients. |
| 6 — Production operation | Defined capacity, on-call ownership, monitoring, restore/rollback and quality evaluation | Measured warm/cold load, worker lease recovery, retention/deletion, protected audit records, incident drills and pilot acceptance. Validate business policy/model use on permitted real data before broader rollout. |

No phase authorizes an assistant to negotiate unreviewed terms, disburse a loan or place arbitrary calls. Define acceptance targets with the lender and measure them; do not substitute library benchmarks for deployed capacity or voice quality.

## What real automated calling requires

The current public Call studio uses the visitor's browser speech API for optional lender playback and typed/suggested borrower replies. It does not deploy self-hosted ASR/TTS or connect to a SIP network. Browser/OS voices are selected by the visitor, and their available voices and playback behaviour vary. The separately tested local Windows/Whisper lab is not the public site's audio backend.

The conversation controller should check consent and the approved action before dialing and again when circumstances change. Disclose the automated assistant, apply the approved recording policy, authenticate the borrower before revealing account details, confirm recognized amounts/dates and offer a person when uncertain. Persist opt-outs and cancel affected jobs; record a callback request without claiming a call was scheduled or a transfer completed before provider confirmation.

Asterisk ARI provides call/media control and asynchronous events. Place it behind the application server; it should not be directly accessed from a staff web page. The adapter must implement the media transport and event reconciliation for the selected deployed version. [Asterisk ARI architecture and production practices](https://docs.asterisk.org/Configuration/Interfaces/Asterisk-REST-Interface-ARI/)

Whisper-based self-hosted ASR and a stock neural TTS voice are candidate components. The existing voice review selects Parler Mini v1 provisionally; its exact model, tokenizer, codec, runtime and notices still need deployment review and measured English/financial-entity quality. Windows SAPI remains a local host feature. No custom voice recording is required for the proposed stock-voice route, and no blanket license clearance is claimed. See [voice asset review](voice-license-review.md).

Owning the software does not supply a carrier connection, calling number, recipient permission or recording rights. A licensed SIP-trunk arrangement and the lender/carrier's approved automated-calling process are necessary for real destinations. Hosting, inference hardware, storage, number rental and carrier minutes need an actual cost estimate. See the detailed [telecalling plan](telecalling-plan.md) for the existing state machine, media, asset and carrier gates.

## Current release boundary

The redesigned website is a fictional lender prototype with genuine restricted Snowflake reads, five working workspaces, a priority queue, evidence/scenario comparisons and visit-local review/conversation simulations. New conversation evidence can stop a growth proposal and show the policy response for that visit. The separate operator demonstration persists demo reviews in Snowflake; the local voice lab persists synthetic conversations in SQLite. These are three different state boundaries.

Production PostgreSQL workers, trusted multi-tenant identities, live carrier calling, production voice assets and validated credit/churn models remain planned until their release evidence exists. Actual CoCo authentication/execution, the required recording, the organizer-template PDF and final participant-portal submission also remain pending. Future releases should retain their actual results in [build status](../BUILD_STATUS.md), [public deployment](public-website-deployment.md) and [submission fields](hackathon-submission.md).
