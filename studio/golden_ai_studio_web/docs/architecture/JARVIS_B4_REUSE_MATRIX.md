# Jarvis B4 Reuse Matrix

Date: 2026-09-29
Baseline: `013ba7c700a5c62fc97aaab10541ed5a769b5d13`

Decision vocabulary: `KEEP_JARVIS`, `KEEP_GOLDEN`, `ADAPT_GOLDEN_INTO_JARVIS`,
`MERGE`, `REIMPLEMENT_PATTERN`, `FREEZE_LEGACY`, `DEFER`, `REJECT`.

## Capability ownership matrix

| Capability | Golden implementation | Jarvis implementation | Overlap | Best current owner | Decision | Migration needed | UI status |
|---|---|---|---|---|---|---|---|
| Chat routing | Studio `/api/chat`, direct handlers | Brain + ModelRouter | high | Jarvis | KEEP_JARVIS; PORT contracts | perimeter containment later | Main/Market Chat canonical |
| Provider policy | direct Gemini/Groq/Ollama handlers and adapters | ModelRouter/provider adapters | high | Jarvis | ADAPT_GOLDEN_INTO_JARVIS only for policy lessons | declarative policy later | status exists, policy view partial |
| Scanner scoring | `golden_scanner.py`, setup/ranking logic | GoldenReadBridge normalized snapshot | medium | Golden calculation, Jarvis boundary | ADAPT_GOLDEN_INTO_JARVIS | typed semantics/freshness | partial read table |
| Radar | `market.html`, market data and macro routes | B3 radar/market read models | high | Jarvis boundary with Golden donor | ADAPT_GOLDEN_INTO_JARVIS | detail/read parity | overview partial |
| Deep analysis | `analysis_engines.py`, market package | MarketContext/deep-analysis adapter | medium | Jarvis boundary | ADAPT_GOLDEN_INTO_JARVIS | complete explainable context | detail partial |
| Meta strategy | `meta_strategy.py` | GoldenReadBridge meta/regime reads | medium | Golden calculation, Jarvis policy | ADAPT_GOLDEN_INTO_JARVIS | evidence labels | read-only |
| Risk | `risk_engine.py` | B3 risk read model | medium | Jarvis security boundary | ADAPT_GOLDEN_INTO_JARVIS | portfolio/explanation contract | read-only, no authorization |
| Validation | `validation_engine.py`, statistics | evidence/read models | medium | Jarvis read boundary | ADAPT_GOLDEN_INTO_JARVIS | synthetic/real evidence labels | partial |
| Robot catalog | catalog/provenance stores | `RobotCatalogReadModel` | high | Jarvis read model | KEEP_JARVIS | reconcile data only in later gate | partial |
| Robot repertoire | legacy status/mutation paths | no complete canonical mutation UI | medium | Jarvis SecurityManager | DEFER | explicit action workflow | not yet visible |
| Tester evidence | adapter, fixture and evidence contracts | B2/B3 evidence read models | high | Jarvis evidence boundary | KEEP_JARVIS | association/read views | evidence rows, no run action |
| MQL5 builder | legacy Studio and project paths | evidence/tool boundary | low/medium | legacy donor only | FREEZE_LEGACY + REFERENCE_ONLY | none for behavior |
| Production robots | `projetos/`, MT5 EA paths | protected external domain | none acceptable | existing protected area | FREEZE_LEGACY | none | never bridge strategy behavior |
| MT5 read | `mt5_connector.py`, market helpers | runtime profile and read bridge | medium | Jarvis boundary | ADAPT_GOLDEN_INTO_JARVIS | controlled real-read gate | status/read only |
| Trading/orders | legacy `order_send`, auto-trade routes | no canonical promotion | dangerous overlap | no promotion | REJECT for normal B4 | separate future authority gate | analysis != execution |
| Scientific memory | Golden scientific memory | Memory V2 + CanonicalMemoryBoundary | high | Jarvis memory authority | ADAPT_GOLDEN_INTO_JARVIS | typed contracts/import manifests | summary only |
| Temporal market memory | market journals/history | no dedicated canonical model | medium | Jarvis boundary | ADAPT_GOLDEN_INTO_JARVIS | subordinate projection, no second DB | design only |
| Computer use | legacy browser/system helpers | Jarvis ToolRegistry/SecurityManager | medium | Jarvis | KEEP_JARVIS | none | canonical controls |
| Voice capture | browser SpeechRecognition/Radar voice | canonical VoiceService and clients | high | Jarvis VoiceService | FREEZE_LEGACY; REFERENCE_ONLY | hardware gate only | paused |
| Voice TTS | browser SpeechSynthesis/SAPI | provider-neutral VoiceService | medium | Jarvis | KEEP_JARVIS + ADAPT lessons | no second voice brain | paused |
| Agents | legacy specialized agents | Jarvis tasks/tools | medium | Jarvis | ADAPT metadata only | no parallel orchestrator | not a separate center |
| Plugins/MCP | plugin loader, MCP references | ToolRegistry/McpClient scaffolding | medium | Jarvis | ADAPT with allowlist | integrated client proof | partial |
| UI panels | Studio/Dashboard/Radar | Jarvis Web/Desktop Control Center | high | Jarvis UI | PORT read views | selective parity | B3 partial |
| Personal Finance | auxiliary finance routes | none | none acceptable | none | DEFER | none | out of scope |

## Reuse rules per donor

- Reuse calculations only through a bounded adapter. Do not copy a second
  scanner, risk engine, analysis engine, memory service or voice brain.
- Preserve original source identifiers, timestamps, evidence class and stale
  state. A read model must never upgrade `UNKNOWN`, `STALE` or `SYNTHETIC` to
  live truth.
- Keep `ACTIVE_IN_REPERTOIRE` distinct from `AUTHORIZED_TO_TRADE`.
- Treat `market.html` as a proven visual donor, not as an authority or a reason
  to create a parallel desktop backend.
- Treat OpenJarvis voice ideas as `REFERENCE_ONLY` until the canonical mic gate
  is solved; do not install or run it in B4 planning.

## Rejected reuse

- Direct legacy order/auto-trade functions as a canonical capability.
- Direct provider calls from Market Chat, Deep Analysis or UI code.
- Legacy browser voice capture as Jarvis VoiceService ownership.
- Production EA logic or MQL5 behavior as a Golden/Jarvis recovery artifact.
- Personal Finance donors, MCPs or banking integrations in the active roadmap.
