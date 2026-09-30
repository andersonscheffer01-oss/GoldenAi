# B4.5A Native MT5 Tester Result Bridge

## Scope

B4.5A adds a read-only result bridge for production Strategy Tester evidence.
It does not launch MetaTrader 5, compile MQL5, mutate the Robot Catalog, or
change a production EA. The implementation is in
`jarvis_core/tester_result_bridge.py`.

## Evidence decision

The bounded forensic review found native MetaTester journal logs but no
trustworthy HTML, HTM, XML, or provider-neutral structured report artifact.
The observed native surface is:

`<selected data root>\\Tester\\logs\\YYYYMMDD.log`

The selected strategy is `TESTER_LOG_BRIDGE`. The bridge verifies the exact
testing block, terminal build, symbol, timeframe, date interval, bounded
artifact path, and run window before normalizing metrics. It preserves the
raw artifact hash and derives a separate normalized-artifact fingerprint.

`NATIVE_REPORT_BRIDGE` is not selected because no report artifact was found.
`NATIVE_STRUCTURED_RESULT_BRIDGE` is not proven. `EA_INSTRUMENTATION_REQUIRED`
is `NO` for B4.5A: the existing production EA already emits native tester
journal evidence and remains unchanged.

## Providers

`NativeTesterLogProvider` reads only bounded terminal tester logs.
`FixtureJsonResultProvider` preserves the proven B4.4 fixture JSON contract.
Both produce `NormalizedTesterResult` and `ProviderOutcome`; no provider has
execution authority.

## Native log coverage

Observed and normalized fields include initial deposit, final balance, custom
`OnTester` result, ticks, bars, history quality when present, tester model,
terminal build, identity, and artifact provenance. Missing values remain
missing. Total trades, detailed drawdown, commission, spread, and other fields
not exposed by the native journal are recorded as limitations rather than
inferred.

## Safety boundary

The bridge rejects path traversal, oversized artifacts, stale artifacts,
wrong identity, wrong period, wrong symbol/timeframe, and ambiguous matching
blocks. Unsupported or unknown model descriptions remain explicitly unknown
with a limitation. It is read-only and emits the documented audit event names
for selection, discovery, rejection, verification, normalization,
reconciliation, and conflict handling.

## Gate result

The existing campaign remains unchanged. B4.5A dry-run coverage binds all
three existing production plans to the provider contract without executing
them. The previous B4.5 approval becomes `STALE_BY_CONTRACT_CHANGE`; a fresh
approval is required before any future controlled campaign run.
