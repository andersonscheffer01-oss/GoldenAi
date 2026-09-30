# JARVIS / GOLDEN Final Data Recovery Map

Static inventory and decision map. No database, JSONL, backtest, or fixture content was opened or changed in this audit. Paths identify candidate sources only.

| Candidate source | Format/family | Value | Provenance condition | Duplication concern | Validation required | Recovery decision | Canonical owner |
|---|---|---|---|---|---|---|---|
| `data/market_ai_audit.jsonl` | JSONL audit events | market analysis history | event schema, timestamp, source, correlation | root and copied runtime files possible | schema/hash/ordering audit | recover selectively | AuditLog-linked market history |
| `data/setup_database/setups.jsonl` | JSONL setups | setup history and labels | setup identity and source | multiple setup/runtime copies | identity/dedup/reconciliation | recover selectively | scanner/performance read model |
| `data/trade_journal/*.jsonl` | JSONL journal | outcomes and execution context | journal IDs, timestamps, source | date/runtime copies | authority and outcome integrity | recover selectively | journal/AuditLog model |
| `studio/historico_v2.json` | JSON history | historical context | schema/version and source | legacy snapshots | parse and provenance check | reference first | canonical memory only after gate |
| `config/backtest_results/*.json` | backtest artifacts | result evidence | run ID, robot, hash, config | generated/retry duplicates | manifest/result reconciliation | recover evidence only | StrategyTester evidence |
| `studio/.../test_fixtures/` | fixture source/config | controlled proof | fixture ID/source hash | retry artifacts | fixture contract and hash | preserve | tester/evidence boundary |
| `studio/.../jarvis/robot_catalog.db` | SQLite catalog | robot inventory/evidence association | artifact IDs and source roots | catalog/runtime copies | active binding and schema | canonical candidate | RobotCatalogReadModel |
| `studio/.../jarvis/golden_tasks.db` | SQLite task store | task lifecycle | task IDs and audit | multiple task DB roots | active writer/caller inventory | canonical candidate | TaskManager |
| `studio/.../jarvis/golden_memory.db` | SQLite memory | Jarvis memory | boundary and writer receipt | copies under root/jarvis | active binding proof | canonical candidate | CanonicalMemoryBoundary |
| `core/memory` repository | SQLite-backed scientific memory | typed evidence/revisions/conflicts | source IDs, evidence levels, links | parallel memory authority | semantics and caller inventory | ADAPT semantics | canonical Jarvis memory |
| `data/qdrant/.../storage.sqlite` | vector store | retrieval support | collection/model identity | hidden index risk | projection/ownership check | reference only | memory boundary if approved |
| `backups/**` | mixed snapshots | historical recovery | backup timestamp and source | stale duplicates | restore rehearsal only | reference only | no authority |
| MQL5/evidence artifacts | `.mq5`, `.ex5`, JSON/manifest | build/test evidence | source/compiled hashes, run IDs | production and fixture mixing | catalog classification | preserve evidence | RobotCatalog/Tester evidence |
| market source definitions | HTML/JS/Python | formulas and field vocabulary | source/provider labels | generated/build copies | static contract extraction | donor only | Market read models |

## Authority rules

1. Filename presence does not prove active runtime authority.
2. A database is not read, imported, migrated, or selected as canonical by this audit.
3. Every future recovery needs source identity, schema/version, freshness, hash or immutable ID, deduplication rule, failure state, security classification, and AuditLog correlation.
4. Runtime/build/dist copies remain evidence or deployment outputs until a separate deployment inventory proves otherwise.
5. Historical backtests and fixture retries must remain immutable; missing or stale result artifacts are not converted to success.

## Data recovery order

P0: establish active writer and canonical DB binding for tasks, memory, catalog, and AuditLog without mutating data.

P1: reconcile market audit, setup journal, tester manifests, and Robot Catalog evidence into read-only reports.

P2: validate scientific-memory semantics and implement only behind the canonical boundary in a separate approved batch.

P3: consider projections such as vault/Qdrant only after truth ownership and rollback are proven.
