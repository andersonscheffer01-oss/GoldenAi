---
name: golden-mql5
description: Regras para trabalhar com MQL5 no projeto Golden AI. Usar ao modificar robôs, indicadores ou estratégias.
---

# Golden MQL5

## Estrutura

```
projetos/
├── EA_*.mq5                    ← Expert Advisors
├── Indicator_*.mq5             ← Indicadores
├── Script_*.mq5                ← Scripts
└── Include/                    ← Bibliotecas compartilhadas
```

## Regras Fundamentais

### NUNCA alterar lógica de entrada sem confirmação

Se a solicitação for APENAS gerenciamento (stop, take, trailing, etc.), NÃO toque na lógica de entrada.

### Separar claramente

```
ENTRADA         ← Quando e como entrar
GERENCIAMENTO   ← O que fazer depois de entrar
RISCO           ← Quanto arriscar
STOP            ← Onde sair com perda
TAKE            ← Onde sair com lucro
BREAKEVEN       ← Mover stop para entrada
TRAILING        ← Acompanhar preço
LIMITES         ← Máximo de operações/dia
```

### Risco Percentual

Ao calcular lote com risco percentual:
- Usar balance OU equity conforme regra da estratégia
- Verificar stop em pontos (não pips)
- Verificar tick_size e tick_value
- Verificar contract_size quando necessário
- Respeitar volume_min, volume_max, volume_step
- Normalizar lote conforme symbol_info

### Compilação

Sempre compilar após alteração:
```
metaeditor64.exe /compile:"arquivo.mq5" /include:"Include"
```

### Validação

Não considere código pronto porque compila sem erros ou parece correto.
SEMPRE teste no Strategy Tester antes de considerar pronto.

## Golden evidence workflow

This is the single canonical Golden MQL5 skill. Do not install or create a
second MQL5 skill authority. Keep specialist donor material as reference only.

- Inspect the existing `.mq5`/`.mqh`, inputs, includes, catalog identity, and
  current Git diff before proposing a change.
- Preserve entry logic, risk controls, SL/TP, breakeven, trailing, daily limits,
  and Magic Number behavior unless the user explicitly authorizes that change.
- Separate source facts, compiler facts, tester facts, and Jarvis inference.
  File existence is never compile evidence; metrics alone are never tester
  evidence.
- Every Golden-generated run must carry a unique `test_run_id` and, when
  available, `robot_id`, version, source/compiled artifact IDs and hashes,
  preset ID, normalized effective parameters, symbol, timeframe, tester model,
  date range, deposit, currency, leverage, terminal/tester build, lifecycle
  timestamps, status, result IDs, and provenance.
- Parameter origins are explicit: `EA_DEFAULT`, `PRESET`, `USER_DEFINED`,
  `OPTIMIZER_GENERATED`, or `JARVIS_SUGGESTED`. A suggestion is not approval.
- Bind runs before execution with a Golden-owned manifest and reconcile results
  by `test_run_id`, artifact hashes, robot identity, parameters, and tester
  configuration. Never associate by nearby filename alone.
- `COMPILE_SUCCESS` requires actual compiler log evidence. Preserve prior
  successful compile evidence when a later compile fails.
- Missing fields remain `NOT_PRESENT` or `UNKNOWN`; never fabricate metrics,
  builds, tester runs, or robot identity.
- Strategy Tester is simulation evidence, not live-trade authority. Any future
  adapter must stay below `JarvisService.execute_tool -> ToolRegistry ->
  SecurityManager -> AuditLog` and use bounded start/timeout/cancel/cleanup/
  stale-run handling.
- Historical unresolved artifacts are immutable. Do not rename, rewrite, or
  inject identity into old reports.

Canonical contracts and the read-only catalog owner live in:
`studio/golden_ai_studio_web/jarvis_core/mql5_evidence.py` and
`studio/golden_ai_studio_web/jarvis_core/robot_catalog.py`.
