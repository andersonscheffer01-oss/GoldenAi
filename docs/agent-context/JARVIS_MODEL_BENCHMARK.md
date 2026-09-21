# JARVIS MODEL BENCHMARK — A/B de Modelos (Fase Benchmark)

> Data: 2026-09-12 · Origem: Freebuff · Status: PRIMEIRA RODADA CONCLUÍDA
> Modelo oficial do Jarvis: **qwen2.5-coder:14b — NÃO ALTERADO** (provado no final da execução)

## O que foi testado

Harness isolado: `tests/benchmark_jarvis_models.py` (marcado BENCHMARK/MANUAL, não roda na suíte).

- Usa o **mesmo system prompt do Brain oficial** e valida toda resposta com o
  **mesmo parser fail-closed** (`JarvisBrain._parse_llm_response` + `_validate_plan`)
  sobre o **schema real do ToolRegistry** (banco temporário).
- **Nenhuma tool é executada** — o benchmark valida apenas a DECISÃO do modelo.
- 24 testes: tool calling (T01–T04), multi-step (T05/T06/T18), visão (T07/T16),
  memória (T08/T15), fail-closed (T09/T10), ambiguidade (T11), PT-BR natural (T12–T16),
  chat (T17/T19), código (T20/T21), JSON estruturado (T22–T24).
- Testes críticos repetidos 3× (consistência): T01, T03, T09, T11, T18.
- Zero alteração no Golden: modelo padrão, configs, banco, embeddings e visão intocados.

## TABELA FINAL

| MODELO | LOCAL/CLOUD | TOOL | JSON | PT-BR | PLAN | FC | CODE | LATÊNCIA | CONSIST. | TOTAL |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:14b (baseline) | Local Ollama | 10.0 | 10.0 | 10.0 | 6.7 | 6.0 | 10.0 | 10 (1,97s) | 9.2 | **80.5** |
| qwen3.8-27b (Groq) | Cloud free | 10.0 | 10.0 | 10.0 | 6.7 | 10.0 | 10.0 | 10 (1,56s) | 9.6 | **85.8** |
| gpt-oss-120b (Groq) | Cloud free | 7.9 | 10.0 | 8.0 | 10.0 | 10.0 | 10.0 | 10 (0,81s) | 10.0 | **85.1** |
| cohere/north-mini-code:free (OpenRouter) | Cloud free | 2.1 | 10.0 | 0.0 | 0.0 | 10.0 | 7.5 | 10 (1,13s) | 9.6 | **54.3** |

Escala por categoria 0–10; total = soma das categorias (máx ~100, com uso-Jarvis ponderado).

## Perfis reais de falha

### qwen2.5-coder:14b (baseline local) — 80.5
- Tool/JSON/PT-BR **perfeitos** em comandos diretos e JSON estruturado.
- **Ambiguidade (fc 6.0):** em "Abra ele." chutou `open_program` com `name: "ele"` em 2/3 repetições.
- **Plano longo (T18, 4 etapas):** só 1/3 produziu plano válido (1 step sem ferramenta; 1 tool inexistente — barradas pelo validador).
- Fail-closed T09: recusou corretamente (`"Desculpe, mas não posso ajudar com isso."`).

### qwen3.8-27b (Groq) — 85.8 · melhor agente geral
- **Perfeito** em tool calling, JSON, PT-BR e fail-closed (sempre pediu esclarecimento em "Abra ele.").
- Mesma fraqueza do baseline em plano longo (T18: 1/3).
- Limitação prática: **rate limit do free tier** (429 com rajadas; requer espaçamento ~5s).

### gpt-oss-120b (Groq) — 85.1 · melhor planejador
- **PLAN 10.0** — único que montou o plano de 4 etapas do ambiente de trading (T18) de forma consistente.
- FC 10.0 (sempre esclareceu ambiguidade).
- Tool 7.9: em T07/T15 preferiu `steps` (multi-tool) onde 1 tool bastava; em T08 respondeu direto em vez de chamar `memory_search`.

### north-mini-code (OpenRouter) — 54.3 · NÃO serve como agente
- Tool 2.1, PT-BR 0.0, plan 0.0: quase nunca emitiu o JSON de tool no formato exigido.
- Ponto positivo: fail-closed honesto — **sempre recusou inventar tool** e pediu esclarecimento.
- Uso real futuro: fallback de chat/código no Golden Chat (papel atual), não agente.

## Melhores por categoria

| Categoria | Vencedor | Observação |
|---|---|---|
| Comandos simples | qwen3.8-27b (cloud) / baseline (local) | empate técnico em precisão; cloud 20% mais rápido |
| Planejamento | **gpt-oss-120b** | único com plan 10.0 |
| Código | todos (10.0) | sem diferencial |
| Latência | gpt-oss-120b (0,81s) | baseline 1,97s é suficiente para voz |
| Fail-closed | qwen3.8-27b / gpt-oss-120b | baseline chuta em ambiguidade |
| Custo/benefício | **baseline local** | grátis, offline, sem rate limit, 80.5 |

## Problemas encontrados durante o benchmark

1. **Groq 403 code 1010** (Cloudflare bloqueia rajadas) e **429 rate limit** no free tier — conhecidos do projeto (server_agent.py já documenta o 403). O harness precisou de espaçamento de 5s + retry com `Retry-After`.
2. Avaliador inicial do harness classificava recusa honesta como falha — corrigido (recusa explícita = PASS de segurança).

## RECOMENDO TESTAR QWEN3:8B LOCAL: **SIM**

Motivo: a família qwen3 apresentou o melhor perfil de agente do benchmark (qwen3.8-27b: 10/10 em tool, JSON, PT-BR e fail-closed). Uma versão 8B local pode igualar ou superar o baseline 14B em tarefas de agente, com menos VRAM (liberando espaço para visão) e menor latência. É o candidato natural a BALANCED local. Atenção: qwen3 tem modo *thinking* que precisará de tratamento no parser.

## RECOMENDO TESTAR GPT-OSS:20B LOCAL DEPOIS: **SIM**

Motivo: gpt-oss-120b foi o único planejador consistente (PLAN 10.0). Uma variante 20B local (~12–16GB quantizada) caberia na VRAM junto/alternando com o Brain e traria planejamento forte sem cloud. Prioridade 2, depois do qwen3:8b.

## Arquitetura futura SUGERIDA (conceitual — NÃO implementada)

```
FAST:      qwen3:8b local (a testar) | alternativo cloud: groq compound-mini
BALANCED:  qwen2.5-coder:14b (atual) → substituído se qwen3:8b vencer o A/B
DEEP/PLAN: gpt-oss-120b via Groq (cloud) | gpt-oss:20b local (a testar)
CODING:    qwen2.5-coder:14b (já validado no dia a dia)
VISION:    qwen2.5vl:7b (intocado — benchmark próprio futuramente)
MEMORY:    nomic-embed-text (INTOCADO — embeddings têm fase própria)
```

Model Router: **continua NÃO EXISTINDO** no código — sugestão apenas conceitual, sem implementação nesta fase.

## Prova de não-alteração

- MODELO OFICIAL TROCADO: **NÃO** (`JARVIS_LLM_MODEL`/default do brain.py intocado; servidores não reiniciados)
- MODELOS BAIXADOS/REMOVIDOS: **0** — nenhum `ollama pull/rm`
- Alterações funcionais no Golden: **0** (apenas `tests/benchmark_jarvis_models.py` + este relatório)
- Segredos: nenhum exposto; chaves lidas em memória via mecanismo existente (`config/api_keys.json`)
- Nenhuma tool executada; nenhum trade; nenhum dado sensível no relatório

## Reprodução

```bash
C:\GoldenAI\.venv\Scripts\python.exe tests/benchmark_jarvis_models.py          # todos
C:\GoldenAI\.venv\Scripts\python.exe tests/benchmark_jarvis_models.py baseline # só local
C:\GoldenAI\.venv\Scripts\python.exe tests/benchmark_jarvis_models.py groq     # só Groq
```
Último run bruto: `tests/benchmark_last_run.json` (sobrescrito a cada execução).
