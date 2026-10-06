# Samvaad 360 enterprise release plan

Updated **6 October 2026, IST**. This plan describes the current implementation and the remaining work needed for an authorised telephone pilot and a production service. The public prototype is [samvaad360.streamlit.app](https://samvaad360.streamlit.app/); its source is [Cherie05/samvaad360](https://github.com/Cherie05/samvaad360).

**Production readiness remains false.** Telephone transport code exists, but provider credentials, staff login, a publicly reachable HTTPS API and authorised recipient numbers remain unconfigured. No real call or verification message was sent. The final local suite passes **400 tests in 69.38 seconds**; [GitHub run 37446880972](https://github.com/Cherie05/samvaad360/actions/runs/37446880972) passes **400 in 71.42 seconds** and private app deployment, confirming 20 customers and live-version readiness for source `be60c2a`. Both local and hosted public browsers pass **15 checks** with a genuine Snowflake snapshot. Hosted verification at **2026-10-06T10:01:09.172213Z** observed the new features after the push; Community Cloud does not directly report its source commit. See [BUILD_STATUS.md](../BUILD_STATUS.md) for evidence. The local dependency audit reports zero known advisories across 103 distributions; it does not cover the private Snowflake runtime or carrier service.

## Technology stack and runtime boundaries

| Boundary | Concrete stack | Implemented role |
| --- | --- | --- |
| Public website | Python 3.11, Streamlit; declared public dependencies pin Streamlit 1.65.0, Snowflake Connector 4.8.0, cryptography 50.0.2 and Authlib 1.8.0 | Anonymous synthetic portfolio UI on Streamlit Community Cloud. [Public dependency pins](../public_app/requirements.txt). |
| Analytics and visual explanations | Deterministic Python domain rules, record aggregation and Vega-Lite charts rendered by Streamlit | Portfolio exposure, intervention mix, repayment/conversation timelines, explicit rule contributions and governance coverage. [Analytics](../public_app/analytics.py), [chart renderer](../public_app/ui/charts.py). |
| Public analytical access | Snowflake key-pair authentication, fixed bounded SQL and `GuardedSnapshotReader` | A genuine Snowflake source for 20 fictional customers in `SAMVAAD_STAGING.PUBLIC_DEMO`, served to visitors through a shared snapshot. The public adapter permits no data writes or visitor-triggered Cortex calls. [Reader](../public_app/repository.py). |
| Public simulations | Per-visit Python review and conversation state, browser speech controls | Fictional policy comparisons, review rehearsal and conversation adaptation; these states do not become operational approvals. [Public application](../public_app/streamlit_app.py). |
| Operational API | Python, FastAPI, Pydantic and Uvicorn; transactional SQLite pilot database | Operational approvals, recipient verification, call reservations, callback events and transcripts. PostgreSQL and enterprise permission services are production work. [API](../webhook/main.py), [telephony service](../samvaad/telephony.py). |
| Genuine telephone transport | Twilio Programmable Voice and Verify over HTTPS, TwiML speech/DTMF and signed callbacks | Provider-backed transport when privately configured. Current voice uses stock `<Say>` speech; no cloned voice or distributed voice-model weights are used by this integration. [Provider routes](../webhook/telephony_routes.py). |
| Staff telephone access | Streamlit OIDC, trusted `st.user` claims and a server-only per-operator API token bridge | Single-tenant pilot access for MANAGER, CREDIT and ADMIN. [Staff bridge](../public_app/telephony_client.py), [telephone UI](../public_app/ui/telephone.py). |
| Managed-host staging | Docker Compose, Python 3.11 image, NGINX reverse proxy and persistent named volumes | Separate frontend/API processes behind one loopback gateway. The image installs root dependency ranges rather than the public-app lock, so it needs its own reproducible build and dependency review. [Enterprise infrastructure](../infra/enterprise/compose.yml). |

These boundaries are deliberate: Snowflake supplies analytical records, while the separate operational store owns approvals, consent and telephone state. A public portfolio snapshot is not a production lender system of record.

## What is implemented

| Product capability | Current implementation | What it establishes |
| --- | --- | --- |
| Lender command center | Prioritised customer cases, guided stories, filters, offer cards and readable policy checks | A usable workbench over fictional lending records. |
| Portfolio analytics | Active-loan exposure by each loan's days past due, intervention mix, observed signals and attention alerts | Actual record totals and recommendations, rather than projected revenue or validated risk forecasts. |
| Customer relationship timeline | Twelve months of recorded repayment status aligned with dated customer conversations | Observable repayment and interaction history. Alignment does not establish causation. |
| Decision explanation | Contributions from the four current retention-priority rules, source IDs, contact checks and reviewer requirements | Reproducible heuristic reasoning; the score is not a calibrated churn probability. |
| Intervention comparison | Four fictional context overlays evaluated by the same policy engine | Before/after action and offer effects, with the added evidence and no database mutation. |
| Governance view | Lending-context completeness, conversation recency, citation coverage and descriptive customer-segment coverage | Visibility into available context. Synthetic segment counts do not establish fairness, model accuracy or regulatory compliance. |
| Public review and Call studio | Visit-local proposals, simulated approvals, browser speech controls, borrower replies, hardship/opt-out adaptation and export | A bounded rehearsal. No real loan, message or telephone call is represented by these controls. |
| Usage protection | Shared admission limits, a bounded hourly Snowflake snapshot, atomic application-statement reservations and a failure circuit breaker | After protected snapshot warm-up, ordinary visitor interactions use memory and invoke no Cortex request. |
| Telephone integration | Staff-only carrier operations, Twilio Voice and Verify requests, approved operational actions, destination controls and signature-validated callbacks | Genuine provider transport code, disabled until configured. A mock transport is not substituted when the carrier is unavailable. |
| Managed-host scaffold | Streamlit frontend, FastAPI service and an NGINX gateway with persistent state volumes | A staging configuration. Compose parsing is established; image builds and gateway runtime validation remain pending because the Docker engine is unavailable. |

The public data path uses the dedicated Snowflake reader and the four fictional tables in `SAMVAAD_STAGING.PUBLIC_DEMO`. The telephone operational path currently uses **a separate SQLite pilot database**. Public session reviews cannot approve its actions. These stores are not a completed production synchronization pipeline.

## A concrete differentiator to demonstrate

Demonstrate a **conversation that changes the next action**, with the evidence visible throughout:

1. Open Imran's repayment and top-up-interest evidence. Inspect the conditional proposal and the rule explanation.
2. Approve the proposal for a public conversation rehearsal.
3. Grant transcript permission and confirm the fictional account holder.
4. Introduce new job-loss evidence. Show the actual new statement, its source ID and the recalculated policy result.
5. Show that growth stops, an officer handoff is recorded, and the earlier proposal cannot continue during that visit.

For Imran's zero-DPD case, the current engine returns no eligible financial intervention after hardship. It must not invent an approved restructure. Kabir's existing overdue-payment case can instead demonstrate a policy transition from gentle reminder to supportive hardship contact. Neha demonstrates consent restrictions overriding an opportunity.

Position this as a focused, inspectable implementation. Next-best-action recommendations, customer context and explanatory decisioning already exist in [Pega Customer Decision Hub](https://www.pega.com/products/decision-hub) and [Salesforce Einstein Next Best Action](https://help.salesforce.com/s/articleView?id=einstein_next_best_action.htm&language=en_US&type=0). Market exclusivity, superior outcomes and guaranteed hackathon success have not been established.

## Public hosting and Snowflake protection

The current reader loads one shared portfolio snapshot at most once per hour. A complete refresh reserves **five application statements before connecting**: one service-identity query and four bounded portfolio reads. The connection closes after the refresh. Browsing profiles, asking for evidence, running comparisons and reviewing a public proposal then read in-memory copies.

| Protection | Current setting or behaviour | Limit |
| --- | --- | --- |
| Application statement reservation | 8 per fixed UTC hour; 64 per fixed UTC day | Each refresh reserves 5, so the day budget permits at most 12 full refresh attempts on the same protection store. Failed attempts remain charged. This counts selected application statements, not all connector protocol traffic or billed credits. |
| Refresh concurrency | One refresh under a shared reader lock | Single flight within that application process. Separate production replicas need shared coordination. |
| Visitor admission | Global and shared-unverified visitor token buckets, with separate browse/action limits | Community Cloud visitors share a limit. A new browser session does not create a new trusted IP identity. |
| Protection storage | Atomic SQLite reservations on the application host | Processes sharing that file share counters. It is not a distributed quota and does not guarantee protection after Community Cloud container replacement. |
| Backend outage | Circuit backoff; retain and date a prior Snowflake snapshot, or use the validated fictional bundle | The UI must show the actual source and age. Cached or bundled facts are not a new live warehouse response. |
| Snowflake warehouse | Existing `SAMVAAD_XS` warehouse and separate `SAMVAAD_DAILY_LIMIT` 5-credit daily monitor | Warehouse consumption is separate from the application statement counter. The monitor does not cover every AI or serverless charge. |

Streamlit explicitly describes its reported IP address as spoofable. The application therefore does not use `st.context.ip_address`, arbitrary forwarded headers or a visitor-supplied session ID as an authenticated security identity. The default Community Cloud admission scope is one shared bucket for unverified visitors. [Streamlit context documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.context)

The code can accept a future trusted gateway attestation: a canonical client IP, Unix timestamp and SHA-256 HMAC signature over `v1\n<IP>\n<timestamp>`. It checks a 60-second freshness window, duplicate headers and signature validity, then stores a keyed digest instead of the raw IP. **That signed-edge path is not deployed on Community Cloud.** A production gateway must overwrite incoming attestation headers, keep the signing secret private and prevent direct access to the origin. The provided NGINX scaffold currently strips these headers; it does not generate the attestation. [Host-local guard implementation](../public_app/security.py).

The scaffold configures peer-IP request limits of 5 requests/second with a burst of 30, a gateway-wide limit of 40 requests/second with a burst of 80, HTTP 429 rejection and a 20-connection limit per peer. WebSocket messages also need application-level admission. Behind a load balancer, configure an explicitly trusted proxy chain before treating a forwarded client address as authoritative. NGINX documents these request limits and their burst behaviour. [NGINX limit_req documentation](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)

Before increasing traffic, verify the warehouse monitor assignment and thresholds in the account. Snowflake resource monitors concern warehouse consumption; budgets are the separate tool for supported serverless and AI spending. Neither the local reservation counter nor a resource monitor establishes an exact all-account spending ceiling. [Snowflake resource monitors](https://docs.snowflake.com/en/user-guide/resource-monitors), [Snowflake cost controls](https://docs.snowflake.com/en/user-guide/cost-controlling)

## Enable an authorised telephone pilot

The **Telephone calling** controls are separate from the **Conversation rehearsal** controls. An anonymous visitor cannot dial. Telephone operations require staff authentication and an approved action in the operational database; approving a public simulation does not satisfy that requirement.

### 1. Prepare the HTTPS API and operational store

Deploy the FastAPI service behind a publicly reachable HTTPS origin with a valid certificate. Set `SAMVAAD_TELEPHONY_PUBLIC_URL` to that exact origin without a path, credentials, query or fragment. Twilio must reach the answer, turn and status callback routes. The URL used for signature verification must match the external callback URL, including its query string. [Twilio request security](https://www.twilio.com/docs/usage/security)

For a controlled single-tenant pilot, mount the SQLite operational database on persistent storage. The current API uses `SAMVAAD_BACKEND=local` and `SAMVAAD_DB_PATH`; it does not have a completed PostgreSQL implementation. Initialization seeds fictional data when the store is empty. Keep actual permitted recipient records distinct from the masked fictional customer contact fields.

### 2. Configure provider settings privately

Use the API host's secret store, or the ignored `.local/enterprise.env` for a local staging setup. Do not publish these values in GitHub, a deck, browser screenshots or chat.

| API environment variable | Purpose |
| --- | --- |
| `SAMVAAD_TELEPHONY_ENABLED` | Keep `false` until the configuration and authorised test are prepared; `true` enables configured carrier operations. |
| `SAMVAAD_TWILIO_ACCOUNT_SID` | The dedicated Twilio account identifier. |
| `SAMVAAD_TWILIO_AUTH_TOKEN` | Provider webhook-signature secret; always private. |
| `SAMVAAD_TWILIO_API_KEY_SID` and `SAMVAAD_TWILIO_API_KEY_SECRET` | Optional API-key pair for outbound provider requests; supply both or neither. |
| `SAMVAAD_TWILIO_VERIFY_SERVICE_SID` | The configured Twilio Verify service. |
| `SAMVAAD_TWILIO_FROM_NUMBER` | The permitted owned/provider-configured caller number, in E.164 form. |
| `SAMVAAD_TELEPHONY_PUBLIC_URL` | The public HTTPS API origin. |
| `SAMVAAD_TELEPHONY_PERMITTED_PREFIXES` | Comma-separated permitted destination prefixes. |
| `SAMVAAD_TELEPHONY_AUTHORIZED_TEST_NUMBERS` | Comma-separated exact authorised pilot destinations. A permitted prefix alone is insufficient. |
| `SAMVAAD_API_TOKENS_JSON` or `SAMVAAD_API_TOKEN_FILE` | Private per-operator API credentials mapped to fixed pilot identities. |

Carrier calls use the actual [Twilio Call resource](https://www.twilio.com/docs/voice/api/call-resource); recipient codes use the actual [Twilio Verify API](https://www.twilio.com/docs/verify/api). Provider billing, numbers and commercial voice terms are separate from Snowflake hackathon credits. No custom cloned voice or third-party model asset is included by this integration.

### 3. Configure staff login and the server-only bridge

Configure the Streamlit OIDC provider through private `[auth]` settings: callback URL, cookie secret, client ID, client secret and provider metadata URL. Register the correct deployed `/oauth2callback` URL with the identity provider. OIDC establishes who signed in; the application must enforce operator authorization separately. [Streamlit authentication setup](https://docs.streamlit.io/develop/concepts/connections/authentication)

Configure private frontend `[telephony]` settings with `enabled`, `api_base_url` and an `operator_tokens` mapping keyed by the exact `issuer|subject`. Each entry is a separate secret API token mapped by the backend to an authorised pilot identity. The bridge accepts claims from trusted `st.user`; it requires a logged-in identity, verified email, a future expiry and an exact issuer/subject match. Test that the chosen provider supplies the required claims. Tokens never belong in browser form fields.

The currently supported operational telephone roles are **MANAGER, CREDIT and ADMIN**. The pilot resolves fixed local identities such as `arjun`/MANAGER, `kavya`/CREDIT and `demo-admin`/ADMIN. This bridge is a single-tenant pilot, not enterprise token delegation or tenant-scoped authorization. Production needs a real identity/permission service and assigned-customer scopes.

For managed containers, supply the Streamlit secret file at `/app/.streamlit/secrets.toml` through a private read-only runtime mount or secret manager. The current image deliberately does not copy a secrets file. The Compose API can load the ignored `.local/enterprise.env`; that does not configure the frontend's separate OIDC and telephone secrets automatically.

### 4. Verify the permitted destination and operational action

Staff can register an **existing number** or an **additional number**, recording the recipient's permission reference. The number must be in the exact destination allowlist and permitted prefix set. Send a Verify code only to an authorised test recipient, then confirm the provider's verification result. A checked box alone does not mark the recipient verified.

Number possession does not establish that the recipient owns the selected borrower account. Strong borrower identity is still pending. The pilot therefore uses a generic officer-review script and does not disclose balances, amounts, rates or account terms over the telephone. A spoken account-holder confirmation is not production identity verification.

Prepare and approve the relevant action in the authenticated operational staff workflow. The telephone service rechecks the frozen proposal, current policy, contact consent, recipient/customer association and verification validity. Defaults include a 09:00–19:00 Asia/Kolkata calling window, at most 10 call reservations and 20 verification reservations over the preceding 24 hours, three action attempts, a four-hour retry interval and a 180-second call time limit.

### 5. Run one genuine provider rehearsal and capture its evidence

Use a recipient who has expressly authorised the pilot. A call request requires explicit real-call acknowledgement and a stable idempotency key. Capture the actual provider Call SID and provider-confirmed progression: queued, ringing/answered where available, and terminal status. A submitted request or network timeout is not evidence that a phone rang or a conversation succeeded.

The implementation validates signed callbacks and provider/account identity, deduplicates conversation events, records opt-out/hardship/human-handoff outcomes, and supports status reconciliation and cancellation. An ambiguous dispatch remains held for inspection; it is not automatically redialed. Verify duplicate callbacks, stale events, signature rejection, cancellation and an uncertain provider response in the deployed environment. The route verifies the configured canonical callback URL and every parsed form field; incoming proxy headers cannot choose its signature origin. Reject malformed/duplicate fields, mismatched reserved call identities and conflicting replay events. [Twilio request security](https://www.twilio.com/docs/usage/security).

Also exercise the conversation's permission and verbal identity gates, opt-out propagation, hardship suppression and speaker-labelled transcript retention. The pilot saves an authorised transcript only after its permission and identity gates; it records no call audio. A human handoff records a review request and has no staffed transfer queue. An interested response issues no loan, changes no rate and sends no financial invitation. See [the detailed pilot runbook](real-telephony-pilot.md).

`pilot_ready` currently means configuration validation succeeded. `provider_connection_verified` and `production_ready` remain false in the service status; configuration alone must not be described as a completed live provider test. No provider-backed end-to-end call has been verified for this release yet.

## Managed hosting verification

The staging files are [compose.yml](../infra/enterprise/compose.yml), [Dockerfile](../infra/enterprise/Dockerfile) and [nginx.conf](../infra/enterprise/nginx.conf). The frontend and API publish no independent host port; only the gateway publishes `127.0.0.1:8080`. This is a local staging boundary, not an already reachable HTTPS deployment.

Once a Docker engine is available, perform these checks from the repository root:

```powershell
docker compose -f infra/enterprise/compose.yml config -q
docker compose -f infra/enterprise/compose.yml build
docker compose -f infra/enterprise/compose.yml up -d frontend api
docker compose -f infra/enterprise/compose.yml run --rm gateway nginx -t
docker compose -f infra/enterprise/compose.yml up -d
Invoke-RestMethod http://127.0.0.1:8080/health
```

Start the frontend and API before the NGINX check so its `frontend` and `api` upstream names can resolve on the Compose network. A health response confirms API reachability; it does not validate an answered call, OIDC login or a production HTTPS route.

The configuration parse has passed. **The build, NGINX syntax/runtime check, startup, secret mounts, persistent-volume permissions, load behaviour and public TLS routing have not passed yet.** The current images use floating `python:3.11-slim-bookworm` and `nginx:stable-alpine` tags; pin reviewed image digests and lock dependencies before a production release. Do not expose the current HTTP staging port as the production carrier callback endpoint.

## Production acceptance gates

| Priority | Required work | Release evidence |
| --- | --- | --- |
| P0 · Genuine telephone pilot | Provider account/number/Verify setup, staff OIDC, private operator credentials, HTTPS callbacks and exact permitted test numbers | One real authorised verification and call; matching provider IDs, signed callback history, cancellation and failure reconciliation. |
| P0 · Enterprise identity | Identity-provider roles, tenant and assigned-customer scopes, revocation and strong borrower authentication | Denial tests for anonymous, expired, wrong-tenant and unassigned-customer requests; approved borrower identity flow. |
| P0 · Durable operations | PostgreSQL operational adapter, transactional outbox/worker, leases, event deduplication and controlled migrations | Crash/retry and concurrent-approval tests, restored backups and reconciled uncertain dispatches. |
| P0 · Shared protection | Trusted ingress, restricted origins, shared quota/refresh coordination and account cost controls | Spoofed-header rejection, quota enforcement across replicas/restarts and warehouse/budget alerts. |
| P1 · Recipient data | Encrypted/contact-scoped storage, secrets rotation, transcript consent, retention/deletion and audited access | Permission and deletion tests with real deployment configuration; no telephone details in public snapshots or routine logs. |
| P1 · Reliable deployment | Pinned images/dependencies, working container builds, TLS, health checks, monitoring, backup/restore and rollback | Reproducible staging build, load/recovery tests and measured operational alerts. |
| P1 · Financial workflow | Real loan-system integration, versioned approval policy, immutable reviewed terms and authenticated delivery | An authorised end-to-end institutional workflow; until then no rate change, loan issuance or pre-approval delivery is claimed. |
| P1 · Model and fairness validation | Representative labelled data, evaluation, segment analysis and reviewer feedback | Validated metrics and documented limitations. Current heuristic and synthetic dashboard counts do not meet this gate. |
| P2 · Voice choice | Review carrier/TTS commercial terms or pin and review an independently deployed voice stack | Approved exact voice/model/runtime assets and tested language, accessibility and interruption behaviour. A generic browser voice preview is separate evidence. |

Keep the current public website useful as a synthetic Customer 360 and policy demonstration while these gates are completed. For the hackathon, submit the implemented evidence-to-recommendation-to-revised-conversation loop accurately, together with actual CoCo CLI workflow evidence, the required recording and the organizer-template deck. The visual dashboard, simulations and carrier adapter should each be described according to what has been verified.
