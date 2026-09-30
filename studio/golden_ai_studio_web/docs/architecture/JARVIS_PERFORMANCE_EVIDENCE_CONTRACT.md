# Jarvis Performance Evidence Contract

Performance is derived only from already available validation/history
observations. Each projection identifies its subject, evidence type counts,
sample count, period, available metrics, source and limitations.

Evidence classes remain distinct: `BACKTEST`, `SIMULATION`, `REPLAY`,
`FORWARD` and `LIVE` are never merged into one unlabeled statistic.
Metrics absent from the source are omitted, not estimated. Samples below the
minimum review threshold are marked with `SAMPLE_BELOW_30`.

The projection is informational and has no execution or robot-selection
authority.
