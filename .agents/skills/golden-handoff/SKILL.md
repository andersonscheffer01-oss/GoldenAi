---
name: golden-handoff
description: Transferir tarefas entre Freebuff e Codex preservando contexto completo. Usar quando uma tarefa precisa continuar em outro agente.
---

# Golden Handoff

## Quando usar
- Quando uma tarefa precisa continuar em outro agente
- Quando o usuário pedir "prepare handoff para codex"
- Quando o usuário pedir "continue o último handoff"

## Como criar um handoff

1. Ler `docs/agent-context/HANDOFF.md` (template)
2. Preencher o template com todos os campos obrigatórios
3. Salvar como arquivo datado em `docs/agent-context/handoffs/`:
   - Formato: `YYYY-MM-DD_HHMM_freebuff-to-codex_nome-da-tarefa.md`
   - Ou: `YYYY-MM-DD_HHMM_codex-to-freebuff_nome-da-tarefa.md`
4. Atualizar `docs/agent-context/HANDOFF.md` como ponteiro para o último handoff
5. Atualizar `docs/agent-context/CURRENT_WORK.md`

## Como retomar um handoff

1. Ler `docs/agent-context/HANDOFF.md` (ponteiro do último)
2. Ler o arquivo completo em `docs/agent-context/handoffs/`
3. Ler `AGENTS.md` e `knowledge.md`
4. Verificar `git status` e `git diff`
5. Conferir que os arquivos mencionados ainda existem e estão corretos
6. NUNCA confiar cegamente no handoff — sempre verificar contra código atual

## Regras
- Máximo 200 linhas por handoff
- NUNCA incluir senhas, API keys ou segredos
- NUNCA incluir logs enormes ou transcrições completas
- SEMPRE incluir arquivos modificados e próximos passos
- SEMPRE incluir git status
- Manter histórico em `docs/agent-context/handoffs/`
