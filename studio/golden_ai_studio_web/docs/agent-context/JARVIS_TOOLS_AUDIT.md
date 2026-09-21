# Auditoria de Ferramentas

- Total no Registry: 43
- Expostas ao Brain: 42
- Não expostas: 1
- Motivo: `open_any_exe` aceita caminho de executável e deve permanecer somente para fluxo interno supervisionado.
- Duplicação de catálogo no Brain: removida.
- Validação automática: nomes, handlers, riscos, confirmação, tipos de schema e assinatura.

Ferramentas HIGH e CRITICAL exigem confirmação. Ferramentas com risco dependente dos
argumentos são classificadas antes da confirmação.
