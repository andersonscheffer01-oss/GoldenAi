# Jarvis Voice Donor Audit 2

Status: `PASS_WITH_RESTRICTIONS`
Research date: `2026-09-27`
Scope: read-only reuse audit for TTS, audio output, turn-taking, and barge-in.
Baseline: `e815107`

No runtime feature was implemented. No donor source was copied into Golden.
No package, model, provider, microphone, speaker, or TTS API was used.

## Donors reviewed

| Donor | Repository | Current main revision checked | License evidence | Result |
| --- | --- | --- | --- | --- |
| OpenClaw | https://github.com/openclaw/openclaw | `32ba81a40d9d57065280aef6a25fed0b39223f21` | MIT root; third-party notices remain separate | broad reference only |
| Hermes Agent | https://github.com/NousResearch/hermes-agent | `062dc1e7f0f5faa5114b4d98b94c48f5ec5df36f` | MIT root; optional/provider dependencies need separate review | strongest contract/orchestration reference |
| Jarvis donor A | https://github.com/ndunl075/Jarvis | `e21ce95f40d8f653eed80cfa4d515c89f795edfb` | MIT root | strongest local playback/barge-in donor |
| Jarvis donor B | https://github.com/ONEPUNCHMAN411/Jarvis | `9bbb3bf26bb4cdea578dd58d26eb74871445fade` | repository license and dependency notices require file-level review | useful Windows queue pattern, weaker privacy fit |

The two Jarvis repositories were shallow-cloned outside the Golden checkout for
source inspection only. The current branch heads above were checked with
`git ls-remote`; no donor checkout was added to the Golden repository.

## Golden baseline

Golden already has a substantial voice output path:

- `jarvis_core/streaming/tts_pipeline.py`: sentence-level Edge TTS synthesis,
  ordered chunks, cancellation, and temporary audio files;
- `jarvis_core/streaming/audio_player.py`: Windows WPF `MediaPlayer` playback
  through an owned subprocess with targeted termination;
- `jarvis_core/streaming/turn_manager.py`: one turn authority and cancellation
  events;
- `jarvis_core/realtime_voice/barge_in.py` and `voice_service.py`: grace period,
  self-audio protection, VAD monitoring, pre-roll, follow-up capture, and turn
  cancellation;
- existing tests cover ordering, cancellation, playback stop, stale turns,
  barge-in handoff, session preservation, and no orphan playback process.

Golden therefore remains the owner of the voice lifecycle. Donors supply narrow
patterns only.

## Findings by donor

### OpenClaw

Relevant sources include `src/tts/`, `docs/tools/tts/`, Talk/realtime voice
documentation, client playback implementations, and Talk interruption tests.
OpenClaw has a mature provider-resolution surface, multiple TTS providers,
provider-native streaming, media persistence, and multi-platform Talk clients.
Its Talk path supports interruption and separate realtime-provider modes.

The architecture is distributed across Gateway, channel delivery, and native
clients. It is not a single Windows `AudioOutputProvider`, and its provider,
media, gateway, and client contracts are substantially broader than Golden's
single-core boundary.

Decision: `REFERENCE_ONLY` for overall Talk/playback architecture; `ADAPT` for
provider capability vocabulary and test cases after a Jarvis-owned contract
exists. Do not port the Gateway, client audio stack, or provider registry.

### Hermes Agent

Relevant sources include `agent/tts_provider.py`, `agent/tts_registry.py`,
`hermes_cli/voice.py`, desktop voice mode, and the official voice-mode guide.

The TTS provider ABC cleanly separates `synthesize()` from optional `stream()`.
It also exposes voice metadata, warm/release lifecycle hooks, output format,
and provider compatibility. Hermes desktop voice mode has sentence-level
streaming, provider-native chunk streaming where available, a per-reply speech
stream, and documented barge-in during thinking and playback. Its detector
uses a calibrated quiet-room floor, a playback grace period, and a separate
voice-chat mode.

The implementation is tied to Hermes Gateway/Desktop configuration, provider
credentials, and a broader distributed runtime. It cannot replace Golden's
VoiceService, SecurityManager, or cancellation authority.

Decision: `ADAPT` the narrow provider contract and lifecycle vocabulary;
`REFERENCE_ONLY` for desktop full-duplex orchestration. No code port is
authorized by this audit.

### Jarvis donor A: ndunl075/Jarvis

Relevant sources:

- `jarvis/audio/protocols.py`
- `jarvis/audio/tts.py`
- `jarvis/audio/pipeline.py`
- `jarvis/audio/vad.py`
- `tests/audio/test_tts.py`
- `tests/audio/test_pipeline.py`

This is the strongest component-level donor for local output. `PiperTTS`
accepts sentence-stream input, synthesizes in a worker thread, writes PCM to a
PortAudio output stream, and exposes an explicit `cancel()` contract.
Cancellation sets a thread event, drains queued audio, and calls
`RawOutputStream.abort()` so buffered audio is discarded immediately. The
pipeline owns one response chain, cancels the TTS and response task on
barge-in, and returns to listening. Its tests cover cancellation and pipeline
state transitions. The donor also has Windows WASAPI/MME selection and output
restart handling.

Important limitations: the donor's default voice is English Piper, the queue
and PortAudio implementation are not a drop-in Golden abstraction, AEC is
explicitly deferred, and the donor has its own state machine and lifecycle.

Decision: `ADAPT` the narrow cancellation/output ownership pattern and
`REIMPLEMENT_PATTERN` the state-transition tests. Do not port the provider,
Piper model, donor state machine, or dependency graph.

### Jarvis donor B: ONEPUNCHMAN411/Jarvis

Relevant sources:

- `jarvis/voice/tts.py`
- `jarvis/voice/audio_player.py`
- `jarvis/voice/voice_manager.py`
- `jarvis/voice/vad.py`
- `jarvis/voice/desktop_audio.py`

The donor has Windows-oriented audio code, sentence-level synthesis, a bounded
`asyncio.Queue(maxsize=5)` between synthesis and playback, VAD during playback,
and a practical interrupt path that calls `AudioPlayer.stop()` and carries a
small audio buffer into the next capture. It uses Edge TTS with an optional
`pyttsx3` fallback and `sounddevice` playback; desktop loopback support uses
`pyaudiowpatch` when installed.

The default Edge TTS path is remote, its fallback/provider ownership is less
explicit than Golden's target contract, and the interrupt path does not expose
three independently cancellable operations for LLM generation, TTS
synthesis, and playback.

Decision: `REFERENCE_ONLY` for the Windows queue and handoff behavior;
`REIMPLEMENT_PATTERN` for tests. Reject direct provider/dependency import for
the current local-first privacy gate.

## Component matrix

| Component | OpenClaw | Hermes | Jarvis A | Jarvis B | Golden decision |
| --- | --- | --- | --- | --- | --- |
| TTS provider abstraction | mature TS/provider registry | Python ABC | protocol-level | concrete class | `ADAPT` Hermes vocabulary; `KEEP_OURS` runtime |
| Local TTS | local client/provider options | local CLI/provider options | Piper | pyttsx3 fallback only | `REFERENCE_ONLY`; provider selection is a later gate |
| Remote TTS | many | many | no default cloud | Edge TTS | `KEEP_OURS` current provider boundary; privacy review required |
| Streaming TTS | provider/client dependent | native chunks plus sentence pipeline | sentence/PCM streaming | sentence synthesis queue | `ADAPT` narrow stream contract |
| Audio output abstraction | client-specific | desktop/client-specific | `TextToSpeech` plus output stream | `AudioPlayer` | `ADAPT` output ownership pattern |
| Speaker ownership | per client/channel | desktop or gateway path | one pipeline owner | one manager/player | `KEEP_OURS` VoiceService owner |
| PCM playback | native-client dependent | provider/client dependent | `RawOutputStream` | decoded `sounddevice` playback | `ADAPT` only after Golden contract |
| Bounded playback queue | media/client dependent | per-reply stream resources | bounded frame queue; audio queue needs review | `asyncio.Queue(maxsize=5)` | `ADAPT` bounded queue semantics |
| Backpressure/order | client/stream resource paths | per-reply audio clock | ordered chunks and bounded ingress | queue order | `KEEP_OURS` plus tests |
| Playback cancellation | client-specific | Talk/client stop | `abort()` and drain | `sd.stop()` | `ADAPT` immediate drain/abort pattern |
| TTS cancellation | provider/session dependent | stream release/provider cancellation | event plus abort | flag plus synth loop stop | `KEEP_OURS` turn cancellation; add narrow contract later |
| Turn-taking | Talk/realtime clients | explicit chained/full-duplex modes | state machine | voice manager status | `KEEP_OURS` existing state machine |
| Response generation cancellation | gateway/client dependent | interrupt event and follow-up | response task cancel | not independently modeled | `KEEP_OURS` TurnManager |
| Session isolation | gateway/session keys | gateway/profile/session | lifecycle/state | manager instance | `KEEP_OURS` session/epoch guards |
| Stale audio suppression | client/media lifecycle | per-reply stream ownership | cancel drains old audio | queue stops on flag | `KEEP_OURS` plus output epoch |
| Barge-in | Talk mode | real desktop full-duplex | VAD -> cancel TTS/task -> listen | VAD -> stop player -> capture | `KEEP_OURS`; compare tests |
| VAD during playback | client-dependent | calibrated playback-phase detector | VAD path, AEC deferred | VAD path | `KEEP_OURS` current monitor |
| Echo/self-trigger | platform/client controls | noise-floor and grace | grace/headset; no AEC | threshold/noise calibration | `REIMPLEMENT_PATTERN`, no AEC claim |
| Device selection/recovery | platform-specific | client/platform-specific | WASAPI/MME fallback/reopen | configured sounddevice device | `ADAPT` narrow Windows recovery |
| Shutdown/restart | client lifecycle | provider/session lifecycle | load/unload and cancel | manager shutdown | `KEEP_OURS` VoiceService lifecycle |
| Tests | extensive TS/native tests | provider/desktop voice tests | audio cancellation/pipeline tests | manager/voice tests | `REIMPLEMENT_PATTERN` selected tests |
| Windows support | not uniform | desktop path, not Golden fit | explicit WASAPI/MME | explicit Windows audio | `ADAPT` only targeted patterns |

## Required reuse decisions

```yaml
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

```yaml
MOSTLY_REUSE_COMPONENTS: []
ADAPT_EXISTING_COMPONENTS:
  - Hermes TTSProvider stream/synthesize capability split
  - ndunl075 PiperTTS immediate abort and queue-drain pattern
  - ndunl075 Windows WASAPI/MME output selection and reopen handling
  - ONEPUNCHMAN411 bounded sentence audio queue and handoff tests
REIMPLEMENT_PATTERN_COMPONENTS:
  - donor barge-in race and late-audio tests
  - output-aware VAD/evidence hooks without claiming AEC
REFERENCE_ONLY_COMPONENTS:
  - OpenClaw distributed Talk/Gateway/client voice architecture
  - Hermes full-duplex desktop mode
  - donor state machines and provider registries
REJECTED_COMPONENTS:
  - second Core or second security model
  - donor scheduler/session owner
  - automatic remote TTS/provider installation
  - donor cloud TTS as an unapproved local-first default
```

## TTS and audio output assessment

```yaml
EXISTING_GOLDEN_TTS: YES
DONOR_TTS_FOUND: YES
BEST_REUSE_SOURCE: Hermes Agent plus ndunl075/Jarvis
SOURCE_MODULE: agent/tts_provider.py; jarvis/audio/tts.py
TTS_CLASSIFICATION: ADAPT
TTS_REUSE_LEVEL: ADAPT_EXISTING
LOCAL_TTS_OPTIONS_FOUND: Piper; Hermes local command/provider surfaces
REMOTE_TTS_OPTIONS_FOUND: OpenClaw provider catalog; Hermes providers; Edge TTS in donor B
PT_BR_SUPPORT: not established by the reviewed local donors; do not infer voice availability
STREAMING_TTS_AVAILABLE: YES, but not uniformly provider-native
LICENSE_GATE: PASS_WITH_RESTRICTIONS; code/model/voice/dependency licenses remain separate
DEPENDENCY_IMPACT: future provider-specific packages/model assets; none added in this audit
```

The correct next abstraction is a Golden-owned `TextToSpeechProvider` with
separate complete synthesis and optional incremental audio stream operations.
It must return ownership metadata but must not execute tools, authorize actions,
call Core, or create a second VoiceService.

```yaml
DONOR_AUDIO_OUTPUT_FOUND: YES
BEST_REUSE_SOURCE: ndunl075/Jarvis
SOURCE_MODULE: jarvis/audio/tts.py
AUDIO_OUTPUT_CLASSIFICATION: ADAPT
AUDIO_OUTPUT_REUSE_LEVEL: ADAPT_EXISTING
SINGLE_OUTPUT_OWNER_COMPATIBLE: YES, after wrapping behind VoiceService
BOUNDED_QUEUE: PARTIAL; explicit in donor B ingress, not a universal donor contract
BACKPRESSURE: YES at selected ingress boundaries
CANCELLATION: YES, strongest in donor A
SHUTDOWN: YES
RESTART: YES in donor A output path
DEVICE_RECOVERY: PARTIAL, strongest in donor A Windows output selection
```

## Turn-taking and barge-in assessment

```yaml
DONOR_TURN_TAKING_FOUND: YES
BEST_REUSE_SOURCE: Golden existing state machine, informed by Hermes and donor A
TURN_TAKING_CLASSIFICATION: KEEP_OURS
TURN_TAKING_REUSE_LEVEL: MOSTLY_REUSE
STATE_MACHINE_FOUND: YES in all voice-capable donors, with different ownership models
COMPATIBLE_WITH_EXISTING_GOLDEN_STATE_MACHINE: donor patterns only; direct import NO
RESPONSE_CANCELLATION: YES in Golden and donor A/Hermes; donor B is partial
SESSION_ISOLATION: YES in Golden/Hermes; donor A/B are lifecycle-local
STALE_OUTPUT_SUPPRESSION: partial in donors; Golden session/turn/epoch guards remain authoritative
```

```yaml
DONOR_BARGE_IN_FOUND: YES
BEST_REUSE_SOURCE: ndunl075/Jarvis, with Hermes detector notes
SOURCE_MODULE: jarvis/audio/pipeline.py; agent desktop voice-mode docs
BARGE_IN_CLASSIFICATION: KEEP_OURS
BARGE_IN_REUSE_LEVEL: MOSTLY_REUSE
USER_SPEECH_DURING_PLAYBACK: YES
PLAYBACK_CANCEL: YES
TTS_CANCEL: YES in donor A; partial in donor B
LLM_CANCEL: YES in donor A/Hermes; Golden TurnManager remains owner
OLD_AUDIO_FLUSH: YES in donor A; queue/stop in donor B
NEW_TURN_START: YES in donor A/B/Hermes
RACE_HANDLING: tests found in donor A and Golden; cross-component behavior still needs Golden tests
TESTS_FOUND: yes, including cancellation, ordering, barge-in, state transitions, and shutdown paths
```

No donor provides a license to claim full-duplex acoustic echo cancellation.
The real reusable pattern is layered: detect speech, cancel playback, cancel
TTS, cancel generation, invalidate old output, and start the next turn. These
operations must remain separately observable in Golden.

## Privacy, security, and dependency gates

| Surface | Finding | Golden decision |
| --- | --- | --- |
| TTS text | Donor providers may be local, command-based, or cloud | response text remains inside VoiceService policy; external TTS requires a future approval gate |
| Audio output | local playback is safe only when owned by the active VoiceService | one output owner; no concurrent speaker owners |
| Provider/plugin loading | donor registries can load extension code | no donor plugin loader; SecurityManager and dependency review remain authoritative |
| Model/voice assets | Piper and other local voices have separate model/voice terms | no model or voice asset selected or downloaded |
| Windows native audio | PortAudio/WASAPI and WPF have different failure modes | future adapter must preserve bounded failure and restart behavior |
| TTS output | must never execute tools or call Core independently | hard Golden boundary |

```yaml
VOICE_SERVICE_REMAINS_OWNER: YES
EXISTING_STATE_MACHINE_PRESERVED: YES
EXISTING_CANCELLATION_PRESERVED: YES
SECURITYMANAGER_PRESERVED: YES
SECOND_CORE_REQUIRED: NO
SECOND_LLM_LOOP_REQUIRED: NO
SECOND_SECURITY_MODEL_REQUIRED: NO
DONOR_FRAMEWORK_REQUIRED: NO
```

## Effort reduction

```yaml
TTS: ADAPT_EXISTING
AUDIO_OUTPUT: ADAPT_EXISTING
TURN_TAKING: MOSTLY_REUSE
BARGE_IN: MOSTLY_REUSE
BUILD_FROM_SCRATCH_AVOIDABLE: YES for cancellation, ordered output, and barge-in sequencing; provider selection and PT-BR quality remain separate gates
```

The donors do not remove the need for Golden glue. The shortest safe path is to
keep the existing VoiceService and add contracts around it in this order:

1. Define a Golden-owned `TextToSpeechProvider` and `AudioOutputProvider` with
   complete synthesis, optional stream, cancellation, flush, and lifecycle
   semantics.
2. Adapt the current Edge TTS and WPF path behind those contracts without
   changing the current provider policy.
3. Add deterministic bounded queue, late-audio, shutdown, device-recovery,
   and cancel-during-synthesis/playback tests.
4. Add a separately approved local TTS provider only after PT-BR voice,
   model-license, packaging, and benchmark gates pass.
5. Keep barge-in orchestration in VoiceService/TurnManager and make playback,
   TTS, and LLM cancellation independently observable.

## Expected final report

```yaml
JARVIS_VOICE_PHASE: IN_PROGRESS
VOICE_DONOR_AUDIT_2: PASS_WITH_RESTRICTIONS
BASELINE: e815107
RESEARCH_DATE: 2026-09-27
OPENCLAW: reviewed; current main 32ba81a; REFERENCE_ONLY overall
HERMES: reviewed; current main 062dc1e; ADAPT provider contract, REFERENCE_ONLY full-duplex runtime
JARVIS_DONOR_A: reviewed; current main e21ce95; ADAPT output/cancel patterns
JARVIS_DONOR_B: reviewed; current main 9bbb3bf; REFERENCE_ONLY queue/handoff patterns
EXTERNAL_SPECIALIZED_PROJECTS: NONE
GOLDEN_RUNTIME_MODIFIED: NO
DONOR_CODE_COPIED_INTO_GOLDEN: NO
NEW_PACKAGES_INSTALLED: NONE
MODEL_DOWNLOADS: NO
MICROPHONE_OPENED: NO
AUDIO_PLAYBACK_STARTED: NO
TTS_API_CALLS: NO
TASK_DB_SCHEMA_MIGRATION: NONE
TASK_DB_SCHEMA_VERSION: 5
DEVICE_REGISTRY_TOUCHED: NO
SECRET_SCAN: PASS
GIT_DIFF_CHECK: PASS
```

`TTS_PROVIDER_REUSE_AVAILABLE`: YES, as a contract/pattern only.
`AUDIO_OUTPUT_REUSE_AVAILABLE`: YES, as a narrow cancellation/output pattern.
`PLAYBACK_QUEUE_REUSE_AVAILABLE`: PARTIAL.
`TTS_CANCELLATION_REUSE_AVAILABLE`: YES, donor A pattern; Golden owner retained.
`PLAYBACK_CANCELLATION_REUSE_AVAILABLE`: YES, donor A abort/drain pattern.
`TURN_TAKING_REUSE_AVAILABLE`: NO direct import; Golden is stronger fit.
`BARGE_IN_REUSE_AVAILABLE`: YES as tested sequencing patterns; Golden already has it.
`ECHO_SELF_TRIGGER_REUSE_AVAILABLE`: PARTIAL; no donor proved AEC.
`DEVICE_RECOVERY_REUSE_AVAILABLE`: PARTIAL, donor A Windows patterns.

## Sources

- OpenClaw repository: https://github.com/openclaw/openclaw
- OpenClaw TTS guide: https://github.com/openclaw/openclaw/blob/main/docs/tools/tts.md
- OpenClaw media playback: https://github.com/openclaw/openclaw/blob/main/docs/nodes/media-playback.md
- Hermes Agent repository: https://github.com/NousResearch/hermes-agent
- Hermes voice mode: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/voice-mode.md
- Hermes TTS provider contract: https://github.com/NousResearch/hermes-agent/blob/main/agent/tts_provider.py
- Jarvis donor A: https://github.com/ndunl075/Jarvis
- Jarvis donor B: https://github.com/ONEPUNCHMAN411/Jarvis
- Golden voice architecture: `docs/architecture/JARVIS_VOICE_ARCHITECTURE.md`
- Golden STT baseline: `docs/architecture/JARVIS_STT_MODEL_DECISION.md`

## Next gate

`NEXT_GATE`: approve a Golden-owned TTS/output contract and deterministic
hardware-free regression suite.

`NEXT_STEP`: implementation may begin only in a separate authorized batch;
this audit itself changes no runtime behavior.
