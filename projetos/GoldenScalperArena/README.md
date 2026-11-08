# Golden Scalper Arena

Laboratório isolado de comparação de cinco estratégias para XAUUSD. As Fases
1–4 são somente simulação: o projeto lê dados, cria snapshots reproduzíveis,
executa fills em carteiras virtuais e apresenta métricas no painel local. Ele
não altera o Golden Jarvis, não chama `OrderSend` e não envia ordens ao MT5.

## Estrutura atual

- `MQL5/GoldenArena.mq5`: exportador de ticks, especificação do símbolo e
  últimas barras fechadas de M1/M5/M15/H1 em `FILE_COMMON`.
- `Python/golden_scalper_arena/`: contratos imutáveis, cinco agentes,
  execução virtual, replay, journal SQLite, métricas, walk-forward, OOS,
  estresse e paper session simulada.
- `Python/tests/`: invariantes e testes de integração das Fases 1–4.
- `Dashboard/arena_dashboard.py`: painel HTTP local, somente leitura.
- `Dashboard/dashboard.html`: snapshot visual gerado para inspeção local.
- `Data/experiments/latest_report.json`: relatório sintético de demonstração;
  `DEMO_SYNTHETIC` não é histórico real nem validação de rentabilidade.

## Rodar os testes

Na pasta `Python`, com o ambiente do projeto:

```powershell
& C:\GoldenAI\.venv\Scripts\python.exe -m pytest -q tests
& C:\GoldenAI\.venv\Scripts\python.exe demo.py --count 120
& C:\GoldenAI\.venv\Scripts\python.exe ..\Dashboard\arena_dashboard.py `
  --report ..\Data\experiments\latest_report.json --port 8790
```

Abra `http://127.0.0.1:8790/`. O painel mostra ranking, resultado líquido,
profit factor, drawdown, sequências, validação temporal, estresse de custos e
proveniência. O cabeçalho deve indicar `READ-ONLY`, `SIMULATION-ONLY` e
`execution_authority=NONE`.

Para um replay com dados reais exportados pelo EA, primeiro valide o arquivo
CSV/JSONL com `data_validator.py`, confirme o fuso e a cobertura, construa
`MarketSnapshot` somente com barras fechadas e execute o pipeline. Dados
ausentes ou relógio não confirmado devem interromper novas entradas virtuais.

Com o EA `GoldenArena.mq5` ativo no gráfico do MT5, a ponte pronta para uma
execução de análise é:

```powershell
& C:\GoldenAI\.venv\Scripts\python.exe run_mt5_export.py `
  --directory "<Common>\Files\GoldenScalperArena" `
  --report ..\Data\experiments\mt5_latest_report.json `
  --server-offset-hours <FUSO_CONFIRMADO> --symbol XAUUSD
```

O parâmetro de fuso é obrigatório porque o exportador MQL5 grava o relógio do
servidor sem offset. A ponte não adivinha o fuso Hantec e não abre posições;
ela somente atualiza o JSON que o painel local lê.

O exportador deve ser compilado/instalado em um terminal de teste do MT5 e
executado em conta de simulação. O caminho de saída comum é
`<Common\Files>\GoldenScalperArena\`; confirme a origem e a cobertura antes de
usar qualquer arquivo no backtest.

O horário exportado pelo MT5 é preservado como relógio bruto do servidor. O
validador Python exige timestamp com offset explícito; ele rejeita o arquivo
quando o fuso não foi confirmado, em vez de converter o horário por suposição.

Na auditoria desta Fase 1, `MQL5/GoldenArena.mq5` foi compilado pelo
MetaEditor 5 local com `0 errors`; o log preserva um aviso de compatibilidade
de versão do MQL5 Market, que não impede o uso local do EA. O arquivo gerado
`GoldenArena.ex5` é um artefato local ignorado pelo Git.

## Fases implementadas

1. Fundação: contratos, validação, Bid/Ask, slippage, risco, limite diário,
   carteira segregada, journal e ponte MT5 read-only.
2. Estratégias: Momentum, Defesa, Rompimento, Pullback e Liquidity Sweep como
   callbacks determinísticos sobre dados observáveis.
3. Validação: replay com finalização, métricas líquidas, walk-forward
   cronológico, bloco OOS intocado e estresse 1,0×/1,5×/2,0×.
4. Painel/paper: relatório JSON, painel local e sessões prospectivas simuladas.

Nenhum resultado sintético recebe vencedor aprovado. A aprovação exige dados
reais suficientes, critérios fora da amostra, custos ampliados sem colapso e
paper trading sem falhas críticas.


