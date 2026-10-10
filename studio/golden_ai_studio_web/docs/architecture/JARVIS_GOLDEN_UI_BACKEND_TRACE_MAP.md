# JARVIS / GOLDEN — UI / Backend Trace Map

## Main surfaces

| UI | Main backend path | Static role |
|---|---|---|
| `studio_v7.html` | `/api/chat`, file/PC/provider routes, legacy voice | broad Golden workbench |
| `dashboard.html` | `/api/scanner/radar`, `/api/mt5/full_analysis`, `/api/mt5/auto_trade`, validation/journal routes | operational dashboard with broker controls |
| `market.html` + scripts | market data, chart, macro/news and radar endpoints | Golden market/radar donor |
| `jarvis_ui/jarvis.html` + `jarvis_ui/src` | Gateway/command router and canonical service | Jarvis UI target |
| Jarvis Desktop | WebView/API client and `/api/jarvis/voice-service/*` | desktop projection of canonical UI/core |

## Scanner and trade call graph

```text
dashboard.html scannerRadar()
  -> POST /api/scanner/radar
  -> server_agent._api_scanner_radar
  -> mt5_connector.ensure_connection()
  -> GoldenScanner.scan_all()
  -> scan_symbol(symbol)
  -> market data + indicators + regime + setup definitions
  -> rank/readiness/score/alert
  -> StatisticsEngine + strategy_audit
  -> radar JSON + integrated robot catalog
  -> window._radarData / openAssetDetail()
  -> ENTRAR NO TRADE
  -> executeTradeFromModal()
  -> POST /api/mt5/auto_trade {auto_execute:true}
  -> _authorize_api_mutation(... mt5_real_order ...)
  -> mt5_trader.auto_trade_from_analysis()
  -> execute_trade()
  -> risk_engine.can_trade()
  -> mt5.order_send(request)
  -> broker result / UI message / trade_journal.log_analysis()
```

The graph is static evidence of reachability, not evidence that an order was sent during this audit. The dashboard modal calculates `entry` from displayed price and SL/TP from H1 ATR. The backend and trader can construct market or pending orders, include magic/comment/filling/deviation fields where applicable, normalize prices and call the broker API.

## Deep Analysis graph

```text
openAssetDetail()
  -> Análise Profunda (Multi-Layer)
  -> runDeepAnalysis()
  -> POST /api/mt5/full_analysis
  -> ensure_connection()
  -> FullAnalyzer.analyze()
  -> MasterAnalyzer.full_analysis()
  -> structured prompt
  -> optional ClineProvider / OpenRouter provider
  -> trade journal/setup persistence
  -> UI renders regime, direction, score, ranked setups, AI text
  -> optional ENTRAR NO TRADE button
```

The deterministic layers and external AI response are not equivalent evidence. The report must preserve which layer produced each field, the model/provider when present, and whether a result is synthetic, historical, read-only or broker-backed.

## AUTO-TRADE graph

`toggleAutoTrade()` changes an in-page boolean and starts a 30-second timer. The timer calls the radar, filters score >= 75, readiness >= 70, opportunity level, non-neutral direction, `VALIDADA` validation and `audit.auto_trade_eligible`, then POSTs `/api/mt5/auto_trade` with `auto_execute:true`. There is no durable Core policy object, canonical approval record or cross-client state in this path. It is therefore a legacy UI execution controller, not a Jarvis control-plane capability.

## Existing Golden Scanner trade path

The Scanner route returns rich fields: price, spread, regime, ATR, daily range, H4/H1/M15/M5 trends, RSI, volatility, session, pips, setup lists, score, alert, conditions, R:R, confluence, expectancy, validation and audit eligibility. The UI exposes both a direct order action and a deep-analysis action. The target UI should consume an immutable Jarvis read model and render a proposal state; it must not inherit the direct fetch to a broker mutation route.

## UI authority result

`jarvis_ui`/Desktop should become the single control-center presentation. Golden pages remain available as legacy surfaces until parity, route containment, provenance and security gates are proven. No UI migration is implied by this static map.
