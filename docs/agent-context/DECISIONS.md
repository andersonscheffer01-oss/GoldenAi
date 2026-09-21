# Decisões do Projeto Golden AI

> Registro de decisões arquiteturais e técnicas importantes.
> Cada agente DEVE consultar este arquivo antes de tomar decisões similares.

---

## D-001: Backend em HTTPServer (não FastAPI)
- **Data**: 2026-08
- **Decisão**: Manter HTTPServer com ThreadingMixIn
- **Motivo**: Compatibilidade com código existente, sem dependências extras
- **Impacto**: Sem async nativo, mas funciona para o caso de uso

## D-002: Frontend single-file
- **Data**: 2026-08
- **Decisão**: HTML/JS/CSS em arquivos únicos
- **Motivo**: Sem build tools, sem node_modules, deploy simples
- **Impacto**: Arquivos grandes (170KB+), mas funcionais

## D-003: SQLite como banco principal
- **Data**: 2026-08
- **Decisão**: SQLite para todos os dados
- **Motivo**: Zero config, portátil, suficiente para uso local
- **Impacto**: Sem concorrência pesada, mas adequado

## D-004: Ollama como IA principal
- **Data**: 2026-08
- **Decisão**: Ollama local (qwen2.5-coder:14b)
- **Motivo**: Privacidade, sem custo, funciona offline
- **Impacto**: Depende de hardware local

## D-005: Jarvis como módulo separado
- **Data**: 2026-09
- **Decisão**: Jarvis 2.0 em jarvis_core/ separado do Scanner
- **Motivo**: Não arriscar o sistema de trading
- **Impacto**: Dois sistemas independentes

## D-006: 47 estratégias com IDs únicos
- **Data**: 2026-09
- **Decisão**: SCALP_BRK_RETEST, DAY_ORB, SWING_FIB, etc.
- **Motivo**: Rastreabilidade e gerenciamento
- **Impacto**: Mais complexidade, mas mais controle

## D-007: Risk Engine separado
- **Data**: 2026-09
- **Decisão**: Módulo próprio para risco
- **Motivo**: Isolar lógica crítica de trading
- **Impacto**: Mais modular, mais testável

## D-008: Validação com dados reais do MT5
- **Data**: 2026-09
- **Decisão**: Importar histórico do MT5 para calibrar validação
- **Motivo**: Dados reais > dados simulados
- **Impacto**: Validação mais confiável

## D-009: AGENTS.md como regras universais
- **Data**: 2026-09
- **Decisão**: Arquivo único com regras para todos os agentes
- **Motivo**: Consistência entre Freebuff e Codex
- **Impacto**: Todos os agentes leem as mesmas regras

## D-010: Handoffs em Markdown
- **Data**: 2026-09
- **Decisão**: Handoffs em docs/agent-context/HANDOFF.md
- **Motivo**: Simples, portável, sem dependências
- **Impacto**: Funciona sem ECC Memory Vault
