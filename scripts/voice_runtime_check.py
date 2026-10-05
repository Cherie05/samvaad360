"""Check actual localhost voice/audio endpoints using synthetic Ravi data only."""
import argparse
import io
import json
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True, choices=["TEST-LOCAL-DEMO"])
    parser.parse_args()
    tokens = json.loads((ROOT / ".local/api-tokens.json").read_text(encoding="utf-8"))
    runner = next(token for token, user in tokens.items() if user == "local-runner")
    headers = {"Authorization": "Bearer " + runner}

    def request(route, body=None, audio=None):
        req_headers = dict(headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if audio is not None:
            data = audio
            req_headers["Content-Type"] = "audio/wav"
        with urlopen(Request(BASE + route, data=data, headers=req_headers), timeout=90) as response:
            content = response.read()
            return content if response.headers.get_content_type() == "audio/wav" else json.loads(content)

    status = request("/api/voice/status")
    assert status["tts_ready"] and status["asr_ready"] and not status["production_ready"] and not status["pstn_enabled"]
    phrase = "Hello. This is a local voice test. Please do not call me again."
    started = time.perf_counter()
    audio = request("/api/voice/speech", {"text": phrase})
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.getnframes() > 0
        duration = wav.getnframes() / wav.getframerate()
    recognized = request("/api/voice/transcribe", audio=audio)
    elapsed = round(time.perf_counter() - started, 3)
    normalize = lambda value: " ".join(value.lower().replace(".", "").split())
    assert normalize(recognized["text"]) == normalize(phrase), recognized["text"]

    action = next(a for a in request("/api/actions") if a["customer_id"] == "C0001" and a["status"] == "APPROVED")
    session = request("/api/voice/sessions", {"action_id": action["action_id"]})
    assert session["state"] == "AWAIT_PERMISSION"
    route = "/api/voice/sessions/" + session["session_id"] + "/turn"
    session = request(route, {"text": "Yes, you may continue", "event_id": "runtime-permission-01"})
    assert session["state"] == "AWAIT_IDENTITY"
    session = request(route, {"text": "Yes, I am the account holder", "event_id": "runtime-identity-01"})
    assert session["state"] == "ACTIVE"
    body = {"text": "Please arrange an officer callback", "event_id": "runtime-callback-01"}
    session = request(route, body)
    assert session["state"] == "ENDED" and session["outcome"] == "CALLBACK"
    assert request(route, body) == session
    assert not request("/api/offers?customer_id=C0001")
    checks = [
        "Authenticated local voice status; TTS and ASR ready; PSTN and production disabled",
        "Actual SAPI speech endpoint returned a nonempty PCM WAV",
        "Actual CPU Whisper API recognized the synthetic phrase exactly after normalization",
        "Ravi session passed permission and demo identity gates and persisted an officer callback",
        "Exact turn replay returned the same session; hardship created no financial invitation",
    ]
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "passed": len(checks),
              "checks": checks, "speech_and_asr_seconds": elapsed, "wav_duration_seconds": round(duration, 3),
              "recognized_text": recognized["text"], "synthetic_only": True, "real_calls_placed": False,
              "latency_scope": "One local synthetic WAV round trip; not a production telephone benchmark"}
    path = ROOT / "output/local-voice-runtime-check.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
