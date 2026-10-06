"""Staff-authenticated provider operations and signature-validated Twilio callbacks."""
from urllib.parse import parse_qs
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from samvaad.telephony import TelephonyService, validate_signature


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecipientBody(Body):
    customer_id: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=9, max_length=16)
    source: Literal["primary", "alternate"]
    consent_note: str = Field(min_length=10, max_length=500)
    verification_requested: Literal[True]


class VerifyBody(Body):
    code: str = Field(min_length=4, max_length=10, pattern=r"^[0-9]+$")


class CallBody(Body):
    action_id: str = Field(min_length=1, max_length=100)
    recipient_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    acknowledged_live_call: Literal[True]


def build_telephony_router(service, actor_dependency, telephony=None):
    telephony = telephony or TelephonyService(service)
    router = APIRouter(tags=["real carrier controlled pilot"])

    @router.get("/api/telephony/status")
    def status(current=Depends(actor_dependency)):
        telephony._staff(current)
        return telephony.status()

    @router.get("/api/telephony/recipients")
    def recipients(customer_id: str, current=Depends(actor_dependency)):
        return telephony.recipients(customer_id, current)

    @router.post("/api/telephony/recipients")
    def recipient(body: RecipientBody, current=Depends(actor_dependency)):
        return telephony.request_verification(**body.model_dump(), actor=current)

    @router.post("/api/telephony/recipients/{recipient_id}/verify")
    def verify(recipient_id: str, body: VerifyBody, current=Depends(actor_dependency)):
        return telephony.verify(recipient_id, body.code, current)

    @router.get("/api/telephony/calls")
    def calls(current=Depends(actor_dependency)):
        return telephony.calls(current)

    @router.post("/api/telephony/calls")
    def start(body: CallBody, current=Depends(actor_dependency)):
        return telephony.start(**body.model_dump(), actor=current)

    @router.get("/api/telephony/calls/{call_id}")
    def call(call_id: str, current=Depends(actor_dependency)):
        return telephony.get(call_id, current)

    @router.post("/api/telephony/calls/{call_id}/cancel")
    def cancel(call_id: str, current=Depends(actor_dependency)):
        return telephony.cancel(call_id, current)

    @router.post("/api/telephony/calls/{call_id}/reconcile")
    def reconcile(call_id: str, current=Depends(actor_dependency)):
        return telephony.reconcile(call_id, current)

    async def callback(request, call_id):
        telephony.settings.require()
        if request.headers.get("content-type", "").split(";")[0].lower() != "application/x-www-form-urlencoded":
            raise HTTPException(415, "Use the provider form callback.")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 16384:
                raise HTTPException(413, "Callback body is too large.")
            raw.extend(chunk)
        try:
            items = parse_qs(raw.decode("utf-8"), strict_parsing=True, keep_blank_values=True, max_num_fields=64)
            if any(len(v) != 1 for v in items.values()):
                raise ValueError()
            values = {key: value[0] for key, value in items.items()}
        except (UnicodeError, ValueError):
            raise HTTPException(422, "Invalid provider callback.") from None
        query = request.url.query
        canonical = telephony.settings.public_url + request.url.path + ("?" + query if query else "")
        if not validate_signature(telephony.settings.auth_token, canonical, values, request.headers.get("X-Twilio-Signature")):
            raise HTTPException(403, "Invalid provider signature.")
        await run_in_threadpool(telephony.callback_identity, call_id, values)
        return values

    @router.post("/telephony/twilio/{call_id}/answer")
    async def answer(call_id: str, request: Request):
        values = await callback(request, call_id)
        return Response(await run_in_threadpool(telephony.conversation, call_id, values), media_type="application/xml")

    @router.post("/telephony/twilio/{call_id}/turn")
    async def turn(call_id: str, request: Request, step: int):
        if not 0 <= step <= 12:
            raise HTTPException(422, "Invalid conversation step.")
        values = await callback(request, call_id)
        return Response(await run_in_threadpool(telephony.conversation, call_id, values, step), media_type="application/xml")

    @router.post("/telephony/twilio/{call_id}/status")
    async def provider_status(call_id: str, request: Request):
        values = await callback(request, call_id)
        await run_in_threadpool(telephony.provider_status, call_id, values)
        return Response(status_code=204)

    router.telephony_service = telephony
    return router
