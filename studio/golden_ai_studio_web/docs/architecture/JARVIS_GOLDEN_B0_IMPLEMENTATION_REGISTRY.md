# Golden / Jarvis B0 Implementation Registry

This registry freezes B0 ownership and recovery decisions. It is a design/governance artifact, not an implementation. Legacy pages remain available until `PARITY_PROVEN=YES`.

| CAPABILITY_ID | DOMAIN | SOURCE_SURFACE | SOURCE_IMPLEMENTATION | CURRENT_OWNER | CURRENT_AUTHORITY | TARGET_OWNER | TARGET_UI | DATA_SOURCE | SIDE_EFFECT_LEVEL | SECURITY_REQUIREMENT | AUDIT_REQUIREMENT | PROVENANCE_REQUIREMENT | REUSE_DECISION | PARITY_STATUS | MIGRATION_BATCH | LEGACY_RETIREMENT_BLOCKER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GOLDEN_CHAT | Golden Chat | `studio_v7.html` | `/api/chat`, composer | server_agent | legacy chat/tool loop | JarvisService | Chat | model/providers/files | local/external | SecurityManager | AuditLog | session/provider | MIGRATE_AUTHORITY | PARTIAL | B1/B6 | canonical chat parity |
| GOLDEN_DASHBOARD | Golden Dashboard | `dashboard.html` | dashboard routes/widgets | server_agent | direct legacy routes | JarvisService | Trading | MT5/journal/scanner | mixed | SecurityManager | AuditLog | read model/source | CONNECT | PARTIAL | B1-B5 | route containment |
| RADAR_MACRO | Radar Macro | `market.html` | market scripts + `market_data.py` | market module | legacy read path | MarketContext/Core | Radar Macro | MT5/external macro/news | read | source policy | AuditLog/read receipt | provider/timestamp/stale | PORT | MISSING_PARITY | B1-B5 | full feature parity |
| MARKET_INTELLIGENCE | Market Intelligence | Radar | overview/forex/chart/tick | market_data.py | legacy data boundary | Jarvis Core | Market Overview | MT5/CoinGecko | read | provider allowlist | read receipt | symbol/timeframe/source | PORT | PARTIAL | B1/B2 | canonical read model |
| TECHNICAL_ANALYSIS | Technical Analysis | Radar | ATR/pivots/levels/BOS/CHoCH | market_data.py | legacy calculation | Core read model | Technical | MT5 candles | read | read-only | formula receipt | input bars/formula | PORT | PARTIAL | B2 | formula parity |
| MACRO_FUNDAMENTAL | Macro/Fundamental | Radar | FRED/BCB rules | market_data.py | legacy calculation | MarketContext | Macro | FRED/BCB | read | provider policy | observation receipt | series/date/transform | ADAPT | MISSING_PARITY | B4 | source integrity |
| NEWS | News | Radar | Google RSS parser | market_data.py | legacy ingestion | Jarvis Core | News | RSS | read | outbound policy | source receipt | URL/source/date | PORT | MISSING_PARITY | B4 | attribution/dedup |
| ECONOMIC_CALENDAR | Economic Calendar | Radar | Trading Economics optional | market_data.py | legacy provider | Jarvis Core | Calendar | Trading Economics | read | key boundary | provider receipt | event fields/timezone | ADAPT | MISSING_PARITY | B4 | stale/unknown policy |
| MARKET_SESSIONS | Market Sessions | Radar | fixed UTC rows | operational_center.js | legacy UI | MarketContext | Sessions | UTC clock/calendar | read | none | status receipt | timezone/DST/holiday | PORT | MISSING_PARITY | B3 | calendar policy |
| OPPORTUNITIES | Scanner | Radar/Dashboard | scanner radar/ranking | golden_scanner.py | legacy scanner | Scanner/Core | Opportunities | MT5 + setups | read | score not authority | scan receipt | inputs/score/sample | CONNECT | PARTIAL | B3/B5 | no probability claim |
| STRATEGIES | Strategies | Dashboard | setup definitions/manager | legacy manager | legacy config | Strategy Catalog | Strategies | local definitions | local mutation | approval for mutation | config audit | version/preset | MERGE | PARTIAL | B5/B7 | repertoire separation |
| VALIDATION | Validation | Dashboard/Radar | validation_engine/pipeline | legacy engine | synthetic/read path | Core validation | Validation | synthetic/journal/MT5 | read | unknown fail-closed | validation receipt | sample/source/method | ADAPT | PARTIAL | B3/B5 | no false real label |
| PERFORMANCE | Backtesting | Dashboard/Radar | journal stats/backtests | legacy journal | legacy read/write | AuditLog/Journal | Performance | journal/backtest artifacts | local mutation | no history rewrite | result association | run/source/sample | MERGE | PARTIAL | B5 | bad data flagged |
| ROBOT_CATALOG | Robot Catalog | Dashboard/external | glob + catalog | mixed | catalog/legacy glob | RobotCatalog | Robots | repo/external files | read | no auto-promotion | catalog receipt | source/hash/class | MERGE | PARTIAL | B1/B7 | inventory reconcile |
| MQL5_EVIDENCE | MQL5 | Studio/adapter | builder/compile paths | legacy + adapter | mixed | JarvisService | MQL5 | source/compiled artifacts | local/external | approval/evidence gate | compile receipt | source/compiled/preset | ADAPT | PARTIAL | B7 | compile success proof |
| STRATEGY_TESTER | Strategy Tester | adapter/legacy tester | StrategyTesterAdapter | Core adapter | canonical adapter | JarvisService | Tester | fixture/config/result | external process | explicit approval | AuditLog + manifest | run/config/result hashes | KEEP_OURS | PARTIAL | B7 | prior failures immutable |
| GOLDEN_VOICE_LEGACY | Voice | Studio | browser SpeechRecognition/TTS | Studio/server_agent | legacy browser/chat | VoiceService | Voice | browser mic/chat | external/local | canonical security | canonical audit | session/provider | LEGACY_FREEZE | PARTIAL | B1/B6 | one voice authority |
| VOICE_CORE | Voice | Jarvis UI/Desktop | `VoiceService` + realtime | VoiceService | canonical | VoiceService | Voice | sounddevice/Silero/STT/TTS | local audio | SecurityManager | AuditLog | session/turn/provider | KEEP_OURS | PARTIAL | B1/B6 | real mic gate |
| COMPUTER_USE | Computer Use | Jarvis UI/Desktop | missions/tools | JarvisService | canonical | JarvisService | Computer | Windows/browser | external | SecurityManager | AuditLog | mission/receipt | ALREADY_CANONICAL | PARTIAL | existing | no parallel agent |
| TASK_SYSTEM | Task System | Jarvis | TaskManager/scheduler | JarvisService | canonical | TaskManager | Tasks | canonical DB | local mutation | scoped approval | AuditLog | task/run/lease | ALREADY_CANONICAL | PROVEN | existing | no second scheduler |
| MEMORY | Memory | Jarvis/Studio | memory routes | JarvisService | canonical/legacy bridge | Memory boundary | Memory | canonical memory | local mutation | policy/classification | AuditLog | namespace/source | CONNECT | PARTIAL | B1 | one DB authority |
| SKILLS | Skills | Jarvis Core | SkillsRouter | JarvisService | canonical | SkillsRouter | Skills | registry | read/config | policy | AuditLog | tool/skill identity | KEEP_OURS | PARTIAL | B1 | no parallel router |
| MCP | MCP | Jarvis Core | MCP registry | JarvisService | canonical provider | ToolRegistry | Skills/MCP | configured providers | external | SecurityManager | AuditLog | provider/tool scope | KEEP_OURS | PARTIAL | B1 | provider not authority |
| SECURITY | Security | all surfaces | SecurityManager + legacy gates | Core/legacy | canonical SecurityManager | SecurityManager | Security | policy/approvals | mutation | fail-closed | AuditLog | action/target/approval | MIGRATE_AUTHORITY | PARTIAL | B1 | direct route freeze |
| AUDIT | Audit | all surfaces | AuditLog/telemetry | Jarvis Core | canonical AuditLog | AuditLog | Audit | action receipts | local mutation | redaction | immutable receipt | KEEP_OURS | PARTIAL | B1 | one audit model |
| SOURCE_INTEGRITY | Source Integrity | Radar | source list/cache | market_data.py | legacy source display | Core | Sources | provider status | read | no secrets | source receipt | timestamp/stale/fallback | PORT | MISSING_PARITY | B1 | provider truth |
| AI_ANALYSIS | AI Analysis | Studio/Radar | chat/market analyze | server_agent | duplicated model paths | ModelRouter | AI Analysis | structured context | external/local | no execution authority | response receipt | context/provider/model | MIGRATE_AUTHORITY | PARTIAL | B6 | structured context |
| REPLAY | Replay | Radar | JSONL analysis history | server_agent | legacy history | AuditLog/Market History | Replay | audit JSONL/MT5 | local mutation | immutable history | replay receipt | snapshot/hash/time | PORT | MISSING_PARITY | B5 | history parity |

## Legacy authority classification

The following route/function families are statically identified and remain `LEGACY_FREEZE`; they were not executed or removed:

| Class | Legacy examples | Canonical replacement |
|---|---|---|
| `READ_ONLY` | status, robot list, market overview, scanner reads | Core read models / ToolRegistry |
| `LOCAL_MUTATION` | filesystem write/clean, strategy toggles/presets, import history, provider/config keys | JarvisService + SecurityManager + AuditLog |
| `EXTERNAL_SIDE_EFFECT` | agent/run-command, desktop actions, MQL5 compile launch, legacy tester launch | scoped Computer Use / evidence adapter |
| `BROKER_SIDE_EFFECT` | auto-trade, close position, position manager, `mt5_trader.execute_trade`, connector `order_send` | no B0 replacement; separate future live gate |
| `DANGEROUS` | direct shell/PowerShell, file deletion, live order, broker mutation, terminal/profile fallback | `LEGACY_FREEZE`; canonical SecurityManager only |
| `VOICE_DUPLICATED_AUTHORITY` | browser capture/TTS, legacy voice routes, direct `/api/chat` from Studio | canonical VoiceService -> JarvisService |

`LEGACY_FREEZE_COUNT:` 18 registry capability families contain direct or indirect legacy authority; this is a governance inventory, not a claim that there are only 18 individual routes.

## B1 contract

`B1_READY: YES_FOR_REVIEW_ONLY`. B1 may implement canonical read models for system health, MT5 state, Robot Catalog, tester evidence/history, Radar summary, source integrity, scanner/opportunities and strategies/validation. Frontends must consume Jarvis read models and must not gain direct authority. No live trading, Strategy Tester, production EA compile, provider configuration, database migration or legacy retirement is included.
