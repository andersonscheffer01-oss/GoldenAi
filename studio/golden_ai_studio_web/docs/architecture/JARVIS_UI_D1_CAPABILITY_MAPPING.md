# JARVIS UI-D1 — Capability Mapping

**Purpose:** map five visual donor views to existing canonical capabilities without feature loss or parallel authority. Donor numbers and controls are not evidence that a capability exists.

## Classification

- **REAL_CANONICAL_DATA:** a read model/owner exists in the repository; each runtime value still requires freshness/provenance.
- **REAL_BUT_NOT_CONNECTED:** useful source/code exists but no validated presentation binding is established here.
- **STATIC_DESIGN_EXAMPLE:** donor HTML/screenshot sample only.
- **FEATURE_NOT_IMPLEMENTED:** no canonical capability or contract is established.
- **ACTION_REQUIRES_APPROVAL:** future state-changing intent, only through canonical SecurityManager and explicit authorization.
- **REJECT:** unsafe/false semantics or duplicate authority.

## Donor-to-Capability Matrix

| Donor view/component | Visual purpose | Donor status | Canonical capability / owner | Read/service and security/audit contract | Target / decision |
|---|---|---|---|---|---|
| Painel — shared header/navigation/status | product identity and scanning | static shell; “online/demo/MT5 sync” labels are examples | Jarvis Desktop shell, runtime health, security and market-source state | `CoreLauncher`/existing status surfaces; no UI-auth authority. Show real timestamp/source. | Shared shell; `MERGE` and bind only to real status. |
| Painel — KPI strip and daily result | executive summary | `STATIC_DESIGN_EXAMPLE`; PnL/counts explicitly demo | Trade Journal and typed tester/campaign evidence; no single universal PnL | Existing read adapters only; separate LIVE/BACKTEST/SIMULATION classes; AuditLog is not trade history. | Painel/Performance; `ADAPT`; never seed demo values. |
| Painel — market thesis/evidence | market context | mock thesis/score/confidence | B4.2 MarketSnapshot/Market Intelligence, scanner, provenance/freshness | `JarvisService.golden_market_intelligence_snapshot` and `golden_scanner_snapshot`; HTTP `/api/jarvis/golden/market-intelligence`, `/radar`; authenticated read, source timestamp and audit context. | Análise GoldenAI; `ADAPT`. |
| Painel — position diagnostic | position empty/occupied state | screenshot copy is illustrative | Canonical MT5 read capability only when enabled and connected; `web-ai-safe` may intentionally disable it | Never infer “none” from unavailable; source/profile state must remain explicit. No live test in D1. | Operações; `ADAPT`, otherwise truthful `SOURCE_UNAVAILABLE`/`DISABLED_BY_PROFILE`. |
| Painel — operational plan and recent history | plan/history preview | `STATIC_DESIGN_EXAMPLE` | Scanner/read-only analysis; Trade Journal for recorded history | Read models with evidence class, timestamp and source ID. No execution from a signal. | Análise + Histórico; `ADAPT`. |
| Análise — symbol/timeframe thesis | market analysis | mock symbols/prices/thesis | `MarketSnapshot`, Golden bridge, market intelligence, temporal/macro context | `golden_market_intelligence_snapshot(symbol,timeframe)` / route; auth, freshness/provenance. `MarketSnapshot` stays canonical. | Análise GoldenAI; `KEEP` hierarchy, `ADAPT` model. |
| Análise — checklist/indicator evidence | explainability and criteria | static eight-rule checklist and values | Golden Scanner, validation, risk detail, macro evidence, provenance | `golden_scanner_snapshot`, `golden_validation_detail`, `golden_risk_detail`, historical macro/temporal evidence; read-only tool risk LOW; audit correlation. | Análise GoldenAI; `ADAPT` fields, do not claim unsupported criterion. |
| Análise — audio synthesis | spoken explanation | toast-only demo | canonical Jarvis VoiceService is a separate existing capability | Voice stays disabled in this scope; no hardware test or second “GoldenAI voice.” | Jarvis contextual surface later; `REFERENCE_ONLY`, defer. |
| Análise — entry/SL/TP and staged protection | operational analysis | `STATIC_DESIGN_EXAMPLE`; dangerously resembles order instruction | Risk and validation are informative, not execution permission | Existing risk/validation read projections; no direct MT5/broker call. Any future mutation requires separate explicit approval and audit. | Análise, read-only; `ADAPT` only if backed, otherwise `REJECT`. |
| Operações — open positions/orders/PnL | operational ledger | fabricated account, tickets, prices, live statuses | canonical MT5 read snapshot where available; Task/Audit models are not positions | Existing `golden_mt5_read_snapshot` and profile boundary when enabled; auth and provenance. No MT5 observation executed for this audit. | Operações; `ADAPT` only the layout, values remain absent until source validates. |
| Operações — close/partial/SL/BE/panic | mutate positions | demo toast handlers, no backend | no migrated route or approval contract authorized by this design | Must be JarvisService → SecurityManager → explicit target-bound approval → capability/provider → AuditLog; this donor has none of that. | `REJECT` handlers; future separately gated design only. |
| Operações — direct Buy/Sell/lot/copy signals | send orders/automation | demo callbacks, direct-MT5 framing | canonical trading path is outside UI-D1 and must not originate in view | No direct UI-to-MT5 or broker. LIVE authorization independent of MT5 connectivity and repertoire status. | `REJECT` all callbacks and order inputs. |
| Operações — bridge console | telemetry | hardcoded success/log lines and HMAC claim | Gateway health and canonical AuditLog/operation receipts where implemented | Do not treat pasted strings as provenance. Show event IDs from source, redact secrets. | Operações/Security; `ADAPT` layout, reject fake log. |
| Performance — aggregate KPIs/equity | compare outcomes | all numbers/static chart are examples | Trade Journal statistics; Strategy Tester native result bridge; Robot Intelligence/campaign evidence | Separate evidence kind, run/robot/artifact identity, period and sample sufficiency. `golden_statistics_snapshot` is historical statistics, not live performance. | Performance; `ADAPT` with explicit series/source partitions. |
| Performance — asset/session matrix | segment outcomes | hardcoded PnL/win rate/session counts | statistics engine/Trade Journal when fields exist | Never derive unsupported segment from total metrics. Label unavailable fields. | Performance; `ADAPT` where canonical fields exist, else `FEATURE_NOT_IMPLEMENTED`. |
| Performance — filter efficacy/parameter adjustment | evaluate/change strategy | unsupported demo score and toast | validation/audit and robot evidence; parameter change is a separate mutation | Evidence read is allowed; parameter mutation needs scope, approval, version/fingerprint, audit and scientific controls. | Read diagnostics may `ADAPT`; tuning button `ACTION_REQUIRES_APPROVAL` and defer. |
| Histórico — trade table and detail inspector | inspect operations | hardcoded tickets/results/thesis | Trade Journal; Robot/market provenance may cross-link by stable IDs | Preserve trading record ownership. Link, do not merge, `AuditLog`, tester runs, campaigns and macro contexts. | Histórico; `ADAPT` table/filter/inspector. |
| Histórico — copy ticket / CSV/PDF export | external action/artifact | simulated toast or clipboard-only behavior | safe export is not evidenced by donor | Copy-to-MT5 is `REJECT`; export must produce a real scoped artifact with audit and data classification. | `ACTION_REQUIRES_APPROVAL` only if later scope warrants; export otherwise `FEATURE_NOT_IMPLEMENTED`. |
| Shared “Lia” identity | AI persona/status | repeated product label in all donor HTML | one canonical Jarvis Core; GoldenAI is analytical capability/brand | No second voice/chat/model/security authority. | `REJECT` identity; map assistant→Jarvis, analysis→GoldenAI. |

## Canonical Destination Mapping

| Desktop view | Canonical owner and existing read paths | Important distinction |
|---|---|---|
| Painel | Existing Jarvis health/status and bounded canonical summary projections | Do not create a dashboard aggregation authority. Each tile keeps its own source/freshness. |
| Análise GoldenAI | `JarvisService` → `GoldenReadBridge`/Market Intelligence, scanner, risk, validation, `MarketSnapshot`, temporal and macro evidence | Snapshot IDs, source, timestamp and stale state are part of the display contract. |
| Operações | Existing read-only MT5 observation only when runtime permits; SecurityManager/AuditLog status for policy | Disconnected/disabled is not zero positions; no trade callbacks. |
| Performance | Trade Journal/statistics, native tester evidence, Robot Intelligence and campaign results | LIVE, BACKTEST and SIMULATION never aggregate silently. |
| Histórico | Trade Journal, tester/campaign history and AuditLog as separate query/source types | AuditLog records decisions/actions; it is not trade ledger. Cross-link by IDs only. |
| Robôs | `RobotCatalogReadModel`, `RobotIntelligence`, artifact identity and campaign/test evidence | DISCOVERED/CANDIDATE/ACTIVE/INACTIVE/BLOCKED/ARCHIVED, repertoire, artifact and trade authorization remain separate. |
| Backtests | `StrategyTesterAdapter`, deterministic materialization/preflight, `TesterResultBridge`, catalog/evidence | Historical result, plan, dry-run and executed authorized run are different lifecycle states. No one-click start. |
| Tarefas | Existing `TaskManager`, `BackgroundTaskScheduler`, `BackgroundControlCenter`, canonical `golden_tasks.db` | No new DB/scheduler; approval is not dispatch. |
| Memória | Existing Jarvis Memory Service/Memory V2 stores, retrieval and knowledge-RAG | No new memory engine; expose provenance/lifecycle and policy state. |
| Segurança | Existing `SecurityManager`, HTTP/Gateway auth and `AuditLog` | UI state is not authorization. Human approvals retain exact scope and one-use semantics. |

## Retained Capability Inventory

| Capability group | Decision | Destination |
|---|---|---|
| Jarvis chat, canonical service, model routing and provider fallback | `KEEP` | Jarvis persistent contextual surface and Jarvis view. |
| Existing Jarvis VoiceService/Voice UI | `KEEP` | Jarvis surface; hardware remains gated and no donor audio simulation is reused. |
| Control Center, system status, security/approvals, tasks/scheduler | `KEEP` / `MOVE` | Shared status bar and dedicated Segurança/Tarefas/Controle surfaces. |
| Golden Scanner, Radar, MarketSnapshot, macro/temporal evidence, deep analysis | `ADAPT` / `MERGE` | Análise GoldenAI; one canonical market read source. |
| Risk/validation | `KEEP` / `ADAPT` | Análise and evidence details, informational and provenance-linked. |
| Trade Journal, historical statistics | `KEEP` | Performance/Histórico, separate from tester and AuditLog. |
| Robot catalog/intelligence, artifacts and scientific campaigns | `KEEP` / `MOVE` | Robôs and Backtests. |
| Strategy Tester adapter/native evidence/reconciliation | `KEEP` / `ADAPT` | Backtests; preserve human authorization gate and provenance. |
| Memory, Skills/MCP, Computer Use | `KEEP` / `MOVE` | Memória, Jarvis and dedicated tool/control views. No capability disappears because donors omit it. |
| Donor charts/tables/navigation hierarchy | `KEEP` / `ADAPT` | Presentation patterns only; canonical data binding is mandatory. |
| Demo numbers, fake connected/latency/account states, toast-as-success | `REJECT` | Never represented as runtime state. |
| Direct MT5, order/position callbacks and autonomous copy-trading | `REJECT` | No donor code reuse; future scope requires a separate approved security design. |

## Required UI Read Contract

Every view result is enveloped by source identity, `observed_at`, freshness/status, correlation/request ID, data class and provenance links. `READY` is allowed only when the canonical source returns usable data. `EMPTY` means a successful query with no rows. `STALE`, `SOURCE_UNAVAILABLE`, `DISABLED_BY_PROFILE`, `AUTH_REQUIRED` and `ERROR` stay distinct. The UI does not fill missing fields with attractive sample data.
