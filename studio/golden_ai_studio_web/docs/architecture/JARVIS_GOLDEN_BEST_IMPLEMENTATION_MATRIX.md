# JARVIS / GOLDEN — Best Implementation Matrix

| Domain | Best existing implementation | Why | Target owner | Classification |
|---|---|---|---|---|
| Core orchestration | `jarvis_core/service.py` | central execution boundary and tool lifecycle | Jarvis Core | `KEEP_OURS` |
| Tool registry | `jarvis_core/registry.py` | rejects duplicate definitions and carries risk metadata | Jarvis Core | `KEEP_OURS` |
| Security | `jarvis_core/security.py` | fail-closed approval and scoped confirmation | Jarvis Core | `KEEP_OURS` |
| Audit | `jarvis_core/audit.py` | redaction and canonical receipt path | Jarvis Core | `KEEP_OURS` |
| Model routing | `jarvis_core/orchestrator/model_router.py` | provider policy and local-only constraints | Jarvis Core | `KEEP_OURS` |
| Tasks | `jarvis_core/task_manager/` | canonical scheduler and task DB | Jarvis Core | `KEEP_OURS` |
| Computer Use | `computer_use_mission.py`, browser/UIA tools | existing durable mission/security model | Jarvis Core | `KEEP_OURS` |
| Voice | `voice_service.py`, `realtime_voice/` | one audio/VAD/session/turn authority | Jarvis Core | `KEEP_OURS` |
| Market reads | `market_readonly.py` plus Golden calculations | Jarvis boundary plus stronger Golden domain math | Jarvis read model | `MERGE` |
| Macro/radar | `market.html` and `market_data.py` | broad existing market presentation/providers | Jarvis market read model | `PORT` |
| Scanner | `golden_scanner.py` | multi-asset ranking and 47-setup domain logic | Scanner behind Core | `ADAPT` |
| Regime matching | `meta_strategy.py` | regime profiles, ranking and news/correlation context | market intelligence | `PORT` |
| Risk calculation | `risk_engine.py` | position sizing and guard calculations | policy input only | `ADAPT` |
| Validation | `validation_engine.py`, `strategy_audit.py` | existing validation/audit vocabulary | evidence service | `MERGE` |
| Robot identity | `robot_catalog.py` | stable identity/source/artifact relationships | Jarvis Core | `KEEP_OURS` |
| Compile evidence | `mql5_evidence.py` | separates source and compiler facts | Jarvis Core | `KEEP_OURS` |
| Tester control | `strategy_tester_adapter.py` | controlled external process contract | Jarvis Core | `KEEP_OURS` |
| Broker reads | `market_readonly.py` | explicit read-only boundary | Jarvis Core | `KEEP_OURS` |
| Broker writes | no canonical implementation | avoids unapproved live authority | future explicit gate | `LEGACY_FREEZE` |

## Existing Golden Scanner trade path

Keep the Scanner as intelligence, not as an execution owner. The future adapter should expose an immutable scan snapshot containing symbol, timestamps, input bars, setup IDs/versions, score components, readiness, validation status, source/provider and stale status. A separate Jarvis policy tool may consume that snapshot and produce a proposal. Only a later, explicitly authorized execution design may cross `SecurityManager` and `AuditLog` into a broker adapter. The current `dashboard.html` direct call to `/api/mt5/auto_trade` must not be copied into Jarvis.

`Análise Profunda (Multi-Layer)` can be retained as a Golden intelligence provider after its deterministic layers, external model call, prompt/context, model identity and failure state are represented in provenance. Its Cline/OpenRouter selection must be adapted to `ModelRouter`; no second AI authority is permitted.

## Implementation ordering

1. Preserve the canonical Jarvis boundaries and freeze direct legacy side effects.
2. Build read models for health, market, radar, scanner, strategies, robot catalog and evidence.
3. Associate source/compile/test artifacts by explicit IDs and hashes.
4. Reconcile UI fields and stale/error states against those read models.
5. Add proposal/approval semantics only after read parity.
6. Treat live broker execution as a separate future gate, never as an incidental UI integration.
