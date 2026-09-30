# MT5 Native Result Forensics

## Inspection boundary

The inspection was read-only and bounded to the selected MT5 data root and
the existing B4.4 fixture evidence. No MT5 process, MetaTester process, or
MetaEditor process was started.

## Findings

No native HTML, HTM, or XML report was present in the bounded terminal,
tester, agent, or campaign output locations. Native journal logs were found
under:

`<selected data root>\\Tester\\logs\\YYYYMMDD.log`

The existing agent log path is also observable under the MetaQuotes tester
agent tree, but the B4.5A provider uses the terminal tester log as its
deterministic bounded source. The log contains MetaTester build information,
tester model, exact expert path, symbol/timeframe, period, initialization
facts, initial deposit, final balance, `OnTester` result, tick count, bar
count, and completion status.

## Observed fixture evidence

The pre-existing fixture run `run_895af6447cb04b789f045274f019854f` produced a
native log that reconciled to OHLC, final balance `100000.00 USD`,
`OnTester=5677`, `5677` ticks, and `1432` bars. Its observed raw log hash was
`23a4871703afeabb18bc8a7c5f444292dc51561b709951dd2f8fed4d44a1553e` at
inspection time. This is evidence from an existing fixture run, not a new
execution.

## Classification

`TESTER_LOG_BRIDGE`: selected and implemented read-only.
`NATIVE_REPORT_BRIDGE`: unsupported by observed artifacts.
`NATIVE_STRUCTURED_RESULT_BRIDGE`: not proven.
`EA_INSTRUMENTATION_REQUIRED`: no for this gate.

Native journals expose a subset of tester metrics and may vary by build,
locale, and log formatting. Unknown fields remain unknown and are reported as
limitations.
