# Handoff — Golden Memory M1.5.1 Real Web Provider

Status: M1.5.1 concluída. Aguardar autorização; não iniciar M1.6.

Atualização M1.5.1A: suporte de health check Brave adicionado, mas validação
real end-to-end ficou bloqueada porque `BRAVE_SEARCH_API_KEY` não está
configurada no processo, no ambiente de usuário nem no ambiente de máquina.
Configurar a variável fora do código e reiniciar o processo do Golden antes de
rodar o smoke real. A chave não deve ser registrada em logs/docs/handoff.

Atualização M1.5.1B: multi-provider web research implementado. O default agora
é `JARVIS_RESEARCH_PROVIDER=auto` com ordem Tavily → Groq Web → Brave. Chaves:
`TAVILY_API_KEY`, `GROQ_API_KEY`, `BRAVE_SEARCH_API_KEY`. Se nenhuma estiver
presente, o fluxo falha explicitamente com `missing_key`, sem dizer que
pesquisou.

## Implementado

- `jarvis_core/memory/v2/research.py`
  - `BraveSearchResearchProvider` pelo contrato existente
    `ResearchProvider.search/fetch`.
  - `build_research_provider_from_env()` com
    `GOLDEN_RESEARCH_PROVIDER=brave`, `BRAVE_SEARCH_API_KEY`,
    `GOLDEN_RESEARCH_TIMEOUT`, `GOLDEN_RESEARCH_RETRIES`,
    `GOLDEN_RESEARCH_MAX_BYTES` e `GOLDEN_RESEARCH_MAX_REDIRECTS`.
  - `SafeHTTPFetcher` sem browser automation, sem JavaScript e sem execução de
    conteúdo.
  - Proteção SSRF: bloqueia schemes não HTTP/HTTPS, localhost, loopback,
    privados, link-local, reserved/metadata e DNS que resolve para alvo interno.
  - Redirects limitados e validados antes de seguir; limites de timeout,
    tamanho e content type.
  - `sanitize_research_query`, normalização/dedup de URLs e telemetria segura.
  - `health_check()` do provider Brave e `research_provider_health_from_env()`
    para confirmar chave presente, endpoint acessível e autenticação válida sem
    expor segredo.
  - `TavilyResearchProvider`.
  - `GroqWebResearchProvider` separado do adapter de chat; exige URLs reais
    normalizáveis e passa pelo mesmo `SafeHTTPFetcher`.
  - `AutoResearchProvider` com fallback determinístico e telemetry
    `provider_selected`, `fallback_used`, `failure_reason` e
    `provider_failures`.
- `jarvis_core/service.py`
  - inicializa `LearningEngine(ResearchEngine(provider_env))`.
  - registra `web_research` e `web_research_learn`.
  - `web_research`: pesquisa/fetch/candidatos sem gravação.
  - `web_research_learn`: promove candidatos elegíveis via
    `GoldenMemoryEngine.remember()` e M1.4.
- `jarvis_core/orchestrator/orchestrator.py`
  - pedidos explícitos de pesquisa geram step determinístico WEB.
  - pedidos com "aprenda", "memorize" ou "guarde" usam
    `web_research_learn`.
- `jarvis_core/orchestrator/skills_router.py`
  - skill WEB agora expõe as ferramentas reais.
- `jarvis_core/memory/v2/__init__.py`
  - exports públicos do provider/fetch/sanitização.
- `tests/test_jarvis_memory_v2_m151.py`
  - cobertura M1.5.1 com mocks determinísticos e smoke real opcional.

## Garantias

- Não reimplementa M1.5.
- `ResearchEngine` não conhece Brave; só usa `ResearchProvider`.
- `LearningEngine` continua desacoplado de provider.
- Memory V2 continua single writer.
- Nenhum write direto em SQLite.
- Nenhum scraper frágil, browser automation ou shell web search.
- Conteúdo web é sempre dado não confiável.
- `SECRET` não sai para web; `SENSITIVE` passa por sanitização de query.
- Fast paths e VOICE_FAST simples continuam sem research.
- Nenhuma alteração em `jarvis_desktop/`.

## Validação

- `python -m pytest tests\test_jarvis_memory_v2_m151.py -q`:
  17 passed, 1 skipped, 7 subtests passed.
- `python -m pytest tests\test_jarvis_orchestrator.py tests\test_jarvis_runtime_integration.py tests\test_jarvis_voice_p1.py -q`:
  36 passed, 28 subtests passed.
- `python -m pytest tests\test_jarvis_memory_v2_m10.py tests\test_jarvis_memory_v2_m11.py tests\test_jarvis_memory_v2_m12.py tests\test_jarvis_memory_v2_m13.py tests\test_jarvis_memory_v2_m14.py tests\test_jarvis_memory_v2_m15.py tests\test_jarvis_memory_v2_m151.py -q`:
  220 passed, 1 skipped, 7 subtests passed.
- `python -m pytest -q`:
  429 passed, 1 skipped, 79 subtests passed, 1 warning conhecido em
  `chart_strategy_test.py`.
- M1.5.1A focado: `python -m pytest tests\test_jarvis_memory_v2_m151.py -q`:
  19 passed, 1 skipped, 7 subtests passed.
- M1.5.1A suíte completa: `python -m pytest -q`:
  431 passed, 1 skipped, 79 subtests passed, 1 warning conhecido em
  `chart_strategy_test.py`.
- Health real no ambiente atual:
  provider `brave`, key_present `False`, auth `missing_key`, endpoint
  `not_checked`.
- M1.5.1B focado: `python -m pytest tests\test_jarvis_memory_v2_m151b.py -q`:
  14 passed, 2 skipped.
- M1.5.1B regressão Memory V2:
  236 passed, 3 skipped, 7 subtests passed.
- M1.5.1B suíte completa:
  445 passed, 3 skipped, 79 subtests passed, 1 warning conhecido em
  `chart_strategy_test.py`.
- Health AUTO no ambiente atual:
  provider `auto`, order Tavily/Groq/Brave, auth `missing_key`, endpoint
  `not_checked`, availability false para Tavily/Groq/Brave.
- Revalidação 2026-09-20 focada M1.5.1B/M1.5.1/orchestrator/hardening:
  68 passed, 3 skipped, 56 subtests passed.
- Revalidação 2026-09-20 compatibilidade market prompt:
  1 passed.
- Suíte global 2026-09-20 não comparável ao baseline M1.5.1B:
  1411 passed, 24 skipped, 44 failed, 4 errors, 89 subtests passed. Falhas
  observadas em testes/fixtures/dependências ambientais fora do escopo
  M1.5.1B, incluindo smoke tests com fixtures ausentes, `sounddevice` ausente,
  testes de streaming/ordering assíncronos e fluxo desktop/core launcher
  alterado por outra frente.

## Limitações conhecidas

- Providers reais atuais: Tavily, Groq Web e Brave. Sem `TAVILY_API_KEY`,
  `GROQ_API_KEY` ou `BRAVE_SEARCH_API_KEY`, pesquisa real fica indisponível de
  forma explícita.
- Smokes reais opcionais foram pulados quando chaves/internet não estavam
  disponíveis.
- Fetch rico de PDF, ranking avançado, resumo LLM e extração sofisticada ficam
  para fases futuras.
- Sem cron/autonomous research, Gaming execution, AMD control, Computer Use,
  Browser Agent, Obsidian import, WhatsApp, trading execution ou UI Desktop V4.
