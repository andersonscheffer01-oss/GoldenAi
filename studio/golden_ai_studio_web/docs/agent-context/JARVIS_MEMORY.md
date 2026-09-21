# Golden Jarvis Memory Core

## Arquitetura

Fluxo: `consulta -> GoldenMemoryManager -> RetrievalService -> embedding real ou busca lexical -> Top-K -> Brain`.
O banco SQLite fica em `jarvis/golden_memory.db`; schema atual `memory_schema_version = 1`.
Cada operação abre e fecha sua própria conexão, usa parâmetros SQL, WAL, busy timeout e lock no manager.

## Tipos e schema

- Session: ciclo de vida de uma conversa, com metadata e encerramento explícito.
- Episodic: eventos não triviais associados à sessão.
- Semantic: fatos, preferências, projetos, decisões e conhecimento permanente.
- MemoryRecord persiste id, tipo, categoria, conteúdo, resumo, importância 0-100,
  confiança 0.0-1.0, source/source_id, session_id, namespace, timestamps, acessos,
  active, metadata e embedding quando disponível.

Namespaces validados: `jarvis` e `golden`; o schema aceita futuros namespaces.
Conflitos não são sobrescritos: afirmações diferentes permanecem ativas para resolução futura.

## Embeddings e fallback

Provider real: Ollama. Modelo: `nomic-embed-text`. Dimensão observada: 768.
Timeout configurável por `JARVIS_EMBEDDING_TIMEOUT` (15 s padrão); probe por
`JARVIS_EMBEDDING_PROBE_TIMEOUT` (3 s padrão). `status()` usa apenas estado cacheado
e não consulta o Ollama. `health_check()` é a verificação pesada explícita.

Quando o modelo está indisponível, nenhum vetor artificial é criado. O sistema permanece
operacional com ranking lexical e informa `DEGRADED`, fallback `lexical`.

## Retrieval

Top-K padrão 8, máximo 20. Contexto total limitado a 2.800 caracteres.
Ranking semântico: similaridade 50%, importância 30%, recência normalizada em 30 dias 20%.
No fallback lexical: correspondência textual 70% e recência em 7 dias 30%.
O contexto é marcado como `MEMÓRIA RECUPERADA` e conteúdo não confiável.

## Deduplicação

Espaços e caixa são normalizados. Duplicatas exatas são unificadas dentro do mesmo
namespace; similaridade semântica usa limiar 0,92 quando o modelo real está disponível.
O cache é por instância para não misturar bancos. Informações diferentes não são fundidas.

## Segurança

Memória permanente rejeita segredos reconhecíveis, data URI, base64 grande, binários,
conteúdo vazio e payload acima de 8.000 caracteres. Prompt injection recuperada continua
sendo dado sem autoridade e não pode invocar tools. Auditoria registra apenas IDs e metadata
pequena, usando a sanitização central do AuditLog; embeddings não são auditados.

## Integração

O Brain consulta memória apenas para entradas não triviais e recebe o resultado em mensagem
separada, abaixo das instruções privilegiadas. Não existe auto-memory geral.
As intenções explícitas podem usar `memory_remember`.

Tools no Registry: `memory_search` LOW, `memory_remember` MEDIUM e `memory_recent` LOW.
Desativação permanece interna. APIs: `/api/jarvis/memory/status`, `/search`, `/remember`, `/recent`.

## Limitações

- Conflitos são preservados, mas ainda não possuem relacionamento `superseded_by`.
- Busca usa candidatos em memória e não possui índice vetorial dedicado.
- O detector de segredos é conservador e não substitui um cofre de credenciais.
- Memória episódica não é gravada automaticamente para toda conversa.

## Regressões já resolvidas

Foram corrigidos anteriormente: indentação de database.py; `db` ausente; uso inválido de
`sqlite3.Row.db`; assinatura de `_session_row_to_dict`; campo embedding ausente;
namespace ausente em search; `memory_get` sem db; health check bloqueando com Ollama adormecido.
Nesta revisão também foram corrigidos status pesado, deadlock de health check, auditoria,
fallback artificial, cache global de dedup, isolamento por namespace e recência sem normalização.
