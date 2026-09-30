# Tester Result Normalization

## Mapping

The native provider maps only fields observed in the artifact:

| Native field | Normalized field | Unit |
| --- | --- | --- |
| `initial deposit` | `initial_deposit` | account currency |
| `final balance` | `final_balance` | account currency |
| `OnTester result` | `on_tester` | native scalar |
| `N ticks` | `ticks` | count |
| `N bars generated` | `bars` | count |
| `quality of analyzed history is N%` | `history_quality` | percent |
| native model description | `tester_model` | enum/string |

The v2 native parser also preserves the EA-defined `ROBUSTO` line as custom
metrics: `custom_on_tester_score`, `custom_complete_positions`,
`custom_wins`, `custom_losses`, `custom_net_result`, `custom_profit_factor`,
`custom_drawdown_percent`, `custom_expectancy`,
`custom_concentration_percent`, and `custom_approved`. These are not mapped
to generic `total_trades` or generic performance fields.

Every mapped field retains its raw field name, raw value, normalized value,
unit, artifact path, provider, confidence, and status. Numeric conversion is
limited to the syntax observed in the bounded log.

## Unknown and partial evidence

Missing fields are not synthesized. An unsupported localization or model
description yields `tester_model=UNKNOWN` and a limitation. The v2 parser
accepts the observed native phrase `generating based on real ticks` in
addition to the earlier real-ticks wording. Metrics not
exposed by the journal, such as total trades or detailed drawdown, remain
absent and are listed in `limitations`.

## Identity and reconciliation

Identity comes from the pre-existing plan/config contract, while symbol,
timeframe, period, and expert path are checked against the native block. The
raw artifact SHA-256 and normalized payload fingerprint are both retained.
Provider comparison is deliberately non-authoritative and returns
`MATCH`, `PARTIAL_MATCH`, `CONFLICT`, or `NOT_COMPARABLE`.
