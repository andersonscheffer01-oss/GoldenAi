# Hermes Agent — Read-Only Architecture Audit for Golden Jarvis

> Referência somente leitura. Nada instalado/executado/copiado. Golden intacto.
> REPO: `C:\GoldenAI\references\HermesAgent` · branch `main` · HEAD `422bc9b`
> (2026-09-13, "fix(migrate): rollback refuses a malformed manifest…").
> LICENSE: **MIT** (Nous Research, 2025). Testes no repo: ~4247 arquivos.
> Entrypoint: `run_agent.py` (86 KB). Stack: Python + workspaces Node (TUI/web).
>
> Convenção: **EVIDÊNCIA** = caminho + símbolo verificados no código.
> Divergências docs×código marcadas com ⚠️.

## Architecture summary (textual)

```
channel (Telegram/Discord/WhatsApp/CLI/TUI)
  → gateway/platforms/* → run_inbound (auth/pairing/session key)
  → SessionStore (session_id per profile:platform:chat:thread:user)
  → agent turn loop (turn_*.py: preflight → context assembly → LLM → tools → finalize)
  → providers (registry + fallback walk + cooldown)
  → tools (registry, guardrails, approvals, MCP discovery)
  → session DB (SQLite + FTS5) + MEMORY.md/USER.md + external memory providers
  → skills (index offer → skill_view load → prompt injection, sem VM)
  → cron (jobs.json + SQLite executions/delivery) / subagents (in-process)
```

## Memory architecture (deep dive)

- **Builtin:** `tools/memory_tool_store.py::MemoryStore` — `MEMORY.md`/`USER.md`
  com chunks `§`, budgets ~2200/1375 chars, file-lock + escrita atômica,
  snapshot congelado p/ system prompt (`format_for_system_prompt`), dedup,
  `add/replace/remove/apply_batch` atômico, scan anti-injeção `strict`,
  guards de drift/wipe, cap 3 falhas de consolidação/turno.
- **Escrita:** modelo chama tool `memory` (`tools/memory_tool.py`) →
  gate de aprovação + review fail-closed → store → `MemoryManager.
  notify_memory_tool_write` espelha p/ externos com proveniência
  (`old_text`, origem, sessão, tool-call).
- **Leitura:** snapshot no system prompt (tier volátil,
  `agent/system_prompt.py::_memory_parts`) + prefetch externo por turno
  como sidecar `api_content` (`agent/turn_context.py`).
- **Busca:** `session_search` (abaixo) + `prefetch/queue_prefetch` externo.
- **Update/delete:** `replace/remove` por substring única ou batch; UI via
  `learning_mutations` (skill→archive, memória→rewrite atômico).
- **Injection:** builtin congelado no system; externo em cerca
  `<memory-context>` + nota "NOT new user input… authoritative reference" +
  scrub em replay (`sanitize_context`, `StreamingContextScrubber`).
- **Recovery:** flush append-only c/ marcador `_DB_PERSISTED_MARKER`,
  `get_messages_as_conversation(repair_alternation=True)`, tip adoption em
  race, fallback JSONL se DB corrompido.
- **Tipos:** `memory` (notas do agente) vs `user` (perfil) — budgets/flags
  separados; transcript sessão vs memória curada vs skills vs summary de
  compactação (reference-only) vs micro-summary vs seção verbatim.

## Session storage

SQLite (`hermes_state_*.py`): tabelas `messages/sessions/state_meta`,
WAL, flush em batch single-transaction, linhas `{role, content,
tool_calls, reasoning, _compressed_summary, timestamp, api_content
sidecar, display_kind, platform_message_id}`. Conteúdo limpo vs bytes
wire separados (`durable_user_row_content`). Retenção viaTitles/contagens;
sessões kanban/subagent/tool ocultas da busca.

## Session search

`tools/session_search_tool.py` (654 linhas): **zero LLM** ("No LLM calls —
every shape returns actual DB messages") sobre **SQLite FTS5+BM25**
(`hermes_state_fts.py`: tokenizador CJK/trigrama, shadow-table cleanup,
sanitizer `_sanitize_fts5_query`, cap 2048 chars). Modos DISCOVERY
(dedup por lineage, cron DEMOTED p/ evitar "recall blindness" #19434,
kanban/subagent ocultos) / SCROLL / READ / BROWSE; snippets ±janela;
resumos de compactação excluídos dos bookends.
⚠️ **Divergência:** README vende "FTS5 session search with LLM
summarization"; código faz recall sem LLM (sumarização existe só na
compactação, `context_compressor.py`).

## Memory providers

`agent/memory_provider.py::MemoryProvider` (lifecycle initialize →
system_prompt_block/prefetch/sync_turn → dispatch → shutdown + hooks
opcionais `on_turn_start/on_session_end/on_pre_compress/...`).
`agent/memory_manager.py::MemoryManager`: builtin sempre 1º + **máx 1
externo**; prefetch paralelo c/ timeout 8 s + spill; escrita serializada
em worker único FIFO; `sync_turn` nunca inline; checkpoint pré-compactação
fail-closed (API v2). Plugins em `plugins/memory/`:
**mem0, honcho (dialectic user modeling), hindsight, holographic,
supermemory, retaindb, byterover, openviking**. Trivial-prompt skip,
recall Status determinístico (`describe_recall`), ContextVars por thread.

## Context injection

Builtin (MEMORY/USER) → tier volátil do system prompt, snapshot congelado.
Externo → sidecar `api_content` no turno + cerca + scrub. Limites: gate de
prompt trivial, timeout 8 s, cap 6k chars na via de compactação
(`sanitize_memory_context`: redact + head 4000 + tail 1500), scan de
ameaça `scope="context"` (`prompt_builder._scan_context_content`).
Golden equivalente: runtime context + banner untrusted + privacy router —
paridade alta; Golden não tem cerca/streaming-scrubber (ideia ADAPT).

## Compaction

`context_compressor.py::ContextCompressor.compress` (threshold token +
preflight + cooldown anti-thrash; 1 LLM aux `temperature 0.1`; poda de
tool-output 1º; head/tail protegidos; seção verbatim de usuário + índice
âncora regex sem LLM + footer de recovery via `session_search`;
`archive_and_compact` preserva todas as linhas; marcadores
`[SKILL_PRUNED]` re-injetados). `micro_compaction.py` (rolling por
exchange, OFF default — quebra prompt cache). Checkpoint de providers
fail-closed antes do commit. **ADAPT** como padrão (compaction como
retrieval diferido, nunca perda).

## Skills

Formato: `SKILL.md` c/ frontmatter (name ≤64, description ≤60 p/ roteamento,
version semver, platforms, metadata.hermes tags/category/related/config) +
dirs `scripts/references/templates/assets` (limites 100k chars/1 MiB).
Descoberta: índice `## Skills` por categoria no system (`prompt_builder.
build_skills_system_prompt`, manifest mtime p/ cold start) + `skills_list`
Tier-1 + `/slug` + bundles YAML. Seleção: decisão do modelo (MUST load se
parcialmente relevante) ou explícita. Carga: `skill_view` (Tier-2,
progressive disclosure, checks colisão/quarentena/disabled, readiness
env/cred). Execução: **sem VM — prompt injection**, modelo usa tools
nativas. Criação: `/learn` + `skill_manage` (validação frontmatter,
ownership/pin/read-before-write, batch atômico, approval staging).
Auto-aprendizado: fork `background_review` pós-turno (whitelist,
orçamento 16 iter/600k tokens, nunca captura transientes) + `curator`
(active→stale 14d→archived 30d, nunca deleta, umbrella-consolidation)
+ `curator_backup` (tar.gz + rollback). Padrão agentskills.io.

## Skills vs procedural memory

Hermes separa explicitamente (`skill_manager_tool.py:2-8`): skills =
memória procedural estreita (how-to-X versionado); MEMORY/USER.md =
declarativo amplo. Economia de retrieval, autoridade de escrita,
lifecycle e isolamento de falha distintos; `learning_graph` modela como
nós diferentes com arestas. **Recomendação: manter Golden PROCEDURAL
(fatos/lições duráveis) separado de futuro SKILLS (pacotes SKILL.md
versionados)** — detalhes no handoff.

## MCP

`tools/mcp_tool_discovery.py` (lazy connect + cooldown + cache),
`mcp_tool_transport.py` (stdio/HTTP/SSE multiplex), `mcp_tool_config.py`
(env filtrado + `${env:}` sem cross-profile), `mcp_tool_scope.py`
(visibilidade por perfil), OAuth sob `mcp-tokens/`, `allowed_mcp_names`,
`is_mcp_tool_parallel_safe`, timeouts por transporte, trust gating
(`hermes_cli/mcp_security.py`). **ADAPT**: lazy+cooldown+allowlist já
espelham filosofia Golden; adotar filtro env + escopo por perfil.

## Subagents

`agent/subagent_lifecycle.py` + `tools/delegate_tool.py`: in-process,
capability HMAC + match de sessão-pai, `allowed_toolsets ⊆ pai`,
metadata ≤8 KB, sem budget (só uso/duração), cancel via interrupt,
`reconnect` nunca relança pós-restart. Herda tools do pai (sem store
própria). **INSPIRE** capability handles; **REJECT** como isolamento
suficiente p/ delegação não-confiável.

## Cron

`cron/` (scheduler watchdog, `jobs.json` c/ flock, `executions.py` +
`delivery_queue.py` SQLite c/ claim fences + PID-liveness + `recover_*`
no boot, retries c/ backoff) + `periodic_scheduler.py` (in-process, sem
persistência). Segurança: exceção `CronPromptInjectionBlocked`, toolset
allowlist por job, credenciais escopadas, auditoria de uso, change-detector
p/ pular LLM. **ADAPT** claim-fence + stale-sweep + recovery no boot p/
jobs duráveis Golden.

## Messaging

`gateway/`: adapter emite `MessageEvent` → admit (auth/pairing/allowlist)
→ `build_session_key` (`agent:profile:platform:chat:thread:user`,
JID WhatsApp canônico, PII hasheada, traversal guard, `api_key` nunca
persistida) → turno → `send()`. Plataformas: Telegram/Discord/Slack/
**WhatsApp (`whatsapp_cloud.py`)**/Signal/CLI/API server. **ADAPT**
session-key namespaced + isolamento por chave p/ futuro WhatsApp/iPhone
Golden. **REJECT** `ensure_deps` instalando pacotes no caminho do chat.

## Voice

`agent/transcription_provider.py` (`transcribe→{transcript}`, sem raise,
`HERMES_LOCAL_STT_COMMAND`), `tts_provider.py` (`synthesize` arquivo +
`stream()` chunks c/ fallback arquivo, warm/release), `transcript_repair`
(blank-row fix), `gateway/streaming_tts_consumer.py` (Opus, por turno).
Ideias p/ P1.4 Golden: **INSPIRE** `stream()` iterator c/ fallback +
warm/release do TTS; transcript-repair de linhas vazias. Golden P1–P1.3
(gate adaptativo, pre-roll, anti-autoescuta, telemetria) sem equivalente
visto — vantagem Golden.

## Streaming

`agent/stream_delivery.py`: **single-writer token fencing**
(`_claim_stream_writer/_superseded`), scrubbers por delta, dedup interim,
hooks de plugin. `chat_completion_stream_monitor.py`: heartbeat 30 s,
slow-notice 60 s, stale-kill + interrupt-abort. **ADOPT** fencing p/
deltas de retry superseded (P1.4).

## Security

Sanitização wire, `redact.py` (máscaras + vault values + formatter),
`file_safety.py` (deny/approval paths, espelhos), `secret_scope.py`
(.env por perfil, scrub de env filho), guardian-LLM em approvals,
`skills_guard`, tirith fail-closed. **Mas** `SECURITY.md` declara: só
isolamento OS é boundary; resto é não-boundary; plugin = privilégio total.
**ALREADY BETTER IN GOLDEN**: registry central + risk + confirm + audit +
secret-filter é mais auditável/aplicável que gates heurísticos dispersos.
**ADAPT**: redact p/ egress + secret-scope por perfil.

## Hermes strengths / weaknesses

+ Aprendizado fechado real (review pós-turno + curator + rollback).
+ FTS5 session search maduro (dedup lineage, anti recall-blindness).
+ Skills como padrão aberto (agentskills.io) c/ progressive disclosure.
+ Providers de memória plugáveis c/ contrato versionado + checkpoint.
+ Gateway multi-canal + cron durável + streaming fencing.
− Segurança in-process declaradamente não-boundary; plugin total.
− Sem tri-state explícito de provider (só backoff exponencial 60s→4h).
− Recall sem LLM apesar do marketing; sem embeddings próprios no core.
− Subagents sem budget/isolamento real; installs em caminho quente.
− Curva de 12k arquivos; TUI/web Bounds pesadas p/ objetivo Golden.

## Golden strengths / weaknesses (pós-auditoria)

+ Fast paths 0 LLM, VOICE_FAST, readiness eager, privacy routing SECRET,
  audit central, risco/confirmações, versionamento/proveniência/entidades.
+ STT robustness + anti-autoescuta + telemetria por utterance.
− Sem FTS5 session search (recall de sessões é lexical simples).
− Sem skills versionadas (PROCEDURAL cobre parcial, sem pacote/teste).
− Sem compaction (histórico Brain é lista em processo).
− Sem cron durável / gateway / fencing de stream.
− Cooldown 60 s fixo (Hermes usa backoff exponencial c/ tombstone).

## Classificações

ADOPT: single-writer stream fencing; FTS5 sanitize-quote + cap 2048;
secret-scope por perfil + env scrub; pre-compress checkpoint fail-closed;
sessão-key namespaced (gateway futuro).
ADAPT: session search FTS5 (demote automações, dedup lineage, snippets
vizinhos); curator ativo→stale→archived + backup/rollback; claim-fence
p/ jobs; frozen snapshot + sidecar cercado; providers externos 1+builtin
c/ timeout+spill; redact egress; backoff exponencial c/ estados explícitos.
INSPIRE: subagent capability HMAC; bundle YAML; learning graph; umbrella
consolidation; change-detector p/ pular LLM; transcript-repair.
REJECT: heurísticas como desculpa p/ gates fracos; installs em caminho
quente; subagents sem budget como isolamento; mtime-window como exfil
control; slash que reescreve prompt como controle; recall-blindness
(BM25 puro s/ demote).
ALREADY BETTER IN GOLDEN: risk/confirm/audit central; privacy routing;
fast paths; readiness eager; versionamento/proveniência/entidades;
STT robustez; sem segundo TTS/STT.

## Foco M1.1

MUST CHANGE BEFORE M1.1: nada estrutural — V2 já compatível (Markdown
stub existe; vault será projeção).
SHOULD CHANGE BEFORE M1.1: definir regra de divergência SQLite↔Markdown
(single-writer + atomic + drift-detect inspirados no Hermes) antes do
vault editável; FTS5 p/ session search (M1.3) pode entrar junto.
CAN WAIT: providers externos; compaction; curator; skills; gateway.
DO NOT ADOPT: auto-escrita de memória sem gate; installs; heurística
como boundary.
OBSIDIAN STRATEGY STILL VALID: **YES** — Hermes valida Markdown como
fonte curada + SQLite operacional; nada lá sugere abandonar o vault.
SOURCE OF TRUTH: Engine=autoridade, SQLite=canônico operacional,
Markdown=projeção editável, Vetor=derivado, Grafo=derivado/canônico por
schema — **mantida**; adicionar detector de drift + single-writer.

## Top 10 ideias p/ Golden

1. FTS5 session search c/ dedup lineage + demote automações.
2. Snapshot congelado + sidecar cercado p/ injeção de contexto.
3. Checkpoint fail-closed pré-compactação.
4. Single-writer serializado p/ escritas de memória.
5. Compaction como retrieval diferido (rows preservadas + footer recovery).
6. Write-path hardening (scan strict, unique-substring, batch atômico, .bak).
7. Curator time-based + backup/rollback de skills.
8. Secret-scope por perfil + env scrub.
9. Backoff exponencial c/ tombstone por (provider,model).
10. Session-key namespaced p/ WhatsApp/iPhone futuro.

## Top 10 a NÃO copiar

1. Heurísticas declaradas não-boundary como modelo de segurança.
2. Instalação de dependências em caminho quente.
3. Subagents sem budget/isolamento.
4. BM25 puro sem demote (recall blindness).
5. Slash-commands que reescrevem prompt como controle.
6. Mtime-window como controle de exfiltração.
7. Recall marketing c/ LLM inexistente no código.
8. Skills sem quarentena p/ diretórios de projeto.
9. Apagar sem archive (Hermes nunca deleta — copiar o acerto, não o erro).
10. Monolito 12k arquivos / 7 backends p/ metas Windows/voz/trading.

FILES CREATED: docs/agent-context/HERMES_AGENT_ARCHITECTURE_AUDIT.md +
handoffs/2026-09-13_opencode_hermes-agent-readonly-audit.md.
GOLDEN FUNCTIONAL FILES CHANGED: NONE. NEXT: aguardar autorização.
