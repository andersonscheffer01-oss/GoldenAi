# Jarvis MT5, MQL5, and Robot Intelligence Donor Audit

**Audit date:** 2026-09-28
**Baseline:** `d2d10d0`
**Scope:** architecture and source audit only. No MT5 terminal, broker, credentials, EA, Strategy Tester, order, live-data request, or paid provider was started or called.

## Decision

**Result: PASS_WITH_RESTRICTIONS.** Golden has a useful read-only market path, a canonical security/audit boundary, MQL5 source assets, and repeatable local backtest artifacts. It does **not** yet have the canonical Robot Catalog, forward-test evidence model, regime matcher, or an approved execution capability. Those omissions correctly prevent any claim that a robot is active or fit for live trading.

## Evidence Model

Robot and strategy claims must use one of these levels, never an implied stronger one:

| Level | Meaning |
|---|---|
| `SOURCE_VERIFIED` | Source was read and its declared logic or safeguards were observed. |
| `DOCUMENTATION_VERIFIED` | A project document declares the behavior; source was not verified. |
| `CONFIG_VERIFIED` | A `.set` or equivalent configuration was observed. |
| `BACKTEST_EVIDENCE` | A persisted result artifact was observed; it is not a guarantee of reproducibility, robustness, or profitability. |
| `FORWARD_TEST_EVIDENCE` | Time-bounded forward-test evidence with provenance. Not present in this audit. |
| `LIVE_OBSERVATION` | Read-only observation of a live account/terminal with provenance. Not performed in this audit. |
| `INFERRED` | A cautious architectural inference. |
| `UNKNOWN` | No reliable evidence was available. |

## Golden Current State

### Canonical Jarvis boundary

`JarvisService` registers the MT5 market tools as `Risk.LOW` read-only tools: status, account, positions, pending orders, tick, symbol metadata, and recent candles. The `market_readonly` adapter has a static regression test prohibiting order execution calls. `JarvisService.execute_tool` remains the common path for tool lookup, security decision, confirmation, execution, verification, and `AuditLog` recording.

**Observed boundary:** `Jarvis -> ToolRegistry -> JarvisService.execute_tool -> SecurityManager -> AuditLog -> handler`.

### Existing MT5 surfaces

| Surface | Evidence | Assessment |
|---|---|---|
| `jarvis_core/tools/market_readonly.py` | `SOURCE_VERIFIED` | Canonical read-only adapter with structured offline behavior and bounded candles. Keep. |
| `jarvis_core/service.py` market registrations | `SOURCE_VERIFIED` | Read-only MT5 tools are registered at low risk; no `order_send` or `send_order` registry entry was observed. Keep. |
| `mt5_connector.py` | `SOURCE_VERIFIED` | Legacy centralized connector can initialize and auto-launch MT5, and exposes an order-send wrapper. It must not be routed through the new capability layer until an execution gate exists. |
| `mt5_trader.py` | `SOURCE_VERIFIED` | Legacy trading module contains market/pending order and position-close paths. No call was made. Treat as non-canonical legacy execution surface. |
| `mt5_backtest.py` | `SOURCE_VERIFIED` | Local Python backtest flow consumes MT5 historical data and writes JSON artifacts. Its results require provenance and reproducibility gates. |
| `mt5_real_backtest.py` | `SOURCE_VERIFIED` | Generates an EA and can open the Strategy Tester. It was not invoked; no automated Strategy Tester result validation was evidenced. |
| `core/computer/mt5_tools.py` | `SOURCE_VERIFIED` | Read-only installation and MQL file discovery is permission-gated. Reuse this discovery helper; do not duplicate it. |

### MQL5 inventory

The tracked repository contains production-looking MQL5 sources, plus test and attachment fixtures. Compiled `.ex5` files were observed locally but deliberately not treated as source evidence.

| Asset | Type | Evidence | Observed characteristics | Catalog state today |
|---|---|---|---|---|
| `projetos/EA_Canal_Pullback_MT5/EA_Canal_Pullback_MT5.mq5` | EA | `SOURCE_VERIFIED`, `CONFIG_VERIFIED` | Hourly/pullback channel, MA/ATR filters, SL/TP, breakeven, trailing, session, spread, daily-loss and OnTester robustness inputs. | `CANDIDATE` |
| `projetos/EA_Rompimento_Range_MTF_MT5/EA_Rompimento_Range_MTF_MT5.mq5` | EA | `SOURCE_VERIFIED`, `CONFIG_VERIFIED` | Multi-timeframe range breakout, risk-percent sizing, daily and position limits, spread and session controls. | `CANDIDATE` |
| `projetos/Robo_Tendencia_MA9_21_50_Volume.mq5` | EA | `SOURCE_VERIFIED` | MA 9/21/50, ATR, volume confirmation, break-even and MA/ATR trailing. | `CANDIDATE` |
| `projetos/Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5` | EA | `SOURCE_VERIFIED` | EMA/ATR/VWAP signal, partial exits, daily limits and schedule controls. | `CANDIDATE` |
| `projetos/Indicador_Estatistico_Range_MTF/Indicador_Estatistico_Range_MTF.mq5` | Indicator | `SOURCE_VERIFIED`, `CONFIG_VERIFIED` | Historical range/breakout statistics and simulated protective logic; no EA lifecycle. | `DISCOVERED` |
| `studio/golden_ai_studio_web/Golden_Midas_VWAP.mq5` | Indicator | `SOURCE_VERIFIED` | Anchored VWAP, bands, EMA and pullback chart signals. | `DISCOVERED` |
| `studio/golden_ai_studio_web/universal_backtest_ea.mq5` | Backtest template | `SOURCE_VERIFIED` | Template consumed by the Strategy Tester launcher. | `ARCHIVED` template |
| `projetos/robo_teste.mq5` | Script fixture | `SOURCE_VERIFIED` | Minimal test script; not an EA candidate. | `ARCHIVED` fixture |

Several `.mq5` paths under attachment and capability-audit fixtures are test data, not robot candidates. They must remain excluded from user-facing catalog discovery.

### Backtest and risk evidence

`config/backtest_results` contains 176 JSON artifacts across multiple strategy IDs, including `SWING_TURTLE_BREAKOUT_XAUUSD_M15`, `DAY_CA_C1_XAUUSD_M15`, generic MA/RSI/Bollinger/breakout strategies, and VWAP/price-action variants. A sampled Turtle breakout artifact identifies itself as a three-day, 320-candle, 17-trade local backtest with a negative total PnL. This is `BACKTEST_EVIDENCE` only. It is not evidence of a validated current recommendation, forward performance, or live profitability.

`risk_engine.py` contains reusable position sizing, daily loss, correlation-exposure, maximum-position, cooldown, news-window, and slippage concepts. Its hardcoded example/account values and static calendar definitions mean it is an `INFERRED` foundation, not a real-time risk-control authority.

## Donor Decision Matrix

| Donor | Audited pattern | Decision | Reason and integration boundary |
|---|---|---|---|
| [ek-labs/pp-mt5](https://github.com/ek-labs/pp-mt5) | Local SQLite mirror, replay/export, dry-run intent hash, per-command limits, kill switch, append-only audit, MCP annotations. | `ADAPT` | Reimplement the **patterns** behind Golden's existing `SecurityManager`/`AuditLog`; do not install or make its CLI/MCP a trading authority. Its write tools remain reference-only. |
| [TakamiyaZee/mt5-mcp-bridge](https://github.com/TakamiyaZee/mt5-mcp-bridge) | Read-only account/quotes/candles plus pre-trade validation, indicators, correlation, calendar blackout, portfolio snapshot, and regime concepts. | `ADAPT` | Port only pure, testable read-model schemas and calculations after data provenance is defined. Reject its trade tools, orchestration, Wine/RPyC bridge, and placeholder signal loop. |
| [amirkhonov/metatrader5-mcp](https://github.com/amirkhonov/metatrader5-mcp) | Broad MT5 MCP coverage, including initialization, login, market data, order checks, order send, history, and positions. | `REFERENCE_ONLY` | Useful compatibility inventory, but it accepts credentials and offers direct order execution. It cannot bypass the Jarvis service/security/audit boundary. |
| [ZhijuCen/mql5-skills](https://github.com/ZhijuCen/mql5-skills) | MQL5 reference material, SL/TP formula verification, Strategy Tester and optimization guidance. | `ADAPT` | Create one bounded Golden MQL5 development skill later; cite official MQL5 docs and keep broker specifications as versioned evidence, never universal constants. |
| [kecoma1/MQL5-SKILLS](https://github.com/kecoma1/MQL5-SKILLS) | Compile-log checking, EA conventions, candles/series rules, chart objects, confirmed backtest workflow. | `ADAPT` | Reuse its workflow shape for explicit compile and Strategy Tester result gates; do not automate a terminal in this phase. |
| [ThomasPraun/mql-developer](https://github.com/ThomasPraun/mql-developer) | Modular EA architecture, state machines, multi-symbol work, tester/Monte Carlo/walk-forward references. | `REFERENCE_ONLY` | Good design checklist, but small and broad. Use as a review source, not a runtime dependency or source of authority. |
| Twelve Data MCP | Quotes, time series, metadata and market events, with an API key and early-stage MCP server. | `DEFER` | Optional future read-only provider only; requires provider/provenance, quota, freshness, and secret-policy review. |
| Alpha Vantage MCP | Official MCP is available for historical and real-time market data. | `DEFER` | Optional future read-only provider; requires key/OAuth, rate-limit, freshness and evidence policy. |
| FRED MCP | Third-party MCP implementations over official FRED economic data APIs. | `DEFER` | Prefer direct official FRED API contract through a bounded provider adapter; no third-party MCP becomes canonical. |
| TradingView MCP / fin-data-mcp / Massive (Polygon) MCP | No specifically pinned, audited repository was supplied in this pass. | `DEFER` | Do not select an implementation until ownership, license, data terms, latency, provenance, and secret handling are audited. |
| Jin10 Market Analysis Skill | Multi-factor market-regime/report pattern, reliant on a third-party MCP/token and includes file/dashboard conventions. | `REFERENCE_ONLY` | The scoring/report schema is a useful inspiration; no token, provider, dashboard writer, or investment recommendation behavior is adopted. |

### Best donor patterns to keep

1. **Intent immutability:** preview a proposed write, hash its canonical intent, bind it to a short-lived confirmation, and invalidate stale intent before any future execution.
2. **Defense in depth:** user-controlled live enablement, explicit confirmation, configurable limits, a kill switch, and append-only sanitized audit evidence.
3. **Read-model-first intelligence:** account/positions/quotes/history/regime/correlation/calendar are independent evidence inputs; none creates a trade authority.
4. **Reproducible test gates:** capture source revision, parameter set, symbol specification, time range, data provenance, compiler log, tester report, and result hashes.
5. **MQL5 engineering discipline:** use explicit series indexing, grouped inputs, correct symbol properties, compile-log validation, and confirmed tester outputs.

## Target Architecture (Not Implemented)

### Canonical Robot Catalog

The future catalog belongs to Golden/Jarvis and contains a stable `robot_id`, name, source location and hash, artifact hashes, strategy family, symbols/timeframes, parameter-set identity, declared safeguards, evidence list, last evaluation, confidence, lifecycle state, and user-owned enablement.

Lifecycle: `DISCOVERED -> CANDIDATE -> ACTIVE | INACTIVE | BLOCKED -> ARCHIVED`.

Only the user can set or retain `ACTIVE`. Re-evaluation may recommend `BLOCKED` or `INACTIVE`, but must never overwrite a user decision without an explicit approval workflow and audit record. Source discovery must exclude fixtures, attachments, generated test EAs, and opaque `.ex5` binaries without matching source/provenance.

### Regime and temporal intelligence

Add a **Regime Matcher** only after the catalog: it compares an evidence-backed current market snapshot to historical backtest/forward contexts using volatility, trend/range, spread, session, correlation, calendar risk, and data freshness. It returns an explanation and confidence, not a trading command.

Temporal memory must retain dated thesis, source provenance, confidence, invalidation conditions, and outcomes. It must distinguish contemporaneous evidence from stale historical patterns and must not rewrite the user's catalog state.

### Execution boundary

Any future execution path is constrained to:

`JarvisService.execute_tool -> SecurityManager -> AuditLog -> approved execution adapter`

MCP servers remain capability providers only. They do not receive independent authority for orders, positions, credentials, task scheduling, memory, or audit. A future execution adapter needs a dedicated design and security gate; it is not a continuation of this audit.

## Safety Assessment

| Control | Status |
|---|---|
| Live trade, broker connection, terminal, EA, Strategy Tester, or order run during this audit | `NO` |
| Credentials, keys, `.env`, device registry, databases, or runtime state changed | `NO` |
| Canonical read-only MT5 tool boundary observed | `YES` |
| Direct legacy order path observed and identified as non-canonical | `YES` |
| Execution capability approved | `NO` |
| Robot catalog / forward-test / live-observation evidence present | `NO` |

## Recommended Roadmap

1. **Catalog and provenance gate:** implement the canonical Robot Catalog as a read model. Classify local source, configs, compiled artifacts, fixtures, and backtest files without discovering or starting terminals.
2. **Reproducible evaluation gate:** add source/config/data/tester provenance, result schema validation, selection of official MQL5 compile/tester evidence, and forward-test evidence records. No execution.
3. **Market context gate:** build read-only regime, calendar, correlation, and portfolio-risk snapshots behind provider contracts with freshness and source attribution. Providers are optional and never enable trading.
4. **Execution design gate:** only after the previous gates, design a new adapter with intent hashing, explicit user confirmation, stale-price/intent invalidation, limits, kill switch, audit retention, and a human-approved demo-only validation plan.

**Next implementation gate:** `ROBOT_CATALOG_AND_PROVENANCE_READ_MODEL`. It is a read-only design/implementation gate and must not launch MT5 or enable order execution.

## Sources Consulted

- [pp-mt5 README](https://github.com/ek-labs/pp-mt5)
- [mt5-mcp-bridge README](https://github.com/TakamiyaZee/mt5-mcp-bridge)
- [metatrader5-mcp README](https://github.com/amirkhonov/metatrader5-mcp)
- [mql5-skills README](https://github.com/ZhijuCen/mql5-skills)
- [MQL5-SKILLS README](https://github.com/kecoma1/MQL5-SKILLS)
- [mql-developer README](https://github.com/ThomasPraun/mql-developer)
- [Twelve Data MCP](https://github.com/twelvedata/mcp), [Alpha Vantage MCP](https://github.com/alphavantage/alpha_vantage_mcp), and [FRED API documentation](https://fred.stlouisfed.org/docs/api/fred/)
