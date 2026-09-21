# EA Canal + Pullback para MetaTrader 5

Expert Advisor em MQL5 para rompimentos de canal no M1, com canal por horário, canal automático por pullback ou os dois modos. O código usa somente candles fechados para formar canais, detectar tendência, reconhecer pullbacks e confirmar rompimentos.

## Regra central do pullback

O EA **não considera duas velas contrárias, isoladamente, como um pullback válido**.

Antes de iniciar a contagem, ele exige uma tendência conforme `ModoDeIdentificacaoDaTendencia`:

- `TENDENCIA_POR_MEDIAS`: EMA rápida acima/abaixo da EMA lenta.
- `TENDENCIA_POR_ESTRUTURA`: dois pivôs confirmados com máximas e mínimas ascendentes/descendentes.
- `TENDENCIA_POR_MEDIAS_E_ESTRUTURA`: médias e estrutura precisam concordar. Este é o padrão recomendado.

O último fundo confirmado de uma tendência de alta, ou o último topo confirmado de uma tendência de baixa, vira a **estrutura protegida**. Se qualquer candle fechado da correção ultrapassar esse pivô, o candidato e o canal automático são cancelados. A primeira vela e o pivô protegido ficam travados; o EA nunca reposiciona o canal retroativamente.

## Arquivos entregues

- `EA_Canal_Pullback_MT5.mq5`: código-fonte completo.
- `EA_Canal_Pullback_MT5.ex5`: binário compilado pelo MetaEditor 5.
- `compile.log`: relatório da compilação.
- `README.md`: instalação, backtest, presets e limitações.

## Instalação

1. No MetaTrader 5, abra `Arquivo > Abrir Pasta de Dados`.
2. Entre em `MQL5\Experts`.
3. Copie `EA_Canal_Pullback_MT5.mq5` para essa pasta.
4. Abra o MetaEditor, localize o EA no Navegador e pressione `F7`.
5. Confirme no painel de compilação: `0 errors, 0 warnings`.
6. Volte ao MT5, atualize a lista de Experts e arraste o EA para um gráfico.
7. Ative `Algo Trading` apenas depois de revisar símbolo, lote, risco, sessões e limites da corretora.

O campo `SimboloParaOperar` usa o nome exato da corretora. Se ela usa sufixo, informe por exemplo `XAUUSD.a`, `GOLD` ou o nome exibido na Observação do Mercado.

## Backtest recomendado

1. Abra o Testador de Estratégias com `Ctrl+R`.
2. Selecione o EA e o símbolo exato da corretora.
3. Use o modelo `Cada tick baseado em ticks reais`.
4. Use período gráfico `M1`; a tendência padrão é calculada no `M5`.
5. Comece com pelo menos 6 a 12 meses, incluindo períodos de alta e baixa volatilidade.
6. Configure comissão, spread variável e depósito próximos da conta real.
7. Ative o modo visual para conferir a âncora do pullback, o pivô protegido e a imutabilidade do canal.
8. Faça teste fora da amostra e forward test em conta demo antes de qualquer uso real.

No Strategy Tester, a persistência por variáveis globais do terminal é desligada automaticamente. Cada teste e cada passe de otimização começam com estado interno limpo, sem reutilizar canais de execução real ou de testes anteriores.

### Checklist visual do pullback

- Duas velas contrárias sem tendência definida não podem formar canal.
- No modo combinado, médias e pivôs precisam apontar para o mesmo lado.
- A linha estrutural implícita é o último pivô confirmado anterior à correção.
- Um pavio que ultrapasse a estrutura protegida cancela o pullback quando `CancelarSeRomperEstrutura=true`.
- Depois de formado, o canal mantém início, limites e tamanho originais.
- O rompimento usa candle fechado e nunca abre na própria vela ainda em formação.

## Configuração inicial conservadora para XAUUSD

- `PeriodoDoGrafico=PERIOD_M1`
- `ModoDeFormacaoDoCanal=CANAL_HORARIO_E_PULLBACK`
- `ModoDeIdentificacaoDaTendencia=TENDENCIA_POR_MEDIAS_E_ESTRUTURA`
- `PeriodoMediaRapida=9`
- `PeriodoMediaLenta=21`
- `TimeframeDaTendencia=PERIOD_M5`
- `BarrasParaAnalisarEstrutura=60`
- `ForcaDoPivoEstrutural=2`
- `MinimoDeVelasDoPullback=2`
- `MaximoDeVelasDoPullback=8`
- `CancelarSeRomperEstrutura=true`
- `PeriodoDoATR=14`
- `QuantidadeDeVelasParaMediaATR=10`
- `MultiplicadorDoATR=1.0`
- `ModoDoTakeProfit=TAKE_UM_CANAL`
- `ModoDoStopLoss=STOP_UM_CANAL`
- `AtivarFiltroATR=true`
- `ExigirReteste=false`
- `AtivarBreakeven=true`
- `AtivarTrailingStop=false`
- `ModoDeCalculoDoLote=LOTE_FIXO`
- `LoteFixo=0.01`
- `MaximoDeOperacoesPorDia=3`
- `MaximoDeOperacoesAbertas=1`
- `MagicNumber=123456`

Os valores em pontos dependem dos dígitos e do contrato oferecido pela corretora. Não reutilize limites de spread, ATR, stop ou take entre corretoras sem validar a escala de `SYMBOL_POINT`.

## Presets para pesquisa, não para promessa de resultado

### Estrutura mais rigorosa

- `ModoDeIdentificacaoDaTendencia=TENDENCIA_POR_MEDIAS_E_ESTRUTURA`
- `ForcaDoPivoEstrutural=3`
- `BarrasParaAnalisarEstrutura=80`
- `ExigirFechamentosContraTendencia=true`
- `CancelarSeRomperEstrutura=true`
- `ExigirRetesteDoCanalPullback=true`

### Mais sinais, com maior risco de ruído

- `ModoDeIdentificacaoDaTendencia=TENDENCIA_POR_MEDIAS`
- `MinimoDeVelasDoPullback=2`
- `ExigirFechamentosContraTendencia=false`
- `UsarPavioNaIdentificacaoDoPullback=true`
- `EntradaNoRompimentoOuReteste=ENTRADA_NO_ROMPIMENTO`

### Somente canal por horário

- `ModoDeFormacaoDoCanal=CANAL_POR_HORARIO`
- `RenovacaoDoCanal=RENOVAR_A_CADA_HORA`
- `VelasParaFormarCanal=10`
- `MetodoDeCalculoDoCanalHorario=CANAL_MAXIMA_MINIMA`

## Segurança e persistência

- Não usa martingale, grid ou aumento de lote após perdas.
- Filtra posições e histórico por símbolo e `MagicNumber`.
- Limita entradas por barra, hora, dia, posições abertas, perdas consecutivas e resultado diário.
- Calcula risco com `OrderCalcProfit`, que considera moeda da conta e especificações do contrato.
- Respeita volume mínimo, máximo, step, `StopLevel` e `FreezeLevel`.
- Salva canal, níveis da posição, alvos e breakeven nas variáveis globais do terminal.
- Ignora sinais antigos ao iniciar e espera a próxima barra fechada.
- O fechamento parcial envia uma ordem oposta vinculada ao ticket, compatível com contas hedge e netting.

## Painel gráfico

O dashboard usa objetos nativos do gráfico e apresenta tema escuro, cartões de ATR, spread e resultado diário, canal atual, tendência, fase do sinal, progresso do pullback, limites operacionais e o motivo do último bloqueio. As cores mudam conforme o estado do mercado e da operação.

- Use `PosicaoHorizontalDoPainel` e `PosicaoVerticalDoPainel` para mover o painel.
- Use `EscalaDoPainel` entre `0.70` e `1.60` para ajustar o tamanho.
- Clique no botão `-` do cabeçalho para recolher; clique em `+` para expandir.
- O painel atualiza em intervalos curtos para permanecer vivo sem redesenhar todos os objetos em cada tick.

## Limitações conhecidas

- A definição de estrutura usa pivôs confirmados; por isso existe atraso intencional de `ForcaDoPivoEstrutural` candles. Isso evita lookahead, mas reduz antecipação.
- O ATR e os valores em pontos variam muito entre símbolos e corretoras. Os padrões não são universais.
- Notícias são bloqueadas apenas pelos horários preenchidos manualmente; não existe conexão automática com calendário econômico.
- Em lotes mínimos pequenos, uma parcial percentual pode ficar abaixo do volume mínimo da corretora. Nesse caso, o EA fecha a posição restante em vez de enviar volume inválido.
- Em `CANAL_HORARIO_E_PULLBACK`, um canal automático válido pode substituir o canal horário atual; um canal automático ativo não é substituído pelo próximo canal horário até expirar ou ser invalidado.
- A compilação valida sintaxe e tipos, não comprova rentabilidade nem elimina riscos de execução, slippage, gaps e liquidez.

## Compilação validada

O arquivo foi compilado com o MetaEditor 5 instalado localmente. Resultado registrado em `compile.log`:

```text
Result: 0 errors, 0 warnings
```

Nenhuma regra foi otimizada para forçar lucro histórico. Valide diferentes períodos, spreads e regimes de mercado.

## Otimizacao robusta

- `Setup_8_Robusto_Base.set` endurece o setup 8 com risco de 0,5%, tendencia obrigatoria, bloqueio de pullback contra a tendencia e cancelamento por quebra estrutural.
- `Otimizacao_Robusta_Fase1.set` libera somente nove parametros para uma primeira pesquisa controlada.
- `OnTester()` calcula o resultado por posicao completa, incluindo parciais, e penaliza poucas amostras, fator de lucro baixo, drawdown alto e concentracao mensal.
- Consulte `GUIA_OTIMIZACAO_ROBUSTA.md` para o processo de forward, ticks reais, estresse e walk-forward.

## Relatorio de horarios no Diario

- `RegistrarCadaEntradaNoDiario=true` imprime data, hora do servidor, faixa horaria, origem do canal, lado, lote, preco, stop e take de cada entrada.
- `RegistrarResumoPorHorarioOnTester=true` imprime no fim do backtest as entradas, taxa de acerto, lucro, fator de lucro e expectativa das 24 faixas horarias.
- `MinimoDeEntradasParaDestacarHorario` evita destacar como melhor uma hora com amostra pequena. O padrao exige 10 entradas.
- A linha `MELHOR HORARIO` usa expectativa, tamanho da amostra e fator de lucro. Os horarios seguem o servidor da corretora, nao o relogio do computador.

## Histórico de correções

- `1.01`: libera o canal automático depois que a operação daquele pullback termina, impedindo que o bloqueio de reentrada paralise os sinais seguintes; também isola a persistência durante backtests e otimizações.
- `1.10`: adiciona criterio robusto de otimizacao por posicao completa, filtros de aprovacao e identificacao `AUTO`/`HORA` nos comentarios das ordens.
- `1.11`: registra cada entrada e apresenta no Diario o desempenho agrupado pelas 24 horas do servidor.
