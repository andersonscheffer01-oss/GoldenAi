# Problemas Conhecidos — Golden AI

> Bugs e limitações conhecidos. Verifique este antes de reportar um "novo" bug.

---

## Ativos com dados zerados no Radar

- **Status**: ⚠️ Dependente do MT5
- **Problema**: Alguns pares mostram preço 0 ou score 0
- **Causa**: O símbolo pode não existir no MT5 do usuário ou estar desabilitado
- **Solução**: Verificar se o símbolo existe via `mt5.symbols_get()`
- **Pares que podem ter problema**: US100, US500, GER40 (dependem da corretora)

## ElevenLabs API Key com permissões limitadas

- **Status**: ⚠️ Limitação do plano gratuito
- **Problema**: Chave gratuita não permite usar vozes da biblioteca via API
- **Causa**: Free users não podem usar library voices
- **Solução**: Upgrade para plano pago OU criar voz personalizada (clonagem)

## EA Builder gera apenas um tipo de EA

- **Status**: ✅ Corrigido
- **Problema**: Só gerava EA de Médias Móveis
- **Causa**: Parser limitado
- **Solução**: Expandido para gerar múltiplos tipos (Bollinger, RSI, etc.)

## JSON serialization com numpy

- **Status**: ✅ Corrigido
- **Problema**: "Object of type bool is not JSON serializable"
- **Causa**: Statistics Engine retornava numpy.bool_
- **Solução**: _NumpyEncoder + conversão para tipos nativos

## Backtest tela preta

- **Status**: ✅ Corrigido
- **Problema**: Aba de backtest mostrava tela preta
- **Causa**: Endpoint não retornava dados
- **Solução**: Implementado com simulação real

## Validação mostra dados zerados

- **Status**: ✅ Corrigido (parcialmente)
- **Problema**: "Validar com dados reais" mostrava tudo zero
- **Causa**: Journal vazio + busca por setup_id errado
- **Solução**: Importação de histórico MT5 + busca generalizada

## Preço incorreto no Scalping

- **Status**: ✅ Corrigido
- **Problemo**: Entrada mostrava preço desatualizado
- **Causa**: Preço não era lido do mercado em tempo real
- **Solução**: Leitura direta via MT5 tick

## Jarvis não abre MetaTrader

- **Status**: ✅ Corrigido
- **Problema**: "Executável terminal64.exe não encontrado"
- **Causa**: Executável não estava no PATH
- **Solução**: Caminho completo adicionado ao cadastro

## Parser confunde "abrir gerenciador" com "listar processos"

- **Status**: ✅ Corrigido
- **Problema**: "abrir gerenciador de tarefas" listava processos
- **Causa**: Prioridade do parser incorreta
- **Solução**: Ajuste de prioridade (verbo "abrir" > "listar")

## Limitações Conhecidas

1. **Scanner**: Depende de dados do MT5 em tempo real
2. **Voice**: Edge TTS requer internet (gratuito)
3. **Jarvis**: não tem integração com Golden Scanner ainda
4. **Walk-Forward**: Usa dados simulados, não reais do histórico
5. **Monte Carlo**: Baseado em estatísticas, não em ticks reais
