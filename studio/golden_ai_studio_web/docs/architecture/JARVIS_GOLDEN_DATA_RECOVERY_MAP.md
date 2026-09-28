# JARVIS / GOLDEN Data Recovery Map

Static inventory of data assets that may be at risk if legacy paths are retired. Presence does not establish authority. No database or JSONL file was modified.

## Database families

| Asset family | Observed path pattern | Likely owner/use | Recovery concern |
|---|---|---|---|
| Task state | `studio/golden_ai_studio_web/jarvis/golden_tasks.db` | canonical task persistence | retain identity, receipts, and lifecycle |
| Robot catalog | `studio/golden_ai_studio_web/jarvis/robot_catalog.db` | catalog/provenance | retain robot, run, artifact, association links |
| Jarvis memory | `studio/golden_ai_studio_web/jarvis/golden_memory.db` | canonical memory family | verify active binding before migration |
| Runtime/audit copies | `golden_runtime.db`, `jarvis/golden_runtime.db`, studio copies | legacy/runtime audit or mixed data | do not merge by filename alone |
| Auxiliary backend | `jarvis/backend/app` SQLAlchemy database family | users, conversations, messages, devices | scoped import and privacy review |
| Backups/work/tests | `backups/**`, `work/**`, test/reference stores | non-authoritative snapshots | preserve as evidence, never auto-promote |

## JSONL and artifacts

| Data | Path | Risk if retired |
|---|---|---|
| Trade journal | `data/trade_journal/journal_*.jsonl` | trade/setup history and feedback context |
| Setup database | `data/setup_database/setups.jsonl` | setup records and scoring history |
| Market AI audit | `data/market_ai_audit.jsonl` | analysis/audit history |
| Backtest reports | `config/backtest_results/**` | historical evidence and comparison artifacts |
| Robot/tester evidence | catalog/fixture/report paths under studio | provenance chain break |
| Vault projection | Jarvis/Obsidian vault paths | decisions and project context if unreconciled |

## Recovery rules

1. Inventory stable identifiers, timestamps, source, schema version, and owner before import.
2. Preserve original records and hashes; imports must be append-only or explicitly versioned.
3. Mark stale, synthetic, replayed, or unverified evidence clearly.
4. Reconcile duplicate DB copies by provenance and active code binding, never by newest file time alone.
5. Route imported data through Jarvis security, memory, catalog, or task boundaries and record AuditLog receipts.
6. Keep generated `build/`, `dist/`, logs, fixtures, and runtime copies out of source authority.

## Data-at-risk summary

UNIQUE_LEGACY_DATA_FOUND: scientific knowledge/revisions/conflicts, experiment links, trade journal/setup records, market AI audit, robot/evidence records, task/audit receipts, auxiliary conversations, and vault projections.

DATA_AT_RISK_IF_LEGACY_RETIRED: YES, pending explicit export/reconciliation gates.

No retirement, migration, compaction, or database mutation is authorized by this archaeology report.
