---
name: golden-safe-change
description: Regras para alterações seguras no projeto Golden AI. Usar antes de modificar qualquer arquivo do projeto.
---

# Golden Safe Change

## Antes de alterar qualquer arquivo

1. `git status` — Verificar alterações pendentes
2. `git diff` — Ver o que já mudou
3. Ler o arquivo inteiro antes de modificar
4. Verificar dependências (imports, chamadas)

## Regras por tipo de arquivo

### Python (.py)
- Rode `python -c "import py_compile; py_compile.compile('arquivo.py')"` após alteração
- Verifique se o servidor inicia
- Não remova imports existentes
- Não altere assinaturas de funções públicas

### HTML/JS
- Verifique se o JS compila
- Não quebre endpoints existentes
- Não remova funções JavaScript

### MQL5
- Nunca altere lógica de entrada sem confirmação
- Sempre compile após alteração
- Use `projects/` para desenvolvimento

### Config
- NUNCA modifique `config/api_keys.json`
- NUNCA modifique `.env`
- NUNCA exponha chaves em documentação

## Após alteração

1. Verificar se o servidor funciona
2. Verificar se o frontend carrega
3. Verificar `git diff` para confirmar o que mudou
4. Atualizar `docs/agent-context/CURRENT_WORK.md` se necessário
