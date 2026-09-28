# JARVIS / GOLDEN Capability Recovery Matrix

Classification vocabulary: KEEP_OURS, PORT, ADAPT, MERGE, REIMPLEMENT_PATTERN, REFERENCE_ONLY, LEGACY_FREEZE, REJECT.

| Area | Golden donor | Jarvis canonical owner | Classification | Boundary |
|---|---|---|---|---|
| Memory lifecycle | scientific memory service | Jarvis Memory V2 | ADAPT | typed evidence and conflicts behind boundary |
| Memory retrieval | legacy vector wrappers | Jarvis retrieval | REFERENCE_ONLY | no second index authority |
| Chat routing | Studio `/api/chat` | Brain/ModelRouter | KEEP_OURS + PORT contracts | legacy endpoint remains contained |
| Voice capture | browser SpeechRecognition | VoiceService | LEGACY_FREEZE | no browser voice brain |
| Voice TTS | browser SpeechSynthesis/desktop speech | VoiceService/provider-neutral TTS | ADAPT | preserve provider policy |
| Radar overview | market routes and scanner | Golden read bridge | PORT | read-only, provenance required |
| Deep analysis | analysis engines/market package | future Jarvis analysis adapter | ADAPT | runtime validation before authority |
| Meta strategy | `meta_strategy.py` | future governed read tool | ADAPT | explain, do not authorize orders |
| Risk | `risk_engine.py` | future governed risk read model | ADAPT | no order side effect |
| Validation | validation/statistics | evidence/read models | ADAPT | synthetic data labeled |
| Trade journal | JSONL journal/setup DB | future data recovery adapter | PORT | preserve original ids and timestamps |
| Robot catalog | catalog/provenance model | Jarvis catalog read model | KEEP_OURS | no repertoire mutation |
| Tester evidence | adapter/fixture contracts | Jarvis evidence registry | KEEP_OURS | controlled runs only |
| MQL5 builder | Studio builder paths | Jarvis task/tool boundary | REFERENCE_ONLY | no strategy merge |
| Computer use | legacy browser/system tools | Jarvis ToolRegistry/SecurityManager | KEEP_OURS | fail closed and audited |
| Agents | legacy agents/orchestrator | Jarvis tasks/tools | ADAPT | metadata/patterns only |
| Plugins | plugin loader | bounded registry/MCP | ADAPT | explicit allowlist |
| UI panels | Studio/Dashboard/Radar | canonical Jarvis UI/Desktop | PORT | read views first |
| Direct trading | legacy order paths | no canonical promotion | LEGACY_FREEZE | no orders or broker changes |
| Production robots | existing MQL5 repertoire | existing protected area | LEGACY_FREEZE | never part of bridge recovery |

## Authority rule

One Jarvis Core owns policy, tools, model routing, audit, provenance, task state, and memory authority. Recovery adapters may read and normalize legacy capability; they must not create parallel services, hidden writes, or alternate security decisions.

## Sequencing

Finish and review B1 checkpoint first. Then define B2 around typed read adapters, memory evidence semantics, freshness, and data reconciliation. UI parity and any runtime validation follow explicit gates.
