# Handoff — Task Manager Core isolado

## Estado

Task Manager Core concluído e isolado em `jarvis_core/task_manager/`. Reutiliza `PlanStep` do
Orchestrator, possui PlannerContracts, SQLite v1, eventos, background runner, timeout global,
cancelamento cooperativo, recuperação de interrupção e retomada sem repetir etapas concluídas.

## Testes

Task Manager 12/12. Regressão conjunta 91/91: Task Manager, Orchestrator, hardening, memória,
voz e market data. Nenhuma ação destrutiva foi executada.

## Limites

Não foi conectado ao Orchestrator, Brain, Service, Registry, API ou UI. Timeout/cancelamento
não encerram à força uma chamada de sistema já bloqueada. Plans SECRET exigirão referências.

## Integração futura

Depois que o Freebuff concluir providers/fallback/shadow/painel, conectar a saída TASK do
Orchestrator ao `TaskManager`, sempre executando cada tool pelo `JarvisService` e
`SecurityManager`. Não permitir executor direto nem expor SQL ao LLM.
