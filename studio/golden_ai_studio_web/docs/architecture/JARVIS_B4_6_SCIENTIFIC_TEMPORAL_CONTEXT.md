# Jarvis B4.6 Scientific and Temporal Market Context

## Scope

B4.6 adds a storage-neutral temporal contract to the existing Golden read
bridge.  It does not create a market engine, a second memory store, a new
matcher, or a new execution path.  The canonical flow remains:

`Golden observations -> JarvisService -> read models -> Control Center`

The three B4.5 production windows are registered by their existing run IDs and
remain linked to their evidence artifacts.  The selected MT5 data root does
contain native XAUUSD `.hcc` and `.tkc` history for 2026, including the target
months, but the committed Jarvis/Golden tree has no canonical parser that can
reproduce OHLC/ticks, spread, availability cutoffs, and hashes from those
binary files.  The committed evidence itself contains native tester metrics
and provenance only.  Therefore all market labels are explicitly `UNKNOWN`
and the contexts are marked
`BLOCKED_BY_MISSING_HISTORICAL_MARKET_ARTIFACT` rather than guessed.

## Temporal contract

`jarvis_core/temporal_market_context.py` defines immutable
`TemporalMarketSnapshot` projections with `observed_at`, `available_at`,
`ingested_at`, `valid_from`, `valid_to`, cutoff, timezone/DST model, source
artifacts, field-level label status, evidence quality, and a deterministic
context fingerprint.

Supported label families are `TREND_STATE`, `VOLATILITY_STATE`,
`STRUCTURE_STATE`, `SESSION_STATE`, `EVENT_RISK_STATE`, and optional USD,
liquidity, and correlation states.  Values are `OBSERVED`, `DERIVED`,
`INFERRED`, or `UNKNOWN`.  Missing historical observations are never turned
into zero, neutral, or a model guess.

The builder rejects observations with `available_at` after the cutoff and
rejects robot outcome fields such as balance, profit, OnTester, trades, wins,
losses, drawdown, or score.  Outcomes are attached only after context freeze,
under `POST_WINDOW_OUTCOME`.

## Reuse decisions

| Existing component | Decision | Reason |
|---|---|---|
| `market_read_models.py` / `MarketSnapshot` | ADAPT | Existing provenance and UNKNOWN semantics are preserved. |
| `golden_bridge.py` / `JarvisService` | KEEP | Existing canonical read boundary remains authoritative. |
| `robot_catalog.py` and B4.5 evidence | KEEP | Identity, hashes, and run evidence remain unchanged. |
| `robot_intelligence.py` | ADAPT | Frozen contexts and post-window outcome separation are projected here. |
| Memory V2 / `scientific_memory.py` | KEEP/ADAPT | Existing canonical memory boundary remains the future persistence owner; B4.6 does not create a second store. |
| Golden scanner, risk, and strategy engines | REFERENCE_ONLY | No historical labels are inferred from runtime strategy output. |
| Empirical matcher | REJECT for this gate | Evidence is insufficient and three windows cannot justify activation. |

## Historical evidence status

The execution evidence preserves R1, R2, and R3 identity, window, symbol,
timeframe, tester model where observed, artifact fingerprints, and native
metrics.  Native tester logs do not provide the required point-in-time market
series.  Native MT5 binary history is present outside the repository, but was
not parsed or mutated in this read-only gate.  Files under the legacy backtest
result area are heterogeneous and are not deterministically associated with
the three B4.5 run IDs, so they are not joined as context.

This is a scientific partial foundation, not a claim that market conditions
were reconstructed.  A future recovery must ingest an independently hashed
historical series, establish its timezone/DST and availability cutoffs, freeze
each window, and only then join the existing robot outcomes.

## UI and safety

The existing Control Center now shows the current temporal read-model state,
the three registered windows, context fingerprints, label values, and the
explicit missing-artifact status.  The surface remains read-only and visibly
separates analysis context from `POST_WINDOW_OUTCOME`; no live-trading
authority is added.

No MT5 process, Strategy Tester, MetaEditor, MQL5 compiler, provider, broker,
voice hardware, credential, or database write is required by this contract.
