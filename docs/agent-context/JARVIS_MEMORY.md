# Memory Core — Fase 7

## O que foi feito
- Criado `jarvis_core/memory/` com SQLite, sessions, episodic, semantic, embeddings, retrieval e manager.
- `GoldenMemoryManager` é a interface principal do Jarvis para memória.
- `nomic-embed-text` é o embedding padrão local.
- Memória é persistida em SQLite com schema versionado.
- Busca semântica usa cosine similarity e ranking híbrido.
- Deduplicação básica evita repetições.
- Secrets/base64 são bloqueados antes de salvar.
- Memória recuperada é tratada como conteúdo não confiável.

## Status
- Backend validado: testes de memória 13/13, hardening 14/14, integração OK.
- APIs validadas em servidor real (2026-09-12): 4/4 PASS.
- APIs ativas: `/api/jarvis/memory/status`, `/search`, `/remember`, `/recent`.
- Chat com memória validado 5/5 no servidor (normalização de formato abreviado do LLM em `brain.py`).
- Deduplicação validada: repetições idênticas viram uma única memória.

## Correção importante (2026-09-12)
A route table do server_agent registrava 8 rotas de memória mas só 4 métodos existiam
(`health`, `registry`, `tool`, `clear-cache` eram referências órfãs → AttributeError).
As 4 rotas órfãs foram removidas; as 4 reais foram testadas individualmente.

## Limitações
- Não substitui AuditLog.
- Não salva toda conversa automaticamente.
- Semantic search só funciona bem com embeddings.
`
