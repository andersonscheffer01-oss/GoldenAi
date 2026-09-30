# Jarvis Market Read Model Contract

The B4.2 read model is owned by Jarvis and calculated from bounded Golden
donor observations. It is read-only and carries:

- `snapshot_id`, `captured_at`, `correlation_id`, symbol and timeframe;
- market map, price/technical state, regime, levels and structure events;
- normalized news, macro indicators, economic events and sessions;
- scanner result semantics, risk state, validation trace and performance
  evidence labels;
- per-source status, freshness, observed/received timestamps and fingerprint;
- transformation and provenance metadata.

`UNKNOWN` means the source did not establish a value. `UNAVAILABLE` means the
source failed or has no usable result. `SOURCE_DISABLED` means the runtime
profile deliberately withheld the source, such as MT5 under `web-ai-safe`.
Neither is converted into a successful or zero-valued observation.

`SCORE_NOT_PROBABILITY` and `ENTRY_READY_DOES_NOT_AUTHORIZE_TRADE` are
explicit scanner semantics. Performance summaries never infer metrics from a
sample that does not contain those metrics and expose sample limitations.
