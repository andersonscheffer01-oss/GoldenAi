# Handoff — M1.2 Knowledge Graph (opencode, 2026-09-13)

## Tarefa
Evoluir entities/relations V2 p/ knowledge graph canônico + Obsidian.

## Status
CONCLUÍDO — PASS. 326 tests + 72 subtests, zero falhas (baseline 272/272).

## Entregas
- `v2/graph.py` (novo): catálogo 19 tipos (directed/symmetric + inversa
  derivada + self bloqueado), normalização conservadora, trust 4 tiers,
  contratos GraphNode/Edge/Neighbor/Path/Result/Resolution.
- `v2/types.py`: +CONCEPT/COMPONENT/DEVICE (sem DECISION/PROCEDURE);
  +MERGED/DISPUTED status; +DOCUMENTED/TEST_CONFIRMED basis.
- `v2/record.py`: EntityV2/RelationV2 com provenance, version, metadata.
- `v2/migrations.py`: schema 3 (cols + versions + memory_entities +
  relation_evidence + backfill; idempotente).
- `v2/store.py` + `v2/graph_store.py` (mixin): resolve (nunca chuta),
  merge transacional, links memória↔entidade, evidências, neighbors,
  alias_conflicts, orphans, counts, validate_graph.
- `v2/engine.py`: Graph API (neighbors/traverse/shortest/subgraph),
  privacy (só sobe; clearance filter), supersede, archive/merge,
  projeção c/ labels + inversas + Memories, entity index, stats.
- `v2/vault.py`: related rotulado, trust, `## Memories`, Entity Index.
- `service.py`: DEV graph {entities, relations, integrity}.
- `tests/test_jarvis_memory_v2_m12.py`: 54 testes (todos os §57).
- M1.0/M1.1: só asserts schema 2→3. Doc V2 atualizada (seção M1.2).
- Smoke real: dataset TESTE no vault oficial, verificado e REMOVIDO.
  DB produção intacto; 4 legadas intactas (suíte M1.0 verde).

## Decisões
Sem GraphRAG/FTS5/hybrid/dedup/auto-memory/LLM-livre/FileWatcher/Bases
(M1.3+). Grafo fora do prompt de voz. Ciclo ≠ erro. Órfã ≠ delete.

## Perf
resolve 2ms, create 42ms, neighbors 4ms, depth2 17ms, path 34ms,
subgraph 16ms (local, texto-only).

## Limites
Import Obsidian (M1.6); consolidação semântica e auto-memory futuras.

## Próximo
M1.3 Hybrid Retrieval + FTS5 + Graph-assisted Retrieval — só c/ autorização.
Receptor: conferir `arquivo:linha`; não tomar como verdade absoluta.
