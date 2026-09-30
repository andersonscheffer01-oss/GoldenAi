# Robot Evidence Dataset Contract

Rows link a robot identity to an evidence artifact or run, evidence type,
symbol, timeframe, period, metrics, market labels, association status,
fingerprint, provenance, and limitations.

Supported evidence types are `BACKTEST`, `SIMULATION`, `REPLAY`, `FORWARD`,
`LIVE`, and `UNKNOWN`. Evidence is never silently mixed. Duplicate artifact
hashes, run IDs, or content fingerprints are excluded from the descriptive
sample count.

Market labels are `OBSERVED`, `DERIVED`, `INFERRED`, or `UNKNOWN`. Missing
labels stay unknown. The dataset records temporal-split readiness and
leakage controls but does not train a model or infer performance statistics.

The dataset is suitable for descriptive analysis only while associations or
market labels remain incomplete. Empirical matching requires labeled,
time-consistent, independently verified samples.
