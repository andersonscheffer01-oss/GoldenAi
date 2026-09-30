# JARVIS / GOLDEN Final Capability Matrix - Post-B4.1

Static source comparison. `INTEGRATION_STATUS` is the primary status. `QUALITY_COMPARISON` and `SECURITY_RISK` are independent dimensions. No row authorizes runtime execution.

| ID | DOMAIN | CAPABILITY | GOLDEN_EVIDENCE | JARVIS_EVIDENCE | GOLDEN_STATUS | JARVIS_STATUS | INTEGRATION_STATUS | QUALITY_COMPARISON | SECURITY_RISK | DATA_VALUE | REUSE_DECISION | ROADMAP_PRIORITY | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-01 | Core | Main chat/session | `studio_v7.html`, `/api/chat` | `JarvisService.generate_response` | mature | canonical | FULLY_INTEGRATED | Jarvis authority stronger | low | high | KEEP | P0 | B4.1 compatibility delegation |
| CM-02 | Core | Tool execution | legacy agent route | `JarvisService.execute_tool` | broad | canonical | FULLY_INTEGRATED | Jarvis governance stronger | medium | high | KEEP | P0 | security/audit owner is Core |
| CM-03 | Core | Streaming chat | `/stream/chat` | no canonical equivalent | active | missing | PARTIAL | Golden breadth, Jarvis policy stronger | high | medium | LEGACY_FREEZE | P0 | frozen until canonical streaming |
| CM-04 | Governance | Security policy | root execution helper | `SecurityManager` | mixed | canonical | PARTIAL | Jarvis stronger | high | high | CONVERGE | P0 | legacy compatibility remains |
| CM-05 | Governance | Audit | market JSONL and root logger | `AuditLog` | broad | canonical | PARTIAL | Jarvis owner stronger | medium | high | MERGE | P1 | market events need one receipt |
| CM-06 | Governance | Provenance/freshness | UI source labels | evidence/read models | partial | foundation | PARTIAL | complementary | medium | high | ADAPT | P1 | add durable source identity |
| CM-07 | Tasks | Task lifecycle | legacy automation routes | TaskManager | partial | mature | FULLY_INTEGRATED | Jarvis stronger | medium | high | KEEP | P0 | database binding still needs runtime proof |
| CM-08 | Computer Use | Browser/files/terminal | legacy helpers | governed tools | broad | mature | FULLY_INTEGRATED | Jarvis safer | high | high | KEEP | P0 | legacy helpers reference only |
| CM-09 | Memory | General memory | older memory services | boundary and memory v2 | broad | canonical direction | PARTIAL | complementary | medium | high | KEEP | P1 | multiple writers remain |
| CM-10 | Memory | Scientific evidence | `core/memory` and `memory_chat` | partial memory v2 fields | mature donor | incomplete | NOT_INTEGRATED | Golden semantics richer | medium | very high | ADAPT | P1 | typed evidence contract |
| CM-11 | Memory | Revisions/conflicts | repository tables | partial lifecycle | mature donor | incomplete | NOT_INTEGRATED | Golden richer | medium | very high | ADAPT | P1 | no silent overwrite |
| CM-12 | Memory | Experiment links | quant/memory modules | partial identifiers | mature donor | incomplete | NOT_INTEGRATED | Golden richer | medium | high | ADAPT | P1 | stable experiment/artifact IDs |
| CM-13 | Market | Overview/multi-asset | `market.html`, `market_data.py` | limited read model | mature | partial | NOT_INTEGRATED | Golden richer | medium | high | PORT | P1 | read-only source contract |
| CM-14 | Market | Source integrity | market source labels | no full registry | partial | missing | NOT_INTEGRATED | Golden has useful labels | medium | high | PORT | P1 | freshness and stale states |
| CM-15 | Market | News flow | Google RSS path | no full equivalent | mature donor | missing | NOT_INTEGRATED | Golden richer | medium | high | ADAPT | P1 | URL/date/dedup provenance |
| CM-16 | Market | Macro/fundamentals | FRED/BCB rules | no full equivalent | partial | missing | NOT_INTEGRATED | Golden richer | medium | high | PORT | P1 | provider boundary required |
| CM-17 | Market | Gold levels | pivot/cluster calculations | no full equivalent | mature donor | missing | NOT_INTEGRATED | Golden explainability | medium | medium | PORT | P1 | formula evidence |
| CM-18 | Market | Technical chart/replay | MT5 candles/chart JS | recent candle tools | mature | partial | PARTIAL | complementary | low | high | CONNECT | P1 | replay not canonical |
| CM-19 | Market | Currency strength | pair normalization | no full equivalent | partial | missing | NOT_INTEGRATED | Golden richer, coverage bias | medium | medium | ADAPT | P2 | disclose symbol coverage |
| CM-20 | Market | Sessions/calendar | fixed UTC and optional TE | no full equivalent | partial | missing | NOT_INTEGRATED | Golden useful but incomplete | medium | medium | PORT | P2 | DST/holiday policy |
| CM-21 | Market | Price drivers | fixed explanatory rules | no full equivalent | partial | missing | NOT_INTEGRATED | Golden useful facts | low | medium | ADAPT | P2 | never predictive claim |
| CM-22 | Scanner | Opportunity ranking | `golden_scanner.py` | partial tools | mature donor | partial | PARTIAL | Golden detail, Jarvis governance | high | high | CONNECT | P1 | score is not probability |
| CM-23 | Scanner | Deep analysis | `analysis_engines.py` and UI | chat/MarketContext | mature donor | partial | PARTIAL | Golden richer context | high | high | ADAPT | P1 | Core owns synthesis |
| CM-24 | Risk | Position/risk explanation | `risk_engine.py` | partial bridge | mature donor | partial | PARTIAL | Golden detail | high | high | MERGE | P1 | no order authority |
| CM-25 | Validation | Robustness/Monte Carlo | `validation_engine.py` | partial commands | mature donor | partial | PARTIAL | Golden detail with labels | high | high | MERGE | P1 | synthetic vs real explicit |
| CM-26 | Performance | Stats/calibration | `statistics_engine.py` | limited audit/journal | mature donor | foundation | PARTIAL | Golden richer | medium | high | PORT | P1 | sample quality and calibration |
| CM-27 | Performance | Trade journal/setup history | JSONL/journal modules | audit/read foundations | mature donor | partial | PARTIAL | complementary | high | very high | MERGE | P1 | authority/reconciliation pending |
| CM-28 | Robots | Robot inventory | external glob/catalog inputs | RobotCatalogReadModel | broad | foundation | PARTIAL | Jarvis provenance stronger | high | high | MERGE | P1 | no production edits |
| CM-29 | Robots | Robot-market matching | setup/radar fields | no empirical matcher | partial | missing | NOT_INTEGRATED | Golden signals only | high | high | DESIGN_ONLY | P2 | use read-only association |
| CM-30 | MQL5 | Source/build evidence | MQL5 routes/evidence | evidence foundation | broad | foundation | PARTIAL | complementary | high | high | KEEP | P1 | no compile in this audit |
| CM-31 | Tester | Strategy Tester adapter | tester config/run artifacts | canonical adapter | foundation | foundation | PARTIAL | Jarvis provenance stronger | high | very high | KEEP | P1 | fixture-only controlled gate |
| CM-32 | Tester | Tester UI/catalog association | legacy tester views | no complete Control Center | partial | missing | NOT_INTEGRATED | Golden visible, Jarvis safer | high | high | PORT | P2 | read-only evidence views |
| CM-33 | Trading | Production orders | dashboard and MT5 legacy | no canonical order owner | active | intentionally absent | LEGACY_DANGEROUS | Golden operational only | critical | high | LEGACY_FREEZE | P0 | out of recovery scope |
| CM-34 | Trading | Auto-trade/Enter Trade | dashboard timer/button | no canonical equivalent | active | intentionally absent | LEGACY_DANGEROUS | no migration claim | critical | medium | REJECT | P0 | no execution performed |
| CM-35 | Voice | Browser voice | `studio_v7.html` | VoiceService | donor | partial/blocked | PARTIAL | Jarvis authority stronger | high | medium | REFERENCE_ONLY | P2 | no hardware test |
| CM-36 | Voice | VAD/STT/TTS/turns | legacy browser APIs | canonical service/tests | partial | foundation | PARTIAL | Jarvis design stronger | high | medium | KEEP | P2 | real acoustic gate pending |
| CM-37 | Desktop | Canonical WebView | legacy native surfaces | Jarvis Desktop | partial | canonical | FULLY_INTEGRATED | Jarvis stronger | medium | high | KEEP | P0 | legacy native classes frozen |
| CM-38 | UI | Control Center | dashboards/studio | Jarvis UI | broad | partial | PARTIAL | Golden breadth, Jarvis safety | medium | high | PORT | P1 | read models before actions |
| CM-39 | Skills | Skill catalog | `.agents/skills` | project/runtime skills | broad | partial | PARTIAL | complementary | low | medium | ADAPT | P2 | metadata and ownership |
| CM-40 | MCP | MCP integrations | scattered descriptors | foundation only | partial | foundation | PARTIAL | unknown deployment | high | medium | ADAPT | P2 | no external calls |
| CM-41 | Agents | Agent/plugin inventory | `agents/`, `plugins/` | registry foundations | broad | foundation | PARTIAL | Golden breadth | medium | medium | ADAPT | P2 | authority/permission map |
| CM-42 | Observability | Runtime health | logs/status endpoints | partial health/audit | partial | partial | PARTIAL | complementary | medium | high | MERGE | P1 | correlation/freshness |
| CM-43 | Mobile | Mobile UI | no approved canonical donor | none | unknown | missing | NOT_INTEGRATED | unknown | medium | low | DEFER | P3 | out of current batches |
| CM-44 | Finance | Personal finance | no approved current path | deferred | deferred | missing | SUPERSEDED | out of scope | medium | low | DEFER | P3 | not a B4.2 target |
| CM-45 | Historical | Legacy snapshots/backups | archives and reports | no active authority | historical | historical | HISTORICAL_ONLY | evidence only | medium | high | REFERENCE_ONLY | P2 | validate before recovery |
| CM-46 | Historical | Old donor repositories | research trees | no runtime authority | historical | none | HISTORICAL_ONLY | reference only | low | medium | REFERENCE_ONLY | P3 | not product roots |
| CM-47 | Architecture | Superseded duplicate brains | Golden legacy services | Jarvis Core | superseded | canonical | SUPERSEDED | Jarvis convergence stronger | critical | medium | LEGACY_FREEZE | P0 | one Jarvis rule |
| CM-48 | Architecture | Legacy native action UI | old Desktop classes | canonical shell | active legacy | canonical | LEGACY_DANGEROUS | Jarvis safer | high | medium | LEGACY_FREEZE | P0 | no parallel authority |
| CM-49 | Unknown | Active DB binding | many DB families | intended canonical paths | unknown | unknown | UNKNOWN | cannot infer statically | high | very high | VALIDATE_FIRST | P0 | no DB reads here |
| CM-50 | Unknown | Runtime provider/account state | config/runtime dependent | policy foundations | unknown | unknown | UNKNOWN | not testable read-only | critical | high | VALIDATE_FIRST | P0 | no credentials read |

## Interpretation

`FULLY_INTEGRATED` means the capability has one usable canonical owner and an observed contract. It does not mean every legacy caller is removed. `PARTIAL` means a usable foundation exists but parity, freshness, security, or UI integration is incomplete. `NOT_INTEGRATED` means valuable Golden behavior has no equivalent canonical read model. `SUPERSEDED` means the old path must not become a second authority. `LEGACY_DANGEROUS` is a source/risk classification, never an execution result. `UNKNOWN` means static evidence is insufficient.
