# Handoff — Golden Jarvis Fase 7 Memória

## Estado

Fase 7.1 concluída. Memory Core SQLite validado e integrado minimamente ao Brain, Registry,
Service e quatro APIs. `nomic-embed-text` real confirmou dimensão 768; fallback lexical é
explicitamente degradado. Testes: hardening 14/14, memory 9/9, integração 4/4, total 27/27.

## Decisões

- Memória recuperada é conteúdo não confiável, nunca instrução privilegiada.
- `status()` é leve; somente `health_check()` consulta Ollama.
- Não há vetor artificial no fallback.
- Não existe auto-memory indiscriminado nem delete físico exposto ao LLM.

## Próximo passo

Não iniciar outra fase automaticamente. Dívidas P2: conflitos com `superseded_by` e índice
vetorial futuro. `psutil` falta apenas para plugin opcional externo ao Memory Core.
