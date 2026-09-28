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
