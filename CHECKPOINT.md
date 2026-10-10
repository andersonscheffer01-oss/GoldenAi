# Golden / Jarvis Checkpoint

Last updated: 2026-09-28

## 1. Project Identity

- Name: Golden / Jarvis
- Git root: `C:\GoldenAI`
- Main application: `C:\GoldenAI\studio\golden_ai_studio_web`
- Branch: `main`
- HEAD: `4362c5398d3ef8c2f6585bad8b1d90c0609ff175`
- Runtime Python: `C:\GoldenAI\.venv\Scripts\python.exe` (Python 3.13.15)
- OS: Windows 11 Pro, build 26200
- Known local endpoints: UI/Core `https://127.0.0.1:8765`; Gateway health/WSS `https://127.0.0.1:8766/health` and WSS on 8766; Ollama `http://127.0.0.1:11434`.
- Desktop launcher: `C:\GoldenAI\studio\golden_ai_studio_web\start_jarvis_desktop.bat`.

## 2. System View

Jarvis is the primary Core and orchestrator. Golden is integrated into Jarvis; no external agent, MCP server, donor repository, scheduler, or provider replaces Jarvis as the owner of execution.

The central owners remain:

- `jarvis_core/registry.py` - `ToolRegistry` is the single tool definition source.
- `jarvis_core/service.py` - `JarvisService` is the canonical tool execution boundary.
- `jarvis_core/security.py` - `SecurityManager` is fail-closed.
- `jarvis_core/audit.py` - `AuditLog` is the canonical audit receipt path.
- `jarvis_core/task_manager/` - `TaskManager`, `TaskDatabase`, scheduler and controls.
- `jarvis_core/computer_use_mission.py` - mission planner/executor, checkpoints and durable mission records.
- `jarvis_core/memory/` and `jarvis_core/memory/v2/` - canonical memory/ECC-related memory boundary and storage.
- `jarvis_core/orchestrator/model_router.py` - canonical `ModelRouter`.

## 3. Current Architecture

| Component | Confirmed path |
|---|---|
| Jarvis Core | `studio/golden_ai_studio_web/jarvis_core/` |
| ToolRegistry | `jarvis_core/registry.py` |
| SecurityManager | `jarvis_core/security.py` |
| AuditLog | `jarvis_core/audit.py` |
| TaskDatabase / TaskManager | `jarvis_core/task_manager/database.py`, `jarvis_core/task_manager/manager.py` |
| BackgroundTaskScheduler | `jarvis_core/task_manager/scheduler.py` |
| ConditionAuditExecutor | `jarvis_core/task_manager/condition_executor.py` |
| Mission planner/executor/store | `jarvis_core/computer_use_mission.py` |
| Browser / Chrome session | `jarvis_core/browser.py` |
| Computer Use tools / UIA / vision | `jarvis_core/tools/computer_use_tools.py`, `jarvis_core/tools/ui_automation.py`, `jarvis_core/vision.py` |
| Memory / ECC-related stores | `jarvis_core/memory/`, `jarvis_core/memory/v2/` |
| ModelRouter / providers / policies | `jarvis_core/orchestrator/model_router.py`, `providers.py`, `policies.py` |
| Voice | `jarvis_core/voice_service.py`, `voice_tts.py`, `realtime_voice/` |
| Golden market/MT5 read-only adapter | `jarvis_core/tools/market_readonly.py` |
| Golden strategies/risk/backtests | `strategy_engine.py`, `strategy_audit.py`, `risk_engine.py`, `mt5_backtest.py` |
| MT5 legacy connector/trader | `mt5_connector.py`, `mt5_trader.py`, `mt5_real_backtest.py` |
| Web frontend | `jarvis_ui/`, `dashboard.html`, `studio_v7.html` |
| Desktop | `jarvis_desktop/`, `jarvis_desktop_launcher.py` |
| Legacy/auxiliary PC agent | `jarvis/pc_agent/` |

## 4. Computer Use Phases

### 3D - CLOSED

Objective: perform a bounded real Windows Notepad mission safely.

- Delivered Known Folder Documents resolution through the Windows native API, UIA/vision grounding, SecurityManager enforcement, AuditLog evidence, and `PATH_NOT_FOUND` recovery.
- A real mission wrote and filesystem-verified the exact authorized content `Golden Jarvis funcionando`.
- Relevant commits: `7b99844` (foundation), `f6bae61` (vision grounding), `b93db37` (Windows path hardening).

### 4D - base phase remains PARTIAL; 4D.1 is CLOSED/PASS

The base controlled Browser Use mission stopped correctly at external consent/anti-bot barriers and is not closed. Do not overwrite that historical fact.

- 4D.1 completed real Chrome-only controlled searches, grounded visible elements, returned three unique result URLs, and kept consent/CAPTCHA/anti-bot fail-closed.
- Main commits: `ff27271` (4D), `32372d7` (Chrome 4D.1), `3e7046b` (URL-only title guard).

### 5D - CLOSED

Objective: preserve and verify cross-application context from browser observation to Notepad under scoped approval.

- Browser-to-editor handoff is implemented with mission context/provenance and protected Save As handling.
- Main commit: `a45be50` (harden Computer Use 5D browser handoff).
- Later 6D evidence is the stronger record for durable Chrome-to-Notepad handoff; do not re-run old 5D work without a new scoped mission.

### 6D - base phase remains PARTIAL; durable implementation is complete

The base 6D real mission passed pause/resume and cross-app handoff but deliberately stopped at an unapproved Save As. Later real recovery tests were blocked by external foreground state. It is not correct to call the base Save As validation closed.

- Durable checkpoints, action receipts, MissionContext reconstruction, integrity hashes and explicit resume tokens are implemented.
- World-state recovery and foreground arbitration fail closed.
- Real evidence: Python `3.14.7` and Ollama title were observed from official pages and preserved in the same MissionContext; no unauthorized `resumo_pesquisa.txt` was created.
- Main commits: `639f147`, `2af91ac`, `1a1cec4`, `dabbb63`, `2234fef`.
- A future real retry needs a fresh authorized mission and a stable idle user session; do not resume historical targets blindly.

## 5. Computer Use 7D and 8D

### 7D - CLOSED with persisted evidence

- Internal scheduler is owned by `TaskManager` and `BackgroundTaskScheduler`; it reuses the canonical task database.
- Persistent entities: `BackgroundTask`, `TaskRun`, task claims/leases, scoped single-use approvals, task events, mission checkpoints, mission records and action receipts.
- Trigger support includes immediate, time, delay, recurring, user-idle and allow-listed condition triggers. Misfire, startup recovery and duplicate occurrence prevention are implemented.
- `WAITING_USER_IDLE` pauses rather than steals foreground. Scheduler triggers never grant GUI permission or approvals.
- `condition_audit` is handled by `ConditionAuditExecutor`, records `CONDITION_TRIGGER_SATISFIED`, and never fabricates a Computer Use mission or GUI action.
- Failed one-shot occurrences are terminal unless explicitly re-enabled; recurring failures advance to the next occurrence rather than immediately redispatching.
- Real condition retest: task `ccdf81e0-c845-43e1-be64-a426aa5c0dc1` completed exactly one run; reload and additional ticks did not create another. Historical failed task `b9d9d361-5225-44c8-9a40-65a92b9bb446` remains terminal and was not redispatched.
- Relevant commits: `e2953ec`, `84d3a36`, `e17e2a4`, `d08c288`, `45955ab`, `716c4c6`, `7101a36`.

### 8D - CLOSED (structural temporary-DB closure gate)

- Control Center, pause/resume/cancel, retry/recovery, notifications/approval projection and scheduler health reuse the same TaskDatabase/scheduler/security/audit ownership.
- `TaskDatabase` is now schema version 5. Migrations are additive; no second scheduler, queue, worker, notification database or health daemon exists.
- The closure gate passed 182 focused scheduler/security/task/approval/recovery tests using temporary databases. It does not claim the unrelated live smoke fixture is healthy.
- Relevant commits: `a4fcf00`, `436a711`, `11c89e7`, `d921468`, `7908e70`, `2eb9dd4`.
- `DISMISS_PERSISTENCE` is deferred intentionally; it is not a correctness defect.

## 6. Voice

### Current gate

`VOICE_GATE_3A/3A.1 - real microphone signal-path and input-level validation`.

- Current validated input: device `1`, `Microfone (3- USB Audio Device)`.
- Current validated output: device `3`, `Alto-falantes (3- USB Audio Device)`.
- Validated host API: MME for both paths.
- Capture contract: 16 kHz mono PCM16, 480-sample/30 ms frames. The device default may report 44.1 kHz, but the opened logical VAD stream reports 16 kHz.
- VAD: local `SileroVADAdapter`, model `silero_vad_v6.onnx`; threshold 0.5, speech-start after 3 windows, endpoint after 700 ms below threshold.
- STT boundary: local faster-whisper contract; do not change configuration or advance it until the real VAD gate passes.
- TTS: provider-neutral foundation with Windows SAPI local fallback; human listening gate recorded intelligible/acceptable playback.

### What passed

- Real microphone stream opens and delivers aligned frames.
- Mic/speaker coexistence and bounded playback abort were observed.
- Voice conversation adapters, bounded streaming TTS, session lifecycle and cancellation wiring have dedicated commits/tests.
- Relevant commits: `5b3f5d8`, `5baad28`, `b672d41`, `a7b9f51`, `e815107`, `84cd693`, `19ef609`, `0f49274`, `904f6ed`, `ec11f3d`, `3933f9b`, `85fc919`.

### What remains unvalidated

- A human-confirmed speech window exists, but its captured PCM amplitude was near the silence baseline. It did not reach VAD speech-start or endpointing.
- This is evidence of an upstream low microphone signal, not proof that Silero VAD is defective and not justification to lower production thresholds.
- The controlled real acoustic barge-in gate has no valid VAD-triggered human interruption yet. Therefore local STT receipt, valid new user turn, old-generation invalidation, and stale-audio non-resume are not validated by real human speech.
- Absence of a valid acoustic/VAD sample is not a proven VAD failure. Do not advance STT/Core/TTS behavior until a controlled real-speech gate succeeds.
- Do not implement AEC, persist microphone audio/transcripts, alter devices, thresholds, VAD, endpointing, STT or turn-taking merely to pass the gate.

Read first: `docs/architecture/JARVIS_VOICE_VAD_REAL_MIC_DIAGNOSTIC.md` and `docs/architecture/JARVIS_VOICE_ACOUSTIC_BARGE_IN_VALIDATION.md`.

## 7. Golden / MT5

- Canonical Jarvis market access is read-only through `jarvis_core/tools/market_readonly.py`: MT5 status/account/positions/orders/ticks/symbol metadata/recent candles.
- `JarvisService` registers those tools with low risk; tests enforce that the read-only adapter does not contain order execution calls.
- Golden includes scanners/strategies/risk/backtesting in `strategy_engine.py`, `strategy_audit.py`, `risk_engine.py`, `mt5_backtest.py`, `market_data.py`, `meta_strategy.py` and related UI files.
- MQL5 sources include channel-pullback, MTF range-breakout, MA/volume trend, EMA/ATR/VWAP, statistical range indicator, Golden Midas VWAP, and a universal backtest template. Compiled artifacts exist locally but are not source evidence.
- 176 local JSON backtest artifacts were observed. They are `BACKTEST_EVIDENCE`, not forward-test or live-trading evidence.
- Legacy `mt5_connector.py`, `mt5_trader.py` and `mt5_real_backtest.py` can initialize terminals or issue orders. They are non-canonical legacy surfaces and must not be invoked or wired around Jarvis security.
- Latest donor audit: `docs/architecture/JARVIS_MT5_MQL5_ROBOT_DONOR_AUDIT.md`, commit `4362c53`.
- Missing future integration: canonical Robot Catalog, provenance/evidence model, regime matcher, forward-test records and an explicit execution design gate. No real trading authority exists.

## 8. Models and AI

- `ModelRouter` is canonical. Provider adapters are in `jarvis_core/orchestrator/providers.py`; policy is in `policies.py`.
- Current policy defaults: Gemini for FAST/GENERAL/DEEP, Groq for VOICE_FAST/CODING, Ollama `qwen2.5vl:7b` for VISION, and Ollama `qwen2.5-coder:14b` for OFFLINE.
- Confirmed integration history: Gemini direct, Groq direct, Ollama direct, OmniRoute -> Ollama and Jarvis -> OmniRoute -> Ollama passed. OmniRoute is optional/experimental fallback.
- OmniRoute Groq is disabled/deferred. Direct Groq remains the route for fast/tool calling; do not reopen OmniRoute Groq investigation without a new approved gate.
- OpenRouter adapter exists but should be treated as configured/conditional, not assumed healthy without a current secret-free health check.
- `SECRET` data selects local Ollama only; cloud adapters are excluded. `LOCAL_ONLY` must never silently fall back to cloud.
- Never version API keys, tokens, credentials, `.env`, browser profiles or cookies. Provider fallback cannot bypass SecurityManager, privacy classification or audit policy.

## 9. Donor Projects and Research

Already audited or mapped donor material is documentation/reuse input only. Nothing is installed from this list by this checkpoint.

| Donor area | Classification |
|---|---|
| OpenClaw | REFERENCIA |
| Hermes Agent | REFERENCIA |
| ndunl075/Jarvis and ONEPUNCHMAN411/Jarvis | AUDITAR_DEPOIS |
| avatar, codex-chatgpt-web, FreeLLMAPI | AUDITAR_DEPOIS |
| Browser Use, UI-TARS, Microsoft UFO | ADAPTAR patterns only; Jarvis keeps ownership |
| public-apis | REFERENCIA |
| MT5/MQL5 skills and MCP donors | ADAPTAR/REFERENCIA as recorded in the MT5 donor audit |
| pp-mt5 safety patterns | ADAPTAR behind Jarvis, never grant independent trade authority |

## 10. Permanent Security Rules

- Jarvis remains the only primary orchestrator.
- SecurityManager is fail-closed; triggers do not grant permission.
- Background scheduling never means hidden GUI interaction.
- When `USER_ACTIVITY_DETECTED=YES`, do not steal foreground, type, click or move the mouse.
- Chrome is the only visible browser provider for Browser Use missions.
- Never bypass CAPTCHA, anti-bot verification, consent, login, privacy or unknown dialogs.
- Approvals are scoped and single-use when applicable.
- Do not expose credentials or version browser profiles, cookies, tokens, runtime DBs or `device_registry.json`.
- Future trading must have an explicit policy/authorization layer and use `JarvisService.execute_tool -> SecurityManager -> AuditLog`; MCP is a provider, not a trading authority.

## 11. Database and Persistence

- Canonical production task database: `C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db`.
- Confirmed current schema version: `5`.
- Confirmed tables: tasks, task steps/events/runs/approvals, background tasks, mission checkpoints/records/action receipts, and schema metadata.
- Users: `TaskDatabase`, `TaskManager`, `BackgroundTaskScheduler`, `MissionCheckpointStore`, mission executor/recovery flows, and Control Center projections.
- Legacy databases at the repository root and under `jarvis/` exist as runtime/legacy data and are not active canonical task stores. Do not delete or migrate them without a dedicated data-governance task.

## 12. Tests and Validation State

- Last test run in this session: `34 passed` for market read-only adapters, capability boundary/governance and security gate.
- Prior focused gates: 7D closure evidence is documented; 8D closure recorded `182 passed`; 4D.1 recorded `181 passed, 1 skipped`; 6D-related suites recorded up to `278 passed, 1 skipped` depending on gate.
- Full collection last documented: 1763 collected; it remains blocked by pre-existing `tests/live_smoke_test.py::test_streaming` setup error because fixture `question` is missing. This is not an 8D result.
- `py_compile` and `git diff --check` passed in prior gate work. This checkpoint session made documentation only and did not re-run a full collection.
- Current real/hardware pending validation: Voice 3A/3A.1 controlled real speech/VAD gate.

## 13. Important Commits (chronological selection)

| Commit | Purpose |
|---|---|
| `b8ae93c` | pre-Git Golden/Jarvis baseline |
| `7b99844` | secure Computer Use primitives |
| `f6bae61` | local vision grounding |
| `b93db37` | Windows Known Folder / path hardening |
| `ff27271` | controlled Browser Use 4D |
| `32372d7` | Chrome 4D.1 hardening |
| `a45be50` | Computer Use 5D browser handoff |
| `639f147` | durable Computer Use 6D workflows |
| `2af91ac` | 6D world-state recovery |
| `1a1cec4` | 6D foreground arbitration |
| `dabbb63` | durable Computer Use 6D mission records |
| `e2953ec` | internal background scheduler |
| `d08c288` | safe condition executor/no failed redispatch |
| `45955ab` | Computer Use 7D closure documentation |
| `2eb9dd4` | Computer Use 8D closure gate tests |
| `0f49274` | Windows SAPI TTS provider |
| `85fc919` | voice session lifecycle/recovery |
| `716c4c6` | canonical task database path governance |
| `d2d10d0` | capability governance read model |
| `4362c53` | MT5/MQL5/robot donor audit |

## 14. Git State at Checkpoint Creation

Pre-existing modified tracked files:

- `studio/golden_ai_studio_web/device_registry.json` (runtime/personal; never stage here)
- `studio/golden_ai_studio_web/jarvis_core/browser.py`
- `studio/golden_ai_studio_web/jarvis_core/tools/computer_use_tools.py`
- `studio/golden_ai_studio_web/tests/test_browser.py`
- `studio/golden_ai_studio_web/tests/test_computer_use.py`

Pre-existing untracked items include root planning/audit markdown, selected `config/backtest_results` JSON artifacts, runtime SQLite databases, `jarvis/jarvis/`, and desktop `build/`/`dist/` artifacts. Preserve all of them. Do not stage any runtime DB, build/dist artifact, backtest output, device registry, credential, browser state or unrelated user file by default.

`CHECKPOINT.md` is intentionally an uncommitted root handoff file at this point. Do not assume its creation authorizes a commit.

## 15. Known Real Issues

| Issue | Impact | State | Recommended next step |
|---|---|---|---|
| Voice real mic signal amplitude is near silence during human-confirmed speech | VAD/endpoint/barge-in/STT cannot be validated honestly | OPEN | Run the narrow Windows mic signal-path/input-level gate interactively; do not tune VAD first. |
| Base Browser Use 4D hit consent/anti-bot barriers | The original base mission has no approved three-title result evidence | PARTIAL | Preserve 4D.1 Chrome controls; request confirmation if a future site shows a non-benign barrier. |
| Base 6D Save As was intentionally unapproved and foreground recovery was externally interrupted | Historical mission remains partial | HISTORICAL/PARTIAL | Start a new explicitly authorized mission only in a stable idle session. |
| Full pytest has a live-smoke setup failure (`question` fixture missing) | Full green suite claim is unavailable | OPEN, pre-existing | Isolate and repair in a dedicated test-fixture task; do not mix with voice work. |
| No Robot Catalog/forward-test/regime matcher | MT5 intelligence cannot responsibly rank or activate robots | DEFERRED | Start the read-only Robot Catalog and provenance gate after current voice priority. |

## 16. Exact Next Step

```text
CURRENT_PHASE:
Voice foundation - Gate 3A/3A.1 real microphone signal-path validation.

CURRENT_GATE:
Controlled human speech must produce a normal real PCM signal and observable VAD response.

NEXT_ACTION:
Run one interactive, human-confirmed Windows microphone signal-path/input-level diagnostic on the existing approved device. Keep data in memory, preserve MME/devices, and stop for user input exactly as the harness requires.

DO_NOT_START_YET:
Do not advance STT/Core/TTS, alter thresholds, add AEC, reopen OmniRoute/Groq, run a historical Computer Use mission, start trading, or start the Robot Catalog implementation until the voice gate is resolved or explicitly reprioritized.

BLOCKERS:
Real human speech did not produce enough amplitude for VAD; full pytest also has the unrelated live-smoke fixture failure.
```

## 17. Planned Future Order

1. Resolve Voice Gate 3A/3A.1 with real interactive microphone evidence.
2. Continue Voice 2.0/natural voice only after the gate passes.
3. Desktop final stabilization/packaging validation.
4. Mobile work.
5. Golden/MT5 deep integration: Robot Catalog and provenance first, then read-only regime/forward-test intelligence.
6. Skills/MCP ecosystem expansion under the canonical capability boundary.
7. External provider/ModelRouter improvements, only with privacy/security review.
8. Production/packaging gates.

Computer Use 8D is already closed structurally; only explicitly deferred product work such as dismissal persistence should be reopened by a dedicated request.

## 18. Safe Commands for the Next Session

```powershell
Set-Location C:\GoldenAI
& C:\GoldenAI\.venv\Scripts\Activate.ps1
rtk git status --short
rtk git log --oneline -20
& C:\GoldenAI\.venv\Scripts\python.exe -m pytest studio\golden_ai_studio_web\tests\test_market_intelligence_readonly.py -q
& C:\GoldenAI\.venv\Scripts\python.exe -m pytest studio\golden_ai_studio_web\tests\test_task_scheduler_7d.py studio\golden_ai_studio_web\tests\test_computer_use_8d_closure.py -q
Set-Location C:\GoldenAI\studio\golden_ai_studio_web
.\start_jarvis_desktop.bat
```

Do not start the desktop or a real voice/browser mission while the user is actively using the computer unless the task explicitly authorizes it.

## 19. NEXT_SESSION_HANDOFF

The repository is on `main` at `4362c53`; the last committed work is the MT5/MQL5 donor audit. Do not redo Computer Use 7D/8D closure work, OmniRoute Groq investigation, or prior historical Computer Use missions. The immediate work is the interactive Voice Gate 3A/3A.1 microphone signal-path diagnostic.

Permanent decisions: Jarvis is the one Core; ToolRegistry, SecurityManager and AuditLog remain authoritative; background tasks never bypass user activity or approvals; SECRET/local-only data never silently uses cloud; MCP and donor projects never receive independent execution authority. Read the voice diagnostic and acoustic-barge-in architecture documents first, then this checkpoint.
