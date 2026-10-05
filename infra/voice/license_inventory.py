"""Read installed voice package metadata; never approves a deployment license.

No network, model loading, shell command, installation, or secret access occurs.
Binary hashes help identify the exact decoder wheel being reviewed. Short
package metadata is not a substitute for linked-library/build/license analysis.
"""

import argparse
import hashlib
import importlib.metadata as metadata
import json
from datetime import datetime, timezone
from pathlib import Path


PACKAGES = (
    "faster-whisper", "ctranslate2", "av", "onnxruntime", "tokenizers",
    "huggingface-hub", "numpy", "transformers", "torch", "torchaudio",
    "sentencepiece", "parler-tts", "descript-audio-codec", "descript-audiotools",
    "speechbrain", "kokoro", "kokoro-onnx", "misaki", "phonemizer-fork", "espeakng-loader",
)


def inventory():
    rows = []
    for name in PACKAGES:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            rows.append({"name": name, "installed": False})
            continue
        meta = distribution.metadata
        files = list(distribution.files or [])
        notices = [str(file) for file in files if any(
            term in file.name.lower() for term in ("license", "copying", "notice", "copyright"))]
        binaries = []
        if name in {"av", "espeakng-loader"}:
            for file in files:
                if file.suffix.lower() not in {".dll", ".so", ".dylib", ".pyd"}:
                    continue
                actual = Path(distribution.locate_file(file))
                if not actual.is_file():
                    continue
                digest = hashlib.sha256()
                with actual.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                binaries.append({"path": str(file), "sha256": digest.hexdigest()})
        rows.append({
            "name": name, "installed": True, "version": distribution.version,
            "declared_license_expression": meta.get("License-Expression"),
            "legacy_license_metadata_excerpt": (meta.get("License") or "")[:240],
            "license_classifiers": [value for value in meta.get_all("Classifier", []) if value.startswith("License ::")],
            "notice_paths": notices, "bundled_binaries": binaries,
            "requires": distribution.requires or [],
            "deployment_review": "pending; metadata does not cover all linked binary licenses",
        })
    return {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "deployment_approved": False,
            "scope": "installed package metadata and selected decoder binary identities; model assets separate",
            "packages": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(inventory(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"Inventory written to {args.output}; deployment review remains pending.")
    else:
        print(report)


if __name__ == "__main__":
    main()
