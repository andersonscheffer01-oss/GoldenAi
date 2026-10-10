# Jarvis / Golden Control Center Recovery Plan

Planning-only document. It maps the eventual canonical Web/Desktop experience; it does not implement UI, migrate data or retire any donor surface.

## Target navigation

`JARVIS -> Trading / Market Intelligence` should eventually expose Market Overview, Radar Macro, Scanner, Technical, Macro/Fundamental, News, Economic Calendar, Sessions, Opportunity Analysis, Market History/Replay, Sources & Integrity and AI Analysis. The broader Control Center also needs Chat/Models/Profiles, Robots/MQL5/Strategy Tester/Backtests/Strategies/Validation, Memory/Tasks/Skills/MCP/Computer Use/Files/System, Voice and Security/Approvals/Audit/Provenance.

## UI contract

Every capability family must expose the following read model fields before parity is claimed:

| Contract field | Required meaning |
|---|---|
| `UI_READ_MODEL` | structured facts, source, timestamp, status and scope |
| `UI_ACTIONS` | explicit read-only or mutating actions; no hidden execution |
| `UI_SECURITY_STATE` | policy, session, approval and live-trading state |
| `UI_APPROVAL_REQUIREMENTS` | required approval scope and single-use semantics |
| `UI_PROGRESS_STATE` | pending/running/completed/timeout with run id |
| `UI_ERROR_STATE` | structured failure, stale, missing and inconclusive states |
| `UI_AUDIT_LINK` | canonical AuditLog receipt or explicit absence |
| `UI_PROVENANCE_VIEW` | source/provider/artifact/hash/reference time |
| `UI_EMPTY_STATE` | honest no-data explanation |
| `UI_DISABLED_STATE` | why an action is unavailable |
| `modes` | `analysis`, `backtest`, `simulation`, `live`, visibly distinct; live remains disabled until a separate gate |

## Recovery batches

| Batch | Scope | Owner/UI | Security and provenance | Tests/dependencies | Rollback/success |
|---|---|---|---|---|---|
| B0 | approve this map, contracts, status vocabulary and donor freeze | Jarvis Core / docs | no mutation; audit decision only | document review | delete no donor; approved contract |
| B1 | canonical source/provider/integrity read model | Core / Sources | secrets stay local; stale and unknown fail closed | provider mocks, timestamps | disable projection; source parity |
| B2 | market overview, MT5 candles/ticks, gold levels, technical data | Market Intelligence / Overview + Technical | read-only MT5 tools only | formula fixtures, alias/missing data | hide projection; factual parity |
| B3 | Radar scanner, currency strength, sessions and validation pipeline | Scanner/Core / Radar + Validation | score is not probability; unknown preserved | coverage, DST policy, fail-closed tests | freeze donor; pipeline parity |
| B4 | news, macro/fundamental, calendar and price drivers | Core / News + Macro + Calendar | provider key boundary, attribution, no fabricated events | parser/provider mocks, stale tests | disable provider; source parity |
| B5 | opportunity ranking, auditable performance, replay snapshots | AuditLog/Journal / Opportunities + Performance + Replay | immutable records, sample warnings, no action authority | association/outlier/replay tests | projection off; evidence parity |
| B6 | structured AI Radar analysis through Jarvis | JarvisService / AI Analysis | context in, explanation out; AI cannot execute | payload/schema/provider/fallback tests | keep legacy analysis; authority unchanged |
| B7 | MQL5/Robot/Tester evidence and retirement review | RobotCatalog/StrategyTesterAdapter / Robots + Tester | compile/run provenance; no production EA in fixture gate | artifact hashes, config reconciliation, full regression | no retirement until zero-loss gate |

Voice is a cross-cutting Control Center family, not a second product surface. It must show the canonical VoiceService state, device readiness, wake/VAD/STT/TTS status, session/turn identity, interruption state, approval requirements and AuditLog/provenance links. The Studio browser voice button remains a legacy donor under `LEGACY_FREEZE` until the canonical path has equivalent UX and the real microphone gate is resolved.

## Radar-to-robot boundary

Future matching may consume regime, trend, momentum, MTF alignment, spread, session, event risk, currency strength, levels, volatility, setup and macro factors through a structured `MarketContext`. It must remain `MT5 operational truth + Radar/Macro + History -> MarketContext -> Robot Catalog -> explainable recommendation`. `ACTIVE_IN_REPERTOIRE != AUTHORIZED_TO_TRADE`; this plan does not implement matching or live execution.

## Web/Desktop rule

`WEB_DESKTOP_SHARED_UI: YES`. The canonical `jarvis_ui` is already reused by Desktop through its WebView/CoreLauncher path. Recovery adds capability read models and panels to the existing canonical UI. It must not create a parallel Desktop UI, second Gateway, second Core, second provider authority, second task system or second audit model.

## Legacy retirement rule

`studio_v7.html`, `dashboard.html` and `market.html` remain high-value donors until every useful capability has a canonical equivalent with the UI contract, security state, provenance, error/unknown handling and regression evidence. A donor may be `SUPERSEDED_WITH_PARITY` only after an explicit review gate. Direct legacy write/order/compile paths stay `LEGACY_FREEZE` until their canonical authority and approval semantics are proven.

## Current next gate

`NEXT_RECOMMENDED_GATE: B0 REVIEW ONLY`. No implementation, provider setup, database migration, Strategy Tester run, production compile, live action or batch execution is included in this recovery plan.
