# MASTER CAPABILITY MAP — COMPLETE

**Date:** 2026-09-19
**Status:** COMPLETE
**Functional code modified:** NO

---

## What Was Done

1. Audited and validated 195+ capabilities across 19 categories
2. Corrected classifications:
   - Golden/MT5 modules → CODE_EXISTS_NOT_CONNECTED (not in ToolRegistry, only HTTP API)
   - Voice components → PARTIAL (coded but daemon not started at construction; barge-in/streaming disabled by default)
   - Legacy read_file/write_file/PDF/code tools → LEGACY_AVAILABLE
3. Marked raw shell unsafe items (run_command shell=True, PowerShell URI interpolation, shutil.rmtree, MetaEditor PS escaping) → UNSAFE_DO_NOT_MIGRATE
4. Created canonical map: `docs/agent-context/MASTER_CAPABILITY_MAP.md`

---

## Counts (Recalculated From Matrix Rows, Unique)

| Status | Count |
|--------|-------|
| WORKING_NOW | 83 |
| CONNECTED_NOT_RUNTIME_TESTED | 0 |
| CODE_EXISTS_NOT_CONNECTED | 28 |
| LEGACY_AVAILABLE | 15 |
| PARTIAL | 13 |
| MISSING | 43 |
| UNSAFE_DO_NOT_MIGRATE | 0 |
| OBSOLETE | 0 |
| TOTAL_UNIQUE_CAPABILITIES | 182 |

Check: sum = 182 = TOTAL_UNIQUE_CAPABILITIES.

Cross-listed (counted once, kept as cross-refs):
- Lixeira (CAT 6) → counted in CAT 2 (consultar/esvaziar)
- Risk Engine (CAT 19) → counted in CAT 12

Normalization: OpenCode Integration PLANNED→MISSING; 4 UNSAFE items are audit entries, not capability rows.

- ToolRegistry: 64 tools (incl. recycle_bin_status, empty_recycle_bin)
- Tests: 126 passed / 0 failed

---

## Canonical Map

```
docs/agent-context/MASTER_CAPABILITY_MAP.md
```

Contains: architecture invariants, status definitions, inconsistencies fixed, raw shell safety audit, 19-category capability matrix, final counts, readiness assessment, implementation phases A–E.

---

## Next Implementation Phase

**Phase A — Essential PC Control:**
- read_file / write_file (migrate from server_agent.py, with path validation)
- clipboard read/write
- GPU monitoring (connect jarvis_desktop/gpu.py)
- Temperatures
- Sleep/hibernate

Then **Phase B — Golden/MT5 Integration** (register tools, fill Route.MT5/TRADING tuples, orders with confirmation).

---

## M1.5.1B — Web Research Multi-Provider Revalidation

**Date:** 2026-09-20
**Status:** PASS arquitetural/focado; suíte global atual não comparável por testes novos/ambientais fora do escopo M1.5.1B.
**Functional code modified:** YES, apenas núcleo Memory V2/research/service/testes focados; sem iniciar M1.6.

Resumo:
- `JARVIS_RESEARCH_PROVIDER=auto` usa fallback determinístico Tavily → Groq Web → Brave.
- Chaves suportadas: `TAVILY_API_KEY`, `GROQ_API_KEY`, `BRAVE_SEARCH_API_KEY`.
- Ambiente atual sem chaves reais: health retorna `missing_key`; smokes reais opcionais pulam sem inventar segredo.
- Fluxos `web_research` e `web_research_learn` preservam `SafeHTTPFetcher`, SSRF block, prompt injection como DATA, provenance e escrita de memória somente no caminho learn elegível.

Validação atual:
- Focados M1.5.1B/M1.5.1/M1.5 hardening/orchestrator: 68 passed, 3 skipped, 56 subtests passed.
- Compatibilidade market prompt: 1 passed.
- Suíte global atual: 1411 passed, 24 skipped, 44 failed, 4 errors, 89 subtests passed; falhas em testes/fixtures/dependências ambientais fora do escopo M1.5.1B.

Próximo: aguardar autorização; não iniciar M1.6.
