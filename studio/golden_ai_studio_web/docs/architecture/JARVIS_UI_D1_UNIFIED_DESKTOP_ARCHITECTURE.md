# JARVIS UI-D1 — Unified Desktop Architecture

**Status:** implementation-ready architecture; no runtime/code implementation in UI-D1.

**Product target:** the existing **Golden Jarvis Desktop**, not `dashboard.html`, a standalone site, or five independent template pages.

## Current Desktop Audit

| Concern | Current source-backed state |
|---|---|
| Framework / shell | PySide6 native `QMainWindow`; active entry `jarvis_desktop.web_app:main`; single-instance and system-tray lifecycle. |
| Main window / rendering | `jarvis_desktop.web_window.DesktopMainWindow` owns a `QWebEngineView`; its source loads the canonical `jarvis_ui/jarvis.html`. The same shell can open a separate `MarketIntelligenceWindow` for `market.html`. |
| Core lifecycle | `CoreLauncher` probes/reuses the server and Gateway; it starts only its own child if required and refuses to claim an occupied-but-unhealthy Gateway. Desktop exit preserves non-owned Core lifecycle semantics. |
| Authentication bootstrap | `DesktopIdentityManager` obtains/reuses Gateway-issued device identity; `DesktopCredentialStore` stores DPAPI ciphertext. `DesktopMainWindow` and market window install a DocumentCreation script that writes the already-paired identity into same-origin WebView localStorage. `http-perimeter-client.js` attaches Bearer and request ID; `GatewayAdapter` authenticates the existing Gateway protocol. No token belongs in source, HTML, logs or ordinary settings. |
| Jarvis integration | Canonical `jarvis_ui` has chat/voice UI and `GatewayAdapter`; gateway routes commands to the existing `JarvisService`. HTTP read projections use the authenticated server perimeter and the same service. |
| Control Center | Current web UI has Jarvis module/control surfaces; native `ControleView`, tasks/ops/config views also exist in `MainWindowV4`, an alternate entry path. Consolidate navigation without creating a second authority. |
| Market integration | `market.html` is currently opened as a separate `QWebEngineView` window. It shares the Desktop WebEngine profile and receives the same protected identity injection. This is an existing view donor, not a second Core. |
| Navigation | Canonical web UI currently has Jarvis-oriented modules (conversation/control/projects/analysis/automation and more); market is a separate window. Native V4 uses CONVERSA/CONTROLE `QStackedWidget` plus secondary legacy views. Neither currently represents the complete donor target in one workspace. |
| Build / packaging | PyInstaller `JarvisDesktop.spec` packages the lightweight client; entry is `jarvis_desktop_launcher.py`. Runtime/Core and data remain external. `jarvis_desktop.startup` launches `python -m jarvis_desktop.web_app --hidden`. |

`dashboard.html` remains a functional donor only. UI-D1 does not repair it. No new frontend app, Core, auth authority, task system, database, memory engine, or trading path is proposed.

## Options Evaluated

| Option | Fidelity | Reuse / auth | Cost and risk | Decision |
|---|---|---|---|---|
| Native PySide6 widgets | Strong desktop integration; chart/table fidelity would need substantial bespoke work. | Reuses shell and API client, but needs a broad new presentation layer. | Highest view migration and visual-parity effort; split web/native semantics can grow. | Not selected as primary. Keep native shell responsibilities and useful widgets. |
| Qt Quick / QML | Flexible desktop visuals. | New presentation runtime; current canonical UI/auth would not be reused directly. | New architecture and packaging risk; low donor-code reuse. | Reject for this migration. |
| Five donor HTML pages / standalone web app | Initial screenshot similarity. | Breaks one-shell/auth ownership and duplicates navigation/runtime. | Parallel frontend, external CDN dependency, fake data and direct-MT5 affordances. | Reject. |
| Embedded frontend inside existing QtWebEngine shell | High donor fidelity with one view/state system. | Reuses existing PySide6 shell, protected identity injection, canonical Jarvis UI and authenticated perimeter. | Requires disciplined modular views, local assets and lazy rendering. | **Selected.** |
| Hybrid native shell + rich embedded workspace | High fidelity and native lifecycle. | Matches current active architecture. | Valid only when one `QWebEngineView` remains the sole feature workspace; do not spawn one WebView/window per feature. | Selected as the implementation shape of the prior option. |

## Target Architecture

```text
Golden Jarvis Desktop (PySide6 owner: window, lifecycle, tray, identity)
  └─ one canonical QWebEngineView / one same-origin Jarvis UI application
       ├─ shared status bar + navigation + active workspace
       ├─ lazy-mounted donor-derived views
       └─ persistent Jarvis chat/context surface
            ├─ authenticated HTTP read client → HTTP perimeter
            │    → existing JarvisService/read models → capabilities → AuditLog
            └─ existing authenticated GatewayAdapter → JarvisService
                 → ToolRegistry / SecurityManager → provider/capability → AuditLog
```

Implementation should fold Market Intelligence into the existing application workspace rather than opening a second feature window. A user may still open the whole Desktop as a window; the feature views themselves are one navigation state and one shell. Only the active/needed view polls or renders heavy charts. `market.html` may donate its existing chart/rendering components only after their data source, freshness and provenance are mapped; no hidden duplicate polling/subscriptions.

### Shell responsibilities

- **PySide6:** app identity, single instance, process ownership, window geometry, tray, WebEngine permissions, protected device identity injection, and controlled lifecycle.
- **Presentation application:** active view, filters/selection, loading/error/empty state, view context, and rendering only. It cannot authorize actions or invent market/business state.
- **HTTP perimeter / Gateway:** authenticate the Desktop identity. Missing/invalid identity remains rejected; origin/CORS policy remains unchanged.
- **JarvisService:** canonical read/action boundary; `ToolRegistry`, `SecurityManager`, approvals, canonical task system, memory, Market Intelligence, Robot Intelligence and AuditLog remain authoritative.
- **Providers/capabilities:** only the existing canonical modules. No UI direct-to-MT5, broker, DB, model provider, filesystem or task database.

## Navigation Contract

One persistent left navigation; no tab/window per donor. Exact destinations:

| Name | Icon concept | Purpose / primary owner | Subviews | Bounded context passed to Jarvis | Security |
|---|---|---|---|---|---|
| Jarvis | conversation | Existing Jarvis chat; JarvisService/Gateway | conversation, sessions | active view, selected entity IDs, explicit question | Authenticated; tool actions still SecurityManager-gated. |
| Painel | overview | Health/read-only summary; JarvisService projections | system, market, tasks, approvals, evidence | time range, selected symbol, visible summary IDs | Read-only. |
| Análise GoldenAI | chart/search | MarketSnapshot, scanner, macro, validation, risk | radar, symbol, deep analysis, sources | symbol, timeframe, mode, snapshot ID, freshness | Read-only analysis; never implies order authorization. |
| Operações | activity | Read-only position/order/status projections where available | positions, pending, protection, alerts | selected record IDs and source timestamp | Read-only by default; mutations absent until separately gated. |
| Performance | chart | Journal/tester/campaign evidence, separately typed | live journal, backtest, simulation, robot | evidence IDs, period, provenance class | Read-only. |
| Histórico | history | Journal, tester/campaign history, AuditLog as distinct sources | trades, test runs, campaigns, audit events | record ID/source class/time window | Read-only; audit records never presented as trades. |
| Robôs | bot | RobotCatalog/RobotIntelligence | catalog, detail, artifacts, evidence, campaigns | robot ID, artifact hash, campaign ID | Read-only catalog; repertoire is not trade authorization. |
| Backtests | flask/chart | StrategyTesterAdapter and evidence bridge | historical, plan, preflight, result | campaign/run/robot/artifact IDs | Planning/read-only by default; execution requires a separate explicit authorization gate. |
| Tarefas | checklist | existing TaskManager/BackgroundTaskScheduler/ControlCenter | queue, run, approval, history | task/run/approval IDs | Controls only through canonical SecurityManager and scoped approval. |
| Memória | brain | existing Memory Service/Memory V2 | working, long-term, knowledge/retrieval | bounded memory IDs and source provenance | Existing memory authorization and provenance. |
| Segurança | shield | SecurityManager, approval state, AuditLog | pending approvals, policy, receipts | request/approval/audit IDs | Security authority only; explicit scoped one-use decisions. |
| Configurações | settings | existing app configuration | appearance, local preferences, providers status | no arbitrary secret or page content | Secrets remain in protected stores; no credentials in view context. |

“Mais” may group lower-frequency destinations, but it does not become a second navigation system. Jarvis remains reachable from every view via the persistent contextual surface.

## DesktopViewContext

Future contract is a small allow-listed value object, not DOM scraping:

```text
DesktopViewContext {
  schema_version,
  active_view,
  selected_symbol?, selected_timeframe?, selected_time_range?,
  analysis_mode: ANALYSIS | BACKTEST | SIMULATION | LIVE,
  selected_robot_id?, selected_campaign_id?, selected_test_run_id?,
  visible_entity_ids: bounded list of canonical IDs,
  source_freshness: {source_id, observed_at, state},
  security_mode,
  correlation_id
}
```

Validate enum values, field lengths, entity count and timestamps at the boundary. No arbitrary HTML, hidden page text, account secrets, raw positions, device token, model prompt, user files or executable directives enter this context. Context informs a question; it never grants capability, approval or execution authority. JarvisService remains the owner of conversation, policy and audit correlation.

## Operational Modes and Adaptive States

- Persistent mode is explicit: **ANÁLISE**, **BACKTEST**, **SIMULAÇÃO**, **LIVE**. The default is ANALYSIS. LIVE is visually unmistakable, unavailable without a distinct server-authoritative authorization state, and never inferred from MT5 connectivity, an active repertoire entry, a donor signal or a selected robot.
- Keep independent states for Jarvis Core, Gateway/auth, provider, market source/freshness, MT5 connection, security mode, approval count, task/run, campaign, tester evidence, memory availability, robot identity, and selected market. “Unknown” is not “online”; stale data is not current; disabled source is not zero-valued data.
- Render `LOADING`, `EMPTY`, `SOURCE_UNAVAILABLE`, `STALE`, `DISABLED_BY_PROFILE`, `AUTH_REQUIRED`, `APPROVAL_REQUIRED`, `ERROR`, and `READY` distinctly. Every state carries source/timestamp/provenance when applicable.
- Offline/local mode retains shell/navigation/chat history behavior only where already supported; it never fabricates market status or declares success for unavailable data.

## Major-View Data and Action Contracts

All views expose: `UI_READ_MODEL`, `UI_ACTIONS`, `UI_SECURITY_STATE`, `UI_APPROVAL_REQUIREMENTS`, `UI_PROGRESS_STATE`, `UI_ERROR_STATE`, `UI_AUDIT_LINK`, `UI_PROVENANCE_VIEW`, `UI_EMPTY_STATE`, `UI_DISABLED_STATE`.

| View | Read model | Actions and approval | Progress / errors / audit / provenance / empty & disabled |
|---|---|---|---|
| Painel | Existing health and read snapshots; no fused fabricated KPI. | Refresh/navigation; no order action. | Per-source loading/error/freshness, correlation link; empty components remain explicit; disabled source identifies profile/policy. |
| Análise GoldenAI | Existing MarketSnapshot/Market Intelligence, scanner, risk and validation projections. | Select symbol/timeframe/period; request existing analytical read only. No “execute signal”. | Show snapshot ID, provider/source timestamps, stale/unavailable/disabled reason; link request ID/AuditLog where emitted. |
| Operações | Canonical observations only when a source is available; do not substitute donor/demo rows. | Filters/selection. Close/modify/order controls are not in D1 scope. Any later mutation needs separate design, explicit authorization, SecurityManager, scoped approval and AuditLog. | Unknown/disabled is not “no positions”; data timestamp and source. No fake “live”. |
| Performance | Trade Journal and tester/campaign evidence as separate evidence classes. | Period/source filters; exports only if canonical export artifact is implemented and audited. No parameter tuning. | Sample sufficiency, metric definition, robot/artifact/run IDs, freshness; source-specific empty state. |
| Histórico | Trade Journal, tester/campaign records, and AuditLog in distinct source adapters. | Filters, details and source-specific export only. No ticket-to-MT5 action. | Stable source ID, timestamp, provenance chain and pagination; missing source gets its own empty/unavailable state. |
| Robôs | Robot Catalog and Robot Intelligence projections. | Inspect/select; status mutations remain separately authorized canonical actions. No execution from catalog. | Distinguish catalog/repertoire/artifact/tested artifact/parameters/evidence/campaign/authorization; unknown identity is explicit. |
| Backtests | Historical native results, plans, dry-run/preflight and authorized result artifacts. | Inspect/compare. A future start action requires preflight, new run identity, immutable manifest and a separate human gate. | Per-stage lifecycle, artifact hashes, config/parameter reconciliation, stale-artifact guard, audit. Planned is never “executed”. |
| Tarefas | Existing task DB/control center, runs, approvals and scheduler diagnostics. | Existing task controls only via canonical TaskManager/SecurityManager; approval remains scoped and one-use. | Real step/progress and waiting reason, durable IDs, audit, empty queue and disabled operation semantics. |
| Memória | Existing Memory Service / Memory V2 retrieval and records. | Existing memory actions only; no new engine. | Source/provenance, freshness/lifecycle and policy errors; empty memory distinct from retrieval failure. |
| Segurança | SecurityManager policy, pending approvals and AuditLog receipts. | Explicit approve/deny with exact scope and existing confirmation semantics. | Pending/expired/stale/consumed/denied states visible; every decision links to audit evidence. |

## UI-D1 Boundary

This document defines shell, contracts and authority. UI-D1 does not create a page, endpoint, widget, schema, database migration, provider integration, voice test, trading flow, tester run, MQL5 compile, or runtime change. UI-D2 begins with shell/navigation implementation only after this architecture and baseline are reviewed.
