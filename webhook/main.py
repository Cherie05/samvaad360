"""FastAPI boundaries for the local Samvaad demo.

Writes authenticate to configured tokens mapped to fixed service identities.
Offer links are deliberately scoped capabilities for synthetic, expiring offers.
Telephone transport is a separate, disabled-by-default controlled pilot.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from samvaad.factory import create_service

WORKSPACE = Path(__file__).resolve().parents[1]
ALLOWED_USERS = frozenset({"arjun", "kavya", "meera", "farah", "local-runner", "demo-admin"})
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


class WriteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalBody(WriteBody):
    decision: Literal["APPROVE", "REJECT"] = "APPROVE"
    note: str = Field(default="", max_length=1000)


class ExecutionBody(WriteBody):
    mode: Literal["simulate"] = "simulate"
    outcome: Literal["ACCEPT", "DECLINE", "CALLBACK", "OPT_OUT", "NO_ANSWER", "ALREADY_PAID", "FAILED"] = "ACCEPT"


class ResponseBody(WriteBody):
    outcome: Literal["ACCEPT", "DECLINE", "CALLBACK", "OPT_OUT", "NO_ANSWER", "ALREADY_PAID", "FAILED"]
    event_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class QuestionBody(WriteBody):
    question: str = Field(min_length=1, max_length=2000)
    customer_id: str | None = Field(default=None, max_length=100)


class InteractionBody(WriteBody):
    text: str = Field(min_length=1, max_length=20000)
    channel: Literal["CHAT", "EMAIL", "CALL_IN", "COMPLAINT"] = "CHAT"


def load_token_map() -> dict[str, str]:
    raw = os.getenv("SAMVAAD_API_TOKENS_JSON")
    token_file = Path(os.getenv("SAMVAAD_API_TOKEN_FILE", str(WORKSPACE / ".local" / "api-tokens.json")))
    try:
        mapping = json.loads(raw) if raw else json.loads(token_file.read_text(encoding="utf-8")) if token_file.exists() else {}
    except (OSError, ValueError) as exc:
        raise RuntimeError("API token configuration is invalid; configure token-to-user JSON.") from exc
    if not isinstance(mapping, dict):
        raise RuntimeError("API token configuration must map token strings to fixed user IDs.")
    if any(not isinstance(token, str) or not token.isascii() or not 24 <= len(token) <= 512 or not isinstance(user, str) or user not in ALLOWED_USERS for token, user in mapping.items()):
        raise RuntimeError("API tokens must have at least 24 characters and map to known local identities.")
    return mapping


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _expires(offer: dict) -> bool:
    value = offer.get("expires_at")
    if not value:
        return True
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def _offer_page(offer: dict, token: str, *, message: str = "") -> str:
    terms = offer.get("offer") or offer.get("terms") or {}
    if isinstance(terms, str):
        terms_html = f"<p>{_escape(terms)}</p>"
    elif isinstance(terms, dict):
        terms_html = "<dl>" + "".join(f"<dt>{_escape(str(key).replace('_', ' ').title())}</dt><dd>{_escape(value)}</dd>" for key, value in terms.items()) + "</dl>"
    else:
        terms_html = f"<p>{_escape(terms)}</p>"
    customer = offer.get("customer_name") or "Demo customer"
    event_id = "offer:" + secrets.token_hex(16)
    form = "" if message else f"""<form method="post" action="/offer/{_escape(token)}/respond">
      <input type="hidden" name="event_id" value="{event_id}">
      <button type="submit" name="outcome" value="ACCEPT">I'm interested</button>
      <button class="secondary" type="submit" name="outcome" value="DECLINE">Decline invitation</button>
      <button class="secondary" type="submit" name="outcome" value="CALLBACK">Request a callback</button>
      <button class="secondary" type="submit" name="outcome" value="OPT_OUT">Stop demo contact</button>
    </form>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Samvaad 360 · Demo invitation</title><style>
    *{{box-sizing:border-box}} body{{margin:0;background:#f5f3fb;color:#211b38;font:16px system-ui,sans-serif;padding:40px 20px}}
    main{{max-width:660px;margin:0 auto;background:white;border:1px solid #e3dfee;border-radius:22px;padding:32px;box-shadow:0 12px 40px #24104310}}
    .brand{{color:#6d45cc;font-weight:750;font-size:20px}} .tag{{display:inline-block;margin-top:20px;padding:6px 11px;border-radius:20px;background:#f1eaff;color:#6744ad;font-size:12px}}
    h1{{font-size:30px;line-height:1.2}} p{{line-height:1.65}} dl{{background:#faf8fe;padding:20px;border-radius:12px}}dt{{font-size:12px;color:#716782;margin-top:12px}}dd{{margin:4px 0;font-weight:600}}
    form{{display:flex;gap:10px;flex-wrap:wrap;margin-top:25px}} button{{border:0;border-radius:10px;padding:13px 18px;background:#6d45cc;color:white;font:inherit;font-weight:600;cursor:pointer}}
    button.secondary{{background:#ede8f6;color:#4e3b73}} .note{{font-size:13px;color:#756c83}} .message{{padding:16px;background:#edf8f0;border-radius:12px}}
    </style></head><body><main><div class="brand">Samvaad 360</div><span class="tag">LOCAL DEMO · SYNTHETIC CUSTOMER</span>
    <h1>Your conditional invitation</h1><p>Hello {_escape(customer)}. These are synthetic demonstration terms. Expressing interest does not create a loan, change a rate, or guarantee credit approval.</p>
    {terms_html}<p class="note">Invitation expires: {_escape(offer.get('expires_at'))}</p>
    {f'<p class="message">{_escape(message)}</p>' if message else ''}{form}
    <p class="note">No email, SMS, payment, or real underwriting decision is generated. Final eligibility would require verification and separate approval.</p>
    </main></body></html>"""


def create_app(service=None, token_map: dict[str, str] | None = None, telephony=None) -> FastAPI:
    service = service or create_service()
    tokens = load_token_map() if token_map is None else token_map
    app = FastAPI(title="Samvaad 360 Local API", version="0.1.0")
    app.state.service = service
    allowed_origins = [origin.strip() for origin in os.getenv("SAMVAAD_CORS_ORIGINS", "").split(",") if origin.strip()]
    if allowed_origins:
        permitted = {"http://localhost:8501", "http://127.0.0.1:8501"}
        if not set(allowed_origins).issubset(permitted):
            raise RuntimeError("Local CORS origins must be localhost:8501 or 127.0.0.1:8501.")
        app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"], allow_credentials=False)

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(Exception)
    async def handle_error(request: Request, exc: Exception):
        code = getattr(exc, "code", None)
        if code:
            normalized = str(code).upper()
            codes = {"NOT_FOUND": 404, "FORBIDDEN": 403, "UNAUTHORIZED": 403, "UNKNOWN_ACTOR": 403, "EXPIRED": 410, "OFFER_REVOKED": 410, "LIVE_NOT_CONFIGURED": 503}
            status = 404 if normalized.endswith("_NOT_FOUND") else 410 if normalized.endswith("_EXPIRED") else 503 if normalized.endswith("_NOT_CONFIGURED") else codes.get(normalized, 409)
            return JSONResponse(status_code=status, content={"error": str(code), "message": str(exc)})
        # Never expose exception internals, secrets, or customer payloads in HTTP errors.
        logger.error("Unexpected local API error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"error": "INTERNAL_ERROR", "message": "The local request failed. See the local server log."})

    def actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not credentials or credentials.scheme.lower() != "bearer" or not credentials.credentials.isascii() or len(credentials.credentials) > 512:
            raise HTTPException(401, "A configured bearer token is required.", headers={"WWW-Authenticate": "Bearer"})
        identity = None
        for candidate, user in tokens.items():
            if isinstance(candidate, str) and candidate.isascii() and hmac.compare_digest(candidate, credentials.credentials):
                identity = user
                break
        if identity not in ALLOWED_USERS:
            raise HTTPException(401, "Invalid API token.", headers={"WWW-Authenticate": "Bearer"})
        return service.resolve_actor(identity)

    from webhook.voice_routes import build_voice_router
    app.include_router(build_voice_router(service, actor))
    from samvaad.telephony import TelephonyService
    from webhook.telephony_routes import build_telephony_router
    telephone = telephony or TelephonyService(service)
    app.state.telephony = telephone
    app.include_router(build_telephony_router(service, actor, telephone))

    @app.get("/health")
    def health():
        enabled = telephone.status()["pilot_ready"]
        return {"status": "ok", "mode": "controlled-telephone-pilot" if enabled else "local-synthetic",
                "external_delivery": enabled, "telephony": "carrier-configured" if enabled else "disabled",
                "operator_auth_configured": bool(tokens), "production_ready": False}

    @app.get("/api/me")
    def whoami(current=Depends(actor)):
        return {"user_id": current.user_id, "role": current.role}

    @app.get("/api/customers")
    def customers(search: str = "", current=Depends(actor)):
        return service.list_customers(search=search)

    @app.get("/api/portfolio")
    def portfolio(current=Depends(actor)):
        return service.portfolio()

    @app.get("/api/customers/{customer_id}")
    def customer360(customer_id: str, current=Depends(actor)):
        return service.customer360(customer_id)

    @app.post("/api/customers/{customer_id}/recommend")
    def recommend(customer_id: str, current=Depends(actor)):
        return service.recommend(customer_id, current)

    @app.post("/api/customers/{customer_id}/opt-out")
    def opt_out(customer_id: str, current=Depends(actor)):
        return service.revoke_consent(customer_id, current)

    @app.post("/api/customers/{customer_id}/interactions")
    def interaction(customer_id: str, body: InteractionBody, current=Depends(actor)):
        return service.add_interaction(customer_id, body.text, channel=body.channel, actor=current)

    @app.get("/api/actions")
    def actions(status: str | None = None, current=Depends(actor)):
        return service.actions(status=status)

    @app.post("/api/actions/{action_id}/approve")
    def approve(action_id: str, body: ApprovalBody, current=Depends(actor)):
        return service.approve_action(action_id, current, decision=body.decision, note=body.note)

    @app.post("/api/actions/{action_id}/execute")
    def execute(action_id: str, body: ExecutionBody, current=Depends(actor)):
        return service.execute_action(action_id, current, mode=body.mode, outcome=body.outcome)

    @app.post("/api/actions/{action_id}/response")
    def response(action_id: str, body: ResponseBody, current=Depends(actor)):
        return service.record_response(action_id, body.outcome, body.event_id, current)

    @app.get("/api/audit")
    def audit(customer_id: str | None = None, action_id: str | None = None, current=Depends(actor)):
        return service.audit(customer_id=customer_id, action_id=action_id)

    @app.get("/api/offers")
    def offers(customer_id: str | None = None, current=Depends(actor)):
        return service.offers(customer_id=customer_id)

    @app.post("/api/ask")
    def ask(body: QuestionBody, current=Depends(actor)):
        return service.ask(body.question, customer_id=body.customer_id, actor=current)

    def scoped_offer(token: str):
        if len(token) > 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise HTTPException(404, "Invitation not found.")
        offer = service.get_offer(token)
        if not isinstance(offer, dict) or not offer.get("action_id"):
            raise HTTPException(404, "Invitation not found.")
        if _expires(offer):
            raise HTTPException(410, "This demo invitation has expired.")
        return offer

    @app.get("/offer/{token}", response_class=HTMLResponse)
    def offer_page(token: str):
        return HTMLResponse(_offer_page(scoped_offer(token), token))

    @app.post("/offer/{token}/respond", response_class=HTMLResponse)
    async def offer_response(token: str, request: Request):
        if len(token) > 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise HTTPException(404, "Invitation not found.")
        content_type = request.headers.get("content-type", "").split(";")[0].lower()
        if content_type != "application/x-www-form-urlencoded":
            raise HTTPException(415, "Use the invitation response form.")
        data = bytearray()
        async for chunk in request.stream():
            # Enforce the limit before copying a chunk. request.body() would
            # buffer the entire unauthenticated upload before checking it.
            if len(data) + len(chunk) > 2048:
                raise HTTPException(413, "Response form is too large.")
            data.extend(chunk)
        try:
            values = parse_qs(data.decode("utf-8"), strict_parsing=True, max_num_fields=4)
        except (UnicodeError, ValueError):
            raise HTTPException(422, "Invalid invitation response.")
        if set(values) != {"outcome", "event_id"} or any(len(value) != 1 for value in values.values()):
            raise HTTPException(422, "Invalid invitation response.")
        outcome, event_id = values["outcome"][0], values["event_id"][0]
        if outcome not in {"ACCEPT", "DECLINE", "CALLBACK", "OPT_OUT"} or not re.fullmatch(r"offer:[0-9a-f]{32}", event_id):
            raise HTTPException(422, "Invalid invitation response.")
        # Bind client retry IDs to this capability so they cannot collide across offers.
        scoped_id = "public:" + hashlib.sha256((token + ":" + event_id).encode()).hexdigest()[:48]
        result = service.respond_to_offer(token, outcome, scoped_id)
        offer = result["offer"]
        messages = {
            "ACCEPT": "Your demo interest has been recorded. No real loan or rate change was created.",
            "DECLINE": "Your demo invitation has been declined.",
            "CALLBACK": "Your callback request has been recorded in the local demo. No real call will be placed.",
            "OPT_OUT": "Your demo contact consent has been revoked. Future demo contact is blocked.",
        }
        message = messages[outcome]
        return HTMLResponse(_offer_page(offer, token, message=message))

    return app
