# JARVIS / GOLDEN Memory Archaeology

Static comparison of memory implementations found under `C:\GoldenAI`. No database was modified and no runtime memory operation was executed.

## Canonical Jarvis memory

`jarvis_core/memory/manager.py` provides `GoldenMemoryManager` with session, episodic, semantic, retrieval, embedding, explicit remember/search/recent/deactivate operations, size/secret/binary filtering, and AuditLog integration. `memory/retrieval.py` combines semantic, importance, and recency signals, has a lexical fallback, limits injected context, and marks retrieved content untrusted.

Memory V2 adds SQLite truth, hybrid retrieval, graph/entities, research/learning/project memory, additive migrations, and a vault/Obsidian projection. The vault is not truth. `JarvisService`, `Brain`, the boundary, registry tools, and `/api/jarvis/memory/*` routes establish the current authority and security posture.

## Legacy scientific memory

`core/memory/service.py` and its repository model knowledge items, typed evidence/source metadata, revisions, explicit conflicts, links to experiments, supersession, optional Qdrant, and local embeddings. `app/modules/memory_chat.py` exposes user/scientific memory intent, topic summaries, related experiments, and provenance fields such as evidence level, source type, source id/location, confidence, tags, metadata, and `supersedes_id`.

These semantics are the most valuable unique legacy contribution. They should be adapted behind the canonical Jarvis boundary, not exposed as a second `MemoryService` or direct database authority.

## Other memory paths

- `app/modules/browser.py` contains older vector-store wrappers. Classify as REFERENCE_ONLY until ownership and data migration are proven.
- `jarvis/backend/app/models.py` and `chat_service.py` persist user-scoped conversations/messages with model, token, latency, and status fields. This is auxiliary conversation history, not long-term Jarvis semantic memory.
- Vault and Obsidian files are projections and may contain useful recoverable context, but imports require provenance and reconciliation.

## Recovery contract

| Legacy semantic | Jarvis disposition | Required guard |
|---|---|---|
| Evidence level/source | ADAPT | typed schema and provenance receipt |
| Revision history | ADAPT | append-only revision identity and supersession |
| Conflict detection | ADAPT | explicit conflict state, never silent overwrite |
| Experiment links | ADAPT | stable experiment/artifact identifiers |
| Claim-to-hypothesis links | ADAPT | source/claim provenance and confidence |
| Qdrant/vector wrapper | REFERENCE_ONLY | no new authority or hidden index |
| Auxiliary conversations | PORT selectively | user scope, retention, and security review |
| Vault projection | KEEP AS PROJECTION | SQLite/Jarvis memory remains truth |

## Decision

MEMORY_RECOVERY_DECISION: ADAPT_GOLDEN_SCIENTIFIC_SEMANTICS_INTO_CANONICAL_JARVIS_MEMORY.

Do not reopen the already-completed canonical memory convergence phases. The next safe work, after B1 checkpoint, is a design and migration gate for typed evidence/conflict/revision/experiment links with explicit data inventory and rollback proof.
