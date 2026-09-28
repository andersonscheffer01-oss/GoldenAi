# JARVIS Voice Conversation Adapter Closure Review

Status: `PASS_WITH_RESTRICTIONS`
Phase: `PARTIAL`
Baseline: `defab74`
Review mode: read-only architecture and decision gate
Review date: 2026-09-28

This review closes the implementation review for Voice Conversation Adapters
1 through 4. It does not authorize another adapter, a provider installation,
model acquisition, microphone access, speaker playback, or a production-code
change. The result is intentionally separate from closure of the complete
voice phase.

## Decision

`VOICE_CONVERSATION_ADAPTER_CLOSURE_REVIEW: PASS_WITH_RESTRICTIONS`

The adapter layer is closed for the implemented logical scope. The complete
voice phase remains `PARTIAL` because the real local TTS provider gate, real
speech VAD gate, natural end-to-end conversation, and human barge-in retest
were not run in this review. The known `CORE_GENERATION_CANCEL: PARTIAL`
limitation remains open and is not hidden by the adapter closure.

Implementation history:

| Adapter | Commit | Result |
| --- | --- | --- |
| Adapter 1 | `904f6ed` | deterministic semantic turn adapter implemented |
| Adapter 2 | `ec11f3d` | identity-aware conversation coordinator integrated |
| Adapter 3 | `3933f9b` | bounded streaming TTS orchestration integrated |
| Adapter 4 | `85fc919` | session lifecycle and bounded recovery wired |
| Adapter 4 regression documentation | `defab74` | focused and broader gate recorded |

The focused post-Adapter-4 run recorded `162 passed`. The selected broader
run recorded `83 passed` and `14 failed`; the failures are classified below.
No failure from `tests/test_voice_adapter4_lifecycle.py` is a new Adapter 4
regression.

## Adapter closure

### Adapter 1

`SemanticTurnDetector` is deterministic, bounded, PT-BR-aware, and offline.
It classifies semantic continuation without calling Core, SecurityManager,
STT, TTS, tools, filesystem, network, or a model. Acoustic endpointing remains
the authority for dispatch. Coverage includes continuation, complete and
ambiguous phrases, timeout fallback, identity, partials, speech-active
precedence, malformed timing, and no-side-effect behavior.

Result: `PASS`

### Adapter 2

`ConversationStreamCoordinator` is one lock-protected coordinator owned by the
existing realtime pipeline. It preserves session, turn, utterance, and epoch
identity; rejects stale or cancelled events; deduplicates partial/final events;
and emits at most one eligible final. Continuations stay within a bounded
window and the existing `VoiceService` callback remains the only Core handoff.

Result: `PASS`

### Adapter 3

`StreamingTextSegmenter` and `StreamingTTSOrchestrator` extend the existing
provider-neutral TTS boundary. The queue is serial and bounded, synthesis jobs
retain session/turn/generation identity, cancellation drains pending work, and
`VoiceAudioPipeline` rejects late output. The implementation uses test fakes;
it does not prove a real TTS provider, model, or speaker path.

Result: `PASS_WITH_RESTRICTIONS`

### Adapter 4

`VoiceService` remains the session owner, `TurnManager` remains the turn and
cancellation authority, and the existing state machine remains authoritative.
Start/stop/restart are idempotent, cleanup is bounded, stale transcripts and
Core/TTS generations are rejected, and component failures have one bounded
recovery transition. Realtime STT/coordinator failures return the current
pipeline to listening without creating a second owner.

Result: `PASS_WITH_RESTRICTIONS`

`ADAPTER_PHASE_CLOSED: YES` means the four adapter implementation scope is
closed. It does not mean that real voice hardware or full-duplex behavior is
closed.

## End-to-end path

| Boundary | Current state | Evidence / restriction |
| --- | --- | --- |
| MIC_INPUT | `IMPLEMENTED_NOT_REAL_GATE` | `AudioInputProvider` owns one lazy `sounddevice.RawInputStream`, bounded queues, device identity, generation guard, and restart. The prior controlled microphone result proves signal-path availability only. |
| VAD | `IMPLEMENTED_NOT_REAL_SPEECH_GATE` | `SileroVADAdapter` uses local ONNX and is integrated; human speech behavior was not validated in this closure. |
| ENDPOINTING | `IMPLEMENTED` | `HybridEndpoint` provides bounded hangover and speech-resumed cancellation. |
| STT | `IMPLEMENTED_LOCAL_APPROVED_ARTIFACT` | `FasterWhisperSTTProvider` is fail-closed, local-only, PT-BR, CPU/int8, and requires the pinned approved snapshot. |
| SEMANTIC_TURN | `IMPLEMENTED` | Adapter 1 deterministic decision engine. |
| CONVERSATION_COORDINATOR | `IMPLEMENTED` | Adapter 2 identity and duplicate guard. |
| CORE_HANDOFF | `IMPLEMENTED_SECURITY_BOUNDARY` | VoiceService calls the canonical service/brain path; tool execution remains behind JarvisService and SecurityManager. |
| STREAMING_RESPONSE_HANDOFF | `IMPLEMENTED_WITH_PROVIDER_RESTRICTION` | Existing streaming path has stale-turn checks and metrics, but provider behavior is not a proof of upstream cancellation. |
| TTS_STREAMING | `IMPLEMENTED_PROVIDER_NEUTRAL` | Adapter 3 bounded segment and work queue. |
| REAL_TTS_PROVIDER | `NOT_READY` | No approved local provider and artifact are installed and selected for this path. |
| AUDIO_OUTPUT | `IMPLEMENTED_NOT_HARDWARE_VALIDATED` | `SoundDeviceAudioOutputProvider` has PCM validation, queue identity, flush, abort, and bounded recovery. No speaker was opened in this review. |

## Local TTS status

| Gate | Result | Meaning |
| --- | --- | --- |
| TTS_PROVIDER_CONTRACT_EXISTS | `YES` | `TextToSpeechProvider` and `AudioOutputProvider` contracts exist. |
| TTS_STREAMING_ORCHESTRATION_EXISTS | `YES` | Segmenter, bounded queue, cancellation, and identity gates exist. |
| REAL_LOCAL_PROVIDER_IMPLEMENTED | `NO` | The new path is provider-neutral with test fakes; legacy SAPI/Edge paths are not the approved local provider gate. |
| REAL_LOCAL_RUNTIME_AVAILABLE | `NO` | No selected and validated production local TTS runtime is connected to this path. |
| APPROVED_MODEL_AVAILABLE | `NO` | The selected Piper artifact is not present. |
| MODEL_LICENSE_VERIFIED | `NO` | Piper voice/model terms remain an approval gate. |
| REAL_SYNTHESIS_VALIDATED | `NO` | No real synthesis was executed. |
| REAL_PLAYBACK_VALIDATED | `NO` | No speaker was opened or played. |

The donor audit found `wyoming-piper` and Piper as credible local references,
not as a cleared drop-in. The existing TTS decision records Piper
`pt_BR-faber-medium` as a candidate, but also records package version,
artifact, checksum, and redistribution approval as pending. Therefore:

`LOCAL_TTS_NEXT_ACTION: SELECT_APPROVED_LOCAL_TTS_PROVIDER`

That action is a future provider approval gate, not an implementation or
installation performed by this review.

## Runtime environment discrepancy

The hardware-gate discrepancy is an interpreter selection issue, not a missing
project dependency declaration.

| Check | Global interpreter | Golden virtual environment |
| --- | --- | --- |
| Executable | `C:\Users\Anderson\AppData\Local\Programs\Python\Python313\python.exe` | `C:\GoldenAI\.venv\Scripts\python.exe` |
| `sounddevice` | not importable | `0.5.6` importable |
| `onnxruntime` | not importable | `1.29.0` importable |
| `faster_whisper` | not importable | `1.2.1` importable |
| Silero asset | unavailable through this interpreter | `faster_whisper/assets/silero_vad_v6.onnx` exists, 1,245,151 bytes |

`requirements.txt` already declares `sounddevice==0.5.6` and
`faster-whisper>=1.0.0`; `onnxruntime` is a runtime dependency of the VAD
path but is not separately declared in that file. The observed root cause is
therefore:

`SOUNDDEVICE_DISCREPANCY_CLASSIFICATION: DIFFERENT_PYTHON_ENVIRONMENT`

The global interpreter would block hardware gates, while the Golden virtual
environment has the required audio/STT/VAD imports. No package was installed
and no environment was changed. The recommended future fix is to run the
existing hardware gates with the canonical Golden virtual environment and to
make any optional/runtime dependency declaration decision in a separate
dependency gate.

`BLOCKS_HARDWARE_GATES: YES_FOR_GLOBAL_INTERPRETER`

### Gate 1 validation result

Gate 1 was validated on 2026-09-28 with the existing Golden virtual
environment. No package installation, device open, model download, or real
audio operation occurred.

```yaml
VOICE_RUNTIME_ENVIRONMENT_ALIGNMENT: PASS
VOICE_RUNTIME_IS_GOLDEN_VENV: YES
PYTHON_EXECUTABLE: C:\\GoldenAI\\.venv\\Scripts\\python.exe
PYTHON_VERSION: 3.13.15
PLATFORM: Windows-11-10.0.26200-SP0 / AMD64 / 64bit
SOUNDDEVICE: PASS (0.5.6)
NUMPY: PASS (2.5.2)
SCIPY: PASS (1.18.0)
SILERO_RUNTIME: PASS (onnxruntime 1.29.0; local ONNX session load/unload)
FASTER_WHISPER: PASS (1.2.1)
CTRANSLATE2: PASS (4.8.1)
PYTEST: PASS (9.1.1)
PYTEST_ASYNCIO: PASS (1.4.0)
APPROVED_STT_ARTIFACT_RESOLVABLE: YES
MODEL_DOWNLOADED: NO
```

The approved faster-whisper snapshot resolved and passed the project's
required-file check at:

`C:\Users\Anderson\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120`

The required files were present: `config.json`, `model.bin`,
`tokenizer.json`, and `vocabulary.txt`. The Silero asset also loaded and
unloaded successfully from the installed faster-whisper assets without
feeding audio.

The previously environment-blocked target was rerun as:

`C:\GoldenAI\.venv\Scripts\python.exe -m pytest tests/test_barge_in_runtime_wiring.py -vv --tb=short`

Result: `25 passed in 25.52s`. The prior sounddevice-related environment
failure does not reproduce under the canonical Golden interpreter. This was a
software/runtime-wiring test only; it did not enumerate or open an audio
device.

## Regression classification

The broader run's 14 failures are not counted as new adapter regressions.
`PRE_EXISTING` is the umbrella classification; the following two categories
partition those failures by observed cause.

| Test | Classification | Observed cause |
| --- | --- | --- |
| `VoiceConversationP11Case.test_follow_up_context_is_sent_without_second_llm` | `PRE_EXISTING / LEGACY_FIXTURE` | Isolated legacy voice/provider harness assertion failed before the Adapter 4 focused gate; not an Adapter 4 lifecycle failure. |
| `VoiceConversationP11Case.test_simple_voice_conversation_selects_voice_fast` | `PRE_EXISTING / LEGACY_FIXTURE` | Legacy routing expectation observed `GENERAL` instead of `VOICE_FAST`; outside Adapter 4 lifecycle ownership. |
| `VoiceConversationP11Case.test_voice_service_uses_one_tts_call` | `PRE_EXISTING / LEGACY_FIXTURE` | Legacy provider path logged missing Groq key and a fallback model 404; the assertion observed zero `_speak` calls. |
| `VoiceConversationP11Case.test_auto_mode_depends_on_source` | `PRE_EXISTING / ENVIRONMENT` | Windows temporary SQLite cleanup lock (`PermissionError`, `golden_tasks.db`) during teardown. |
| `VoiceConversationP11Case.test_complex_voice_conversation_uses_deep` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_fast_paths_bypass_voice_fast_and_llm` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_output_modes_and_same_utterance_instruction` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_secret_voice_fast_never_calls_cloud` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_spoken_response_removes_markdown_and_urls` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_tool_intent_is_not_swallowed` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_voice_fast_fallback_is_short_and_model_specific` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `VoiceConversationP11Case.test_voice_runtime_context_is_truthful_and_compact` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `LowConfidenceFeedbackCase.test_low_confidence_speech_asks_for_repeat` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |
| `LowConfidenceFeedbackCase.test_pure_noise_stays_silent` | `PRE_EXISTING / ENVIRONMENT` | Same Windows temporary SQLite teardown lock. |

```yaml
TOTAL_REPORTED_FAILURES: 14
PRE_EXISTING: 14
ENVIRONMENT: 11
LEGACY_FIXTURE: 3
VOICE_REGRESSION: 0
UNRELATED_REGRESSION: 0
UNKNOWN: 0
NEW_VOICE_REGRESSION_BLOCKER: NONE_IN_ADAPTER_4_FOCUSED_RUN
```

The 11 teardown failures are test-environment cleanup failures, not evidence
that the corresponding assertions failed. The three legacy/provider failures
remain follow-up work for their owning routing/provider tests; they are not a
reason to reopen Adapter 4 in this closure review.

## Real VAD readiness

`READY_FOR_REAL_SPEECH_VAD: NO`.

The code path and approved local STT/VAD asset are present in the Golden
virtual environment, but the closure did not run a real speech sample. The
global interpreter mismatch would fail before hardware capture. The next real
VAD gate must run under the canonical Golden virtual environment and must
record an explicit human speech result; synthetic fixtures and RMS/noise are
not substitutes.

`REAL_SPEECH_VAD_BLOCKER: VOICE_RUNTIME_ENVIRONMENT_ALIGNMENT_AND_EXPLICIT_REAL_SPEECH_GATE`

## Cancellation and stale-output review

| Layer | Result | Boundary |
| --- | --- | --- |
| UPSTREAM_GENERATION_CANCEL | `PARTIAL` | Turn cancellation and provider-facing cancellation are cooperative; the provider is not proven to terminate upstream computation immediately. |
| OUTPUT_GENERATION_INVALIDATION | `PASS` | `TurnManager`, `_tts_epoch`, session identity, and stale-output checks invalidate old generations before late callbacks are accepted. |
| TTS_CANCELLATION | `PASS_WITH_RESTRICTIONS` | Provider-neutral TTS cancels, drains, and joins bounded work; legacy Edge/SAPI remains a separate fallback path. |
| PLAYBACK_ABORT | `PASS_WITH_RESTRICTIONS` | The output contract flushes and aborts the owned stream; physical speaker abort was not validated. |

Current stale-output safety classification:

```yaml
STALE_CORE_OUTPUT_CAN_EXECUTE: NO
STALE_TEXT_CAN_REACH_TTS: NO
STALE_AUDIO_CAN_PLAY: NO
UPSTREAM_COMPUTE_MAY_CONTINUE: YES
CORE_GENERATION_CANCEL_BLOCKS_FIRST_NATURAL_E2E: NO
```

The last value is deliberately `NO`: stale-output invalidation is sufficient
for a first controlled no-interruption E2E. Upstream continuation is still a
resource/latency limitation and must be addressed before a hardened
barge-in-soak claim.

## Barge-in and full E2E

`READY_FOR_HUMAN_BARGE_IN_RETEST: NO`.

Blockers are the absence of an approved real local TTS provider/artifact,
absence of real speaker playback evidence, and absence of a fresh human
speech-during-playback retest. The existing `accept_barge_in` ordering is
correct for the logical boundary: classify policy, invalidate generation,
cancel the old turn/TTS, create a new turn, flush through the output owner,
and return to listening. It is not proof of acoustic behavior.

`AEC_REQUIRED_BEFORE_FIRST_E2E: NO`.

A controlled first natural E2E can be half-duplex and explicitly observed.
`AEC_RESEARCH_REQUIRED: YES_IF_SELF_TRIGGER_OR_BARGE_IN_REMAINS_UNRELIABLE`.
No AEC implementation or threshold change is authorized by this review.

`READY_FOR_FULL_NATURAL_CONVERSATION_E2E: NO`.

E2E blockers, in order, are runtime environment alignment, approved local TTS
provider/artifact approval, real TTS synthesis/output validation, explicit
real-speech VAD/endpoint validation, and only then the controlled natural
conversation and human barge-in gates.

## Observability

Logical instrumentation exists for capture, STT, routing, execution, TTS,
provider TTFT, first sentence, first TTS audio, total response, chunks
emitted, chunks played, session, response, process, and TTS owner. The
physical speaker boundary is not independently timestamped by a confirmed
device callback in this review.

`LATENCY_INSTRUMENTATION_READY: PARTIAL`

It is sufficient for offline and provider-boundary measurements, not yet for a
trustworthy acoustic `speech-start -> physical-abort` measurement.

## Privacy and security

| Boundary | Status |
| --- | --- |
| LOCAL_MIC | `YES_BY_DESIGN` |
| LOCAL_VAD | `YES_BY_DESIGN` |
| LOCAL_STT | `YES_BY_DESIGN` when the approved local artifact is available |
| LOCAL_TTS | `NOT_YET_SELECTED/VALIDATED` |
| MANDATORY_CLOUD_FOR_VOICE_PIPELINE | `NO_FOR_LOCAL_PATH`; legacy Edge fallback remains cloud-dependent if selected |
| VOICE_SECURITY_BOUNDARY | `PASS` |

VoiceService sends command/tool work through the existing JarvisService path;
tool risk, confirmation, execution, verification, and audit remain owned by
SecurityManager and AuditLog. The adapters add no direct tool or privileged
action capability. No audio, transcript, secret, or model was persisted or
created by this review.

## Critical path

Exactly one next gate is selected. The ordering below is the dependency path,
not permission to execute all gates in this review.

```yaml
GATE_1: VOICE_RUNTIME_ENVIRONMENT_ALIGNMENT
GATE_2: APPROVED_LOCAL_TTS_PROVIDER_AND_ARTIFACT_GATE
GATE_3: REAL_SPEECH_VAD_AND_ENDPOINT_GATE
GATE_4: CONTROLLED_NATURAL_VOICE_E2E
GATE_5: HUMAN_BARGE_IN_RETEST
POST_E2E_OPTIMIZATIONS:
  - prove upstream generation termination or bounded provider cancellation
  - add physical playback latency boundary measurement
  - investigate AEC only if controlled acoustic evidence requires it
```

`NEXT_GATE: APPROVED_LOCAL_TTS_PROVIDER_AND_ARTIFACT_GATE`

`NEXT_STEP: proceed to reuse-first local TTS provider and artifact selection;
keep using C:\\GoldenAI\\.venv\\Scripts\\python.exe for all future Voice
validation commands.`

## Closure definitions

`VOICE_MVP_COMPLETE_WHEN`:

- one approved local TTS provider and artifact pass provenance/license checks;
- the canonical Golden environment opens the existing input/output boundaries;
- one real human speech sample passes VAD, endpoint, local STT, and semantic
  turn acceptance;
- one controlled natural voice request completes through Core and SecurityManager;
- output identity prevents stale text/audio from reaching the speaker;
- no second session, Core, SecurityManager, or playback owner exists.

`VOICE_HARDENED_WHEN`:

- MVP criteria are repeatable across restart and device recovery;
- controlled human barge-in passes with measured interruption timing;
- upstream generation cancellation is proven or its bounded cost is explicitly
  accepted and instrumented;
- physical playback and microphone coexistence are measured;
- AEC is introduced only if evidence requires it and only behind the existing
  cancellation/security boundaries;
- privacy, artifact provenance, provider ownership, and failure recovery are
  regression-tested in the canonical environment.

## Safety and change record

```yaml
PRODUCTION_CODE_CHANGED: NO
DEPENDENCIES_INSTALLED: NO
MODELS_DOWNLOADED: NO
MICROPHONE_OPENED: NO
AUDIO_PLAYED: NO
WINDOWS_SETTINGS_CHANGED: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
PUSH: NO
```

Created by this review:

- `docs/architecture/JARVIS_VOICE_CONVERSATION_ADAPTER_CLOSURE.md`

No unrelated dirty worktree file is part of this document or its commit.
