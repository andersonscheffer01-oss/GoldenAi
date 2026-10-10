# Jarvis / Golden Capability Recovery Map

This is a no-implementation recovery map. `market.html` is a first-class donor and remains intact until parity is proven. `KEEP`, `CONNECT`, `PORT`, `ADAPT`, `MERGE`, `MIGRATE_AUTHORITY`, `SUPERSEDED_WITH_PARITY`, `LEGACY_FREEZE` and `REJECT` are decisions, not completed work.

| OLD_FEATURE | OLD_SURFACE | OLD_OWNER | VALUE | CURRENT_JARVIS_EQUIVALENT | PARITY_STATUS | SECURITY_STATUS | BEST_IMPLEMENTATION | RECOVERY_DECISION | TARGET_OWNER | TARGET_UI | MIGRATION_GATE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Chat/session | Studio | server agent | rich workflow | Gateway + JarvisService | PARTIAL | canonical stronger | preserve UX, move authority | MIGRATE_AUTHORITY | JarvisService | Chat | session/provenance tests |
| Legacy voice chat | Studio | browser SpeechRecognition/SpeechSynthesis | low-friction voice input | VoiceService | PARTIAL | browser permission only | adapt UX, freeze capture authority | LEGACY_FREEZE | VoiceService | Voice | real mic/VAD gate |
| Canonical voice | Jarvis UI/Desktop | VoiceService/realtime stack | local mic, VAD, STT, TTS, turns | VoiceService | PARTIAL | SecurityManager/Core | keep one owner, finish evidence | KEEP | VoiceService | Voice | real speech gate |
| Model selector/providers | Studio/Dashboard | server agent + UI | task-specific routing | ModelRouter | PARTIAL | duplicated | connect selector to policy | CONNECT | ModelRouter | Models | provider policy matrix |
| Developer/Trader/Assistant modes | Studio | UI prompts | user intent framing | interaction profiles | PARTIAL | ambiguous | map to policy profiles | ADAPT | Jarvis Core | Profiles | mode/authorization separation |
| Multimodal upload | Studio | legacy routes | image/audio/video/doc | Core vision/voice | PARTIAL | temp provenance | adapt through tools | ADAPT | Jarvis Core | Chat/Files | artifact provenance |
| PC/files/terminal | Studio/Dashboard | legacy routes | automation power | Computer Use + SecurityManager | PARTIAL | legacy broad | freeze direct path | LEGACY_FREEZE | SecurityManager | PC/Security | approval and audit parity |
| Robot list | Dashboard | external glob | operational visibility | Robot Catalog | PARTIAL | read-only legacy | classify all artifacts | MERGE | RobotCatalog | Robots | inventory reconciliation |
| MQL5 builder | Studio | server agent | high-value development | MQL5 evidence tools | PARTIAL | direct writes | reuse UX, canonicalize writes | ADAPT | JarvisService | MQL5 | source/compile evidence |
| Market map | market.html | market_data.py | multi-asset view | MT5 read-only tools | MISSING_PARITY | read-only data mixed providers | build read model | PORT | Market Intelligence | Market Overview | provider/source contract |
| Source integrity | market.html | market_data.py | trust and freshness | no full equivalent | MISSING_PARITY | incomplete | canonical source registry | PORT | Jarvis Core | Sources | status/stale tests |
| News flow | market.html | Google RSS path | context | no full equivalent | MISSING_PARITY | no durable provenance | adapt ingestion read-only | PORT | Jarvis Core | News | attribution/dedup policy |
| Gold levels | market.html | market_data.py | explainable levels | MT5 candles only | MISSING_PARITY | read-only | port formula as evidence | PORT | Market Intelligence | Technical | formula fixture tests |
| Technical chart | market.html | chart route + JS | inspection/replay | candle read tool | PARTIAL | read-only | shared read model, Jarvis UI later | CONNECT | Jarvis Core | Technical | chart model contract |
| Currency strength | market.html | market_data.py/JS | relative context | no full equivalent | MISSING_PARITY | broker-dependent | adapt with coverage | ADAPT | Market Intelligence | Strength | missing-symbol tests |
| Sessions | market.html | operational_center.js | timing context | no full equivalent | MISSING_PARITY | fixed UTC only | implement canonical calendar later | PORT | Market Intelligence | Sessions | DST/holiday policy |
| Validation pipeline | market.html | operational_center.js | explainable gate | validation commands | PARTIAL | unknown handling inconsistent | merge into status read model | MERGE | Jarvis Core | Validation | UNKNOWN fail-closed tests |
| Opportunity ranking | market.html/dashboard | scanner.py | prioritization | scanner tools | PARTIAL | score can be misunderstood | connect as non-probability score | CONNECT | Scanner | Opportunities | sample/risk disclosure |
| Calendar and blocks | market.html | Trading Economics optional | event risk | no full equivalent | MISSING_PARITY | key/config external | adapt provider boundary | ADAPT | Jarvis Core | Calendar | provider + stale tests |
| Auditable performance | market.html | journal/stats | outcome truth | journal/task audit | PARTIAL | data quality warnings exist | merge read model | MERGE | AuditLog/Journal | Performance | association and quality gate |
| Fundamental gold | market.html | FRED/BCB rules | context | no full equivalent | MISSING_PARITY | source dates partial | port observations/rules | PORT | Market Intelligence | Macro | series provenance |
| Price drivers | market.html | fixed rules | explainability | no full equivalent | MISSING_PARITY | not predictive | adapt as facts + rules | ADAPT | Market Intelligence | Macro | no-probability wording |
| AI Radar analysis | market.html | legacy model path | synthesis | Jarvis chat/tools | PARTIAL | AI not execution authority | structured context into Jarvis | MIGRATE_AUTHORITY | JarvisService | AI Analysis | context/prompt/evidence tests |
| Replay | market.html | JSONL audit + chart | explainability | no full equivalent | MISSING_PARITY | history path legacy | preserve snapshots, read-only | PORT | AuditLog/Market History | Replay | immutable snapshot tests |
| Production trading | Dashboard/legacy MT5 | mt5_trader/connector | financial action | no canonical execution gate | REJECT_AS_CURRENT_SCOPE | critical | do not migrate here | LEGACY_FREEZE | SecurityManager | Security | separate authorization gate |

## Radar feature recovery matrix

| RADAR_FEATURE | UI_LOCATION | IMPLEMENTATION | DATA_SOURCE | PROVIDER | REAL/MOCK/UNKNOWN | CURRENT_OWNER | SECURITY | PROVENANCE | HISTORICAL_DATA | JARVIS_EQUIVALENT | REUSE_DECISION | TARGET_OWNER | TARGET_UI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Market overview | map/ticker | `get_market_overview` | MT5 + CoinGecko | broker/public | REAL with partial freshness | legacy module | read-only path, legacy connector | timestamps/source labels | no durable snapshot | MT5 tools only | PORT | Market Intelligence | Overview |
| News intelligence | news panel | Google RSS parser | RSS | Google News | REAL ingestion, rule labels | legacy module | outbound read | URL/source/date | no durable history in ingestion | none full | PORT | Jarvis Core | News |
| Technical chart | central chart | `get_market_chart` | MT5 OHLCV | broker | REAL | legacy module | read-only | symbol/timeframe/update | candles in response only | recent candles tool | CONNECT | Market Intelligence | Technical |
| Gold levels | levels board | pivot + clustered levels | MT5 D1/M15 | broker | REAL calculation | legacy module | read-only | formula/reference date | response only | none full | PORT | Market Intelligence | Levels |
| Macro factors | fundamental | FRED/BCB rules | HTTPS series | FRED/BCB | REAL if online, otherwise unknown | legacy module | external read | observation dates | in-process cache only | no full | PORT | Market Intelligence | Macro |
| Currency strength | D1 panel | mean pair change + normalization | MT5 Forex pairs | broker | REAL with coverage bias | legacy JS/Python | read-only | symbol coverage not durable | no history | none full | ADAPT | Market Intelligence | Strength |
| Sessions | operational center | fixed UTC windows | system UTC clock | none | REAL but incomplete | legacy JS | read-only | no DST/holiday proof | no history | none full | PORT | Market Intelligence | Sessions |
| Pipeline | operational center | UI boolean projection | overview/radar/risk | mixed | PARTIAL | legacy JS | fail-closed inconsistent | stage details only | no durable run | validation tools | MERGE | Jarvis Core | Validation |
| Opportunity ranking | operational center | scanner score/readiness | scanner + journal fields | MT5 + local | PARTIAL | scanner legacy | no order in scanner | score/source fields | limited | scanner results | CONNECT | Scanner | Opportunities |
| Calendar | operational center | optional TE API | economic events | Trading Economics | UNKNOWN when unconfigured | legacy module | key env only | fields mapped, no full stale model | no history | none full | ADAPT | Jarvis Core | Calendar |
| Performance | operational center | journal stats checks | trade journal | local | PARTIAL | legacy journal | flags bad RR/sample | journal provenance | 30-trade threshold | AuditLog read model | MERGE | AuditLog | Performance |
| AI analysis/replay | analysis drawer | structured context + LLM | MT5/scanner/macro/history | local/provider | PARTIAL | server agent | legacy provider path | JSONL audit exists | replay records | Jarvis chat | MIGRATE_AUTHORITY | JarvisService | AI/Replay |

## Zero-loss rule

No donor surface is retired because it is legacy. `MISSING_PARITY` remains a blocking status for market overview, news, technical chart, levels, strength, sessions, validation, ranking, calendar, performance, fundamental/macro, source integrity, AI analysis and replay until the canonical Control Center has equivalent read models, security states, provenance and regression coverage.
