# Runtime and dependency readiness audit

Reviewed 5 October 2026, IST. The tested local product is usable for synthetic
rehearsals. Production customer deployment remains blocked by the operational,
identity, retention, capacity and voice release gates below. The initial audit did not
reset or modify the interactive database, place calls, download neural TTS
weights, connect to Snowflake, or upgrade application dependencies.

## Verification evidence

The final fresh run passed **175 tests**, with zero failures/errors/skips, in
47.44 seconds after all authorized code, MFA setup and packaging fixes. JUnit is
`output/production-readiness-tests.xml`. One warning
concerns deprecated Starlette TestClient/httpx integration; it did not fail the
suite. Fixtures use isolated temporary databases. Approval/role denial,
duplicate execution/events, expiry/opt-out, changed eligibility, voice gates,
API boundaries, offline cloud tooling and Streamlit AppTests were exercised.
This is functional verification, not a production load or penetration test.

`pip check` reported no broken requirements both before and after installing
the audit tool. Installation added 17 scanner packages and did not upgrade
existing packages. The owner subsequently updated only pip to 26.2.1 and
setuptools to 84.0.0. The repeat advisory scan reports **zero known
vulnerabilities across 101 distributions, with no skips**, and `pip check`
still passes. The authorized recording fix below changed only the voice
service/review tests in this reviewer's scope; other reviewers' cloud/security
changes are included in the final full suite.

The initial `pip-audit 2.10.1` scan queried **101 installed distributions**, with
no skipped packages. Its 20 raw records represent **10 distinct advisories**:
six for pip 24.0 and four for setuptools 65.5.0. No finding was reported for the
other audited runtime packages. The scan covers known Python package advisories;
it does not establish security of application logic, OS components, model
assets, PBX/codecs, linked FFmpeg binaries or unknown vulnerabilities. Raw scan:
`output/production-dependency-audit.before.json`; the post-fix result is
`output/production-dependency-audit.json`. Source findings and isolated
reproductions: `output/production-reliability-audit.json`.

## Concrete release gates

| Area | Observed evidence | Required before production |
| --- | --- | --- |
| Recovery and delivery | `samvaad/voice.py:24` creates session records with no lease, heartbeat, deadline or provider-call ID. `voice.py:85` persists an action as EXECUTING and supports manual session resume. An isolated service reconstruction retained AWAIT_PERMISSION with no end time. `samvaad/service.py:318` rejects live execution. | Durable queue/outbox, bounded worker leases, timeout/handoff, crash recovery and reconciliation of ambiguous carrier origination. Persistence alone is not an automatic recovery worker. |
| Recording and retention | The initial isolated audit found raw borrower text retained after transcript refusal. This local defect is fixed: new `voice_events` store SHA-256 fingerprints with empty text, and borrower turns are retained only after permission is granted. Refusal/opt-out/ambiguous consent and legacy replay regressions pass. | Define operational-trace/transcript retention, purge and verified deletion. Historical raw traces from previous builds still require controlled cleanup; the migration/replay policy below is not a general purge worker. |
| Identity | `samvaad/service.py:137` resolves fixed demo actors. The voice identity prompt explicitly says verbal account-holder confirmation is a synthetic gate. | Trusted operator authentication, customer/tenant scope, a distinct automation principal and approved borrower verification before individualized terms. The selector/demo confirmation cannot become production authentication. |
| Storage and restoration | `service.py:83` opens per-request SQLite connections with WAL, foreign keys and BEGIN IMMEDIATE writes. No scheduled backup, restore rehearsal or purge worker was found in inspected implementation sources. | Transactional operational database, encrypted backups, demonstrated restore with RPO/RTO, controlled schema migrations, retention and protected audit records. Snowflake analytical tables cannot replace these guarantees by declaring keys alone. |
| Voice capacity | `webhook/voice_routes.py:68` limits streamed input to 10 MB and uses the worker threadpool. `samvaad/voice_audio.py:88` limits PCM WAV duration to 60 seconds. SAPI has a 45-second subprocess timeout. ASR has no application deadline/admission controller and there are no application speech quotas. | Bounded inference queue, per-principal/session quotas, ASR timeout/cancellation, overload behavior and measured warm/cold p50/p95 at target concurrency. Existing file limits do not establish inference capacity. |
| Speech quality and financial entities | Local SAPI to Whisper transcribed one synthetic sentence, including its opt-out, exactly in 3.388 seconds. The engine returns text/language without a confidence/handoff contract. | Evaluate consenting recordings, telephone bandwidth, silence/noise, English/Hindi accents, important amounts/dates/rates and opt-outs. Low confidence or unsupported language must yield review/handoff. A single smoke check is not a language or latency benchmark. |
| Voice assets and telephony | `voice_audio.py:31` reports production_ready=false. `infra/voice/model-manifest.json` disables production loading. No carrier-connected worker is active. | Review pinned Parler Mini v1 stock voice, T5 tokenizer/encoder, DAC weights and full runtime; compile binary SBOM/notices. Complete PBX/media lab, carrier/number onboarding and approved calling/recording purpose before any real call. |
| Readiness and operations | `webhook/main.py:179` provides a local health response, without probing database or inference dependencies. No production SLO, load result or speech-inference budget enforcement was found. | Distinguish liveness/readiness, monitor queue/leases/ASR/TTS/storage, redact logs, define budgets/alerts and test operational runbooks. |

The tested approval service remains the decision authority: conditional offers
come from approved actions, not a language-model assertion. API tests reject
unauthenticated writes and wrong approvers; service tests prevent bypass,
duplicate business effects and expired/revoked capability use. Public offer
responses are atomic and token-scoped (`service.py:463`). These controls must be
preserved behind real identity and transactional cloud storage.

The full voice component and transitive license decisions are documented in
[voice-license-review.md](voice-license-review.md) and the staged delivery path
in [telecalling-plan.md](telecalling-plan.md). Local installed Windows voices
are a host demonstration feature, with no blanket voice-binary redistribution
approval. No package-license scan approves a model or speaker asset.

## Recording defect remediation and legacy policy

The authorized fix adds `payload_hash` to existing local event tables
idempotently (`samvaad/voice.py:43`). Its schema check/ALTER reacquires the SQLite
writer lock after executescript so competing constructors cannot add the same
column concurrently. New events bind the event ID to the
SHA-256 of the normalized payload; they store no raw event text. Refusal,
pre-permission opt-out and ambiguous responses create no raw borrower turn.
The affirmative permission utterance is stored only after the permission flag
is set within the same transaction. Later permitted speech remains
available for the bounded hardship/identity/outcome workflow.

Unconsented hardship speech immediately stops the proposed financial dialogue
and records an officer-review callback, without storing the utterance or
creating an offer. Explicit opt-out retains higher priority. A permitted
utterance that mentions hardship still reaches the existing review gate before
financial terms/acceptance. The controller therefore preserves the safety
signal without making raw recording a prerequisite for stopping contact.

An exact replay of a historical raw event remains compatible: the service
checks its digest, then clears that event's raw payload and saves its hash.
A conflicting payload still fails. Existing old borrower turns and untouched
legacy raw events are not silently deleted by this schema change. Before any
real-data deployment, perform an approved migration/deletion review. The demo
owner can reset synthetic fixtures after the rehearsal to remove old traces;
this reviewer did not reset the interactive database.

The final **175-test gate passes**, including **12 Streamlit AppTests** with
the recording fix. Six new
consent/legacy/hardship/migration cases were added. This resolves the current persistence
defect but does not establish a production recording or retention policy.
Hashes of short utterances can be guessable; they are deduplication
fingerprints, not an anonymization guarantee.

## Packaging advisory review

The initial findings concern installation/build behavior. Their presence does
not prove that a remote app request reaches the vulnerable code. The observed
runtime is Python 3.11.9; the pip fallback-tar issue depends on absence of PEP
706 support, so its described condition is mitigated by this Python version.
Other wheel/entry-point/index issues still justify patching the toolchain.

| Component | Distinct initial advisory IDs | Owner's targeted patch |
| --- | --- | --- |
| pip 24.0 | CVE-2025-8869; CVE-2026-1703, 3219, 6357, 8643, 13346 | pip 26.2.1 |
| setuptools 65.5.0 | CVE-2022-40897, CVE-2024-6345, CVE-2025-47273, CVE-2026-59890 | setuptools 84.0.0 |

Primary release evidence records the pip 26.2 URL-decoding security fix and the
setuptools Unicode-normalization exclusion fix. The maintainer's PackageIndex
advisory describes the earlier arbitrary-write risk. These are targeted build
tool changes; no broad runtime upgrade is required by the scan.
[pip changelog](https://pip.pypa.io/en/stable/news/),
[setuptools changelog](https://setuptools.pypa.io/en/latest/history.html),
[maintainer PackageIndex advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf),
[PyPA entry-point advisory announcement](https://mail.python.org/archives/list/security-announce@python.org/thread/YV63UET5D3OOJY7O4M5XCVYO2YM4NBYJ/).

## Scope of the next deployment

A controlled cloud sandbox with synthetic data can exercise the prepared
analytical load/Cortex assets once the owner has account configuration,
warehouse/privileges and a credit budget. It must keep demo identity and live
delivery clearly labeled and restricted. An externally accessible production
staff/customer application requires the unresolved gates above; real calls
require the additional voice/carrier gates. Passing local tests or moving
data to Snowflake does not satisfy those gates automatically.
