# Decisões

## 2026-09-11 — Registry como fonte única

O `ToolRegistry` é a única fonte de definição das ferramentas do Golden Jarvis.
O Brain não mantém catálogo independente. Toda ferramenta nova deve ser registrada uma vez
e sua representação para o LLM deve ser gerada por `get_llm_tools()`.

## 2026-09-11 — Execução fail-closed

Qualquer falha de JSON, schema, lookup ou tipo encerra o fluxo sem execução.
`open_any_exe` não é exposta ao modelo.

## 2026-09-11 — Memória é contexto não confiável

Memórias recuperadas nunca recebem autoridade de system prompt. O Brain recebe apenas Top-K
limitado e rotulado como dado não confiável. Sem `nomic-embed-text`, o fallback é busca lexical
declarada como degradada; vetores artificiais não representam busca semântica.
