# JARVIS Piper TTS Artifact, Runtime, and Provenance Gate

```text
JARVIS_VOICE_PHASE: IN_PROGRESS
PIPER_TTS_ARTIFACT_GATE: PASS_WITH_RESTRICTIONS
TTS_ARTIFACT_APPROVAL: BLOCKED
READY_FOR_AUTONOMOUS_TTS_BATCH: NO
RESEARCH_DATE: 2026-09-27
BASELINE_TTS_DECISION: b936d79
```

This is a read-only approval gate. It does not implement TTS, install Piper,
download a model, synthesize audio, open a speaker, or modify runtime code.

## Decision and precise blocker

The selected runtime direction remains Piper local/offline with
`pt_BR-faber-medium` / `faber`. The maintained runtime identified for 2026 is
the OHF-Voice distribution, not the archived Rhasspy source:

```text
runtime package: piper-tts==1.8.0
runtime source: https://github.com/OHF-Voice/piper1-gpl
publisher revision: 639388b6317fc4731e91d53da42aea68fd4166ff
runtime license: GPL-3.0-or-later
```

The exact Windows x64 wheel exists as a CPython 3.9 stable-ABI wheel and is
compatible by tag with Python 3.13. It was not installed.

The voice artifact is available at the pinned Hugging Face revision
`rhasspy/piper-voices:v1.0.0`, but provenance is not yet clean enough to
approve acquisition:

1. The exact `v1.0.0` config fetched from the pinned path is 4,855 bytes with
   SHA-256 `7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f`.
2. The current official Rhasspy voice manifest reports the same config name as
   6,969 bytes with MD5 `cbd8c19032f775db27d563b3bc3df7c6`, which is a
   different artifact identity.
3. The model card documents the dataset as CC0 but does not separately grant
   a clear model/voice redistribution or commercial-use license.

Therefore the gate is blocked pending an explicit reconciliation of the
revision-pinned config and a separate model/voice license decision. No file
from `main`, `latest`, or an unpinned cache may substitute for the pinned
artifact.

## Local audit

Search scope was limited to `C:\GoldenAI`, the Golden project directories,
the current project environment, and the existing relevant caches. Nothing
was copied or moved.

```text
PIPER_RUNTIME_ALREADY_AVAILABLE: NO
PIPER_RUNTIME_PATH: NONE

LOCAL_TTS_MODEL_FOUND: NO
LOCAL_TTS_MODEL_PATH: NONE

LOCAL_TTS_CONFIG_FOUND: NO
LOCAL_TTS_CONFIG_PATH: NONE

PIPER_EXECUTABLE_FOUND: NO
PIPER_PACKAGE_FOUND: NO
PT_BR_FABER_MODEL_FOUND: NO
PT_BR_FABER_CONFIG_FOUND: NO
```

The existing `references/HermesAgent` Piper tests and the donor checkout are
source references only; they are not approved Golden runtime artifacts.

## Piper runtime

```text
PIPER_RUNTIME_SOURCE: PyPI piper-tts release backed by OHF-Voice/piper1-gpl
PIPER_RUNTIME_PACKAGE: piper-tts
PIPER_RUNTIME_VERSION: 1.8.0
PIPER_RUNTIME_REVISION: 639388b6317fc4731e91d53da42aea68fd4166ff
PIPER_RUNTIME_LICENSE: GPL-3.0-or-later
```

The PyPI 1.8.0 release declares Python `>=3.9`, publishes a
`cp39-abi3-win_amd64` wheel, and lists Python 3.13 as a supported classifier.
The exact future Windows wheel identity is:

```text
filename: piper_tts-1.8.0-cp39-abi3-win_amd64.whl
size: approximately 34.1 MB as published by PyPI
sha256: 5da9bfdb05dfe15da3536859d422e605483ffa6d2b3ec2c5b9593bae6b5aa6a4
```

The PyPI publish attestation identifies the OHF-Voice repository and the
revision above. This is sufficient to pin a future installation, but not to
authorize it in this gate.

```text
WINDOWS_COMPATIBILITY: PASS_WITH_RESTRICTIONS
PYTHON_3_13_COMPATIBILITY: PASS_WITH_RESTRICTIONS
CPU_COMPATIBILITY: PASS_WITH_RESTRICTIONS
CPU_FIRST_PATH: YES
GPU_REQUIRED: NO
```

The restriction is evidentiary: the wheel/tag and source metadata fit the
machine, but this environment has not installed or executed Piper. The host
CPU is an AMD Ryzen 5 5600X with 6 cores and 12 logical processors. The future
path must use `PiperVoice.load(..., use_cuda=False)` and the ONNX Runtime CPU
execution provider.

### Runtime dependencies

The official 1.8.0 package declares:

```text
onnxruntime>=1,<2
pathvalidate>=3,<4
```

The Python implementation imports NumPy; Golden already has NumPy and
ONNX Runtime in its environment. The official Windows wheel contains the
Piper native bridge and espeak-ng data needed by the Python runtime. No
external `piper.exe` is required for the selected Python API path.

If a source distribution is used instead of the approved Windows wheel, the
build path additionally requires CMake, Ninja, a compiler toolchain, and the
espeak-ng build. That source-build path is not approved for the next batch.

```text
REQUIRED_PYTHON_PACKAGES:
  - piper-tts==1.8.0
  - onnxruntime>=1,<2
  - pathvalidate>=3,<4
  - numpy (already present; imported by Piper)

REQUIRED_NATIVE_BINARIES:
  - wheel-bundled espeakbridge native module
  - wheel-bundled espeak-ng data
  - no external Piper executable for the Python API path

REQUIRED_RUNTIME_FILES:
  - pt_BR-faber-medium.onnx
  - pt_BR-faber-medium.onnx.json
  - provenance.json, created during authorized acquisition
```

## Exact model and voice

```text
MODEL_ID: pt_BR-faber-medium
VOICE: faber
LOCALE: pt_BR
QUALITY: medium
LANGUAGE: Portuguese (Brazil)
SPEAKERS: 1

MODEL_REPOSITORY: rhasspy/piper-voices
MODEL_REVISION: v1.0.0
MODEL_DIRECTORY: pt/pt_BR/faber/medium

MODEL_FILENAME: pt_BR-faber-medium.onnx
CONFIG_FILENAME: pt_BR-faber-medium.onnx.json
OTHER_REQUIRED_FILES: none for PiperVoice.load; MODEL_CARD is required for provenance review
MODEL_FORMAT: ONNX
SAMPLE_RATE: 22050 Hz
```

Pinned source URLs:

```text
model:
https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx

config:
https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json

model card:
https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/pt/pt_BR/faber/medium/MODEL_CARD
```

Artifact evidence at the pinned revision:

```text
MODEL_SIZE: 63201294 bytes
CONFIG_SIZE: 4855 bytes
MODEL_SHA256: 858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7
CONFIG_SHA256: 7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f
MODEL_HF_LFS_SHA256: 858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7
CONFIG_HF_GIT_OID: b0206c81d70e6e4468b94d36491b4c17fac531b7
```

The model SHA-256 is the Hugging Face LFS object identity. The config
SHA-256 was computed from a read-only fetch of the pinned file and must be
recomputed and compared immediately after any authorized acquisition. The
Hugging Face API reports the config's Git object ID separately; it is not a
SHA-256 file digest.

The official model card describes `faber` as one-speaker, medium-quality,
22,050 Hz Brazilian Portuguese, trained from the U.S. English `lessac`
medium voice, with the `NabuCasa/voice-datasets` dataset listed as CC0.
Training provenance beyond that statement is:

```text
VOICE_DATASET_PROVENANCE: NabuCasa/voice-datasets; further provenance NOT DOCUMENTED
```

## License and usage rights

Licenses are kept separate. The Piper engine license does not automatically
license a voice artifact.

```text
PIPER_ENGINE_LICENSE: GPL-3.0-or-later
MODEL_REPOSITORY_LICENSE: MIT metadata on rhasspy/piper-voices
MODEL_LICENSE: NOT DOCUMENTED as a separate artifact grant
VOICE_LICENSE: NOT DOCUMENTED as a separate artifact grant
CONFIG_LICENSE: NOT DOCUMENTED at file level
DATASET_LICENSE: CC0, according to MODEL_CARD
DONOR_ADAPTER_LICENSE: donor A repository is MIT; file-level notices must be preserved before adaptation
```

The repository metadata and dataset notice are evidence, not a legal opinion.
Because the model/voice redistribution terms are not separately explicit, the
following remain uncleared:

```text
PERSONAL_INTERNAL_USE: NOT_CLEARED
PUBLIC_DISTRIBUTION: NOT_CLEARED
COMMERCIAL_USE: NOT_CLEARED
```

No model, config, model card, or sample audio was added to Golden.

## Canonical future storage and provenance

No canonical model directory currently exists in the project. The proposed
Golden-managed location is outside the source tree:

```text
CANONICAL_TTS_MODEL_STORAGE:
C:\GoldenAI\models\tts\piper\pt_BR-faber-medium\
```

The runtime files should retain their exact upstream names:

```text
pt_BR-faber-medium.onnx
pt_BR-faber-medium.onnx.json
provenance.json
```

The model must not enter Git, `jarvis_ui`, `build`, or `dist`.

`provenance.json` should be generated only during an authorized acquisition and
contain, at minimum:

```text
provider
runtime
runtime_version
runtime_revision
runtime_wheel_filename
runtime_wheel_sha256
model_id
voice
locale
repository
revision
model_url
config_url
model_card_url
model_size_bytes
config_size_bytes
model_sha256
config_sha256
manifest_md5_values
engine_license
model_license
voice_license
dataset_license
acquired_at_utc
```

## Acquisition and download policy

```text
MODEL_DOWNLOAD_REQUIRED: YES
PIPER_RUNTIME_INSTALL_REQUIRED: YES
MODEL_DOWNLOADS: NO
NEW_PACKAGES_INSTALLED: NONE

APPROVED_MODEL_SOURCE: BLOCKED_PENDING_PROVENANCE_RECONCILIATION
APPROVED_RUNTIME_SOURCE: PyPI piper-tts==1.8.0, OHF-Voice attested wheel

HUMAN_APPROVAL_REQUIRED_FOR_MODEL_DOWNLOAD: YES
HUMAN_APPROVAL_REQUIRED_FOR_RUNTIME_INSTALL: YES
IMPLICIT_TTS_MODEL_DOWNLOAD_ALLOWED: NO
```

Future authorization must cover only:

1. The exact `piper-tts==1.8.0` Windows x64 wheel and its declared runtime
   dependencies, with the recorded wheel SHA-256.
2. The exact `pt_BR-faber-medium.onnx` at `rhasspy/piper-voices:v1.0.0`.
3. The matching `pt_BR-faber-medium.onnx.json` after the size/hash
   discrepancy is reconciled and explicitly approved.
4. A provenance record and license notices.

It must exclude alternate voices, fallback models, `main`, `latest`, samples,
automatic voice download, and any runtime source build. Missing or invalid
artifacts must fail closed as `TTS_UNAVAILABLE`; they must never trigger a
substitute download.

## Output contract

The maintained Piper Python API exposes `PiperVoice.synthesize`, yielding one
`AudioChunk` per phonemized sentence. The chunk exposes:

```text
OUTPUT_SAMPLE_RATE: 22050 Hz for faber
OUTPUT_CHANNELS: 1
OUTPUT_SAMPLE_FORMAT: signed int16 for audio_int16_bytes
OUTPUT_ENCODING: raw PCM bytes; no WAV header in audio_int16_bytes
OUTPUT_FLOAT_FORM: float32 samples in [-1, 1] also exposed by AudioChunk
OUTPUT_BYTE_ORDER: native NumPy order; little-endian on this Windows x64 host
STREAM_BEHAVIOR: sentence chunks, not sample-level network streaming
```

The selected integration path can feed a Golden-owned `AudioOutputProvider`
with in-memory PCM. No temporary WAV is required for the Python API path.
The CLI's WAV/raw output and direct `ffplay` path are not the Golden runtime
integration path.

```text
IN_MEMORY_PCM_AVAILABLE: YES
TEMP_WAV_REQUIRED: NO
AUDIO_OUTPUT_PROVIDER_COMPATIBLE: YES_WITH_GOLDEN_ADAPTER
GENERATED_AUDIO_PERSISTED: NO
NETWORK_REQUIRED_DURING_INFERENCE: NO
TEXT_LEAVES_DEVICE: NO
AUDIO_LEAVES_DEVICE: NO
```

The provider yields sentence chunks; sentence segmentation and timeout
buffering are adapter orchestration, and speaker writes are playback
orchestration. These must remain separate in Golden.

## Donor and architecture reuse map

### Jarvis donor A

Donor A calls the Python API, not an executable or subprocess:

```text
from piper import PiperVoice
PiperVoice.load(model_path)
voice.synthesize(text, SynthesisConfig(...))
```

Its concrete output path uses `numpy`, `sounddevice.OutputStream`, and
`scipy.signal.resample_poly`; cancellation calls `OutputStream.abort()`,
drains queued audio, and closes the stream. It does not auto-download voice
files. Its declared dependencies include `piper-tts`, `sounddevice`, and
`scipy`, with NumPy used by the implementation.

```text
JARVIS_A_PIPER_ADAPTER: ADAPT
JARVIS_A_SENTENCE_STREAMING: REIMPLEMENT_PATTERN
JARVIS_A_PCM_QUEUE: ADAPT
JARVIS_A_PLAYBACK_CANCELLATION: ADAPT
JARVIS_A_TESTS: REIMPLEMENT_PATTERN
```

The adapter must not copy the donor's complete state machine, speaker owner,
provider policy, or dependency graph. The `abort`/drain idea is useful only
behind the existing Golden output owner.

### Hermes

Hermes provides the useful provider vocabulary: required `synthesize`,
optional `stream`, and lifecycle hooks such as `warm`/`release`. Golden should
adapt the contract vocabulary, not import Hermes runtime architecture.

```text
HERMES_PROVIDER_CONTRACT: ADAPT_CONTRACT_ONLY
HERMES_WARM_RELEASE: REIMPLEMENT_PATTERN_BEHIND_VOICESERVICE
HERMES_TEST_PATTERNS: REIMPLEMENT_PATTERN
```

### Jarvis B

Jarvis B contributes bounded queue, Windows device handoff, and recovery
patterns. Its Edge TTS path remains reference-only and is not promoted to the
primary provider.

```text
JARVIS_B_BOUNDED_QUEUE: ADAPT
JARVIS_B_DEVICE_RECOVERY: ADAPT
```

Golden ownership remains:

```text
VoiceService
    |
    +-- TextToSpeechProvider
    |       |
    |       +-- Piper adapter -> in-memory PCM chunks
    |
    +-- AudioOutputProvider -> one speaker owner
```

```text
GOLDEN_CANCELLATION_PRESERVED: YES
GOLDEN_TURN_MANAGER_PRESERVED: YES
GOLDEN_STATE_MACHINE_PRESERVED: YES
SECOND_CANCELLATION_MODEL_CREATED: NO
VOICE_SERVICE_REMAINS_OWNER: YES
```

The future cancellation path is `TurnManager`/Golden cancellation -> invalidate
TTS epoch -> stop accepting generated chunks -> abort/flush the output
provider. TTS must not call Core, execute tools, authorize actions, or access
TaskDatabase.

## Security and project boundaries

```text
TTS_PROVIDER_DIRECT_CORE_CALL: NO
TTS_PROVIDER_DIRECT_TOOL_EXECUTION: NO
TTS_PROVIDER_DIRECT_TASK_DB_ACCESS: NO
SECOND_CORE_CREATED: NO
SECOND_SECURITY_MODEL_CREATED: NO

TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
CANONICAL_TASK_DB_MATCH: YES
CANONICAL_TASK_DB: C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db

DEVICE_REGISTRY_TOUCHED: NO
RUNTIME_FILES_MODIFIED: NONE
DONOR_CODE_COPIED: NO
```

## Validation

The focused collection contained 106 tests with zero collection errors and no
collection warnings observed. The hardware-free voice regression is the
baseline suite used by the preceding TTS selection gate:

```text
VOICE_REGRESSION: PASS (106 passed in the official Golden venv)
SECURITY_COMPUTER_USE_REGRESSION: NOT_RUN (outside this read-only TTS gate)
SCHEDULER_REGRESSION: NOT_RUN (outside this read-only TTS gate)

TEST_COLLECTION: PASS
TESTS_COLLECTED: 106
COLLECTION_ERRORS: 0
COLLECTION_WARNINGS: 0 observed

SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS
```

No microphone, speaker, TTS API, model inference, or real synthesis was used.

## Changes and Git safety

```text
RUNTIME_FILES_MODIFIED: NONE
FILES_CREATED: docs/architecture/JARVIS_TTS_ARTIFACT_DECISION.md
FILES_MODIFIED: docs/architecture/JARVIS_TTS_ARTIFACT_DECISION.md
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
REAL_TTS_SYNTHESIS_EXECUTED: NO
AUDIO_PLAYBACK_STARTED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
DEVICE_REGISTRY_TOUCHED: NO
PUSH: NO
```

The documentation-only commit for this gate is intentionally separate from
the existing dirty worktree and must not include `device_registry.json`,
databases, build output, dist output, logs, credentials, or donor files.

## Final report

```text
JARVIS_VOICE_PHASE: IN_PROGRESS
PIPER_TTS_ARTIFACT_GATE: PASS_WITH_RESTRICTIONS
BASELINE_TTS_DECISION: b936d79
TTS_ARTIFACT_APPROVAL: BLOCKED

PIPER_RUNTIME_ALREADY_AVAILABLE: NO
PIPER_RUNTIME_PATH: NONE
PIPER_RUNTIME_SOURCE: PyPI piper-tts backed by OHF-Voice/piper1-gpl
PIPER_RUNTIME_PACKAGE: piper-tts
PIPER_RUNTIME_VERSION: 1.8.0
PIPER_RUNTIME_REVISION: 639388b6317fc4731e91d53da42aea68fd4166ff
PIPER_RUNTIME_LICENSE: GPL-3.0-or-later

WINDOWS_COMPATIBILITY: PASS_WITH_RESTRICTIONS
PYTHON_3_13_COMPATIBILITY: PASS_WITH_RESTRICTIONS
CPU_COMPATIBILITY: PASS_WITH_RESTRICTIONS
GPU_REQUIRED: NO
DONOR_A_PIPER_RUNTIME_MECHANISM: Python Piper API -> ONNX Runtime, not subprocess

MODEL_ID: pt_BR-faber-medium
VOICE: faber
LOCALE: pt_BR
QUALITY: medium
MODEL_REPOSITORY: rhasspy/piper-voices
MODEL_REVISION: v1.0.0
MODEL_FILENAME: pt_BR-faber-medium.onnx
CONFIG_FILENAME: pt_BR-faber-medium.onnx.json
MODEL_FORMAT: ONNX
SAMPLE_RATE: 22050 Hz
MODEL_SIZE: 63201294 bytes
CONFIG_SIZE: 4855 bytes at v1.0.0; manifest conflict reports 6969 bytes
MODEL_SHA256: 858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7
CONFIG_SHA256: 7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f
MODEL_LICENSE: NOT DOCUMENTED separately
VOICE_LICENSE: NOT DOCUMENTED separately
CONFIG_LICENSE: NOT DOCUMENTED at file level
VOICE_DATASET_PROVENANCE: NabuCasa/voice-datasets; CC0; further provenance NOT DOCUMENTED

PERSONAL_INTERNAL_USE: NOT_CLEARED
PUBLIC_DISTRIBUTION: NOT_CLEARED
COMMERCIAL_USE: NOT_CLEARED

MODEL_DOWNLOAD_REQUIRED: YES
PIPER_RUNTIME_INSTALL_REQUIRED: YES
APPROVED_MODEL_SOURCE: BLOCKED_PENDING_RECONCILIATION
APPROVED_RUNTIME_SOURCE: PyPI piper-tts==1.8.0 Windows x64 wheel
HUMAN_APPROVAL_REQUIRED_FOR_MODEL_DOWNLOAD: YES
HUMAN_APPROVAL_REQUIRED_FOR_RUNTIME_INSTALL: YES
IMPLICIT_TTS_MODEL_DOWNLOAD_ALLOWED: NO
CANONICAL_TTS_MODEL_STORAGE: C:\GoldenAI\models\tts\piper\pt_BR-faber-medium\

OUTPUT_SAMPLE_RATE: 22050 Hz
OUTPUT_CHANNELS: 1
OUTPUT_SAMPLE_FORMAT: signed int16
OUTPUT_ENCODING: raw PCM bytes
IN_MEMORY_PCM_AVAILABLE: YES
TEMP_WAV_REQUIRED: NO
AUDIO_OUTPUT_PROVIDER_COMPATIBLE: YES_WITH_GOLDEN_ADAPTER

NETWORK_REQUIRED_DURING_INFERENCE: NO
TEXT_LEAVES_DEVICE: NO
AUDIO_LEAVES_DEVICE: NO
GENERATED_AUDIO_PERSISTED: NO

VOICE_SERVICE_REMAINS_OWNER: YES
SECOND_CORE_CREATED: NO
SECOND_SECURITY_MODEL_CREATED: NO
SECOND_CANCELLATION_MODEL_CREATED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO

SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS
RUNTIME_FILES_MODIFIED: NONE
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
REAL_TTS_SYNTHESIS_EXECUTED: NO
AUDIO_PLAYBACK_STARTED: NO

COMMIT: PENDING_DOCUMENTATION_ONLY
PUSH: NO

READY_FOR_AUTONOMOUS_TTS_BATCH: NO
KNOWN_ISSUES: pinned v1.0.0 config disagrees with current official manifest; model/voice license is not separately documented
KNOWN_RESTRICTIONS: no install, no download, no inference, no playback, no implicit fallback acquisition
STOP_REASON: provenance and license gate blocked
NEXT_STEP: reconcile the exact config revision and obtain explicit artifact/runtime approval before installation
```

## Official references

- [piper-tts 1.8.0 on PyPI](https://pypi.org/project/piper-tts/1.8.0/)
- [OHF-Voice Piper releases](https://github.com/OHF-Voice/piper1-gpl/releases)
- [OHF-Voice Piper build and stable ABI notes](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/BUILDING.md)
- [Pinned Piper voice model card](https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/pt/pt_BR/faber/medium/MODEL_CARD)
- [Piper voice manifest](https://github.com/rhasspy/piper/blob/master/src/python_run/piper/voices.json)
- [Pinned Piper model file](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx)
- [Pinned Piper config file](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json)
- [Golden TTS selection decision](JARVIS_TTS_DECISION.md)
- [Golden Voice Donor Audit 2](JARVIS_VOICE_DONOR_AUDIT_2.md)
