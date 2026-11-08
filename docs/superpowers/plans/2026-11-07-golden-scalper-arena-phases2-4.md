# Plano: Golden Scalper Arena — Fases 2–4

## Tarefa 1 — Contratos vermelhos

Adicionar testes para sinais determinísticos dos cinco agentes, replay e
finalização, métricas de risco, walk-forward, estresse e o modelo de dados do
painel antes da implementação.

## Tarefa 2 — Cinco agentes independentes

Implementar estratégias puras sobre barras fechadas e tick atual. Cada sinal
deve ter stop/take válidos, motivo e índice observado; dados insuficientes
retornam `None` ou sinal inválido sem abrir posição.

## Tarefa 3 — Replay e validação

Integrar journal ao coordenador, fechar posições no fim da amostra, gerar
relatórios por agente, implementar janelas walk-forward, OOS reservado,
estresse de spread/slippage e sessão prospectiva 100% simulada.

## Tarefa 4 — Painel da Arena

Criar dashboard local isolado com relatório JSON, ranking dos cinco agentes,
métricas, validação, proveniência e bloqueios de segurança. Gerar uma amostra
sintética claramente rotulada para validar o fluxo sem alegar resultado real.

## Tarefa 5 — Verificação final

Rodar pytest, py_compile, replay de demonstração, inspeção do JSON/painel,
`git diff --check`, compilação do EA MQL5 já existente e varredura de APIs de
ordem. Não tocar no Jarvis ou em módulos de trading existentes.

