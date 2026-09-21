# M1.7.1 — Project Memory Runtime Wiring + Real Acceptance

**Status**: CONCLUÍDO
**Data**: 2026-09-14
**Agente**: Codex

---

## O que foi feito

ProjectMemoryManager integrado no runtime do Golden Jarvis. Brain agora
detecta intenção de projeto e injeta contexto compacto no prompt do LLM.

## Mudanças

### service.py (L155-157)
```python
from .memory.v2.project_memory import ProjectMemoryManager
self.project_memory = ProjectMemoryManager(self.memory_v2)
```
Após criar `memory_v2`, instancia `ProjectMemoryManager`.

### brain.py
- `__init__`: novo param `project_memory`
- `_needs_project_context()`: regex detecta continue/retome/voltar ao/onde paramos/status/projeto/decisões/issues/handoff/próximo passo
- `_resolve_project_from_query()`: resolve nome/alias do projeto a partir do texto
- `_get_project_context()`: retorna `[PROJECT_CONTEXT]...[/PROJECT_CONTEXT]` compacto
- `_get_memory_context()`: append project context após memória geral
- `get_brain()`: novo param `project_memory`, busca de `DESKTOP_CENTER.service.project_memory`

### project_memory.py
- `sync_to_second_brain()`: agora atualiza CURRENT_STATE + DECISIONS + KNOWN_ISSUES + HANDOFF

## Fluxo

```
usuário: "continue o Golden"
    ↓
_needs_project_context("continue o Golden") → True
    ↓
_resolve_project_from_query("continue o Golden") → "Golden"
    ↓
get_project_context("Golden") → ProjectContext compacto
    ↓
[PROJECT_CONTEXT] injectado no prompt do LLM
    ↓
Brain responde com contexto do projeto
```

## Fast path preservado

```
usuário: "que horas são?"
    ↓
_needs_project_context("que horas são?") → False
    ↓
NENHUM custo de Project Memory
```

## Testes (29)

- Intent detection (9): continue/retome/onde paramos/status/decisões/voltar ao/trivial/empty/weather
- Resolver from query (5): golden/goldenai/jarvis alias/not found/trivial
- Ambiguity (1): dois projetos匹配 → não adivinha
- Brain integration (3): context injected/trivial no context/budget
- Second Brain sync (2): creates files/no duplicate
- Candidate signals (3): negative promotes/neutral defers/casual rejected
- Privacy (1): SECRET not in context
- Performance (3): resolution <100ms, context <500ms, chars budget
- No retrieval tax (1): trivial não executa
- Session end (1): records + handoffs

## NÃO TOCAR

Desktop V4, Voice, Radar, MT5, Research Providers, SecurityManager — preservados.

## Próximo

M1.8 — aguardar autorização.
