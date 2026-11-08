# Golden Scalper Arena — Fase 1

## Objetivo

Criar um laboratório isolado para simulação de XAUUSD com cinco carteiras
virtuais independentes. A primeira entrega constrói a fundação verificável:
contratos de dados, validação de ticks, execução virtual, risco e journaling.
As estratégias só serão habilitadas depois que essa base passar pelos testes.

## Limites da primeira entrega

- Pasta isolada: `projetos/GoldenScalperArena/`.
- Nenhuma alteração no conector, no Risk Engine ou na execução do Golden Jarvis.
- Nenhuma chamada `OrderSend`, posição real, modificação de conta ou permissão
  de trading.
- O Expert Advisor do laboratório apenas lê ticks/rates e exporta snapshots
  identificados; a simulação virtual é feita pelo Python.
- Dados desconhecidos, especificação incompleta do símbolo e ticks inválidos
  interrompem a entrada virtual; não são convertidos em zeros.
- Cada agente receberá uma cópia imutável do mesmo snapshot e não terá acesso
  ao estado ou ao resultado dos outros agentes.

## Contratos

`Tick`, `Bar`, `MarketSnapshot`, `SymbolSpec`, `StrategySignal`,
`VirtualPosition`, `TradeRecord` e `PortfolioState` serão dataclasses imutáveis
ou controladas pelo motor. O snapshot terá `event_index`, `event_time`, Bid,
Ask, spread e barras fechadas. Nenhuma API de estratégia poderá pedir uma
barra/tick posterior ao `event_index` atual.

## Execução e risco

- Compra virtual preenche no Ask; venda virtual preenche no Bid.
- Saídas usam o lado oposto do mercado.
- Spread e slippage são custos explícitos e auditáveis.
- O tamanho é calculado somente quando `tick_size`, `tick_value`, contrato,
  volume mínimo/máximo/step e stop válido estão disponíveis.
- Limites padrão: saldo virtual de US$ 10.000, risco de 0,25%, perda diária
  de 1,5% e uma posição por agente.
- Stop, take, duração máxima e limite diário fecham virtualmente a posição;
  o motor nunca chama MetaTrader para executar.

## Evidência e validação

O journal SQLite terá registros de snapshots, sinais, fills virtuais e saídas,
com `run_id`, versão da estratégia, sequência do evento, timestamps, preços
Bid/Ask, custos, motivo e metadados do símbolo. A persistência é append-only
por contrato (sem `UPDATE`/`DELETE` no caminho normal).

Os testes iniciais cobrem: monotonicidade e look-ahead, Bid/Ask de entrada e
saída, spread/slippage, stop/take, limite diário, carteira isolada, snapshot
idêntico para cinco agentes e rejeição segura de dados ausentes.


