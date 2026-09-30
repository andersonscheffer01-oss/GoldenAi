# Jarvis B4.2 Market Intelligence Recovery

Status: `IMPLEMENTED_READ_ONLY`

B4.2 consolidates the existing Golden Radar, market data, scanner, risk,
validation and historical performance observations behind the existing
`JarvisService -> GoldenReadBridge` boundary. Golden remains a donor; it is
not a second Jarvis authority.

The canonical product request is `/api/jarvis/golden/market-intelligence`.
It produces one correlated snapshot with `snapshot_id`, `correlation_id`,
source availability, freshness, provenance, technical structure, scanner,
risk, validation and performance sections.

No order, trade, MT5 initialization/login, Strategy Tester, MQL5 compile,
Voice, microphone, database migration or provider validation is part of this
batch. Missing data is represented as `UNKNOWN`, `UNAVAILABLE` or
`SOURCE_DISABLED`; no zero values are fabricated.

Display-only session state uses the IANA timezone database with deterministic
DST handling. Legacy scanner scoring is not rewritten and historical
evidence is not silently reinterpreted.

Robot-to-market matching remains intentionally unimplemented. The snapshot
only exposes precursor fields for a later empirical design gate.
