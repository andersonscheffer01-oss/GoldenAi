# JARVIS / GOLDEN — MT5 and Trading Reconciliation

**Scope:** static code and artifact inspection only. No MT5 connection, terminal launch, tester, order, account or broker mutation occurred.

## Ownership map

| Concern | Golden evidence | Jarvis status | Decision |
|---|---|---|---|
| Market reads | `mt5_connector.py`, scanner, market modules | `tools/market_readonly.py` | Jarvis read-only boundary |
| Regime/setup intelligence | `golden_scanner.py`, `meta_strategy.py` | no equivalent full engine | adapt behind read model |
| Risk calculation | `risk_engine.py` | SecurityManager is not a replacement risk engine | preserve as calculation input; policy remains Core |
| Validation/backtest | validation engine, journal, JSON reports | evidence/catalog contracts | merge provenance, preserve history |
| Robot identity | MQL5 files, strategy catalog | `RobotCatalog` | Jarvis catalog authority |
| Compile/test provenance | legacy paths plus adapter | `mql5_evidence.py`, `StrategyTesterAdapter` | Jarvis evidence authority |
| Live order | dashboard/server/trader/connector | no canonical live-order tool | `LEGACY_FREEZE` |

## Existing Golden Scanner trade path

`dashboard.html` loads `/api/scanner/radar`; `_api_scanner_radar` calls `ensure_connection()`, `GoldenScanner.scan_all()`, `StatisticsEngine`, and `strategy_audit`. The resulting fields include setup IDs, mode/tier, readiness, direction, conditions, R:R, confluence, expectancy, validation status and `auto_trade_eligible`.

The modal button `ENTRAR NO TRADE` calls `executeTradeFromModal()`. It derives entry from the displayed scan price and uses H1 ATR to create SL/TP, then calls `/api/mt5/auto_trade` with `auto_execute:true`. The backend gates the mutation with `_authorize_api_mutation` and delegates to `mt5_trader.auto_trade_from_analysis`. `execute_trade` obtains a live tick, calculates lots from account balance/risk/point values when needed, invokes `risk_engine.can_trade`, builds market or pending request data, and calls `mt5.order_send`. It records an open event after success and returns order/deal/result data.

The scanner itself does not prove a broker trade. A matching journal row with `trade_opened:false`, ticket `0` and `PENDING` is intent/history evidence, not proof of execution. The static path can be real-capable even when a particular artifact is not proof of execution.

`AUTO-TRADE` is a browser timer, defaults off in the inspected code, and is not a durable Jarvis policy. When enabled, it scans every 30 seconds and requires score >= 75, readiness >= 70, `OPORTUNIDADE`, non-neutral direction, `VALIDADA` validation and `auto_trade_eligible`. It then calls the same real mutation endpoint. Duplicate protection is not established at the UI timer level; risk and broker state checks are downstream concerns.

## Deep Analysis

`/api/mt5/full_analysis` calls `ensure_connection`, `FullAnalyzer`, `MasterAnalyzer`, structured prompt construction, optional Cline/OpenRouter provider calls, and journal/setup persistence. It produces regime/ranked setup/AI fields and can feed the same order button. Deterministic calculations, external model output, journal write and broker execution are separate evidence classes and must not be collapsed into one “validated” label.

## Risk and order controls found statically

`risk_engine.can_trade` checks daily loss, consecutive losses, cooldown, maximum open positions, correlation exposure and news proximity. `execute_trade` calculates volume from balance, risk percentage, stop distance, tick value/size, point and broker volume bounds; it normalizes price/SL/TP and uses market or pending order types, magic/comment, GTC and IOC fields. Exact broker/account mode, margin behavior, symbol visibility, spread policy at execution and actual retcodes require runtime validation and were not tested.

`mt5_connector.ensure_connection()` can attempt to initialize/launch MT5 and `send_order`/trader paths reach `order_send`; `safe_shutdown` intentionally keeps MT5 alive. This is incompatible with an implicit Jarvis read model and is therefore frozen behind an explicit future execution gate.

## Reconciliation verdict

The Golden Scanner and risk calculations are valuable domain implementations. The dashboard-to-broker path is a legacy side-effect authority. Future integration must expose scan/proposal evidence through Jarvis, preserve the existing robot/catalog/evidence identities, and require a separate user-approved live execution design. No production robot, strategy, broker, account, historical backtest or device registry was modified.
