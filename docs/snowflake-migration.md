# Snowflake migration handoff

Updated 5 October 2026, IST. The five-tab local application, shared domain workflows, API, invitation pages, and persistent Voice lab are implemented. Local audio uses installed Windows SAPI and provisioned Whisper CPU ASR. The Snowflake connector is installed, and executable analytical setup/export/load/enrichment tools are prepared. No named account connection or warehouse is configured; no Snowflake database, deployment, Cortex inference, live phone call, or production identity has been activated. Trial credit balance/expiry and CoCo eligibility remain unverified.

## 1. Connect and inspect before applying cloud assets

Configure a private named Snowflake connection and select an existing warehouse in `.local/cloud.toml`. Keep credentials in the supported private Snowflake configuration, outside project files and command arguments. Run `python -m scripts.cloud_doctor`, then `--connect` for metadata-only discovery. Verify actual account type, region/model access, account privileges, and credit budget separately; metadata visibility alone does not prove every capability.

The current [capability report](../output/cloud/capabilities.json) records the installed connector and missing connection/warehouse. The [cloud setup guide](cloud-setup.md) gives executable commands and their default plan-only behavior. These tools never create an account, warehouse, privileged role, or grant.

## 2. Apply and reconcile the analytical layer

Review `output/cloud/deploy.sql` and the source SQL in `cloud/sql/`. The prepared layer contains RAW customers/loans/payments/interactions, CORE financial/evidence views, and AI raw-result storage. `cloud_export` produces a reproducible 20-customer bundle with 21 loans, 370 payments, 22 interactions, a timezone-aware reference, and a manifest checksum.

Use `cloud_deploy --apply` and `cloud_load --apply` only with the configured account and reviewed database/warehouse. Import uses bound values, refuses mismatched populated tables, verifies counts/checksums/unique fixture IDs, and rolls back a failed bootstrap. Identical completed reload is a no-op. Run one bootstrap loader at a time; this does not provide a concurrent standard-table uniqueness guarantee. Reconcile active-loan aggregates and payment totals before connecting the frontend.

## 3. Implement a transactional operational adapter

Standard Snowflake PRIMARY KEY/UNIQUE/FOREIGN KEY declarations do not provide the enforced guarantees needed for action claims, approvals, scoped offer responses, consent, and persistent voice sessions. Hybrid tables enforce these constraints but are unavailable in standard trial accounts. [Constraint overview](https://docs.snowflake.com/en/sql-reference/constraints-overview), [hybrid availability](https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations).

For the trial deployment, implement PostgreSQL operational storage plus Snowflake analytical data. PostgreSQL owns authoritative catalogue/action/approval state, response IDs, offers, consent changes, voice-session claims, durable outbox delivery, and audit. Replicate approved facts/events to Snowflake with explicit source IDs. An eligible paid-account hybrid implementation is an alternative requiring its own transaction/concurrency validation.

Neither adapter exists yet. Preserve the service contract behind `samvaad/factory.py`; the current factory intentionally raises `CLOUD_PENDING` for cloud mode. Port the existing atomic claim/replay/opt-out behavior and tests, including one active voice session per action. Do not replace it with check-then-send logic over unenforced analytical keys.

Bind approvers to trusted identity and provision a separate automation principal. Recheck eligibility, consent/DND, frozen terms, catalogue version, expiry, retries, and calling purpose at the authoritative execution boundary. A UI selector, arbitrary role parameter, or CoCo hook cannot supply production authorization.

## 4. Evaluate and integrate Cortex providers

`cloud_enrich` prepares or explicitly runs bounded AI_CLASSIFY, AI_SENTIMENT, and AI_EXTRACT jobs, defaulting to five interactions. Source IDs/hashes and raw result/error objects are preserved. This is a prepared enrichment job, not a live application provider. Validate borrower-only speech, negation, competing rates, categorical-to-numeric sentiment mapping, unknown facts, and failures before any decision refresh.

Optional Search is defined with customer/interaction/channel attributes and scheduled initialization. Enforce server-side customer authorization and filters on every query: Search uses its owner's rights. Its 1800-second serving auto-suspend does not stop indexing. [Search access model](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/query-cortex-search-service), [suspend behavior](https://docs.snowflake.com/en/sql-reference/sql/alter-cortex-search).

Implement the missing application Search/Analyst/Agent providers with a narrow recommendation-queue tool. Approval and outbound execution remain outside assistant authority. Run golden questions and cross-customer/bypass regressions against real Cortex responses; local deterministic answers do not establish those live results.

## 5. Deploy frontend, API, and identities

Choose Streamlit in Snowflake with a reachable, trusted operational backend, or a separately hosted frontend/application tier if that better fits the PostgreSQL/voice worker topology. Verify the actual connection/secret/network mechanism before promising this deployment. `app/environment.yml` is a dependency scaffold, not a hosted website.

Deploy FastAPI offer endpoints over HTTPS. Replace local bearer/persona simulation with trusted operator identity, tenant/customer authorization, and a separate automation identity. Preserve opaque-token scoping, atomic consent/expiry checks, exact-event replay, escaped output, and token redaction. Test denied and allowed paths across actual analyst, manager, credit, and worker sessions.

## 6. Prove CoCo independently

CoCo is not currently discoverable. Standard Snowflake trial credits do not establish CLI eligibility: Snowflake documents paid accounts or a dedicated CoCo trial. [CoCo requirements](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

After installing/configuring an eligible account, run `python -m scripts.cloud_coco_check`, then optional `--run-smoke`. This verifier checks actual help/version and exact-marker model output; code-mode smoke does not verify project skills. Use a standard interactive session to demonstrate skill discovery, recommendation generation, separately approved execution, and real hook invocation. Save redacted session evidence. Python CLI and hook unit checks remain separate evidence.

## 7. Release the telecalling stack separately

The local `VoiceService` is persistent and guarded. It includes transcript permission, synthetic account-holder confirmation, bounded approved dialogue, opt-out, hardship deflection, replay handling, and the Customer 360 feedback loop. Its verbal identity check is not production borrower authentication. Local SAPI/Whisper WAV checks demonstrate a local audio path, not a phone-bandwidth or customer-call benchmark.

Parler Mini v1 stock voice is the provisional production English TTS candidate, subject to pinned weights/tokenizer/encoder/codec/runtime inventory, notices, and audible quality/latency evaluation. Mini v1.1 stays disabled pending tokenizer terms. Deploy ASR/TTS and a durable session worker separately from Asterisk/PBX, validate a private SIP lab first, then verify a carrier-approved trunk/number/recipient and calling/recording policies. Neither a PBX nor carrier-connected worker is deployed. [Telecalling plan](telecalling-plan.md), [voice asset review](voice-license-review.md).

## 8. Cloud and live acceptance gate

Require reconciled facts; real scoped Cortex citations; expected hero workflows; dynamic caps; trusted approval; atomic competing-worker/event handling; consent/retry/expiry controls; actual CoCo evidence; HTTPS invitations; and one traceable outcome refreshing Customer 360. For voice, also require authorized identity/recording, media-format checks, measured ASR/TTS quality, opt-out propagation, human callback/handoff, and crash/origination reconciliation. Capture actual cost and latency; scale beyond the synthetic cohort only after these checks pass.

The [original build plan](../output/Samvaad360_Build_Plan.md) remains planning/hackathon context. Its October 5 implementation update identifies the delivered local scope. No browser-layout approval, cloud deployment, live call, or contest eligibility is implied by this handoff.
