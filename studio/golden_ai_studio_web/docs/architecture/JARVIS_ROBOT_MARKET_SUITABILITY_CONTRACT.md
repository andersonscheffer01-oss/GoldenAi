# Robot Market Suitability Contract

Suitability consumes a B4.2 market snapshot and a canonical robot profile.
It compares observed symbol, timeframe, regime, volatility, spread and
session fields against declared or evidence-derived robot metadata.

Results expose `SUPPORTED`, `PARTIAL`, `CONTRADICTED`, or `UNKNOWN`, with
matches, contradictions, unknowns, evidence strength, explanation, and
market snapshot provenance. The result is analysis only.

`EMPIRICAL_MATCHING=NOT_IMPLEMENTED`, `OPAQUE_AI_SCORE=FALSE`, and
`FAKE_PROBABILITY=FALSE` are permanent B4.3 guardrails. A suitability result
cannot change repertoire state, MT5 state, AutoTrading, positions, or trading
authorization.
