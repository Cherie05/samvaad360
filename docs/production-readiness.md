# Production readiness and cloud transition

Updated 6 October 2026 IST. **Production deployment: NO-GO; public synthetic prototype: verified live.** The redesigned public website passes 11 independent hosted-browser checks with live Snowflake reads, and GitHub passes 283 tests. The private Snowflake demo also opens under the owner's account and saves review records; a bounded Cortex model request succeeds. These demonstrations require the controls below before serving real staff or borrowers. See [the phased product and production plan](product-production-plan.md).

The enterprise extension implements shared snapshot/query protection, verified-edge IP support, charts and a genuine controlled-pilot Twilio transport. Its stock speech, possession verification and signed callbacks do not establish production borrower identity, delegated staff permissions or live carrier acceptance. The separate SQLite telephone ledger and server-only OIDC staff bridge are described in [enterprise release gates](enterprise-release-plan.md). No provider request, phone call or SMS was sent during implementation.

## What was checked and fixed

The review covers source-level identity/data boundaries, approval/consent/expiry/replay behavior, actual local browser and speech/API journeys, known Python package advisories, runtime recovery, voice asset status and current Snowflake account/runtime prerequisites. Tests use isolated databases. This is not a penetration test, production load test, credit-model validation or blanket license approval.

| Check | Evidence |
| --- | --- |
| Current automated gate | **283 passed**, one nonblocking test-client warning; 40.53 seconds. [Latest GitHub test/deployment run](https://github.com/Cherie05/samvaad360/actions/runs/37365585311), source commit `0d78eb7` |
| Public website | Eleven anonymous hosted-browser checks with Snowflake: five workspaces, policy/evidence, review gates, voice controls/text fallback, conditional negotiation refusal, evidence-driven hardship change, isolation, scoped answers, what-if, consent and mobile layout. `output/cloud/public-browser/hosted/result.json` |
| Actual website rehearsal | Six browser checks: scoped Customer 360, approval role, voice gates/audio/interest, invitation callback, cited answer and mobile overflow. `output/local-browser-check.json` |
| Actual voice/API rehearsal | Five checks: authenticated readiness, actual SAPI WAV, actual local Whisper recognition, persisted callback and exact replay/no hardship invitation. `output/local-voice-runtime-check.json` |
| Package compatibility | `pip check` passes |
| Known dependency advisories | After targeted pip 26.2.1/setuptools 84.0.0 updates: zero findings across 101 distributions, no skips. `output/production-dependency-audit.json`; initial findings retained separately |
| Cloud account and startup | Account/role/region verified; synthetic import reconciled. Owner confirms all four hosted tabs and saved reviewer note. One Cortex connection request returned `OK`; CoCo account/skill/hook use remains unverified. `output/cloud/trial/result.json` |
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
| P0 | The operational repository remains SQLite; the full cloud service factory raises `CLOUD_PENDING`. Scoped Snowflake analytics and a Twilio transport are implemented separately. | Implement/test the transactional operational repository, authoritative approvals/consent/outbox and the complete cloud service integration. Reconcile fixtures and run real cloud contract checks. |
| P0 | The separate private demo runs on supported Streamlit 1.52.2, but the full local application and telephone worker are not migrated. Windows SAPI cannot run in Snowflake Linux hosting. | Choose and verify the operational host/runtime, trusted identities, HTTPS invitations and production network/provider access. The working analytical demo does not clear these gates. |
| P0 for real calls | A genuine Twilio adapter with stock provider speech exists, but carrier configuration and live acceptance are absent. Verbal account-holder confirmation is a pilot check; a staffed transfer worker is absent. | Configure the carrier, HTTPS API and trusted staff access; verify permitted test calls, consent, borrower authentication, speech quality, recovery and human handoff. A neural voice bundle and PBX/SIP lab apply to the optional self-hosted voice path. |
| P1 | Persisted sessions have no automatic lease/watchdog/origination reconciliation. Inference lacks application admission quotas/deadlines. | Durable workers/outbox, idempotent carrier events, crash/timeout recovery, bounded concurrency and measured warm/cold load results. |
| P1 | Backups, restore rehearsal, retention/purge, protected audit storage and operational alerts are missing. Private-demo GitHub deployment is tested; production release/rollback controls remain pending. | Demonstrated restore/deletion, protected secrets/audit, HTTPS/rate/body controls, dependency/binary inventory, monitoring/runbooks and production rollback. |
| P1 | Rules and supported answers use synthetic facts and heuristics, not validated credit/churn models. Insurance claims are not implemented. | Evaluate real permitted data and narrowly authorized business policies; define and test the intended lender/insurance release separately. |

New recording rules do not automatically remove every historic trace. The owner reset this entirely synthetic demo after rehearsals. Any real historical data would require an authorized retention/migration cleanup, including database journals/backups and earlier raw access logs. See [runtime audit](production-runtime-audit.md) and [voice asset review](voice-license-review.md).

## Cloud staging sequence

The public website was independently verified in fresh anonymous browser contexts with its Snowflake source and all 11 workflow checks passing. Public reviews, opt-out holds and conversations last for that visit; they are not authoritative staff approvals or durable contact preferences. Speech controls and transcript fallback are verified, but browser voice audibility is unverified. No phone call or financial change occurred.

For the separate private app, the owner confirms all four main tabs open after the Python patch pin. [The latest GitHub workflow](https://github.com/Cherie05/samvaad360/actions/runs/37365585311) passed 283 tests, authenticated with temporary OIDC credentials, deployed `SAMVAAD360`, confirmed 20 customers and restored its live copy after commit. Request `e4bae60f7f3b4669999d98399b258f4b` saved; the queue later displayed the reviewer and note. The exact status and separate manual-refresh result were not supplied. [One fixed-prompt Cortex request](https://github.com/Cherie05/samvaad360/actions/runs/37338451069) returned `OK`; grounded-answer quality/enrichment and CoCo execution are still unverified. Private Snowsight browser evidence is the owner's report.

Earlier cloud preflight passed 199 tests, including 24 cloud-port checks on Streamlit 1.52.2; the current complete suite has 283 passing tests. Resource/schema creation, synthetic import reconciliation and private hosting completed. CoCo 1.1.87 version/help and the exact native `cortex.exe skill list` command are verified; all three project skills are locally discovered. Authentication, model use, actual skill execution and runtime hooks still require verification. The separate Snowpark/Streamlit demonstration does not implement the local application's production repository or move its financial/voice execution. The cloud runtime has two documented upstream advisories; see [runtime review](cloud-runtime-advisories.md) and [the account guide](hackathon-cloud-setup.md). Initial local audit results and original release hashes are retained as historical evidence in output reports.

1. Completed: obtain account/user, authenticate privately and create `SAMVAAD_XS`. The earlier dashboard reported $400 and six days remaining; current billing and expiry have not been verified.
2. Completed: store credential-free connection metadata, establish main-branch GitHub OIDC and verify the account/role before releases. No personal Snowflake password or MFA code is stored in GitHub.
3. Completed: create scoped resources/schema/views, load and reconcile synthetic facts, repair hosted startup and make one bounded Cortex capability request. Pending: current entitlements, customer-answer/enrichment validation, exact approved-review status after manual refresh and actual CoCo account/skills/hooks.
4. Implement operational cloud state and analytical providers, bind trusted staff/borrower identities and rehearse the complete deployed workflows. Analytics rows and a demo review table do not migrate financial execution.
5. Release production voice/carrier integration only after its independent asset, media, identity and operations gates pass.

Self-service trial AI features are disabled by default until a credit card is added. Adding a card is separate from upgrading; the owner controls billing changes. Standard trials also exclude hybrid tables, external network access and Duo MFA. Trial suspension can occur at expiry even when unused balance remains. [Official trial conditions](https://docs.snowflake.com/en/user-guide/admin-trial-account).

For a standard trial, PostgreSQL remains the proposed operational database and Snowflake the analytical layer. A visible Postgres menu is not proof of a provisioned instance or tested adapter. CoCo requires an eligible paid account or dedicated CoCo trial; ordinary trial credits do not establish access. [Hybrid limitations](https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations), [CoCo requirements](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

Current hosting facts: [Streamlit dependencies](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management), [runtime differences](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/runtime-environments). Follow the concrete [hackathon setup guide](hackathon-cloud-setup.md) for completed resource setup and dashboard navigation. The initial audit made no cloud changes; subsequent authorized setup created the synthetic database and private app resources. No credit-card change or live call has been made.
