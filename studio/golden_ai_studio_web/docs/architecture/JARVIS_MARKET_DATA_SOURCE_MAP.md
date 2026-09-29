# Jarvis Market Data Source Map

## Source matrix

| Source | Purpose | Authority | Refresh/cache | Failure behavior | Provenance state |
|---|---|---|---|---|---|
| MetaTrader 5 | Broker quotes, ticks, candles, levels, technical context | Broker-specific truth for traded symbols | Tick 500 ms; chart 15 s; overview request | `MT5 desconectado`/empty component | Source and `updated_at` present; no snapshot id |
| CoinGecko | Bitcoin/Ethereum public market cards | Public crypto fallback/source | Request cache is not persisted in `market_data.py` | Empty crypto rows and source offline | Source/status present |
| FRED | US rates, inflation expectation, broad USD | Official macro series | Macro cache 900 s | Series omitted; error collected | Series id/source/date present |
| Banco Central do Brasil | Selic and IPCA series | Official Brazilian macro series | Macro cache 900 s | Series omitted; error collected | Series id/source/date present |
| Google News RSS | Gold/macro and pair news | Aggregated news feed | General 60 s; pair 120 s | Empty list/source may remain blank | Title/link/source/published_at when parseable |
| Trading Economics | Economic calendar | Configured external provider | Calendar 60 s | `configure` or error state | Event source/time/fields if returned |
| Twelve Data | Declared multi-asset coverage | Configuration indicator only | No data path found in audited code | `ready` can be shown without fetched Twelve Data | Configuration state only; do not treat as data |
| Golden Scanner | Setups, readiness, confluence and validation fields | Existing Golden strategy code | Endpoint-driven scan | Empty/unavailable response | No unified Market snapshot id |

## Transformations

- Chart levels use the previous closed daily candle for classic gold pivots and a separate pivot-clustering algorithm for technical levels.
- Chart ATR uses true ranges over the recent analysis window; RSI uses the last 14 gains/losses; structure labels are swing-break `BOS` or `CHoCH`.
- Currency strength averages daily percentage changes per base/quote currency and normalizes by the maximum absolute observed value to a 0-100 relative scale.
- Macro reading counts favorable/contrary drivers and returns `Favoravel ao ouro`, `Contrario ao ouro` or `Misto`; it is a context score, not probability.
- Opportunity ranking computes `readiness * 0.65 + aligned_timeframes * 7.5 - spread_penalty`, bounded to 0-100.

## Freshness and consistency

The UI displays general `updated_at`, source labels and coarse source status. It does not expose a field-level `LIVE`, `FRESH`, `STALE`, `CACHED`, `UNKNOWN` or `UNAVAILABLE` contract. Overview, chart, scanner and AI context are separate requests and can observe different ticks/candles. No correlation id or shared snapshot timestamp is sent across them.

The AI context rebuilds charts for M5/M15/H1/H4/D1 and records one response timestamp, but each timeframe can have a different source retrieval instant. The Market Chat does not receive the AI context at all.

## Refresh/performance

The chart uses a 500 ms tick loop and a 15 s candle loop while the tab is visible. The overview uses a 60 s countdown/manual refresh. Guards prevent overlapping chart/tick calls per component. There is no AbortController, request generation check, or cross-component deduplication. News/macro/calendar caches reduce provider load, but chart and overview calls remain independent.

## Static audit limits

No live sample was taken in this gate because the backend was not started and MT5 was not touched. Runtime freshness, provider availability and cross-panel value equality therefore remain unverified. The map is based on source contracts and explicit error paths.
