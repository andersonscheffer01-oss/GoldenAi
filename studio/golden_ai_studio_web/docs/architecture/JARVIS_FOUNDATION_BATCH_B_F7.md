# Foundation Batch B: F7 Memory Ownership Audit

## Decision

`DESIGN_ONLY_STOP`. No memory migration, schema change, import, deletion, or
runtime write-path change is safe in this gate.

## Implementations found

| Area | Implementation | Current role | Classification |
|---|---|---|---|
| Legacy memory | `jarvis_core.memory.GoldenMemoryManager` and `Database` | sessions, episodic/semantic records, legacy retrieval and user memory tools | active compatibility writer/reader |
| V2 memory | `GoldenMemoryEngine` + `SQLiteMemoryStore` | canonical-key records, versions, graph, FTS, embeddings, provenance and privacy | canonical target candidate |
| Hybrid retrieval | `jarvis_core.memory.v2.hybrid` | V2 lexical/vector/graph retrieval | derived/read path |
| Project memory | `ProjectMemoryManager` | project state, decisions, issues, lessons and handoffs through V2 | active V2 writer |
| Research learning | `ResearchEngine` / `LearningEngine` | optional researched memory promotion through V2 | active V2 writer when learning is requested |
| Working memory | `GoldenMemoryEngine.working` | TTL-only process memory | volatile, non-persistent |
| Conversation context | Brain/Voice session history and legacy server `CONVERSATIONS` | request/session context | separate volatile compatibility path |
| Embeddings | legacy `EmbeddingService` hook reused by V2 | derived semantic/vector data | derived, provider-local |

## Persistence and ownership

The active `JarvisService` constructs `GoldenMemoryManager` first at
`base_dir/jarvis/golden_memory.db`, then opens `GoldenMemoryEngine` on that
same file. V2 creates only additive `v2_*` tables and indexes; legacy tables
remain intact. The production DesktopCenter base directory points to the
canonical workspace, while tests and standalone callers intentionally use
isolated roots.

The V2 SQLite store is the intended long-term canonical memory boundary. The
Markdown/Obsidian store is only a SQLite-first projection and is never the
source of truth. `LegacyMemoryAdapter` preserves compatibility and does not
perform a data migration.

## Active writers and readers

- Legacy writers: `JarvisService._memory_remember` and legacy session,
  episodic, and semantic managers.
- V2 writers: `GoldenMemoryEngine.remember/update`, project memory helpers,
  and research learning promotion.
- Legacy readers: service memory search/recent endpoints and Brain legacy
  context retrieval.
- V2 readers: V2 hybrid search, project context, research/learning and graph
  diagnostics. Brain uses V2 only when the hybrid mode is explicitly `on`;
  the default remains shadow for comparison.

This means duplication is currently structural and intentional: one physical
database with two schema namespaces and multiple compatible read/write APIs.
It is not evidence that records may be copied or deleted during F7.

## Safe next migration

Before changing the default write path, a later gate must establish record
provenance and parity between legacy and V2, define a one-way compatibility
read adapter, verify privacy/SECRET behavior, and add rollback/reconciliation
receipts. That gate must also settle retention and deletion semantics for
legacy records, embeddings, projections, conversation history and project
memory. No such migration was executed here.

## Safety evidence

- No database was opened for mutation by this audit.
- No memory record, legacy store, vault file, user file, or device registry
  was modified.
- No migration, import, embedding generation, provider call, or full-PC scan
  was performed.
- Existing V2/legacy memory regression suites remain the validation surface;
  the known Windows temporary SQLite cleanup limitation remains documented
  from the foundation baseline.
