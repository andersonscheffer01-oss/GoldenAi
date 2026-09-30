# Jarvis Risk and Validation Contract

Risk and validation are read projections only. Jarvis SecurityManager remains
the sole authority for any future action; this contract cannot authorize a
trade, order, position change or configuration mutation.

Risk preserves the donor report and exposes component slots for market, setup,
portfolio, event and execution risk. Missing component evidence stays
`UNKNOWN`.

Validation preserves historical evidence and its evidence class. Stages may
be `PASS`, `FAIL`, `UNKNOWN`, `NOT_APPLICABLE`, `SOURCE_DISABLED` or
`INSUFFICIENT_DATA`. `UNKNOWN` is not rewritten as `FAIL`.
