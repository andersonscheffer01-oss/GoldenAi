# JARVIS / GOLDEN — Database Authority Map

**Mode:** read-only inventory; no database was opened in write mode and no migration was performed.

## Observed database families

The tree contains canonical candidates, legacy runtime copies, backups, temporary test databases and donor/research databases. Representative paths include:

| Path | Observed role | Authority |
|---|---|---|
| `studio/golden_ai_studio_web/jarvis/golden_tasks.db` | Jarvis task/run/approval/mission store, schema-v5 history | canonical task store |
| `studio/golden_ai_studio_web/jarvis/robot_catalog.db` | robot catalog/provenance/associations | canonical catalog store |
| `studio/golden_ai_studio_web/jarvis/golden_memory.db` | Jarvis memory runtime | canonical memory family, exact active binding requires runtime check |
| `studio/golden_ai_studio_web/golden_runtime.db` | Golden Studio runtime/legacy state | legacy/runtime, not task authority |
| root `golden_runtime.db` | working/runtime copy | legacy/runtime, not task authority |
| `jarvis/golden_runtime.db`, `jarvis/golden_memory.db` | auxiliary runtime copies | legacy/non-active unless a service explicitly binds them |
| `data/golden_ai.db`, `data/jarvis/...` | historical/data stores | domain/history; no automatic authority |
| `backups/**`, `work/**`, donor trees | backup, test, worktree or reference data | never active authority |

The raw repository contains more database files than the seven files in the stale checkpoint because backups, temporary test directories and work copies are present. File presence is not authority evidence.

## Canonical ownership

`TaskDatabase`, `TaskManager`, `BackgroundTaskScheduler`, approvals, mission checkpoints, action receipts and Control Center projections must use the configured canonical Jarvis task DB. Additive migrations are governed by the existing schema path; legacy v1/runtime DBs must not be merged or deleted opportunistically.

`RobotCatalog` and MQL5 evidence contracts own robot identity, source/compiled artifact relationships, hashes and associations. Historical tester/backtest artifacts remain immutable and must be associated explicitly by IDs/hashes rather than filename proximity.

Memory has a Jarvis-owned boundary and multiple historical files. The active binding must be confirmed by service configuration/runtime read before any future data operation; this audit makes no migration claim.

## Write risks

Legacy server routes can write journal/setup JSONL, market audit JSONL, runtime state and imported history. The dashboard can reach broker-side effects, which are outside ordinary database authority. A canonical integration must separate read models from mutation commands, record provenance and audit receipts, and preserve unknown/unresolved historical artifacts.

## Required future gate

Before any consolidation: enumerate service bindings, lock the target path, take a read-only schema snapshot, define retention/immutability, reconcile IDs and hashes, and obtain a dedicated data-governance authorization. This audit does not perform that work.
