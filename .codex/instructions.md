# Codex — Instruções para Golden AI

> Configuração específica do Codex para trabalhar no projeto Golden AI.

## Regras Fundamentais

1. Ler `AGENTS.md` antes de qualquer tarefa
2. Ler `knowledge.md` para contexto do projeto
3. Consultar `docs/agent-context/CURRENT_WORK.md` para trabalho atual
4. Consultar `docs/agent-context/KNOWN_ISSUES.md` para problemas conhecidos
5. Consultar `docs/agent-context/DECISIONS.md` para decisões anteriores

## O que NÃO fazer

- NÃO modifique `config/api_keys.json`
- NÃO modifique `.env`
- NÃO exponha senhas ou chaves
- NÃO faça `git reset` ou `git clean`
- NÃO altere lógica de trading sem confirmação
- NÃO remova proteções de risco

## Formato de Handoff

Quando criar um handoff, use o template em `.agents/skills/golden-handoff.md` e salve em `docs/agent-context/HANDOFF.md`.

## Verificação Final

Antes de considerar tarefa completa:
1. Verificar `git diff` — o que mudou?
2. Verificar se o servidor funciona
3. Verificar se o frontend carrega
4. Verificar se nenhum segredo foi exposto
5. Atualizar `docs/agent-context/CURRENT_WORK.md`
