# Golden Scalper Arena — Fases 2–4

## Objetivo

Completar o laboratório isolado de XAUUSD com cinco estratégias objetivas,
replay determinístico, validação temporal, testes de custo e um painel local de
comparação. Todas as carteiras continuam virtuais e o laboratório não altera o
Golden Jarvis nem possui caminho de execução financeira.

## Decisões de segurança

- Toda execução permanece `simulation_only=true`, `read_only=true` e
  `execution_authority=NONE`.
- Os agentes recebem somente `MarketSnapshot`, que contém tick atual e barras
  fechadas. O contrato rejeita barras futuras e ticks fora de ordem.
- As cinco carteiras são independentes. O callback de um agente não recebe
  sinais, trades ou saldo de outro agente.
- Resultado sintético é marcado como `DEMO_SYNTHETIC`; não será apresentado como
  performance real ou como prova de rentabilidade.
- O painel lê um relatório JSON gerado pelo replay e não envia comandos ao MT5.

## Agentes

Cada agente é uma função determinística sobre o snapshot e a visão da sua
própria carteira:

1. Momentum: aceleração recente confirmada por ATR, sem extensão excessiva.
2. Defesa: rejeições repetidas de uma região; absorção é apenas inferida.
3. Rompimento: fechamento além da faixa anterior com persistência.
4. Pullback: tendência superior, retração controlada e retomada.
5. Liquidity Sweep: varredura observável de máxima/mínima e retorno à estrutura.

Stops, takes e volume são derivados da especificação do símbolo e da
volatilidade observada. Nenhum agente usa candle em formação ou resultado de
outro agente.

## Validação e painel

O replay registra sinais e trades, fecha posições abertas no fim da amostra com
`END_OF_RUN`, calcula métricas líquidas e ordena os cinco agentes. A esteira
inclui janelas walk-forward cronológicas, um bloco OOS final intocado, cenários
de spread/slippage ampliados e sessões prospectivas simuladas.

O painel local exibe origem/proveniência, autoridade, status de validação,
ranking, drawdown, profit factor, sequências, custos e avisos. Sem dados reais
válidos, ele mostra `SEM VENCEDOR`/`NÃO VALIDADO`, em vez de preencher números
inventados.

## Critério de conclusão

As fases estarão implementadas quando testes automatizados cobrirem os cinco
agentes, isolamento, ausência de look-ahead, replay, métricas, walk-forward,
estresse, sessão simulada e contrato do painel; e um replay sintético puder
gerar `Data/experiments/latest_report.json` para inspeção visual/local.

