"""Local speech adapters. Audio never goes to a hosted recognition API.

Windows SAPI uses installed OS voices for the local lab. Optional Whisper
recognition loads a local model directory and refuses implicit downloads.
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import wave
from functools import lru_cache
from pathlib import Path

from samvaad.models import ActionError

ROOT = Path(__file__).resolve().parents[1]


def status():
    model = Path(os.environ.get("SAMVAAD_ASR_MODEL_PATH", str(ROOT / ".local/models/whisper-base")))
    try:
        import importlib.util
        asr_package = importlib.util.find_spec("faster_whisper") is not None
    except ImportError:
        asr_package = False
    tts = os.name == "nt" and shutil.which("powershell") is not None
    return {"tts_ready": tts, "tts_provider": "Windows installed SAPI voice (local lab only)",
            "asr_ready": asr_package and all((model / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")),
            "asr_provider": "Local faster-whisper / MIT model", "production_ready": False}


def synthesize(text, voice_name=None):
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ActionError("INVALID_SPEECH", "Speech text must contain 1-4,000 characters.")
    if not status()["tts_ready"]:
        raise ActionError("TTS_NOT_CONFIGURED", "The local SAPI voice needs Windows. Configure a reviewed production TTS adapter on other systems.")
    # Pass text via a private JSON file, never interpolate it into shell code.
    directory = ROOT / ".local/audio-tmp"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sapi-", dir=directory) as temp:
        work = Path(temp).resolve()
        if directory.resolve() not in work.parents:
            raise ActionError("INVALID_AUDIO_PATH", "The temporary audio path escaped the workspace.")
        config = work / "request.json"
        script = work / "speak.ps1"
        output = work / "speech.wav"
        config.write_text(json.dumps({"text": text, "voice": voice_name or "", "output": str(output)}, ensure_ascii=False), encoding="utf-8")
        script.write_text("""param([string]$RequestFile)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$samvaadRequest = Get-Content -LiteralPath $RequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$samvaadSynth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  if ($samvaadRequest.voice) { $samvaadSynth.SelectVoice($samvaadRequest.voice) }
  $samvaadSynth.SetOutputToWaveFile($samvaadRequest.output)
  $samvaadSynth.Speak($samvaadRequest.text)
} finally { $samvaadSynth.Dispose() }
""", encoding="utf-8")
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-File", str(script), str(config)], capture_output=True, timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ActionError("TTS_FAILED", "Local speech generation failed or timed out.") from exc
        if result.returncode or not output.exists():
            raise ActionError("TTS_FAILED", "Local speech generation failed. Check the installed voice configuration.")
        audio = output.read_bytes()
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if wav.getnframes() <= 0:
                raise ActionError("TTS_FAILED", "The speech engine returned empty audio.")
        return {"audio": audio, "mime_type": "audio/wav", "provider": "Windows SAPI (installed OS voice)", "voice": voice_name or "System default"}


@lru_cache(maxsize=2)
def _asr_model(model_path):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ActionError("ASR_NOT_CONFIGURED", "Install requirements-voice.txt and provision the reviewed Whisper model first.") from exc
    if not Path(model_path).is_dir() or not (Path(model_path) / "model.bin").is_file():
        raise ActionError("ASR_NOT_CONFIGURED", "Provision the local Whisper model. Runtime transcription never downloads a model implicitly.")
    try:
        return WhisperModel(model_path, device="cpu", compute_type="int8", local_files_only=True)
    except Exception as exc:
        raise ActionError("ASR_NOT_CONFIGURED", "The local recognizer model is incomplete or incompatible. Re-run explicit model provisioning.") from exc


def transcribe(audio):
    if not isinstance(audio, bytes) or not audio or len(audio) > 10_000_000:
        raise ActionError("INVALID_AUDIO", "Provide a PCM WAV recording of at most 10 MB and 60 seconds.")
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if wav.getnchannels() not in {1, 2} or wav.getsampwidth() not in {1, 2, 3, 4} or wav.getframerate() not in {8000, 16000, 22050, 24000, 44100, 48000} or wav.getnframes() / wav.getframerate() > 60:
                raise ActionError("INVALID_AUDIO", "Use a mono/stereo PCM WAV of at most 60 seconds.")
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise ActionError("INVALID_AUDIO", "The recording is not a valid PCM WAV.") from exc
    model_path = os.environ.get("SAMVAAD_ASR_MODEL_PATH", str(ROOT / ".local/models/whisper-base"))
    model = _asr_model(str(Path(model_path).resolve()))
    try:
        segments, info = model.transcribe(io.BytesIO(audio), beam_size=1, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as exc:
        raise ActionError("ASR_FAILED", "Local speech recognition failed. Use a typed turn or review the model setup.") from exc
    return {"text": text, "language": info.language, "provider": "Local faster-whisper (CPU int8)"}
