# Handoff — Hermes Cache Addendum (opencode, 2026-09-13)

## Tarefa
Addendum read-only de cache (prompt/prefix/KV) do HermesAgent → recomendações Golden Jarvis. NÃO implementar.

## Status
CONCLUÍDO. 2 arquivos criados. Nenhum código funcional alterado.

## Achados-chave
- `i_cache` NÃO EXISTE no Hermes (grep zero hits). Não criar instrução.
- Hermes real: system 3-tier congelado/sessão (`system_prompt.py:605-675`), 4-breakpoint Anthropic (`prompt_caching.py`), `prompt_cache_key` OpenAI (`transports/codex.py:304`), escopo lógico pós-compactação (`prompt_cache_scope.py:132`), skills index estável + corpo on-demand, memória snapshot congelada, telemetria cached tokens. Gemini-CachedContent e Groq: não achados no Hermes.
- Providers (docs oficiais): GROQ YES só p/ 3 modelos (gpt-oss-20b/120b/safeguard); **qwen3.8-27b (VOICE_FAST) NO**; compound-mini UNKNOWN; OLLAMA PARTIAL (KV/residência, `keep_alive`); GEMINI YES (impl.+expl.); OPENROUTER PARTIAL passthrough (troca=cold).
- Golden (`brain.py:157-170`): messages[0] STATIC ok (P0); quebradores: catálogo filtrado/intent, memória/query, history VOICE, user msg. Preço/hora/health fora — correto. Fast paths 0 LLM mantidos.
- Voz ~10.7s não atribuível ao LLM; VOICE_FAST abaixo de todos os mínimos de cache → ganho atual ≈0.

## Decisão M1.1
**NO — CAN WAIT UNTIL P1.4.** Nada de cache bloqueia M1.1. Prep opcional P1.4: serialização canônica, `keep_alive` Ollama, telemetria tokens, `session_id` OpenRouter.

## Classificação
ADOPT: skills-index/memória-snapshot (conceitos). ADAPT: 3-tier, escopo pós-compactação, hash determinístico. INSPIRE: cache_control/prompt_cache_key/response-cache. REJECT: `i_cache`, sidecar-WAL como cache. ALREADY BETTER: P0 + fast paths + SECRET-local.

## Arquivos
- Criado: `docs/agent-context/HERMES_CACHE_ADDENDUM.md`
- Criado: este handoff
- Alterado: `docs/agent-context/HANDOFF.md` (ponteiro)
- Funcionais alterados: NONE

## Git
Verificado: somente leitura + 2 arquivos docs novos. Sem `reset/clean/checkout`.

## Próximo
Aguardar autorização. Receptor: conferir evidências `arquivo:linha` contra código atual; não tratar como verdade absoluta.
