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

Every mapped field retains its raw field name, raw value, normalized value,
unit, artifact path, provider, confidence, and status. Numeric conversion is
limited to the syntax observed in the bounded log.

## Unknown and partial evidence

Missing fields are not synthesized. An unsupported localization or model
description yields `tester_model=UNKNOWN` and a limitation. Metrics not
exposed by the journal, such as total trades or detailed drawdown, remain
absent and are listed in `limitations`.

## Identity and reconciliation

Identity comes from the pre-existing plan/config contract, while symbol,
timeframe, period, and expert path are checked against the native block. The
raw artifact SHA-256 and normalized payload fingerprint are both retained.
Provider comparison is deliberately non-authoritative and returns
`MATCH`, `PARTIAL_MATCH`, `CONFLICT`, or `NOT_COMPARABLE`.
