# Golden Scalper Arena Jarvis Tab Implementation Plan

> **For agentic workers:** use the native execution approach; this plan is a small, testable UI integration.

**Goal:** Add a native `Golden Scalper Arena` tab under `INTELIGÊNCIA E CONTROLE` in Jarvis.

**Architecture:** The desktop shell maps a new route to a new `gView`. The view requests a read-only JSON projection from the existing HTTP server and renders security state, report status, ranking and validation. A small backend helper resolves and validates the Arena report relative to the repository root.

**Tech Stack:** Python `HTTPServer`, HTML, vanilla JavaScript, existing Gateway adapter, pytest and Node smoke harnesses.

**Spec:** `docs/superpowers/specs/2026-11-08-golden-arena-jarvis-tab-design.md`

## Global Constraints

- Preserve existing Jarvis navigation, endpoints and trading protections.
- Read only; `simulation_only=true`; `execution_authority=NONE`; no order API.
- Missing/invalid report must fail closed to an explicit unavailable state.
- Do not expose secrets or run the Arena from the UI request.

## Tasks

### Task 1: Backend report projection

Files: create `studio/golden_ai_studio_web/jarvis_core/arena_panel.py`, modify
`studio/golden_ai_studio_web/server_agent.py`, test
`studio/golden_ai_studio_web/tests/test_arena_panel.py`.

- Write tests for a valid report and missing report.
- Implement a path-safe JSON reader with a fixed security envelope.
- Register `GET /api/jarvis/golden/arena/report` through the existing dispatcher.
- Run the focused test and Python compilation.

### Task 2: Native Jarvis view

Files: modify `jarvis_ui/jarvis.html`, `jarvis_ui/src/desktop-shell.js`,
`jarvis_ui/src/desktop-shell.css`, test `test_desktop_unified_shell.py`.

- Add the new navigation button beneath `INTELIGÊNCIA E CONTROLE`.
- Add route/view mappings and render the report through the authenticated Gateway.
- Add compact ranking/security/validation layout and explicit unavailable state.
- Test route presence, read-only contract and no external-window behavior.

### Task 3: Verification

- Run focused backend/UI tests, full relevant Jarvis tests, `py_compile`,
  `git diff --check`, server startup/health and a report endpoint smoke.
- Confirm no `OrderSend`, `order_send`, `trade.Buy` or `trade.Sell` was added to
  the Arena integration.

