# Golden Scalper Arena dentro do Jarvis

## Intenção

Adicionar a Golden Scalper Arena como uma aba nativa do Jarvis, dentro da seção
`INTELIGÊNCIA E CONTROLE`, preservando as abas existentes e exibindo o relatório
da Arena no mesmo shell desktop.

## Abordagens consideradas

- Iframe para o painel HTTP da Arena: simples, mas cria uma segunda navegação e
  depende de outro processo/porta.
- Link externo para `dashboard.html`: não atende ao pedido de aba integrada.
- View nativa + endpoint GET do relatório: escolhido porque mantém o shell,
  autenticação existente, leitura somente e estado de indisponibilidade explícito.

## Limites

- A aba será somente leitura, `simulation_only=true` e
  `execution_authority=NONE`.
- O backend somente lerá `projetos/GoldenScalperArena/Data/experiments/latest_report.json`;
  não executará replay, MT5 ou ordens através da aba.
- Relatório ausente, inválido ou não validado será mostrado como estado
  indisponível/não validado, sem números demonstrativos inventados.
- As demais abas, endpoints e lógica de trading não serão removidos ou alterados.

