# Handoff — Golden Memory M1.1 Obsidian Vault (opencode, 2026-09-13)

## Tarefa
Implementar camada Markdown/Obsidian do Memory Engine V2 (projeção, não BD).

## Status
CONCLUÍDO — PASS. 272 tests + 72 subtests, zero falhas (baseline 229/229).

## Arquitetura
Engine → SQLite canônico → Markdown projeção → vetor derivado.
Single-writer: só o engine via MarkdownMemoryStore (lock/record + atomic).
Vault: `C:\GoldenAI\memory\vault` (env `GOLDEN_MEMORY_VAULT_PATH`).

## Entregas
- `memory/v2/vault.py` (novo): slug/tags/wikilink, YAML próprio, frontmatter,
  folder map, atomic write, policy (SECRET/SENSITIVE/WORKING/SESSION),
  scrub, trust_level, README/index, drift helpers.
- `memory/v2/store.py`: MarkdownMemoryStore funcional (projeção + drift +
  archive + rebuild-safe + human preservation).
- `memory/v2/migrations.py`: schema 2 + `v2_projections` (idempotente).
- `memory/v2/engine.py`: projeção pós-commit degradada, entities/wikilinks,
  `check_drift`, `rebuild_vault(dry_run)`, `vault_status`, `project_legacy`.
- `service.py`: engine com vault default (try/except, nunca derruba).
- `tests/test_jarvis_memory_v2_m11.py`: 43 testes (todos os §55).
- M1.0 atualizados: schema 1→2 (3 asserts) + stub→funcional.
- Doc: `docs/agent-context/GOLDEN_MEMORY_ENGINE_V2.md` (seção M1.1).
- Vault real criado (15 dirs + README + index); 4 memórias TESTE
  (entity/decision/procedural/lesson) projetadas, verificadas e REMOVIDAS.
  DB produção intocado.

## Decisões
SENSITIVE→IGNORED default; SECRET→ERROR security-block; episodic 1
arquivo/dia-prefixado (consolidação diária = futuro); DELETED_LOGICAL
remove projeção gerenciada; `MemorySearchResult` adicionado ao import
do engine (faltava no M1.0).

## Perf
remember 7ms → 21ms c/ projeção (delta 14ms). Voz/fast paths intactos.

## Limitações
Sem FileWatcher/import (M1.6); sem Bases; sem dedup semântico; edição
externa só detectada (DRIFT/CONFLICT).

## Próximo
M1.2 Entities + Relations / Knowledge Graph — somente após autorização.
Receptor: conferir `arquivo:linha` contra código; não tomar como verdade.
