# Voice licensing review

Reviewed against primary sources on 5 October 2026, IST. This is an engineering
dependency review, not a guarantee that every deployment has no legal issues.
Commercially usable software can still require notices, source availability,
carrier onboarding, or rights to a particular speaker's recording.

## Recommendation

Keep installed Windows speech synthesis for the current local demonstration.
Select **Parler-TTS Mini v1** as the provisional production English TTS
candidate with a stock voice. Its model card declares Apache-2.0, and voice
style is controlled by description; the user does not need to supply a custom
speaker recording. The model and its complete pinned runtime still require an
audible quality/latency benchmark and deployment inventory before release.
[Parler model card](https://huggingface.co/parler-tts/parler-tts-mini-v1).

Keep Mini v1.1 disabled because of an additional **tokenizer provenance gate**: its card says
the prompt tokenizer derives from `unsloth/llama-2-7b`, and its asset config
identifies `LlamaTokenizer`. Original Meta Llama 2 materials have separate
community-license terms. The Parler weight-card label alone does not resolve
the exact copied tokenizer asset's terms; obtain explicit provenance/terms
before approving that bundle. Mini v1 uses a T5 tokenizer and is the cleaner
English candidate selected provisionally for evaluation. The T5 tokenizer,
embedded text encoder, DAC codec weights and exact runtime still need their
own pinned inventory and deployment review.
[v1.1 tokenizer](https://huggingface.co/parler-tts/parler-tts-mini-v1.1/blob/main/tokenizer_config.json),
[original Llama 2 terms](https://github.com/meta-llama/llama/blob/llama_v2/LICENSE),
[Mini v1 tokenizer](https://huggingface.co/parler-tts/parler-tts-mini-v1/blob/main/tokenizer_config.json).

**SpeechT5 plus Microsoft's HiFi-GAN vocoder** remains an alternative, with
MIT-labeled weights. A separately cleared speaker embedding is required for
that alternative; prefer one derived from an owned recording with speaker
permission rather than automatically copying tutorial voice vectors. Neither
candidate is a blanket guarantee against all license issues.
[SpeechT5 weights](https://huggingface.co/microsoft/speecht5_tts),
[HiFi-GAN weights](https://huggingface.co/microsoft/speecht5_hifigan).

For Hindi, evaluate Indic Parler-TTS separately after English works. Its model
card declares Apache-2.0, supports multiple Indian languages, and currently
requires accepting repository access conditions. Download authorization and
hardware testing remain pending.
[AI4Bharat model card](https://huggingface.co/ai4bharat/indic-parler-tts).

## Component decisions

| Component or asset | Primary-source finding | Decision / remaining work |
| --- | --- | --- |
| Windows `System.Speech` / SAPI voices | The API enumerates installed speech engines; it does not grant a blanket redistribution license for those engines. [Microsoft API](https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer.getinstalledvoices) | Local host demo only. Record installed engine names and applicable Windows/voice terms. Do not copy voice binaries into a Linux container or market this as an open model. |
| faster-whisper | Repository uses MIT; CPU INT8 and CUDA execution are documented. [Project](https://github.com/SYSTRAN/faster-whisper) | Preferred ASR implementation. Review the actual resolved wheel dependencies, decoder build, and chosen converted checkpoint. |
| CTranslate2 | Runtime license is MIT. [License](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) | Retain its copyright and license notices. GPU deployment separately uses NVIDIA runtime terms. |
| Original Whisper weights | Upstream explicitly applies MIT to both code and model weights. [Upstream license statement](https://github.com/openai/whisper#license) | Prefer original weights, or a documented conversion of those exact weights. A third-party fine-tuned checkpoint needs its own review. |
| PyAV / FFmpeg decoder | PyAV's wrapper is BSD-3-Clause. FFmpeg is LGPL-2.1-or-later by default, while enabling GPL parts changes its licensing. [PyAV license](https://github.com/PyAV-Org/PyAV/blob/master/LICENSE.txt), [FFmpeg legal page](https://ffmpeg.org/legal.html) | Do not call the ASR dependency graph MIT-only. Review the installed decoder's bundled binaries, build flags, codecs, notices, and matching source before distributing an image. |
| ONNX Runtime / tokenizer runtime | ONNX Runtime has an MIT source license; Hugging Face Tokenizers uses Apache-2.0. [ONNX license](https://github.com/microsoft/onnxruntime/blob/main/LICENSE), [Tokenizers license](https://github.com/huggingface/tokenizers/blob/main/LICENSE) | Retain notices; record exact binary distributions and any separately bundled components in the SBOM. |
| Systran converted Whisper base | The model card labels MIT and documents conversion from OpenAI Whisper base to CTranslate2. [Conversion card](https://huggingface.co/Systran/faster-whisper-base) | The implementation owner is provisioning a pinned local revision. Record the full revision, model hashes, source card and upstream MIT notice; availability is separate from ASR quality validation. |
| `microsoft/speecht5_tts` weights | Model card labels the weights MIT, describes LibriTTS fine-tuning, and notes that Hugging Face authored the card. [Model card](https://huggingface.co/microsoft/speecht5_tts) | Alternative English TTS candidate. Archive the exact model revision, source card, and available upstream license text. Test intelligibility, names, numbers, and latency. |
| `microsoft/speecht5_hifigan` weights | Model card labels the vocoder MIT and links the original release. [Model card](https://huggingface.co/microsoft/speecht5_hifigan) | Review and pin independently of the acoustic model; do not infer its license from the TTS repository alone. |
| Transformers runtime | Apache-2.0 source license. [License](https://github.com/huggingface/transformers/blob/main/LICENSE) | Pin a tested SpeechT5-compatible version in an isolated voice environment. Review the complete resolved dependency report. |
| Speaker encoder weights | SpeechBrain's x-vector checkpoint is labeled Apache-2.0; its card documents VoxCeleb training and 16 kHz input. [Encoder card](https://huggingface.co/speechbrain/spkrec-xvect-voxceleb) | Candidate for deriving an embedding from an owned recording. Preserve the model terms, review input rights, and avoid using third-party example speaker vectors automatically. |
| Own recording and derived speaker vector | Software/model licenses do not establish consent to imitate a person or reuse someone else's recording | Require a record of recording ownership, speaker authorization for synthetic commercial calling, permitted purpose, and withdrawal handling. Treat recording/vector as separate assets in the manifest. |
| Kokoro-82M weights and published voice files | Official model repository identifies Apache-2.0 and publishes a voice list. [Model card](https://huggingface.co/hexgrad/Kokoro-82M), [voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) | Potential commercial candidate, not selected by default. Archive the exact weight and each chosen voice file, their hashes, and corresponding terms. A voice list is not evidence that every mirrored voice pack has identical rights. |
| Kokoro default Python dependency path | `kokoro` requires `misaki[en]`; that extra includes phonemizer and eSpeak loaders. [Kokoro dependencies](https://github.com/hexgrad/kokoro/blob/main/pyproject.toml), [Misaki extras](https://github.com/hexgrad/misaki/blob/main/pyproject.toml) | Do not describe `pip install kokoro` as a dependency stack containing only permissive licenses. Resolve and review before selecting. |
| Kokoro ONNX implementation | Implementation advertises MIT; its tokenizer imports phonemizer and loads eSpeak libraries. [Repository](https://github.com/thewh1teagle/kokoro-onnx), [tokenizer](https://github.com/thewh1teagle/kokoro-onnx/blob/main/src/kokoro_onnx/tokenizer.py) | ONNX conversion does not remove phonemizer obligations or independently prove rights to its combined `voices.bin` asset. |
| phonemizer, phonemizer-fork and eSpeak-NG | Their upstream terms use GPLv3; the fork package declares GPLv3-or-later. [phonemizer license](https://github.com/bootphon/phonemizer/blob/master/LICENSE), [fork package metadata](https://pypi.org/project/phonemizer-fork/3.3.1b3/), [eSpeak license](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING) | GPL is commercially usable with its conditions. This is not a royalty problem, but redistribution/combined-program obligations need review. Omit this path from the first permissive TTS candidate. |
| Parler-TTS Mini v1 | Model card declares Apache-2.0; voice is controlled through a description and its tokenizer config uses T5Tokenizer. [Model card](https://huggingface.co/parler-tts/parler-tts-mini-v1), [tokenizer config](https://huggingface.co/parler-tts/parler-tts-mini-v1/blob/main/tokenizer_config.json) | Provisional production English stock-voice default. Benchmark inference and review all pinned assets/runtime before release. |
| Parler runtime and audio codec | Upstream setup lists Transformers, Torch, SentencePiece, audio codec, audio tools, and Protobuf; one dependency follows an unpinned Git repository. [Setup](https://github.com/huggingface/parler-tts/blob/main/setup.py) | Pin Git commits and review codec/model assets too. Do not install straight from moving `main` for production. |
| Parler v1.1 prompt tokenizer | The model card names Llama-2-derived tokenizer provenance, distinct from the TTS weights. [Card](https://huggingface.co/parler-tts/parler-tts-mini-v1.1) | Block production bundle approval until exact tokenizer rights are resolved; evaluate T5-tokenizer Mini v1 as an alternative. |
| Mini v1 text encoder/tokenizer assets | Its config identifies `google/flan-t5-large`; that checkpoint card declares Apache-2.0. [Parler config](https://huggingface.co/parler-tts/parler-tts-mini-v1/blob/main/config.json), [FLAN-T5 card](https://huggingface.co/google/flan-t5-large) | Inventory the exact embedded/downloaded encoder and tokenizer assets, hashes and notices independently. A Python T5Tokenizer class license does not by itself cover its vocabulary files. |
| Parler DAC codec weights and implementation | Parler config names `parler-tts/dac_44khZ_8kbps`; that model card identifies MIT for weights, and Descript's source license is MIT. [Codec card](https://huggingface.co/parler-tts/dac_44khZ_8kbps), [source license](https://github.com/descriptinc/descript-audio-codec/blob/main/LICENSE) | Pin the exact codec asset/conversion and preserve notices; review resolved audiotools/dependencies separately. |
| Asterisk PBX | GPLv2 core; upstream expressly permits external applications over ARI/AMI/AGI under a license of their choice. Loadable modules have separate implications. [Upstream license](https://github.com/asterisk/asterisk/blob/master/LICENSE) | Preferred initial lab PBX as a separate process controlled through ARI. Keep original notices and fulfill applicable binary/source obligations if distributing PBX images; do not embed proprietary modules without a separate review. |
| FreeSWITCH PBX | Upstream declares MPL-1.1 for the main code and lists additional file/component licenses. [License inventory](https://github.com/signalwire/freeswitch/blob/master/LICENSE) | Viable alternative with file-level obligations. Choose modules/codecs explicitly; do not label the entire build MPL-only or obligation-free. |
| SIP trunk, caller number, recordings | An OSS PBX does not grant access to telephone networks or rights to any caller number | Production requires a carrier contract, allocated caller ID, sender onboarding, and applicable calling/recording policies. See `telecalling-plan.md`. |

## Release evidence

Maintain two inventories: installed **software**, and **model/voice assets**.
For each include source URL, fixed revision, SHA-256, license identifier and
saved text, notices, conversion history, permitted purpose, and reviewer/date.
For a voice asset add provenance and speaker permission where relevant. A
package's `License` metadata alone does not license separately downloaded
weights, sample recordings, embeddings, or voice packs.

For distribution, build a third-party-notice bundle and satisfy the actual
licenses in the resolved image. For service operation, separately review data,
speaker, carrier, privacy, and telecom requirements. Free software licenses do
not establish that a voice sounds natural, that transcription is accurate, or
that a call is authorized.

No production TTS weights, external speaker vectors, PBX image, or SIP trunk
were downloaded or activated by this review. The implementation owner is
separately provisioning local Whisper ASR. The manifest under `infra/voice/`
is an unapproved production deployment scaffold. Report local audio/ASR test
results separately; they do not approve redistribution of a dependency image.

`infra/voice/license_inventory.py` can capture installed package metadata,
bundled notice paths and decoder binary hashes without network access. Its
output is an inventory aid, not proof that a wheel's short license label also
covers every linked library or that the complete distribution satisfies every
license. Production deployment remains gated on a reviewed SBOM and notices.

The local inventory captured seven installed voice/runtime packages, including
faster-whisper 1.2.1, CTranslate2 4.8.2 and PyAV 18.1.0. It records 74 decoder
binary hashes and the PyAV wrapper's installed license path. That path alone
does not establish the bundled FFmpeg/codecs' terms. See
`output/voice-license-inventory.json`; `deployment_approved` remains false.
