# Handoff — Golden Memory M1.5 Research/Learning

Status: M1.5 concluída. Aguardar autorização; não iniciar próxima fase.

## Implementado

- `jarvis_core/memory/v2/research.py`
  - `ResearchProvider.search(query)` / `ResearchProvider.fetch(result)`.
  - `StaticResearchProvider` para dados manuais, testes e fontes já coletadas.
  - `ResearchEngine` para transformar resultados em evidências/candidatos.
  - `SourceTrustEvaluator` com níveis A/B/C/D/E.
  - `EvidenceRecord` com URL/ref, source_type, timestamp, title, domain, trust,
    confidence, basis e flags de prompt injection.
  - `KnowledgeCandidate` com estados `DISCOVERED`, `SUPPORTED`, `DISPUTED`,
    `VALIDATED`, `REJECTED`, `SUPERSEDED`.
  - `LearningEngine` para comparar candidatos com Memory V2/M1.4 e promover
    manualmente via `GoldenMemoryEngine.remember()`.
  - `ExpertProfile` para GAMING/AMD/WINDOWS/TRADING/CODING/GOLDEN/RESEARCH,
    armazenando referências/índices, não cópia de memória.
  - `LocalExperience` para contexto futuro de hardware/software/driver/projeto/
    jogo/versão/data/métrica/resultado.
- `jarvis_core/memory/v2/types.py`
  - novos `SourceType`: `OFFICIAL_DOCS`, `TECHNICAL_BENCHMARK`,
    `COMMUNITY_FORUM`, `WEB_ARTICLE`, `RESEARCH_PROVIDER`.
- `jarvis_core/memory/v2/consolidation.py`
  - trust de M1.4 atualizado para os novos source types.
- `jarvis_core/memory/v2/graph.py`
  - `source_trust()` reconhece fontes oficiais/benchmarks e web externa.
- `jarvis_core/memory/v2/__init__.py`
  - exports públicos M1.5.
- `tests/test_jarvis_memory_v2_m15.py`
  - 16 testes cobrindo fonte oficial, fórum, conflito, repetição em fóruns,
    prompt injection, promoção, rejeição, disputed claim, proveniência, expert
    profile, isolamento de projeto, privacy/SECRET, integração M1.4, provider
    failure, resultado duplicado e experiência local.

## Garantias

- GoldenMemoryEngine continua sendo a autoridade/single writer.
- Não foi criada nova base de memória.
- Conteúdo externo é sempre dado não confiável; não vira instrução.
- Nenhum aprendizado executa comando automaticamente.
- `SECRET` é bloqueado antes de pesquisa web e promoção.
- Pesquisa só ocorre quando chamada explicitamente; sem cron/autonomia.
- Nenhuma alteração em `jarvis_desktop/`.

## Validação

- `python -m pytest tests\test_jarvis_memory_v2_m15.py -q`: 16 passed.
- `python -m pytest tests\test_jarvis_memory_v2_m10.py tests\test_jarvis_memory_v2_m11.py tests\test_jarvis_memory_v2_m12.py tests\test_jarvis_memory_v2_m13.py tests\test_jarvis_memory_v2_m14.py -q`: 187 passed.
- `python -m pytest -q`: 412 passed, 72 subtests passed, 1 warning conhecido
  em `chart_strategy_test.py` (teste retorna `dict`).

## Limitações conhecidas

- Provider real de web ainda não conectado.
- Extração de claims é determinística e simples, sem LLM.
- Sem pesquisa periódica/autônoma.
- Sem Browser Agent, Computer Use, AMD control, Gaming optimization execution,
  OpenCodeSkill, WhatsApp, Obsidian FileWatcher/import, auto-modificação de
  código, GraphRAG completo ou UI Desktop V4.
