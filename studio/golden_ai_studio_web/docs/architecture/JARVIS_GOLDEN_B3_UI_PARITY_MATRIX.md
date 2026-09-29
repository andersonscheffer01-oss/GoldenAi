# Jarvis / Golden B3 UI Parity Matrix

| Legacy feature | Legacy location | Canonical Jarvis surface | Status | B3 boundary |
| --- | --- | --- | --- | --- |
| Radar market map | `market.html` / Radar Macro | Market Intelligence panel | PARTIAL | read models only |
| Asset technical detail | Radar Macro | selected asset detail | PARTIAL | no frontend calculation |
| Scanner opportunities | Golden Scanner / Dashboard | Scanner table and drill-down | PARTIAL | score is not probability |
| Deep analysis context | Radar / analysis routes | opportunity detail context | PARTIAL | existing B2 adapter |
| Robot identity | catalog and MT5 evidence | Robot Catalog panel | PARTIAL | no discovery from UI |
| Backtest evidence | historical validation surfaces | Validation / Evidence panel | PARTIAL | unresolved records visible |
| Strategy Tester runs | controlled adapter evidence | Tester evidence rows | PARTIAL | no run action |
| Scientific memory | legacy memory and Memory V2 | Scientific Memory panel | PARTIAL | summary and relation vocabulary |
| Provenance | Golden/B2 envelopes | Source Integrity panel | PARTIAL | source and freshness visible |
| Auto-trade | legacy Dashboard | no canonical action | INTENTIONALLY_DEFERRED | frozen |
| Enter trade | legacy Radar | no canonical action | INTENTIONALLY_DEFERRED | frozen |
| Legacy voice | Studio/Radar | canonical voice stack | INTENTIONALLY_DEFERRED | unchanged |

## Status Meaning

`FULL` requires verified behavioral and visual equivalence. `PARTIAL` means a
useful canonical read surface exists without claiming complete legacy parity.
`MISSING` means no equivalent exists. `INTENTIONALLY_DEFERRED` means the
capability is deliberately outside the B3 authority boundary.

## Product Decisions

- Keep legacy Studio, Dashboard, Radar, and Scanner available for comparison.
- Do not copy critical Golden logic into JavaScript.
- Do not expose provider credentials, broker secrets, raw auth headers, or
  direct MT5 calls in the UI.
- Keep one Jarvis Core, one security model, one memory authority, and one
  Control Center implementation for Web and Desktop.
