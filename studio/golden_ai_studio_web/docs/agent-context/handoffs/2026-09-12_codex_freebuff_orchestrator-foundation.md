# Handoff Codex -> Freebuff — Orchestrator Foundation

## Estado

Fundação concluída: CentralOrchestrator, contratos tipados, SkillsRouter, ModelRouter,
provider health/fallback, privacidade, untrusted boundary, planner contract e rollout
`off/shadow/on`. Padrão `shadow`; fluxo seguro do Golden preservado.

## Arquivos

Criados `jarvis_core/orchestrator/*`, `tests/test_jarvis_orchestrator.py` e
`docs/agent-context/JARVIS_ORCHESTRATOR.md`. Alterados somente `brain.py`, `registry.py`
e `service.py` para integração compatível.

## Testes

79/79: orchestrator, hardening, memory, voice e market data. Nenhuma ação destrutiva.

## Não alterar

Registry continua fonte única; SecurityManager continua autoridade; memory é conteúdo não
confiável; nomic e modelos locais permanecem. Não ativar `on` globalmente sem validação real.

## Próximo trabalho mecânico

Freebuff pode adicionar painel/status e adapters simples de providers usando as abstrações
existentes. Não duplicar roteadores nem colocar execução dentro de provider.

## Próxima fase pesada

Task Manager + Planner + Background Jobs, somente mediante nova tarefa.
