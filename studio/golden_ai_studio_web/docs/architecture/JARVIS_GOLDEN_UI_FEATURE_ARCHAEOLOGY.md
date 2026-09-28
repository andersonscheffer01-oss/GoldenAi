# JARVIS / GOLDEN UI Feature Archaeology

Static map of user-facing capability donors. The target is one canonical Jarvis Web/Desktop control surface with read-first recovery and no duplicated authority.

| Surface | Useful features found | Backend relationship | Recovery decision |
|---|---|---|---|
| `studio_v7.html` | chat/model modes, market/radar, charts, MQL5/EA builder, files, multimodal, PC/system, security, analytics/backtests | many direct legacy routes, including `/api/chat` | PORT read views and workflows selectively; LEGACY_FREEZE writes |
| `dashboard.html` | robots, backtests, scanner, radar, risk, strategies, validation, security, chat, compare/statistics | legacy dashboard routes | PORT governed read panels |
| `market.html` | multi-asset map, gold, news, technical chart, macro, sessions, pipeline, ranking, calendar, performance, replay, AI analysis | `market_data.py`, scanner and analysis routes | PORT as Radar read model; preserve source/freshness labels |
| `jarvis_ui/jarvis.html` | canonical chat, voice/command, trading read panels, search, telemetry | Gateway and Jarvis Core | KEEP_OURS |
| `jarvis_desktop/` | desktop shell and controlled integration | canonical services/tools | KEEP_OURS |
| Radar Central voice drawer | mic/chat/status UI, browser capture, legacy chat/TTS endpoints | capture bypasses VoiceService; status can query it | LEGACY_FREEZE; adapt observations only |
| auxiliary `jarvis/frontend` | older auth/conversation/finance/device surfaces | auxiliary backend | REFERENCE_ONLY until authority is proven |

## Feature losses versus Jarvis UI

The canonical UI currently does not visibly expose the full Radar, deep-analysis, scientific-memory, validation-detail, or robot evidence surface. B1 adds a read-bridge summary card and overview endpoint; it does not claim full parity.

## Safety boundary

UI recovery must use Jarvis Gateway, ToolRegistry, SecurityManager, AuditLog, and canonical service contracts. A visually complete panel is not evidence of backend authority. Direct legacy order buttons, broker actions, credential flows, and browser voice capture remain frozen until separately governed.

## Voice comparison pointer

The detailed Studio/Radar voice reconciliation already exists in `JARVIS_GOLDEN_VOICE_RECONCILIATION.md`. This report records the UI consequence only: retain one canonical `VoiceService`, and do not create a Golden voice brain.
