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
