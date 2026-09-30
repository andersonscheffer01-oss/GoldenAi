# JARVIS / GOLDEN Final Lost Value Register

This register identifies useful Golden value that is not yet represented with equivalent Jarvis semantics. It is not an implementation authorization.

| ID | Lost or underrepresented value | Evidence | Why it is missing | Canonical equivalent today | Risk | Decision |
|---|---|---|---|---|---|---|
| LV-01 | Typed scientific evidence levels and source types | `core/memory/models.py`, `app/modules/memory_chat.py` | Jarvis memory has related fields but not the complete scientific contract | memory v2 / boundary | medium | ADAPT |
| LV-02 | Revision history, explicit conflicts, supersession | `core/memory/service.py`, repository tables | writer/authority convergence not proven across DB families | partial memory lifecycle | high | ADAPT |
| LV-03 | Experiment and artifact links | quant memory modules | no single canonical experiment identity/read model | evidence/catalog foundations | high | ADAPT |
| LV-04 | Claim-to-hypothesis relationships | scientific memory helpers | absent from canonical UI and retrieval contract | none full | medium | ADAPT |
| LV-05 | Multi-asset Radar panels | `market.html`, `market.js` | canonical Control Center exposes only limited market read models | market context | medium | PORT |
| LV-06 | News/source/freshness detail | Google RSS and source labels | no durable source registry and dedup contract | none full | medium | PORT |
| LV-07 | Macro/fundamental facts | FRED/BCB rules and Forex panel | provider boundary and stale behavior not canonical | none full | medium | PORT |
| LV-08 | Gold level formulas and explanations | `market_data.py` levels path | formula/evidence contract is not in Jarvis UI | none full | low | PORT |
| LV-09 | Currency strength and session context | market JS and operational center | coverage, DST, and holiday semantics incomplete | none full | medium | ADAPT |
| LV-10 | Deep multi-timeframe structure | `analysis_engines.py`, scanner context | only partial MarketContext/chat bridge | Jarvis chat | high | ADAPT |
| LV-11 | Meta-strategy explanation | `meta_strategy.py` | existing bridge is partial and not a full read model | partial strategy tools | high | ADAPT |
| LV-12 | Risk explanation/report | `risk_engine.py` | read/status bridge lacks complete evidence and UI | risk tools | high | MERGE |
| LV-13 | Validation evidence detail | `validation_engine.py` | real/synthetic provenance and UI states incomplete | validation tools | high | MERGE |
| LV-14 | Statistics/calibration | `statistics_engine.py` | journal/statistics are not one canonical performance model | audit/journal foundation | medium | PORT |
| LV-15 | Setup/trade journal history | JSONL and `trade_journal.py` | multiple runtime stores and authority are unresolved | AuditLog/journal read model | high | RECOVER_DATA |
| LV-16 | Robot-to-market association | scanner/setup and catalog fields | no stable empirical matcher contract | RobotCatalogReadModel | high | DESIGN_ONLY |
| LV-17 | Visible Strategy Tester evidence workflow | adapter and legacy views | adapter is backend foundation, Control Center UI is incomplete | tester/evidence foundation | high | PORT |
| LV-18 | Browser voice UX lessons | `studio_v7.html` and Radar voice paths | canonical VoiceService must own capture and turns | VoiceService | high | REFERENCE_ONLY |
| LV-19 | Auxiliary conversation metadata | `jarvis/backend/app` | different lifecycle and ownership | canonical conversations | medium | PORT_SELECTIVELY |
| LV-20 | UI feature breadth | dashboard/studio/market | canonical UI intentionally safer and narrower | Jarvis Control Center | medium | PORT_SELECTIVELY |

## Zero-loss blockers

The following must remain unresolved and explicitly visible before a donor surface can be retired: source identity/freshness, read-only versus mutable action states, provenance receipts, unknown-data handling, audit correlation, empty/disabled/error states, and regression coverage. Direct broker action, auto-trade, production strategy logic, and duplicated voice authority are not lost-value recovery targets.

## Scientific-memory recovery contract

The recommended path is to adapt Golden scientific semantics behind `CanonicalMemoryBoundary`: typed evidence, source identity, evidence level, confidence, revision identity, conflict state, supersession, experiment/artifact links, and claim/hypothesis links. SQLite/Jarvis memory remains truth; vault, Qdrant wrappers, and projections remain non-authoritative. No data import or schema change is part of this audit.
