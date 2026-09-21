# Handoff — Hermes Agent Read-Only Audit (2026-09-13, Opencode)

## Escopo cumprido

Auditoria read-only (clone depth-1, só leitura). Nenhum arquivo funcional
do Golden tocado; nada instalado/executado; nenhum código copiado.
Suíte Golden não rodada (sem mudança funcional).

## Referência

`C:\GoldenAI\references\HermesAgent` · main · HEAD `422bc9b` (2026-09-13)
· MIT · ~4247 arquivos de teste · entry `run_agent.py`.

## Documento principal

`docs/agent-context/HERMES_AGENT_ARCHITECTURE_AUDIT.md` — fluxos MEMORY e
SKILLS com evidências arquivo→símbolo→comportamento, tabela 19 áreas,
MUST/SHOULD/CAN-WAIT/DO-NOT p/ M1.1, Obsidian YES, source-of-truth mantida,
top 10 adotar / top 10 não copiar.

## Achados que mais importam p/ Golden

1. FTS5 session search maduro (demote cron p/ recall-blindness) — ADAPT M1.3.
2. Snapshot congelado + sidecar cercado — ADAPT na injeção de contexto.
3. Checkpoint fail-closed pré-compactação — ADOPT quando houver compaction.
4. Skills ≠ memória declarativa (frontmatter+scripts+testes+curator) —
   manter PROCEDURAL separado; skills Golden = M-futuro.
5. Segurança Hermes declaradamente não-boundary — Golden já melhor
   (não regredir p/ heurísticas dispersas).
6. Divergência docs×código: recall "com LLM" é sem LLM (só DB).
7. Backoff exponencial + tombstone — adaptar sobre tri-state Golden.

## M1.1

Nada estrutural obrigatório. SHOULD: regra anti-divergência
(single-writer + drift-detect) antes do vault editável. Vault Obsidian
segue válido como projeção humana do canônico SQLite.
