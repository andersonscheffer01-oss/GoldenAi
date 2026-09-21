# Handoff — Golden Memory M1.0 Foundation (2026-09-13, Opencode)

## Estado

**PASS.** Fundação V2 existe, versionada, testada (30 novos), legado 100%
intocado (DB real: 4/4 memórias, schema v1, dim 768). Suíte **229/229**,
72 subtests, zero regressão P0–P1.3.

## Auditoria do legado (lido, não assumido)

- `jarvis_core/memory/`: manager (RLock, audit, `_unsafe_content_reason`),
  models (3 types, category, 8 sources, record, status), database
  (WAL, schema v1, sessions/memories/embeddings + 6 índices),
  embeddings (nomic-embed-text 768, fallback lexical degradado explícito),
  episodic (filtro trivial), semantic (dedup exato + cosine 0,92),
  session, retrieval (vector→lexical, pesos 0,5/0,3/0,2, top 8/20).
- Integrações: Brain `get_context` (banner untrusted), tools
  memory_search/remember/recent, router MEMORY/GENERAL. Voice não toca
  memória direta (history em processo). Privacy: filtro de segredo no
  write + SECRET nunca cloud. Testes: 13 memória + hardening.

## Criado (tudo novo em `jarvis_core/memory/v2/`)

- `types.py`: 8 kinds, ConfidenceBasis, RecordStatus, SourceType(9),
  EntityType(11), RelationType(9), MatchSource, EmbeddingState.
- `record.py`: MemoryRecordV2 (22 campos §6 + hash/canonical),
  EntityV2, RelationV2, MemoryCandidate, MemorySearchResult,
  MemorySecurityError/ValidationError. Privacy = DataClassification.
- `migrations.py`: v1, idempotente, mesmo arquivo, prefixo `v2_`.
- `store.py`: MemoryStore ABC + SQLiteMemoryStore + Markdown stub M1.1.
- `engine.py`: GoldenMemoryEngine (remember/recall/search/get/update/
  archive/list_versions/upsert_entity/link_entities/get_relations) +
  WorkingMemory TTL + embed degradado + audit hook + status().
- `legacy_adapter.py`: leitura legada como V2, sem migração física.
- `service.py` (+2 blocos): `memory_v2` eager com fallback None +
  `engine_v2` no memory/status (DEV mínimo).

## Comportamentos-chave validados

Idempotência (canonical/entity/relation), versionamento com snapshot,
soft-delete, SECRET recusado (conteúdo, metadata-key, privacy),
rollback em relação inválida, concorrência 8 threads, TTL, lexical +
coseno com dimensão validada, perf <10 ms/op textual.

## Ao vivo

Servidor reiniciado: READY, legado intacto, `engine_v2: V2 READY,
schema 1, pending 0`. Nenhum dado existente apagado/movido.

## Limitações / próximo

Sem auto-memory (só fundação); sem Obsidian/GraphRAG/FileWatcher;
ranking híbrido futuro; `LOW_CONFIDENCE` falado segue sem prova;
janela 6 s. NEXT: M1.1 Obsidian vault, só com autorização.
