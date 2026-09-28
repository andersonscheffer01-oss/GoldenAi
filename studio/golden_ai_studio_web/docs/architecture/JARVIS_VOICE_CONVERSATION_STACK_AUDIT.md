# JARVIS Voice Conversation Stack Audit

Status: `PASS_WITH_RESTRICTIONS`
Mode: read-only architecture and reuse audit
Baseline: `6b4c3e9`
Research date: 2026-09-28

## Scope and safety

This document audits existing source and official upstream repositories. It
does not implement a voice framework, change production voice code, install a
dependency, download a model, open the microphone, play audio, or run the
real-speech VAD gate.

The controlled real microphone baseline remains valid evidence only for the
audio signal path. It does not prove real speech VAD, semantic endpointing, or
full-duplex conversation quality.

## Executive answer

`FREE_OPEN_SOURCE_NATURAL_VOICE_STACK_EXISTS: PARTIALLY`

There is no single drop-in stack found that is simultaneously Windows-first,
local-only, cloud-optional, security-compatible with Golden, and complete for
capture, VAD, semantic turns, local STT, local TTS, LLM streaming, playback,
barge-in, recovery, and session ownership.

The closest open frameworks are useful orchestration references:

- Pipecat supplies a strong frame/processor pipeline, local audio transport,
  VAD/user-turn strategies, interruption frames, and many provider adapters.
- LiveKit Agents supplies the strongest documented turn/interruption/session
  engine, including adaptive interruption and semantic turn options, but its
  primary shape is an RTC/server agent runtime. Its terminal mode is useful for
  local testing, not evidence of a Windows desktop replacement.
- Wyoming supplies a practical local protocol and modular local services for
  wake word, VAD, faster-whisper, and Piper. It is a service mesh for voice
  components, not a replacement for the Golden Core and SecurityManager.

The evidence supports a controlled `HYBRID` direction, with Golden retaining
all authority and adapting only narrow orchestration patterns after a separate
design gate.

## Projects reviewed

### Existing donors

| Project | Source reviewed | License evidence | Result |
| --- | --- | --- | --- |
| OpenClaw | `C:\JarvisDonors\openclaw`; Talk/client audio and lifecycle sources | MIT root; third-party notices separate | `REFERENCE_ONLY` overall; platform lifecycle ideas only |
| Hermes Agent | `C:\JarvisDonors\hermes-agent`; desktop voice, TTS registry and voice mode | MIT root; optional providers require file-level review | `ADAPT` provider vocabulary; `REFERENCE_ONLY` full runtime |
| ndunl075/Jarvis | `C:\JarvisDonorAudit\ndunl075-Jarvis`; `jarvis/audio/*`, audio tests | MIT | strongest local cancellation/output pattern; `ADAPT` only |
| ONEPUNCHMAN411/Jarvis | `C:\JarvisDonorAudit\ONEPUNCHMAN411-Jarvis`; `jarvis/voice/*` | file/dependency review required | Windows queue and handoff reference; not a boundary owner |

### Specialist projects discovered and audited

| Project | Relevant capability | Windows/local finding | Classification |
| --- | --- | --- | --- |
| Pipecat | frame pipeline, local transport, VAD, turns, interruptions, STT/TTS/LLM services | local PortAudio path exists; Windows-specific desktop ownership is not established as a Golden-compatible runtime | `ADAPT` |
| LiveKit Agents | AgentSession, turn detection, adaptive interruption, semantic turns, playback/session lifecycle | terminal local I/O exists; primary production model is RTC/server-oriented and may add infrastructure | `ADAPT` |
| python-sounddevice | PortAudio device/host API enumeration and RawInput/OutputStream | directly relevant to current Windows path | `REFERENCE_ONLY`; Golden already owns the adapter |
| Silero VAD ecosystem | local VAD model and streaming windows | local CPU path is appropriate; real-speech calibration is still a pending Golden gate | `KEEP_OURS` |
| SYSTRAN faster-whisper | local Whisper inference and generator-based transcription | Windows CPU/local deployment is practical; upstream model inference is not a full turn-taking engine | `KEEP_OURS` |
| openWakeWord | offline wake-word/phrase detection and streaming examples | model/runtime can run locally; capture lifecycle remains application-owned | `REFERENCE_ONLY` |
| Wyoming / OHF-Voice | JSONL plus PCM protocol, local wake/VAD/STT/TTS services | useful as an isolated local adapter boundary; no auth/encryption by design, so it cannot be a direct privileged boundary | `REFERENCE_ONLY` |
| wyoming-faster-whisper | local service, VAD endpointing option, cache-first model behavior | service deployment adds process/protocol lifecycle; not needed for current in-process STT | `REFERENCE_ONLY` |
| wyoming-piper | local Piper TTS service with streaming option | local TTS is credible, but voice/model licensing remains separate | `REFERENCE_ONLY` |

## Local/free capability matrix

| Capability | Free/open source option found | Local without mandatory cloud | Evidence and restriction |
| --- | --- | --- | --- |
| Windows microphone | `python-sounddevice` / PortAudio | Yes | Golden already validated the real USB microphone path; framework portability is not a Windows guarantee |
| VAD | Silero VAD, Pipecat Silero analyzer, Wyoming VAD events | Yes | local model and CPU path; thresholds and real speech behavior remain Golden-owned |
| Wake word | openWakeWord / Wyoming openWakeWord | Yes | caller supplies PCM/model; no conversation lifecycle or security boundary |
| STT | faster-whisper, Wyoming faster-whisper, framework adapter | Yes | local model artifact and runtime; streaming orchestration must be designed separately |
| TTS | Piper / Wyoming Piper / framework local service | Yes | local voices are possible; model/voice terms and artifact provenance are separate gates |
| LLM | Ollama or another local endpoint through ModelRouter | Yes | framework can call a local endpoint, but Golden ModelRouter remains policy owner |
| LLM streaming handoff | Pipecat processors or LiveKit activity/session patterns | Yes in principle | orchestration pattern, not proof that all providers are local |
| Barge-in | local VAD plus output cancellation in Golden/Pipecat/LiveKit | Yes | acoustic echo cancellation is not supplied by the reviewed stack as a free turnkey Windows guarantee |
| RTC/network transport | LiveKit self-hosted or cloud; Pipecat WebRTC transports | Not necessarily | adds infrastructure and a second media/session boundary; not required for local desktop |
| Paid API | none required by the frameworks themselves | Yes | provider choice can introduce paid/cloud requirements |

Conclusion: `LOCAL_MIC_SUPPORTED: PARTIALLY`, `LOCAL_VAD_SUPPORTED: YES`,
`LOCAL_STT_SUPPORTED: YES`, `LOCAL_TTS_SUPPORTED: YES`,
`LOCAL_LLM_SUPPORTED: YES`, `MANDATORY_PAID_API: NO`,
`MANDATORY_CLOUD: NO_FOR_LOCAL_PROVIDER_PATH`.

## Golden current baseline

Golden is stronger than a blank framework integration in the boundaries that
matter for this project:

- `jarvis_core/realtime_voice/audio_input.py` owns one native-rate
  `sounddevice.RawInputStream`, logical device resolution, a generation guard,
  a conversion worker, bounded raw/canonical queues, diagnostics, and restart.
- `jarvis_core/realtime_voice/audio_queue.py` defines bounded async input,
  cancellation, flush, and drop-oldest backpressure.
- `jarvis_core/realtime_voice/vad.py` contains the local `SileroVADAdapter`.
- `jarvis_core/realtime_voice/hybrid_endpoint.py` adds a post-VAD hangover
  boundary and speech-resumed cancellation behavior.
- `jarvis_core/realtime_voice/integration.py` routes VAD, endpointing, utterance
  buffering, STT cancellation, transcript acceptance, and state transitions.
- `jarvis_core/voice_service.py` remains the owner of VoiceService, Core
  handoff, cancellation, session identity, and the single injected audio/TTS
  pipeline.
- `jarvis_core/stt_faster_whisper.py` provides a fail-closed local provider
  with approved artifact validation and cancellation-aware utterance STT.
- `jarvis_core/voice_tts.py` defines provider-neutral `PcmAudioChunk`, TTS and
  output protocols, identity `(session, turn, generation)`, queue boundaries,
  cancellation, and stale-output rejection.
- `jarvis_core/audio_output.py` owns one bounded PCM output stream with flush,
  abort/close, format/identity guards, and bounded recovery.
- `jarvis_core/streaming/turn_manager.py` is the single turn/cancellation
  authority.

Golden therefore has a credible local foundation, but the official status
remains partial because the real speech VAD gate was intentionally not run in
this audit and because current voice paths still include a legacy
`jarvis_core/streaming/tts_pipeline.py` Edge TTS path alongside the newer
provider-neutral path. That split is an integration risk, not permission to
rewrite it in this research phase.

## What the frameworks actually provide

### Pipecat

Source-level review covered the frame processor guidance, local transport,
output transport queue, interruption frames, and user-turn strategies.

Useful properties:

1. A pipeline is a sequence of frame processors. `StartFrame`, system frames,
   user-turn frames, output frames, and `InterruptionFrame` make lifecycle and
   cancellation observable.
2. A VAD/user-turn strategy can broadcast an interruption upstream and
   downstream. Queued frames have an explicit interruptible flag, which is a
   useful model for Golden's generation and playback identity checks.
3. Slow work is expected to run in tracked background tasks rather than inside
   `process_frame`, preserving VAD responsiveness. This is directly relevant to
   streaming STT and TTS handoff.
4. `LocalAudioTransport` uses PortAudio and supports local I/O, but the source
   does not establish Golden's Windows device identity, recovery, SecurityManager,
   or Core ownership semantics.
5. Provider breadth is not equivalent to local privacy. Each service and model
   must still be checked for cloud calls, model terms, credentials, and output
   ownership.

Decision: adapt frame/processor and interruption patterns only. Do not import a
second pipeline owner or let Pipecat call tools/Core outside a Golden-owned
adapter.

### LiveKit Agents

Source-level review covered `AgentSession`, `AgentActivity`, turn handling,
interruption handling, and terminal-mode guidance.

Useful properties:

1. `AgentSession` explicitly joins audio/video/text I/O, VAD, STT, TTS, LLM,
   turn detection, endpointing, interruptions, and tool orchestration.
2. `AgentActivity` models current speech, input speech start/stop, interruption,
   preemptive generation, false interruption recovery, and stale/cleared audio.
3. The framework exposes VAD interruption and adaptive interruption concepts,
   and can use semantic turn detection. These are the most valuable references
   for future Golden semantic turns.
4. The repository documents `python myagent.py console` for local terminal audio
   I/O, but production usage is commonly an agent server connected to LiveKit
   rooms. This is not evidence of a drop-in PySide6/Windows desktop layer.
5. The framework is Apache-2.0, while LiveKit turn-detection models have a
   separate LiveKit Model License. Code license approval does not clear model
   use.

Decision: adapt the state vocabulary, interruption timing ideas, and semantic
turn evaluation patterns. Do not adopt AgentSession as a second session owner,
RTC gateway, or Core/tool authority.

### Wyoming and component specialists

Wyoming is a peer-to-peer JSONL plus PCM protocol. It documents local events
for wake word, VAD, STT, TTS, and streaming text. `wyoming-faster-whisper` and
`wyoming-piper` demonstrate local service packaging, while openWakeWord
provides a local detector library.

This is useful for process isolation and provider contracts, but Wyoming has no
authentication or encryption by design and is intended for a trusted network.
It must therefore remain behind a Golden adapter if ever used. Its Linux and
Home Assistant orientation also means it is not proof of a Windows desktop
runtime.

`SYSTRAN/faster-whisper` is a strong local inference reference and supports
generator-based transcription and community live integrations. Golden already
has its own approved artifact and cancellation boundary, so direct replacement
is unnecessary.

## Component decisions

The following decisions are architectural classifications only. They do not
authorize implementation or donor source copying.

| Component | Decision | Evidence/rationale |
| --- | --- | --- |
| `MIC_INPUT` | `KEEP_OURS` | Real Windows provider, logical device selection, generation guard, and recovery already exist. |
| `AUDIO_OUTPUT` | `KEEP_OURS` | Golden output provider has bounded PCM, identity/format guards, flush, abort, and recovery. |
| `VAD` | `KEEP_OURS` | Silero adapter is local and already integrated with Golden state. |
| `ENDPOINTING` | `KEEP_OURS` | Hybrid endpoint is the current controlled boundary; do not add a competing endpointer. |
| `TURN_MANAGER` | `KEEP_OURS` | One authoritative turn/cancellation owner is a safety invariant. |
| `SEMANTIC_TURN_DETECTION` | `ADAPT` | Study LiveKit/Pipecat semantic/backchannel patterns behind a Golden-owned contract. |
| `STT_PROVIDER` | `KEEP_OURS` | Approved local faster-whisper provider and artifact policy already exist. |
| `STT_STREAMING_ORCHESTRATION` | `ADAPT` | Adapt background-task and partial/final event patterns; keep provider/Core boundaries. |
| `LLM_STREAMING_HANDOFF` | `KEEP_OURS` | ModelRouter/Core policy must remain authoritative; adapt only scheduling patterns. |
| `TTS_PROVIDER_ABSTRACTION` | `KEEP_OURS` | Golden `TextToSpeechProvider` and `PcmAudioChunk` are already provider-neutral. |
| `TTS_STREAMING_ORCHESTRATION` | `ADAPT` | Borrow sentence/chunk ordering and tracked task patterns; resolve legacy/new path split later. |
| `PLAYBACK_QUEUE` | `KEEP_OURS` | Golden queue identity, backpressure, flush, and output ownership are explicit. |
| `BARGE_IN` | `KEEP_OURS` | Golden preserves TurnManager and cancellation ownership; compare external race tests only. |
| `SELF_TRIGGER_HANDLING` | `KEEP_OURS` | Current explicit policy is safer than claiming acoustic source separation. |
| `AEC` | `REFERENCE_ONLY` | No reviewed source proves a free, Windows-ready AEC solution for this hardware path. |
| `DEVICE_RECOVERY` | `KEEP_OURS` | Windows-specific identity and recovery are already a Golden requirement. |
| `SESSION_LIFECYCLE` | `ADAPT` | Borrow framework lifecycle/checkpoint vocabulary without creating a second session owner. |

Allowed classifications are intentionally limited to the requested vocabulary:
`KEEP_OURS`, `PORT`, `ADAPT`, `REIMPLEMENT_PATTERN`, `REFERENCE_ONLY`, and
`REJECT`. No component received `PORT` because no donor contract is a safe
drop-in for the Golden boundaries.

## Best reference by remaining problem

| Remaining problem | Best reference | What can be learned | What must remain Golden |
| --- | --- | --- | --- |
| semantic end of turn | LiveKit turn handling; Pipecat user-turn strategies | explicit endpoint/turn policy and background inference | thresholds, acceptance, session and Core dispatch |
| interrupt propagation | Pipecat `InterruptionFrame`; LiveKit `AgentActivity` | broadcast cancellation and stale output clearing | TurnManager, output identity, SecurityManager |
| sentence-level streaming | Pipecat processor/task model; Hermes voice mode | do not block input while synthesizing/playing | provider selection and local/privacy policy |
| local output abort | ndunl075/Jarvis audio pipeline | cancel provider, drain queue, abort output together | Golden `VoiceAudioPipeline` and output owner |
| local voice service composition | Wyoming | normalized PCM/event boundaries and process isolation | auth, encryption, audit, Core and no second brain |
| wake lifecycle | OpenClaw/Hermes/openWakeWord | lease/state reconciliation and detector reset | Golden session/security/audit boundaries |

## Options

### Option A: Keep Golden

Technically viable and lowest risk. Golden already owns the Windows capture,
VAD, endpoint, session, STT, output, cancellation, and security seams. The
cost is implementing semantic turn detection and richer streaming orchestration
in-house.

### Option B: Hybrid

Recommended. Keep Golden as the brain and owner, then adapt narrow patterns:
Pipecat-style non-blocking frame/task orchestration and interruption
propagation, plus LiveKit-style semantic turn and false-interruption
evaluation. The adapter would expose Golden events and never create a second
Core, Gateway, SecurityManager, VoiceService, or device owner.

### Option C: Framework engine

Not recommended now. Replacing Golden with Pipecat or LiveKit would duplicate
session, playback, cancellation, provider, and tool ownership. LiveKit also
adds RTC/server infrastructure and model-license surfaces; Pipecat still
requires Golden-specific Windows and security integration. Migration cost and
regression risk exceed the evidence-based benefit.

## Recommendation

`RECOMMENDATION: HYBRID`

The hybrid must be a pattern-level adapter, not framework sovereignty:

1. Golden remains the only Core, SecurityManager, AuditLog, VoiceService,
   TurnManager, device owner, and output owner.
2. First adapt semantic turn/false-interruption contracts in a non-hardware
   test harness.
3. Keep local faster-whisper, local Silero, and the existing TTS/output
   contracts. Do not add a remote provider as a shortcut.
4. Require explicit evidence for partial/final STT handoff, sentence TTS
   ordering, playback flush, generation invalidation, and session teardown.
5. Only after that design review authorize the separate real-speech VAD gate.

`EXTERNAL_FRAMEWORK_SUBSTANTIALLY_REDUCES_WORK: YES_FOR_ORCHESTRATION_ONLY`
`EXTERNAL_FRAMEWORK_REPLACES_GOLDEN_CORE: NO`
`ADAPT_FRAMEWORK_FIRST: YES`
`REAL_SPEECH_VAD_GATE_RUN: NO`

## Engineering impact

| Area | Impact | Risk |
| --- | --- | --- |
| production runtime | none in this audit | none introduced |
| dependencies | none added | no supply-chain change |
| Windows audio | unchanged | current real-device path remains authoritative |
| latency | potential future improvement from non-blocking orchestration | must measure before adoption |
| cancellation | future adapter must preserve generation and queue invalidation | stale audio regression risk |
| security | no framework may bypass SecurityManager/Core | high if framework is made authoritative |
| licensing | code/model/voice terms remain separate | medium; especially LiveKit models and TTS voices |
| operations | LiveKit/Wyoming may add processes or transport | medium; avoid unless a concrete need is proven |

## Required safety invariants

```yaml
PRODUCTION_CODE_CHANGED: NO
DEPENDENCIES_INSTALLED: NO
MODELS_DOWNLOADED: NO
MICROPHONE_OPENED: NO
AUDIO_PLAYED: NO
WINDOWS_SETTINGS_CHANGED: NO
DEVICE_REGISTRY_TOUCHED: NO
TASK_DB_SCHEMA_MIGRATION: NONE
SECOND_CORE_REQUIRED: NO
SECOND_SECURITY_MODEL_REQUIRED: NO
PUSH: NO
```

## Next decision gate

```yaml
NEXT_GATE: VOICE_CONVERSATION_ADAPTER_DESIGN_REVIEW
NEXT_STEP: Define a Golden-owned semantic-turn and streaming-orchestration adapter, with offline tests for cancellation, partial/final STT, sentence ordering, playback flush, and stale-generation rejection.
REAL_SPEECH_VAD_GATE: DEFERRED
HUMAN_SPEECH_REQUIRED_NOW: NO
```

No real speech VAD gate was run because this audit explicitly prohibited it.
No human speech or synthetic event is used as a substitute.

## Official source references

- [Pipecat repository](https://github.com/pipecat-ai/pipecat)
- [Pipecat contributor architecture notes](https://github.com/pipecat-ai/pipecat/blob/main/AGENTS.md)
- [Pipecat BSD-2-Clause license](https://github.com/pipecat-ai/pipecat/blob/main/LICENSE)
- [LiveKit Agents repository](https://github.com/livekit/agents)
- [LiveKit AgentSession source](https://github.com/livekit/agents/blob/main/livekit-agents/livekit/agents/voice/agent_session.py)
- [LiveKit AgentActivity source](https://github.com/livekit/agents/blob/main/livekit-agents/livekit/agents/voice/agent_activity.py)
- [LiveKit Agents license and terminal mode](https://github.com/livekit/agents/blob/main/AGENTS.md)
- [LiveKit model license](https://github.com/livekit/agents/blob/main/MODEL_LICENSE)
- [python-sounddevice documentation](https://python-sounddevice.readthedocs.io/en/latest/)
- [openWakeWord repository](https://github.com/dscripka/openWakeWord)
- [SYSTRAN faster-whisper repository](https://github.com/SYSTRAN/faster-whisper)
- [Wyoming protocol](https://github.com/OHF-Voice/wyoming)
- [Wyoming faster-whisper](https://github.com/OHF-Voice/wyoming-faster-whisper)
- [Wyoming Piper](https://github.com/OHF-Voice/wyoming-piper)
- [Wyoming openWakeWord](https://github.com/OHF-Voice/wyoming-openwakeword)
- [Wyoming security model](https://github.com/OHF-Voice/wyoming/blob/main/SECURITY.md)

## Audit result

```yaml
JARVIS_VOICE_PHASE: PARTIAL
VOICE_CONVERSATION_STACK_AUDIT: PASS_WITH_RESTRICTIONS
BASELINE: 6b4c3e9
FREE_OPEN_SOURCE_NATURAL_VOICE_STACK_EXISTS: PARTIALLY
LOCAL_MIC_SUPPORTED: PARTIALLY
LOCAL_VAD_SUPPORTED: YES
LOCAL_STT_SUPPORTED: YES
LOCAL_TTS_SUPPORTED: YES
LOCAL_LLM_SUPPORTED: YES
MANDATORY_PAID_API: NO
MANDATORY_CLOUD: NO_FOR_LOCAL_PROVIDER_PATH
JARVIS_CORE_CAN_REMAIN_BRAIN: YES
RECOMMENDATION: HYBRID
FILES_CREATED: docs/architecture/JARVIS_VOICE_CONVERSATION_STACK_AUDIT.md
FILES_MODIFIED: NONE
COMMITS: documentation-only commit after verification
PUSH: NO
```
