# MASTER CAPABILITY MAP — COMPLETE

**Date:** 2026-09-19
**Status:** COMPLETE
**Functional code modified:** NO

---

## What Was Done

1. Audited and validated 195+ capabilities across 19 categories
2. Corrected classifications:
   - Golden/MT5 modules → CODE_EXISTS_NOT_CONNECTED (not in ToolRegistry, only HTTP API)
   - Voice components → PARTIAL (coded but daemon not started at construction; barge-in/streaming disabled by default)
   - Legacy read_file/write_file/PDF/code tools → LEGACY_AVAILABLE
3. Marked raw shell unsafe items (run_command shell=True, PowerShell URI interpolation, shutil.rmtree, MetaEditor PS escaping) → UNSAFE_DO_NOT_MIGRATE
4. Created canonical map: `docs/agent-context/MASTER_CAPABILITY_MAP.md`

---

## Counts (Recalculated From Matrix Rows, Unique)

| Status | Count |
|--------|-------|
| WORKING_NOW | 83 |
| CONNECTED_NOT_RUNTIME_TESTED | 0 |
| CODE_EXISTS_NOT_CONNECTED | 28 |
| LEGACY_AVAILABLE | 15 |
| PARTIAL | 13 |
| MISSING | 43 |
| UNSAFE_DO_NOT_MIGRATE | 0 |
| OBSOLETE | 0 |
| TOTAL_UNIQUE_CAPABILITIES | 182 |

Check: sum = 182 = TOTAL_UNIQUE_CAPABILITIES.

Cross-listed (counted once, kept as cross-refs):
- Lixeira (CAT 6) → counted in CAT 2 (consultar/esvaziar)
- Risk Engine (CAT 19) → counted in CAT 12

Normalization: OpenCode Integration PLANNED→MISSING; 4 UNSAFE items are audit entries, not capability rows.

- ToolRegistry: 64 tools (incl. recycle_bin_status, empty_recycle_bin)
- Tests: 126 passed / 0 failed

---

## Canonical Map

```
docs/agent-context/MASTER_CAPABILITY_MAP.md
```

Contains: architecture invariants, status definitions, inconsistencies fixed, raw shell safety audit, 19-category capability matrix, final counts, readiness assessment, implementation phases A–E.

---

## Next Implementation Phase

**Phase A — Essential PC Control:**
- read_file / write_file (migrate from server_agent.py, with path validation)
- clipboard read/write
- GPU monitoring (connect jarvis_desktop/gpu.py)
- Temperatures
- Sleep/hibernate

Then **Phase B — Golden/MT5 Integration** (register tools, fill Route.MT5/TRADING tuples, orders with confirmation).

---

## M1.5.1B — Web Research Multi-Provider Revalidation

**Date:** 2026-09-20
**Status:** PASS arquitetural/focado; suíte global atual não comparável por testes novos/ambientais fora do escopo M1.5.1B.
**Functional code modified:** YES, apenas núcleo Memory V2/research/service/testes focados; sem iniciar M1.6.

Resumo:
- `JARVIS_RESEARCH_PROVIDER=auto` usa fallback determinístico Tavily → Groq Web → Brave.
- Chaves suportadas: `TAVILY_API_KEY`, `GROQ_API_KEY`, `BRAVE_SEARCH_API_KEY`.
- Ambiente atual sem chaves reais: health retorna `missing_key`; smokes reais opcionais pulam sem inventar segredo.
- Fluxos `web_research` e `web_research_learn` preservam `SafeHTTPFetcher`, SSRF block, prompt injection como DATA, provenance e escrita de memória somente no caminho learn elegível.

Validação atual:
- Focados M1.5.1B/M1.5.1/M1.5 hardening/orchestrator: 68 passed, 3 skipped, 56 subtests passed.
- Compatibilidade market prompt: 1 passed.
- Suíte global atual: 1411 passed, 24 skipped, 44 failed, 4 errors, 89 subtests passed; falhas em testes/fixtures/dependências ambientais fora do escopo M1.5.1B.

Próximo: aguardar autorização; não iniciar M1.6.

## Computer Use 3D — Windows Known Folder Hardening

**Date:** 2026-09-23
**Status:** REAL VALIDATION PASS

- The real Notepad mission completed through `JarvisService`, UIA, SecurityManager, and AuditLog.
- Windows `Documents` is resolved with `SHGetKnownFolderPath`; no user-profile path is hardcoded on Windows.
- `PATH_NOT_FOUND` is audited, bounded, re-resolves the Known Folder, and only dismisses a matching Windows error dialog.
- Authorized result verified at the resolved Documents folder with exact content `Golden Jarvis funcionando`.
- Focused Computer Use/UIA/Vision/Security regression: 172 passed, 30 subtests passed.

## Computer Use 4D — Controlled Browser Use

**Date:** 2026-09-23
**Status:** PARTIAL — real mission blocked by browser consent/verification state

- Browser Use extends the existing singleton BrowserSession, ToolRegistry, SecurityManager,
  AuditLog, planner, and mission executor; no parallel Jarvis core was created.
- Visible Edge launch, UIA window focus guard, structured field grounding, navigation
  detection, stale-ref protection, bounded wait, and DOM/ARIA page extraction are wired
  through the existing service.
- The real mission opened Edge, focused the correct `msedge.exe` window, grounded the
  textarea search field, and reached the search page state.
- Bing exposed a cookie consent dialog (`Aceitar`, `Rejeitar`, `Mais opções`) and the
  controlled flow stopped without clicking it. A prior Google attempt exposed an anti-bot
  verification page. Neither CAPTCHA nor consent/verification barriers are bypassed.
- The phase is not CLOSED because three valid result titles were not extracted from a
  permitted result page. The safe outcome is `USER_CONFIRMATION_REQUIRED`/blocked.

## Computer Use 4D.1 — Chrome, Consent and Safe Provider Fallback

**Date:** 2026-09-23
**Status:** REAL VALIDATION PASS

- `GOOGLE_CHROME` is the only visible browser provider. Edge, Firefox, Chromium,
  Brave and Opera are disabled for this mission path; no non-Chrome fallback is used.
- Public search fallback is bounded to Google -> Bing -> DuckDuckGo inside the same
  visible Chrome session. Provider loops are prevented and a maximum of three providers
  is enforced.
- Benign cookie consent may use a grounded reject/only-necessary action through the
  existing SecurityManager/UIA/DOM path. Notifications, location, camera, microphone,
  password, default-browser prompts, login, privacy gates and unknown dialogs stop for
  user confirmation.
- CAPTCHA, Cloudflare, anti-bot verification, stealth, proxy and fingerprint bypass are
  never attempted.
- The result extractor waits for visible structured candidates, excludes navigation and
  sponsored links, and deduplicates normalized URLs before accepting three results.
- Real missions completed in Chrome for `OpenAI` and `Python`. Both validated a Chrome
  process/window and returned three unique result URLs; the Python run returned three
  `python.org` titles.
- Focused Browser/Computer Use regression: 181 passed, 1 skipped. The historical
  `172 passed + 30 subtests` count belongs to the prior 3D-focused collection; the
  current 4D-focused collection is separately reported from the full repository
  collection (`1605 tests collected`).

## Computer Use 6D — Durable Long Workflows

**Date:** 2026-09-24
**Status:** PARTIAL — real pause/resume passed; save intentionally stopped for confirmation

- Existing `ComputerMissionPlanner`, `ComputerMissionExecutor`, `MissionContext`,
  `TaskDatabase`, `SecurityManager`, and `AuditLog` were extended without a parallel workflow
  engine or database.
- Durable logical checkpoints and action receipts use the existing task database. Stored state
  is schema-versioned, integrity-checked, context-revisioned, and excludes UI coordinates,
  screenshots, cookies, browser tokens, PIDs, and other runtime-only fields.
- Resume requires an explicit `mission_id:checkpoint_id` token, revalidates world state, honors
  dependency contracts, skips verified side effects, and recovers unknown save state by checking
  the filesystem before retrying.
- Real mission `computer-use-6d-real-success-10` paused after Python extraction at
  `CHECKPOINT_PYTHON_DONE`, then resumed with a new executor. Python was not re-executed.
  Python value: `Python 3.14.7`; official source: `https://www.python.org/downloads/latest/`.
- The resumed mission obtained the Ollama title `Ollama` from `https://ollama.com/`, handed off
  Chrome to Notepad, verified the summary, and stopped at the Save As confirmation. The target
  `C:\Users\Anderson\Documents\resumo_pesquisa.txt` was not created because write authorization
  was not granted.
- Focused 6D and related Computer Use tests: `149 passed, 1 skipped`.

## Computer Use 6D.1 — World State Recovery

**Date:** 2026-09-24
**Status:** BLOCKED — recovery logic PASS; real save blocked by external app closure

- Added explicit world-state classification and fail-closed recovery for `APP_CLOSED`,
  `WINDOW_MISSING`, `DOCUMENT_MISSING`, `TARGET_CHANGED` and unknown in-flight actions.
- Recovery validates the persisted `MissionContext` and official source provenance, invalidates
  old window/document identities, opens a new mission-owned Notepad document through UIA, and
  rebuilds the summary from persisted values. Python and Ollama were not re-researched.
- Added an atomic confirmed `ui_type_editor` action and bounded native foreground activation
  to close the focus race between separate focus and keyboard calls.
- Real resume detected the closed/missing Notepad state and emitted recovery audit events, but
  the external PUBG foreground caused Notepad to disappear again before `focus-notepad` could
  be verified. The authorized target `C:\Users\Anderson\Documents\resumo_pesquisa.txt`
  remains absent and no file was written.
- Focused 6D.1/UIA regression: `59 passed`.

## Computer Use 6D.2 — Foreground Arbitration

**Date:** 2026-09-24
**Status:** PARTIAL — real user-activity guard PASS; long mission remains paused

- UIA now reports process presence, window presence, focus, minimized/occluded/background
  state, foreground owner, foreground epoch, and recent input age without recording input
  content.
- `GetLastInputInfo` uses `kernel32.GetTickCount64`; the real Windows check returned
  `last_user_input_age_ms: 0` while an external foreground application was active.
- Mission actions refuse to steal focus or send input when `USER_EXTERNAL_APP` is active.
  A real canonical `JarvisService` mission paused before `ui_focus_window`, persisted
  `CHECKPOINT_PAUSED_USER_ACTIVITY`, and emitted `USER_ACTIVITY_DETECTED` plus
  `MISSION_PAUSED_FOR_USER_ACTIVITY` in AuditLog.
- UIA typing is atomic and fail-closed on foreground HWND/epoch changes; legacy keyboard
  fallback was removed from `ui_type_editor`.
- Focus recovery is bounded to two attempts and requires explicit resume. No research was
  re-run and no authorized document was written during this validation.
- Regression: `251 passed, 1 skipped` in the focused Computer Use/UIA/security/browser set
  after the final test addition; the broader relevant set previously passed `250 passed,
  1 skipped`.

## Computer Use 6D.3 — Durable Mission Store and Safe Resume

**Date:** 2026-09-24
**Status:** STRUCTURAL IMPLEMENTATION PASS — real mission deferred for user activity

- The existing `TaskDatabase` now stores a schema-versioned `mission_records` row alongside
  logical checkpoints and action receipts. Records include mission identity, request, status,
  step position, checkpoint, context revision, pause reason, safe snapshot and integrity hash.
- Resume tokens remain mission-scoped (`mission_id:checkpoint_id`); missing, mismatched or
  tampered mission/checkpoint state fails closed as `RESUME_TOKEN_NOT_FOUND`.
- A new executor reconstructs the planner, MissionContext, provenance, step state and receipts
  from the existing database. Runtime coordinates, handles, screenshots, cookies, tokens and
  browser profiles are excluded from durable snapshots.
- Explicit resume observes `ui_user_activity` through the existing `GetLastInputInfo` path,
  waits for one configurable quiet window, resets on new input, supports cancellation, and
  never auto-resumes from background activity.
- Structural regression: `278 passed, 1 skipped` in the integrated non-real suite; focused
  6D/mission regression: `55 passed`.
- No real 6D.3 mission was started because the user reported active computer use. The next
  step is a new mission from zero only after the user authorizes a stable idle session;
  current stop marker: `REAL_USER_SESSION_REQUIRED`.

# Computer Use 7D - Condition Triggers

**Date:** 2026-09-26
**Status:** CLOSED

- The canonical task store is `jarvis/golden_tasks.db`, schema version 2. The active
  service, scheduler and mission persistence share that path.
- `condition_audit` is routed to `ConditionAuditExecutor`; it records
  `CONDITION_TRIGGER_SATISFIED` without invoking ComputerMissionExecutor or GUI input.
- One-shot failed occurrences are terminal unless explicitly re-enabled. Recurring failures
  advance to the next future occurrence and do not redispatch immediately.
- Real condition retest passed with task `ccdf81e0-c845-43e1-be64-a426aa5c0dc1` and one
  completed run. The user-created zero-byte trigger remained untouched. Durable reload and
  additional ticks produced no second run.
- The earlier failed task `b9d9d361-5225-44c8-9a40-65a92b9bb446` remains historical FAILED
  state and was not redispatched after the fix.
- Commit: `d08c288`. No push. Runtime databases, trigger files, build/dist artifacts and
  `device_registry.json` are outside the commit.
# Computer Use 7D.1 - Internal Background Scheduler

**Date:** 2026-09-25
**Status:** STRUCTURAL IMPLEMENTATION PASS - real Windows validation deferred

- Persistent background tasks reuse `jarvis/golden_tasks.db` through the existing
  `TaskDatabase`; schema v1 migrates additively to v2 with `background_tasks`,
  `task_runs`, and `task_approvals`.
- `BackgroundTaskScheduler` is the single internal scheduler owned by the existing
  `TaskManager`/`JarvisService`. It has no direct GUI, mouse, keyboard, browser, or
  process-launch path; dispatch is delegated to the canonical mission/security flow.
- Supported triggers are IMMEDIATE, AT_TIME, AFTER_DELAY, RECURRING, USER_IDLE, and
  CONDITION. Recurrence supports DAILY, WEEKLY, and INTERVAL. Conditions are an
  allow-listed registry with injected providers and no eval/exec/shell/PowerShell.
- SQLite `BEGIN IMMEDIATE` claims, leases, unique `(task_id, scheduled_for)` occurrences,
  startup recovery, scoped single-use approvals, cancellation, enable/disable, and
  audit events prevent duplicate dispatch and unsafe resume.
- `SystemClock` and `FakeClock` keep scheduling deterministic and testable.
- Automated structural/integrated validation passed: `90 passed, 8 subtests` in the
  7D.1 scheduler plus existing TaskManager and Computer Use 6D collections.
- No real Windows action was executed in 7D.1. Final gate: `REAL_USER_SESSION_REQUIRED`.
