# Plano: Golden Scalper Arena — fundação de simulação

> Implementação no worktree atual. Não tocar em módulos existentes do Jarvis.

## Tarefa 1 — Contratos e testes vermelhos

Criar testes para contratos de símbolo/tick/snapshot/sinal, validação de dados,
look-ahead e invariantes de risco. Rodar os testes e registrar a falha esperada
antes de implementar.

## Tarefa 2 — Validador e execução virtual

Implementar contratos imutáveis, validador de ticks e motor de execução
virtual. Garantir lado correto Bid/Ask, slippage, stop/take, duração, risco e
limites. O motor não deve importar nem chamar `MetaTrader5` ou `OrderSend`.

## Tarefa 3 — Arena isolada e journal

Implementar o coordenador que distribui a mesma leitura aos agentes sem
compartilhar carteira/resultado, além de journal SQLite append-only e métricas
mínimas de desempenho. Adicionar um contrato de agentes ainda sem sinais de
produção; estratégias ficam para a Fase 2.

## Tarefa 4 — Ponte MT5 somente leitura

Adicionar `MQL5/GoldenArena.mq5` como exportador de snapshots com
`SymbolInfoTick`/`CopyRates`, sem funções de trading. Compilar com evidência
real quando o MetaEditor estiver disponível; se não estiver, registrar a
limitação sem declarar compilação.

## Tarefa 5 — Verificação e handoff

Rodar testes da pasta, `py_compile`, verificar diff e procurar APIs de ordem.
Atualizar a documentação da Arena sem alterar `CURRENT_WORK.md` do Jarvis
até a Fase 1 estar concluída. Não fazer commit amplo nem reverter alterações
existentes.


