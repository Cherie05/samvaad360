# Voice deployment scaffold

These files record the proposed production voice boundary. They do not start a
PBX, download models, dial numbers, or change the local application's provider.

The provisional production evaluation candidate is Parler Mini v1 with a
stock voice and T5 tokenizer, and faster-whisper using a reviewed Whisper checkpoint. SpeechT5
is an alternative only with a cleared speaker asset. Asterisk
is a separate ARI-controlled process; its GPL obligations and module licenses
remain part of the deployed image review.

Mini v1.1 is disabled until the terms of its Llama-2-derived tokenizer assets
are resolved. Review the selected v1 tokenizer/text encoder, DAC codec weights,
implementation and resolved runtime dependencies as separate inventory entries.

Before using a model, fill its exact revision, SHA-256, saved license/notice
paths, and review state in `model-manifest.json`. No entry here is approved for
automatic production loading. Review external speaker recordings/vectors
independently. Do not use a repository's source license as a substitute for a
model/voice asset's license.

`deployment.env.example` is a lab planning template, not configuration consumed
by the current app. Keep carrier use disabled until the carrier and calling
policy gates in `../../docs/telecalling-plan.md` are satisfied. Production
secrets belong in a secret store and must not be committed.

Use a private PBX lab first. Pin the chosen PBX build, inventory enabled
modules/codecs, preserve notices/source obligations, keep ARI behind the worker,
and provide real service health/readiness before adding a carrier.

Capture installed dependency metadata without downloading/loading a model:

```powershell
.\.venv\Scripts\python.exe infra\voice\license_inventory.py --output output\voice-license-inventory.json
```

The report includes package license metadata, installed notice paths and selected
decoder binary hashes. It does not approve a deployment. The local ASR revision
and asset manifest are referenced separately in `model-manifest.json`.
