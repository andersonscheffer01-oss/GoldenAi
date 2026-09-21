# Golden Memory Engine V2 — Fundação (M1.0)

> Porta oficial de memória do Jarvis. Brain/Voice/Radar/Skills falam com o
> engine; nunca com SQLite/vetor/Markdown diretamente. Legado preservado.

## Arquitetura

```
Jarvis (Brain/Voice/Service)
  ↓
GoldenMemoryEngine (`jarvis_core/memory/v2/engine.py`)
  ├── WorkingMemory (volátil, TTL 900 s)
  ├── SQLiteMemoryStore (principal)
  ├── MarkdownMemoryStore (stub M1.1 — NotImplemented)
  ├── LegacyMemoryAdapter (lê GoldenMemoryManager, sem migrar)
  └── embed hook (EmbeddingService legado; falha → PENDING, sem crash)
```

Tipos: WORKING, SESSION, EPISODIC, SEMANTIC, ENTITY, DECISION, PROCEDURAL,
LESSON (`v2/types.py`). Entidades/relações em tabelas próprias.

## Schema (mesmo `golden_memory.db`, prefixo `v2_`, legado intocado)

- `v2_memories`: id/type/title/content/summary/status/created/updated/
  accessed/version/confidence/basis/privacy/source_type/source_ref/
  source_ts/project/tags/metadata/embedding_status/embedding_model/
  content_hash/canonical_key.
- `v2_memory_versions`: snapshot pré-update (versionado, nunca apaga).
- `v2_entities` + `v2_entity_aliases` (UNIQUE type+name; aliases idempotentes).
- `v2_relations` (UNIQUE src+type+dst; FKs com checagem em código).
- `v2_embeddings` (vetor JSON + modelo; dimensão validada na leitura).
- `v2_schema_version` (migrations idempotentes; atual: 1).

## Lifecycle / status

ACTIVE → (update gera versão) → SUPERSEDED | ARCHIVED | DELETED_LOGICAL.
Soft-delete sempre; `find_*` só enxerga ACTIVE. `updated_at`/`version`
sob RLock + transação única (tudo commit ou rollback).

## Privacy (DataClassification oficial — sem segundo sistema)

PUBLIC/INTERNAL/SENSITIVE/SECRET. SECRET nunca persiste (vault dedicado);
padrões de credencial em content/summary/metadata/chaves/source_ref
levantam `MemorySecurityError`. SECRET continua 100% local no roteamento.

## Confidence (0–1, sem auto-invenção)

Basis: SOURCE_CONFIRMED | INFERRED | TENTATIVE | USER_CONFIRMED.
Valores fora de [0,1] rejeitados; sem score automático.

## Proveniência

source_type (conversation/file/test/benchmark/user_explicit/system/agent/
import/legacy) + source_ref (sem segredo) + source_timestamp + project.

## Deduplicação (exata nesta fase; semântica é futuro)

- `content_hash` (sha256 normalizado): duplicata exata retorna o id
  existente sem nova versão.
- `canonical_key` (ex.: `decision:golden:voice_model`): upsert versionado.
- Legado mantém seu dedup próprio (normalizado + cosine 0,92) intocado.

## Compatibilidade legada

`LegacyMemoryAdapter(manager)`: `recall()` mapeia memories/sessions para
`MemoryRecordV2` (privacy INTERNAL, basis INFERRED). Nenhuma migração
física; `GoldenMemoryManager`, Brain `get_context`, follow-up e tools de
memória inalterados. Engine V2 exposto em `service.memory_v2` + bloco
`engine_v2` no `/api/jarvis/memory/status` (DEV: V2 READY/DEGRADED,
schema, pending embeddings).

## Embeddings

Modelo preservado: `nomic-embed-text` (dim 768), sem re-embedar. Engine
recebe hook `embed`; falha/offline → persiste texto com PENDING.
Busca: lexical agora + coseno quando houver vetores (contrato híbrido
LEXICAL/VECTOR/METADATA/GRAPH pronto; ranking complexo é futuro).

## Concorrência / performance

RLock + WAL + busy_timeout; upserts idempotentes (UNIQUE + INSERT OR
IGNORE/ON CONFLICT). Smoke: remember 7 ms, get 2 ms, dedup 2 ms,
entity 4 ms (text-only, sem embedding).

## Testes

`tests/test_jarvis_memory_v2_m10.py` (30): contratos, versionamento,
dedup, entidades/relações, SECRET, migrations, legado, embedding
degradado, rollback, concorrência (8 threads), TTL, perf, status.

## Próximos (M1.2+ somente com autorização)

GraphRAG; FileWatcher; consolidação/dedup semântico; auto-memory com
MemoryCandidate; sync iPhone. (M1.1 vault abaixo: CONCLUÍDO.)

## M1.1 — Markdown Vault (Obsidian-compatible) ✅

Fonte de verdade: `GoldenMemoryEngine` → SQLite canônico → Markdown
projeção → vetor derivado. Vault default `C:\GoldenAI\memory\vault`
(env `GOLDEN_MEMORY_VAULT_PATH`). Golden funciona sem Obsidian.

- Single writer: só o engine projeta, via `MarkdownMemoryStore`
  (`v2/store.py`) + locks por record + `atomic_write` (temp+fsync+replace).
- Schema v2: `v2_projections(memory_id, kind, path, projection_hash,
  projection_version, sync_status, detail, last_sync_at)`.
- Sync: SYNCED | PENDING | DRIFT | CONFLICT | ERROR | IGNORED.
  SQLite nunca desfeito por falha Markdown; edição externa = DRIFT/
  CONFLICT, nunca importada (FileWatcher é M1.6).
- Notas gerenciadas: frontmatter `id` (`mem_<id>`/`ent_<id>`,
  rename-safe) + `managed_by: golden-memory-v2`; YAML próprio sem deps;
  UTF-8; slug sanitizado Windows; colisão via sufixo `--mem<id>`.
- Pastas: 00_Inbox, 01_Daily (episodic, prefixo data), 02_People,
  03_Projects, 04_Knowledge(+/Lessons), 05_Decisions, 06_Procedures,
  07_Trading (override trading), 08_Golden, 09_Tasks, 10_Documents,
  11_Research, 12_Conversations, 90_Archive, 99_System.
  WORKING/SESSION nunca projetam; ARCHIVED move p/ 90_Archive;
  SUPERSEDED mantém nota + histórico no SQLite.
- Entidades → notas próprias; relations → `[[wikilinks]]`
  (representação; tabela SQLite canônica); aliases no frontmatter;
  tags normalizadas; `trust_level` (trusted/untrusted) + banner DADO.
- Privacy: PUBLIC/INTERNAL projetam; SENSITIVE restrito (IGNORED);
  SECRET proibido (engine já rejeita + `security-block` na projeção);
  scrub pré-Markdown inclui title.
- `rebuild_vault(dry_run)` SQLite→Markdown, só toca gerenciadas;
  humanas nunca apagadas; index em `99_System/Golden Memory Index.md`.
- Perf: remember 7 ms → 21 ms c/ projeção (delta 14 ms, texto-only).
- Testes: `tests/test_jarvis_memory_v2_m11.py` (43). Total 272 + 72 subtests.

## M1.2 — Knowledge Graph ✅

Grafo usa `v2_entities`/`v2_relations` (+ `v2_memory_entities`,
`v2_relation_evidence`, `v2_entity_versions`, `v2_relation_versions`).
Markdown = representação; sem GraphRAG/FTS5/hybrid/dedup (M1.3+).
Schema 3 (migration idempotente; produção e legado intactos).

- Entidade: id estável + `normalized_name` (case/whitespace; sem fusão
  agressiva) + aliases 1ª classe (coluna normalizada) + status/privacy/
  confidence/basis + provenance (source_type/ref) + version + metadata.
- Tipos: 11 M1.0 + CONCEPT/COMPONENT/DEVICE. SEM DECISION/PROCEDURE/
  TEST/FEATURE (MemoryRecords já cobrem; sem segunda fonte de verdade).
- `resolve_entity`: canonical exata → normalizada → alias exato →
  normalizado → AMBIGUOUS/NOT_FOUND (nunca chuta; filtro clearance).
- `merge_entities` explícito e transacional: rewiring sem duplicatas
  (evidência preservada), aliases/memórias movidos, origem → MERGED,
  `merged_from` no destino, audit. Sem merge automático.
- Relações: catálogo de 19 tipos (`v2/graph.py`) com DIRECTED/
  SYMMETRIC + inversa derivada (nunca persistida) + self-edge bloqueada.
  Simétricas canonicalizadas (menor id). Provenance obrigatória na
  prática (source_type/ref), confidence 0–1 com basis (incl.
  TEST_CONFIRMED/DOCUMENTED). Sem criação via LLM nesta fase.
- Privacy só sobe: relação = max(origem, destino, pedida). SECRET nunca
  Markdown/cloud/caller não autorizado. Trust 4 tiers por source_type.
- Ciclo de relação: ACTIVE/SUPERSEDED/DISPUTED/ARCHIVED (snapshot em
  toda mutação; sem resolução semântica).
- Memory↔entity (`v2_memory_entities`, roles) + evidências múltiplas
  (`v2_relation_evidence`); notas mostram Related/Memories.
- Query API: get/find/resolve/list_entities, neighbors (filtros +
  ordem confidence↓/updated↓/nome↑), incoming/outgoing, traverse BFS
  (visited, max_depth=2/max_nodes=50 default), shortest_path,
  get_subgraph (contratos GraphNode/Edge/Neighbor/Path/Result).
  Privacy filter (clearance) antes do retorno. Grafo fora do prompt
  de voz (sem mudança em Brain/recall/rotas).
- Obsidian: Related com labels (`USES_MODEL → [[Qwen 3.8 27B]]`,
  inversas no alvo: `PROVIDES → [[...]]`), `## Memories`, trust no
  frontmatter, `99_System/Entity Index.md` (só PUBLIC/INTERNAL),
  rebuild reconstrói wikilinks do canônico; humanas intactas.
- Diagnóstico: `graph_stats` (totais/ativos/disputed/órfãs/conflitos),
  `validate_graph` (dangling, self-edge, duplicata simétrica,
  tipo/privacy/status inválidos, alias ambíguo; ciclo NÃO é erro),
  órfãs só reportadas. DEV status mostra entities/relations/integrity.
- Perf local: resolve 2 ms, relation create 42 ms, neighbors 4 ms,
  depth-2 17 ms, shortest path 34 ms, subgraph 16 ms.
- Testes: `tests/test_jarvis_memory_v2_m12.py` (54). Total 326 + 72.

## M1.3 — Hybrid Retrieval + FTS5 + Graph Assist ✅

O SQLite canônico continua sendo a fonte de verdade. A migration v4 é
aditiva e cria `v2_memories_fts` como índice derivado reconstruível; se o
SQLite não oferecer FTS5, a busca degrada para token-overlap sem perder o
conteúdo canônico. O tokenizer é `unicode61`, compatível com texto PT-BR.

- Sanitização: a query nunca entra diretamente em `MATCH`. Ela é normalizada,
  limitada a 500 caracteres/12 tokens, remove operadores e monta apenas frases
  citadas unidas por `OR`. O mesmo limite vale para embedding e resolução de
  entidades. Quotes, parênteses, AND/OR/NOT/NEAR, `*`, `:`, `-`, Unicode,
  vazia, expressão inválida e entrada de 100 mil caracteres têm cobertura.
- Candidatos: FTS5/BM25 lexical, vetor cosine (`nomic-embed-text`, 768d),
  metadados/recência, entidade resolvida explicitamente e expansão de grafo.
  Falha de vetor não bloqueia FTS; embedding pendente permanece degradado.
- Entidades: somente `FOUND` participa. `AMBIGUOUS` e `NOT_FOUND` não escolhem
  alias silenciosamente. O grafo é assistência limitada, não GraphRAG:
  depth padrão 1, teto 2 e no máximo 50 entidades/nós visitados.
- Fusão: Reciprocal Rank Fusion por ranking, com `k` por fonte. BM25, cosine e
  distância do grafo não são somados em escalas cruas. Há deduplicação,
  desempate determinístico e boosts explícitos limitados a 0,05.
- Filtros: type, project, tags, source_type, created_from/created_to,
  status/history e privacy/clearance. Nenhum ranking ultrapassa clearance.
- Privacy/trust: PUBLIC/INTERNAL/SENSITIVE seguem clearance; SECRET não é
  persistido/indexado. Trust é exposto no resultado. Memória recuperada entra
  como bloco `[MEMORY_CONTEXT]` marcado como dado não confiável, nunca como
  instrução. Vault/grafo completos não entram no prompt.
- Budget: padrão máximo de 8 itens e 2.800 caracteres, com truncamento limpo.
  O sidecar é volátil e não altera o prefixo estático do Brain.
- Consistência: `validate_retrieval_indexes()` detecta FTS ausente/órfão/
  divergente, embedding pending/missing e links pendentes. `repair_indexes()`
  remove/reconstrói apenas derivados; conteúdo canônico não é corrigido.
- Observabilidade: `fts_ms`, `vector_ms`, `metadata_ms`, `graph_ms`,
  `fusion_ms`, `total_ms`, status e contagens de candidatos.
- Qualidade controlada: 23 registros e 15 queries. Legacy Top-1 0,7333,
  Recall@5 0,9111, MRR 0,8333; Hybrid 1,0/1,0/1,0. Nesta máquina:
  P50 142,5 ms e P95 249,3 ms no teste comparativo. Medição sem provider
  vetorial: FTS P50 6,8 ms, graph 12,1 ms, fusion 60,8 ms, total 123,7 ms.

### Integração runtime

`JarvisService` mantém as duas portas explícitas: `legacy_memory` é a API
compatível e `memory_v2` é o `GoldenMemoryEngine`. O Brain recebe ambas e
aplica `JARVIS_MEMORY_HYBRID_V2`:

- `off`: somente `legacy_memory.get_context()`, sem chamada híbrida.
- `shadow` (default): contexto legado continua no prompt e a busca híbrida
  roda em executor único controlado, somente para telemetria sem conteúdo
  (`legacy_count`, `hybrid_count`, top IDs, latência, fallback/erro). Se uma
  comparação estiver em andamento, a seguinte é ignorada em vez de enfileirar.
- `on`: `memory_v2.hybrid_context()` fornece o contexto principal; qualquer
  exceção cai silenciosamente para o contexto legado.

Fast paths retornam antes do retrieval. Conversa VOICE_FAST simples também é
dispensada; pedidos explícitos de memória podem consultar. O V2 usa o hook
oficial `EmbeddingService.embed_sync` com `nomic-embed-text`/768d. O contexto
híbrido continua limitado a 8 itens/2.800 caracteres e marcado como DATA não
confiável; clearance runtime padrão é INTERNAL.

Limitações: corpus de qualidade é pequeno e local; métricas não equivalem a
produção. Benchmark vetorial real depende do Ollama com `nomic-embed-text`.
GraphRAG, dedup semântico e extração automática pertencem a fases posteriores.

## M1.4 — Consolidation + Semantic Dedup + Contradictions ✅

`GoldenMemoryEngine.remember()` continua sendo o single writer e consulta o
`MemoryConsolidator` determinístico antes de persistir. O classificador produz
`NEW`, `EXACT_DUPLICATE`, `SEMANTIC_DUPLICATE`, `UPDATE`, `COMPLEMENT`,
`CONTRADICTION` ou `UNCERTAIN`, usando no máximo seis candidatos do retrieval
híbrido, similaridade lexical, cosine quando disponível, project/type,
proveniência, trust e confidence. Nenhuma chamada LLM é necessária.

- Exact duplicate mantém o ID e reforça evidência/proveniência em metadata;
  a alteração é versionada. Semantic duplicate só consolida conteúdo realmente
  equivalente; textos curtos exigem massa lexical mínima e cosine alto não
  autoriza sozinho merge de DECISION/PROCEDURAL/LESSON.
- `canonical_key` realiza update versionado apenas dentro do mesmo projeto e
  quando a fonte recebida tem trust suficiente. Fonte inferior cria registro
  separado `DISPUTED`, sem sobrescrever correção explícita do usuário.
- Complementos permanecem ACTIVE como registros independentes e guardam a
  relação de consolidação. Contradição de fonte/confiança superior pode criar o
  novo ACTIVE e marcar o anterior SUPERSEDED; empate ou evidência insuficiente
  mantém ambos e marca o novo DISPUTED/UNCERTAIN.
- Privacy nunca diminui. A seleção de candidatos respeita clearance; SECRET
  continua recusado antes de embedding, Markdown ou persistência comum.
- Hash e canonical key são isolados por `project`; o RLock existente serializa
  classificação + escrita e impede double merge em chamadas concorrentes.
- Falha/ausência de embedding degrada para lexical/hybrid sem bloquear gravação.
  Relações e evidências ficam em metadata versionada; SQLite segue canônico.

Validação M1.4: `tests/test_jarvis_memory_v2_m14.py` cobre 15 cenários,
incluindo concorrência, histórico, proveniência, privacidade e degradação.
Suíte completa: 395 testes + 72 subtests, zero falhas. Medição local text-only:
remember 21 ms, exact dedup 10 ms; hybrid P50 94,0 ms/P95 156,7 ms.

Limitações M1.4: detecção de contradição cobre atribuições explícitas e negação
lexical, não interpretação aberta; conflitos sem evidência suficiente ficam
UNCERTAIN para resolução futura. Web research, continuous learning, importação
Obsidian, extração LLM e GraphRAG completo continuam fora de escopo.

## M1.5 — Continuous Learning + Research Engine Foundation ✅

Fundação criada em `jarvis_core/memory/v2/research.py`. A arquitetura separa
pesquisa/aprendizado de persistência: `ResearchEngine` coleta/faz fetch por
contrato desacoplado de provider, `SourceTrustEvaluator` classifica fonte,
`EvidenceRecord` preserva proveniência, `KnowledgeCandidate` mantém estado de
aprendizado e `LearningEngine` só promove conhecimento via
`GoldenMemoryEngine.remember()`. Memory V2 continua sendo single writer; não há
segundo banco de memória.

- Fluxo: provider `search/fetch` → conteúdo externo marcado como dado não
  confiável → extração determinística de claims → evidências com URL/ref,
  source_type, timestamp, title, domain, trust, confidence e basis →
  candidatos → comparação com Memory V2/M1.4 → NEW/DUPLICATE/UPDATE/
  CONTRADICTION/UNCERTAIN → promoção manual para memória → Knowledge Graph/
  vault pelos caminhos já existentes do engine.
- Trust: níveis A/B/C/D/E. A = documentação oficial/primária; B = benchmark/
  reprodução técnica; C = múltiplas fontes independentes coerentes; D =
  fórum/comunidade; E = hipótese isolada. Repetição em fórum permanece D e não
  vira fato oficial. Trust da fonte é separado de confidence do conteúdo.
- Segurança web: páginas, fóruns e PDFs são tratados como `UNTRUSTED DATA`.
  Padrões de prompt injection são sinalizados em evidência e removidos da
  extração de claims; nenhum aprendizado executa comandos ou muda instruções.
- Estados: `DISCOVERED`, `SUPPORTED`, `DISPUTED`, `VALIDATED`, `REJECTED`,
  `SUPERSEDED`. Apenas `SUPPORTED`/`VALIDATED` são promovíveis; ambiguidade e
  disputa não são resolvidas arbitrariamente.
- Privacidade: usa `DataClassification` oficial. `SECRET` é bloqueado antes de
  pesquisa web e antes de promoção; URLs em proveniência removem query/fragment
  para evitar vazamento acidental.
- Experiência local: `LocalExperience` prepara contexto hardware/software/
  driver/projeto/jogo/versão/data/métrica/resultado para candidatos futuros sem
  confundir recomendação global com resultado local.
- Expert profiles: `ExpertProfile` cobre GAMING, AMD, WINDOWS, TRADING,
  CODING, GOLDEN e RESEARCH. O expert guarda índices (`memory_ids` e hashes de
  candidatos), não duplica conteúdo nem vira source of truth.
- Research API: `ResearchProvider.search(query)` e `ResearchProvider.fetch()`.
  `StaticResearchProvider` cobre testes/manual/prefetched data. Não há scraper,
  browser automation, Computer Use, cron ou pesquisa autônoma nesta fase.
- Performance: pesquisa só roda quando chamada explicitamente pelo
  `LearningEngine`; fast paths, VOICE_FAST e conversa simples não pagam custo.

Validação M1.5: `tests/test_jarvis_memory_v2_m15.py` cobre fonte oficial,
fórum, fontes conflitantes, repetição em fórum, prompt injection, promoção,
rejeição, disputed claim, proveniência, expert profile, isolamento de projeto,
privacy/SECRET, integração M1.4, falha de provider, resultado duplicado e
experiência local. Suíte completa em 2026-09-13: 412 testes + 72 subtests
verdes (1 warning conhecido em `chart_strategy_test.py`, retorno `dict` em
teste).

Limitações M1.5: extração de claims é determinística e simples; provider real
de web ainda não está conectado; aprendizado é manual por solicitação explícita;
sem cron/autonomous research, execução de otimizações, Browser Agent,
Computer Use, GraphRAG completo ou UI Desktop V4.

## M1.5.1 — Real Web Research Provider ✅

Provider real conectado sem alterar a arquitetura M1.5. `ResearchEngine` segue
conhecendo apenas o contrato `ResearchProvider.search/fetch`; o adapter real
fica em `jarvis_core/memory/v2/research.py` e pode ser trocado por env sem
alterar `LearningEngine`.

- Provider: `BraveSearchResearchProvider`, ativado por
  `GOLDEN_RESEARCH_PROVIDER=brave` + `BRAVE_SEARCH_API_KEY`. Sem chave, o
  provider fica indisponível de forma explícita; o Jarvis não diz que pesquisou.
- Search: query sanitizada (`sanitize_research_query`), limite 1–10, timeout e
  retries por env (`GOLDEN_RESEARCH_TIMEOUT`, `GOLDEN_RESEARCH_RETRIES`),
  resultados estruturados com title, url, domain, snippet, timestamp,
  source_type e provider. URLs são normalizadas/deduplicadas.
- Fetch: `SafeHTTPFetcher` usa apenas HTTP/HTTPS, sem JavaScript e sem executar
  conteúdo. Bloqueia schemes não suportados, localhost, 127.0.0.1, 0.0.0.0,
  ::1, IPs privados, link-local, reserved/metadata endpoints e DNS que resolve
  para alvo interno. Redirects são limitados e validados antes de seguir.
  Tamanho, timeout e content types são limitados.
- Prompt injection: conteúdo web permanece `UNTRUSTED DATA`; padrões como
  "ignore previous instructions" e "execute PowerShell" são flags de evidência
  e não viram instrução nem claim promovível.
- Privacy/egress: `SECRET` é bloqueado antes de search/fetch. Queries removem
  padrões de segredo antes de sair; telemetria não inclui conteúdo sensível.
- Jarvis route: a skill WEB agora tem ferramentas explícitas
  `web_research` e `web_research_learn`. Pedidos como "pesquise...",
  "procure na internet..." e "verifique na web..." chamam pesquisa real; pedidos
  com "aprenda"/"memorize"/"guarde" usam o fluxo de aprendizagem. Conversa
  comum, fast paths e VOICE_FAST simples continuam sem research.
- Pesquisar vs aprender: `web_research` retorna fontes/candidatos sem memória.
  `web_research_learn` promove somente candidatos permitidos pelas regras
  M1.5/M1.4 via `GoldenMemoryEngine.remember()`. Nada escreve SQLite direto.
- Observabilidade: resultados expõem telemetry segura: provider, search_ms,
  fetch_ms, results_count, pages_fetched, candidates_created, promoted,
  disputed e failed.

Validação M1.5.1: `tests/test_jarvis_memory_v2_m151.py` cobre contrato do
adapter real, timeout, provider indisponível, resultado malformado, URLs
duplicadas, redirect, página grande, content type rejeitado, SSRF, prompt
injection, SECRET/SENSITIVE egress, trust oficial vs fórum, pesquisar sem
aprender, pesquisar+aprender, integração M1.4, rotas Jarvis, fast paths e
VOICE_FAST. Smoke real opcional usa `BRAVE_SEARCH_API_KEY` e é pulado sem
internet/chave. Suíte completa em 2026-09-14: 429 testes + 79 subtests verdes,
1 smoke real opcional skipped, 1 warning conhecido em `chart_strategy_test.py`.

Limitações M1.5.1: só Brave Search está implementado como provider real; sem
fallback público sem chave para evitar scraper frágil. Fetch suporta textos/HTML
e JSON simples; PDFs e extração rica ficam para fase futura. Sem cron,
autonomous research, Browser Agent, Computer Use, UI Desktop V4 ou M1.6.
