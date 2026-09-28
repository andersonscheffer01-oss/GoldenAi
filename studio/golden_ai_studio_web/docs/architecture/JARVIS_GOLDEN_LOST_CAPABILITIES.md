# JARVIS / GOLDEN Lost and Unrecovered Capabilities

This is a recovery register, not an implementation plan. Items are static findings and remain unapproved until a later scoped gate.

| ID | Capability | Evidence location | Current Jarvis state | Value | Decision |
|---|---|---|---|---|---|
| LC-01 | Typed scientific evidence | `core/memory`, `app/modules/memory_chat` | no equivalent full contract | High | ADAPT |
| LC-02 | Memory revisions/conflicts | scientific memory repository | basic lifecycle differs | High | ADAPT |
| LC-03 | Experiment and artifact links | scientific memory/quant modules | not fully represented | High | ADAPT |
| LC-04 | Claim-to-hypothesis memory | media and memory modules | absent from canonical surface | Medium | ADAPT |
| LC-05 | Radar multi-asset read detail | `market.html`, `market_data.py` | B1 overview only | High | PORT as read model |
| LC-06 | Deep structure/MTF analysis | `analysis_engines.py`, `market/` | not fully exposed | High | ADAPT |
| LC-07 | Meta strategy explanation | `meta_strategy.py` | partial bridge | High | ADAPT |
| LC-08 | Risk explanation/report | `risk_engine.py` | partial bridge | High | ADAPT |
| LC-09 | Validation evidence detail | `validation_engine.py` | partial and synthetic paths | High | ADAPT with labels |
| LC-10 | Statistics/calibration | `statistics_engine.py` | not fully exposed | Medium | PORT |
| LC-11 | Trade journal/setup history | `trade_journal.py`, JSONL | data exists, authority requires reconciliation | High | RECOVER DATA |
| LC-12 | Market AI audit history | `data/market_ai_audit.jsonl` | legacy data asset | Medium | RECOVER DATA |
| LC-13 | Canonical control-center read panels | Jarvis UI vs Studio/Dashboard | limited B1 card | Medium | PORT |
| LC-14 | Full Radar UI parity | `market.html` and scripts | absent from Jarvis | Medium | PORT selectively |
| LC-15 | Proven voice hardware lessons | Studio/Radar browser paths | canonical hardware proof open | Medium | REFERENCE_ONLY |
| LC-16 | Auxiliary conversation history | `jarvis/backend/app` | not canonical | Medium | PORT selectively |
| LC-17 | Agent/plugin descriptors | `agents/`, `plugins/` | canonical equivalents differ | Medium | ADAPT metadata |
| LC-18 | Legacy browser/media helpers | `app/modules/browser.py` | governed replacements exist | Low | REFERENCE_ONLY |
| LC-19 | Direct scanner/trade execution | Golden legacy paths | intentionally not canonical | High risk | LEGACY_FREEZE |
| LC-20 | Production MQL5 strategy behavior | `projetos/` and robot paths | protected repertoire | out of scope | LEGACY_FREEZE |

## Priority

High value recovery is limited to read-only, explainable, provenance-bearing data and analysis. Medium value recovery covers UI and metadata parity. Low value items are reference material unless a concrete user need and authority decision exists. Direct orders, broker mutation, live trading, production strategy logic, and duplicated voice brains are not recovery targets.

## Gate for every item

Before implementation, define canonical owner, input/output schema, source identity, freshness/staleness behavior, security policy, AuditLog event, failure behavior, and a test that proves no legacy execution path was activated.
