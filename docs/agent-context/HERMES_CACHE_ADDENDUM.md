# HERMES CACHE ADDENDUM — Prompt / Prefix / KV Cache Audit

> READ-ONLY. Nada implementado, nada alterado em código funcional.
> Data: 2026-09-13. Autor: opencode. Ref: `C:\GoldenAI\references\HermesAgent`.
> Baseline Golden: 229/229 tests, 72 subtests, M1.0 PASS, P0–P1.3 PASS, Hermes Read-Only Audit PASS.

---

## 1. I_CACHE — veredito

**I_CACHE FOUND: NO.** Grep `\bi_cache\b` em `references/HermesAgent` = zero hits (verificado 2026-09-13). `icache` = zero hits.
Símbolos reais próximos: `agent/prompt_caching.py`, `agent/prompt_cache_boundary.py` (`register_stable_prefix`/`find_stable_prefix`), `agent/prompt_cache_scope.py`, `cache_control`, `prompt_cache_key` (`agent/transports/codex.py:304`), `_SKILLS_PROMPT_CACHE` (`agent/prompt_builder.py:1353`). **Não criar instrução `i_cache`. Não existe.**

## 2. Hermes — arquitetura real de cache

Três arquivos centrais (verificados no disco):
- `agent/prompt_caching.py:1-6` — estratégia Anthropic, 4 breakpoints default (prefixo estático + fim do system + últimas 2 não-system), TTL único 5m/1h.
- `agent/prompt_cache_boundary.py:1-6,26,39` — prefixos estáveis declarados pelo builder (`register_stable_prefix`/`find_stable_prefix`).
- `agent/prompt_cache_scope.py:132,142` — escopo lógico `gwk_<hash>` ou raiz de linhagem de compressão, memoizado; sobrevive a rotação de session_id.

Montagem (`agent/system_prompt.py:605-675`, `build_system_prompt()` em `:666`):
`stable + \n\n + context + \n\n + volatile`. Construído **1x por sessão**, reusado (`agent/agent_init.py:588` `_cached_system_prompt`); só compressão dispara rebuild. Doc no cabeçalho (`system_prompt.py:1-4`).

| Bloco Hermes | Builder | Estável? |
|---|---|---|
| Stable tier (SOUL.md-or-default, help, guidance, Alibaba identity, coding brief) | `system_prompt.py:616-636,488-494` | Estável por sessão. Rebuild em troca de modelo (`_model_gate` `:40,516,520`) |
| Context tier (system_message do caller, AGENTS.md/CLAUDE.md, snapshot workspace pinado por sessão+cwd) | `system_prompt.py:637-648,541-563` | Estável por sessão, muda entre sessões |
| Volatile tier (skills index primeiro, `_memory_parts`, timestamp, env hints) | `system_prompt.py:649-663` | Volátil por desenho, mas **congelado por sessão** (built once) |
| Tools | `model_tools.py:1-7`, `agent_init.py:1062-1067`, `toolsets.py:295,356-377` (sorted), enviado todo turno `turn_request_assembly.py:191-216` | Estável por sessão; troca mid-session proibida (`gateway/run_turn.py:1757`, `gateway/run_agent_cache.py:509`, `AGENTS.md:20` "prompt caching is sacred") |
| Skills | índice via `prompt_builder.py:1345,1415`, LRU `_SKILLS_PROMPT_CACHE` com chave `(dirs, sorted tools/toolsets, platform, disabled, categories)` `:1353-1363`, corpos via tool `skill_view` on-demand | Índice estável por sessão; corpo = tool result do turno |
| Memória | SOUL→stable; MEMORY/USER→volatile congelado (`system_prompt.py:460-469`); writes mid-session vão ao disco mas **não mudam o prompt** (`tools/memory_tool.py:4`, docs `which-file-does-what.md:34`, `memory.md:57`); Honcho injeta em **user message**, não system (`plugins/memory/honcho/README.md:41`) | Snapshot congelado no início da sessão |
| User message | histórico + input novo; scaffolds registram boundary (`skill_commands.py:64,280`, `cron/scheduler_prompt.py:275`) | Cauda volátil; tudo acima = prefix hit |

**Volátil no início? Não.** Hermes congela system inteiro por sessão e isola cauda volátil no fim (user message + últimas mensagens). Timestamp/memória/plugins ficam no volatile band mas congelados — não re-render por turno. Anti-pattern testado: `tests/gateway/test_session.py:122` (id volátil por mensagem destruiria cache).

## 3. Tools / skills / memory / snapshot / compaction

- **Tools:** catálogo completo todo turno (NÃO lazy para o modelo; lazy só imports Python e corpos de skill). Ordem determinística: `toolsets.py:295,377` sorted; hash `codex.py:319-322` `sorted by name + json.dumps(sort_keys=True)`. Canonicalização de tool calls por turno (`turn_request_assembly.py:174-179`).
- **Skills:** índice (nomes+descrições) injetado; corpo completo só via `skill_view`. Ajuda cache porque o índice é estável e o corpo pesado vira tool result (fora do prefixo). Invalidação explícita (`clear_skills_system_prompt_cache` em `conversation_loop.py:685`, `skill_manager_tool.py:717`).
- **Memory:** system só recebe snapshot congelado; retrieval externo (Honcho) vai para user message com fence `<memory-context>`. O que entra no system: SOUL (estável) + MEMORY/USER snapshot (volátil-congelado). O que entra no turno: memória externa, tool results.
- **Snapshot/sidecar:** "sidecar" no Hermes = SQLite WAL (`hermes_state_dbfile.py:127`) e coluna `api_content` (`hermes_state_messages.py:289,636,661`), NÃO prompt sidecar. Snapshot de prompt = in-memory (`_cached_system_prompt`, `_plugin_system_prompt_sections_snapshot` `:112-118`) + prompt persistido no DB; tier estático reconstruído via `reconstruct_static_prefix` (`system_prompt.py:699-725`). Efeito em cache: preserva identidade de objeto em igualdade de bytes.
- **Compaction:** `hermes_state_compression.py` = linhagem/locks, não bytes. Rebuild real em `conversation_compression.py:2798-2837` (`_rebuild_system_prompt_at_boundary`: invalida → refresh tools → ALWAYS rebuild; se byte-equal mantém identidade do objeto para backends que chaveiam por identidade). Escopo lógico sobrevive à rotação (`codex.py:543-546,605-606` preferem `cache_scope_id`; `codex.py:546` "Keeps the cache warm across compression rotation"). In-place compaction (`agent_init.py:1483` default True) evita rotação. Histórico abaixo do boundary de summary quebra prefixo por definição; system estável minimiza dano.

## 4. Provider-native no Hermes (com evidência / não achado)

- **Anthropic `cache_control`: SIM** (`prompt_caching.py:273` `apply_anthropic_cache_control`; `anthropic_message_convert.py`; `agent_runtime_helpers.py:1477` policy; envelope vs native layout; TTL Qwen 1h→5m clamp, MiniMax-M2 off).
- **OpenAI `prompt_cache_key` (+ retention): SIM** (`providers/base.py:78,81`; `transports/codex.py:304-325` hash `pck_<sha256[:24]>`, `:608-613` wire, `:670` xAI extra_body; `chat_completions.py:70,109`; `prompt_cache_scope.py` escopo estável; `24h` para `api.meta.ai`/Bedrock Mantle).
- **Bedrock Converse `cachePoint`: SIM** (`bedrock_adapter.py:426-449,482-525,890-894`; allowlist + self-heal).
- **xAI `x-grok-conv-id`: SIM** (`codex.py:658`).
- **OpenRouter: parcial** — envelope `cache_control` honrado (`prompt_caching.py:23-32`), roteamento sticky `session_id` (`opencode_affinity.py:59`), telemetria `cached_tokens` (`chat_completions.py:572-580`), **response cache** separado (`config_defaults.py:644-646` TTL 300s, `auxiliary_client.py:849-868`).
- **Gemini CachedContent: NÃO ACHADO** como mecanismo de request; só telemetria `cachedContentTokenCount` (`gemini_native_adapter.py:442`). **Groq: NÃO ACHADO** (nenhum header/marker).

## 5. Providers do Golden — documentação oficial (2026-09-13)

| Provider | Cache | Tipo | Modelos | Mínimo | TTL | Telemetria | Preço | Latência | Privacidade |
|---|---|---|---|---|---|---|---|---|---|
| **GROQ** | YES | automático | **só 3**: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `openai/gpt-oss-safeguard-20b` ([docs](https://console.groq.com/docs/prompt-caching)) | 128–1024 toks | 2h sem uso | `prompt_tokens_details.cached_tokens` | 50% desc. input cacheado; sem taxa extra | reduzida em hit | volátil, expira auto, nunca entre orgs |
| **QWEN qwen/qwen3-8b-27b @Groq (VOICE_FAST)** | **NO** | — | existe ([models](https://console.groq.com/docs/models): 450 t/s, 131k ctx) mas **fora da lista de caching** | NOT DOCUMENTED | NOT DOCUMENTED | `cached_tokens`=0 até listarem | sem desconto assumível | sem ganho assumível | garantia de plataforma volátil vale |
| **COMPOUND-MINI (fallback)** | **UNKNOWN / NOT DOCUMENTED** | sistema agêntico (Llama 3.3 70B + GPT-OSS 120B, 1 tool call/req, sem custom tools, [docs](https://console.groq.com/docs/compound/systems/compound-mini)) | fora da lista | NOT DOCUMENTED | NOT DOCUMENTED | `usage_breakdown.models[]`, sem `cached_tokens` doc. | depende dos modelos base; sem desconto assumível | ~3x menor que compound | query vai a backends de tool |
| **OLLAMA** | **PARTIAL** | KV local automático em prefixo exato, sem API gerenciada ([api](https://docs.ollama.com/api), [faq](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)) | todos locais | nenhum doc.; ∝ prefixo estático | = residência: `keep_alive` default 5m (`-1` infinito, `0` descarrega) | `prompt_eval_cached_count`, `prompt_eval_duration`, `load_duration` | nenhum ($ local) | pula reprocesso do prefixo | **fica no PC — melhor p/ SECRET** |
| **GEMINI** | **YES** | (a) implícito auto (2.5+), (b) explícito `caches.create→CachedContent` ([docs](https://ai.google.dev/gemini-api/docs/caching)) | implícito 2.5+ (incl. 3.8-flash); explícito 2.0/2.5/3.x | 3.x=4096, 2.x=2048 (verificar revisão exata) | implícito ~3–5min s/ garantia; explícito default 60min | `cachedContentTokenCount` | implícito: leitura ~0.1x (90% off); explícito: cria+storage+leitura desc. | reduzida em hit | cache retido project-scoped; VPC-SC |
| **OPENROUTER** | **PARTIAL / passthrough** ([docs](https://openrouter.ai/docs/features/prompt-caching)) | herda provider nativo + sticky routing; **response caching** é feature separada (replay exato, `X-OpenRouter-Cache`, TTL 1–86400s) | por endpoint resolvido, não por label `:free` | herda provider | herda provider + sticky 10min inatividade | `prompt_tokens_details.{cached_tokens, cache_write_tokens}`, `cache_discount` | passthrough (Groq 0.5x, Gemini 0.25x, Anthropic rd 0.1x/wr 1.25–2x…) | menor em hit | prefixo vive no provider final; **troca de provider = cache frio**; fixar `session_id` |

Ollama ajuda real ao Golden: `keep_alive` longo + `num_ctx` congelado + prompt estático primeiro + Brain residente (hoje `brain.py` sem `keep_alive`). Nota: `server_agent.py:324` mapeia `gemini-flash→gemini-3-flash-preview` vs `policies.py` `gemini-3.8-flash` — skew de versão a alinhar quando mexer em Gemini (fora deste addendum).

## 6. Response cache (separado de prompt cache)

Replay exato mesma pergunta/mesmo contexto. Faz sentido no Golden para: docs estáticas, capability/status, comandos determinísticos, perguntas repetidas. **Nunca** para: market data, hora, estado do PC, trading ao vivo, memória dinâmica. Hermes só usa via OpenRouter (`response_cache` TTL 300s) — referência válida e isolada.

## 7. Golden — montagem atual (`jarvis_core/brain.py:146-170`)

```
messages[0] system  = _system_prompt(profile)            # STATIC
messages[1] system  = _runtime_context + tool catalog filtrado  # SESSION_STABLE-na-prática-por-turno
messages[2]? system = "Contexto recuperado…DADO NÃO CONFIÁVEL" + memory_context  # TURN_VOLATILE
messages[3..]?       = history[-4:] (só VOICE_FAST com plan.response)  # TURN_VOLATILE
messages[-1] user   = user_input                          # TURN_VOLATILE
```

- Brain é o único montador (`brain.py:17-32,76-144`); Orchestrator decide sem LLM (`orchestrator/orchestrator.py:34-95` regex: CLARIFY/WINDOWS/SYSTEM/MARKET_DATA/…); ModelRouter/ProviderAdapter são transporte (`model_router.py:66-158`, `providers.py:36-71`); adapters externos fazem passthrough (`claude_provider.py:147-177`, `cline_provider.py:129-165`); `codex_provider.py:26-42` reescreve mas fora do Brain.
- P0 separou estático de runtime (`_system_prompt` só estável; telemetria `static_prompt_size/runtime_context_size/tool_catalog_size` `brain.py:68-71,153-154`; teste `test_static_prompt_is_stable…` PASS). Mas volátil fica **no meio** (runtime, memória, histórico) — invalida prefix-cache além de `messages[0]`. Sem `cache_control`/hash/ordem estável documentada hoje.
- Fast paths 0 LLM confirmados: SYSTEM/WINDOWS/MARKET_DATA/CLARIFY (`brain.py:87-117`, `orchestrator.py:36-68`, `service.py:183,1106-1117,246-390`). **Cache nunca substitui fast path.**
- Memory V2: SQLite canônico `memory/v2/` (engine/store/migrations/schema v1/entities/relations), `nomic-embed-text` 768d best-effort com fallback lexical, SECRET nunca persiste (`record.py:15-47,81-101`, `engine.py:98-99`), legado ativo no prompt via `manager.get_context(top_k=8, 2800 chars)` + banner NÃO CONFIÁVEL (`retrieval.py:101-119`). Sem resumo de sessão injetado.
- Baseline perf (docs/testes, não remedido aqui): VOICE_FAST TTFT ~300–350ms (P50 302ms), texto 1º turno ~675ms, STT P50 ~2.03s; voz ~10.7s **não localizado literalmente** (único ~10s+: SECRET frio 11.8s). Não atribuir 10.7s ao LLM.

## 8. Classificação dos blocos Golden

| Bloco | Classe | Por quê |
|---|---|---|
| Identidade Jarvis | STATIC | `_system_prompt` fixo |
| Safety/privacidade | STATIC | regras + `SECRET→só ollama` em `model_router.select` |
| Instruções tool | STATIC | contrato JSON fixo |
| Tool schemas filtrados | SESSION_STABLE* | `*` = muda por intent (`_allowed_tools` por decisão) — é o maior quebrador evitável |
| Skills (filtro) | SESSION_STABLE | só filtra tools, sem dump |
| Memória recuperada | TURN_VOLATILE | muda por query/ranking; banner NÃO CONFIÁVEL correto |
| Resumo sessão | — (ausente) | só `history[-4:]` em VOICE_FAST |
| Runtime state | TURN_VOLATILE | `input_source/voice_capture` |
| Provider state | — (fora do prompt) | só telemetria; correto, manter fora |
| Time/date, market data | REALTIME via tool | correto, manter fora do prompt |
| User message | TURN_VOLATILE | sempre nova |
| Segredos | SECRET (excluído) | `classify_data` + `MemorySecurityError` + audit `[REDACTED]`; correto |

**Campos que quebram cache hoje:** `messages[1]` (catálogo filtrado por intent), `messages[2]` (memória por query), `history` VOICE_FAST, `user_input`. Preço/hora/health **não** estão no prompt (correto).

## 9. Ordem recomendada / key / invalidação

Ordem proposta (missão §22) **adotada com 1 ajuste**: REALTIME nunca entra no prompt — vai em tool result pós-LLM (como hoje). Ordem:

```
STATIC PREFIX: identidade → safety → regras → tool schemas ESTÁVEIS (full ou subset fixo por perfil) → skill catalog
SESSION-STABLE: perfil sessão → projeto → fatos estáveis
TURN-VOLATILE: memórias recuperadas (rotuladas, fence) → tarefa → últimos turnos → mensagem atual
(REALTIME: fora do prompt — tool results)
```

Conceito de key futura (não implementar): `hash(system_prompt_version + tool_catalog_version + skill_catalog_version + model_id + privacy_profile)`. Riscos: versionamento precisa de single-writer; qualquer dict/set não-ordenado muda hash; `privacy_profile` errada vaza classe; model_id inclui revisão (ex. `gemini-3-flash-preview` vs `gemini-3.8-flash`).
Invalida por: tool schema/skill/policy/model/provider/system version. **Nunca** por timestamp/preço/health (fora do prefixo).
Serialização: exigir `json.dumps(sort_keys=True, separators=(",",":"))` + listas sorted para schemas/policies/skill index (hoje não documentado no Golden — Hermes faz em `codex.py:319-322`).

## 10. Privacidade / poisoning / multi-user / single-writer

- Cache por (usuário, sessão, privacy class, provider). SECRET só local (Ollama) — roteamento atual já força (`model_router.py:68-71,88-89`); nunca enviar SECRET ao cloud para obter hit.
- **Conteúdo não confiável nunca no prefixo estável**: memória recuperada já tem banner (`retrieval.py:105`) mas sentada em `messages[2]` (meio) — em desenho futuro vai para cauda volátil com fence (compatível com Memory V2 → Obsidian: retrieval → privacy filter → trust labeling → sidecar TURN-VOLATILE; nunca Vault inteiro).
- Multi-user futuro (Desktop/WhatsApp/iPhone): namespace `user/channel/session` na key; sem compartilhar prefixo entre privacidade distinta.
- Single-writer + drift detection (recomendação anterior p/ M1.1) também estabiliza versões de contexto/cache — um escritor de memória/sessão evita keys divergentes.

## 11. Hierarquia, streaming, métricas, ganhos honestos

- Hierarquia L0–L5 (§19) **válida como modelo mental**: L0 fast path > L1 determinístico in-process > L2 retrieval/memory > L3 provider prefix > L4 KV/residência local > L5 response cache opt-in seguro. Não implementar.
- Streaming ≠ cache: cache reduz prefill/processamento de input; streaming reduz tempo percebido; STT/TTS são componentes separados. Não misturar nos 10.7s de voz.
- Telemetria futura (sem logar prompt): `prompt_tokens, cached_prompt_tokens, uncached_prompt_tokens, cache_hit/miss, cache_write/read, cache_key_hash, prefix_version, TTFT, prefill_ms, generation_ms`.
- **Ganhos honestos:** VOICE_FAST (turnos curtos, TTFT P50 ~302ms) está **abaixo de todos os mínimos** (Groq 128–1024, Gemini 1–4k, OpenAI 1024) → ganho de prefix cache hoje ≈ 0 no VOICE; Ollama `keep_alive` é a única alavanca local. Ganho futuro cresce com GENERAL/DEEP, histórico longo, tool catalogs grandes, docs grandes (ex. `gpt-oss-120b` no Groq já suportado; Gemini explícito). Retrieval/memory cache (L2) tem potencial independente de provider. Não prometer redução nos 10.7s de voz via cache.
- Memory retrieval cache futuro (embedding/lexical/entity/relation com invalidação por MemoryEngine version) avaliado como útil e isolado de prompt cache.

## 12. Decisão M1.1 e classificação

**M1.1 BLOCKER: NO. Precisamos implementar cache antes do M1.1? NO — CAN WAIT UNTIL P1.4.** Motivos: (a) VOICE_FAST sem suporte doc. (Groq/Qwen) e abaixo dos mínimos; (b) P0 já separou estático/runtime; (c) Memory V2/Obsidian (M1.1) deve primeiro estabilizar retrieval+privacidade; cache de prefixo sem conteúdo grande/estável daria ~0. Preparação pequena opcional em P1.4: serialização canônica, `keep_alive` Ollama, telemetria de tokens, `session_id` estável p/ OpenRouter — sem tocar lógica de trading/privacidade.

| Ideia Hermes | Classe |
|---|---|
| 3-tier system (stable/context/volatile) + build 1x por sessão | ADAPT (Golden já tem messages[0] estável; estender congelamento) |
| `cache_control` Anthropic / `prompt_cache_key` OpenAI | INSPIRE (só quando Golden usar provider suportado; hoje Groq/Qwen sem suporte) |
| Escopo lógico sobrevivendo a compactação | ADAPT (para futuro) |
| Skills index estável + corpo on-demand | ADOPT (conceito; Golden já filtra sem dump — manter) |
| Memória snapshot congelada + writes invisíveis mid-session | ADOPT (conceito p/ M1.1) |
| Catálogo full sorted + hash determinístico | ADAPT (Golden usa subset por intent — decidir full-fixo-por-perfil vs subset; determinismo já) |
| Response cache OpenRouter | INSPIRE (só p/ conteúdo estático/determinístico) |
| Sidecar WAL/`api_content` | REJECT (conceito diferente; não é cache de prompt) |
| `i_cache` como feature/instrução | REJECT (não existe) |
| P0 separação + fast paths + SECRET-local do Golden | ALREADY BETTER IN GOLDEN |

---

## 13. Respostas (formato §39)

- **STATUS:** PASS (read-only; nada executado/alterado/instalado)
- **HERMES CACHE ARCHITECTURE:** 3-tier system congelado por sessão + 4-breakpoint Anthropic + `prompt_cache_key` OpenAI + escopo lógico + telemetria cached tokens; skills/memória congeladas; compactação rebuild com preservação de identidade.
- **I_CACHE FOUND:** NO. **MEANING:** termo inexistente; não inventar semântica.
- **STATIC PREFIX:** SOUL/guidance/brief + context pinado; tools sorted full; skills index; tudo congelado por sessão.
- **SESSION-STABLE:** perfil/projeto/fatos; workspace snapshot; memória snapshot.
- **TURN-VOLATILE:** user message, últimas mensagens, tool results, memória externa (Honcho em user msg).
- **TOOL SCHEMA CACHEABILITY:** alta (full+sorted+hash) — quebrada só por troca de toolset/modelo.
- **SKILLS CACHEABILITY:** alta (índice estável; corpo fora do prefixo).
- **MEMORY CACHEABILITY:** alta por congelamento; writes mid-session não invalidam.
- **SNAPSHOT/SIDECAR EFFECT:** snapshot in-memory preserva prefixo; sidecar é WAL/`api_content`, sem efeito em prompt cache.
- **COMPACTION EFFECT:** altera histórico abaixo do summary; system estável; key lógica sobrevive; byte-equal preserva identidade.
- **PROVIDER CACHE SUPPORT:** GROQ YES (3 modelos); QWEN3.8@GROQ NO; COMPOUND-MINI UNKNOWN; OPENROUTER PARTIAL passthrough (troca=cold); GEMINI YES (impl.+expl.); OLLAMA PARTIAL (KV/residência).
- **GOLDEN CURRENT PROMPT ASSEMBLY:** `brain.py:157-170` (static + runtime/catalog + memória + history VOICE + user).
- **CACHE-BREAKING FIELDS:** catálogo filtrado por intent, memória por query, history VOICE, user msg (meio+fim). Preço/hora/health fora — correto.
- **CURRENT GOLDEN CACHEABILITY:** baixa hoje (prompts curtos, subset variável, sem provider suportado no VOICE_FAST); P0 deu base.
- **RECOMMENDED PROMPT ORDER / KEY / INVALIDATION:** §9 acima.
- **PRIVACY/POISONING RISKS:** §10; SECRET-local manter; não-confiável fora do prefixo.
- **CURRENT EXPECTED LATENCY/COST GAIN:** ≈0 no VOICE_FAST (sem suporte + abaixo mínimos); pequeno no GENERAL curto.
- **FUTURE EXPECTED LATENCY/COST GAIN:** médio-alto em GENERAL/DEEP com histórico+tools+docs grandes (`gpt-oss-120b`, Gemini), mais L2 retrieval e L4 `keep_alive`.
- **MEMORY V2 / OBSIDIAN IMPACT:** retrieval→filter→label→sidecar volátil preserva cache; nunca Vault inteiro.
- **M1.1 BLOCKER:** NO. **MUST CHANGE BEFORE M1.1:** nada de cache. **SHOULD CHANGE:** nada obrigatório. **CAN WAIT FOR P1.4:** serialização canônica, `keep_alive`, telemetria, `session_id` OpenRouter.
- **ADOPT / ADAPT / REJECT:** §12.
- **FILES CREATED:** `docs/agent-context/HERMES_CACHE_ADDENDUM.md` + `docs/agent-context/handoffs/2026-09-13_opencode_hermes-cache-addendum.md`.
- **GOLDEN FUNCTIONAL FILES CHANGED:** NONE.
- **NEXT:** aguardar autorização.
