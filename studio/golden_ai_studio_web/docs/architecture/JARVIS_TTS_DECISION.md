# JARVIS TTS Provider and Voice Selection Decision

Status: `PASS_WITH_RESTRICTIONS`

Date: 2026-09-27

Scope: provider/model/voice selection only. This document does not implement a
TTS provider, install a package, download a model, open an audio device, play
audio, or run real synthesis.

## Decision summary

`Piper` is the selected local-first TTS provider for the next explicitly
approved implementation batch.

The selected voice identity is:

```text
provider: Piper
engine: Piper ONNX runtime
language: pt_BR
model: pt_BR-faber-medium
voice: faber
repository: rhasspy/piper-voices
revision: v1.0.0
artifact: pt_BR-faber-medium.onnx
sample_rate: 22050 Hz
speakers: 1
```

This is an architectural selection, not an artifact approval. The model is not
present on this machine, the Piper package is not installed, and the exact
runtime package version has not been selected. The next batch must therefore
stop before download or synthesis until the package, artifact checksum, model
card, and license record are approved together.

The current Golden Edge TTS path remains the operational fallback until a
Piper batch is completed. It is not silently replaced by this document.

## Baselines and ownership

The decision was made against these project baselines:

| Baseline | Commit |
| --- | --- |
| Local STT integration | `e815107` |
| Controlled PT-BR STT benchmark | `740d399` |
| Voice donor audit 2 | `d74d3ba` |

The runtime ownership boundary remains:

```text
VoiceService -> TTS provider adapter -> AudioPlayer -> Windows output
```

There is one JARVIS, one Core, one `VoiceService`, one active turn owner, and
one `SecurityManager`. A provider must never create a second voice loop, call
Core directly, bypass `SecurityManager`, or own an independent speaker path.

The existing `VoiceService`, `TurnManager`, output epoch, cancellation, and
barge-in authorities remain the owners of lifecycle and turn semantics. The
reuse classifications from `JARVIS_VOICE_DONOR_AUDIT_2.md` are preserved:

```text
TTS_PROVIDER: ADAPT
AUDIO_OUTPUT: ADAPT
PLAYBACK_QUEUE: ADAPT
TTS_CANCELLATION: KEEP_OURS
PLAYBACK_CANCELLATION: ADAPT
TURN_TAKING: KEEP_OURS
BARGE_IN: KEEP_OURS
ECHO_HANDLING: REIMPLEMENT_PATTERN
DEVICE_RECOVERY: ADAPT
```

## Candidate audit

Three serious candidates were compared. No candidate was installed or
executed during this gate.

### Candidate A: Piper

| Field | Result |
| --- | --- |
| Candidate status | `SELECTED_PRIMARY_LOCAL` |
| Provider type | Local/offline |
| Package | `piper-tts`, exact version `UNMEASURED` and not installed |
| Runtime | Piper ONNX runtime; exact runtime package lock `UNMEASURED` |
| PT-BR support | `PASS`; official voice manifest lists `pt_BR-faber-medium` |
| Exact model | `pt_BR-faber-medium` |
| Exact voice | `faber`, one speaker |
| Artifact format | ONNX model plus JSON config and model card |
| Artifact revision | `rhasspy/piper-voices:v1.0.0` |
| Artifact size | 63,201,294 bytes for the ONNX model in the official manifest |
| Artifact integrity | Official manifest MD5: `e0724a2f07965f6523d2a1e96b488a4c` |
| Output metadata | 22,050 Hz, one speaker, medium quality |
| Local artifact found | `NO` |
| CPU/Windows | `PASS_WITH_RESTRICTIONS`; no local run has been measured |
| Python 3.13 | `UNMEASURED`; package compatibility gate remains open |
| Streaming | `ADAPT`; normalize provider output behind the existing queue; do not assume native incremental streaming |
| Cancellation | `ADAPT`; retain Golden turn cancellation and output epoch; use provider stop only as an implementation detail |
| License | Piper repository metadata is MIT; the voice model card identifies the dataset as CC0. This is not a legal clearance for redistribution or commercial use |
| Privacy | Local inference target; text and audio should remain on-device after artifact acquisition |
| Download | Required, separately authorized; implicit download is prohibited |

The official Piper voice manifest identifies the exact locale, model path,
size, and checksum. The model card identifies `pt_BR`, 22,050 Hz, one speaker,
medium quality, and a CC0 dataset. The Piper repository is archived, so the
implementation batch must pin the package and artifact rather than follow an
unbounded moving branch.

### Candidate B: existing Edge TTS

| Field | Result |
| --- | --- |
| Candidate status | `EXISTING_FALLBACK` |
| Provider type | Remote hosted service |
| Package | `edge-tts==7.2.8` already installed |
| Exact voice | `pt-BR-FranciscaNeural` |
| PT-BR support | `PASS`; Microsoft lists the voice under Portuguese (Brazil) |
| Model/artifact | Hosted and undisclosed; no local model identity or revision |
| Output | MP3; sample rate `UNMEASURED` |
| Current path | `jarvis_core/voice_service.py` and `jarvis_core/streaming/tts_pipeline.py` |
| Streaming shape | Sentence-level collection followed by playback, not end-to-end provider-to-speaker streaming |
| Cancellation | Existing cancellation stops collection/turn work; provider abort semantics remain limited |
| Windows/CPU | `PASS`; current WPF `MediaPlayer` path is already present |
| Privacy | Response text leaves the machine; no raw microphone upload is implied by this TTS path |
| License/terms | Service and voice terms must be reviewed at runtime/product deployment; hosted voice is not a redistributable local artifact |
| Role | Keep as current fallback until local Piper is separately approved |

Edge TTS is a good compatibility fallback and already fits the Golden output
path, but it does not meet the local-first artifact requirement. Voice names and
hosted service behavior can change independently of the repository. The
current implementation is therefore treated as an existing remote provider,
not as the selected local model.

### Candidate C: Windows SAPI / pywin32

| Field | Result |
| --- | --- |
| Candidate status | `MACHINE_FALLBACK_ONLY` |
| Provider type | Local Windows platform speech |
| Package | `pywin32==312` already installed; `pyttsx3` is not installed |
| PT-BR support | `MACHINE_PASS`; this Windows image exposes Microsoft Daniel/Maria Portuguese (Brazil) voices |
| Exact voice | Machine-dependent; no stable artifact identity |
| Model/artifact | Installed Windows voice token; no project-controlled model artifact |
| CPU/Windows | `PASS` as a platform capability |
| Python 3.13 | `PASS` for the installed `pywin32` package; real TTS was not executed |
| Streaming | `FAIL_FOR_PRIMARY`; `SpVoice.Speak` is a synchronous/queued platform call, not a normalized PCM stream |
| Cancellation | `RESTRICTED`; retain as a last-resort fallback because speech ownership and interruption are platform-coupled |
| Privacy | Local; no provider upload |
| Role | Keep as a fallback option only; do not select as the primary provider |

Microsoft documents `SpVoice.Speak` as a synchronous or asynchronous speech
operation with its own queue. That makes it useful as a machine fallback, but
not a good fit for Golden's independently cancellable provider/output
contracts.

## Selected provider gate

```text
SELECTED_TTS_PROVIDER: Piper
SELECTED_TTS_PROVIDER_TYPE: LOCAL_OFFLINE
SELECTED_TTS_PACKAGE: piper-tts
SELECTED_TTS_PACKAGE_VERSION: UNMEASURED_NOT_INSTALLED
SELECTED_TTS_RUNTIME: Piper ONNX
SELECTED_TTS_MODEL: pt_BR-faber-medium
SELECTED_TTS_VOICE: faber
SELECTED_TTS_LANGUAGE: pt_BR
SELECTED_MODEL_REPOSITORY: rhasspy/piper-voices
SELECTED_MODEL_REVISION: v1.0.0
SELECTED_MODEL_FORMAT: ONNX
SELECTED_MODEL_PATH: pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx
SELECTED_MODEL_SAMPLE_RATE: 22050
SELECTED_MODEL_SIZE_BYTES: 63201294
SELECTED_MODEL_MD5: e0724a2f07965f6523d2a1e96b488a4c
LOCAL_MODEL_FOUND: NO
MODEL_DOWNLOAD_REQUIRED: YES
IMPLICIT_MODEL_DOWNLOAD_ALLOWED: NO
PT_BR_SUPPORTED: YES
CPU_COMPATIBILITY: PASS_WITH_RESTRICTIONS
WINDOWS_COMPATIBILITY: PASS_WITH_RESTRICTIONS
PYTHON_3_13_COMPATIBILITY: UNMEASURED
LICENSE_GATE: PASS_WITH_RESTRICTIONS
ARTIFACT_GATE: BLOCKED_PENDING_APPROVAL
READY_FOR_AUTONOMOUS_TTS_BATCH: NO
```

`PASS_WITH_RESTRICTIONS` is intentional. The provider identity and exact
PT-BR model are sufficiently grounded for architecture, but autonomous work
cannot start until package version, download source, checksum verification,
model card, and redistribution terms are recorded. No model or package is
implicitly acquired by this decision.

## Reuse and adaptation plan

The next implementation batch, after approval, should be narrow:

1. Add a Golden-owned provider adapter behind `VoiceService` and the existing
   `TextToSpeechProvider` boundary. Do not copy a donor provider wholesale.
2. Preserve `VoiceService` as the only voice runtime owner and preserve the
   existing `TurnManager`, session identity, cancellation epoch, stale-result
   suppression, and barge-in authority.
3. Normalize Piper output into the existing audio pipeline. The provider must
   not call Windows speakers directly.
4. Use one bounded playback queue with ordered response ownership, explicit
   flush/drain on cancellation, and no late audio from an old turn.
5. Adapt the donor A `RawOutputStream.abort()` and queue-drain idea only if it
   fits the existing `AudioPlayer`; it does not authorize importing donor
   state machines or a second audio owner.
6. Keep Edge TTS and SAPI behind explicit fallback policy. A fallback must be
   observable in `TTS_OWNER` and must not create a second VoiceService.

The output boundary should eventually expose enough metadata for tests and
telemetry to distinguish provider synthesis, playback start, cancellation,
device recovery, and final completion. The current gate does not add those
fields.

## Privacy, security, and secrets

| Concern | Decision |
| --- | --- |
| Local Piper text | Remains on device after model acquisition |
| Edge fallback text | Leaves device to the hosted service |
| SAPI text | Remains on device |
| Microphone audio | Not touched by this gate |
| API keys | No key is required or added for the selected local provider |
| SecurityManager | Remains the only authorization boundary |
| Downloads | Must be explicit, allowlisted, checksum-verified, and audited |
| Cache | Use a dedicated model cache; no silent startup download |
| Logs | Do not log full response text or secrets merely to identify TTS |
| Audio files | No new persistence policy is introduced; current temporary-file cleanup remains in force |

## Machine and environment evidence

Read-only inspection on 2026-09-27:

```text
Python: 3.13.15, 64-bit Windows environment
edge-tts: 7.2.8
pywin32: 312
sounddevice: 0.5.6
onnxruntime: 1.29.0
numpy: 2.5.2
piper/piper-tts: NOT INSTALLED
pyttsx3: NOT INSTALLED
soundfile: NOT INSTALLED
Piper model cache: NOT FOUND in inspected project/user cache locations
```

Windows exposes Portuguese (Brazil) SAPI voices named Microsoft Daniel and
Microsoft Maria. This proves only machine availability, not a stable voice
artifact or quality result.

Performance, RAM, first-token latency, end-to-end latency, real synthesis
quality, and device playback behavior are deliberately:

```text
UNMEASURED
```

No inference should be drawn from the absence of measurements.

## Required gates before implementation

The next autonomous TTS batch is allowed only after all of these are complete:

1. Approve an exact `piper-tts` package version compatible with Python 3.13
   and Windows, and record its lock/hash source.
2. Approve the official `rhasspy/piper-voices` `v1.0.0` artifact source.
3. Download only after explicit approval into a dedicated cache; do not put
   model files in the source tree, `build`, or `dist`.
4. Verify model size, checksum, config, and model card before loading.
5. Record the engine license, model repository license, model-card dataset
   license, and redistribution decision separately.
6. Run a hardware-free PT-BR synthesis/quality smoke test before any speaker
   test. The test must not silently fall back to Edge or SAPI.
7. Add cancellation, stale-turn, queue ordering, playback ownership, and
   device recovery tests before enabling the provider in runtime policy.
8. Only then request an explicitly authorized real audio/output gate.

Until then:

```text
READY_FOR_AUTONOMOUS_TTS_BATCH: NO
```

## Safety and change boundary

```text
RUNTIME_FILES_MODIFIED: NONE
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
AUDIO_PLAYBACK_STARTED: NO
REAL_TTS_SYNTHESIS_EXECUTED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO
```

Only this documentation file is intended to be committed for this gate. No
donor code, runtime code, dependency manifest, model, credential, database,
log, build output, or distribution output belongs in the change.

## Official references

- Piper voice manifest and exact `pt_BR-faber-medium` artifact metadata:
  [Piper voices.json](https://github.com/rhasspy/piper/blob/master/src/python_run/piper/voices.json)
- Exact Piper `faber` model card at the pinned revision:
  [pt/pt_BR/faber/medium/MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/v1.0.0/pt/pt_BR/faber/medium/MODEL_CARD)
- Piper source and archive status:
  [rhasspy/piper](https://github.com/rhasspy/piper)
- Existing remote TTS client:
  [rany2/edge-tts](https://github.com/rany2/edge-tts)
- Microsoft PT-BR voice catalog:
  [Azure Speech language and voice support](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=pronunciation-assessment)
- Windows SAPI `SpVoice.Speak` contract:
  [Microsoft Speech API documentation](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ms723609(v=vs.85))
- Local Golden ownership and reuse findings:
  [JARVIS Voice Donor Audit 2](JARVIS_VOICE_DONOR_AUDIT_2.md)

## Gate report

```text
DECISION: PASS_WITH_RESTRICTIONS
SELECTED_PROVIDER: Piper
SELECTED_MODEL: pt_BR-faber-medium
SELECTED_VOICE: faber
LOCAL_ARTIFACT_PRESENT: NO
PACKAGE_PRESENT: NO
MODEL_DOWNLOAD_APPROVED: NO
LICENSE_FULLY_CLEARED: NO
READY_FOR_AUTONOMOUS_TTS_BATCH: NO
```
