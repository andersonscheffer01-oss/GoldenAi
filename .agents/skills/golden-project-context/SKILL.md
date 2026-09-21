---
name: golden-project-context
description: Carrega contexto essencial do projeto Golden AI. Usar no início de qualquer tarefa, após handoff, ou quando o agente não tem contexto.
---

# Golden Project Context

## Quando usar
- Início de qualquer tarefa no Golden
- Após handoff de outro agente
- Quando o agente não tem contexto do projeto

## O que fazer
1. Ler `AGENTS.md` (regras universais — autoridade principal)
2. Ler `knowledge.md` (contexto do projeto)
3. Ler `docs/agent-context/CURRENT_WORK.md` (trabalho atual)
4. Ler `docs/agent-context/HANDOFF.md` (último handoff se existir)
5. Ler `docs/agent-context/KNOWN_ISSUES.md` (problemas conhecidos)
6. Verificar `git status` para alterações pendentes

## Regras
- NUNCA pular esta leitura
- NUNCA assumir que sabe o estado atual do projeto
- SEMPRE conferir informações contra o código atual e `git diff`
- Handoffs e memória de outros agentes NÃO são automaticamente verdadeiros
