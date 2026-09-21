# Otimizacao robusta do EA Canal Pullback

Este processo procura estabilidade, nao o maior lucro isolado. Nenhum backtest garante resultado futuro.

## Arquivos

- `Setup_8_Robusto_Base.set`: versao conservadora do setup 8, pronta para validacao. Risco em 0,5%, tendencia obrigatoria, pullback contra a tendencia bloqueado e rompimento da estrutura cancelando o canal.
- `Otimizacao_Robusta_Fase1.set`: otimiza somente nove parametros ligados a forma e validade do pullback. Regras de seguranca, risco e gestao permanecem fixas.

## Criterio personalizado

No Testador de Estrategia, selecione `Custom max` como criterio de otimizacao. O `OnTester()` agrupa todos os deals de entrada, parciais e saida pelo identificador da posicao. Assim, uma posicao com quatro alvos conta como uma operacao completa, e nao como cinco negociacoes independentes.

Uma passagem e rejeitada com score negativo quando ocorrer qualquer condicao:

- menos de 100 posicoes completas;
- lucro liquido menor ou igual a zero;
- fator de lucro menor que 1,15;
- drawdown maximo da equidade maior que 15%;
- mais de 35% do lucro liquido concentrado no melhor mes.

Entre as passagens aprovadas, o score favorece recuperacao sobre drawdown, fator de lucro, quantidade de amostras e distribuicao mensal. Nao escolha somente o primeiro colocado: procure uma regiao de parametros vizinhos com resultados semelhantes.

## Fase 1 - pesquisa ampla

1. Use XAUUSD no M1 e carregue `Otimizacao_Robusta_Fase1.set`.
2. Selecione `1 minute OHLC` para a pesquisa inicial.
3. Use `Fast genetic based algorithm` e criterio `Custom max`.
4. Use pelo menos 15 meses para treinamento. Exemplo: 2025-01-01 a 2026-03-31.
5. Ative forward personalizado de 2026-04-01 a 2026-08-31.
6. Descarte resultados com poucos negocios, meses negativos muito concentrados ou forte diferenca entre backtest e forward.
7. Separe aproximadamente 20 combinacoes de uma mesma zona estavel, nao apenas picos isolados.

## Fase 2 - confirmacao por ticks reais

Reexecute as combinacoes selecionadas em `Every tick based on real ticks`, sem otimizar. Uma configuracao candidata deve manter:

- fator de lucro acima de 1,15 no periodo total e acima de 1,05 no forward;
- drawdown de equidade abaixo de 15%;
- pelo menos 100 posicoes completas no total;
- resultado positivo em mais de 60% dos meses;
- nenhum mes respondendo por mais de 35% do lucro total;
- curva sem salto unico responsavel pela maior parte do resultado.

Ao terminar um backtest individual, abra a aba `Diario` e procure por `HORARIO |`. Cada linha mostra quantidade de entradas, acerto, lucro, PF e expectativa daquela hora. A linha `MELHOR HORARIO` destaca apenas faixas com a amostra minima configurada. Durante a otimizacao em massa, mantenha esse relatorio desligado para nao sobrecarregar o Diario.

## Fase 3 - estresse

Repita o teste final com os mesmos parametros:

- atraso de execucao aleatorio e depois atraso fixo entre 100 e 300 ms;
- spread aumentado para 120 e 160 pontos em testes sinteticos comparaveis;
- comissao da conta real configurada;
- deposito semelhante ao que sera utilizado;
- risco de 0,25% e 0,50%;
- outro intervalo de mercado, sem nova otimizacao.

Rejeite a configuracao se uma pequena mudanca de spread, atraso ou parametro transformar o resultado em prejuizo. Isso indica ajuste excessivo ao historico.

## Walk-forward recomendado

Depois da primeira selecao, repita ciclos sem reutilizar o periodo futuro:

1. otimize 12 meses;
2. valide nos 3 meses seguintes;
3. avance a janela em 3 meses;
4. repita pelo menos quatro vezes;
5. mantenha apenas configuracoes aprovadas na maioria das janelas.

## Uso conservador

Antes da conta real, execute o EA em demonstracao por quatro semanas com `Setup_8_Robusto_Base.set`. Compare quantidade de sinais, spread, slippage e resultados com o teste de ticks reais. Comece com risco de 0,25% a 0,50%; nao use o perfil de 15% de drawdown como meta de risco.
