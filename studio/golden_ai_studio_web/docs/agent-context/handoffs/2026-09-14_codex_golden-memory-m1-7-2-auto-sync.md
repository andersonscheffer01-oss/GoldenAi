---
date: 2026-09-14
from: codex
to: opencode/freebuff
milestone: M1.7.2
status: CONCLUÍDO
scope: Golden AI — Auto Second Brain Sync + Dynamic Project Resolution
files_changed:
  - jarvis_core/memory/v2/project_memory.py
  - jarvis_core/brain.py
  - tests/test_jarvis_memory_v2_m172.py
  - docs/agent-context/CURRENT_WORK.md
  - docs/agent-context/HANDOFF.md
tests: 26/26 pass, 160/160 full suite
---

# M1.7.2 — Auto Second Brain Sync + Dynamic Project Resolution

## O que foi feito

### 1. Dirty Flag + Auto Sync (`project_memory.py`)

- `_dirty_projects: set` — rastreia projetos com alterações canônicas
- `_sync_content_hashes: Dict[str, str]` — hash SHA256 do conteúdo anterior
- `_mark_dirty(project)` — marca projeto como alterado
- `_sync_if_dirty()` — sincroniza todos os dirty projects, coleta erros
- `_content_hash(text)` — hash determinístico para comparação
- `_write_if_changed(path, content)` — write-if-changed: skip se hash idêntico

**Mutation methods wired**: `record_decision`, `record_issue`, `record_lesson`, `update_project_state`, `remember` (DECISION/LESSON), `on_session_end`

### 2. Write-If-Changed (`sync_to_second_brain`)

- Antes: sempre escrevia os 4 arquivos (CURRENT_STATE, DECISIONS, KNOWN_ISSUES, HANDOFF)
- Agora: compara hash SHA256 antes de escrever; skip se conteúdo idêntico
- Result inclui `files_updated` e `skipped`
- Arquivos vazios: deleta se existem (decisions/issues sem registros)

### 3. Dynamic Project Resolution (`brain.py`)

- **ANTES**: hardcoded list `known = [("golden", ["golden", "goldenai"...]), ...]`
- **AGORA**: itera `list_projects()` e matcha aliases dinamicamente
- Novos projetos funcionam sem alteração de código
- AMBIGUOUS: múltiplos matches → retorna string "AMBIGUOUS" (não None)

### 4. Fast Path + Failure Isolation

- Trivial messages (ok, obrigado, etc.) → zero tax, sem sync
- Sync failure: capturado por projeto, não quebra memória canônica
- `on_session_end`: chama `_sync_if_dirty()` após salvar handoff

## Testes (26)

```
DirtyFlagCase (7):         initial_clean, mark_dirty_on_state_change/decision/issue/lesson, session_end, no_dirty_on_trivial
AutoSyncCase (4):          session_end_triggers_sync, trivial_no_sync, sync_if_dirty, sync_failure_isolation
WriteIfChangedCase (3):    first_write, same_content_skips, different_content_writes
DebounceCoalescingCase (1): multiple_mutations_one_sync
WatcherNoLoopCase (1):     sync_writes_deduped
DynamicResolutionCase (3): project_resolved, alias_resolved, new_project_works
AmbiguityCase (3):         ambiguous, not_found, resolved
FailureIsolationCase (1):  sync_failure_preserves_memory
FastPathCase (1):          trivial_no_project_context
PerformanceCase (2):       sync_ms (<500ms), noop_sync_skips (<200ms)
```

## Full suite

```
160 passed (M1.7.2=26 + M1.7.1=29 + M1.7=58 + M1.6=30 + M1.6.1=17)
```

## Notas para próximo agente

- `EntityType.PROJECT` já existe em `types.py`
- `GraphNode` tem `entity_id` (não `id`); `EntityV2` tem `id`
- `normalize_name()` lowercase — case-insensitive matching
- `SECRET_PATTERNS` regex: `api[_-]?key\s*[:=]` (sem espaço entre api e key)
- `DataClassification` está em `jarvis_core.orchestrator.models`
- Vault: `C:\GoldenAI\vault\Segundo Cerebro\` (NÃO em `memory\vault`)
- Segundo Cerebro NÃO é fonte canônica — é projeção compacta
- Desktop V4 NÃO aprovado — não tocar
- Próximo milestone: M1.8 (quando autorizado)
