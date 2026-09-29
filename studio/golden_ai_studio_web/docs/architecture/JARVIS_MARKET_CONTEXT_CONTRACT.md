# Jarvis MarketContext Contract

`MarketContext` is a bounded, read-only snapshot assembled from existing
Golden read models. It is not long-term memory and is not a trading
authorization.

## Shape

The current snapshot may contain:

```text
surface
selected_asset
symbol
timeframe
context_timestamp
market_regime
technical_state
price_state
volatility
spread
currency_strength
scanner_state
selected_opportunity
macro_context
economic_events
relevant_news
freshness
provenance
source_timestamps
availability
```

Only values available from the Golden bridge/read models are copied. Missing
values use an explicit `UNKNOWN`/`UNAVAILABLE` state rather than fabricated
market data. The envelope preserves source provenance and observed timestamps
when the source supplies them.

## Lifecycle

For each Market AI request, `JarvisService.market_context_snapshot()` reads
the requested symbol/timeframe and scanner view, then the same snapshot is
passed to `JarvisBrain.generate_response()`. The brain serializes it as a
bounded system context marked as observed data, separate from the user
message, memory context and system policy.

## Degradation

Partial or unavailable Golden data remains explicit in the context and is
reported in the response metadata. A response never treats missing context as
live data. MarketContext does not write a new database or automatically create
scientific/long-term memory.

## `web-ai-safe` source semantics

When `RuntimeProfile.mt5_enabled` is false, MarketContext still preserves the
requested `surface`, `symbol`, `selected_asset`, `timeframe`, timestamp and
read-model envelope. MT5-dependent chart, price, spread and scanner fields are
`UNAVAILABLE` or `SOURCE_DISABLED`, with provenance/freshness left explicit.
The bridge passes the capability into the legacy market helpers, and the MT5
connector fails closed before initialization or auto-launch. No cached value is
relabeled as `LIVE` or `FRESH` merely because an AI request was made.
