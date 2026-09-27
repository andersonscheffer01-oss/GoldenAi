# Jarvis Acoustic Wake Provider and License Decision Gate

Status: `PASS_WITH_RESTRICTIONS`
Research date: `2026-09-27`
Scope: provider, model, license, compatibility, and architecture decision only.

No acoustic wake package was installed, no model was downloaded, and no
microphone was opened for this gate.

## Decision summary

`SELECTED_WAKE_PROVIDER: DEFERRED`

`SELECTED_WAKE_MODEL: DEFERRED`

`LICENSE_GATE: BLOCKED_PENDING_PROVIDER_AND_MODEL_APPROVAL`

The current evidence is sufficient to define the integration boundary, but not
to authorize an implementation or redistribution choice. openWakeWord is the
best architectural fit for a local, no-credential path, but its bundled
pre-trained models are documented as CC BY-NC-SA 4.0 and the exact model
provenance for a commercial/public Jarvis distribution is not cleared.
Porcupine is a technically strong Windows option, but its official setup
requires a Picovoice account and secret AccessKey, and its proprietary service
terms and distribution plan have not been approved.

Therefore this gate does not select a provider. `READY_FOR_AUTONOMOUS_BATCH_02B`
is `NO` until a human approves a provider, a specific model/keyword artifact,
its license, and the dependency pinning.

## Golden baseline

- `MICROPHONE_OWNER: VoiceService`
- `AUDIO_INPUT_PROVIDER: AudioInputProvider`
- `CAPTURE_STREAM: one sounddevice.RawInputStream`
- `FRAME_CONTRACT: 16000 Hz, mono, signed 16-bit PCM, 480 samples, 960 bytes, 30 ms`
- `QUEUE: bounded AudioFrameQueue, max 32, DROP_OLDEST`
- `EXISTING_WAKE_LIFECYCLE_REUSED: YES`
- `EXISTING_GOLDEN_ACOUSTIC_WAKE: NONE`
- `EXISTING_WAKE_FALLBACK: transcript-level JarvisVoice.detect_wake_word()`
- `SINGLE_CAPTURE_STREAM_PRESERVED: YES`

The donor wake implementation is not copied. The current Golden wake check is
text-level and is not treated as an acoustic provider.

## Candidate: openWakeWord

`OPENWAKEWORD_CURRENT_STATUS: ACTIVE_OPEN_SOURCE_CANDIDATE`

- `CODE_LICENSE: Apache-2.0`
- `BUNDLED_MODEL_LICENSE: CC BY-NC-SA 4.0, as stated by the official repository`
- `CUSTOM_MODEL_LICENSE: NOT AUTOMATICALLY CLEARED; depends on training data,
  source assets, and the chosen distribution terms`
- `PERSONAL_LOCAL_USE: code is permissive; bundled model remains subject to
  CC BY-NC-SA attribution/non-commercial/share-alike terms`
- `PRIVATE_INTERNAL_USE: likely compatible for non-commercial internal use,
  subject to the model terms; legal/provenance review remains required`
- `PUBLIC_DISTRIBUTION: not cleared for bundled models because of the
  non-commercial/share-alike terms`
- `COMMERCIAL_DISTRIBUTION: not cleared for bundled models; separate model
  provenance/licensing is required`
- `JARVIS_PRETRAINED_MODEL_STATUS: official repository lists a "hey jarvis"
  model; this is not proof of an exact standalone "Jarvis" artifact`
- `CUSTOM_JARVIS_MODEL_REQUIRED: YES if the exact phrase or approved artifact
  is not accepted`
- `RUNTIME_DEPENDENCIES: openWakeWord runtime plus NumPy and its selected local
  inference backend/model assets; exact package set must be pinned after approval`
- `TRAINING_DEPENDENCIES: materially heavier than runtime, including the
  official training workflow dependencies; training is out of scope`
- `WINDOWS_COMPATIBILITY: not rejected; Windows-specific packaging and chosen
  inference wheels must be verified before installation`
- `PYTHON_COMPATIBILITY: not pinned for Golden by this gate; verify the exact
  package release against the project Python before install`
- `INPUT_SAMPLE_RATE: 16000 Hz`
- `INPUT_FORMAT: 16-bit PCM`
- `REQUIRED_FRAME_SIZE: official README recommends multiples of 80 ms; exact
  model call size is model/runtime dependent`
- `FRAME_ADAPTATION_REQUIRED: YES; aggregate the canonical 30 ms frames into
  an accepted 80 ms multiple or other documented provider size`
- `OFFLINE_INFERENCE: YES, when local model/runtime assets are installed`
- `CONTINUOUS_AUDIO_TO_CLOUD: NO`
- `SECOND_MICROPHONE_STREAM_REQUIRED: NO`
- `MODEL_SIZE: NOT ESTABLISHED; varies by model/backend and was not downloaded`
- `MODEL_PROVENANCE_REQUIREMENTS: retain the exact artifact identity, source,
  license, attribution, training-data restrictions, and redistribution decision`
- `OPENWAKEWORD_LICENSE_GATE: RESTRICTED/BLOCKED_PENDING_MODEL_CLEARANCE`

The official README also exposes a model download helper. It was not called in
this phase.

## Candidate: Porcupine

`PORCUPINE_CURRENT_STATUS: ACTIVE_PROPRIETARY_CANDIDATE`

- `SDK_LICENSE: proprietary Picovoice service terms; project distribution
  rights and plan are not approved`
- `MODEL_LICENSE: provider-specific; exact downloaded model terms were not
  obtained or approved`
- `CUSTOM_KEYWORD_LICENSE: provider-specific Console/API terms; not approved`
- `PERSONAL_LOCAL_USE: requires a valid AccessKey and applicable terms`
- `PRIVATE_INTERNAL_USE: requires a valid AccessKey and applicable terms`
- `PUBLIC_DISTRIBUTION: not cleared; AccessKey handling and redistribution
  terms require an explicit product/licensing decision`
- `COMMERCIAL_DISTRIBUTION: not cleared; commercial agreement/plan may apply`
- `ACCESSKEY_REQUIRED: YES`
- `ACCOUNT_REQUIRED: YES, according to the official quick start`
- `INTERNET_REQUIRED_AT_RUNTIME: NOT ESTABLISHED by this gate; the official
  docs establish AccessKey authorization, not a permission to assume offline
  operation under every deployment condition`
- `SECRET_REQUIRED: YES; AccessKey must remain secret`
- `JARVIS_PREBUILT_STATUS: official examples list built-in keywords, not Jarvis`
- `CUSTOM_JARVIS_KEYWORD_REQUIRED: YES for an approved Jarvis phrase`
- `WINDOWS_COMPATIBILITY: YES; official docs list Windows x86_64 and arm64`
- `PYTHON_COMPATIBILITY: YES for Python 3.9+ per the official quick start`
- `INPUT_SAMPLE_RATE: provider-defined; read from the instantiated engine`
- `INPUT_FORMAT: 16-bit linear PCM, single-channel`
- `REQUIRED_FRAME_SIZE: Porcupine.frame_length at runtime`
- `FRAME_ADAPTATION_REQUIRED: YES; the 480-sample Golden frame must be
  reframed to the engine's reported frame length`
- `OFFLINE_INFERENCE: local frame processing is documented, but deployment
  authorization/runtime connectivity requirements remain unresolved`
- `CONTINUOUS_AUDIO_TO_CLOUD: NO evidence in the frame-processing API of
  continuous raw-audio upload; do not infer broader service terms`
- `SECOND_MICROPHONE_STREAM_REQUIRED: NO`
- `PORCUPINE_LICENSE_GATE: RESTRICTED/BLOCKED_PENDING_ACCESSKEY_AND_TERMS`

No AccessKey was requested, created, stored, or used.

## Optional third candidate

`THIRD_CANDIDATE: NONE`

`REASON_INCLUDED: NONE`

No third candidate was included because no additional option was found in the
current audit that was simultaneously as well-supported for local Windows /
Python / single-stream PCM integration and sufficiently clear on model and
distribution licensing. Adding a name without clearing those gates would add
noise rather than evidence.

## Factual comparison

- `LICENSE_COMPARISON: openWakeWord code is Apache-2.0 but bundled models are
  CC BY-NC-SA 4.0; Porcupine is proprietary and requires provider terms`
- `CUSTOM_JARVIS_COMPARISON: openWakeWord supports a custom-model workflow;
  Porcupine supports custom keywords through Console/API; neither artifact is
  approved here`
- `PRIVACY_COMPARISON: both can process local frames without a second capture
  stream; openWakeWord has no AccessKey path, while Porcupine requires one`
- `DEPENDENCY_COMPARISON: openWakeWord runtime/model backend must be pinned;
  Porcupine needs its SDK/native runtime and keyword/model artifacts`
- `WINDOWS_COMPARISON: Porcupine explicitly documents Windows x86_64/arm64;
  openWakeWord requires package/backend verification in Golden`
- `FRAME_COMPATIBILITY_COMPARISON: both need an adapter from 30 ms/480 samples;
  openWakeWord recommends 80 ms multiples, Porcupine exposes frame_length`
- `CREDENTIAL_COMPARISON: openWakeWord no credential identified; Porcupine
  AccessKey is mandatory and secret`
- `DISTRIBUTION_COMPARISON: openWakeWord bundled model restrictions are
  explicit; Porcupine distribution rights remain provider-plan dependent`

## Architecture contract for a future implementation

```text
one physical microphone stream
        |
        v
AudioInputProvider
        |
        v
bounded frame fan-out
        +-- FrameAdapter -> WakeDetectorProvider
        +-- VAD / RealtimeVoicePipeline
                         |
                         v
                    WakeLifecycle
                         |
                         v
                    VoiceService
```

- `WAKE_PROVIDER_BOUNDARY: WakeDetectorProvider`
- `WAKE_PROVIDER_METHODS: start, reset, process_frame, activation event, close`
- `FRAME_ADAPTER_REQUIRED: YES`
- `FRAME_ADAPTER_STRATEGY: consume ordered 30 ms frames, aggregate/reframe in
  volatile memory to the selected engine contract, preserve timestamps and
  sequence diagnostics, and never open a device`
- `WAKE_VAD_ORDER: wake candidate first; after WakeLifecycle activation, feed
  the same fan-out to the existing VAD/endpoint path`
- `SINGLE_CAPTURE_FANOUT: YES`
- `RAW_AUDIO_PERSISTENCE_REQUIRED: NO`
- `CONTINUOUS_AUDIO_TO_CLOUD_FOR_WAKE: NO`
- `WAKE_PROVIDER_FAILURE_POLICY: disable acoustic wake, emit sanitized health /
  AuditLog diagnostics, keep Core alive, and retain text/manual fallback`
- `TEXT_MANUAL_WAKE_FALLBACK: YES`
- `EXISTING_SECURITYMANAGER_REUSED: YES`
- `EXISTING_APPROVAL_MODEL_PRESERVED: YES`
- `STALE_DUPLICATE_PROTECTION: preserve WakeLifecycle session/activation checks;
  a detector event never grants privileged authorization`

## Safety and regression gate

```yaml
RUNTIME_FILES_MODIFIED: NONE
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
MICROPHONE_OPENED: NO
AUDIO_RECORDED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO
```

The canonical task database was not changed. The runtime remains hardware-free
for this gate.

## Decision

```yaml
ACOUSTIC_WAKE_DECISION_GATE: PASS_WITH_RESTRICTIONS
SELECTED_WAKE_PROVIDER: DEFERRED
SELECTED_WAKE_MODEL: DEFERRED
MODEL_SOURCE: DEFERRED
MODEL_LICENSE: PENDING_PROVIDER_SPECIFIC_REVIEW
MODEL_DOWNLOAD_REQUIRED: YES_FOR_ANY_IMPLEMENTATION
LICENSE_GATE: BLOCKED_PENDING_APPROVAL
PRIVACY_GATE: PASS_WITH_RESTRICTIONS
DEPENDENCY_GATE: PASS_WITH_RESTRICTIONS
WINDOWS_GATE: PASS_WITH_RESTRICTIONS
SINGLE_STREAM_GATE: PASS
HUMAN_APPROVAL_REQUIRED_BEFORE_INSTALL: YES
READY_FOR_AUTONOMOUS_BATCH_02B: NO
```

## Official sources

- openWakeWord repository and README: https://github.com/dscripka/openWakeWord
- openWakeWord model-download implementation: https://github.com/dscripka/openWakeWord/blob/main/openwakeword/utils.py
- Porcupine Python quick start: https://picovoice.ai/docs/quick-start/porcupine-python/
- Porcupine Python API (`frame_length`, `sample_rate`, `process`): https://picovoice.ai/docs/api/porcupine-python/
- Porcupine Windows support: https://picovoice.ai/docs/quick-start/porcupine-windows/
- Picovoice terms of use: https://picovoice.ai/docs/terms-of-use/
- python-sounddevice documentation: https://python-sounddevice.readthedocs.io/en/latest/

`THIRD_PARTY_SOURCES_USED: NONE`

## Required next step

Before Batch 02B implementation, obtain an explicit human decision for one of:

1. approve a specifically identified openWakeWord model with its non-commercial
   or separately cleared distribution terms;
2. approve Porcupine, its AccessKey secret-management path, account/plan, and
   distribution terms; or
3. defer acoustic wake and keep text/manual wake only.

No runtime implementation is authorized by this document alone.
