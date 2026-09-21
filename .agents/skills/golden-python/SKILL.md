---
name: golden-python
description: Regras para trabalhar com Python no projeto Golden AI. Usar ao modificar backend, engine, ou qualquer módulo Python.
---

# Golden Python

## Estrutura

```
studio/golden_ai_studio_web/
├── server_agent.py          ← Backend principal (6000+ linhas)
├── golden_scanner.py         ← Scanner (2000+ linhas)
├── statistics_engine.py      ← Motor estatístico
├── validation_engine.py      ← Validação
├── risk_engine.py            ← Risco
├── trade_journal.py          ← Diário
├── mt5_connector.py          ← MT5
├── position_manager.py       ← Posições
└── jarvis_core/              ← Jarvis 2.0
    ├── service.py            ← Agente PC
    ├── registry.py           ← Ferramentas
    ├── security.py           ← Permissões
    ├── audit.py              ← Auditoria
    └── models.py             ← Modelos
```

## Antes de alterar

1. Identifique o módulo afetado
2. Verifique imports que dependem dele
3. Verifique se o frontend consome o endpoint
4. Verifique se outros módulos importam dele

## Regras

- Não remova endpoints HTTP existentes
- Não altere assinaturas de funções públicas
- Não remova imports
- Não altere lógica de trading sem confirmação
- Rode syntax check após alteração
- Teste o servidor após alteração

## Padrões do projeto

- Funções começam com `_` para métodos privados
- Endpoints usam `_api_` prefix
- Handlers retornam `{"ok": True/False, "message": "..."}`
- Usar `threading.Lock` para SQLite
- Usar `subprocess.run` com `timeout` para comandos
