# Conexão MT5 Aberta — Especificação

## Objetivo

Carregar dados e análises do MetaTrader 5 que já esteja aberto no Windows,
priorizando uma conta Hantec quando identificada e aceitando uma única outra
instância aberta quando não houver Hantec.

## Abordagens consideradas

1. Manter caminhos fixos: não atende instalações Hantec ou múltiplos brokers.
2. Descobrir processos MT5 abertos, anexar por caminho, identificar o broker
   pelo servidor/terminal e rejeitar ambiguidade: abordagem aprovada.
3. Exigir configuração manual por broker: previsível, mas não atende “qualquer
   um que estiver aberto” sem manutenção adicional.

## Contrato de segurança

- Somente APIs de leitura do MetaTrader 5 serão usadas.
- `execution_authority=NONE` em snapshots e erros de conexão.
- Não abrir, iniciar, matar ou fechar terminais.
- Não chamar `order_send`, `symbol_select` ou APIs de alteração de conta.
- Não alterar entrada, gerenciamento, risco, stop, take, breakeven ou trailing.
- Em múltiplas instâncias sem seleção inequívoca, falhar fechado com estado
  `SOURCE_UNAVAILABLE`/ambíguo; nunca escolher silenciosamente.

## Seleção

1. Enumerar processos ativos `terminal64.exe`/`terminal.exe` com `psutil`.
2. Anexar cada candidato pelo executável já em execução, sem auto-launch.
3. Ler `terminal_info()` e `account_info()` para obter servidor/empresa.
4. Se exatamente uma instância contém `hantec` na identidade, selecioná-la.
5. Caso contrário, selecionar apenas quando houver exatamente uma instância
   conectada; múltiplas instâncias conectadas retornam ambiguidade.
6. Os dados e análises legadas devem usar essa mesma conexão read-only.

## Resultado esperado

Painel, Análise GoldenAI, Operações, Performance e Histórico recebem o mesmo
estado observado do broker aberto, com servidor/broker visível, sem inferir
dados quando a conexão estiver indisponível.

