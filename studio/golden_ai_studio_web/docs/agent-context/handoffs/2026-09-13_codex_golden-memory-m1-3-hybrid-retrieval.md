# Handoff — Codex — Golden Memory M1.3 (2026-09-13)

## Estado

M1.3 concluída com PASS. A implementação do OpenCode foi preservada e
auditada por leitura, testes direcionados, qualidade e regressão completa.
Não foi iniciada M1.4.

## Implementação validada

- Migration v4 aditiva e idempotente; FTS5 `unicode61` derivado.
- Sanitizador transforma entrada em tokens citados e impede MATCH arbitrário.
- Fontes lexical, vector, metadata, entity e graph; RRF sem score cru misto.
- Entidade somente FOUND; ambiguity/not-found não são forçados.
- Privacy/clearance, trust e blocos de contexto como DATA não confiável.
- Context budget e observabilidade por estágio.
- Consistency/repair atuam nos índices derivados, não no canônico.

## Correções Codex

1. Query normalizada agora é limitada a 500 caracteres antes de chegar aos
   adapters vector/entity; antes apenas o MATCH estava efetivamente limitado.
2. `graph_depth` agora tem teto 2 e `graph_max_nodes` teto 50, inclusive para
   chamadas com valores extremos.
3. Expansão conta entidades visitadas no limite, evitando passeio amplo em
   grafos cujos nós não tenham memórias vinculadas.
4. Dois testes de regressão cobrem query de 100k e limites duros do grafo.
5. Restaurada a suíte P1.1 de 12 testes removida durante cancelamento de uma
   tarefa anterior; conteúdo recuperado do registro original, sem alteração.

## Final closure — integração runtime

- `C:\GoldenAI\AGENTS.md` agora aponta exclusivamente para esta árvore
  documental. A árvore antiga foi preservada com um pointer LEGACY/STALE.
- `JarvisService`: `legacy_memory` e `memory_v2` explícitas; alias `memory`
  mantido por compatibilidade. V2 usa o embedder oficial nomic/768d.
- Brain: OFF usa apenas legado; SHADOW retorna legado e compara V2 em executor
  único; ON usa V2 e cai para legado em qualquer falha.
- SHADOW registra apenas contagens, top IDs, latência e estado; nunca conteúdo.
- Fast paths e VOICE_FAST simples não pagam retrieval. Pedido explícito de
  memória por voz continua elegível.
- Filtros `source_type`, `created_from` e `created_to` implementados.
- Default continua `shadow`; nenhuma ativação silenciosa de ON.
- Ollama `:11434` estava indisponível durante o fechamento; benchmark vetorial
  real não foi falsificado e ficou bloqueado apenas por infraestrutura.
- Regressão final após integração: 381 passed + 72 subtests, zero falhas
  (1 warning preexistente em `chart_strategy_test.py`).
- Banco real: 4 memórias + 4 embeddings intactos, `v2_memories=0`. O backend
  que já estava ativo registrou uma sessão operacional durante a missão
  (92 → 93); nenhuma sessão foi removida e nenhum corpus foi inserido.

## Qualidade e desempenho

Dataset temporário: 23 registros, grafo controlado, 15 queries variadas.
Legacy: Top-1 0,7333; Recall@5 0,9111; MRR 0,8333.
Hybrid: Top-1 1,0; Recall@5 1,0; MRR 1,0.
Hybrid: P50 142,5 ms; P95 249,3 ms.

Estágios em uma execução local sem provider vetorial:
FTS P50 6,8/P95 20,5 ms; vector 0/0 ms (disabled); graph 12,1/46,9 ms;
fusion 60,8/110,7 ms; total 123,7/202,7 ms.

## Validação

- M1.3: 44 passed.
- P1.1 restaurada + quality: 13 passed.
- Suíte completa final: 371 passed + 72 subtests, zero falhas (1 warning
  preexistente em `chart_strategy_test.py`, que retorna dict em vez de None).
- Banco de produção lido via SQLite `mode=ro`; 4 memórias legadas presentes.
- Startup final com `C:\GoldenAI\.venv`: providers READY, STT READY,
  VoiceService ativo e Memory V2 READY/schema 4. O startup acrescentou três
  sessões legadas (89 → 92) e alterou o hash do arquivo; as 4 memórias e seus
  4 embeddings permaneceram intactos, e `v2_memories` continuou vazio.

## Limitações

- Dataset de qualidade é pequeno e controlado; 100% não é promessa real.
- Teste comparativo não habilita provider vetorial; funcionalidade vector é
  coberta por testes com embedding falso e degradação.
- `source_type` e intervalo de datas não têm filtros dedicados na API M1.3.
- GraphRAG, dedup semântico e extração automática ficam para fases futuras.

## Próximo

Aguardar autorização. Não iniciar M1.4.
