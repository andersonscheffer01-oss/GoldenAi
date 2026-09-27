# Jarvis Real Audio and Wake Provider Decision

Status: `BATCH-02A IMPLEMENTED`  
Runtime scope: audio input boundary only; acoustic wake remains deferred.

This record audits the existing Golden/Jarvis voice paths, records the Batch
02A implementation, and defines the remaining acoustic-wake gate. Batch 02A
declares the existing backend, adds the provider boundary, and validates it
with fake frames. It does not download a model or activate continuous boot
listening.

## Baseline and evidence

- `VoiceService` is the only approved voice runtime owner.
- `SileroVADAdapter`, `HybridEndpoint`, `AudioFrameQueue`,
  `RealtimeVoicePipeline`, and `WakeLifecycle` already exist and were covered
  by Autonomous Batch 01.
- `AudioFrameQueue` is bounded at 32 frames and drops the oldest frame on
  overflow. Its canonical frame is 16 kHz, mono, signed 16-bit PCM, 480
  samples, or 960 bytes, representing 30 ms.
- `JarvisVoice.record_from_microphone()` and
  `JarvisVoice.record_until_silence()` currently use lazy `sounddevice`
  capture. Legacy barge-in monitor and follow-up paths in `VoiceService` also
  open `sounddevice.InputStream` directly.
- `RealtimeVoicePipeline` currently accepts frames from its caller; it does
  not own a hardware device.
- The current wake detector is text-level: `JarvisVoice.detect_wake_word()`
  checks the transcript for `Jarvis`. No acoustic wake detector provider is
  present in Golden.
- Donor Audit 1B classifies donor audio protocols and device lifecycle as
  `ADAPT`, the donor pipeline as `REIMPLEMENT_PATTERN`, and donor wake as
  `ADAPT` behind Golden ownership. No donor source is copied.

## Existing implementation classification

| Surface | Evidence | Classification | Decision |
| --- | --- | --- | --- |
| Legacy microphone capture | `voice.py` uses `sounddevice.rec` and blocking `InputStream` | `ADAPT_EXISTING` | Consolidate behind one provider in Batch 02 |
| Realtime frame path | `AudioFrameQueue` and `RealtimeVoicePipeline` | `KEEP_OURS` | Reuse unchanged as the consumer boundary |
| VAD | `SileroVADAdapter` and `HybridEndpoint` | `KEEP_OURS` | Reuse the existing 16 kHz PCM contract |
| Wake lifecycle | `WakeLifecycle` plus canonical `VoiceStateMachine` | `KEEP_OURS` | Detector emits events; lifecycle owns activation identity |
| Acoustic wake detector | No Golden implementation found | `DEFER` | Human/provider decision required |
| PyAudio | No Golden implementation or wrapper found | `REJECT` | Would add a competing capture backend |

## Audio architecture decision

`MICROPHONE_OWNER: VoiceService`

`AUDIO_PROVIDER_BOUNDARY: AudioInputProvider`

The future provider is a narrow hardware boundary owned and started/stopped by
`VoiceService`. It may use a callback or blocking reader internally, but its
only output is timestamped, sequenced PCM frames delivered to the existing
bounded queue. It must not call Core, an LLM, tools, SecurityManager,
TaskDatabase, or the wake lifecycle.

`SELECTED_AUDIO_PROVIDER: ADAPT_EXISTING (sounddevice backend)`

This is now implemented as the Batch 02A provider boundary. The repository
already used `sounddevice`, the existing `.venv` contains `sounddevice 0.5.6`,
and the canonical `C:\GoldenAI\requirements.txt` now declares the exact
installed version. The provider is lazy-imported and is started only by an
explicit VoiceService call.

The target is exactly one active `InputStream` or `RawInputStream` for the
VoiceService. The callback/read boundary performs capture, monotonic
timestamp/sequence assignment, and bounded enqueue only. Wake and VAD are
consumers of that same frame fan-out. They do not open separate streams.

`AUDIO_FALLBACK: system default device, with future explicit device selection`

Device IDs must not be written to `device_registry.json` by this phase. Device
enumeration and disconnected-device recovery remain Batch 02 work.

### Frame and queue contract

| Field | Decision |
| --- | --- |
| Sample rate | 16,000 Hz |
| Channels | 1, mono |
| Format | signed 16-bit PCM, little-endian bytes at the Python boundary |
| Frame duration | 30 ms, 480 samples, 960 bytes |
| Timestamp | monotonic capture timestamp for diagnostics/lifecycle only |
| Sequence | provider-local monotonic sequence for loss/ordering diagnostics |
| Queue | existing bounded `AudioFrameQueue`, max 32 frames |
| Overflow | drop oldest frame and increment/emit a diagnostic counter |
| Persistence | no raw frame persistence |

PortAudio is the native backend implication of `sounddevice`; the future
Windows package check must validate the pinned wheel, architecture, bundled
PortAudio component, and installed device drivers. The provider must still
fail closed on missing permissions/device errors without taking down Core.

The official `sounddevice` documentation exposes both callback and blocking
input-stream APIs, including `RawInputStream`; the existing code's use of
`InputStream` is therefore reusable behind this boundary, but its current
direct ownership is not the final architecture.

## Wake architecture decision

`WAKE_PROVIDER_BOUNDARY: WakeDetectorProvider`

The provider consumes frames from the single capture fan-out and emits a
candidate activation event containing the current session identity, provider
sequence, and monotonic observation time. It never creates a `VoiceSession`,
calls Core, or grants approval. `WakeLifecycle` remains the sole activation
authority.

`SELECTED_WAKE_PROVIDER: DEFERRED_PENDING_HUMAN_DECISION`

No acoustic provider is installed or selected in this gate. The existing
transcript-level `Jarvis` check remains the current fallback path and is not a
real wake detector.

The primary audited candidate is openWakeWord because Donor Audit 1B already
classifies the donor wake pattern as `ADAPT`, and its documented input is
16-bit 16 kHz PCM. However, the repository's included models are documented
as CC BY-NC-SA 4.0, while the code is Apache 2.0; the exact custom `Jarvis`
model, model source, and distribution terms still require an explicit review.
Porcupine supports Windows and local frame processing, but its official setup
requires a Picovoice AccessKey and its licensing/procurement terms are not
cleared for this project. Neither option is installed or downloaded here.

`WAKE_PROVIDER_LICENSE_GATE: RESTRICTION`

`MODEL_REQUIRED: YES for any acoustic provider`  
`MODEL_SOURCE: UNSELECTED`  
`MODEL_SIZE: UNKNOWN until provider/model approval`  
`MODEL_LICENSE: REQUIRES PROVIDER-SPECIFIC REVIEW`

`CUSTOM_JARVIS_WAKE_SUPPORTED: PARTIAL`

openWakeWord documents a pre-trained "hey jarvis" model and a custom-model
workflow, but that is not evidence that the exact desired phrase and model
terms are cleared for this project.

`CONTINUOUS_AUDIO_TO_CLOUD_FOR_WAKE: NO`

### Recommended ordering

```text
one physical microphone stream
        |
        v
AudioInputProvider
        |
        v
bounded frame fan-out
        +-- WakeDetectorProvider
        +-- VAD / RealtimeVoicePipeline after activation
                         |
                         v
                   WakeLifecycle
                         |
                         v
                    VoiceService
                         |
                         v
                    VoiceSession
```

Wake and VAD share frames from the same capture. VAD does not become an
approval mechanism, and wake detection does not authorize privileged work.

## Privacy, failure, and lifecycle requirements

- `RAW_AUDIO_PERSISTENCE_POLICY: NEVER_BY_DEFAULT`
- `MICROPHONE_CONTINUOUS_LISTENING_ENABLED: NO` in this gate.
- Audio remains in volatile memory and is discarded after the consumer is
  complete; no WAV/debug archive or Voice database is introduced.
- `MICROPHONE_FAILURE_ISOLATED: REQUIRED_BY_PROVIDER_BOUNDARY`
- `WAKE_PROVIDER_FAILURE_ISOLATED: REQUIRED_BY_PROVIDER_BOUNDARY`
- Existing cancellation, VAD reset, WakeLifecycle cancellation, and restart
  contracts are compatible and remain the source of truth.

The future shutdown order is:

```text
VoiceService stop
  -> stop provider callback/read loop
  -> close the native stream
  -> cancel and flush AudioFrameQueue
  -> unload/reset VAD and WakeLifecycle
  -> finish VoiceSession shutdown
```

No forced process/thread kill is part of the design. Device startup failure or
disconnect should emit a sanitized structural audit/health event, leave Core
alive, and require explicit retry or device selection. Automatic device-ID
persistence and recovery are deferred.

## Batch 02A result and remaining dependency plan

### COMPLETED_IN_BATCH_02A

- `sounddevice==0.5.6` declared in the canonical requirements file.
- `AudioInputProvider` implemented with lazy import, one stream, bounded queue,
  diagnostics, controlled device errors, and idempotent lifecycle.
- `FakeAudioInputProvider` added for hardware-free tests.
- VoiceService explicit start/stop/restart integration added without boot
  autostart.

### REQUIRED_NEXT

- Optional short Windows hardware smoke, with no recording or persistence.
- Explicit device selection and disconnected-device recovery.
- Human approval of an acoustic wake provider, model, and license.

### OPTIONAL_LATER

- An approved openWakeWord package/model after license and model provenance
  review.
- A different local wake provider only after an explicit human decision.

### REJECTED_DEPENDENCIES

- PyAudio as a second capture backend.
- Porcupine before AccessKey/licensing approval.
- Any Torch/TensorFlow/large wake runtime or unreviewed model download.
- Donor runtime/code, a second voice loop, or a second microphone stream.

## Task, security, and database checks

- Existing `SecurityManager`, approval model, and `AuditLog` remain the only
  authorities.
- No second Core, LLM loop, security model, task system, Voice database, or
  IPC is added.
- `TASK_DB_SCHEMA_MIGRATION: NONE`.
- `TASK_DB_SCHEMA_VERSION: 5`.
- Read-only resolution confirmed:
  `C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db`.
- `CANONICAL_TASK_DB_MATCH: PASS`; the database was opened read-only only for
  the schema check and was not modified.
- `DEVICE_REGISTRY_TOUCHED: NO`.

## Batch 02A readiness

`REAL_AUDIO_ARCHITECTURE_DECIDED: YES`  
`WAKE_PROVIDER_STRATEGY_DECIDED: NO, PROVIDER/MODEL HUMAN GATE PENDING`  
`DEPENDENCY_PLAN_COMPLETE: PASS_WITH_RESTRICTIONS`  
`READY_FOR_ACOUSTIC_WAKE_DECISION: YES`  
`READY_FOR_AUTONOMOUS_BATCH_02: NO`

The real-audio boundary is implemented and ready for optional hardware review.
The overall voice batch is not marked ready for acoustic implementation
because the wake provider, model, and license gate remain unresolved.

## Next proposal: acoustic wake gate

This is a proposal only; it was not executed by Batch 02A.

### Phase 1 - Approved Local Wake Provider

Only after human approval of provider, model, phrase, license, and dependency
pinning. Feed the same provider frames into the existing `WakeLifecycle`; add
stale, duplicate, threshold, false-positive fixture, and failure-isolation
tests. No cloud audio and no automatic model download.

### Phase 2 - Real Audio + Wake + VAD E2E

Run an explicitly optional Windows hardware smoke test, then validate one
stream, wake activation, VAD endpointing, VoiceService cancellation/shutdown,
restart, no raw persistence, and Core/security isolation. The normal suite
must remain hardware-free.

## Sources and provenance

- Golden source of truth: `JARVIS_DONOR_AUDIT_1B.md`,
  `JARVIS_VOICE_ARCHITECTURE.md`, and `REUSE_FIRST_POLICY.md`.
- `python-sounddevice` official documentation: callback, blocking, and raw
  input stream APIs.
- `sounddevice` PyPI metadata: MIT package license and Windows wheels.
- `openWakeWord` official repository: Apache-2.0 code, documented 16 kHz PCM
  input, and CC BY-NC-SA 4.0 included pre-trained models.
- Picovoice official Porcupine Python quick start: Windows support and
  AccessKey requirement.

No donor code was copied. Batch 02A did not modify `device_registry.json`, the
canonical task database, or any raw-audio file.
