# Jarvis Golden B1 Adapter Matrix

| Capability | Existing owner | B1 adapter/read model | Mutations described but disabled | Evidence |
|---|---|---|---|---|
| `golden.scanner` | Golden scanner + `market_readonly` | normalized scanner snapshot | scan, auto-trade | source fields preserved; score is not probability |
| `golden.radar` | `market_data.py` Radar Macro | overview projection | provider cache refresh | provider and freshness envelope |
| `golden.market_data` | `market_data.py` + `market_readonly.py` | AI context projection | symbol selection | observed context only |
| `golden.market_regime` | `meta_strategy.py` | regime and compatibility projection | portfolio change | calculated read envelope |
| `golden.meta_strategy` | `meta_strategy.py` | symbol/radar ranking projection | strategy activation | calculated source metadata |
| `golden.risk_engine` | `risk_engine.py` + existing read tool | risk status projection | risk configuration and orders | read-only risk report |
| `golden.validation` | `mt5_backtest.py` history | historical validation summary | validation and backtest runs | `HISTORICAL_EVIDENCE` |
| `golden.strategies` | `strategy_engine.py` + `strategy_audit.py` | catalog, audit and matching coverage | strategy mutation | existing robot-market coverage explicit |
| `golden.mql5` | `robot_catalog.py` + `mql5_evidence.py` | identity/artifact/evidence summary | compile, tester and repertoire mutation | artifact/provenance hashes retained |
| `golden.deep_analysis` | `market_data.py` + `meta_strategy.py` | analysis context projection | persistence and trade execution | input/source/timestamp envelope |

## Reuse decisions

All rows are `ADAPT` or `MERGE` at the read-model boundary: existing Golden
implementations remain the source of domain facts, while Jarvis owns the
canonical projection, security metadata and UI route. No parallel scanner,
risk engine, validation engine, voice stack or model router was created.

The MT5 read bridge reuses `market_readonly.py`; the tester evidence bridge
reuses the Robot Catalog and existing evidence contracts. B1 does not call
any mutation-capable operation.
