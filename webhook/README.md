# Local integration API

Run the project with `python scripts/run_local.py`; the supervisor creates random development tokens in `.local/api-tokens.json`. This untracked file maps each token to a fixed demo user, and must stay private. API endpoints accept `Authorization: Bearer <token>`. Alternatively set `SAMVAAD_API_TOKENS_JSON` to a JSON object mapping tokens of at least 24 characters to one of `meera`, `farah`, `arjun`, `kavya`, `local-runner`, or `demo-admin`. No role is accepted from a request. Without configuration, operator endpoints reject all requests.

The identities intentionally simulate users on one developer machine; possession of all local development tokens is equivalent to local developer access. This is not production authentication. Real deployment requires Snowflake identity, separate operator sessions, and a separately provisioned automation principal.

`GET /health` is public. `/api/customers`, `/api/portfolio`, `/api/actions`, `/api/audit`, `/api/offers`, and `/api/me` require authentication. Writes use customer/action-specific recommendation, approval, execution, response, and opt-out routes. Analyst/admin identities can add a bounded conversation through `POST /api/customers/{customer_id}/interactions` with `text` and `channel` (`CHAT`, `EMAIL`, `CALL_IN`, or `COMPLAINT`). `POST /api/ask` accepts a question and optional customer ID. Execution is restricted to `mode=simulate`; provider delivery is disabled.

`GET /offer/{token}` displays a synthetic conditional invitation. The token grants only access to that invitation. `POST /offer/{token}/respond` atomically validates the invitation and records interest, decline, a callback request, or explicit contact opt-out with a deduplicated event; it cannot approve, execute, or change offer terms. An exact opt-out event replay succeeds without more audit events even after consent is revoked. Expired tokens always return HTTP 410, including replays. New responses to revoked offers return HTTP 410. Pages escape all dynamic values and use `no-store` and `no-referrer` headers.

For a standalone API process, use `python -m uvicorn webhook.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log`. This keeps invitation bearer paths out of raw HTTP access logs. The factory also accepts a service and token map for isolated API tests, and importing the module does not create a database.

Carrier voice callbacks and outbound email/SMS are disabled. No external account or credentials are needed for the local demonstration. Live callbacks require provider signature verification, public HTTPS deployment, consent enforcement, and separate integration checks before enabling them.

## Local voice API

Authenticated `/api/voice/status`, `/sessions` and `/sessions/{id}` report the local lab and persisted sessions. Only the fixed `local-runner` identity can start sessions or submit/end turns. `POST /api/voice/sessions` requires an approved `action_id`; `/{id}/turn` requires bounded `text` and a unique `event_id`. The domain service rechecks consent, current eligibility and approved terms. These routes do not dial a number or accept caller-supplied roles.

`POST /api/voice/speech` accepts a JSON object with `text` and returns an actual WAV using the installed Windows voice. `POST /api/voice/transcribe` accepts raw `audio/wav` bytes (PCM, up to 60 seconds / 10 MB) and returns locally recognized text. Recognition uses the explicitly provisioned model and never implicitly downloads one. The frontend requires reviewing and submitting recognized text separately. Audio processing does not execute an action. Production TTS and carrier endpoints are not configured.
