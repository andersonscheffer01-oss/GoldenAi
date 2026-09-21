# M1.7 — Project Memory / Long-Term Memory

**Status**: CONCLUÍDO
**Data**: 2026-09-14
**Agente**: Codex

---

## O que foi feito

Memória de longo prazo por projeto. Jarvis consegue retomar uma tarefa em nova
conversa sem precisar reconstruir todo o histórico.

## Arquivos criados

### Código

- `jarvis_core/memory/v2/project_memory.py` (~600 linhas):
  - `ProjectRecord` — identidade estável do projeto
  - `ProjectState` — estado compacto (máx 1200 chars)
  - `MemoryCandidate` — detector de candidatos a memória
  - `ProjectContext` — contexto completo para resume
  - `HandoffData` — handoff compacto (máx 800 chars)
  - `ProjectResolver` — resolução via entity graph (4-step)
  - `ProjectMemoryManager` — orquestrador principal
  - `SessionLongTermExtractor` — extrai fatos persistentes
  - `HandoffGenerator` — gera handoff a partir de memórias
  - `MemoryCandidateDetector` — detecta sinais de decisão/lição/procedimento

### Testes

- `tests/test_jarvis_memory_v2_m17.py` — 58 testes, todos passando

## Funcionalidades implementadas

| Seção M1.7 | Implementada |
|------------|-------------|
| 1. Auditoria | Sim — mapeou engine, memória, hybrid, consolidação, learning, watcher, context_index |
| 2. Project Memory | Sim — ProjectRecord com entity_id, name, aliases, root_path, status |
| 3. Project Resolution | Sim — resolve via EntityType.PROJECT + entity graph aliases |
| 4. Current State | Sim — ProjectState.to_compact() com budget de 1200 chars |
| 5. Memory Candidates | Sim — detector com sinais de decisão/lição/procedimento/status |
| 6. Session → Long Term | Sim — extract_task_completed, extract_decision, extract_bug, extract_lesson |
| 7. Handoff Automático | Sim — HandoffGenerator gera handoff a partir de memórias |
| 8. Retrieval por Projeto | Sim — hybrid_search com project filter + BOOST_SAME_PROJECT |
| 9. Cross-Project | Sim — get_global_memories para memória sem scope |
| 10. Contexto Codex/OpenCode | Sim — sync_to_second_brain atualiza CURRENT_STATE.md |
| 11. Token Budget | Sim — constants: STATE=1200, MEMORIES=8, HANDOFF=800, DECISIONS=5 |
| 12. Freshness | Sim — CURRENT (<24h), STALE (<7d), UNKNOWN |
| 13. Contradições | Sim — via M1.4 consolidation (superseded/disputed) |
| 14. Privacidade | Sim — SECRET rejeitado, SENSITIVE preservado |
| 15. get_project_context | Sim — retorna ProjectContext com state, memories, decisions, issues, handoff |
| 16. Nova Conversa | Sim — get_project_context("Golden") retoma sem histórico |
| 17. Não Inventar | Sim — UNKNOWN para informação ausente |
| 18. Performance | Sim — usa índices existentes, não faz scan completo |
| 19. Testes | Sim — 58 testes, todos passando |
| 20. Teste Real | Sim — leitura controlada, sem alteração de produção |
| 21. Segundo Cerebro | Sim — sync_to_second_brain compatível com 00_INDEX.md |
| 22. AGENTS.MD | Não alterado — regra M1.6.1 já cobre |
| 23. NÃO TOCAR | Preservado — Desktop, Voice, Radar, MT5 não alterados |
| 24. Documentação | Sim — CURRENT_WORK.md e HANDOFF.md atualizados |
| 25. Aceitação | Sim — teste end-to-end no test_jarvis_memory_v2_m17.py |

## Teste de aceitação (seção 25)

O teste `test_get_project_context` demonstra o fluxo completo:

1. Criar projeto "Golden" com aliases
2. Registrar decisão e issue
3. Chamar `get_project_context("Golden")`
4. Retornar: state, decisions, known_issues, handoff, important_files, token_estimate

Resultado: contexto suficiente para continuar sem leitura completa do repositório.

## Reutilização de infraestrutura existente

- `EntityType.PROJECT` — já existia em types.py
- `project` field em MemoryRecordV2 — já indexado em FTS5
- Hybrid Retrieval com project filter + BOOST_SAME_PROJECT
- Entity Resolution (4-step) — reutilizado para aliases
- WorkingMemory — pode ser usada para session context
- M1.4 consolidation — já lida com contradições/superseded

## Não criado (reutilizado)

- NÃO criou banco paralelo — usa SQLite existente
- NÃO fez Markdown virar fonte canônica
- NÃO salvou tudo indiscriminadamente
- NÃO alterou Desktop V4

## Próximo

- M1.8 — aguardar autorização
- Desktop — aguardar autorização
