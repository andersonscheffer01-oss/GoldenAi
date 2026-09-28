# JARVIS Local TTS Provider Audit

Status: Gate 2 research and selection only
Baseline: `f947cfd`
Date: 2026-09-28

## Scope and safety

This document records a reuse-first audit of local text-to-speech providers and
artifacts for the Golden voice runtime. No provider was installed, no model was
downloaded, no audio was synthesized or played, and no microphone or speaker
was opened. Production code, `device_registry.json`, runtime databases, and
security policy were not changed.

The gate is intentionally not an installation or integration approval. Any
future artifact installation requires a separate explicit gate with exact
package hashes, model revisions, license notices, and a rollback plan.

## Golden contract audited

The canonical contract is in `jarvis_core/voice_tts.py`.

- `PcmAudioChunk` carries PCM bytes, positive sample rate, channel count,
  `s16le` format, sequence/final markers, and `(session_id, turn_id,
  generation)` identity.
- `TextToSpeechProvider` exposes `warm()`, cancellable `synthesize()` and
  `stream()` operations, `cancel()`, and `release()`.
- `AudioOutputProvider` exposes `warm()`, identity-checked `enqueue()`,
  `cancel()`, `flush()`, and `release()`.
- `VoiceAudioPipeline` is the single provider-to-output owner. It rejects stale
  turn identities and cancels the prior provider/output before a new turn.
- `StreamingTTSOrchestrator` owns bounded segmentation, backpressure,
  cancellation, queue draining, and worker join.
- The current provider-neutral production path contains a fake provider, not a
  production local TTS implementation.

`jarvis_core/audio_output.py` provides the existing lazy
`SoundDeviceAudioOutputProvider`. It accepts bounded mono/stereo `s16le` PCM,
guards identity and format, and owns the single output stream. A selected TTS
provider must yield chunks into this contract; it must not open its own speaker
path or create a second turn owner.

## Previous decisions and constraints

`docs/architecture/JARVIS_TTS_DECISION.md` selected Piper as a local-first
direction, but left runtime licensing, voice/model licensing, artifact
provenance, and exact installation unresolved. The subsequent artifact gate
confirmed that `piper-tts==1.8.0` and the selected `pt_BR-faber-medium` artifact
were not present and that their final license bundle was not approved.

The conversation-stack audit also found no drop-in production provider and
classified Wyoming Piper as a useful reference/adapter rather than an existing
Golden runtime component.

## Runtime and machine facts

The canonical runtime is `C:\GoldenAI\.venv\Scripts\python.exe`:

- Python 3.13.15
- CPU: AMD Ryzen 5 5600X, 6 cores / 12 logical processors
- RAM: approximately 31.92 GB
- GPU: AMD Radeon RX 9060 XT; current Golden Torch is `2.13.0+cpu`
- CUDA/ROCm is unavailable in the current Torch runtime
- `espeak-ng` is not currently on `PATH`
- `kokoro`, `piper`, `coqui-tts`, `sherpa-onnx`, and `soundfile` are not
  installed in the canonical environment

Therefore CPU inference is the only currently demonstrated execution path.
The GPU is not an approved acceleration path for this application until a
separate runtime compatibility gate proves it without changing the voice
contract.

## Candidate audit

### 1. Kokoro: primary candidate, conditional approval

Project: [hexgrad/kokoro](https://github.com/hexgrad/kokoro)

- Runtime: current repository declares version `0.9.4`, Apache-2.0, Python
  `>=3.10,<3.14`, and dependencies on PyTorch, Transformers, Misaki, NumPy,
  and Hugging Face Hub. This fits Python 3.13 in the current repository.
- Packaging caveat: the published [PyPI 0.9.4 metadata](https://pypi.org/project/kokoro/0.9.4/)
  reports a contradictory upper Python bound (`<3.13`). The exact distribution
  to be used must therefore be pinned and verified before installation.
- Local/offline: yes, after artifacts are explicitly installed. The official
  project documents local generation and streaming/chunk iteration.
- PT-BR: native Portuguese language code `p`; the official
  [voice list](https://huggingface.co/hexgrad/Kokoro-82M/blob/a3ebfcc2bb43e3d8df8199d4081f4fc6d310cc6d/VOICES.md)
  includes `pf_dora`, `pm_alex`, and `pm_santa` for Brazilian Portuguese.
- Model: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), v1.0; the
  model card records Apache-licensed weights and model SHA256
  `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4`.
  The model card also identifies CC BY training-data components, so attribution
  and notice handling remains part of the artifact gate.
- Windows: plausible, but the official Windows instructions require an
  `espeak-ng` installation for phonemization. That dependency is absent from
  the current machine and must be pinned with its license/notice before use.
- Streaming: the generator/chunk model is compatible with bounded Golden
  streaming after conversion from the provider's audio representation to
  `s16le` PCM. Cancellation must be checked between generated segments and no
  provider-owned output stream may be created.
- Naturalness and latency: not proven for Golden. Project claims about speed or
  quality are not a substitute for a controlled PT-BR listening and latency
  benchmark.
- Integration cost: small at the Golden contract boundary, medium overall
  because PyTorch, phonemization, artifact packaging, float-to-PCM conversion,
  and cancellation need an isolated verification step.
- Decision: `KEEP_FOR_TEST`.

Kokoro is the best current primary candidate because it combines native PT-BR,
permissive runtime and weight licensing, local generation, and a practical
chunking shape. It is **not artifact-approved yet**: package metadata conflicts
with the current repository declaration, exact package and voice artifacts are
not pinned, and the Windows phonemizer dependency is not recorded.

### 2. Piper/OHF-Voice: fallback candidate, license constrained

Project: [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)

- Current release: official [PyPI `piper-tts` 1.8.0](https://pypi.org/project/piper-tts/)
  and the corresponding official repository release. The Windows x86-64
  wheel is published for the Python 3.9+ ABI; its recorded wheel SHA256 is
  `5da9bfdb05dfe15da3536859d422e605483ffa6d2b3ec2c5b9593bae6b5aa6a4`.
- Runtime license: GPL-3.0-or-later.
- PT-BR: the official [voice documentation](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md)
  supports `pt_BR`. The previous Golden selection was `pt_BR-faber-medium`,
  22,050 Hz.
- API: the official [Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
  yields audio chunks and exposes sample rate/width/channels, which maps well
  to an adapter.
- Artifact licensing: the exact [faber model card](https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/pt/pt_BR/faber/medium/MODEL_CARD)
  does not provide the separate voice/model grant needed for Golden approval.
  Dataset metadata and repository metadata are not sufficient substitutes for a
  final artifact license record.
- Windows/CPU: credible and likely simple on this machine; not benchmarked in
  this gate.
- Naturalness/latency: no current Golden evidence. Do not carry forward old
  assumptions as measured results.
- Decision: `ADAPT` as a fallback only. It remains blocked from artifact
  approval by GPL runtime and unresolved voice/model licensing.

### 3. Sherpa-ONNX: strong isolated alternative, not yet selected

Project: [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)

- Runtime: Apache-2.0; current official release is `v1.13.8`.
- Windows/Python: official releases publish a Windows x64 Python wheel,
  including a cp313 wheel; the observed cp313 Windows wheel hash is
  `195455d8d6cc49f616e9d459b7d08f10a32daf2ddcbe90d4d479a8ba9aab28bf`.
- Offline: yes. Official [TTS C API documentation](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/c-api/docs/tts.dox)
  documents offline TTS and Piper/Kokoro model families.
- PT-BR/artifacts: a model package and exact voice provenance still need to be
  selected and licensed. Piper-family phonemization can reintroduce GPL or
  compatibility concerns; the project has an active discussion about removing
  such dependencies.
- Integration: medium. A native/isolated boundary may be attractive for
  packaging, but the adapter, process lifecycle, chunk format, cancellation,
  and model-specific provenance are unverified here.
- Decision: `ADAPT` as a future alternative, not primary.

### 4. Wyoming Piper: protocol reference, not the Golden provider

Project: [OHF-Voice/wyoming-piper](https://github.com/OHF-Voice/wyoming-piper)

- Current release: `2.5.2`; official [PyPI metadata](https://pypi.org/project/wyoming-piper/2.5.2/)
  and project configuration identify an MIT runtime, Python `>=3.10`, and
  Python 3.13 support. It depends on `piper-tts>=1.8.0,<2`.
- It is a local protocol server, not a drop-in in-process implementation of
  the Golden `TextToSpeechProvider` contract.
- It adds a process/network boundary and its model still inherits Piper's
  unresolved voice/model licensing issue. The project has no role in approving
  Golden's single output owner or cancellation semantics.
- Decision: `REFERENCE_ONLY`. Reuse protocol ideas only if a later isolated
  provider gate explicitly accepts the extra boundary.

### 5. Coqui maintained fork: capable but license and footprint constrained

Project: [idiap/coqui-ai-TTS](https://github.com/idiap/coqui-ai-TTS), package:
[coqui-tts](https://pypi.org/project/coqui-tts/).

- Current package line observed: `0.27.5`; runtime license MPL-2.0; Python
  `>=3.10,<3.15`, including Python 3.13 classifiers. Windows is described as
  possible, but the tested platform is Linux.
- PT-BR: [XTTS documentation](https://github.com/coqui-ai/TTS/blob/dev/docs/source/models/xtts.md)
  includes Portuguese among supported languages.
- Model license: XTTS uses the Coqui Public Model License, not a simple
  permissive model grant. Commercial/product use requires a separate legal
  review.
- Integration: medium/large due to PyTorch/model cache/voice cloning concerns
  and a different output/streaming shape. It is not a small adapter to the
  existing PCM/cancellation contract.
- Decision: `REJECT` as Golden primary for this phase. Keep only as a future
  legally reviewed alternative.

### 6. MeloTTS: not suitable for this target

Project: [myshell-ai/MeloTTS](https://github.com/myshell-ai/MeloTTS).

- Runtime: MIT and CPU real-time claims are useful signals, but the official
  supported language list does not include Portuguese/PT-BR.
- Native Windows/Python 3.13: the official project guidance is primarily Linux
  and Python 3.9; Windows is described through Docker rather than the desired
  native Golden runtime path.
- Current project maintenance and issue burden do not provide enough evidence
  for a stable PT-BR Windows choice.
- Decision: `REJECT`.

### 7. Windows SAPI: machine fallback only

The existing Golden decision document records SAPI as a local machine fallback.
It has no controlled project voice artifact, depends on installed Windows
voices, and has weaker cancellation/streaming guarantees. It may be useful as
an emergency machine fallback but is not the selected local artifact provider.

Decision: `REFERENCE_ONLY` / machine fallback, not a reproducible primary.

## Selection matrix

| Candidate | PT-BR | Local/offline | Python 3.13 / Windows | Runtime license | Model/voice status | Contract fit | Decision |
|---|---|---|---|---|---|---|---|
| Kokoro | Native `p` voices | Yes | Conditional; current main says yes, PyPI metadata conflicts | Apache-2.0 | Apache weights; notices/voice bundle pending | Small adapter, medium packaging | KEEP_FOR_TEST |
| Piper | Native `pt_BR` | Yes | Credible | GPL-3.0-or-later | Exact voice grant unresolved | Good | ADAPT fallback |
| Sherpa-ONNX | Model-dependent | Yes | Strong wheel evidence | Apache-2.0 | Exact PT-BR model/provenance pending | Medium/native boundary | ADAPT |
| Wyoming Piper | Via Piper | Yes, server | Python 3.13 declared | MIT server, Piper GPL dependency | Piper issue remains | Process/protocol boundary | REFERENCE_ONLY |
| Coqui maintained | Portuguese | Yes | Conditional Windows evidence | MPL-2.0 runtime | CPML model restriction | Medium/large | REJECT |
| MeloTTS | No PT-BR | Yes | Poor native fit | MIT | Wrong language/platform | Poor | REJECT |
| SAPI | Machine voice dependent | Local | Windows only | OS/provider dependent | Not reproducible | Weak cancellation | REFERENCE_ONLY |

## Proposed architecture if the next gate approves installation

Use an **in-process Kokoro adapter** behind the existing
`TextToSpeechProvider` interface, subject to the artifact gate:

1. Load one explicitly pinned model/voice bundle during `warm()`.
2. Generate bounded sentence/segment chunks with no speaker ownership.
3. Convert provider output to `s16le` PCM at the provider sample rate.
4. Attach the current session/turn/generation identity to every chunk.
5. Check cancellation between segments and before enqueueing each chunk.
6. Let `VoiceAudioPipeline` and `SoundDeviceAudioOutputProvider` remain the
   only output owners.
7. Release model/runtime resources only through the existing lifecycle.

No provider may bypass `TurnManager`, generation invalidation, the bounded TTS
orchestrator, or the existing output cancellation/flush path.

## Artifact and license gate

Primary candidate: Kokoro.

- `ARTIFACT_PROVIDER`: Kokoro
- `ARTIFACT_MODEL_ID`: `hexgrad/Kokoro-82M`
- `ARTIFACT_VERSION_OR_REVISION`: v1.0; exact immutable repository revision
  still must be pinned in the installation gate
- `ARTIFACT_MODEL_SHA256`: `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4`
- `ARTIFACT_LICENSE`: Apache-2.0 weights; training-data attribution and
  per-voice notice reconciliation required
- `ARTIFACT_EXPECTED_SIZE`: approximately 327 MB for the model file according
  to the model card; exact voice files and package sizes are not pinned
- `PROPOSED_STORAGE`: `C:\GoldenAI\models\tts\kokoro\Kokoro-82M\v1.0\`
- `IMPLICIT_RUNTIME_DOWNLOAD_ALLOWED`: NO

Artifact approval is **not ready**. Before installation, pin the exact Kokoro
package/wheel and hash, exact model revision and voice files, `espeak-ng`
Windows artifact/version/hash/license/notice, and any required attribution
files. Then request a separate explicit installation approval.

## Gate result

```yaml
JARVIS_VOICE_PHASE: PARTIAL
LOCAL_TTS_PROVIDER_AND_ARTIFACT_GATE: PASS_WITH_RESTRICTIONS
BASELINE: f947cfd

GOLDEN_CONTRACT_AUDITED: YES
PRODUCTION_CODE_MODIFIED: NO
DEPENDENCIES_INSTALLED: NO
MODELS_DOWNLOADED: NO
AUDIO_SYNTHESIZED: NO
MICROPHONE_OPENED: NO
SPEAKER_OPENED: NO
DEVICE_REGISTRY_TOUCHED: NO

PRIMARY_PROVIDER: Kokoro
PRIMARY_IMPLEMENTATION_FORM: IN_PROCESS_PROVIDER
PRIMARY_PT_BR_MODEL: hexgrad/Kokoro-82M v1.0
PRIMARY_PT_BR_VOICES: pf_dora, pm_alex, pm_santa
PRIMARY_RUNTIME_LICENSE: Apache-2.0
PRIMARY_MODEL_LICENSE: Apache-2.0 weights; attribution and voice/artifact notice bundle pending
PRIMARY_LICENSE_VERIFIED: NO
PRIMARY_WINDOWS_COMPATIBLE: CONDITIONAL
PRIMARY_PYTHON_3_13_COMPATIBLE: CONDITIONAL
PRIMARY_OFFLINE: YES
PRIMARY_INTEGRATION: SMALL_ADAPTER_WITH_PACKAGING_CAVEATS
PRIMARY_NATURALNESS_EVIDENCE: UNKNOWN_REQUIRES_LISTENING_GATE
PRIMARY_LATENCY_EVIDENCE: UNKNOWN_REQUIRES_BENCHMARK

FALLBACK_PROVIDER: Piper/OHF-Voice piper1-gpl
FALLBACK_MODEL: pt_BR-faber-medium
FALLBACK_REASON: CPU/streaming/Windows fit is credible, but GPL runtime and voice/model grant remain unresolved

SHERPA_ONNX_STATUS: ADAPT_FUTURE_ALTERNATIVE
WYOMING_PIPER_STATUS: REFERENCE_ONLY
COQUI_STATUS: REJECT_FOR_PRIMARY
MELOTTS_STATUS: REJECT_NO_PT_BR_NATIVE_WINDOWS_FIT
SAPI_STATUS: REFERENCE_ONLY_MACHINE_FALLBACK

ARTIFACT_APPROVAL_READY: NO
ARTIFACT_PROVIDER: Kokoro
ARTIFACT_MODEL_ID: hexgrad/Kokoro-82M
ARTIFACT_SOURCE: https://huggingface.co/hexgrad/Kokoro-82M
ARTIFACT_VERSION_OR_REVISION: v1.0; immutable revision pending
ARTIFACT_LICENSE: Apache-2.0 weights; attribution/CC BY notices pending reconciliation
ARTIFACT_EXPECTED_SIZE: approximately 327 MB model file; exact bundle pending
PROPOSED_STORAGE: C:\GoldenAI\models\tts\kokoro\Kokoro-82M\v1.0\
IMPLICIT_RUNTIME_DOWNLOAD_ALLOWED: NO

READY_FOR_TTS_RUNTIME_ARTIFACT_INSTALLATION_GATE: NO
NEXT_GATE: KOKORO_ARTIFACT_AND_LICENSE_PINNING_GATE
NEXT_STEP: Pin package, model/voice files, espeak-ng artifact and notices; request explicit installation approval

FILES_CREATED: docs/architecture/JARVIS_LOCAL_TTS_PROVIDER_AUDIT.md
FILES_MODIFIED: NONE
TESTS: Read-only contract audit and environment inspection; no audio/runtime provider test executed
REMOTE_TEXT_SENT: NO
REMOTE_AUDIO_SENT: NO
SECRET_SCAN: PASS_NOT_APPLICABLE_NO_SECRET_FILES_TOUCHED
COMMIT_CREATED: YES
PUSH: NO
```

## Gate 2B addendum: Kokoro artifact and license pinning

This addendum supersedes the earlier conditional candidate assessment for
artifact approval. It is still research/verification only: no package, model,
voice, or `espeak-ng` artifact was installed or downloaded.

### Runtime pin

The cleanest reproducible runtime target is the published PyPI artifact, not an
unreleased repository checkout:

- `KOKORO_RUNTIME_SOURCE`: PyPI release
- `KOKORO_RUNTIME_PACKAGE`: `kokoro==0.9.4`
- `KOKORO_RUNTIME_VERSION`: `0.9.4`
- `KOKORO_RUNTIME_REVISION`: wheel SHA-256
  `a129dc6364a286bd6a92c396e9862459d3d3e45f2c15596ed5a94dcee5789efd`
- `KOKORO_RUNTIME_SDIST_SHA256`:
  `fbf633262797f8cf46fdac3315cf9cade67dc8b762c0feccf334892772fb9ac4`
- `KOKORO_RUNTIME_LICENSE`: Apache-2.0
- `KOKORO_RUNTIME_LICENSE_SOURCE`: package metadata and the upstream
  `LICENSE` file

The PyPI wheel is 32.6 kB and the source distribution is 26.2 MB. The package
has no upstream `v0.9.4` Git tag/release to use as a substitute for the PyPI
artifact. The current repository `main` also reports version `0.9.4`, but it is
not mixed into this runtime pin; repository source is used only to audit the
implementation and dependency behavior.

### Python and dependency compatibility

The evidence is internally inconsistent:

- current repository `pyproject.toml`: `>=3.10, <3.14`;
- current official repository `uv.lock`: `>=3.10, <3.13`;
- published PyPI `kokoro==0.9.4`: `>=3.10, <3.13`;
- published `misaki==0.9.4`: `>=3.8, <3.13`.

The official lock resolves Kokoro's core graph through `misaki[en]`,
`espeakng-loader`, `phonemizer-fork`, spaCy, spaCy curated transformers,
PyTorch, Transformers, NumPy, Hugging Face Hub, and Loguru. It also records
native/binary packages such as `blis`, `cymem`, `murmurhash`, `preshed`,
`srsly`, and `tokenizers`. The lock's captured PyTorch is 2.6.0 and is not the
current Golden `torch 2.13.0+cpu`; it must not be silently transplanted into
the Golden environment.

The `espeakng-loader==0.2.4` package publishes a Windows x86-64 wheel with
size 9,437,292 bytes and SHA-256
`41f1e08ac9deda2efd1ea9de0b81dab9f5ae3c4b24284f76533d0a7b1dd7abd7`.
This is evidence of a possible Windows distribution, not an installation or
license approval.

Result: Python 3.13.15 is **not supported by the published package/official
lock metadata**. The repository declaration alone is insufficient. Windows
11 AMD64 is technically plausible but unvalidated in the canonical runtime.

### espeak-ng role and Windows form

For PT-BR, Kokoro maps `lang_code='p'` to `pt-br` and constructs
`misaki.espeak.EspeakG2P(language='pt-br')`. Misaki's official implementation
uses `phonemizer.backend.EspeakBackend` and configures its library and data
paths through `espeakng_loader`. Thus `espeak-ng` is required for the proposed
PT-BR phonemization path; it is a G2P dependency, not the neural TTS voice or
the output audio owner.

The official Kokoro Windows instructions point to an x64 `*.msi` from the
official [eSpeak NG releases](https://github.com/espeak-ng/espeak-ng/releases).
The official eSpeak NG guide documents the same Windows MSI flow. The upstream
eSpeak NG source/API is GPL-3.0-or-later. The alternative Python
`espeakng-loader` wheel bundles/locates the native library and data, but its
packager, binary provenance, notices, and distribution terms must be reviewed
separately. No exact MSI or loader artifact is approved yet.

### Model pin

The exact model snapshot is:

- `MODEL_REPOSITORY`: `hexgrad/Kokoro-82M`
- `MODEL_REVISION`: `f3ff3571791e39611d31c381e3a41a3af07b4987`
- `MODEL_VERSION`: `v1.0`, published 2025-01-27
- `MODEL_FORMAT`: PyTorch state-dict file loaded with `torch.load(...,
  weights_only=True)`
- `MODEL_REQUIRED_FILES`: `config.json`, `kokoro-v1_0.pth`, selected files in
  `voices/`, and `VOICES.md`/license notices
- `MODEL_LICENSE`: Apache-2.0 for the model weights
- `MODEL_LICENSE_SOURCE`: official Hugging Face model metadata and model card
- `MODEL_LICENSE_VERIFIED`: YES, with required attribution/training-data notices
- `MODEL_FILE`: `kokoro-v1_0.pth`
- `MODEL_FILE_SIZE`: 327,212,226 bytes
- `MODEL_FILE_SHA256`: `496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4`
- `CONFIG_FILE_SIZE`: 2,351 bytes

The model repository's card explicitly states Apache-licensed weights and
lists CC BY 3.0/4.0 training-data notices. Those notices must be carried into
the later artifact bundle; they do not grant a separate license to voice files.

### PT-BR voice artifact pins

All three selected files are in the same immutable model snapshot. The source
repository and exact file hashes are verified, but no separate voice license
grant is declared by the official voice table or model card.

| Voice | Artifact | Snapshot | Size | SHA-256 | License | Provenance |
|---|---|---|---:|---|---|---|
| `pf_dora` | `voices/pf_dora.pt` | `f3ff3571791e39611d31c381e3a41a3af07b4987` | 523,425 bytes | `07e4ff987c5d5a8c3995efd15cc4f0db7c4c15e881b198d8ab7f67ecf51f5eb7` | No separate term declared; NOT VERIFIED | YES |
| `pm_alex` | `voices/pm_alex.pt` | `f3ff3571791e39611d31c381e3a41a3af07b4987` | 523,425 bytes | `cf0ba8c573c2480fc54123683a35cf1e2ae130428e441eb91f9149bdb188a526` | No separate term declared; NOT VERIFIED | YES |
| `pm_santa` | `voices/pm_santa.pt` | `f3ff3571791e39611d31c381e3a41a3af07b4987` | 523,430 bytes | `d42103169c5c872abbafb9129133af7e942bb9d272c3cc3b95c203e7d7198c29` | No separate term declared; NOT VERIFIED | YES |

The official `VOICES.md` identifies the files as Brazilian Portuguese voices
and publishes short SHA prefixes; the file pages provide the full SHA-256 and
size. This proves identity/provenance, not a separate legal grant. The model
repository's Apache metadata must not be extended to the voices by assumption.

### Audio and streaming behavior

- `NATIVE_SAMPLE_RATE`: 24,000 Hz, as shown by the official generator examples
  and model output path.
- `CHANNELS`: one logical channel; the model returns a squeezed 1-D waveform
  tensor.
- `OUTPUT_FORMAT`: in-memory PyTorch `FloatTensor`, no container and no direct
  PCM bytes.
- `RAW_PCM_DIRECT`: NO.
- `CONVERSION_REQUIRED`: YES; convert bounded float audio to validated mono
  `s16le` PCM before creating `PcmAudioChunk`.
- `SEGMENT_SYNTHESIS_SUPPORTED`: YES. `KPipeline` accepts text segments and
  yields per-segment results; this matches Adapter 3's bounded text segments.
- `TRUE_AUDIO_STREAMING_REQUIRED`: NO.

The existing Golden output provider remains the sole speaker owner.

### Download, cancellation, and integration boundary

The standard Kokoro path implicitly calls `hf_hub_download` for `config.json`,
the model file, and voice files when local paths are not supplied. This is not
acceptable for Golden runtime. The adapter must pass explicitly pinned local
paths, fail closed on a missing artifact, and run with network access disabled
or otherwise proven unreachable. No runtime cache miss may become a download.

The selected PT-BR path performs synchronous G2P and model inference and does
not expose a Golden cancellation token. In-process cancellation can therefore
invalidate stale output but cannot reliably interrupt an active model call.
The recommended form is a **local isolated provider process**:

```text
Golden VoiceService
  -> existing TextToSpeechProvider adapter
  -> bounded local request
  -> isolated Kokoro process
  -> float waveform / PCM result
  -> Golden AudioOutputProvider
```

The child process must own neither `VoiceService`, `TurnManager`, conversation
coordination, security authority, nor speaker output. Each request must carry
`request_id`, `session_id`, `turn_id`, `generation`, text, voice ID, and an
explicit artifact root. The response must carry the same identity, sample
rate, channels, sample format, PCM bytes or a bounded error. Cancellation must
terminate the current bounded child operation, flush the Golden output queue,
and rely on Golden generation guards to reject any late result.

### Canonical storage and integrity plan

Proposed storage:

```text
C:\GoldenAI\models\tts\kokoro\Kokoro-82M\f3ff3571791e39611d31c381e3a41a3af07b4987\
  runtime\
  model\config.json
  model\kokoro-v1_0.pth
  voices\pf_dora.pt
  voices\pm_alex.pt
  voices\pm_santa.pt
  licenses\
```

The later installation gate must verify:

- runtime wheel SHA-256 and, if used, source distribution SHA-256;
- immutable model snapshot revision;
- model LFS SHA-256 and exact byte size;
- each voice LFS SHA-256 and exact byte size;
- `config.json` and notice/license files;
- exact `espeakng-loader` Windows wheel or official MSI version/hash;
- an offline startup test proving no network fetch occurs.

Known selected-artifact size floor, excluding runtime/dependency artifacts:

- model + three voices: 328,782,506 bytes;
- plus `config.json` and `VOICES.md`: 328,792,482 bytes;
- runtime package and phonemizer dependencies are additional and must be
  measured from the final lock.

### License matrix

| Component | License | Verified | Source / restriction |
|---|---|---|---|
| Kokoro runtime/source | Apache-2.0 | YES | Official repository `LICENSE` and PyPI metadata |
| Kokoro model weights | Apache-2.0 | YES | Official Hugging Face metadata/model card; preserve notices |
| `pf_dora.pt` | Separate voice term not declared | NO | Voice file identity verified; license grant absent |
| `pm_alex.pt` | Separate voice term not declared | NO | Voice file identity verified; license grant absent |
| `pm_santa.pt` | Separate voice term not declared | NO | Voice file identity verified; license grant absent |
| eSpeak NG engine | GPL-3.0-or-later | YES | Official source/COPYING; distribution implications unresolved |
| `espeakng-loader` wheel | Package-specific terms require review | NO | PyPI artifact is third-party packaging of native engine/data |

### Installation plan for a future gate

No installation is authorized by this document. If legal/artifact approval is
later obtained, the next gate should:

1. create a separate local TTS runtime using Python 3.12 or another version
   explicitly supported by the pinned dependency closure; do not downgrade
   `C:\GoldenAI\.venv`;
2. install only the hash-pinned `kokoro==0.9.4` distribution and a newly
   verified compatible dependency lock;
3. select either a fully audited `espeakng-loader` Windows wheel or an official
   x64 MSI, with its exact notices and hash;
4. place the model and all three candidate voices under the immutable storage
   root above;
5. verify every hash and size before loading;
6. run the isolated child with explicit local paths and network denied;
7. test one bounded PT-BR segment to PCM without opening a speaker, then test
   cancellation, stale-generation rejection, and queue flush;
8. only after those checks request a separate human listening gate for voice
   selection.

### Gate 2B result

```yaml
JARVIS_VOICE_PHASE: PARTIAL
KOKORO_ARTIFACT_AND_LICENSE_PINNING_GATE: PASS_WITH_RESTRICTIONS
BASELINE: 1f48b1b22af5310cbe08b9933d1e7e511de37c0c

KOKORO_RUNTIME_SOURCE: PyPI
KOKORO_RUNTIME_PACKAGE: kokoro==0.9.4
KOKORO_RUNTIME_VERSION: 0.9.4
KOKORO_RUNTIME_REVISION: wheel sha256:a129dc6364a286bd6a92c396e9862459d3d3e45f2c15596ed5a94dcee5789efd
KOKORO_RUNTIME_LICENSE: Apache-2.0
RUNTIME_LICENSE_VERIFIED: YES

REPOSITORY_PYTHON_REQUIREMENT: ">=3.10, <3.14"
PYPI_PYTHON_REQUIREMENT: ">=3.10, <3.13"
PYTHON_3_13_15_SUPPORTED_BY_METADATA: CONDITIONAL
PYTHON_3_13_15_SUPPORTED_BY_DEPENDENCIES: NO
WINDOWS_11_AMD64_SUPPORTED: CONDITIONAL
DEPENDENCY_BLOCKER_FOUND: YES
DEPENDENCY_BLOCKERS:
  - published Kokoro and Misaki metadata exclude Python 3.13
  - official uv.lock also excludes Python 3.13 and resolves an older graph
  - native/binary closure is not validated in Golden's Python 3.13 environment
  - espeak-ng and loader licensing/provenance are not fully reconciled

ESPEAK_NG_REQUIRED: YES
ESPEAK_NG_ROLE: PT-BR G2P/phonemization via Misaki EspeakG2P(language=pt-br)
ESPEAK_NG_LICENSE: GPL-3.0-or-later
ESPEAK_NG_WINDOWS_SUPPORT: Official x64 MSI documented; exact release/hash pending
ESPEAK_NG_INTEGRATION_FORM: Misaki uses espeakng-loader library/data paths; loader or MSI requires separate approval

MODEL_REPOSITORY: hexgrad/Kokoro-82M
MODEL_REVISION: f3ff3571791e39611d31c381e3a41a3af07b4987
MODEL_VERSION: v1.0
MODEL_FORMAT: PyTorch .pth state dict
MODEL_REQUIRED_FILES: config.json, kokoro-v1_0.pth, selected voices/*.pt, notices
MODEL_LICENSE: Apache-2.0 weights
MODEL_LICENSE_VERIFIED: YES
MODEL_EXPECTED_SIZE: 327212226 bytes model; 328792482 bytes with config, VOICES.md and three candidate voices

PF_DORA_ARTIFACT: voices/pf_dora.pt @ f3ff3571791e39611d31c381e3a41a3af07b4987; sha256:07e4ff987c5d5a8c3995efd15cc4f0db7c4c15e881b198d8ab7f67ecf51f5eb7; 523425 bytes
PF_DORA_LICENSE: separate voice license not declared
PF_DORA_LICENSE_VERIFIED: NO
PF_DORA_PROVENANCE_VERIFIED: YES

PM_ALEX_ARTIFACT: voices/pm_alex.pt @ f3ff3571791e39611d31c381e3a41a3af07b4987; sha256:cf0ba8c573c2480fc54123683a35cf1e2ae130428e441eb91f9149bdb188a526; 523425 bytes
PM_ALEX_LICENSE: separate voice license not declared
PM_ALEX_LICENSE_VERIFIED: NO
PM_ALEX_PROVENANCE_VERIFIED: YES

PM_SANTA_ARTIFACT: voices/pm_santa.pt @ f3ff3571791e39611d31c381e3a41a3af07b4987; sha256:d42103169c5c872abbafb9129133af7e942bb9d272c3cc3b95c203e7d7198c29; 523430 bytes
PM_SANTA_LICENSE: separate voice license not declared
PM_SANTA_LICENSE_VERIFIED: NO
PM_SANTA_PROVENANCE_VERIFIED: YES

NATIVE_SAMPLE_RATE: 24000 Hz
CHANNELS: 1 logical mono channel
OUTPUT_FORMAT: PyTorch FloatTensor waveform; convert to mono s16le PCM
SEGMENT_SYNTHESIS_SUPPORTED: YES
TRUE_AUDIO_STREAMING_REQUIRED: NO

RECOMMENDED_IMPLEMENTATION_FORM: LOCAL_ISOLATED_PROVIDER_PROCESS
GOLDEN_VOICE_SERVICE_REMAINS_OWNER: YES
GOLDEN_AUDIO_OUTPUT_REMAINS_OWNER: YES
IMPLICIT_RUNTIME_DOWNLOAD_ALLOWED: NO
CANCELLATION_STRATEGY: bounded isolated child termination plus Golden generation guards and output flush

PROPOSED_STORAGE: C:\GoldenAI\models\tts\kokoro\Kokoro-82M\f3ff3571791e39611d31c381e3a41a3af07b4987\
MODEL_INTEGRITY_IDENTIFIER: model SHA256 496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4; size 327212226
VOICE_INTEGRITY_IDENTIFIER: pf_dora 07e4ff987c5d5a8c3995efd15cc4f0db7c4c15e881b198d8ab7f67ecf51f5eb7; pm_alex cf0ba8c573c2480fc54123683a35cf1e2ae130428e441eb91f9149bdb188a526; pm_santa d42103169c5c872abbafb9129133af7e942bb9d272c3cc3b95c203e7d7198c29
EXPECTED_TOTAL_SIZE: 328792482 bytes for model, config, VOICES.md and three candidate voices; dependencies extra

KOKORO_RUNTIME: Apache-2.0 / VERIFIED
KOKORO_MODEL: Apache-2.0 weights / VERIFIED_WITH_NOTICES
PF_DORA: separate voice license absent / NOT_VERIFIED
PM_ALEX: separate voice license absent / NOT_VERIFIED
PM_SANTA: separate voice license absent / NOT_VERIFIED
ESPEAK_NG: GPL-3.0-or-later / source verified, distribution path pending

KOKORO_DECISION: BLOCKED_LICENSE
ARTIFACT_APPROVAL_READY: NO
RUNTIME_INSTALLATION_READY: NO

PRODUCTION_CODE_CHANGED: NO
DEPENDENCIES_INSTALLED: NO
MODEL_DOWNLOADED: NO
VOICE_ARTIFACTS_DOWNLOADED: NO
ESPEAK_INSTALLED: NO
MICROPHONE_OPENED: NO
SPEAKER_OPENED: NO
AUDIO_PLAYED: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
PUSH: NO

FILES_CREATED: NONE
FILES_MODIFIED: docs/architecture/JARVIS_LOCAL_TTS_PROVIDER_AUDIT.md
COMMIT: DOCUMENTATION_ONLY_PENDING

READY_FOR_TTS_RUNTIME_ARTIFACT_INSTALLATION_GATE: NO
NEXT_GATE: KOKORO_LICENSE_RESOLUTION_AND_ISOLATED_RUNTIME_INSTALLATION_GATE
NEXT_STEP: obtain separate voice grants, reconcile espeak-ng/loader licensing, then pin a Python-3.12-compatible isolated dependency lock
KNOWN_RESTRICTIONS: no install, download, synthesis, audio playback, hardware access, production code, device registry, DB migration, or push
```

## Gate 2C addendum: final Kokoro license resolution

This addendum closes the Kokoro license-resolution gate without installing
packages, downloading artifacts, creating a runtime, or changing production
code. The baseline for this review is `ae719f926dae4d418d78fd3799bbcca751f806cb`.

### Voice provenance and license result

The official Kokoro model card declares the model and weights under
Apache-2.0. The official `VOICES.md` identifies `pf_dora`, `pm_alex`, and
`pm_santa` as Brazilian Portuguese voices and gives their file hashes, but it
does not provide an independent license grant or usage terms for any of the
three voicepack files. The official file metadata likewise exposes model-level
Apache metadata, not a per-voice grant. A maintainer post discusses permissive
Apache-licensed contributed data and possible corresponding voicepacks, but it
does not explicitly grant rights for these three files.

Accordingly, none of the candidate voices is explicitly approved. The correct
state is `AMBIGUOUS`, not Apache by inference. The repository license coverage
for the voice files is therefore also `AMBIGUOUS`.

### eSpeak NG and loader review

The current Kokoro/Misaki path invokes eSpeak NG through an in-process shared
library loaded by `espeakng-loader`. Upstream eSpeak NG is GPL-3.0-or-later.
Misaki is Apache-2.0, while the PyPI metadata reviewed for
`espeakng-loader==0.2.4` does not state a package-specific license. The
embedded upstream engine/data terms and the in-process distribution form must
be reconciled before any redistribution or bundling decision. This is a legal
review item, not a claim that private local execution has the same result as
distribution.

For personal local use, the practical legal analysis may differ from
redistribution, but that distinction is not clearance for Golden. The current
ambiguous voice provenance and loader/engine distribution questions mean that
the artifacts must not be bundled with Golden without legal review.

### Conditional isolated-runtime design

Kokoro is not approved for the Golden primary path. If a future voice receives
an explicit grant and the dependency closure is approved, the only acceptable
follow-up design is a separate Python 3.12.x child runtime at
`C:\\GoldenAI\\runtimes\\tts\\kokoro\\`. Golden Python 3.13.15 and
`C:\\GoldenAI\\.venv` remain unchanged. The child would use explicit local
artifact paths, fail closed when artifacts are absent, and never implicitly
download models or voices.

The minimal IPC design is subprocess stdin/stdout with JSON-lines control
messages and a bounded PCM response. Requests carry `request_id`, `session_id`,
`turn_id`, `generation`, `text`, `voice_id`, and an explicit artifact root.
Golden remains the owner of VoiceService, TurnManager, generation guards,
playback cancellation, output flushing, security boundaries, and stale-result
rejection. No HTTP listener, LAN exposure, second voice architecture, or
independent playback owner is permitted.

### Final Gate 2C report

```yaml
JARVIS_VOICE_PHASE: PARTIAL
KOKORO_LICENSE_RESOLUTION_AND_RUNTIME_APPROVAL: PASS_WITH_RESTRICTIONS
BASELINE: ae719f926dae4d418d78fd3799bbcca751f806cb

PF_DORA: AMBIGUOUS
PF_DORA_LICENSE: No separate license or usage grant declared
PF_DORA_EVIDENCE: Official VOICES/file hash plus model-level Apache metadata; no per-voice grant
PM_ALEX: AMBIGUOUS
PM_ALEX_LICENSE: No separate license or usage grant declared
PM_ALEX_EVIDENCE: Official VOICES/file hash plus model-level Apache metadata; no per-voice grant
PM_SANTA: AMBIGUOUS
PM_SANTA_LICENSE: No separate license or usage grant declared
PM_SANTA_EVIDENCE: Official VOICES/file hash plus model-level Apache metadata; no per-voice grant
REPOSITORY_LICENSE_EXPLICITLY_COVERS_VOICE_FILES: AMBIGUOUS
APPROVED_VOICE_SET: NONE

ESPEAK_NG_LICENSE: GPL-3.0-or-later
MISAKI/LOADER_LICENSES: Misaki Apache-2.0; espeakng-loader package-specific license absent from reviewed PyPI metadata; embedded eSpeak terms require review
INTEGRATION_FORM: Current path is in-process shared-library G2P through espeakng-loader; future isolated worker only, external boundary not currently implemented
LEGAL_REVIEW_REQUIRED: YES
PERSONAL_LOCAL_USE_FINDING: Local private execution may differ from redistribution; not a legal clearance
REDISTRIBUTION_FINDING: Do not bundle current voices, loader, or engine without legal review

ISOLATED_RUNTIME_VIABLE: CONDITIONAL
ISOLATED_PYTHON_VERSION: Python 3.12.x
ISOLATED_RUNTIME_LOCATION: C:\\GoldenAI\\runtimes\\tts\\kokoro\\
GOLDEN_PYTHON_UNCHANGED: YES
IPC_FORM: subprocess stdin/stdout JSON-lines control plus bounded PCM response
NETWORK_EXPOSED: NO
IMPLICIT_MODEL_DOWNLOAD_DISABLED_BY_DESIGN: YES

VOICESERVICE_REMAINS_OWNER: YES
TURNMANAGER_REMAINS_OWNER: YES
GENERATION_GUARDS_REMAIN_OWNER: YES
AUDIO_OUTPUT_REMAINS_OWNER: YES
SECOND_VOICE_ARCHITECTURE: NO

KOKORO_DECISION: REJECT_FOR_GOLDEN_PRIMARY
ARTIFACT_APPROVAL_READY: NO
RUNTIME_INSTALLATION_READY: NO
FINAL_KOKORO_RESEARCH_GATE: YES

PRODUCTION_CODE_CHANGED: NO
DEPENDENCIES_INSTALLED: NO
MODEL_DOWNLOADED: NO
VOICE_ARTIFACTS_DOWNLOADED: NO
ESPEAK_INSTALLED: NO
MICROPHONE_OPENED: NO
SPEAKER_OPENED: NO
AUDIO_PLAYED: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
PUSH: NO

FILES_MODIFIED: docs/architecture/JARVIS_LOCAL_TTS_PROVIDER_AUDIT.md
COMMIT: DOCUMENTATION_ONLY
NEXT_GATE: LOCAL_TTS_FALLBACK_SELECTION_GATE
NEXT_STEP: Reconsider Sherpa-ONNX, a maintained Piper successor, or SAPI fallback using existing evidence; do not reopen Kokoro research
KNOWN_RESTRICTIONS: no install, download, runtime creation, model/voice acquisition, synthesis, audio, hardware, production code, device registry, DB migration, or push
```

## Gate 2D: local TTS fallback selection

This gate is selection-only and reuses the existing Golden contracts. No
provider, package, model, voice, Windows component, path, or environment was
installed or changed. No synthesis, playback, microphone, or speaker access
was performed. Kokoro remains closed as a primary decision from Gate 2C.

### Reuse-first findings

Golden already owns `VoiceService`, `TurnManager`, `TextToSpeechProvider`,
`StreamingTTSOrchestrator`, `AudioOutputProvider`, generation guards,
cancellation, playback, and security boundaries. The provider-neutral pipeline
currently has a fake provider, while the legacy `VoiceService` already has a
SAPI fallback through `pywin32`. The selected path must reuse the provider
abstraction and make SAPI an adapter; it must not create a second voice owner,
speaker path, turn manager, or cancellation architecture.

The canonical runtime remains `C:\\GoldenAI\\.venv\\Scripts\\python.exe`,
Python 3.13.15. A read-only import check found `pywin32` available, while
`piper` and `sherpa_onnx` are absent. The machine exposes these SAPI voices:

- `Microsoft Maria Desktop - Portuguese(Brazil)`; language `416`, female,
  Microsoft vendor;
- `Microsoft Zira Desktop - English (United States)`; language `409`, female,
  Microsoft vendor.

### Windows SAPI assessment

SAPI is a Windows-native API and does not require Golden to distribute a neural
voice artifact. The installed Maria voice is an actual PT-BR capability on this
machine, and enumeration was read-only. Microsoft documents voice enumeration
through `SpVoice.GetVoices`, output to `SpMemoryStream`/`SpFileStream`, standard
PCM stream formats, asynchronous speech, and `Skip`/`Pause` controls. This is
enough architectural evidence for a small adapter that renders bounded text
segments to PCM/WAV and hands the bytes to Golden's existing output pipeline.

The exact Maria native format was not probed because this gate forbids
synthesis. SAPI supports standard PCM formats, but the adapter must read the
actual stream format and convert only at the provider boundary if required.
Cancellation remains conditional until the adapter proves that `Skip` or
equivalent SAPI control invalidates the pending request and that Golden's
generation guard rejects any late PCM. `NATURALNESS` and `LATENCY` remain
unvalidated.

The license model is different from a model artifact: Maria is an OS-installed
Microsoft voice selected through the local Windows SAPI registry, not a file
bundled by Golden. This supports local/private use on the licensed Windows
installation. It is not permission to redistribute the voice or generated
corpora; any product redistribution remains subject to the applicable Windows
terms and legal review.

### Sherpa-ONNX assessment

The sherpa-onnx runtime is Apache-2.0, publishes Windows x64 Python wheels
including CPython 3.13, supports offline TTS, and exposes Python/C/C++ APIs
that return generated samples. The official TTS catalog includes the exact
PT-BR artifact `vits-piper-pt_BR-dii-high`, converted from
`OpenVoiceOS/pipertts_pt-BR_dii`, with 22,050 Hz mono output. Its public model
card explicitly declares CC BY-NC-ND 4.0 and non-commercial/no-derivatives
restrictions. The runtime is technically viable, but this model is not a
Golden primary or distributable fallback.

The sherpa catalog also references PT-BR Piper artifacts such as
`vits-piper-pt_BR-faber-medium` and `vits-piper-pt_BR-cadu-medium`. Their
available cards identify language, sample rate, and CC0 datasets, but do not
provide a separate explicit voice/model grant sufficient to approve the ONNX
artifact for Golden distribution. No model was downloaded and no hash was
computed locally in this gate.

### Piper assessment

The current maintained implementation is `OHF-Voice/piper1-gpl`. Its runtime
is GPL-3.0-or-later, supports Windows/Python and offline CPU synthesis, and
the Python API exposes WAV and chunk-level PCM output. The exact official
PT-BR candidate `pt_BR-faber-medium` at Piper voices revision `v1.0.0` is
22,050 Hz, one speaker, with ONNX artifact SHA256
`858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7`.
Its model card identifies the CC0 dataset but does not explicitly grant the
voice/model artifact rights needed for Golden approval. The separate
OpenVoiceOS PT-BR Dii model is explicit but CC BY-NC-ND 4.0, so it is not a
general product fallback.

Piper is therefore technically credible but blocked for this selection by the
runtime distribution implications and unresolved Faber voice/model grant. It
is not rejected because GPL is inherently unusable; it is rejected because
the complete runtime plus voice distribution package is not approved here.

### Decision matrix

| Provider | Implementation | Maintenance | Runtime license | PT-BR | Voice/model license | Windows | Runtime form | Offline | Artifact clarity | Golden integration | Naturalness | Latency | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Windows SAPI | Microsoft `SpVoice` | OS-provided | Windows/provider terms | Maria installed | OS component; no bundled artifact | YES on this machine | Windows native API | YES | Machine-specific, no model pin | Small adapter | UNVALIDATED | UNVALIDATED | SELECT_PRIMARY |
| sherpa-onnx + Dii | Apache runtime | Active | Apache-2.0 | `vits-piper-pt_BR-dii-high` | CC BY-NC-ND 4.0 | YES | Python 3.13 or native child | YES | URL/revision, no local hash | Medium adapter | UNVALIDATED | UNVALIDATED | REJECT |
| Piper + Faber | OHF-Voice `piper1-gpl` | Active | GPL-3.0-or-later | `pt_BR-faber-medium` | Explicit voice grant absent | YES | Python or local process | YES | Revision and model hash | Small/medium adapter | UNVALIDATED | UNVALIDATED | REJECT |

### Selected boundary

SAPI is selected as Golden's local PT-BR primary for this machine, with a
conditional approval limited to local use of the already installed Windows
voice. The next gate must implement or validate only a small adapter behind
the existing `TextToSpeechProvider`: select the installed PT-BR token, render
bounded segments to an in-memory or temporary stream, convert to bounded
mono `s16le` PCM when needed, attach session/turn/generation identity, and
honor cancellation before enqueueing. The Golden `AudioOutputProvider`
remains the only playback owner.

No neural model is selected as fallback at this gate. If the Maria voice is
unavailable on another Windows installation, fail closed and require a new
provider/artifact approval; do not silently download or substitute a cloud
voice. `IMPLICIT_DOWNLOAD_DISABLED: YES`.

### Final Gate 2D report

```yaml
JARVIS_VOICE_PHASE: PARTIAL
LOCAL_TTS_FALLBACK_SELECTION_GATE: PASS_WITH_RESTRICTIONS
BASELINE: b9403c791fbd96736f960dacae2fb55a7f487a8e

SHERPA_ONNX:
  STATUS: TECHNICALLY_VIABLE_NOT_SELECTED
  RUNTIME_LICENSE: Apache-2.0
  WINDOWS: YES
  RUNTIME_FORM: IN_PROCESS_PYTHON_3_13_OR_STANDALONE_LOCAL_PROCESS
  PT_BR_MODEL: vits-piper-pt_BR-dii-high
  PT_BR_MODEL_LICENSE: CC BY-NC-ND 4.0
  PT_BR_LICENSE_VERIFIED: YES
  ARTIFACT_PINNABLE: NO
  DECISION: REJECT

PIPER:
  STATUS: TECHNICALLY_VIABLE_LICENSE_CONSTRAINED
  IMPLEMENTATION: OHF-Voice/piper1-gpl
  RUNTIME_LICENSE: GPL-3.0-or-later
  WINDOWS: YES
  RUNTIME_FORM: IN_PROCESS_PYTHON_OR_STANDALONE_LOCAL_PROCESS
  PT_BR_MODEL: pt_BR-faber-medium @ rhasspy/piper-voices v1.0.0
  PT_BR_MODEL_LICENSE: Explicit voice/model grant absent; dataset CC0 only
  PT_BR_LICENSE_VERIFIED: NO
  ARTIFACT_PINNABLE: YES
  DECISION: REJECT

WINDOWS_SAPI:
  STATUS: INSTALLED_AND_READ_ONLY_VALIDATED
  INSTALLED_PT_BR_VOICE_FOUND: YES
  VOICE: Microsoft Maria Desktop - Portuguese(Brazil)
  OFFLINE: YES
  PCM_CAPTURE: YES
  LICENSE_MODEL: OS-installed Microsoft voice; no Golden-distributed artifact
  DECISION: SELECT_PRIMARY

OTHER_FINALIST:
  PROVIDER: NONE
  STATUS: NONE
  PT_BR: NONE
  LICENSE: NONE
  DECISION: NONE

PRIMARY:
  PRIMARY_PROVIDER: Windows SAPI
  PRIMARY_IMPLEMENTATION: Microsoft SpVoice / installed Maria token
  PRIMARY_RUNTIME_FORM: WINDOWS_NATIVE_API
  PRIMARY_PT_BR_VOICE_OR_MODEL: Microsoft Maria Desktop - Portuguese(Brazil)
  PRIMARY_RUNTIME_LICENSE: Windows/SAPI OS component terms
  PRIMARY_MODEL_OR_VOICE_LICENSE: Installed OS voice; redistribution not cleared
  PRIMARY_LICENSE_VERIFIED: NO
  PRIMARY_WINDOWS_READY: YES
  PRIMARY_OFFLINE: YES
  PRIMARY_ARTIFACT_PINNABLE: NOT_APPLICABLE
  PRIMARY_NATURALNESS: UNVALIDATED
  PRIMARY_LATENCY: UNVALIDATED
  PRIMARY_INTEGRATION_COST: SMALL_ADAPTER
  PRIMARY_DECISION: CONDITIONALLY_APPROVED
  PRIMARY_REASON: Existing PT-BR voice is installed, offline, requires no model distribution, and fits a native adapter boundary; cancellation/PCM details require the next controlled adapter gate.

FALLBACK:
  FALLBACK_PROVIDER: NONE_SELECTED
  FALLBACK_VOICE_OR_MODEL: NONE
  FALLBACK_REASON: Neural PT-BR candidates have unresolved or restrictive artifact licensing.

GOLDEN:
  VOICE_SERVICE_REMAINS_OWNER: YES
  TURN_MANAGER_REMAINS_OWNER: YES
  TTS_PROVIDER_REUSED: YES
  STREAMING_TTS_ORCHESTRATOR_REUSED: YES
  AUDIO_OUTPUT_REMAINS_OWNER: YES
  GENERATION_GUARDS_REMAIN_OWNER: YES
  SECOND_VOICE_ARCHITECTURE: NO

SAFETY:
  PRODUCTION_CODE_CHANGED: NO
  DEPENDENCIES_INSTALLED: NO
  MODELS_DOWNLOADED: NO
  VOICE_ARTIFACTS_DOWNLOADED: NO
  WINDOWS_VOICES_INSTALLED: NO
  MICROPHONE_OPENED: NO
  AUDIO_SYNTHESIZED: NO
  AUDIO_PLAYED: NO
  DEVICE_REGISTRY_TOUCHED: NO
  TASK_DB_SCHEMA_MIGRATION: NONE
  PUSH: NO

CHANGES:
  FILES_MODIFIED: docs/architecture/JARVIS_LOCAL_TTS_PROVIDER_AUDIT.md
  COMMIT: DOCUMENTATION_ONLY_PENDING

DECISION:
  LOCAL_TTS_PROVIDER_SELECTED: YES
  READY_FOR_CONTROLLED_TTS_INSTALLATION: NO
  NEXT_GATE: WINDOWS_SAPI_ADAPTER_AND_PCM_VALIDATION_GATE
  NEXT_STEP: Validate Maria token selection, actual PCM stream format, bounded segment conversion, cancellation, stale-generation rejection, and AudioOutputProvider handoff without synthesizing during this gate.
  KNOWN_RESTRICTIONS: no install, download, model acquisition, voice installation, synthesis, playback, microphone, production runtime change, device registry change, DB migration, or push
```
