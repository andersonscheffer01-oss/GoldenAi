# JARVIS UI-D1 — Desktop Migration Plan

**Current gate result:** architecture and donor audit complete; implementation intentionally not started.

**Scope invariant:** migrate inside the existing Golden Jarvis Desktop, preserving one Core, service, security model, task DB, memory system and audit authority.

## Phase Sequence

| Gate | Scope | Likely files / owners | Risk and dependency | Runtime proof | Human visual proof / checkpoint |
|---|---|---|---|---|---|
| **UI-D2 — Unified Desktop Shell** | Consolidate navigation, top status, view container and persistent Jarvis entry into the existing `DesktopMainWindow` + canonical `jarvis_ui`. One `QWebEngineView` owns feature workspace; retain protected identity injection and existing Core reuse. No feature data migration yet. | `jarvis_desktop/web_window.py`, existing `jarvis_ui/jarvis.html`, `jarvis_ui/src/app.js`, `src/styles.css`, local fonts; PyInstaller spec only if a new local asset needs packaging. | Shell changes can regress boot/auth/market navigation. Depends on identity and ownership tests; no new auth code or second Core. | Existing Desktop launch/reuse/health, same-origin Bearer perimeter, page load, internal view switching, one Core/one WebView, no external CDN requests, no MT5/Voice/provider starts. | At 1366x768, 1920x1080, 2560x1440 and DPI 100/125/150: no blank view, clipped controls or auth loop; old functions remain reachable. Checkpoint only exact UI-D2 files. |
| **UI-D3 — Five Donor View Fusion** | Implement Painel, Análise GoldenAI, Operações, Performance and Histórico as views of the unified shell. Port hierarchy/components, not demo markup/data/actions. Add Robôs, Backtests, Tarefas, Memória and Segurança entry points to avoid loss. | New focused view modules/assets under existing `jarvis_ui` (or its established organization), shared components and navigation; no new HTML app. | High visual surface/risk of accidental fabricated values. Depends on D2 shell and design token sign-off. | Static/mock-free UI-state tests, keyboard/focus, lazy mount/poll pause, all views render empty/disabled/error fixtures. | Donor-to-target screenshot comparison for each view; “Lia” visible references zero in shipped UI; no fake PnL/orders/prices; dangerous controls absent. |
| **UI-D4 — Canonical Read Models** | Bind each component only to existing JarvisService/read-model routes; add no parallel business logic. Preserve source classes, freshness and provenance. | Existing `server_agent.py` route adapters only if a proven read contract is absent; `jarvis_core/golden_bridge.py`, `service.py`, market/robot/tester read models, front-end API client and focused tests. | Medium/high due to data/source semantics. Depends on D3 component contracts and endpoint characterization; do not modify legacy routes as shortcut. | Focused service/API/UI tests; authenticated route success and missing/invalid Bearer rejection; CORS and profile behavior; no provider calls, MT5, tester or trading. | Human confirms radar/market state, evidence links, catalogs and empty/unavailable states match actual canonical source; no mock values. |
| **UI-D5 — Contextual Jarvis** | Pass bounded `DesktopViewContext` (allow-listed IDs and view selections) to the existing Jarvis surface; no DOM scraping or UI execution privilege. | `jarvis_ui/src/app.js`, `gateway-adapter.js` only if contract requires; existing `JarvisService` context/audit integration and focused tests. | Context leakage or enlarged authority. Depends on stable D3/D4 view IDs and the current canonical Jarvis session. | Schema allow-list/size tests, redaction tests, existing service/security/audit tests, context correlation proof. | Human confirms Jarvis remains reachable and accurately sees only the selected supported entity/context; actions still require canonical security. |
| **UI-D6 — Adaptive State, Security and Approvals** | Unified source-state vocabulary, status bar, exact approval scope/state, task/run/campaign progress and operational mode distinction. | Shared shell/components; existing `SecurityManager`, `AuditLog`, task Control Center and source DTOs; tests only for view mappings and canonical contracts. | Incorrectly showing “ready/live/approved” is critical. Depends on canonical state payloads and UI-D4 provenance. | State-matrix tests; approval expiration/stale/one-use tests through existing services; `LIVE` unavailable absent authoritative gate. | Visual review of all warning/disabled/approval/live/offline/stale states, including color-independent labels. |
| **UI-D7 — Fidelity, Runtime and Migration Closure** | Close parity, performance, packaging, accessibility, existing function discovery and rollout/rollback. | Existing Desktop packaging/startup paths; test manifests and architecture checkpoint docs. | Distribution and user-workflow risk. Requires D2–D6. | Launch packaged application, one-Core/one-view checks, authenticated routes, no CDN, lazy chart/polling behavior and regression suites. No trading campaign implied. | Side-by-side screenshots at target resolutions and DPI; user validates every view and key legacy function; checkpoint exact files, no push absent request. |

## Migration Rules

1. Do not modify any donor ZIP or copy donor demo values into fixtures that could be mistaken for live data.
2. The current Desktop shell and protected identity flow own desktop authentication. No new browser pairing path, auth system, hardcoded token or reduced perimeter.
3. Reuse `JarvisService`, ToolRegistry, SecurityManager, canonical TaskManager/`golden_tasks.db`, Memory V2, MarketSnapshot/Golden bridge, Robot Catalog/Intelligence, tester evidence, and AuditLog.
4. No direct UI-to-MT5, UI-to-broker, UI-to-database or UI-to-provider path. Operations in D1 remain observation-only. A future mutation surface needs its own reviewed gate.
5. The LIVE mode is not inferred from MT5 connection, robot catalog/repertoire, presence of a signal, or any donor badge.
6. Keep views lazy: inactive charts stop expensive rendering/polling; a single source subscription is shared instead of one per view.
7. Each gate reviews the exact Git diff against its starting state. Preserve all pre-existing dirty work and do not stage broad globs.

## UI-D2 Entry Criteria

- Review and accept the five UI-D1 architecture documents.
- Confirm the actual packaged launch path remains `jarvis_desktop_launcher.py` → `jarvis_desktop.web_app` and one Jarvis Core.
- Resolve any runtime/auth environment drift before live visual testing; do not restart or reconfigure a user-owned process as part of D1.
- Agree the explicit design token reconciliation in `JARVIS_UI_D1_DESIGN_SYSTEM.md`.
- Keep current worktree pre-existing modifications untouched; no UI-D1 commit was created.

## Visual Comparison Protocol

For each donor, compare its supplied screenshot to the active Jarvis Desktop at 1366x768, 1920x1080 and 2560x1440, with 100/125/150% DPI. Checklist: shared shell proportions; active navigation; density/ordering of primary panels; numeric alignment; state labels; no clipping/overlap; chart/table legibility; focus/keyboard path; visible Jarvis entry; and exact source/freshness label. Record intentional differences (for example: removing fake numbers and trade actions) rather than claiming pixel-perfect parity. Use screenshot overlays/diffs only after the target is implemented and source data is known; a visually matching demo value is a defect, not fidelity.

## UI-D1 Closure Facts

- Five donors inspected in full at screenshot, design-brief and HTML levels; their order is based on content, not filename suffix.
- Five distinct screens are one application; five repeated chrome implementations merge into one shell.
- Current active Desktop uses PySide6 + the existing canonical QtWebEngine UI and protected identity. Keep that architecture and consolidate the market window into the workspace in a future implementation gate.
- Product identity is Jarvis for assistant/system and GoldenAI for analytical intelligence; the donor’s Lia persona is not part of the future UI.
- No functional code, runtime, DB, device registry, provider, voice, MT5, tester or broker state was changed by UI-D1.
