# Jarvis Windows Audio Input Donor Audit

Baseline: `d126929`

Status: research-only gate. No production microphone code, dependency, Windows
setting, `device_registry.json`, database, model, or runtime behavior was
changed by this audit.

## Scope and evidence rules

This audit distinguishes four states:

- `IMPLEMENTATION_EXISTS`: source code was inspected.
- `IMPLEMENTATION_HAS_TESTS`: deterministic tests were found.
- `WINDOWS_REAL_HARDWARE_VALIDATED`: the implementation was exercised on real
  Windows hardware.
- `PRODUCTION_PROVEN`: there is evidence of sustained production use.

The last two states are not inferred from source code or mocked tests. Existing
Golden host API captures remain the evidence for this machine: MME can work but
repeatability is unresolved; DirectSound blocking capture is invalid; WASAPI
opens at a native rate but the confirmed sample was not usable; WDM-KS does not
support the blocking API used by the probe. This audit did not start another
capture and did not resume `MME_REPEATABILITY_VALIDATION`.

## Repositories and revisions reviewed

| Project | Revision / source | License | Maintenance signal | Scope result |
| --- | --- | --- | --- | --- |
| OpenClaw | `C:/JarvisDonors/openclaw`, `374f893b896c5445598d47541a4cc6b8d4eb2762` | MIT | Active multi-platform project | Apple-native speech/audio and RTC surfaces; no Windows PortAudio capture donor found |
| Hermes | `C:/JarvisDonors/hermes-agent`, `802ae8544b59f62c97468ed31b55f417ba12e9f2` | MIT | Active desktop/agent project | Wake ownership, client capture mode, lifecycle and tests; no mature Windows device-selection implementation found |
| `ndunl075/Jarvis` | `C:/JarvisDonorAudit/ndunl075-Jarvis`, `e21ce95f40d8f653eed80cfa4d515c89f795edfb` | MIT | Active donor snapshot | Best local capture pattern: callback, host API/name matching, native-rate framing, resampling, fallback and lifecycle tests |
| `ONEPUNCHMAN411/Jarvis` | `C:/JarvisDonorAudit/ONEPUNCHMAN411-Jarvis`, `9bbb3bf26bb4cdea578dd58d26eb74871445fade` | MIT | Active donor snapshot | Useful bounded queue, RMS/noise-floor and barge-in patterns; numeric device selection and no strong reconnect evidence |
| `python-sounddevice` | Official docs, current documentation | MIT | Maintained upstream documentation | PortAudio abstraction, callback streams and device/host-API enumeration; not a complete recovery policy |
| Pipecat | `pipecat-ai/pipecat`, official main sources | BSD-2-Clause | Active repository and examples | Local audio transport and turn/interruption pipeline patterns; transport framework, not a Windows device identity solution |
| LiveKit Agents | `livekit/agents`, official main sources | Apache-2.0 for framework | Active repository and SDK | Strong full-duplex/turn interruption semantics over RTC; not a local Windows PortAudio donor |
| openWakeWord | `dscripka/openWakeWord`, official repository | Apache-2.0 | Public releases and maintained repository | Wake-word frame contract/examples; not a device lifecycle or recovery implementation |

The donor source and project pages were inspected directly. No package was
installed and no donor source was copied into Golden.

## Golden current state

| Area | Current implementation | Assessment |
| --- | --- | --- |
| Audio input provider | `jarvis_core/realtime_voice/audio_input.py::AudioInputProvider` owns one `sounddevice.RawInputStream`, callback, bounded `AudioFrameQueue`, 16 kHz mono PCM16 and 480-sample frames. | Good ownership and frame contract; device is currently passed through as configured and stream open is fixed at 16 kHz. |
| Windows capture library | `sounddevice`/PortAudio. | Keep the existing library; the audit does not justify a dependency replacement. |
| Device selection | `device` may be a numeric selector or `None`; the provider probes devices/host APIs but does not yet resolve a stable name plus host API candidate. | Main gap exposed by the A/B results and USB index instability risk. |
| Recovery | Higher-level Golden recovery architecture exists, but the current provider does not itself re-enumerate a vanished device, reopen a bounded candidate, or verify that a replacement is the same logical device. | Needs one future recovery integration, not a second authority. |
| Signal health | Diagnostic harness records RMS, peak, frame cadence, drops and overflow; provider callback catches delivery failures. | Useful diagnostics, but stream-open is not yet equivalent to usable-signal health and there is no provider-level stuck-zero/reconnect guard. |
| VAD feed | `SileroVADAdapter` receives the Golden 16 kHz/mono/PCM16/30 ms contract; `HybridEndpoint` handles endpointing. | Keep ours. Do not replace VAD based on donor differences. |
| Legacy voice path | `jarvis_core/voice_service.py` still contains a separate blocking `sounddevice.InputStream` barge-in/follow-up path. | Important lifecycle split; audit recommends unifying ownership in a later implementation gate, without changing it here. |
| Safety and ownership | Golden `VoiceService`, `TurnManager`, cancellation and SecurityManager remain authoritative. | Keep ours. Donors are component references only. |

## Required matrix

| PROJECT | WINDOWS_SUPPORT | AUDIO_LIBRARY | HOST_API | CAPTURE_MODEL | DEVICE_SELECTION | DEVICE_RECOVERY | SIGNAL_HEALTH | VAD_INTEGRATION | FULL_DUPLEX | BARGE_IN | TESTS | LICENSE | DECISION |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OpenClaw | No Windows local capture evidence in reviewed sources | Apple Speech/AVAudio/RTC surfaces | Apple-native | Native platform pipelines | OS/device observers | Lifecycle/observer patterns | Platform-specific | Not a Golden-compatible Windows feed | RTC concepts | RTC concepts | Some observer/lifecycle tests | MIT | `REFERENCE_ONLY` |
| Hermes | Desktop project, but no mature Windows PortAudio path found | `sounddevice` appears in optional voice tooling; client capture/wake path is separate | Backend-dependent; no Windows host API strategy found | Callback/client capture and gateway lease patterns | Config and single-owner wake lease, not stable Windows identity | Wake stop/resume/re-arm behavior | `audio_silent` status and lifecycle hints | Wake input, not Golden STT/VAD contract | Surface ownership; not local duplex proof | Wake/voice interruption lifecycle | Extensive mocked voice/wake tests | MIT | `REFERENCE_ONLY` |
| `ndunl075/Jarvis` | Windows-oriented Python audio code; source supports PortAudio-style desktop use | `sounddevice.RawInputStream` | Enumerates WASAPI/MME by name; prefers WASAPI then MME where appropriate | Callback; native device rate; fixed target frames | Case-insensitive name variants, host API and input-channel checks | Candidate fallback and nonfatal device fallback reporting; unload is idempotent | Callback status logging, wrong-size frame rejection and frame cadence | 16 kHz mono PCM16 frames suitable for VAD | Pipeline supports optional listening during speaking; AEC caveat remains | Explicit wake/interruption path; not a Golden replacement | Strong mocked device/lifecycle/callback/fallback tests; no equivalent real Windows proof | MIT | `ADAPT` narrow patterns |
| `ONEPUNCHMAN411/Jarvis` | Windows packaging/build evidence; no host API proof | `sounddevice.InputStream` | No explicit host API selection | Callback to bounded async queue; configurable 16 kHz chunks | Numeric/configured device and default query logging | No mature re-enumeration/reopen policy found | RMS level callback, p95 noise calibration, bounded queue drops oldest | VAD/utterance capture consumes chunks | Captures during TTS for barge-in | TTS interruption and barge-in buffer | Mocked voice tests; no real Windows host comparison | MIT | `ADAPT` signal-health/queue ideas only |
| `python-sounddevice` | PortAudio supports Windows through the installed host APIs | `sounddevice` | `query_hostapis()` and device metadata exposed; selection remains application policy | Callback or blocking streams; raw buffer streams available | Numeric or default device query; no logical identity/recovery policy | No automatic application-level reopen contract | Stream status flags available; no opinionated usable-signal gate | No VAD | Stream primitive only | Stream primitive only | Upstream API/examples, not Golden scenario tests | MIT | `KEEP_OURS` library, `ADAPT` API usage |
| Pipecat | Local audio transport requires PortAudio; broader transports are WebRTC/WebSocket | Local transport / PortAudio and provider transports | Transport-dependent | Frame/task pipeline | Transport/client selection; not a Windows device identity layer | Transport/task lifecycle, not Golden USB recovery | Audio task/transport health patterns | Silero VAD and turn-management integrations | Strong pipeline/transport support | Interruption/turn-management patterns | Unit/examples and transport tests; no current-device proof | BSD-2-Clause | `REFERENCE_ONLY` / `ADAPT` concepts |
| LiveKit Agents | Local terminal input exists; primary model is RTC/server agents | LiveKit RTC media | WebRTC/RTC | Streaming frames and agent session lifecycle | RTC/client device selection, not PortAudio index recovery | Session/resource cleanup and reconnect-oriented RTC lifecycle | VAD/turn detection and interruption signals | Provider/turn detection integrations | Strong full-duplex RTC model | Adaptive interruption and generation cancellation | Broad tests and examples; no local Windows PortAudio proof | Apache-2.0 | `REFERENCE_ONLY` |
| openWakeWord | Platform-neutral examples; not a Windows device manager | Commonly consumes caller-provided PCM | Caller-owned | Streaming frame consumer | Caller-owned | Caller-owned | Model-level detection, not input health | Wake-word consumer only | No | No | Examples/tests around detection, not Windows capture | Apache-2.0 | `REFERENCE_ONLY` |

## Best donor findings

### Windows capture and callback reference

The strongest match is `ndunl075/Jarvis/jarvis/audio/devices.py`.
`AudioInputSource` enumerates current devices, filters for input capability,
matches configured names across host API variants, queries each device's native
sample rate, opens a callback `RawInputStream`, converts native-rate buffers to
the target frame size, rejects malformed frame sizes, and tries a bounded
candidate list. Its `unload()` stops before closing, clears stream state, and
its callback catches consumer failures so an exception does not escape into the
PortAudio callback boundary.

This is better than the current Golden path for device identity, native-rate
handling and fallback. It is not proof that its policy works on this exact USB
microphone: its tests stub sounddevice and do not establish real Windows
hardware validation or production proof.

### Device identity and recovery

The same donor's name-plus-host-API candidate logic is the best available
pattern. It is still not a stable OS endpoint identifier. Golden should own a
logical identity/fingerprint and re-enumeration policy, because numeric
PortAudio indices can move after USB or default-device changes. Recovery must
remain under Golden's existing recovery authority and must be bounded; a donor
fallback list must not become a second recovery loop.

### Signal health

`ONEPUNCHMAN411-Jarvis/jarvis/voice/voice_manager.py` has the clearest signal
health pattern: a startup noise-floor calibration, normalized RMS callbacks,
bounded chunk queue, and freshness behavior that drops the oldest chunk when
full. This complements, but does not replace, Golden's existing raw diagnostic
measurements. The useful future rule is to distinguish `stream_open` from
`signal_usable` using cadence, overflow/error state, and bounded silence/stuck
zero observation. No threshold is changed by this audit.

### VAD feed

Golden's existing `SileroVADAdapter` plus `HybridEndpoint` is already the
stronger ownership boundary. The donor's 16 kHz mono PCM16 framing confirms the
contract; it does not justify changing Golden VAD, endpointing, or thresholds.

### Full duplex and barge-in

LiveKit Agents and Pipecat provide useful session/interruption concepts, but
their best evidence is RTC/transport-level rather than Windows local capture.
LiveKit's voice activity path distinguishes acoustic interruption from
backchannel and cancels stale generation work; Pipecat exposes frame/task
queues and interruption events. These are reference patterns only. Golden must
preserve its `TurnManager`, cancellation generations, self-trigger policy and
SecurityManager. No AEC is inferred or added.

## Component decisions

| Component | Decision | Reason |
| --- | --- | --- |
| `WINDOWS_AUDIO_LIBRARY` | `KEEP_OURS` | Existing `sounddevice`/PortAudio is appropriate; no replacement is justified. |
| `CAPTURE_MODEL` | `ADAPT` | Prefer callback-driven capture with explicit lifecycle over more blocking `RawInputStream.read()` probing. |
| `HOST_API_SELECTION` | `ADAPT` | Enumerate by host API name and capability; do not assume WASAPI is always superior. |
| `DEVICE_SELECTION` | `ADAPT` | Use configured logical name plus host API/capability candidates, with default-device fallback only when policy permits. |
| `DEVICE_IDENTITY` | `REIMPLEMENT_PATTERN` | Golden needs its own stable identity/fingerprint and policy; no donor provides a complete Windows-stable identifier contract. |
| `DEVICE_RECOVERY` | `ADAPT` | Reuse bounded candidate/reopen ideas inside Golden's existing recovery authority. |
| `STREAM_LIFECYCLE` | `ADAPT` | Use explicit open/start, stop/close, callback detach and failure isolation; preserve one Golden owner. |
| `CALLBACK_QUEUE` | `ADAPT` | Combine donor callback safety with Golden `AudioFrameQueue`; preserve freshness and bounded memory. |
| `SAMPLE_RATE_CONVERSION` | `ADAPT` | Open at native device rate, then normalize to Golden's 16 kHz frame contract. |
| `SIGNAL_HEALTH` | `ADAPT` | Add a future provider health state from cadence/errors/RMS without treating open as usable audio. |
| `VAD_FEED` | `KEEP_OURS` | Golden already owns Silero, framing and endpoint policy. |
| `FULL_DUPLEX_CAPTURE` | `REFERENCE_ONLY` | RTC examples are not a Windows local-device solution; no AEC or threshold change is justified. |
| `BARGE_IN_INPUT` | `KEEP_OURS` | Keep Golden TurnManager/cancellation; borrow only narrow interruption observability patterns later. |

## Critical question

`DOES_A_MATURE_TESTED_IMPLEMENTATION_ALREADY_SOLVE_OUR_CURRENT_PROBLEM:`
`PARTIALLY`

`PROJECT:` `ndunl075/Jarvis`

`COMPONENT:` device selection, callback capture, native-rate normalization,
stream lifecycle and bounded fallback

`EXACT_FILES:`

- `C:/JarvisDonorAudit/ndunl075-Jarvis/jarvis/audio/devices.py`
- `C:/JarvisDonorAudit/ndunl075-Jarvis/tests/audio/test_devices.py`
- `C:/JarvisDonorAudit/ndunl075-Jarvis/jarvis/audio/protocols.py`

`EXACT_PATTERN:` enumerate input-capable device variants by name and host API;
prefer a policy-defined candidate; query native samplerate; run a callback
stream; normalize frames; reject malformed buffers; close cleanly; fall back to
another candidate with an observable nonfatal event.

`WHY_IT_IS_BETTER_THAN_CURRENT_GOLDEN:` it directly addresses the observed
Windows host/rate/index problems, while the current provider assumes a fixed
16 kHz open and passes through a numeric/default selector. The donor still
requires adaptation and real validation; its mocked tests are not hardware
proof.

## Dependency and license decision

No new dependency is required. The proposed adaptation stays within the
existing `sounddevice`/PortAudio stack. `ndunl075/Jarvis` and
`ONEPUNCHMAN411/Jarvis` are MIT; Pipecat is BSD-2-Clause; LiveKit Agents is
Apache-2.0; openWakeWord is Apache-2.0. This gate recommends adapting behavior
and tests, not copying foreign orchestration or introducing a license-bearing
runtime component.

Python 3.13 compatibility, native wheels, and packaging impact were therefore
not changed or revalidated by installation in this gate. They must be checked
only if a future implementation proposes a new package. No installation or
model download occurred.

## Recommendation

`CONTINUE_MME_REPEATABILITY_TEST:` `NO`

`ADAPT_DONOR_BEFORE_MORE_HARDWARE_TESTS:` `YES` for a separate implementation
gate; no implementation is performed here.

`PROPOSED_ADAPTATION:` extend the existing `AudioInputProvider` behind its
current contract with a Golden-owned resolver and health state. Resolve a
logical microphone by name/host API/input capability, open at its native rate
through a callback, resample into 16 kHz/480-sample frames, and use bounded
re-enumeration/reopen on stream failure. Preserve one stream owner, Golden
queue/VAD, TurnManager, cancellation, SecurityManager and no audio
persistence. Add deterministic resolver/lifecycle/recovery tests before any
new human hardware gate.

`NEW_DEPENDENCY_REQUIRED:` `NO`

`LICENSE_BLOCKER:` `NO`

## Safety record

- `PRODUCTION_CODE_CHANGED: NO`
- `DEPENDENCIES_INSTALLED: NO`
- `WINDOWS_SETTINGS_CHANGED: NO`
- `DEVICE_REGISTRY_TOUCHED: NO`
- `DB_MIGRATION: NO`
- `AUDIO_CAPTURE_RUN: NO`
- `PUSH: NO`

## Sources

- [python-sounddevice documentation](https://python-sounddevice.readthedocs.io/en/latest/)
- [ndunl075/Jarvis donor](https://github.com/ndunl075/Jarvis)
- [ONEPUNCHMAN411/Jarvis donor](https://github.com/ONEPUNCHMAN411/Jarvis)
- [OpenClaw](https://github.com/openclaw/openclaw)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [Pipecat](https://github.com/pipecat-ai/pipecat)
- [Pipecat local audio examples](https://github.com/pipecat-ai/pipecat/blob/main/examples/README.md)
- [LiveKit Agents](https://github.com/livekit/agents)
- [LiveKit adaptive interruption handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/)
- [openWakeWord](https://github.com/dscripka/openWakeWord)

## Gate result

`JARVIS_VOICE_PHASE: PARTIAL`

`WINDOWS_AUDIO_INPUT_DONOR_AUDIT: PASS_WITH_RESTRICTIONS`

The research gate passes with the restriction that the best donor is not
real-hardware or production proof for Golden. The next gate is a reviewed,
minimal provider adaptation followed by deterministic tests; only then should
the paused MME repeatability validation be reconsidered.
