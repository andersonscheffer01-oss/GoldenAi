
# JARVIS Donor Audit 1B: Voice + Windows/Desktop

Status: PASS_WITH_RESTRICTIONS
Date: 2026-09-26
Scope: read-only architecture and component extraction audit.

This is an audit record, not an implementation authorization. No donor code
was copied into Golden and no donor dependency was installed in the Golden
environment.

## Executive Summary

Golden already has a real VoiceService, a realtime voice package, streaming and
turn-cancellation helpers, and a PySide6 desktop shell that renders the
canonical jarvis_ui through QWebEngine. The shell reuses CoreLauncher,
JarvisApiClient, the device-token identity flow, HTTPS health, and the
single-instance guard. Golden remains the owner of Core, SecurityManager,
AuditLog, task durability, browser safety, and Computer Use.

Donor A, ndunl075/Jarvis, is the stronger voice donor. It has explicit audio
stage protocols, fixed PCM frame contracts, local openWakeWord, Silero VAD,
faster-whisper, Piper streaming TTS, deterministic cancellation, device
abstractions, and focused audio tests. Its cost is native audio/model
packaging and a separate asyncio/Qt lifecycle.

Donor B, ONEPUNCHMAN411/Jarvis, is the stronger desktop-pattern donor. It has
PyQt6, Qt signals, tray and overlay surfaces, a local API, plugin modules, and
installer/startup scripts. Its local API directly exposes tool execution
without a Golden-style SecurityManager or approval boundary. It must not become
a second control plane.

Recommendation: VOICE FOUNDATION FIRST. Adapt selected Donor A patterns
behind Golden-owned interfaces. Keep the current Desktop shell and the
Computer Use 8D architecture.

## Audit Result

~~~
JARVIS_DONOR_AUDIT: IN_PROGRESS
DONOR_AUDIT_1B: PASS
GOLDEN_RUNTIME_MODIFIED: NO
DONOR_CODE_COPIED_INTO_GOLDEN: NO
SINGLE_CORE_PRESERVED: PASS
SECURITYMANAGER_PRESERVED: PASS
LICENSE_GATE: PASS_WITH_RESTRICTIONS
MODEL_ASSET_LICENSE_GATE: PASS_WITH_RESTRICTIONS
DEPENDENCY_GATE: PASS_WITH_RESTRICTIONS
SUPPLY_CHAIN_GATE: PASS_WITH_RESTRICTIONS
PRIVACY_GATE: PASS_WITH_RESTRICTIONS
SECURITY_GATE: PASS_WITH_RESTRICTIONS
DEVICE_REGISTRY_TOUCHED: NO
SECRET_SCAN: PASS
~~~

PASS means that the requested audit gates were completed with findings
recorded. It does not clear donor code, models, assets, or dependencies for
porting.

## Golden Current Voice Baseline

Source paths audited:

- jarvis_core/voice.py
- jarvis_core/voice_service.py
- jarvis_core/realtime_voice/state_machine.py
- jarvis_core/realtime_voice/vad.py
- jarvis_core/realtime_voice/barge_in.py
- jarvis_core/realtime_voice/integration.py
- jarvis_core/realtime_voice/audio_queue.py
- jarvis_core/streaming/turn_manager.py
- jarvis_core/streaming/tts_pipeline.py
- jarvis_core/streaming/audio_player.py
- jarvis_core/service.py
- server_agent.py

| Capability | Current Golden implementation | Maturity | Known gap |
| --- | --- | --- | --- |
| STT | JarvisVoice lazily loads faster-whisper and transcribes local microphone WAV/bytes. | Active | Native/model packaging remains operational work. |
| Audio input | sounddevice capture in JarvisVoice; status exposes level and age. | Active | No single stage protocol equivalent to Donor A. |
| Wake word | Text-level JarvisVoice.detect_wake_word after transcription. | Active, bounded | Dedicated acoustic wake detection is not the primary path. |
| VAD | RMS/end-silence capture plus Silero ONNX adapters in realtime_voice. | Active | Legacy and realtime paths have different shapes. |
| Voice session | VoiceService owns one daemon thread, session/conversation IDs, state, and capture requests. | Active | State consolidation is future work. |
| Conversation loop | VoiceService calls the existing JarvisService orchestrator/tool pipeline. | Active | Donors must not own Core, memory, or routing. |
| Streaming | streaming package, TurnManager, provider streams, sentence chunking, optional true streaming. | Active | Provider-specific first-audio/cancel contracts need continued tests. |
| Barge-in | Separate VAD/RMS monitor, pre-roll, cancellation event, follow-up capture, turn cleanup. | Active/experimental | Echo/AEC and hardware behavior remain sensitive. |
| TTS | edge-tts to temporary MP3/WPF MediaPlayer, with Windows SAPI fallback; streaming helpers exist. | Active | Network/provider and cancellation paths are not one uniform adapter. |
| Device selection | sounddevice input selection and Windows output paths. | Partial | One unified device lifecycle contract is a gap. |
| Security | Voice previews risk through the existing orchestrator; execution goes through JarvisService. | Active | Future UI must never add direct privileged calls. |
| Audit | Core owns canonical AuditLog; voice telemetry includes source/session/TTS ownership fields. | Active | Voice event schema should be stabilized later. |

VoiceService in jarvis_core/voice_service.py is the runtime owner. server_agent.py
resolves the singleton through get_voice_service for the
/api/jarvis/voice-service/* endpoints. Desktop observes the service and
requests capture; it does not run a second browser SpeechRecognition path.

The current states include OFF, OUVINDO, LISTENING, CAPTURING_FOLLOWUP,
TRANSCRIBING, WAITING_WAKE, SPEAKING, and ERROR across VoiceService and
JarvisVoice. The realtime package separately models listening/thinking/speaking.
This is usable but is a future consolidation boundary, not a reason to import
a donor state machine.

## Golden Current Desktop Baseline

Source paths audited:

- jarvis_desktop/web_app.py: current launch path
- jarvis_desktop/web_window.py: current QWebEngine shell
- jarvis_desktop/core_launcher.py
- jarvis_desktop/api_client.py
- jarvis_desktop/tray.py
- jarvis_desktop/single_instance.py
- jarvis_desktop/identity.py
- jarvis_desktop/main_window.py and app.py: legacy/native UI
- jarvis_desktop/main_window_v4.py and app_v4.py: legacy V4
- start_jarvis_desktop.bat: current development launcher
- start_jarvis_desktop_v4.bat: legacy launcher
- tests/test_web_desktop.py

| Capability | Current status | Maturity |
| --- | --- | --- |
| Desktop app | web_app creates one QApplication, acquires SingleInstance, reuses or launches the existing Core, then creates DesktopMainWindow. | Active |
| GUI | PySide6 and QtWebEngine; canonical web UI loads through HTTPS. | Active |
| Tray | JarvisTray/QSystemTrayIcon owns show, hide, status, and exit actions. | Active |
| Core connection | CoreLauncher probes HTTPS health/UI, starts server_agent only when needed, passes Golden TLS/LAN environment, and stops only a child it owns. | Active |
| API | Desktop uses the existing backend through JarvisApiClient; it does not construct Core business objects. | Active |
| Identity | DesktopIdentityManager provisions/reuses the canonical device token. | Active |
| Computer Use | Core/tools remain authoritative; donor automation is not substituted. | Closed and preserved |
| Tasks | tasks_view consumes task endpoints. | Active |
| Notifications/approvals | UI consumes existing status/task/approval data; no separate engine found in desktop. | Active consumer |
| Health | Status, provider/orchestrator, GPU, radar, and scheduler-facing views consume existing endpoints. | Active consumer |
| V4 | app_v4/main_window_v4 remain legacy/compatibility code, not the current launcher path. | Legacy |

tests/test_web_desktop.py protects canonical UI URL, single instance,
renderer-failure isolation, Core reuse, no direct ToolRegistry/SecurityManager
bypass, tray lifecycle, and reuse of the existing VoiceService.

## Repository Verification

Both repositories were verified with git ls-remote, shallow clones outside
Golden, root license files, GitHub metadata, source paths, tests, and build
metadata. Audit clones:

- C:\JarvisDonorAudit\ndunl075-Jarvis
- C:\JarvisDonorAudit\ONEPUNCHMAN411-Jarvis

| Field | Donor A | Donor B |
| --- | --- | --- |
| Repository | ndunl075/Jarvis | ONEPUNCHMAN411/Jarvis |
| URL | https://github.com/ndunl075/Jarvis | https://github.com/ONEPUNCHMAN411/Jarvis |
| Owner | ndunl075 | ONEPUNCHMAN411 |
| Default branch | main | main |
| Verified shallow HEAD | e21ce95f40d8f653eed80cfa4d515c89f795edfb | 9bbb3bf26bb4cdea578dd58d26eb74871445fade |
| HEAD date | 2026-09-09 | 2026-06-25 |
| HEAD subject | Fix a CONTRIBUTING line left contradicting itself (#18) | clean up audio decode |
| Primary language | Python | Python |
| Root license | MIT, LICENSE | MIT, LICENSE |
| Releases/tags | No releases; no tags observed | v1.0 release/tag observed |
| Documentation | README, SPEC, BUILD, SECURITY, CHANGELOG | README, CHANGELOG, CONTRIBUTING, installer/build files |
| REPOSITORY_VERIFIED | YES | YES |

The verification is tied to the inspected revisions. A future port must pin a
new revision and repeat the verification.

## Donor A Architecture

Relevant exact paths:

- jarvis/audio/protocols.py: 16 kHz mono int16 frame contract, stage protocols,
  and speak/speak_stream/cancel contracts.
- jarvis/audio/pipeline.py: async frame orchestration, wake/VAD/STT/response/TTS,
  endpointing, and cancellation of the response chain.
- jarvis/audio/wake_word.py: local openWakeWord, score threshold, reset, model path.
- jarvis/audio/vad.py: direct Silero ONNX, 512-sample windows, persistence, endpoint,
  reset, and unload.
- jarvis/audio/stt.py: faster-whisper load/unload and asyncio.to_thread transcription.
- jarvis/audio/tts.py: Piper streaming, sentence buffering, device fallback,
  resampling, queue playback, abort and close.
- jarvis/audio/devices.py: capture/output device abstraction and lifecycle.
- jarvis/app.py: Qt main thread, dedicated audio asyncio loop/thread, bridge, shutdown.
- jarvis/ui/tray.py and jarvis/ui/overlay.py: tray/status and visual surfaces.
- tests/audio/test_wake_word.py, test_vad.py, test_stt.py, test_tts.py,
  test_pipeline.py, test_devices.py: focused audio contract tests.

Wake is local openWakeWord and operates on fixed PCM frames. VAD is local Silero
ONNX with explicit windows and endpointing. STT is local faster-whisper; the
model can download from Hugging Face on first load unless pre-bundled. TTS is
local Piper and does not auto-download voice files. A voice metadata asset is
present under packaging/bundle/voices/, while actual model terms remain a
separate gate.

The pipeline has a real barge-in design: wake is fed in all states, optional VAD
barge-in cancels the response/TTS chain, TTS exposes cancel, and playback uses
abort plus queue draining. The design documents speaker-to-mic/AEC limits and
disables VAD barge-in by default until AEC or headphone-only deployment. This
is strong design evidence, not proof of hardware coverage.

Donor A uses PySide6. jarvis/app.py keeps Qt on the main thread and runs audio
asyncio on a dedicated thread, with run_coroutine_threadsafe bridges. It checks
tray availability and has ordered shutdown. Tests cover shutdown order, partial
boot, tray failure, and injected dependencies.

Donor A pyproject declares PySide6, openwakeword, faster-whisper, silero-vad,
piper-tts, sounddevice, scipy, httpx, psutil, optional Windows pyautogui/pynput,
and MCP. The dependency cost is HEAVY for packaged voice: PortAudio,
ONNX/onnxruntime, CTranslate2/Whisper, Piper files, Qt plugins, and Windows
packaging. Its direct ONNX approach avoids a torch runtime for Silero.

## Donor B Architecture

Relevant exact paths:

- jarvis/voice/voice_manager.py: composition, background modes, noise-floor
  calibration, device switching, listener loop, TTS events, barge-in buffering.
- jarvis/voice/audio_capture.py: sounddevice input, asyncio queue, callback bridge.
- jarvis/voice/audio_player.py: decode, blocking sounddevice playback, stop state.
- jarvis/voice/vad.py, wake_word.py, stt.py, tts.py: VAD, openWakeWord,
  faster-whisper, Edge TTS and pyttsx3 fallback.
- jarvis/voice/live_transcription.py, utterance.py, voice_profiles.py.
- jarvis/app.py: PyQt6 QApplication, signals/timers, audio loop, tray/overlay,
  ordered shutdown.
- jarvis/ui/advanced_chat_window.py: large PyQt6 window, tray, chat, panels/settings.
- jarvis/ui/web_window.py: PyQt6 QWebEngine and QWebChannel bridge.
- jarvis/ui/orb_overlay_window.py, orb_3d.py, computer_use_overlay.py.
- jarvis/api/local_server.py: loopback aiohttp API.
- jarvis/plugins/*: Python tool/UI plugin modules.
- installer/jarvis_setup.nsi, installer/jarvis_setup.iss, build_exe.py,
  setup_windows_startup.py.

VoiceManager calibrates ambient RMS, supports wake-phrase and always-listening
modes, drains stale audio, and interrupts TTS when VAD detects speech. It stops
AudioPlayer and buffers the trigger/follow-up chunks. This is useful but less
explicit than Donor A's cancellation contract, so it is ADAPT only.

local_server.py binds aiohttp to 127.0.0.1:8765 and rejects non-local browser
Origin values. It exposes status, tools, chat, and tool routes. The tool route
checks the name against the registry and then executes it. There is no auth
token, per-request approval, or Golden SecurityManager boundary. Loopback and
Origin checks reduce remote exposure but do not replace authorization.
Classification: reject as a direct privileged boundary; reimplement only behind
Golden service, SecurityManager, and AuditLog.

Donor B uses PyQt6, not PySide6. The NSIS and Inno scripts copy a PyInstaller
build, create shortcuts, register uninstall metadata, optionally write the
HKCU Run key, and run a Playwright install step. setup_windows_startup.py offers
Run key, Startup folder, and Task Scheduler. These are packaging references
only; they imply admin, registry, subprocess, and network surfaces.

## Voice Component Analysis

| Capability | Donor A | Donor B | Golden decision |
| --- | --- | --- | --- |
| Wake word | Local openWakeWord, model path, score threshold/reset. | openWakeWord, sensitivity and fallback. | ADAPT behind VoiceService; retain audit/privacy. |
| VAD | Silero ONNX, fixed window, endpoint state, protocol. | Silero wrapper plus adaptive noise threshold. | ADAPT behavior; no second VAD owner. |
| Barge-in | Explicit response/TTS cancel, queue drain, abort, AEC limitation. | VAD during playback, stop, buffered follow-up. | ADAPT cancellation contract; preserve TurnManager. |
| Streaming STT | Async wrapper, but request/response Whisper, not token streaming. | Async manager, no independent partial-token contract. | REIMPLEMENT_PATTERN only if partial/final contract is needed. |
| Streaming TTS | Piper chunks, sentence buffering, callback playback, abort/rewire. | Edge chunks and collected fallback bytes. | ADAPT Donor A contract; keep provider policy. |
| Audio lifecycle | Source/device protocols and unload. | Capture/player start/stop and device replacement. | ADAPT narrow lifecycle contract. |
| Voice state | Separate state machine and lifecycle actions. | Manager status and event bus. | KEEP_OURS ownership. |
| Provider coupling | local Ollama/Piper/Whisper. | Edge/ElevenLabs/provider ecosystem. | KEEP_OURS ModelRouter. |
| Privacy | Local audio path documented. | Edge TTS sends text to cloud. | KEEP_OURS secret/provider policy. |

## Desktop Component Analysis

| Component | Exact donor source path | Classification | Rationale |
| --- | --- | --- | --- |
| Audio-stage protocols | A: jarvis/audio/protocols.py | ADAPT | Strong contracts, but Golden owns names/session/security. |
| Async audio pipeline | A: jarvis/audio/pipeline.py | REIMPLEMENT_PATTERN | State and cancellation ideas fit; ownership does not. |
| Qt/audio split | A: jarvis/app.py; B: jarvis/app.py | REIMPLEMENT_PATTERN | Strong boundary pattern, framework and composition differ. |
| Wake/VAD/STT/TTS | A: jarvis/audio/*.py; B: jarvis/voice/*.py | ADAPT | Behavioral patterns only; model and license gate remains. |
| Tray/overlay UX | A: jarvis/ui/tray.py; B: jarvis/ui/orb_overlay_window.py | REFERENCE_ONLY | Golden already owns active shell and Computer Use UI. |
| PyQt6 desktop window | B: jarvis/ui/advanced_chat_window.py | REFERENCE_ONLY | Large UI couples presentation and business/provider concerns. |
| QWebEngine bridge | B: jarvis/ui/web_window.py | REFERENCE_ONLY | Golden canonical HTTPS UI remains authoritative. |
| Local API | B: jarvis/api/local_server.py | REIMPLEMENT_PATTERN | Loopback/Origin idea useful; direct /tool is not authorized. |
| Plugins | B: jarvis/plugins/* | REIMPLEMENT_PATTERN | Need manifest, provenance, permissions, isolation, rollback. |
| Installers | B: installer/* and build_exe.py | REFERENCE_ONLY | Packaging checklist only; no copy. |
| Startup helper | B: setup_windows_startup.py | REJECT | Registry, Startup, and Task Scheduler choices expand policy surface. |
| Golden Core launcher | Golden: jarvis_desktop/core_launcher.py | KEEP_OURS | HTTPS, CA validation, child ownership and no blind restart. |
| Golden Computer Use | Golden: browser.py, computer_use_tools.py, computer_use_mission.py | KEEP_OURS | 4D-8D closure and provenance/safety gates are canonical. |

## Component Classification Matrix

No component is cleared for literal PORT. The table covers every donor area
selected for detailed review and records exact source paths, dependencies,
license/security surfaces, Golden equivalents, savings, and risks.

| Donor/component | Exact source path | Purpose | Dependencies/cost | License | Security surface | Golden equivalent | Classification | Savings | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A audio protocols | jarvis/audio/protocols.py | Frame/stage contracts | asyncio, LIGHT | MIT root; file review | audio boundary | voice.py/realtime_voice | ADAPT | MEDIUM | MEDIUM |
| A pipeline | jarvis/audio/pipeline.py | Audio orchestration | asyncio/queues, MODERATE | MIT root | cancellation/turns | VoiceService/TurnManager | REIMPLEMENT_PATTERN | MEDIUM | HIGH |
| A wake | jarvis/audio/wake_word.py | Local wake detection | openwakeword/ONNX, MODERATE | root MIT plus model terms | always-listening mic | text wake/realtime voice | ADAPT | MEDIUM | HIGH |
| A VAD | jarvis/audio/vad.py | Speech endpointing | silero/onnxruntime, MODERATE | root MIT plus model terms | raw audio/native runtime | realtime_voice/vad.py | ADAPT | MEDIUM | MEDIUM |
| A STT | jarvis/audio/stt.py | Local transcription | faster-whisper/CTranslate2, HEAVY | root MIT plus model terms | model download/transcripts | voice.py | KEEP_OURS | NONE | MEDIUM |
| A Piper TTS | jarvis/audio/tts.py | Local streaming/cancel | Piper/sounddevice/scipy, HEAVY | root MIT plus voice terms | output/model assets | voice_service/streaming | ADAPT | MEDIUM | HIGH |
| A device lifecycle | jarvis/audio/devices.py | Mic/output selection | PortAudio, MODERATE | dependency review | device handles | voice.py helpers | ADAPT | MEDIUM | MEDIUM |
| A Qt composition | jarvis/app.py | Qt/audio lifecycle | PySide6/threads, MODERATE | root MIT | thread/shutdown | web_app.py/Core | REIMPLEMENT_PATTERN | MEDIUM | HIGH |
| B VoiceManager | jarvis/voice/voice_manager.py | Voice composition | PyQt/audio/providers, HEAVY | root MIT; dependency review | cloud TTS/tool coupling | VoiceService | REFERENCE_ONLY | LOW | HIGH |
| B barge-in | jarvis/voice/voice_manager.py | Stop and buffer speech | audio/VAD, MODERATE | root MIT/model review | playback races | Golden barge-in | ADAPT | MEDIUM | HIGH |
| B Qt app | jarvis/app.py | QApplication/bridge | PyQt6, MODERATE | root MIT | UI thread/shutdown | PySide6 shell | ADAPT | MEDIUM | MEDIUM |
| B desktop UI | jarvis/ui/advanced_chat_window.py | Chat/tray/settings | PyQt6/providers, HEAVY | root MIT/assets review | UI action reach | jarvis_desktop/jarvis_ui | REJECT | NONE | HIGH |
| B local API | jarvis/api/local_server.py | HTTP status/chat/tools | aiohttp, MODERATE | root MIT | unauthenticated /tool | JarvisApiClient/backend | REIMPLEMENT_PATTERN | LOW | CRITICAL |
| B plugins | jarvis/plugins/* | Python extensions | arbitrary, HEAVY | per-file review | process/files/secrets | future extension contract | REIMPLEMENT_PATTERN | MEDIUM | CRITICAL |
| B installers | installer/*, build_exe.py | Package Windows app | Qt/CUDA/Playwright, HEAVY | assets/deps review | admin/registry/downloads | Golden build | REFERENCE_ONLY | LOW | HIGH |
| B startup | setup_windows_startup.py | Persistence methods | Windows/pywin32, MODERATE | root MIT | registry/elevation | Golden policy | REJECT | NONE | HIGH |
| Golden ownership | service.py, security.py, audit.py, task_manager/* | Control plane | existing | Golden-owned | sole authority | none | KEEP_OURS | NONE | LOW |
| Golden Computer Use | browser.py, computer_use_tools.py, computer_use_mission.py | Safe missions | existing | Golden-owned | focus/files/provenance | none | KEEP_OURS | NONE | LOW |

Counts: KEEP_OURS=3, PORT=0, ADAPT=6, REIMPLEMENT_PATTERN=5,
REFERENCE_ONLY=4, REJECT=3.

## Security Findings

LOW:
- Both root repositories are public and root MIT licenses were present.
- Both have tests that provide design evidence, not Golden security clearance.

MEDIUM:
- Always-on microphone, local models, temporary audio, and TTS need explicit
  lifecycle/privacy telemetry.
- Native audio, Qt, ONNX, Whisper, and model packaging increase crash/shutdown
  surface.
- Donor B Edge TTS is cloud-dependent.
- Donor install/startup scripts write registry values or run subprocesses.

HIGH:
- Donor B local /tool has no auth token, approval token, or SecurityManager.
- Plugin Python/UI modules have broad execution reach without Golden gates.
- Speaker-to-mic feedback and cancellation can race on Windows hardware.

CRITICAL/REJECTED:
- No donor core, memory, scheduler, approval engine, provider policy, browser
  engine, credential resolver, or security model may replace Golden ownership.
- No donor API/plugin/voice callback/UI action may invoke privileged Golden tools
  outside SecurityManager -> ToolRegistry/Service -> AuditLog.
- No automatic remote plugin/model/installer execution is approved.

## License Findings

- Donor A root LICENSE is MIT, copyright 2026 Jarvis Contributors.
- Donor B root LICENSE is MIT, copyright 2025-2026 Venkata Mannem.
- No donor file was ported and no Golden license file changed.
- Root MIT does not automatically cover model weights, voice files, icons,
  sounds, Qt/PortAudio/ONNX binaries, or all transitive dependencies.
- Donor A packaging/bundle/voices/en_GB-alan-medium.onnx.json is metadata; the
  actual voice model terms remain a separate gate.
- Donor B assets, icon, CUDA/Playwright/Qt packaging, and provider SDKs need
  separate review.
- Every future port requires a new file-level, dependency, model, and asset
  review at the pinned revision.

## Dependency, Native, and Supply Chain Findings

| Surface | Donor A | Donor B | Gate |
| --- | --- | --- | --- |
| Audio | sounddevice/PortAudio, scipy | sounddevice and decoder stack | Review before runtime change |
| STT | faster-whisper/CTranslate2 and model files | faster-whisper and optional CUDA | HEAVY; package explicitly |
| VAD/wake | ONNX plus model files | same family plus PyInstaller collection | Model/license review |
| TTS | Piper local voice model | Edge network plus pyttsx3 fallback | Privacy/provider decision |
| Qt | PySide6 and plugins | PyQt6 and QtWebEngine | Keep Golden PySide6 |
| Browser | optional tools/MCP | Playwright and Chromium install | Keep Golden browser |
| Downloads | Hugging Face first-load path | model/provider and Playwright install | No unreviewed auto-download |
| Pinning | major bounds and lock file | broad declarations; no equivalent lock inspected | Re-pin before use |
| Scripts | build.ps1, PyInstaller spec | build_exe, NSIS/Inno, startup helper | Reference only |

Resource budget is qualitative: wake/VAD MEDIUM; local STT/TTS HIGH;
PySide6/QWebEngine HIGH; combined always-on voice plus desktop HIGH. No numeric
latency target was inferred. Relevant stages are VAD endpoint, STT first/final
transcript, Core decision, TTS first audio, and barge-in abort.

## Privacy and Secrets

Donor A documents a local wake/VAD/STT/TTS/Ollama path, with optional network
features separated. Donor B Edge TTS sends response text to the provider and
has a local pyttsx3 fallback. Neither changes Golden provider policy.

Provider/API-key code paths exist in both donors. Values were not printed,
loaded, or copied. Future use must pass Golden secret policy, redaction, and
AuditLog sanitization. Model files and raw audio are separate privacy assets
from source code and need explicit retention decisions.

## Thread, Process, Startup, and Failure Isolation

- Donor A uses Qt main thread plus a dedicated audio asyncio loop/thread,
  callback bridges, and ordered shutdown.
- Donor B uses a Qt main thread plus async/event-bus voice management, audio
  tasks, tray, and overlay.
- Golden Desktop is a shell; CoreLauncher reuses an online Core or owns one
  child and stops only a child it owns. SingleInstance protects the shell.
- Voice failure must not create a second Core or scheduler. Desktop failure must
  leave an already-running Core and durable tasks available.
- A future separate voice process would require authenticated IPC, session
  identity, SecurityManager routing, failure isolation, and AuditLog evidence.
  This audit does not choose a separate process.

## KEEP_OURS

- JarvisService and one-core composition.
- SecurityManager, confirmation/denial, and scope policy.
- AuditLog and redaction.
- ToolRegistry and risk metadata.
- TaskDatabase, BackgroundTaskScheduler, notifications, approvals,
  retry/recovery, and health/control-center APIs from Computer Use 8D.
- ModelRouter and provider classification policy.
- BrowserSession, Computer Use mission/context, Windows automation, stale
  target/user-activity safety, and provenance.
- PySide6/QWebEngine shell, HTTPS launcher, identity pairing, single instance,
  and canonical jarvis_ui.
- VoiceService ownership and Golden event/response identity.

## PORT

NONE. No donor source file is cleared for literal porting. A future PORT
requires pinned revision, file-level license review, dependency/SBOM review,
secret scan, security decision, Golden-owned interface, and regression tests.

## ADAPT

- Donor A audio-stage protocol and fixed-frame vocabulary.
- Donor A local wake lifecycle after model/license review.
- Donor A Silero VAD lifecycle behind Golden realtime voice.
- Donor A Piper chunk/cancel/queue behavior if local TTS is selected.
- Donor A device selection/rewire lifecycle.
- Donor B barge-in buffering and noise-floor ideas with Golden TurnManager.
- Selected Donor B Qt signal/timer/tray presentation ideas through Desktop Adapter.

## REIMPLEMENT_PATTERN

- Golden-owned audio source/output/cancellation pipeline based on Donor A.
- Cross-thread Qt/audio boundary for Golden PySide6.
- Authenticated local service/IPC normalized to Golden service APIs.
- Plugin manifest, provenance, dependencies, permissions, isolation, rollback,
  and teardown based on Donor B and Audit 1A.
- Installer/startup lifecycle only after a dedicated Windows security design.

## REFERENCE_ONLY

Donor A tray/overlay UX; Donor B large chat window, QWebEngine bridge, 3D orb,
panel layout, installer scripts, and provider breadth.

## REJECT

Donor B direct unauthenticated /tool execution; broad startup helper choices;
and any donor core, scheduler, memory, approval, provider, browser,
credential, or security ownership. Automatic remote plugin/model/installer
execution is also rejected.

## Voice 2.0 Target Architecture

Conceptual target only:

~~~
Jarvis Core / JarvisService
        |
  VoiceController (Golden-owned session + state)
        |
  +-----+---------+----------+
  |               |          |
Wake/VAD      STT Adapter  TTS Adapter
  |               |          |
  +-------- Audio Runtime ---+
              |
      device/capture/playback
~~~

Future flow:

~~~
Wake/VAD -> transcript -> Jarvis Core -> SecurityManager when required
         -> response stream -> TTS -> AuditLog/telemetry
~~~

Barge-in is a cancellation transaction: detect user speech with explicit
VAD/echo policy, cancel the response turn through TurnManager, flush playback
buffers, preserve only the new utterance, and re-enter Core. Voice consumes
existing approval, notification, and health APIs rather than creating engines.

Process recommendation: same Core ownership with adapter isolation first.
Choose a separate process only if evidence proves native audio crashes cannot be
contained and authenticated IPC is approved.

## Desktop Target Architecture

~~~
PySide6 Desktop Adapter / Tray / QWebEngine
                    |
          JarvisApiClient / service boundary
                    |
              Jarvis Core
          /        |        \
       Tasks     Voice     Approvals
          \        |        /
             Health / Audit
~~~

Desktop owns Qt presentation, tray/window lifecycle, and connection state. It
does not own business logic, LLM routing, memory, task claims, approvals,
browser automation, or direct filesystem/process actions. HTTPS launcher and
device identity remain the boundary.

## Computer Use 8D and Security Integration

Computer Use 8D is CLOSED and remains KEEP_OURS.

| Capability | Existing owner | Future Voice/Desktop use |
| --- | --- | --- |
| Task queries | 8D.1 BackgroundControlCenter | Read-only task/status views and voice queries. |
| Pause/resume/cancel | 8D.2 controls | Service route with existing risk/approval. |
| Retry/recovery | 8D.3 controls | Reuse existing engine; no voice retry engine. |
| Notifications/approvals | 8D.4 center | Desktop renders; voice reads/requests through same model. |
| Health/diagnostics | 8D.5 health | Desktop displays; voice asks through read-only diagnostics. |

~~~
Voice/Desktop -> Jarvis service/API -> SecurityManager
              -> existing capability -> AuditLog
~~~

Desktop must not query task databases directly. Voice must not call privileged
tools directly. Audit events must preserve request/session/mission identity and
sanitized arguments/results.

## P0 Recommendations

1. Audio cancellation contract: Donor A ADAPT/REIMPLEMENT_PATTERN. Integrate
   at VoiceService/TurnManager with playback abort, response cancellation,
   queue flush, and deterministic tests.
2. Local VAD and wake lifecycle: Donor A ADAPT behind Golden realtime voice.
3. Qt/audio failure boundary: Donor A/B REIMPLEMENT_PATTERN for Golden PySide6,
   preserving Core/scheduler when voice or Qt fails.
4. Local API security review: Donor B REIMPLEMENT_PATTERN only behind Golden
   authentication, SecurityManager, confirmation, and AuditLog.

## P1 Recommendations

- Device selection/rewire and unavailable-device recovery.
- Sentence-grouped TTS streaming and first-audio telemetry.
- Desktop status mapping for listening/thinking/speaking/task/approval/error.
- Installer packaging checklist after a separate persistence/elevation review.

## Proposed Implementation Waves

VOICE FOUNDATION:
1. Define one Golden-owned audio source/output/cancellation contract.
2. Add mocked device lifecycle and cancellation tests.
3. Normalize VAD/wake events into existing VoiceService session.
4. Normalize streaming STT/TTS telemetry and cancellation.
5. Validate barge-in with speaker/headphone and failure-isolation fixtures.
6. Wire actions only through Core/SecurityManager/AuditLog.

DESKTOP FOUNDATION:
1. Keep web_app/web_window and document active versus legacy V4.
2. Add status/event contracts without a second engine.
3. Add headless Qt lifecycle tests for renderer failure, tray teardown, and Core reuse.
4. Design installer/startup separately; no registry changes in this audit.

ROADMAP_CHANGE_RECOMMENDED: NO. This audit recommends Voice Foundation first
but does not silently change the active roadmap.

## Expected Development Savings

| Area | Saving | Basis |
| --- | --- | --- |
| Audio contracts/tests | HIGH | Donor A has protocols and focused test seams. |
| Barge-in cancellation | MEDIUM/HIGH | Donor A has abort/queue/response cancellation. |
| Device lifecycle | MEDIUM | Both donors show capture/output restart patterns. |
| Qt/audio threading | MEDIUM | Both exercise Qt/event-loop boundaries. |
| Desktop UI | LOW | Golden already has the active shell. |
| Installer | LOW | Donor scripts are references only. |

## Testability and Donor Test Quality

Donor A has focused tests for wake word, VAD, STT, TTS, pipeline, devices, and
PySide6 UI/tray/lifecycle. Its stage protocols and injected callbacks are good
mock seams; native behavior still needs hardware/package validation.

Donor B has broad UI/integration tests, Qt application/tray tests, and
tool/plugin tests. Its large UI/provider coupling makes isolated reuse less
testable. Neither suite is Golden acceptance coverage. Future Golden tests must
assert one Core, one SecurityManager, one AuditLog, no duplicate voice loop, no
unsafe replay, and failure isolation.

## Known Unknowns

- Exact licenses/provenance for wake, VAD, Whisper, Piper, and other model
  weights/assets were not cleared by root MIT licenses.
- Hardware AEC, PortAudio, microphone-driver, and speaker-feedback behavior was
  not run during this read-only audit.
- Donor cloud provider availability and rate limits were not tested.
- Donor release artifact contents and installer behavior were not executed.
- Golden legacy app.py/main_window.py and V4 modules remain in the tree; the
  active launcher is start_jarvis_desktop.bat -> web_app.py.
- No donor code was imported into Golden, so runtime compatibility is unverified.

## Final Recommendation

Proceed with a small VOICE FOUNDATION design/test phase first. Select Donor A
audio contracts, local wake/VAD lifecycle, and cancellation behavior as
adaptation targets, but implement behind Golden VoiceService, TurnManager,
ModelRouter, SecurityManager, and AuditLog. Keep current STT/Core ownership
until measured evidence justifies change.

Keep the current Desktop shell and Computer Use 8D architecture. Use Donor B
only for Qt lifecycle vocabulary, tray/overlay ideas, and packaging checklists
as REFERENCE_ONLY/REIMPLEMENT_PATTERN. Do not import its local API, plugins,
startup helper, or UI control plane.

## Required Final Report

~~~
JARVIS_DONOR_AUDIT: IN_PROGRESS
DONOR_AUDIT_1B: PASS
GOLDEN_RUNTIME_MODIFIED: NO
DONOR_CODE_COPIED_INTO_GOLDEN: NO
SINGLE_CORE_PRESERVED: PASS
SECURITYMANAGER_PRESERVED: PASS
DONOR_A: ndunl075/Jarvis
DONOR_A_REPOSITORY: https://github.com/ndunl075/Jarvis
DONOR_A_REPOSITORY_VERIFIED: YES
DONOR_A_LICENSE: MIT
DONOR_A_DEFAULT_BRANCH: main
DONOR_A_COMPONENTS_REVIEWED: audio pipeline, wake, VAD, STT, TTS, devices, tray, Qt lifecycle, tests
DONOR_B: ONEPUNCHMAN411/Jarvis
DONOR_B_REPOSITORY: https://github.com/ONEPUNCHMAN411/Jarvis
DONOR_B_REPOSITORY_VERIFIED: YES
DONOR_B_LICENSE: MIT
DONOR_B_DEFAULT_BRANCH: main
DONOR_B_COMPONENTS_REVIEWED: PyQt6 app/UI, tray, overlay, local API, plugins, installers, startup, voice, tests
VOICE_BASELINE_AUDITED: PASS
DESKTOP_BASELINE_AUDITED: PASS
WAKE_WORD_AUDITED: PASS
VAD_AUDITED: PASS
BARGE_IN_AUDITED: PASS
STREAMING_STT_AUDITED: PASS
STREAMING_TTS_AUDITED: PASS
PYQT_ARCHITECTURE_AUDITED: PASS
TRAY_ARCHITECTURE_AUDITED: PASS
INSTALLER_ARCHITECTURE_AUDITED: PASS
LOCAL_API_SECURITY_AUDITED: PASS
CLASSIFICATIONS: KEEP_OURS, PORT NONE, ADAPT, REIMPLEMENT_PATTERN, REFERENCE_ONLY, REJECT
TOP_P0_COMPONENTS: A cancellation/VAD/wake lifecycle; Qt/audio boundary; B local API security
TOP_P1_COMPONENTS: device recovery; TTS telemetry; desktop status; packaging checklist
VOICE_TARGET_ARCHITECTURE_PROPOSED: PASS
DESKTOP_TARGET_ARCHITECTURE_PROPOSED: PASS
COMPUTER_USE_8D_REUSE_MAPPED: PASS
LICENSE_GATE: PASS_WITH_RESTRICTIONS
MODEL_ASSET_LICENSE_GATE: PASS_WITH_RESTRICTIONS
DEPENDENCY_GATE: PASS_WITH_RESTRICTIONS
SUPPLY_CHAIN_GATE: PASS_WITH_RESTRICTIONS
PRIVACY_GATE: PASS_WITH_RESTRICTIONS
SECURITY_GATE: PASS_WITH_RESTRICTIONS
VOICE_PROCESS_MODEL_RECOMMENDATION: same Core ownership; adapter isolation first
DESKTOP_PROCESS_MODEL_RECOMMENDATION: current PySide6 shell plus existing Core child ownership
IPC_RECOMMENDATION: existing HTTPS/service boundary; no donor direct tool API
EXPECTED_DEVELOPMENT_SAVINGS: high audio contracts/tests; medium cancellation/device/thread patterns; low desktop/installer
ROADMAP_CHANGE_RECOMMENDED: NO
FILES_CREATED: docs/architecture/JARVIS_DONOR_AUDIT_1B.md
FILES_MODIFIED: none
SECRET_SCAN: PASS
DEVICE_REGISTRY_TOUCHED: NO
COMMIT: docs: add Voice and Desktop donor audit
PUSH: NO
KNOWN_UNKNOWNS: model/asset licenses, hardware AEC, native behavior, release artifacts, compatibility
KNOWN_ISSUES: Donor B direct local /tool lacks Golden authorization; startup/install surfaces not approved
NEXT_STEP: VOICE FOUNDATION FIRST
~~~
