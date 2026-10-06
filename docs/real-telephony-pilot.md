# Genuine telephone calling: implemented controlled pilot, activation pending

The telephone API uses actual Twilio Programmable Voice and Verify endpoints. It
does not synthesize a connected call or successful SMS when no provider is
configured. The public website's conversation rehearsal is a separate feature.
No real call or verification message has been sent during implementation.

The current phone workflow is a **controlled pilot**, with
`production_ready=false`. It persists reservations, provider identifiers,
conversation state, callbacks and authorised transcripts in the local SQLite
workflow database. Real staff identity, tenant/customer permissions, PostgreSQL,
strong borrower identity, monitored recovery, data retention and live carrier
acceptance remain release gates.

## Setup required to place the first authorised call

1. Provision a Twilio account, an owned/authorised outbound caller number and a
   Verify service. Restrict destinations in the provider console and keep
   credentials in the API host's secrets manager. Trial accounts can impose
   additional verified-recipient restrictions. Snowflake trial credits do not
   pay telephone, SMS, number rental or speech charges.
   [Voice call resource](https://www.twilio.com/docs/voice/api/call-resource),
   [Verify prerequisites](https://www.twilio.com/docs/verify/api/verification).
2. Deploy the FastAPI service behind a trusted HTTPS origin with durable storage.
   The prepared container is [infra/voice/Dockerfile](../infra/voice/Dockerfile),
   with independently pinned API dependencies. Its image build and hosted
   callback reachability still require verification; Community Cloud cannot
   serve these FastAPI routes merely by publishing the Streamlit frontend.
3. Set the variables in [infra/voice/env.example](../infra/voice/env.example)
   privately. Both a permitted prefix and an **exact authorised test-number
   allowlist** are required. Set `SAMVAAD_TELEPHONY_ENABLED=true` only for the
   reviewed pilot deployment. Configure the public HTTPS API origin, not the
   Streamlit URL. Keep provider tokens and staff token mappings out of GitHub,
   chat, command arguments and browser code.
4. Configure the website's staff OIDC login and its server-only API bridge. The
   pilot API permits manager, credit or admin operators resolved from configured
   bearer tokens. Those existing local identities are not enterprise SSO or
   delegated production permissions; the staff bridge is a controlled deployment
   boundary, not a claim of enterprise readiness.
5. Register the customer's existing E.164 number, or an explicitly authorised
   alternate number. Existing numbers must match the operational customer
   record. The synthetic portfolio deliberately contains masked numbers, which
   cannot be dialled. Registration requires a permission reference and the number
   owner's requested verification, then sends a genuine provider OTP message.
6. Complete provider OTP verification. Verification proves **phone possession**;
   it does not establish the borrower's account-holder identity or KYC. Verify
   expires locally after 10 minutes and allows five check attempts; a successful
   recipient registration is valid for 30 days. The pilot permits at most three
   verification requests per number per day and 20 overall.
7. Separately approve a current operational action, select its verified recipient,
   and explicitly acknowledge a real carrier call. A public visit's simulation
   review cannot authorise this operation. The normal call window is 09:00–19:00
   Asia/Kolkata, with a 10-call daily budget, three attempts per action and a
   four-hour retry interval. Adjust policy only through a reviewed deployment.

## Executed phone workflow

The provider accepts a call request only when it returns a valid call SID for the
configured account. Connection, answer and completion are established through
signed provider callbacks and provider status queries. The assistant identifies
itself, requests transcript permission, accepts speech or keypad input, requests
a verbal pilot identity confirmation, and records a respectful preference or
officer review request. The call is limited to 180 seconds and 12 input rounds.
[Speech and keypad collection](https://www.twilio.com/docs/voice/twiml/gather).

The phone pilot discloses **no customer balances, amounts or rates**, even after
an OTP and spoken confirmation. Secure borrower authentication is required before
production financial disclosure. Interest records a review request; it does not
issue a loan, change a rate or send a financial invitation. Human handoff creates
an officer review record; a staffed transfer queue is not implemented.

Opt-out stops the conversation and revokes calling and marketing consent in the
operational database. Hardship stops the earlier proposal. When transcript
permission and the pilot identity gate are present, speaker-labelled borrower
evidence is added to Customer 360 as an actual telephone interaction. Lender
speech is excluded from customer intent extraction. No call audio is recorded by
this integration; the provider's speech recogniser processes speech to text.

Every public provider route verifies `X-Twilio-Signature` against the configured
canonical HTTPS URL and all form fields, then checks account SID and the reserved
call identity. Invalid signatures, oversized bodies, duplicate fields, replay
conflicts and mismatched conversation steps are rejected. Proxy headers cannot
choose the signature-verification origin.
[Provider signature algorithm](https://www.twilio.com/docs/usage/security).

## Crash and timeout recovery

An idempotency key and call reservation commit before provider I/O. Concurrent
requests share the reservation. Transport timeouts, malformed responses and
uncertain provider failures leave `DISPATCH_UNCERTAIN`; the action remains held
and is never automatically redialled with a different key. A signed callback can
bind the provider SID, after which an authenticated operator can reconcile status
or cancel the call. When no SID is known, review the provider logs and reserved
callback URL; do not assume a timeout means that no call was placed. PostgreSQL,
durable workers, alerts and an exercised reconciliation runbook are required for
multiple replicas and enterprise operation.

## Voice and commercial terms

The telephone adapter uses managed Twilio stock speech through `<Say>` with the
basic `woman` voice and `en-US`, and speech collection with `en-IN`. It distributes
no voice model files and performs no cloning. Providers still impose commercial,
speech-processing and calling terms, which must be reviewed for deployment;
there is no blanket claim that every voice or jurisdiction is licence-free.
[Speech voices and applicable terms](https://www.twilio.com/docs/voice/twiml/say).

## Evidence and remaining acceptance

Carrier-specific automated tests use isolated transport doubles to exercise
approval, possession verification, consent, destination restrictions, durable
dispatch, callback signatures, replay handling, transcript gates and real HTTP
request formatting. They are not proof of telephone delivery. Before activation,
verify a genuine permitted-recipient OTP, an answered call with live speech and
DTMF, opt-out propagation, signed callbacks, restart/reconciliation and cost
limits. Record actual provider identifiers and outcomes privately. All commercial
calling remains disabled until that configuration and rehearsal are complete.
