# HANDOFF — Master Capability Map Complete

**From:** Previous agent (capability audit)
**To:** Next agent
**Date:** 2026-09-19
**Phase:** Capability Map — COMPLETE

---

## Status: COMPLETE

Canonical Master Capability Map created and validated. No functional code modified.

---

## Deliverables

1. **Canonical map:** `docs/agent-context/MASTER_CAPABILITY_MAP.md`
2. **Current work:** `docs/agent-context/CURRENT_WORK.md`

---

## Key Facts for Next Agent

- **Single Jarvis Core** architecture — no duplicate Brain/JarvisService/ModelRouter/ToolRegistry/SecurityManager
- ToolRegistry has **64 tools** (incl. recycle_bin_status, empty_recycle_bin)
- Golden/MT5 modules: CODE_EXISTS_NOT_CONNECTED — exist in code, only reachable via server_agent.py HTTP API
- Voice: PARTIAL — fully coded, daemon requires explicit start(); barge-in (JARVIS_BARGE_IN=0) and streaming (JARVIS_STREAMING_VOICE=0) disabled by default
- Legacy run_command (shell=True + LLM input): UNSAFE_DO_NOT_MIGRATE
- PowerShell URI interpolation in voice_service.py: UNSAFE_DO_NOT_MIGRATE
- Security confirmation flow: fail-closed FIXED (approved field checked, deny_confirmation added)
- Tests: 126 passed / 0 failed

---

## Architecture Invariants (do not violate)

```
1 JarvisService | 1 ToolRegistry (64 tools) | 1 SecurityManager
1 Brain | 1 ModelRouter | 1 Orchestrator | 1 Gateway
```

- Shared classifier `is_conceptual_query()` in `orchestrator/orchestrator.py` is single source of truth
- `Tool.confirmation` is the attribute name (not `confirmation_required`)
- DataClassification.SECRET stays local-only (Ollama)
- Never use real destructive actions in tests

---

## Next Steps

1. **Phase A — Essential PC Control:** read_file/write_file (migrate with path validation), clipboard, GPU, temperatures, sleep/hibernate
2. **Phase B — Golden/MT5 Integration:** register tools in ToolRegistry, fill Route.MT5/TRADING tuples, orders Risk.CRITICAL + confirmation=True
3. See full phase plan in `docs/agent-context/MASTER_CAPABILITY_MAP.md` (IMPLEMENTATION PHASES section)

---

## Modification Policy

Não alterar componentes validados SEM necessidade.
Mudanças necessárias para a fase atual são permitidas,
desde que preservem a arquitetura, segurança e testes.

Manter absolutamente (nunca reconstruir):

```
1 JarvisService | 1 ToolRegistry | 1 SecurityManager
1 Brain | 1 ModelRouter | 1 Gateway
```

Registrar novas ferramentas no ToolRegistry EXISTENTE é permitido e esperado
(Phase A/B farão isso). Nunca criar um segundo ToolRegistry ou segundo Jarvis.

---

## Addendum — Golden Memory M1.5.1B

**Date:** 2026-09-20
**Status:** PASS arquitetural/focado; aguardar autorização, não iniciar M1.6.

M1.5.1B implementou e revalidou pesquisa web multi-provider com
`JARVIS_RESEARCH_PROVIDER=auto`, fallback Tavily → Groq Web → Brave e chaves
`TAVILY_API_KEY`, `GROQ_API_KEY`, `BRAVE_SEARCH_API_KEY`. O ambiente atual não
tem chaves configuradas; health retorna `missing_key` e smokes reais opcionais
são pulados com segurança.

Validação focada atual: 68 passed, 3 skipped, 56 subtests passed. Compatibilidade
market prompt: 1 passed. A suíte global atual não está comparável ao baseline
por testes novos/ambientais fora do escopo M1.5.1B.
