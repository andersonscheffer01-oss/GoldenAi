# JARVIS / GOLDEN DEVELOPMENT ROADMAP

Roadmap derivado do Master Gap Audit de 2026-09-28. Ele e uma ordem de trabalho, nao autorizacao para executar mudancas. Baseline: `4195731`.

O Gate F1 (`dd152a1`) confirmou `JARVIS_CORE` como alvo canonico por evidencia de runtime, sem executar ownership switch. O primeiro gate de implementacao recomendado e um diagnostico read-only de ownership e resolucao do Task DB, antes de Security/Audit/ModelRouter convergence.

## Gate 0 - Consolidacao arquitetural

Objetivo: tornar explicito o owner de cada caminho sem alterar comportamento.

Prerequisites:

- preservar `device_registry.json` e todas as mudancas preexistentes;
- manter `server_agent.py` como launch path apenas ate o novo owner ser provado;
- inventariar imports e rotas diretas do stack raiz;
- escolher uma fonte de verdade para Security, Audit, ModelRouter e Plugins.

Definition of done:

- cada rota ativa aponta para um owner documentado;
- caminhos root/legacy tem status e criterio de aposentadoria;
- nenhum segundo Core e criado;
- nenhum comportamento funcional muda nesta fase.

## Gate 1 - Governanca de dados

Objetivo: parar a proliferacao de DBs sem apagar ou migrar dados automaticamente.

Acao futura autorizavel:

- confirmar o processo que deve possuir `C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db`;
- marcar DBs de teste/standalone por origem e lifecycle;
- adicionar health/read-only diagnostics para detectar base_dir divergente;
- somente depois propor migracao formal, com backup e aprovacao separada.

Nao fazer no Gate 1: deletar DB, compactar, resetar schema ou misturar historicos.

## Gate 2 - Security e Audit unificados

Objetivo: uma decisao de permissao e um formato de audit para o caminho ativo.

Reutilizar:

- `jarvis_core.security.SecurityManager`;
- `jarvis_core.audit.AuditLog`;
- scopes de browser read-only e Computer Use existentes;
- sanitizacao atual de segredo/payload.

Validacao minima futura:

- rotas diretas antigas passam pelo mesmo SecurityManager/AuditLog;
- denial/confirmation continuam fail-closed;
- nenhum token, audio, screenshot ou segredo entra no audit.

## Gate 3 - Orchestration e providers

Objetivo: um ModelRouter canonicamente responsavel por providers.

Reutilizar `jarvis_core/orchestrator/model_router.py`, policies e adapters existentes. Converter/remover handlers diretos apenas com testes de regressao equivalentes. OmniRoute permanece opcional conforme handoff anterior; nao reabrir investigacao Groq via OmniRoute nesta auditoria.

## Gate 4 - Voice checkpoint

Estado atual: `PAUSED_WITH_KNOWN_RESTRICTION`.
Proximo gate: `REAL_MIC_SIGNAL_PATH_INVESTIGATION`.

Pre-requisitos:

- nao alterar thresholds, device registry ou arquitetura de turn-taking;
- usar o dispositivo aprovado e o fluxo interativo existente;
- nao persistir audio/transcritos;
- aceitar PASS somente com fala humana confirmada e sinal mensuravel.

## Gate 5 - Capability validation

Depois de Core/Security/DB consolidados, validar em ordem:

1. browser read-only e consentimentos;
2. vision grounding sem acao destrutiva;
3. file/document intelligence em fixtures controlados;
4. MT5 read-only;
5. connectors pessoais somente quando houver adapter e approval model.

Cada gate deve produzir evidencia real, limites, audit e rollback; mocks nao devem ser reportados como validacao de mundo real.

## Following phases

- Fase A: consolidacao de ownership e docs/source of truth.
- Fase B: governanca de DB e observabilidade.
- Fase C: security/audit unificados.
- Fase D: ModelRouter/provider ownership.
- Fase E: retomada do Voice no checkpoint de mic.
- Fase F: capabilities opcionais (MCP, mobile, personal integrations, trading real) somente com gates proprios.

## Stop conditions

Parar e pedir nova autorizacao se uma fase exigir:

- hardware real, foreground, teclado/mouse, camera ou audio;
- migracao/delecao de banco;
- alteracao de `device_registry.json`;
- credenciais, contas, mensagens, ordens ou trades;
- instalacao/download de pacote ou modelo;
- bypass de SecurityManager;
- segundo Core/Gateway/Task system.
