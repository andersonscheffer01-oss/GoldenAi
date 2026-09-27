# JARVIS TTS License and Artifact Blocker Resolution

```text
JARVIS_VOICE_PHASE: IN_PROGRESS
TTS_BLOCKER_RESOLUTION_GATE: PASS_WITH_RESTRICTIONS
BASELINE: 3507104
RESEARCH_DATE: 2026-09-27
```

Mode: research and decision only. No TTS implementation, package install,
model download, synthesis, audio output, or architecture change was performed.

## Executive decision

The Faber artifact identity blocker is resolved:

```text
FABER_ARTIFACT_IDENTITY_GATE: PASS
PINNED_MODEL_CONFIG_PAIR_VALID: YES
CONFIG_SIZE_DISCREPANCY_EXPLAINED: YES
```

The license blocker is not resolved:

```text
FABER_LICENSE_GATE: BLOCKED
TTS_ARTIFACT_APPROVAL: BLOCKED
READY_FOR_AUTONOMOUS_TTS_BATCH: NO
```

The correct conclusion is not to replace Piper or invent a new provider. The
selected direction remains Piper/Faber, pending a separate license decision
for the voice/model artifact and the GPL runtime integration.

## Faber investigation

### Pinned artifact set

Both files resolve from the same official Hugging Face repository, tag, and
directory:

```text
repository: rhasspy/piper-voices
revision: v1.0.0
revision_commit: 375a0fe641dea077c2a47b4e9a056d6da521eed3
directory: pt/pt_BR/faber/medium

model: pt_BR-faber-medium.onnx
model_size: 63201294 bytes
model_sha256: 858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7

config: pt_BR-faber-medium.onnx.json
config_size: 4855 bytes
config_sha256: 7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f
config_git_oid: b0206c81d70e6e4468b94d36491b4c17fac531b7
```

The JSON identifies `piper_version: 1.0.0`, `pt_BR`, dataset `faber`, one
speaker, 22,050 Hz, and the same model family. The ONNX LFS object is the
same model object on the pinned tag and the current Hugging Face `main` tree.
The pinned pair is therefore internally consistent for acquisition; Golden
must keep the two files together and must not mix revisions.

Pinned URLs:

- [Faber ONNX at v1.0.0](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx)
- [Faber JSON at v1.0.0](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json)
- [Faber model card at v1.0.0](https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/pt/pt_BR/faber/medium/MODEL_CARD)

### Explanation of the 4,855 versus 6,969 discrepancy

The 6,969-byte value came from the `voices.json` manifest in the historical
`rhasspy/piper` source repository. That repository is archived and its
manifest metadata is stale relative to the actual `rhasspy/piper-voices`
artifact tree.

Read-only comparison showed:

```text
rhasspy/piper-voices:v1.0.0 config: 4855 bytes
rhasspy/piper-voices:main config: 4855 bytes
rhasspy/piper-voices:v1.0.0 config Git OID: b0206c81d70e6e4468b94d36491b4c17fac531b7
rhasspy/piper-voices:main config Git OID: b0206c81d70e6e4468b94d36491b4c17fac531b7
historical rhasspy/piper manifest entry: 6969 bytes, older MD5 metadata
```

This is manifest metadata drift, not evidence that the pinned ONNX and JSON
are mismatched. The authoritative acquisition identity is the pinned voice
repository revision and the file hashes above, not the stale historical
manifest entry.

### Faber provenance

```text
language: pt_BR / Portuguese (Brazil)
voice: faber
quality: medium
sample_rate: 22050 Hz
speakers: 1
dataset/source: https://github.com/NabuCasa/voice-datasets
dataset_license: CC0
training_note: finetuned from U.S. English lessac medium voice
additional_training_provenance: NOT DOCUMENTED
```

The dataset license is not treated as the model or voice license.

## License resolution

Licenses are classified independently:

| Component | Evidence | Classification | Gate result |
| --- | --- | --- | --- |
| Piper runtime | OHF-Voice package metadata and source | Explicit GPL-3.0-or-later | Requires integration review |
| Voice repository | `rhasspy/piper-voices` README metadata says MIT | Explicit repository metadata | Scope over each voice file is not separately stated |
| Faber model | No model-specific license in MODEL_CARD | Unknown at artifact level | Blocked |
| Faber voice | No separate voice license in MODEL_CARD | Unknown at artifact level | Blocked |
| Faber config | Covered only by repository metadata; no file notice | Explicit repository metadata, file scope unknown | Blocked with model/voice gate |
| Faber dataset | MODEL_CARD says CC0 | Explicit dataset license | Not sufficient to clear model/voice |
| Donor A adapter | Donor repository is MIT | Explicit repository-level evidence | No code copied; review required before adaptation |

The official Piper maintainer's licensing discussion says voice checkpoints do
not receive a universal additional license and that users must inspect the
training history and make the final judgment. It also distinguishes the
engine license from voice/data terms. This supports keeping Faber blocked
rather than inferring a voice license from CC0 or repository metadata.

```text
FABER_MODEL_LICENSE: EXPLICIT_REPOSITORY_METADATA_MIT; MODEL_SCOPE_UNKNOWN
FABER_VOICE_LICENSE: UNKNOWN / NOT DOCUMENTED
FABER_CONFIG_LICENSE: EXPLICIT_REPOSITORY_METADATA_MIT; FILE_SCOPE_UNKNOWN
FABER_DATASET_LICENSE: EXPLICIT CC0

PERSONAL_INTERNAL_USE: NOT_CLEARED
PUBLIC_DISTRIBUTION: NOT_CLEARED
COMMERCIAL_USE: NOT_CLEARED
```

These are evidence classifications, not legal advice.

## Piper runtime and GPL implications

```text
PIPER_RUNTIME: piper-tts
PIPER_VERSION: 1.8.0
PIPER_REVISION: 639388b6317fc4731e91d53da42aea68fd4166ff
PIPER_LICENSE: GPL-3.0-or-later
```

The official PyPI release provides a Windows x64 `cp39-abi3` wheel, declares
Python 3.9+ including Python 3.13 classifiers, and depends on
`onnxruntime>=1,<2` and `pathvalidate>=3,<4`. The wheel is a better future
acquisition target than an unpinned source build.

```text
IN_PROCESS_INTEGRATION_POSSIBLE: YES, subject to GPL and distribution review
OUT_OF_PROCESS_INTEGRATION_POSSIBLE: YES, subject to GPL and distribution review
```

In-process means importing `piper` and its GPL runtime into the Golden Python
process. Out-of-process means a VoiceService-owned provider helper runs the
Piper executable or a small Piper worker and returns PCM over a controlled
IPC boundary. The latter can reduce import/lifecycle coupling and make
provider replacement easier, but it does not automatically eliminate GPL
obligations when the helper/runtime is distributed with Golden.

No legal conclusion is made here. The remaining review must cover the exact
distribution model, notices, source obligations, bundled native components,
and model/voice terms.

```text
RECOMMENDED_PROVIDER_BOUNDARY:
VoiceService -> backend-neutral TextToSpeechProvider -> Piper adapter/worker -> PCM -> AudioOutputProvider

GPL_IMPLICATIONS: architecture distinction only; not a license exemption
KNOWN_UNCERTAINTIES:
  - model/voice file-level license scope
  - provenance and license implications of the lessac base voice
  - GPL obligations for the chosen Golden distribution model
```

## Limited alternative search

The existing Faber choice was kept where possible. Three official PT-BR Piper
voices were checked, with no audio quality claim:

### Alternative 1: cadu

```text
PROVIDER: Piper
MODEL: pt_BR-cadu-medium
VOICE: cadu
PT_BR: YES
LOCAL: YES
LICENSE: repository metadata MIT
MODEL_LICENSE: NOT DOCUMENTED separately
VOICE_LICENSE: NOT DOCUMENTED separately
DATASET_LICENSE: CC0
WINDOWS: PASS_WITH_RESTRICTIONS
CPU: PASS_WITH_RESTRICTIONS
ARTIFACT_PINNABLE: YES, rhasspy/piper-voices:v1.0.0
MODEL_SIZE: 62950044 bytes
MODEL_SHA256: 765f0809a6ea9035d4a6d0d008dbf8876e68b2dd32029312672fa8f405bdb535
REUSE_VALUE: same Piper adapter and PCM contract
DECISION: BLOCKED_BY_SAME_MODEL_VOICE_LICENSE_GAP
```

### Alternative 2: jeff

```text
PROVIDER: Piper
MODEL: pt_BR-jeff-medium
VOICE: jeff
PT_BR: YES
LOCAL: YES
LICENSE: repository metadata MIT
MODEL_LICENSE: NOT DOCUMENTED separately
VOICE_LICENSE: NOT DOCUMENTED separately
DATASET_LICENSE: CC0
WINDOWS: PASS_WITH_RESTRICTIONS
CPU: PASS_WITH_RESTRICTIONS
ARTIFACT_PINNABLE: YES, rhasspy/piper-voices:v1.0.0
MODEL_SIZE: 62950044 bytes
MODEL_SHA256: 3a6f4c46355813c2b7bbc4d16b6d13d60ed72074b952a393baace82a7d0c94b5
REUSE_VALUE: same Piper adapter and PCM contract
DECISION: BLOCKED_BY_SAME_MODEL_VOICE_LICENSE_GAP
```

### Alternative 3: edresson

```text
PROVIDER: Piper
MODEL: pt_BR-edresson-low
VOICE: edresson
PT_BR: YES
LOCAL: YES
LICENSE: repository metadata MIT
MODEL_LICENSE: NOT DOCUMENTED separately
VOICE_LICENSE: NOT DOCUMENTED separately
DATASET_LICENSE: CC BY 4.0
WINDOWS: PASS_WITH_RESTRICTIONS
CPU: PASS_WITH_RESTRICTIONS
ARTIFACT_PINNABLE: YES, rhasspy/piper-voices:v1.0.0
MODEL_SIZE: 63104526 bytes
MODEL_SHA256: de4cecee38b30bb1a6378a337af605d59f0c377df702c6a6752870db8991cd84
REUSE_VALUE: same Piper adapter and PCM contract
DECISION: BLOCKED_BY_SAME_MODEL_VOICE_LICENSE_GAP
```

```text
ALTERNATIVE_SEARCH_REQUIRED: YES
ALTERNATIVE_SEARCH_RESULT: no alternative cleared the missing model/voice license scope
```

No replacement provider is selected. Edge TTS remains the existing remote
fallback and SAPI remains the machine-dependent local fallback; neither is
promoted automatically.

## Provider boundary and privacy

The provider contract remains backend-neutral:

```text
warm()
synthesize(...)
stream(...)
cancel(...)
release()
```

Golden ownership is unchanged:

```text
VOICE_SERVICE_REMAINS_OWNER: YES
TEXT_TO_SPEECH_PROVIDER_BACKEND_NEUTRAL: YES
GOLDEN_CANCELLATION_PRESERVED: YES
GOLDEN_TURN_MANAGER_PRESERVED: YES
GOLDEN_STATE_MACHINE_PRESERVED: YES
SECURITYMANAGER_PRESERVED: YES
SECOND_CORE_REQUIRED: NO
SECOND_SECURITY_MODEL_REQUIRED: NO
```

For the approved local architecture target:

```text
NETWORK_REQUIRED_DURING_INFERENCE: NO
TEXT_LEAVES_DEVICE: NO
AUDIO_LEAVES_DEVICE: NO
SECRET_REQUIRED: NO
```

If local TTS fails, future policy is `TTS_UNAVAILABLE` or an explicitly
selected fallback. It must never silently send text to Edge/cloud TTS.

## Safety and validation

```text
RUNTIME_FILES_MODIFIED: NONE
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
REAL_TTS_SYNTHESIS_EXECUTED: NO
AUDIO_PLAYBACK_STARTED: NO

TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO

SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS
```

Focused voice regression remained hardware-free. The official Golden venv
collected and passed 106 tests. Computer Use and scheduler suites were not
rerun because this gate is limited to TTS provenance and licensing.

```text
VOICE_REGRESSION: PASS (106 passed)
TEST_COLLECTION: PASS
COLLECTION_ERRORS: 0
SECURITY_COMPUTER_USE_REGRESSION: NOT_RUN_SCOPE
SCHEDULER_REGRESSION: NOT_RUN_SCOPE
```

## Final report

```text
JARVIS_VOICE_PHASE: IN_PROGRESS
TTS_BLOCKER_RESOLUTION_GATE: PASS_WITH_RESTRICTIONS
BASELINE: 3507104
RESEARCH_DATE: 2026-09-27

FABER_MODEL_REVISION: v1.0.0 / 375a0fe641dea077c2a47b4e9a056d6da521eed3
FABER_MODEL_SHA256: 858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7
FABER_CONFIG_SHA256: 7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f
PINNED_MODEL_CONFIG_PAIR_VALID: YES
CONFIG_SIZE_DISCREPANCY_EXPLAINED: YES
EXPLANATION: stale historical rhasspy/piper manifest metadata; pinned voice repo is 4855 bytes

FABER_MODEL_LICENSE: EXPLICIT repository MIT metadata; model-specific scope UNKNOWN
FABER_VOICE_LICENSE: UNKNOWN / NOT DOCUMENTED
FABER_CONFIG_LICENSE: EXPLICIT repository MIT metadata; file scope UNKNOWN
FABER_DATASET_LICENSE: EXPLICIT CC0

PERSONAL_INTERNAL_USE: NOT_CLEARED
PUBLIC_DISTRIBUTION: NOT_CLEARED
COMMERCIAL_USE: NOT_CLEARED
FABER_ARTIFACT_IDENTITY_GATE: PASS
FABER_LICENSE_GATE: BLOCKED

PIPER_RUNTIME: piper-tts
PIPER_VERSION: 1.8.0
PIPER_REVISION: 639388b6317fc4731e91d53da42aea68fd4166ff
PIPER_LICENSE: GPL-3.0-or-later
IN_PROCESS_INTEGRATION_POSSIBLE: YES_WITH_LICENSE_REVIEW
OUT_OF_PROCESS_INTEGRATION_POSSIBLE: YES_WITH_LICENSE_REVIEW

ALTERNATIVE_SEARCH_REQUIRED: YES
ALTERNATIVE_1: pt_BR-cadu-medium — blocked by same model/voice license gap
ALTERNATIVE_2: pt_BR-jeff-medium — blocked by same model/voice license gap
ALTERNATIVE_3: pt_BR-edresson-low — blocked by same model/voice license gap

SELECTED_TTS_PROVIDER: Piper
SELECTED_TTS_MODEL: pt_BR-faber-medium
SELECTED_TTS_VOICE: faber
SELECTED_RUNTIME: piper-tts
SELECTED_RUNTIME_VERSION: 1.8.0
SELECTED_MODEL_REPOSITORY: rhasspy/piper-voices
SELECTED_MODEL_REVISION: v1.0.0
MODEL_LICENSE: UNKNOWN_SCOPE
VOICE_LICENSE: UNKNOWN
RUNTIME_LICENSE: GPL-3.0-or-later

NETWORK_REQUIRED_DURING_INFERENCE: NO
TEXT_LEAVES_DEVICE: NO
AUDIO_LEAVES_DEVICE: NO
SECRET_REQUIRED: NO

DONOR_REUSE_PLAN: adapt Piper Python/worker contract, sentence chunks, bounded PCM queue, abort/flush and device recovery; preserve Golden ownership

VOICE_SERVICE_REMAINS_OWNER: YES
TEXT_TO_SPEECH_PROVIDER_BACKEND_NEUTRAL: YES
GOLDEN_CANCELLATION_PRESERVED: YES
GOLDEN_TURN_MANAGER_PRESERVED: YES
GOLDEN_STATE_MACHINE_PRESERVED: YES
SECURITYMANAGER_PRESERVED: YES
SECOND_CORE_REQUIRED: NO
SECOND_SECURITY_MODEL_REQUIRED: NO

RUNTIME_FILES_MODIFIED: NONE
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
REAL_TTS_SYNTHESIS_EXECUTED: NO
AUDIO_PLAYBACK_STARTED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO
SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS

FILES_CREATED: docs/architecture/JARVIS_TTS_LICENSE_RESOLUTION.md
FILES_MODIFIED: docs/architecture/JARVIS_TTS_LICENSE_RESOLUTION.md
COMMIT: PENDING_DOCUMENTATION_ONLY
PUSH: NO

TTS_ARTIFACT_APPROVAL: BLOCKED
READY_FOR_AUTONOMOUS_TTS_BATCH: NO
HUMAN_APPROVAL_REQUIRED_FOR_INSTALL: YES
HUMAN_APPROVAL_REQUIRED_FOR_MODEL_DOWNLOAD: YES
STOP_REASON: voice/model license scope and GPL distribution review remain unresolved
NEXT_STEP: obtain explicit licensing clearance for Faber or an approved replacement artifact
```

## Official references

- [OHF-Voice piper-tts 1.8.0](https://pypi.org/project/piper-tts/1.8.0/)
- [OHF-Voice Piper releases](https://github.com/OHF-Voice/piper1-gpl/releases)
- [Piper voices v1.0.0](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)
- [Piper voices current Faber tree](https://huggingface.co/rhasspy/piper-voices/tree/main/pt/pt_BR/faber/medium)
- [Piper voices README and repository license metadata](https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/README.md)
- [Faber model card](https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/pt/pt_BR/faber/medium/MODEL_CARD)
- [Historical Piper voice manifest](https://github.com/rhasspy/piper/blob/master/src/python_run/piper/voices.json)
- [Official Piper licensing discussion](https://github.com/rhasspy/piper/discussions/271)
- [Golden TTS artifact decision](JARVIS_TTS_ARTIFACT_DECISION.md)
