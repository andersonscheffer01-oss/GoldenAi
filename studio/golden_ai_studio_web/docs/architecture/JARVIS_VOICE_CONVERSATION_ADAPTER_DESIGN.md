# JARVIS Voice Conversation Adapter Design

Status: `ADAPTER_3_IMPLEMENTED`
Review result: `PASS_WITH_RESTRICTIONS`
Baseline: `ec11f3d`
Source audit: `docs/architecture/JARVIS_VOICE_CONVERSATION_STACK_AUDIT.md`
Recommendation: `HYBRID`

This document defines the smallest adapter layer for useful conversation
patterns from Pipecat, LiveKit Agents, and Wyoming. Adapter 1, Adapter 2, and
the bounded Adapter 3 TTS orchestration are implemented without adding
dependencies, running the real-speech VAD gate, or replacing any Golden
owner. Adapter 4 remains deferred.

## Adapter 1 implementation status

`VOICE_ADAPTER_1` is now implemented as a pure deterministic decision engine
in `jarvis_core/realtime_voice/semantic_turn.py`. It preserves the approved
contract and returns only `CONTINUE_LISTENING`, `LIKELY_COMPLETE`, `COMPLETE`,
or `UNCERTAIN`, with bounded reason codes and the unchanged
`session_id`/`turn_id`/`utterance_id`/`epoch` identity.

The detector has no Core, SecurityManager, STT, TTS, audio, filesystem,
network, or model dependency. Its first strategy is a small PT-BR-aware
heuristic set that keeps unfinished trailing connectives and ellipses open,
requires the existing acoustic endpoint for completion, and falls back
deterministically when the bounded continuation window expires. Adapter 2
integrates this pure result into the existing pipeline without giving the
detector a dispatch capability.

Offline coverage is in `tests/test_semantic_turn.py` and includes incomplete
Portuguese phrases, continuation, complete phrases, natural pauses, ambiguity,
timeout fallback, malformed timing, Unicode, identity preservation, partial
transcripts, speech-active precedence, repeatability, and no-side-effect
behavior.

Known limitation: this adapter does not fix `CORE_GENERATION_CANCEL: PARTIAL`
and does not tune Silero VAD, `HybridEndpoint`, or `TurnManager`.

## Adapter 2 implementation status

`VOICE_ADAPTER_2` is implemented in
`jarvis_core/realtime_voice/conversation_coordinator.py` and integrated by
`RealtimeVoicePipeline`. It is one bounded, lock-protected coordinator per
existing realtime pipeline; it is not a second state machine, VoiceService,
STT pipeline, scheduler, audio owner, or Core route.

The coordinator receives existing `TranscriptEvent` values together with the
current acoustic endpoint and `turn_id`. It preserves
`session_id`/`turn_id`/`utterance_id`/`epoch`, rejects stale session/turn/epoch
events, rejects cancelled or inactive events, deduplicates partial/final
events, and emits at most one eligible final per logical utterance. Partial
transcripts remain observable only and are never eligible for Core dispatch.

An acoustic endpoint plus an incomplete semantic final opens a bounded
continuation window. Subsequent segments are combined into one logical final
with one callback eligibility. A timeout completes through the existing
acoustic boundary. Semantic uncertainty without an acoustic endpoint does not
dispatch. Detector failure uses acoustic fallback only when an acoustic
endpoint is present; malformed input is rejected.

Turn replacement cancels the current STT token, advances the transcript
epoch, resets bounded coordinator state, and retains the same pipeline owner
and session. The existing `VoiceService` callback remains the only Core
handoff boundary. No SecurityManager, tool, filesystem, network, microphone,
speaker, or persistence call was added.

Offline regression coverage is in
`tests/test_voice_conversation_coordinator.py` and covers continuation,
single-final dispatch, partial isolation, stale identity, cancellation,
timeout, acoustic fallback, detector failure, memory bounds, pipeline
integration, and turn replacement. Real speech, real VAD, real STT, and real
audio were not run in this implementation gate.

## Adapter 3 implementation status

`VOICE_ADAPTER_3` extends the existing provider-neutral TTS boundary in
`jarvis_core/voice_tts.py` with `StreamingTextSegmenter` and
`StreamingTTSOrchestrator`. The implementation form is
`EXTEND_EXISTING`: `VoiceAudioPipeline` remains the only identity/output
gate, `AudioOutputProvider` remains the only output sink, and `VoiceService`
remains the lifecycle owner.

`StreamingTextSegmenter` accepts arbitrary text chunks and keeps at most
`max_pending_chars=1200` pending characters. It prefers sentence punctuation,
paragraph boundaries, and conservative long-clause boundaries. When the
bound is reached it flushes at whitespace before a forced cut. It handles
PT-BR Unicode, common abbreviations, decimals/currency, URLs, and basic
Markdown markers without treating transport chunks as speech units. Final
flush is idempotent and emits meaningful trailing text once.

`StreamingTTSOrchestrator` uses a serial `max_pending_segments=4` work queue.
The producer waits when the queue is full, so current-generation text is not
silently discarded. Serial synthesis makes playback order deterministic and
avoids a second playback scheduler. Repeated source callbacks may provide a
bounded `chunk_id` for deduplication. Jobs retain the active
`session_id`/`turn_id`/`generation`; `VoiceAudioPipeline` rejects late chunks
after a new generation, session restart, cancellation, or output flush.

Normal completion, cancellation, provider failure, and session stop all drain
the bounded queue and join the worker. Provider errors are returned as bounded
results without corrupting `VoiceService`. No real TTS provider, model,
microphone, speaker, network, or persistence path is used by this gate.

## Non-negotiable architecture

```yaml
ONE_JARVIS: YES
ONE_CORE: YES
ONE_SECURITY_MODEL: YES
ONE_TURN_MANAGER: YES
ONE_VOICE_SERVICE: YES
ONE_CANCELLATION_AUTHORITY: YES
VOICE_SERVICE_REMAINS_OWNER: YES
TURN_MANAGER_REMAINS_OWNER: YES
JARVIS_CORE_REMAINS_BRAIN: YES
SECURITY_MANAGER_REMAINS_ACTION_AUTHORITY: YES
SECOND_STATE_MACHINE_CREATED: NO
SECOND_AUDIO_SYSTEM_CREATED: NO
FRAMEWORK_ENGINE_REPLACEMENT: REJECT
```

An adapter may classify, schedule, segment, or translate events. It may not
execute a tool, call Core directly, authorize an action, create a second
session, own a device, or become an alternate playback path.

## Golden source review

The current Golden contracts were inspected before designing the adapters:

| Contract | Current source | Current finding |
| --- | --- | --- |
| Voice runtime owner | `jarvis_core/voice_service.py::VoiceService` | owns lifecycle, session, Core handoff, cancellation, TTS boundary, and recovery entry points |
| Voice identity | `jarvis_core/voice_foundation.py::VoiceSession` | session identity and session cancellation already exist |
| Transcript contract | `jarvis_core/voice_foundation.py::TranscriptEvent` | immutable text event with `session_id`, `utterance_id`, `epoch`, final/partial flag |
| Final gate | `jarvis_core/voice_foundation.py::TranscriptAcceptanceGate` | rejects cancelled, wrong-session, wrong-epoch, empty, and duplicate finals |
| Cancellation | `jarvis_core/voice_foundation.py::VoiceCancellation` | cooperative, thread-safe, auditable reason |
| Turn authority | `jarvis_core/streaming/turn_manager.py::TurnManager` | one current turn, cancellation event, stale and cancelled checks |
| Acoustic VAD | `jarvis_core/realtime_voice/vad.py::SileroVADAdapter` | local model adapter and acoustic event source |
| Acoustic endpoint | `jarvis_core/realtime_voice/hybrid_endpoint.py::HybridEndpoint` | bounded hangover and speech-resumed cancellation |
| Audio pipeline | `jarvis_core/realtime_voice/integration.py::RealtimeVoicePipeline` | VAD, endpoint, utterance buffer, STT call, and final acceptance path |
| STT provider | `jarvis_core/stt_faster_whisper.py::FasterWhisperSTTProvider` | approved local utterance STT; current provider contract is final-oriented, not token streaming |
| TTS/output contract | `jarvis_core/voice_tts.py` | `TextToSpeechProvider`, `AudioOutputProvider`, `PcmAudioChunk`, `VoiceAudioPipeline` |
| Real output | `jarvis_core/audio_output.py::SoundDeviceAudioOutputProvider` | bounded PCM output, identity/format guards, flush, abort/close, bounded recovery |
| Streaming path | `jarvis_core/streaming/orchestrator.py::StreamingOrchestrator` | LLM stream, sentence chunker, concrete TTS pipeline, audio player, stale turn checks |
| Existing states | `jarvis_core/realtime_voice/state_machine.py::VoiceStateMachine` | `IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SPEAKING`, `INTERRUPTED`, `ERROR`, `STOPPED` |

The design extends these boundaries. It does not duplicate them.

## External pattern extraction

Source revisions are the read-only `main` heads checked for this review.

| Source project | Version/commit | Source file/class | Pattern extracted | Golden use |
| --- | --- | --- | --- | --- |
| Pipecat | `2716ecb780470bcdc56f3e5ac01057a04104a519` | `AGENTS.md`; `FrameProcessor`; `InterruptionFrame`; `VADUserTurnStartStrategy`; `SegmentedSTTService` | frame/event flow, broadcast interruption, non-blocking background work, interruption-aware queues | adapt to `ConversationStreamCoordinator` and existing `RealtimeVoicePipeline` |
| Pipecat | same | `src/pipecat/transports/base_output.py` | bounded output queue, silence fallback, explicit bot-speaking lifecycle | adapt measurements and queue behavior to `AudioOutputProvider`; do not copy transport |
| LiveKit Agents | `57b3227a7842697e6ad45b1275369cf9700bf161` | `livekit-agents/livekit/agents/voice/agent_session.py::AgentSession` | one activity/session composition for VAD, STT, TTS, LLM, turns, tools | reference lifecycle vocabulary only; VoiceService remains owner |
| LiveKit Agents | same | `livekit-agents/livekit/agents/voice/agent_activity.py::AgentActivity` | interruption source, adaptive interruption, false-interruption handling, stale audio clearing | adapt decision ordering and observability; no LiveKit session |
| Wyoming | `fa5d98c1e8d3f1b00eadcf46df6f87f1d352ca3e` | `README.md`, protocol/event definitions | normalized JSONL plus PCM events for wake, VAD, STT, TTS, and playback | optional provider adapter on loopback only |
| Wyoming faster-whisper | `8c9142ecfa8fdb5b3cea82ad1dcad71cc24ebab9` | service README/endpointing options | local service, cache-first artifacts, optional VAD endpointing | reference only; current in-process STT is simpler |
| Wyoming Piper | `544902bc7fd75a7c31f3d90a18289e425c601f84` | service README/streaming option | local TTS service and raw audio streaming | future provider option, subject to voice/artifact approval |

No donor source is copied. No framework dependency is added.

## Adapter 1: semantic turn detection

### Goal

Use transcript and timing evidence to avoid premature completion after an
acoustic pause, without allowing semantic reasoning to override acoustic
authority or execute Core actions.

### Initial strategy

`NEW_MODEL_REQUIRED: NO`.

The first implementation should use deterministic heuristics over existing
partial/final transcript signals, acoustic endpoint evidence, punctuation when
available, and bounded timing. It should not call an LLM for every endpoint.
A later optional provider may use an existing local or explicitly selected
remote model only for classification, never for action execution.

The initial strategy can recognize conservative signals such as:

- unfinished conjunctions, prepositions, pronouns, or explicit ellipsis;
- a transcript that ends in a known continuation pattern;
- a complete imperative or question with a stable final transcript;
- contradictory acoustic/semantic evidence, returned as `UNCERTAIN`.

For example, `"Jarvis, procure os arquivos que eu..."` followed by a short
pause is `LIKELY_INCOMPLETE` or `UNCERTAIN`, not an immediate Core dispatch.
The later `"salvei ontem"` can complete the same utterance if identity and
window guards still match.

### Provider-neutral sketch

```python
class SemanticTurnDetector(Protocol):
    def decide(
        self,
        *,
        session_id: str,
        turn_id: int,
        utterance_id: str,
        epoch: int,
        transcript: str,
        is_final: bool,
        acoustic_endpoint: bool,
        speech_active: bool,
        elapsed_ms: float,
    ) -> SemanticTurnDecision: ...


@dataclass(frozen=True)
class SemanticTurnDecision:
    state: Literal[
        "CONTINUE_LISTENING",
        "LIKELY_COMPLETE",
        "COMPLETE",
        "UNCERTAIN",
    ]
    confidence: float
    reason: str
    session_id: str
    turn_id: int
    utterance_id: str
    epoch: int
```

The decision is bounded data. It has no Core, ToolRegistry, SecurityManager,
filesystem, or network capability.

### Acoustic authority rules

| Acoustic evidence | Semantic evidence | Result |
| --- | --- | --- |
| speech still active | any | `CONTINUE_LISTENING`; no completion |
| no endpoint yet | complete-looking text | keep listening; semantic signal cannot end audio by itself |
| endpoint candidate | incomplete-looking text | open bounded continuation window |
| endpoint candidate | complete-looking final text | `COMPLETE`, subject to identity gate |
| endpoint candidate | uncertain/error/timeout | acoustic fallback completion |
| continuation speech arrives in window | any matching identity | cancel pending completion and continue same utterance |
| window expires | incomplete/uncertain | complete acoustically; never wait forever |

Silero VAD and `HybridEndpoint` remain the acoustic authorities. Semantic
classification can delay an acoustic completion inside a bounded window, but
cannot invent speech, reopen a stopped session, or bypass `TranscriptAcceptanceGate`.

### Failure and timeout policy

The implementation must expose configuration, not hidden constants:

- `decision_timeout_ms`: maximum time allowed for one semantic decision;
- `max_continuation_window_ms`: maximum extension after an endpoint candidate;
- `max_pending_decisions`: bounded number of decisions per utterance;
- `fallback_on_error`: acoustic completion policy.

On timeout or provider failure, emit an observability event and return to the
acoustic endpoint path. A semantic provider must never hold a voice turn
indefinitely.

## Adapter 2: STT streaming orchestration

### Existing provider preserved

`FasterWhisperSTTProvider` and `SpeechToTextProvider` remain unchanged as
provider authority. The current provider is utterance-oriented. The adapter
does not pretend that a final-only provider is token-streaming.

The coordinator may support an optional future streaming capability, but it
must normalize its events into the existing Golden identity model:

```text
session_id + turn_id + utterance_id + epoch
```

`TranscriptEvent` remains the text payload. `VADEvent` remains the acoustic
payload. No duplicate event enum is needed for those existing signals.

### Event mapping

| Conversation event | Existing Golden source/contract | Core eligibility |
| --- | --- | --- |
| `SPEECH_STARTED` | `VADEvent.SPEECH_STARTED` | no |
| `PARTIAL_TRANSCRIPT` | `TranscriptEvent(is_final=False)` | never |
| `ENDPOINT_CANDIDATE` | `VADEvent.ENDPOINT` plus endpoint metadata | no |
| `FINAL_TRANSCRIPT` | `TranscriptEvent(is_final=True)` after acceptance gate | yes, existing authorized path only |
| `UTTERANCE_COMPLETE` | coordinator decision after acoustic/semantic rules | no direct action; releases accepted final |
| `STT_CANCELLED` | `VoiceCancellation` reason and coordinator event | no |
| `STT_ERROR` | controlled provider exception and coordinator event | no |

### Late and stale transcript policy

1. On new session, increment the acceptance epoch and cancel the old token.
2. On barge-in, invalidate the generation and create a new turn before
   accepting new audio.
3. A late partial may be observed for metrics but never reaches Core.
4. A late final is rejected when session, utterance, turn, epoch, or cancellation
   identity does not match.
5. A final accepted once is idempotent; duplicate final identity is rejected.
6. A cancelled provider may finish in the background, but its result is
   discarded and cannot create a Core request.

This preserves current `TranscriptAcceptanceGate` behavior and adds `turn_id`
to the coordinator envelope rather than creating a competing acceptance gate.

## Adapter 3: TTS streaming orchestration

### Responsibilities

The future adapter connects:

```text
LLM text chunks
    -> TextToSpeechSegmenter
    -> bounded TTS jobs
    -> existing TTS provider
    -> PcmAudioChunk
    -> existing VoiceAudioPipeline/AudioOutputProvider
    -> speaker
```

`TextToSpeechProvider`, `PcmAudioChunk`, `VoiceAudioPipeline`,
`AudioOutputProvider`, and playback cancellation remain Golden-owned.

### Text segmentation policy

Do not send individual LLM tokens to TTS. The segmenter should:

- prefer sentence punctuation and natural clause boundaries;
- wait for a configurable minimum useful text size before synthesis;
- force a bounded flush when maximum text wait is reached;
- avoid splitting abbreviations, decimal numbers, URLs, code, markdown links,
  and fenced code blocks;
- suppress formatting markers from spoken text through an explicit policy;
- emit the final residual segment exactly once.

The thresholds are configuration and measurement points, not fixed benchmark
claims. The segmenter should be a pure deterministic component in the first
implementation.

### Backpressure

The minimum safe policy is:

- one active TTS job;
- one bounded prefetched segment, if the provider supports it;
- no unbounded task creation;
- producer waits cooperatively when the job boundary is full;
- cancellation immediately drops pending text for the obsolete generation;
- output queue remains bounded and reports accepted/dropped/rejected counts;
- only matching `(session_id, turn_id, generation)` chunks can enter output.

Text is not silently dropped because of ordinary backpressure. Obsolete text
is cancelled and dropped only after generation invalidation.

### Existing path risk

`jarvis_core/streaming/orchestrator.py` currently uses
`SentenceChunker`, `TTSPipeline`, concrete provider stream functions, and
`AudioPlayer`, while `jarvis_core/voice_tts.py` provides the newer
provider-neutral PCM path. This is a known split. The adapter design does not
merge or rewrite those paths; a later implementation gate must select one
VoiceService-owned output route and add migration tests first.

## Interruption and generation ordering

The canonical future ordering is:

1. VAD reports user speech while Golden is speaking.
2. `VoiceService.accept_barge_in()` validates the existing self-trigger policy.
3. Increment `tts_epoch` / invalidate the old generation.
4. Cancel the old operation token and current `TurnManager` turn.
5. Cancel pending LLM streaming and TTS jobs cooperatively.
6. Flush the output queue and abort active playback through the current output
   owner.
7. Close or drain the old provider iterator; late callbacks observe stale
   generation/turn identity and are rejected.
8. Create the new turn and fresh cancellation token.
9. Continue listening and route only the new utterance through STT/Core.

The old generation is invalidated before cancellation so a race cannot make a
late provider callback current again.

### Cancellation classification

```yaml
CORE_GENERATION_CANCEL: PARTIAL
OUTPUT_INVALIDATION: PASS
```

Golden reliably invalidates turns/generations and rejects late output. The
streaming provider and Core generation are cooperatively cancelled; a provider
may still yield or finish after cancellation. That is why stale-result gates
remain mandatory. This is not a claim of physical upstream cancellation.

## Adapter 4: session lifecycle

The lifecycle adapter is a translator over the existing `VoiceService`,
`VoiceSession`, and `VoiceStateMachine`. It is not another state machine.

| Conversation phase | Existing state owner | Lifecycle responsibility |
| --- | --- | --- |
| `IDLE` | `VoiceStateMachine.IDLE` / `VoiceService` | keep session alive, await wake/listening activation |
| `LISTENING` | `VoiceStateMachine.LISTENING` | accept canonical audio frames |
| `TRANSCRIBING` | `VoiceStateMachine.TRANSCRIBING` | run STT under utterance identity |
| `THINKING` | `VoiceStateMachine.THINKING` | invoke Core through existing path |
| `SPEAKING` | `VoiceStateMachine.SPEAKING` | stream TTS/output under generation |
| `BARGE_IN` | existing `INTERRUPTED -> LISTENING` transition | perform ordered invalidation and fresh turn |
| `RECOVERING` | existing machine extension or `ERROR -> IDLE` mapping | bounded recovery subphase, not a new machine |
| `STOPPING` | `STOPPED` transition | cooperative shutdown and resource release |

If explicit `RECOVERING` and `STOPPING` states are needed, they must be added
to the existing `VoiceStateMachine` in a later implementation review. The
adapter must not create a parallel lifecycle graph.

### Session identity rules

- Barge-in preserves `session_id` and advances turn/generation.
- Runtime restart creates a new `VoiceSession` and invalidates all prior work.
- Recovery of a device or provider does not create a second VoiceService.
- Every callback carries or is associated with the active session/turn/epoch.
- Session teardown cancels VAD/STT/TTS/output and leaves no worker or stream.

## Recovery policy

| Failure | First response | Session result |
| --- | --- | --- |
| microphone temporary failure | bounded `AudioInputProvider.restart()` | keep session if recovery succeeds; otherwise controlled `ERROR/IDLE` |
| STT failure | emit `STT_ERROR`, discard only current utterance | remain listening; no Core request |
| semantic detector failure | emit metric, use acoustic endpoint fallback | remain listening or complete acoustically |
| Core/LLM failure | close current generation and report controlled error | remain in session; no TTS for failed generation |
| TTS failure | cancel current text/audio work | keep input alive if possible; local playback may be unavailable |
| audio output failure | flush/abort, bounded device recovery | resume only after output health; never create a second output owner |
| session restart | cancel everything and advance epoch | new `VoiceSession`; old callbacks rejected |

Each recovery transition needs a reason, attempt count, elapsed time, and final
state in non-sensitive telemetry.

## Local/offline mode

```yaml
LOCAL_VOICE_MODE:
  MIC: Golden AudioInputProvider
  VAD: SileroVADAdapter
  STT: FasterWhisperSTTProvider
  CORE: Jarvis Core with selected local ModelRouter route
  TTS: provider-neutral contract; approved local provider still pending
  OUTPUT: SoundDeviceAudioOutputProvider
  MANDATORY_CLOUD: NO
  MANDATORY_PAID_API: NO
```

`LOCAL_TTS: PARTIAL`. Golden has the abstraction and output path, but the
currently reviewed runtime still contains a legacy Edge TTS path and no final
approved local PT-BR provider/artifact in this design gate. Until that provider
passes its own license, artifact, and real-output gates, offline mode must
advertise TTS as unavailable or explicitly select an approved local provider;
it must not silently fall back to cloud.

Cloud STT/TTS/LLM providers may be optional adapters later. Selecting one must
be explicit, policy-visible, and subject to the existing remote text/audio
privacy rules.

## Wyoming boundary

Wyoming is useful for normalized PCM/event contracts and process isolation, but
the protocol is intentionally unauthenticated and unencrypted. If a future
adapter uses it, the only acceptable initial boundary is a Golden-owned
loopback endpoint with:

- explicit provider selection;
- localhost binding and no untrusted-network exposure;
- request/response size and timeout limits;
- health and protocol validation;
- no direct tools, Core, SecurityManager, or filesystem access;
- AuditLog events without raw audio;
- generation/session checks at the Golden adapter boundary.

No Wyoming endpoint is authorized by this document.

## Pipecat and LiveKit interface targets

### Pipecat patterns worth adapting

- `InterruptionFrame` semantics become an internal cancellation signal routed
  through `VoiceService`, not a new external frame bus.
- `SegmentedSTTService` background-work rule becomes the coordinator rule that
  STT work cannot block VAD input.
- `FrameProcessor` task tracking becomes bounded coordinator tasks with
  explicit shutdown and cancellation ownership.
- Output queue/silence behavior becomes metrics and output contract tests,
  not a second transport.

Target Golden interfaces: `RealtimeVoicePipeline`, `VoiceCancellation`,
`VoiceAudioPipeline`, `AudioOutputProvider`, and `TurnManager`.

### LiveKit patterns worth adapting

- `AgentSession` composition becomes a design checklist for one VoiceService,
  not an imported session object.
- adaptive interruption becomes a future semantic classifier over existing VAD
  and transcript evidence;
- false-interruption recovery becomes a bounded hold/resume decision with no
  replay of stale audio;
- activity/session metrics become a unified Golden timing record.

Target Golden interfaces: `VoiceService.accept_barge_in`,
`TranscriptAcceptanceGate`, `TurnManager`, `VoiceStateMachine`, and future
`SemanticTurnDetector`.

## AEC insertion point

`AEC: REFERENCE_ONLY` and not implemented.

If evidence later justifies AEC, insert an optional
`InputFramePreprocessor` between `AudioInputProvider` canonical PCM output and
the VAD/utterance consumer:

```python
class InputFramePreprocessor(Protocol):
    def process(
        self,
        frame: bytes,
        *,
        playback_reference: bytes | None,
        session_id: str,
        generation: int,
    ) -> bytes: ...
```

The default implementation is a pass-through. A future AEC must not own the
mic, speaker, turn manager, or session and must not change thresholds merely to
pass a test.

## Latency measurement model

No target benchmark is claimed. Future tests should record monotonic timestamps
for one `(session_id, turn_id, utterance_id, epoch, generation)`:

```yaml
MIC_FRAME_AT:
VAD_START_AT:
ENDPOINT_CANDIDATE_AT:
SEMANTIC_DECISION_AT:
STT_FINAL_AT:
CORE_REQUEST_AT:
CORE_FIRST_TOKEN_AT:
TTS_FIRST_CHUNK_AT:
PLAYBACK_START_AT:
```

Derived measurements:

```text
vad_start_latency = VAD_START_AT - MIC_FRAME_AT
endpoint_latency = ENDPOINT_CANDIDATE_AT - VAD_START_AT
semantic_latency = SEMANTIC_DECISION_AT - ENDPOINT_CANDIDATE_AT
stt_latency = STT_FINAL_AT - ENDPOINT_CANDIDATE_AT
core_ttft = CORE_FIRST_TOKEN_AT - STT_FINAL_AT
tts_first_audio = TTS_FIRST_CHUNK_AT - CORE_FIRST_TOKEN_AT
playback_start = PLAYBACK_START_AT - TTS_FIRST_CHUNK_AT
turn_total = PLAYBACK_START_AT - MIC_FRAME_AT
```

Missing stages remain null. Values must not be invented or inferred from
unrelated timestamps.

## Non-sensitive observability

The future adapter should emit structured metrics only:

- turn duration and phase durations;
- endpoint and semantic decision latency;
- STT final latency and accepted/rejected counts;
- Core first-token latency;
- TTS first-audio and playback start latency;
- barge-in invalidation, cancellation, flush, and abort latency;
- input/output queue depths, drops, rejects, and device recovery attempts;
- provider errors, timeouts, and lifecycle transitions.

Metrics may include opaque session/turn/utterance identifiers. They must not
persist raw audio. Transcript persistence remains policy-controlled. Remote
audio/text is allowed only when an explicit provider is selected.

## Proposed minimal files and classes

This is a future implementation shape, not a request to create these files in
this gate.

### One new module

`jarvis_core/realtime_voice/conversation_adapters.py`

Responsibility: provider-neutral semantic decision, bounded STT/TTS
orchestration, and lifecycle translation over current Golden contracts.

Owner: `VoiceService`, with `TurnManager` and existing providers injected.

Inputs: existing VAD events, `TranscriptEvent`, LLM text chunks, provider
callbacks, cancellation, session/turn/epoch/generation identity.

Outputs: bounded decisions, accepted final transcript events, ordered
`PcmAudioChunk` delivery, metrics, and controlled recovery events.

Dependencies: standard library plus current Golden contracts only. No Pipecat,
LiveKit, Wyoming, new model, or new runtime dependency.

Proposed classes:

- `SemanticTurnDetector` protocol and deterministic heuristic implementation;
- `ConversationStreamCoordinator` for identity/cancellation/event ordering;
- `TextToSpeechSegmenter` for pure text boundary decisions;
- `VoiceSessionLifecycleAdapter` as a translator over the existing state machine.

### Existing modules to extend later

| Existing file | Minimal future extension |
| --- | --- |
| `jarvis_core/voice_foundation.py` | optional identity envelope/capability protocol only if current types cannot carry `turn_id` |
| `jarvis_core/realtime_voice/integration.py` | inject coordinator and semantic decision callback without changing VAD ownership |
| `jarvis_core/voice_service.py` | lifecycle/recovery hooks and one canonical orchestration route |
| `jarvis_core/streaming/orchestrator.py` | route through the approved segmenter/output boundary or retire only after regression proof |
| `tests/test_voice_conversation_adapters.py` | deterministic adapter tests; no hardware |

No separate scheduler, session store, event bus, audio system, or security
layer is proposed.

## Interface sketches

```python
class ConversationStreamCoordinator:
    def start_utterance(
        self, *, session_id: str, turn_id: int, utterance_id: str, epoch: int
    ) -> None: ...

    def observe_acoustic(self, event: VADEvent, *, at: float) -> None: ...

    def observe_transcript(self, event: TranscriptEvent) -> None: ...

    def cancel(self, reason: str) -> None: ...

    def accepted_final(self) -> TranscriptEvent | None: ...


class TextToSpeechSegmenter:
    def feed(self, text_chunk: str) -> list[str]: ...
    def flush(self) -> list[str]: ...
    def reset(self) -> None: ...


class VoiceSessionLifecycleAdapter:
    def transition(self, state: ConversationalState, *, reason: str = "") -> None: ...
    def recover(self, failure: str) -> RecoveryDecision: ...
    def stop(self, reason: str) -> None: ...
```

All methods are conceptual. They must be implemented only after this design is
accepted and each method receives focused tests.

## Event flows

### Happy path

```text
USER SPEAKS
 -> AudioInputProvider canonical PCM
 -> SileroVADAdapter SPEECH_STARTED
 -> RealtimeVoicePipeline buffers utterance
 -> HybridEndpoint emits endpoint candidate
 -> SemanticTurnDetector decides complete or bounded continuation
 -> FasterWhisperSTTProvider returns final TranscriptEvent
 -> TranscriptAcceptanceGate accepts matching identity
 -> Jarvis Core receives final text through existing service path
 -> Core streams response text
 -> TextToSpeechSegmenter emits natural segments
 -> approved TTS provider emits PcmAudioChunk
 -> VoiceAudioPipeline accepts matching generation
 -> AudioOutputProvider plays
 -> VoiceService returns to LISTENING
```

### Barge-in path

```text
JARVIS SPEAKING
 -> real user speech reaches VAD
 -> VoiceService accepts normal barge-in policy
 -> invalidate old generation
 -> cancel old operation and TurnManager turn
 -> cancel pending LLM/TTS work
 -> flush output queue and abort playback
 -> reject stale callbacks and stale transcripts
 -> create new turn with fresh cancellation
 -> capture new user utterance
 -> STT final
 -> Core
 -> new response
```

### Failure paths

| Failure | Required behavior |
| --- | --- |
| STT failure | log non-sensitive error, reject current utterance, remain listening |
| semantic failure | log decision failure, use acoustic endpoint fallback |
| Core failure | invalidate current generation, do not synthesize a failed response, remain in session |
| TTS failure | cancel pending audio, expose unavailable/degraded output, keep input if healthy |
| output failure | flush/abort, attempt bounded same-device recovery, no second output owner |

## Deterministic offline test design

Future implementation must add tests before another human audio gate:

1. Incomplete phrase after acoustic endpoint keeps a bounded continuation
   window.
2. Completed phrase crosses the semantic/acoustic combination rule.
3. Semantic decision timeout falls back to acoustic completion.
4. Semantic provider failure is isolated and observable.
5. Partial transcript never reaches Core.
6. Late final with old session, turn, utterance, epoch, or generation is
   rejected.
7. Cancelled turn cannot emit a final Core request.
8. Segmenter handles punctuation, abbreviations, numbers, URLs, code, and
   markdown without token-by-token speech.
9. TTS jobs and output queue remain bounded under slow playback.
10. Stale TTS generation cannot enter output after barge-in.
11. Barge-in order invalidates, cancels, flushes, aborts, and starts the new
    turn exactly once.
12. Mic/STT/semantic/Core/TTS/output recovery preserves or resets session
    according to the recovery table.
13. Session shutdown leaves no task, stream, or output worker.

No microphone, speaker, model download, network provider, or persisted audio is
required for these tests.

## Acceptance criteria for future implementation

### `SEMANTIC_TURN_ADAPTER`

- uses no new model/dependency in the first version;
- cannot complete while acoustic speech is active;
- cannot execute Core actions;
- bounded timeout and continuation window are observable;
- provider failure always falls back acoustically;
- incomplete phrase and completed phrase tests pass.

### `STT_STREAMING_ORCHESTRATION`

- preserves `session_id`, `turn_id`, `utterance_id`, and `epoch`;
- partials are observable only and never execute Core;
- stale/cancelled finals are rejected;
- at most one accepted final exists per utterance identity;
- provider failure does not kill the VoiceService session.

### `TTS_STREAMING_ORCHESTRATION`

- never sends individual tokens directly to TTS;
- has bounded text jobs and bounded audio queue;
- preserves segment order;
- tags every chunk with session/turn/generation identity;
- barge-in cancels, flushes, aborts, and rejects stale audio;
- output failure cannot create another speaker owner.

### `SESSION_LIFECYCLE_ADAPTER`

- delegates to the existing `VoiceStateMachine` and `VoiceService`;
- creates no competing state machine;
- keeps session identity across barge-in and bounded recovery;
- creates a new session only on explicit runtime restart;
- releases all providers and hardware on stop.

## Migration plan

```yaml
VOICE_ADAPTER_1:
  name: semantic decision contract
  scope: pure heuristic detector and acoustic/semantic combination rules
  verification: offline incomplete/complete/timeout/failure tests
  hardware: none

VOICE_ADAPTER_2:
  name: identity-aware conversation coordinator
  scope: normalize existing VAD/TranscriptEvent/cancellation events
  verification: partial/final/stale/cancelled/duplicate tests
  hardware: none

VOICE_ADAPTER_3:
  name: bounded text-to-speech segmentation
  scope: segment existing LLM chunks and route one approved output boundary
  verification: punctuation/backpressure/stale-generation tests
  hardware: none

VOICE_ADAPTER_4:
  name: lifecycle and recovery wiring
  scope: extend VoiceService without adding a state machine
  verification: provider failure and shutdown/recovery tests
  hardware: none

VOICE_ADAPTER_5:
  name: real speech VAD gate
  scope: separate authorization after adapter tests pass
  verification: controlled human speech only
  hardware: required, but deferred by this review
```

## Master Gap Audit preparation

These findings should later feed the global audit; that audit is not run here:

- split between `VoiceAudioPipeline`/`AudioOutputProvider` and legacy
  `StreamingOrchestrator`/`TTSPipeline`/`AudioPlayer`;
- current faster-whisper contract is utterance/final-oriented, not a complete
  partial streaming STT contract;
- no production semantic-turn provider exists yet;
- Core cancellation is cooperative; output invalidation is stronger than
  upstream generation cancellation;
- observability is distributed across `StreamingMetrics`, provider diagnostics,
  and VoiceService trace fields rather than one conversation timing record;
- local TTS provider/artifact approval remains incomplete while the legacy Edge
  path is available;
- legacy blocking audio paths remain in `voice_service.py` and require future
  ownership/convergence review;
- the real speech VAD gate remains pending and must not be inferred from signal
  or synthetic tests.

## Dependency and license gate

```yaml
NEW_DEPENDENCY_REQUIRED: NO
PROPOSED_DEPENDENCIES: []
LICENSE_BLOCKER: NO_FOR_DESIGN
```

Pipecat, LiveKit Agents, and Wyoming are references only in this design. No
framework package is added. Any future local TTS model, voice artifact,
framework model, or protocol service needs its own license/provenance review.

## Privacy and security

```yaml
RAW_AUDIO_PERSISTED: NO
TRANSCRIPT_PERSISTENCE: POLICY_CONTROLLED
REMOTE_AUDIO: ONLY_IF_EXPLICIT_PROVIDER_SELECTED
REMOTE_TEXT: ONLY_IF_EXPLICIT_PROVIDER_SELECTED
VOICE_IS_AUTHORIZATION: NO
SECURITY_MANAGER_BYPASS: NO
```

A spoken command remains ordinary untrusted input until it crosses the
existing Jarvis Core and SecurityManager path. Semantic classification cannot
approve a sensitive operation.

## Original design review result

```yaml
JARVIS_VOICE_PHASE: PARTIAL
VOICE_CONVERSATION_ADAPTER_DESIGN_REVIEW: PASS_WITH_RESTRICTIONS
BASELINE: f36cf07

GOLDEN_SOURCE_REVIEWED: YES
PIPECAT_SOURCE_REVIEWED: YES
LIVEKIT_SOURCE_REVIEWED: YES
WYOMING_SOURCE_REVIEWED: YES

RECOMMENDED_ARCHITECTURE: HYBRID
VOICE_SERVICE_REMAINS_OWNER: YES
TURN_MANAGER_REMAINS_OWNER: YES
JARVIS_CORE_REMAINS_BRAIN: YES
SECURITY_MANAGER_REMAINS_ACTION_AUTHORITY: YES
SECOND_STATE_MACHINE_CREATED: NO

SEMANTIC_TURN_ADAPTER: DESIGNED
STT_STREAMING_ADAPTER: DESIGNED
TTS_STREAMING_ADAPTER: DESIGNED
SESSION_LIFECYCLE_ADAPTER: DESIGNED

SEMANTIC_STRATEGY: DETERMINISTIC_HEURISTICS_FIRST
NEW_MODEL_REQUIRED: NO
NEW_DEPENDENCY_REQUIRED: NO
ACOUSTIC_FALLBACK_DEFINED: YES
BOUNDED_TIMEOUT_DEFINED: YES

EXISTING_FASTER_WHISPER_PRESERVED: YES
PARTIAL_TRANSCRIPT_EXECUTES_CORE: NO
FINAL_IDENTITY_GUARD_PRESERVED: YES
STALE_FINAL_REJECTED_BY_DESIGN: YES

EXISTING_TTS_ABSTRACTION_PRESERVED: YES
TEXT_SEGMENTATION_DESIGNED: YES
BOUNDED_BACKPRESSURE_DESIGNED: YES
STALE_AUDIO_REJECTED_BY_DESIGN: YES

GOLDEN_BARGE_IN_PRESERVED: YES
GENERATION_INVALIDATION_ORDER_DEFINED: YES
CORE_GENERATION_CANCEL: PARTIAL
OUTPUT_INVALIDATION: PASS

EXISTING_STATE_MACHINE_EXTENDED: YES
SECOND_STATE_MACHINE_REQUIRED: NO
RECOVERY_POLICY_DESIGNED: YES

LOCAL_MIC: YES
LOCAL_VAD: YES
LOCAL_STT: YES
LOCAL_TTS: PARTIAL
MANDATORY_CLOUD: NO
MANDATORY_PAID_API: NO

OFFLINE_TESTS_DESIGNED: YES
REAL_MIC_REQUIRED_FOR_ADAPTER_TESTS: NO
REAL_AUDIO_REQUIRED_FOR_ADAPTER_TESTS: NO

VOICE_ADAPTER_1: Semantic decision contract
VOICE_ADAPTER_2: Identity-aware conversation coordinator
VOICE_ADAPTER_3: Bounded text-to-speech segmentation
VOICE_ADAPTER_4: Lifecycle and recovery wiring

FINDINGS_FOR_MASTER_GAP_AUDIT: Split TTS paths; final-only STT contract; missing semantic provider; cooperative Core cancellation; fragmented observability; local TTS approval gap; legacy blocking audio path.

PRODUCTION_CODE_CHANGED: NO
DEPENDENCIES_INSTALLED: NO
MODELS_DOWNLOADED: NO
MICROPHONE_OPENED: NO
AUDIO_PLAYED: NO
WINDOWS_SETTINGS_CHANGED: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
PUSH: NO

FILES_CREATED:
  - docs/architecture/JARVIS_VOICE_CONVERSATION_ADAPTER_DESIGN.md
FILES_MODIFIED: NONE
COMMIT: documentation-only commit after verification

READY_TO_IMPLEMENT_ADAPTERS: NO
RUN_REAL_SPEECH_VAD_GATE_NOW: NO
NEXT_GATE: IMPLEMENTATION AUTHORIZATION FOR VOICE_ADAPTER_1
NEXT_STEP: Approve the design, then implement only the deterministic semantic adapter and its offline tests.
KNOWN_RESTRICTIONS: No production implementation, no new dependency, no model download, no microphone, no playback, no device registry change, no database migration, no push.
```

## Adapter 2 verification record

```yaml
JARVIS_VOICE_PHASE: PARTIAL
VOICE_ADAPTER_2: PASS_WITH_RESTRICTIONS
BASELINE: 904f6ed
IMPLEMENTATION_FORM: NEW_MINIMAL_COORDINATOR

SEMANTIC_ADAPTER_INTEGRATED: YES
ACOUSTIC_ENDPOINT_INTEGRATED: YES
STT_EVENTS_INTEGRATED: YES
LIVE_VOICE_SERVICE_WIRING: YES

SESSION_ID_GUARD: YES
TURN_ID_GUARD: YES
UTTERANCE_ID_GUARD: YES
EPOCH_GUARD: YES
GENERATION_CANCEL_GUARD: PARTIAL
STALE_PARTIAL_REJECTED: YES
STALE_FINAL_REJECTED: YES
CANCELLED_EVENT_REJECTED: YES
DUPLICATE_FINAL_DISPATCHED_TWICE: NO
NEW_UTTERANCE_AFTER_COMPLETION_ALLOWED: YES

PARTIAL_REACHES_CORE: NO
UNCERTAIN_WITHOUT_ENDPOINT_DISPATCHED: NO
ACOUSTIC_FALLBACK_BOUNDED: YES
CONTINUATION_BOUNDED: YES
ONE_LOGICAL_UTTERANCE: YES
ONE_ELIGIBLE_FINAL: YES
DIRECT_CORE_CALL: NO
DIRECT_SECURITY_CALL: NO
DIRECT_TOOL_CALL: NO

ADAPTER_1_TESTS: PASS
ADAPTER_2_TESTS: PASS
BROADER_VOICE_REGRESSION: 244 passed
ENVIRONMENT_BLOCKED_TEST: test_barge_in_runtime_wiring.py (sounddevice unavailable)
PY_COMPILE: PASS
SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS

REAL_MIC_RUN: NO
REAL_AUDIO_RUN: NO
REAL_SPEECH_VAD_GATE: DEFERRED
LOCAL_TTS: PARTIAL
CORE_GENERATION_CANCEL: PARTIAL
NEW_DEPENDENCY_REQUIRED: NO
DEPENDENCIES_INSTALLED: NO
MODELS_DOWNLOADED: NO
DEVICE_REGISTRY_TOUCHED: NO
PUSH: NO

FILES_CREATED:
  - jarvis_core/realtime_voice/conversation_coordinator.py
  - tests/test_voice_conversation_coordinator.py
FILES_MODIFIED:
  - jarvis_core/realtime_voice/integration.py
  - jarvis_core/voice_service.py
  - docs/architecture/JARVIS_VOICE_CONVERSATION_ADAPTER_DESIGN.md
```

## Adapter 3 verification record

```yaml
JARVIS_VOICE_PHASE: PARTIAL
VOICE_ADAPTER_3: PASS_WITH_RESTRICTIONS
BASELINE: ec11f3d
IMPLEMENTATION_FORM: EXTEND_EXISTING
STREAMING_TTS_COMPONENT: StreamingTextSegmenter + StreamingTTSOrchestrator

VOICE_SERVICE_REMAINS_OWNER: YES
TURN_MANAGER_REMAINS_OWNER: YES
SECOND_STATE_MACHINE_CREATED: NO
EXISTING_TTS_ABSTRACTION_PRESERVED: YES
EXISTING_AUDIO_OUTPUT_PRESERVED: YES
NEW_DEPENDENCY: NO

DETERMINISTIC_SEGMENTATION: YES
TOKEN_BY_TOKEN_TTS: NO
PT_BR_SUPPORTED: YES
UNICODE_SAFE: YES
ARBITRARY_CHUNK_BOUNDARIES: PASS
FINAL_FLUSH_EXACTLY_ONCE: YES
PENDING_TEXT_BOUNDED: YES
FORCED_FLUSH_DEFINED: YES

TTS_QUEUE_BOUNDED: YES
BACKPRESSURE_DEFINED: YES
ORDERING_PRESERVED: YES
OUT_OF_ORDER_SYNTHESIS_SAFE: NOT_APPLICABLE_SERIAL_SYNTHESIS
MEMORY_BOUNDED: YES

SESSION_ID_GUARDED: YES
TURN_ID_GUARDED: YES
GENERATION_EPOCH_GUARDED: YES
STALE_TEXT_REJECTED: YES
STALE_TTS_RESULT_REJECTED: YES
DUPLICATE_SEGMENT_DEDUPLICATED: YES_WITH_BOUNDED_CHUNK_ID
OUTPUT_INVALIDATION: PASS
CORE_GENERATION_CANCEL: PARTIAL

NORMAL_COMPLETION_CLEAN: YES
CANCELLATION_CLEAN: YES
SESSION_STOP_CLEAN: YES
SESSION_RESTART_ISOLATED: YES
PROVIDER_ERROR_BOUNDED: YES
ZOMBIE_TASKS: NO

ADAPTER_1_TESTS: PASS
ADAPTER_2_TESTS: PASS
NEW_ADAPTER_3_TESTS: 11 passed
FOCUSED_TESTS: 34 passed
BROADER_REGRESSION: 341 passed
FAILED_NEW: NONE
FAILED_PRE_EXISTING: NONE
BLOCKED_ENVIRONMENT: test_barge_in_runtime_wiring.py (18 passed, 7 failed; sounddevice unavailable)
PY_COMPILE: PASS
SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS

REAL_LOCAL_TTS_PROVIDER_USED: NO
LOCAL_TTS: PARTIAL
MODEL_DOWNLOADED: NO
REAL_AUDIO_PLAYED: NO
MICROPHONE_OPENED: NO
REMOTE_TEXT_SENT: NO
REMOTE_AUDIO_SENT: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
UNRELATED_WORKTREE_CHANGES_PRESERVED: YES
PUSH: NO

FILES_CREATED:
  - tests/test_voice_tts_streaming.py
FILES_MODIFIED:
  - jarvis_core/voice_tts.py
  - jarvis_core/voice_service.py
  - docs/architecture/JARVIS_VOICE_CONVERSATION_ADAPTER_DESIGN.md
```

## Official source references

- [Pipecat architecture notes](https://github.com/pipecat-ai/pipecat/blob/main/AGENTS.md)
- [Pipecat output transport](https://github.com/pipecat-ai/pipecat/blob/main/src/pipecat/transports/base_output.py)
- [Pipecat license](https://github.com/pipecat-ai/pipecat/blob/main/LICENSE)
- [LiveKit AgentSession](https://github.com/livekit/agents/blob/main/livekit-agents/livekit/agents/voice/agent_session.py)
- [LiveKit AgentActivity](https://github.com/livekit/agents/blob/main/livekit-agents/livekit/agents/voice/agent_activity.py)
- [LiveKit Agents development and license notes](https://github.com/livekit/agents/blob/main/AGENTS.md)
- [LiveKit model license](https://github.com/livekit/agents/blob/main/MODEL_LICENSE)
- [Wyoming protocol and security model](https://github.com/OHF-Voice/wyoming)
- [Wyoming faster-whisper](https://github.com/OHF-Voice/wyoming-faster-whisper)
- [Wyoming Piper](https://github.com/OHF-Voice/wyoming-piper)
- [SYSTRAN faster-whisper](https://github.com/SYSTRAN/faster-whisper)
