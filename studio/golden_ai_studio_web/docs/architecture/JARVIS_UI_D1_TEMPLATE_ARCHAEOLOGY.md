# JARVIS UI-D1 — Template Archaeology

**Status:** audit complete; documentation only

**Baseline observed:** `main` at `cae6dd3f4a8aea9347024d28816c84748fec6ead`

**Inputs:** five user-supplied ZIPs `(3)` through `(7)`; originals were not modified. Screenshots, `DESIGN.md`, and `code.html` were all inspected.

## Evidence and View Mapping

| Donor | ZIP SHA-256 | Screenshot / code identity | Intended view | Evidence in screenshot and markup |
|---|---|---|---|---|
| `stitch_painel_forex_golden_jarvis (7).zip` | `DBF35A27C4A68CDC4432D71E4F30BFADB619C716D77922C7982B395733DFBB15` | `screen.png`, `code.html`; code SHA `8E17CCC8C288D5C7842EF533B2A389AA2E1F97740CCC45ED8443955B4AE0D9E0` | Painel / Home | Operational summary, market thesis, position placeholder, illustrative daily performance and recent history. |
| `stitch_painel_forex_golden_jarvis (3).zip` | `41E73388B59A0452570C11229BC47707E366A2261CBAEDF57C057F94244A439C` | `screen.png`, `code.html`; code SHA `DA48EA9D33B8CB6F67345C16B5B04E53F6ADF3DDC39C57C3B48134DC84AAD3DD` | Análise GoldenAI | Market thesis, audio-summary mock, entry/stop/target examples, staged protection, quantitative checklist, volatility/dispersal curve. |
| `stitch_painel_forex_golden_jarvis (4).zip` | `5B62001922CCF34B190BB642A588A7AA85884564AC66652DBB3FA0F3953B7A3A` | `screen.png`, `code.html`; code SHA `1B33CD1FD17EF3B8B25A9CE6B72BCFF3C1DFEDE9B600419D1D09C5F824F92099` | Operações | Open/pending orders, exposure, PnL, protection, direct MT5 controls and bridge console. Several controls imply live mutations. |
| `stitch_painel_forex_golden_jarvis (5).zip` | `15FECBE1695C8C6ACDDC031AC53BD7688C8BA1CACB1012EB4DCE28A5E0943C95` | `screen.png`, `code.html`; code SHA `90F109D085253D7F6B6382B0FCB1B305EF10BCA80C43D9D45C524DEDFC05E5C4` | Performance / Estatísticas | Equity curve, per-asset results, session/time matrix, filter efficacy and aggregate metrics. |
| `stitch_painel_forex_golden_jarvis (6).zip` | `A9E0561833B1F149BB1871FADD81462B4DB3A38E261ABA43DB122998D39DF7B3` | `screen.png`, `code.html`; code SHA `4F40DB470FC98FDB2F02F96D0AA3181A52F0601A2D1C5BFE4CEA7D067A18FF70` | Histórico | Filterable trade ledger, detail/“thesis” inspector, export affordances and pagination. |

All five `DESIGN.md` files have the same SHA-256: `17A539FB66FBCB78368518202DC36A3F7D22FAAEB5954D323D7BDF0EEA80FA57`. This is one shared design brief, not five independent specifications. It names the general product “Terminal Analítico Institucional” and describes a professional, high-density Forex terminal.

## Shared Shell and Design Intent

All screenshots show one consistent shell: dark graphite canvas; fixed top bar with Golden Jarvis branding, connection/analysis/demo indicators, refresh and operator control; left navigation for Painel, Análise, Operações, Histórico and Estatísticas; a bottom MT5/account status block; dense workspace content. Repeated labels, navigation and status controls belong to the shared shell, not duplicated per view.

The brief specifies Inter for text, JetBrains Mono for market numbers, compact 4/8px spacing, restrained 4–8px radii, thin separators, gold as identity/analysis accent, blue as neutral analytical accent, green/red as semantic outcome colors, and low-shadow surfaces. It also specifies responsive layouts, while the product target is Windows desktop first.

**Design brief inconsistencies:** YAML tokens use `surface: #10141a`, `primary: #fabc45`, `secondary: #a2c9ff`, `tertiary: #67df70`; prose instead names `#0D1117`, `#D29922`, `#58A6FF`, `#3FB950`. The prose also says roundness “1” but specifies radii up to 12px. UI-D2 must resolve these into one explicit token set; see `JARVIS_UI_D1_DESIGN_SYSTEM.md`.

## Donor Findings

### ZIP (7) — Painel

- **Screenshot analyzed:** yes. Three-column analytical composition below the shared shell: market thesis/evidence, position-state diagnostic, and operational-plan example; lower area has a daily-equity chart and recent-history table.
- **HTML analyzed:** yes. Repeats shared navigation/status chrome; headings identify “Lia — Análise do Mercado”, “Situação da Posição”, “Plano Operacional”, “Desempenho no Dia” and “Histórico de Operações”.
- **Unique components:** executive summary, compact evidence list, explicit no-open-position empty state, summary chart/history.
- **Charts/tables:** illustrative daily equity line; recent-operation rows.
- **Controls/status:** symbol/signal display, voice “Ouvir”, “fazer análise”, demo badge, Jarvis/Lia status, MT5 sync/account card.
- **Interactions:** analysis/audio affordances call demonstration toast handlers; no HTTP, WebSocket, or chart-library data source was found.
- **Lia:** 21 whole-word references in HTML; `DESIGN.md` has none.
- **Mock data:** demo counts, win/loss totals, dollar PnL, signal direction, confidence, entry/stop/target, account and MT5 status. Treat all as `STATIC_DESIGN_EXAMPLE`.
- **Potentially dangerous:** displayed signal/entry levels and “fazer análise” are not authority to execute; all require canonical read data and truthful unavailable states.
- **Decision:** `KEEP` the hierarchy and useful empty state; `ADAPT` to canonical home read models and freshness; `MERGE` shared shell; `REJECT` demo metrics and success claims. Map to **Painel**.

### ZIP (3) — Análise GoldenAI

- **Screenshot analyzed:** yes. Dense analytical workspace with recommendation/evidence on the left and quantitative checklist/volatility curve on the right.
- **HTML analyzed:** yes. Headings identify audio synthesis, thesis/recommendation, MT5 entry parameters, staged position protection, eight quantitative criteria, and intraday dispersal/volatility.
- **Unique components:** thesis plus evidence, criterion-by-criterion checklist, volatility visualization, provenance-like audit/footer labels.
- **Charts/tables:** static SVG-style curve and compact quantitative rows.
- **Controls/status:** symbol/timeframe labels, “varredura completa”, audio play, clipboard-like value affordances, confidence and checklist status.
- **Interactions:** visible actions are local demo handlers; no `fetch`, `XMLHttpRequest`, WebSocket or chart-library runtime was found.
- **Lia:** 19 whole-word references in HTML; `DESIGN.md` has none.
- **Mock data:** prices, stops/targets, score/confidence, confluence, volume uplift, timing, regime and audit IDs are illustrative.
- **Potentially dangerous:** entry/SL/TP, staged protection and “varredura” must remain analytical display only unless a separately approved canonical workflow exists. No donor order callback is reusable.
- **Decision:** `KEEP` evidence-first density; `ADAPT` to MarketSnapshot, scanner, macro/event context, validation, risk and provenance; `MERGE` the market context selector; `REJECT` generated-looking claims and execution parameters without canonical evidence. Map to **Análise GoldenAI**.

### ZIP (4) — Operações

- **Screenshot analyzed:** yes. Compact operational summary above open-position table, pending-order table, direct-MT5 order-entry panel and bridge-message console.
- **HTML analyzed:** yes. Headings explicitly name live custody, pending book/signals, direct MT5 sending and bridge messages.
- **Unique components:** position/order ledger, protection state, risk-entry inputs, emergency actions, bridge status/log.
- **Charts/tables:** open-position and pending-order tables; small PnL trace.
- **Controls/status:** close-all/panic, breakeven, close/partial/modify stop, execute/cancel pending order, Buy/Sell market, copy-signal toggle, lot/SL inputs, export/refresh/log controls.
- **Interactions:** controls call local `triggerAction`/toast demonstration functions; no actual backend transport was found. The apparent success copy is not execution evidence.
- **Lia:** 16 whole-word references in HTML; `DESIGN.md` has none.
- **Mock data:** account number, position/order tickets, margin, exposure, PnL, broker latency, spreads, risk, bridge messages, HMAC/session and “live” states. All are `STATIC_DESIGN_EXAMPLE`, not runtime evidence.
- **Potentially dangerous:** every order, position, copy-trading, panic-close, breakeven, stop movement and pending-order mutation. Never reuse donor handlers or connect UI directly to MT5/broker.
- **Decision:** `KEEP` the scannable ledger and explicit state hierarchy; `ADAPT` to canonical read-only observation and approval/status projections; `MERGE` only read-only alerts/protection display; `REJECT` donor mutation controls and simulated success. Map to **Operações**.

### ZIP (5) — Performance

- **Screenshot analyzed:** yes. Dense quantitative report, KPI strip, equity curve, per-asset allocation/results, session matrix and filter-efficacy section.
- **HTML analyzed:** yes. Headings identify institutional quantitative report, long-term equity curve, per-asset results, session/time matrix and filter efficacy.
- **Unique components:** performance comparison, session/time segmentation, filter diagnostics, period selector and export affordances.
- **Charts/tables:** static SVG-like equity plot; per-asset rows; weekday/session table; aggregate KPI fields.
- **Controls/status:** 7D/30D/90D/all filters, export CSV/PDF, curve/candle toggle, analysis/audio and filter-adjustment affordances.
- **Interactions:** period/tab and toast behavior only; export/adjustment messages simulate capability, with no durable export/service call found.
- **Lia:** 15 whole-word references in HTML; `DESIGN.md` has none.
- **Mock data:** balance, profit, drawdown, win rate, Sharpe, expectancy, per-asset PnL, sample size, filter effects and audit claims. All are `STATIC_DESIGN_EXAMPLE`.
- **Potentially dangerous:** “adjust filter parameters” is a configuration mutation, not a visualization; export can imply an audit artifact that does not exist.
- **Decision:** `KEEP` comparisons and segmentation; `ADAPT` to separately labeled Trade Journal, tester and campaign evidence; `MERGE` filter diagnostics with robot intelligence only when the source supports it; `REJECT` invented metrics and toast-only export. Map to **Performance**.

### ZIP (6) — Histórico

- **Screenshot analyzed:** yes. Filter row, summary strip, execution ledger and right-side selected-trade/audit thesis inspector.
- **HTML analyzed:** yes. Heading identifies “Histórico de Ordens & Registro de Confluência”; code includes filterable rows, detail drawer, pagination and export affordances.
- **Unique components:** time/asset/exit filters, selectable ledger rows, detail/evidence inspection, paginated history.
- **Charts/tables:** execution table and selected-operation detail; no separate live chart source.
- **Controls/status:** period filters, all-assets/exit selectors, CSV/PDF, page controls, copy-ticket affordance.
- **Interactions:** local row selection/filter/pagination and toast/export demonstration; no backend request found.
- **Lia:** 18 whole-word references in HTML; `DESIGN.md` has none.
- **Mock data:** tickets, symbol, side, size, timestamps, fills, duration, PnL, score, confluence and thesis. All are illustrative.
- **Potentially dangerous:** copy ticket to MetaTrader is an external-action affordance; must not become an order/deep-link shortcut. Audit events are not trade records.
- **Decision:** `KEEP` filtering and detail inspection; `ADAPT` to distinct Trade Journal, tester/campaign and AuditLog sources; `MERGE` only through linked provenance IDs; `REJECT` fabricated rows and ticket execution/copy semantics. Map to **Histórico**.

## Cross-Donor Findings

- The HTML files are five variations of the same shell and Tailwind utility vocabulary. Their `DESIGN.md` is byte-identical.
- Each HTML loads Tailwind from `cdn.tailwindcss.com`, Google Fonts, and Material Symbols remotely. This conflicts with offline/local-first reliability; the Desktop target must use packaged/local assets and must not add runtime CDN dependencies.
- Static inspection found no donor `fetch`, XHR, WebSocket or Chart.js/ECharts connection. Canvas/SVG and values are hand-authored visual examples; button messages are demo toasts.
- All five HTML files have visible and internal “Lia” identity references: ZIPs `(3..7)` contain 19, 16, 15, 18 and 21 whole-word occurrences respectively. These are historical donor findings, not approved product labels. Future UI uses **Jarvis** for assistant/system identity and **GoldenAI / Análise GoldenAI** for analytical identity. Do not mechanically replace all labels with one term.
- Shared and repeated: brand/status top bar, left navigation, Demo indicator, account/MT5 footer, gold accent, dense analytical workspace. View-specific: thesis/checklist (analysis), execution ledger/controls (operations), quantitative plots (performance), filters/audit inspector (history), executive summary (home).

## Current Desktop and Function Preservation

The active Desktop entry is `jarvis_desktop.web_app`: `CoreLauncher` reuses/starts the existing server, `DesktopIdentityManager` provisions the device identity, and `DesktopMainWindow` renders the canonical `/jarvis_ui/jarvis.html` in a `QWebEngineView`. Its authenticated HTTP helper and Gateway adapter are existing integration points. The shell currently opens `market.html` in a second `MarketIntelligenceWindow`, sharing the WebEngine profile and protected Desktop identity. Native `MainWindow`/`MainWindowV4` and widget views exist as alternate/legacy paths; the PyInstaller spec entry is `jarvis_desktop_launcher.py`, not `app_v4.py`.

Keep the existing Jarvis chat, voice controls (without enabling hardware), Control Center, tasks/approvals, memory, skills, Computer Use, market/scanner, robot catalog/intelligence, Strategy Tester evidence, campaigns, AuditLog, security and provenance. Move them into the unified navigation; do not drop functionality because a donor omitted it. Keep mutations behind JarvisService/SecurityManager/explicit authorization/AuditLog. Donor trading callbacks are `REJECT`, not candidates for copy/paste.

Related specifications: `JARVIS_UI_D1_UNIFIED_DESKTOP_ARCHITECTURE.md`, `JARVIS_UI_D1_DESIGN_SYSTEM.md`, `JARVIS_UI_D1_CAPABILITY_MAPPING.md`, and `JARVIS_UI_D1_MIGRATION_PLAN.md`.
