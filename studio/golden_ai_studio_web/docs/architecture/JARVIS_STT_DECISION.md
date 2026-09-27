# Jarvis Streaming STT Provider Selection and Architecture Gate

Status: `PASS_WITH_RESTRICTIONS`
Research date: `2026-09-27`
Scope: audit and selection only. No STT implementation, package installation,
model download, microphone activation, or Core change was performed.

```yaml
JARVIS_VOICE_PHASE: IN_PROGRESS
STREAMING_STT_SELECTION_GATE: PASS_WITH_RESTRICTIONS
BASELINE_VOICE_COMMIT: a7b9f51
ACOUSTIC_WAKE_DECISION_COMMIT: 66d4276
```

## Executive decision

`SELECTED_STT_PROVIDER: EXISTING_GOLDEN_PROVIDER`

`SELECTED_STT_PROVIDER_TYPE: LOCAL`

The first implementation batch should keep Golden's existing local
`faster-whisper` path and place a richer provider boundary around it. This is a
provider selection, not a claim that the current path is true streaming: the
current runtime waits for Golden VAD/end-silence, writes a bounded temporary WAV,
and then consumes the complete `faster-whisper` segment generator.

The provider family is sufficiently identified for an adapter design, but the
exact model artifact and its license/provenance are not cleared because no
model was downloaded or inspected in this gate. Therefore:

`READY_FOR_AUTONOMOUS_STT_BATCH: NO`

The remote `gpt-live-transcribe` path is a credible future optional provider
for real partial transcripts, but it is not selected as the first implementation
and must not become an automatic fallback without idempotency and privacy
approval.

## Environment

```yaml
PYTHON_EXECUTABLE: C:\\GoldenAI\\.venv\\Scripts\\python.exe
PROJECT_PYTHON_VERSION: 3.13.15
VIRTUALENV_ACTIVE: NO (interpreter invoked directly)
VIRTUALENV_PATH: C:\\GoldenAI\\.venv
CPU: AMD Ryzen 5 5600X, 6 cores / 12 threads
RAM: 31.92 GB
GPU: AMD Radeon RX 9060 XT
CUDA: NOT_AVAILABLE (nvidia-smi not present; no CUDA validation performed)
REALTIME_PERFORMANCE: UNMEASURED
```

The environment inspection was read-only. No driver, CUDA component, model, or
audio device stream was opened.

## Existing Golden STT

`EXISTING_STT_FOUND: YES`

`EXISTING_STT_IMPLEMENTATIONS:`

- `jarvis_core/voice.py::JarvisVoice.transcribe_audio_bytes`: lazy
  `faster_whisper.WhisperModel`, CPU `int8` by default, language `pt` by
  default, configurable model/beam/prompt, and structured confidence fields.
- `jarvis_core/voice_service.py`: owns capture, VAD/end-silence lifecycle,
  calls the existing STT method, rejects low-confidence/noise transcripts, and
  forwards accepted final text through the existing Core/security path.
- `jarvis_core/voice_foundation.py::SpeechToTextProvider`: minimal future
  protocol accepting bounded audio and cooperative cancellation; not yet wired
  as the runtime provider seam.
- `jarvis_core/realtime_voice/vad.py` and `hybrid_endpoint.py`: existing local
  VAD/endpoint components; they do not perform transcription.
- Browser upload path: server-side bounded transcription through the same
  `JarvisVoice` implementation; no separate cloud STT provider was found.

`STT_REUSE_CLASSIFICATION:`

- Existing `faster-whisper` path: `KEEP_OURS`.
- Existing `SpeechToTextProvider` protocol: `ADAPT_EXISTING`.
- Existing Golden VAD and endpointing: `KEEP_OURS`.
- Donor STT implementation: `REFERENCE_ONLY` / `REIMPLEMENT_PATTERN` for
  streaming lifecycle ideas; no donor code is copied.
- Browser Web Speech API: `REJECT_AS_PROVIDER`; it is a separate client path,
  not the canonical desktop microphone owner.

`DONOR_AUDIT_1B_STT_GUIDANCE:`

Donor Audit 1B classifies Donor A's faster-whisper STT as `KEEP_OURS` for the
Golden provider choice, while its async audio pipeline is a
`REIMPLEMENT_PATTERN`. The donor "streaming STT" is still request/response
Whisper, not a token-level live transcript contract. Donor provider coupling,
state ownership, and audio loop ownership must not replace VoiceService.

## Candidate 1: existing faster-whisper

```yaml
NAME: faster-whisper
TYPE: local existing Golden provider
TRUE_STREAMING_STT: NO in current Golden integration
PARTIAL_TRANSCRIPTS: NO in current integration
FINAL_TRANSCRIPTS: YES
WINDOWS_COMPATIBILITY: observed installed in the current Windows venv; fresh packaged-build validation remains future work
PYTHON_3_13_COMPATIBILITY: observed installed under Python 3.13.15; no clean reinstall performed
PT_BR_SUPPORT: language is configured as pt; pt-BR quality is unmeasured
MIXED_PT_EN_SUPPORT: initial_prompt contains Golden/MT5/technical vocabulary; quality is unmeasured
INPUT_SAMPLE_RATE: 16000 Hz
INPUT_FORMAT: PCM16 mono, wrapped as WAV for current call
FRAME_OR_CHUNK_REQUIREMENT: bounded completed utterance in current integration
AUDIO_ADAPTATION_REQUIRED: no resampling for current 16 kHz path; future streaming adapter required
OFFLINE: YES after exact model assets are available locally
AUDIO_LEAVES_DEVICE: NO
NETWORK_REQUIRED: only for obtaining model assets if not pre-bundled; not for local inference
SECRET_REQUIRED: NO
MODEL_REQUIRED: YES
MODEL_FAMILY: Whisper-compatible CTranslate2 model
APPROX_MODEL_SIZE: NOT_VERIFIED; current default name is small, but no artifact was downloaded
MODEL_SOURCE: faster-whisper model acquisition path/Hugging Face artifact, exact revision not pinned in current code
MODEL_LICENSE: exact artifact license/provenance pending; do not infer it from client license
CLIENT_CODE_LICENSE: MIT
RUNTIME_DEPENDENCIES: faster-whisper 1.2.1, CTranslate2 4.8.1, NumPy, PyAV assets as packaged by the provider
HEAVY_DEPENDENCIES: native CTranslate2 and model assets; PyTorch is present in the environment but is not required by this inference path
CANCELLATION_SUPPORT: current bounded call is not a true streaming cancellation contract; future adapter must use cooperative cancellation and ignore late results
SESSION_RESTART: VoiceService session/lifecycle already exists; adapter must bind session and utterance identity
LATE_RESULT_HANDLING: existing stale capture checks exist; provider adapter must add session/sequence validation
```

The official project describes `faster-whisper` as a CTranslate2
reimplementation of Whisper and documents lazy segment iteration. It does not
make the current Golden integration a live partial-transcript engine.

## Candidate 2: OpenAI gpt-live-transcribe

```yaml
NAME: gpt-live-transcribe
TYPE: remote realtime transcription API
TRUE_STREAMING_STT: YES
PARTIAL_TRANSCRIPTS: YES, transcript delta events
FINAL_TRANSCRIPTS: YES, completion event after commit
WINDOWS_COMPATIBILITY: transport/client is platform-neutral; Windows packaging is not explicitly guaranteed by the provider guide
PYTHON_3_13_COMPATIBILITY: not explicitly guaranteed by the provider guide; HTTP/WebSocket client compatibility must be verified before use
PT_BR_SUPPORT: language hint mechanism exists; exact pt-BR recognition quality is unmeasured
MIXED_PT_EN_SUPPORT: prompt, keywords, and multiple language hints are documented; quality is unmeasured
INPUT_SAMPLE_RATE: official realtime example uses 24000 Hz PCM
INPUT_FORMAT: PCM16 audio/pcm
FRAME_OR_CHUNK_REQUIREMENT: append chunks to input_audio_buffer and commit each turn
AUDIO_ADAPTATION_REQUIRED: YES; Golden 16 kHz frames require a documented conversion/resampling path
OFFLINE: NO
AUDIO_LEAVES_DEVICE: YES
DESTINATION: OpenAI Realtime transcription service over authenticated network transport
NETWORK_REQUIRED: YES
SECRET_REQUIRED: YES, OpenAI API credential
MODEL_REQUIRED: provider-hosted gpt-live-transcribe
APPROX_MODEL_SIZE: NOT_APPLICABLE_TO_LOCAL_DEPLOYMENT
MODEL_SOURCE: OpenAI hosted model
MODEL_LICENSE: API/service terms; not a redistributable local model
CLIENT_CODE_LICENSE: SDK/client terms must be reviewed if installed; no SDK installed in this gate
RUNTIME_DEPENDENCIES: authenticated WebSocket or supported realtime transport, provider client, session lifecycle
HEAVY_DEPENDENCIES: no local model runtime; network/session complexity instead
CANCELLATION_SUPPORT: adaptable through buffer clear/commit/session close and late-event suppression; exact Jarvis adapter contract remains future work
SESSION_RESTART: provider sessions can be recreated; item_id/session identity must be mapped to VoiceSession
LATE_RESULT_HANDLING: provider event ordering is not globally guaranteed across turns; match item/session identity and discard stale events
```

The official guide documents incremental transcript deltas and final completion
events, client-side VAD/explicit commit, PCM input, prompt/keyword/language
hints, and tunable delay. It also states that live audio should use the
Realtime transcription flow rather than file-upload streaming.

Current official price evidence is `$0.017/minute` for `gpt-live-transcribe`;
actual cost depends on audio duration and account terms. This is not a monthly
estimate.

## Candidate 3

`NOT_INCLUDED`: no third provider was sufficiently represented in the existing
Golden runtime to justify broadening this gate. Vosk, whisper.cpp, Deepgram,
AssemblyAI, Google Speech, and Azure Speech were not installed or integrated;
adding them experimentally would violate the audit-only scope.

## Factual comparison

```yaml
LOCAL_REMOTE_COMPARISON: faster-whisper keeps audio and inference local; gpt-live-transcribe sends live audio to OpenAI
PRIVACY_COMPARISON: local has no provider upload; remote requires explicit external-audio approval and secret handling
LATENCY_ARCHITECTURE_COMPARISON: local current path waits for endpoint and final decode; remote emits deltas but adds network/session latency
DEPENDENCY_COMPARISON: local native runtime/model assets; remote transport, provider client, network, and session lifecycle
WINDOWS_PYTHON_COMPARISON: local is already installed under Windows/Python 3.13.15; remote requires future client/transport verification
PT_BR_COMPARISON: local explicitly sets pt and technical prompt; remote supports language/context hints; both require real representative-audio evaluation
STREAMING_COMPARISON: local current path is utterance transcription; remote is true realtime delta/final transcription
CANCELLATION_COMPARISON: local needs cooperative decode boundary and stale-result suppression; remote needs session/buffer cancellation plus event suppression
CREDENTIAL_COMPARISON: local no secret; remote API secret required
LICENSE_COMPARISON: local client MIT but exact model artifact remains a separate provenance/license gate; remote uses API/service terms and no model redistribution
COST_COMPARISON: local has local compute/storage cost; remote is usage-priced at the official published rate
```

No real-time factor, latency, WER, RAM benchmark, or CPU/GPU benchmark was
fabricated or run in this gate.

## Target architecture

`STT_PROVIDER_BOUNDARY: SpeechToTextProvider, expanded in a future batch`

Recommended conceptual operations:

```text
start_session(session_id, utterance_id)
accept_frame(frame)
finish_utterance()
cancel(reason)
close()
```

Transcript events should contain at least:

```text
TranscriptEvent
    text
    is_final
    sequence
    session_id
    utterance_id
    provider metadata
```

`VAD_AUTHORITY: existing Golden SileroVADAdapter/HybridEndpoint`

`ENDPOINTING_AUTHORITY: Golden VAD and endpointing; provider endpointing may
inform transport only and must not silently replace Golden authority`

`AUDIO_TO_STT_FLOW:`

```text
AudioInputProvider
  -> bounded PCM16 frame queue
  -> Golden VAD / HybridEndpoint
  -> bounded utterance segment or approved provider stream
  -> SpeechToTextProvider
  -> TranscriptEvent
  -> final-only VoiceSession/Core boundary
```

`STT_SECOND_MICROPHONE_STREAM: NO`

`AUDIO_BUFFERING_STRATEGY: bounded utterance buffer for the first batch; future
incremental provider buffer must remain bounded and preserve frame sequence`

`MAX_UTTERANCE_STRATEGY: reuse the existing 6-second VoiceService listen window
and end-silence rules; reject/close overlong input rather than accumulating
indefinitely`

`PARTIAL_TRANSCRIPT_EXECUTES_CORE: NO`

`FINAL_TRANSCRIPT_CORE_BOUNDARY: final accepted event enters the existing
VoiceService -> JarvisService -> SecurityManager path`

`STALE_TRANSCRIPT_STRATEGY: require matching session_id, utterance_id, sequence,
and cancellation epoch; discard late events from cancelled/restarted sessions`

`DUPLICATE_FINAL_STRATEGY: idempotency key from session_id + utterance_id;
commit one final transcript only`

`CANCELLATION_STRATEGY: cooperative provider cancellation, close/flush bounded
buffers, invalidate the current epoch, ignore late provider events, and permit
session restart`

`FAILURE_ISOLATION_STRATEGY: end or degrade the voice turn, emit sanitized
diagnostics, preserve Core and VoiceSession integrity, and retain manual/text
fallback`

## Security and privacy

`TRANSCRIPT_TREATED_AS_UNTRUSTED_INPUT: YES`

`EXISTING_SECURITYMANAGER_REUSED: YES`

`EXISTING_APPROVAL_MODEL_PRESERVED: YES`

`RAW_AUDIO_PERSISTED: NO`

`CONTINUOUS_AUDIO_TO_CLOUD: NO for selected provider; YES only if a future
remote provider is explicitly approved`

`SECOND_JARVIS_CORE_CREATED: NO`

`SECOND_LLM_LOOP_CREATED: NO`

`SECOND_SECURITY_MODEL_CREATED: NO`

Partial transcripts are display/diagnostic data only. They never execute tools,
authorize actions, or bypass confirmation. A final transcript remains ordinary
untrusted user input and must pass existing risk classification and approval.

## Decision and gates

```yaml
SELECTED_STT_PROVIDER: EXISTING_GOLDEN_PROVIDER
SELECTED_STT_PROVIDER_TYPE: LOCAL
SELECTED_STT_PROVIDER_RATIONALE: already integrated, local, no credential, compatible with the existing 16 kHz path, and preserves privacy/single-stream ownership
SELECTED_STT_MODEL: DEFERRED exact faster-whisper model artifact
MODEL_DOWNLOAD_REQUIRED: YES unless an approved artifact is pre-bundled
MODEL_DOWNLOAD_SIZE: NOT_VERIFIED
LICENSE_GATE: PASS_WITH_RESTRICTIONS; exact model provenance/license pending
PRIVACY_GATE: PASS for selected local path
DEPENDENCY_GATE: PASS_WITH_RESTRICTIONS; native runtime/model packaging remains
WINDOWS_GATE: PASS_WITH_RESTRICTIONS
PYTHON_GATE: PASS_WITH_RESTRICTIONS; observed on Python 3.13.15, clean install not repeated
PT_BR_GATE: PASS_WITH_RESTRICTIONS; configured, not quality-benchmarked
CANCELLATION_GATE: PASS_WITH_RESTRICTIONS; future provider adapter required
SINGLE_STREAM_GATE: PASS
HUMAN_APPROVAL_REQUIRED_BEFORE_INSTALL: YES for any new provider/model/dependency
```

## Safety and regression record

```yaml
RUNTIME_FILES_MODIFIED: NONE
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
MICROPHONE_OPENED: NO
AUDIO_RECORDED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO
SECOND_SECURITY_MODEL_CREATED: NO
SECOND_JARVIS_CORE_CREATED: NO
SECOND_LLM_LOOP_CREATED: NO
```

The canonical task database remained read-only and unchanged.

## Official sources

- faster-whisper official repository: https://github.com/SYSTRAN/faster-whisper
- OpenAI file transcription guide: https://developers.openai.com/api/docs/guides/speech-to-text
- OpenAI realtime transcription guide: https://developers.openai.com/api/docs/guides/realtime-transcription
- OpenAI GPT-Live-Transcribe model: https://developers.openai.com/api/docs/models/gpt-live-transcribe
- OpenAI API pricing: https://developers.openai.com/api/docs/pricing
- Golden Voice architecture: `docs/architecture/JARVIS_VOICE_ARCHITECTURE.md`
- Golden Donor Audit 1B: `docs/architecture/JARVIS_DONOR_AUDIT_1B.md`

`THIRD_PARTY_SOURCES_USED: NONE`

## Regression and next gate

`READY_FOR_AUTONOMOUS_STT_BATCH: NO`

`PROPOSED_STT_PHASE_1: define the expanded SpeechToTextProvider and
TranscriptEvent contract with fake/injected providers only`

`PROPOSED_STT_PHASE_2: adapt the existing faster-whisper provider to bounded
utterance input, session epochs, cooperative cancellation, stale-result and
duplicate-final protection; do not add a second capture stream`

`PROPOSED_STT_PHASE_3: hardware-free audio + VAD + STT + VoiceSession tests;
only afterward consider an explicitly approved real-audio smoke test`

`KNOWN_ISSUES: current STT is utterance-based, not true streaming; model
artifact/license and clean-package behavior remain unverified; no real-time
performance or pt-BR quality benchmark was run`

`KNOWN_RESTRICTIONS: no remote provider fallback, no model download, no new
dependency, no microphone, no runtime code change`

`STOP_REASON: audit complete; model provenance and true-streaming adapter remain
implementation gates`

`NEXT_STEP: approve the exact local model artifact/provenance, then authorize a
separate STT implementation batch`
