# Production readiness and cloud transition

Audited 5 October 2026, IST. **Production deployment: NO-GO.** The local synthetic lender MVP passes its functional checks. The next step is controlled Snowflake analytics staging with fictional data, after private account authentication. The existing demo UI requires production controls before it can serve real staff or borrowers.

## What was checked and fixed

The review covers source-level identity/data boundaries, approval/consent/expiry/replay behavior, actual local browser and speech/API journeys, known Python package advisories, runtime recovery, voice asset status and current Snowflake account/runtime prerequisites. Tests use isolated databases. This is not a penetration test, production load test, credit-model validation or blanket license approval.

| Check | Evidence |
| --- | --- |
| Current automated gate | **175 passed**, no failures/errors/skips; about 47 seconds. `output/production-readiness-tests.xml` and `output/production-readiness.json` |
| Actual website rehearsal | Six browser checks: scoped Customer 360, approval role, voice gates/audio/interest, invitation callback, cited answer and mobile overflow. `output/local-browser-check.json` |
| Actual voice/API rehearsal | Five checks: authenticated readiness, actual SAPI WAV, actual local Whisper recognition, persisted callback and exact replay/no hardship invitation. `output/local-voice-runtime-check.json` |
| Package compatibility | `pip check` passes |
| Known dependency advisories | After targeted pip 26.2.1/setuptools 84.0.0 updates: zero findings across 101 distributions, no skips. `output/production-dependency-audit.json`; initial findings retained separately |
| Cloud account discovery | Connector installed; no configured connection/warehouse or CoCo executable. No account contacted. `output/cloud/capabilities.json` |
| Cloud setup helper | Credential-free TOML metadata, no changes by default, preserved existing connections, conflict rejection, hidden local password/MFA input and safe error handling; offline regressions |

Resolved defects:

- Public invitation forms enforce their 2 KB limit while streaming; oversized tails are not consumed.
- The supervised API disables raw HTTP access logging so invitation capability paths are not logged. Historical logs are not automatically scrubbed; reset synthetic invitations are invalidated.
- Unexpected UI exceptions show a generic message and log only their type.
- New voice events store a payload fingerprint, rather than raw text. Unconsented borrower turns are not stored in the transcript; exact replay and payload-conflict checks remain enforced. Fingerprints are operational records, not a general anonymization guarantee.
- Unconsented repayment hardship closes a growth conversation for officer review without retaining the utterance or creating an invitation.
- The legacy voice-event schema migration holds a writer lock, including when multiple constructors start together.

## What blocks production

| Priority | Blocker | Required exit evidence |
| --- | --- | --- |
| P0 | Browser personas and API tokens are development identities. An accessible UI user can select an approver; API reads expose all demo customers/voice sessions and invitation tokens to every valid demo identity. | Trusted login, server-derived roles, customer/tenant authorization on every read/write and a distinct worker principal. Test cross-customer and wrong-role denial. |
| P0 | Only SQLite/local providers are implemented; cloud mode raises `CLOUD_PENDING`. | Implement/test the transactional operational repository, authoritative approvals/consent/outbox and scoped Snowflake analytical/Cortex providers. Reconcile fixtures and run real cloud contract checks. |
| P0 | Hosting compatibility is unresolved. The app needs Streamlit 1.65, while warehouse runtime currently lists support through 1.52.2; Windows SAPI cannot run in Snowflake Linux hosting. Trial external network access is unavailable. | Choose a supported host/runtime, port incompatible tab/audio/provider behavior or validate eligible container/package/network capabilities. Exercise trusted identities and HTTPS invitations on the actual deployed topology. |
| P0 for real calls | Verbal account-holder confirmation is synthetic; no production neural TTS bundle, PBX/media adapter, live carrier or human-transfer worker exists. | Reviewed borrower authentication, pinned license/notices, measured ASR/TTS quality and financial entities, PBX/SIP lab, carrier onboarding, consent/recording controls and traceable test calls. |
| P1 | Persisted sessions have no automatic lease/watchdog/origination reconciliation. Inference lacks application admission quotas/deadlines. | Durable workers/outbox, idempotent carrier events, crash/timeout recovery, bounded concurrency and measured warm/cold load results. |
| P1 | Backups, restore rehearsal, retention/purge, protected audit storage, operational readiness/alerts and release automation are missing. | Demonstrated restore/deletion, protected secrets/audit, HTTPS/rate/body controls, dependency/binary inventory, monitoring/runbooks and tested deploy/rollback. |
| P1 | Rules and supported answers use synthetic facts and heuristics, not validated credit/churn models. Insurance claims are not implemented. | Evaluate real permitted data and narrowly authorized business policies; define and test the intended lender/insurance release separately. |

New recording rules do not automatically remove every historic trace. The owner reset this entirely synthetic demo after rehearsals. Any real historical data would require an authorized retention/migration cleanup, including database journals/backups and earlier raw access logs. See [runtime audit](production-runtime-audit.md) and [voice asset review](voice-license-review.md).

## Cloud staging sequence

Latest hosted observation: the owner reported a package compilation failure when opening `SAMVAAD360`, including after simplifying its environment. Publication and data import remain complete, but hosted startup is not verified working. The [startup repair](cloud-startup-repair.md) now has eight offline guard checks. The private [GitHub workflow](https://github.com/Cherie05/samvaad360/actions/runs/37330489632) passed 210 tests and its temporary Snowflake login, then published `SAMVAAD_RUNTIME_CHECK` without a custom environment and confirmed 20 customer rows. This diagnostic's browser result remains pending; no fresh private login is needed to open it in the owner's existing Snowsight session. The main application, live models and production controls remain separate unresolved gates.

Follow-up: the full suite now passes 199 tests (`output/cloud/hackathon-preflight-tests.xml`), with 24 cloud-port checks passing on Streamlit 1.52.2. The owner privately authenticated account `ZYLTUKM-HU63768` / `ARUNVPP24`. Resource/schema creation, synthetic import reconciliation, six-file upload and `SAMVAAD360` live publication completed (`output/cloud/trial/result.json`). Hosted browser and actual model/CoCo checks remain pending. CoCo 1.1.87 version/help is verified. This separate Snowpark/Streamlit demonstration does not implement the local application's production repository or move its financial/voice execution. The older warehouse runtime has two documented upstream advisories; see [runtime review](cloud-runtime-advisories.md) and the [new-account guide](hackathon-cloud-setup.md). The 175-test table above records the earlier production audit; it is not the new full-suite count.

1. Obtain the non-secret account identifier, login name and existing warehouse from Snowsight. The owner reports $400 remaining and six days until trial expiry; the connector has not verified billing.
2. Review/run `python -m scripts.configure_cloud` with those values, then `--apply` to store local metadata without credentials. Use native password/MFA unless the account actually has browser SSO. Run the connected doctor from the owner's local terminal; password/MFA codes are never sent through chat or stored by the helper.
3. Confirm account/region/role, visible warehouse, trial limits, budget and Cortex enablement. Render plans for the configured `SAMVAAD_STAGING` database and review them. Only then apply schemas/views, load the synthetic bundle and reconcile facts. Search and real enrichment are separate metered steps.
4. Implement operational cloud state and live analytical providers, resolve hosting, bind trusted identities and rehearse deployed workflows. Analytics rows alone do not migrate the application.
5. Release production voice/carrier integration only after its independent asset, media, identity and operations gates pass.

Self-service trial AI features are disabled by default until a credit card is added. Adding a card is separate from upgrading; the owner controls billing changes. Standard trials also exclude hybrid tables, external network access and Duo MFA. Trial suspension can occur at expiry even when unused balance remains. [Official trial conditions](https://docs.snowflake.com/en/user-guide/admin-trial-account).

For a standard trial, PostgreSQL remains the proposed operational database and Snowflake the analytical layer. A visible Postgres menu is not proof of a provisioned instance or tested adapter. CoCo requires an eligible paid account or dedicated CoCo trial; ordinary trial credits do not establish access. [Hybrid limitations](https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations), [CoCo requirements](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

Current hosting facts: [Streamlit dependencies](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management), [runtime differences](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/runtime-environments). Follow the concrete [hackathon setup guide](hackathon-cloud-setup.md) for completed resource setup and dashboard navigation. The initial audit made no cloud changes; subsequent authorized setup created the synthetic database and private app resources. No credit-card change or live call has been made.
