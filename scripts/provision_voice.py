"""Explicit one-time provisioning of a permissively licensed local ASR model."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_REPO = "Systran/faster-whisper-base"
MODEL_REVISION = "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly download the reviewed MIT model (approximately 145 MB)")
    args = parser.parse_args()
    destination = ROOT / ".local/models/whisper-base"
    if not args.download:
        print(json.dumps({"model": MODEL_REPO, "revision": MODEL_REVISION, "license": "MIT", "download": False, "ready": (destination / "model.bin").is_file()}))
        return 0
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        parser.error("Install requirements-voice.txt first.")
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=MODEL_REPO, revision=MODEL_REVISION, local_dir=destination, allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "vocabulary.json", "preprocessor_config.json", "README.md"])
    # Preserve the actual license notice alongside downloaded model artifacts.
    import urllib.request
    license_url = "https://raw.githubusercontent.com/openai/whisper/main/LICENSE"
    with urllib.request.urlopen(license_url, timeout=30) as response:
        (destination / "LICENSE").write_bytes(response.read())
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.iterdir() if path.is_file() and path.name != "samvaad-model-manifest.json"}
    (destination / "samvaad-model-manifest.json").write_text(json.dumps({"repository": MODEL_REPO, "revision": MODEL_REVISION, "license": "MIT", "source": "https://huggingface.co/" + MODEL_REPO + "/tree/" + MODEL_REVISION, "sha256": hashes}, indent=2), encoding="utf-8")
    print(json.dumps({"ready": (destination / "model.bin").is_file(), "repository": MODEL_REPO, "license": "MIT", "location": str(destination)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
