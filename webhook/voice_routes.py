"""Authenticated API for the local voice lab; no carrier endpoint or dialer."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from samvaad.voice import VoiceService
from samvaad import voice_audio


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartBody(Body):
    action_id: str = Field(min_length=1, max_length=100)


class TurnBody(Body):
    text: str = Field(min_length=1, max_length=4000)
    event_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")


class EndBody(Body):
    outcome: Literal["CALLBACK", "NO_ANSWER", "OPT_OUT"] = "CALLBACK"


class SpeechBody(Body):
    text: str = Field(min_length=1, max_length=4000)


def build_voice_router(service, actor_dependency):
    voice = VoiceService(service)
    router = APIRouter(prefix="/api/voice", tags=["local voice lab"])

    @router.get("/status")
    def status(current=Depends(actor_dependency)):
        return {**voice_audio.status(), "mode": "LOCAL_VOICE_LAB", "pstn_enabled": False}

    @router.get("/sessions")
    def sessions(customer_id: str | None = None, current=Depends(actor_dependency)):
        return voice.sessions(customer_id)

    @router.get("/sessions/{session_id}")
    def session(session_id: str, current=Depends(actor_dependency)):
        return voice.get(session_id)

    @router.post("/sessions")
    def start(body: StartBody, current=Depends(actor_dependency)):
        return voice.start(body.action_id, current)

    @router.post("/sessions/{session_id}/turn")
    def turn(session_id: str, body: TurnBody, current=Depends(actor_dependency)):
        return voice.turn(session_id, body.text, body.event_id, current)

    @router.post("/sessions/{session_id}/end")
    def end(session_id: str, body: EndBody, current=Depends(actor_dependency)):
        return voice.end(session_id, current, body.outcome)

    @router.post("/speech")
    def speech(body: SpeechBody, current=Depends(actor_dependency)):
        result = voice_audio.synthesize(body.text)
        return Response(result["audio"], media_type="audio/wav")

    @router.post("/transcribe")
    async def transcribe(request: Request, current=Depends(actor_dependency)):
        if request.headers.get("content-type", "").split(";")[0].lower() not in {"audio/wav", "audio/x-wav"}:
            raise HTTPException(415, "Send PCM WAV audio.")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 10_000_000:
                raise HTTPException(413, "Use a WAV recording of at most 10 MB.")
        return await run_in_threadpool(voice_audio.transcribe, bytes(data))

    return router
