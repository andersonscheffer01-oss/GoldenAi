# Auditoria do Golden Jarvis

## Arquitetura encontrada

O Golden atual é uma aplicação web local servida por `server_agent.py`. O Radar Macro está em
`market.html`, com módulos JavaScript separados para mercado, gráfico, análise por IA, centro
operacional e controle do computador. O arquivo `golden_runtime.db` já fornece armazenamento
SQLite. O backend possui chat, provedores de IA, visão, arquivos, informações do sistema, scanner,
backtest, risco e integração com MetaTrader 5.

## Recursos reaproveitados

- Rotas HTTP e servidor atual na porta 8765.
- Central PC e reconhecimento de voz no navegador.
- Edge TTS com vozes neurais em português.
- Banco SQLite existente.
- Integrações com Ollama, modelos externos, visão e MetaTrader 5.
- Serviços atuais de autorização para APIs mutáveis.

## Lacunas encontradas

- Comandos da Central eram regras diretas, sem registro tipado de ferramentas.
- Histórico da Central ficava apenas em memória.
- Não havia estado central do agente, modo de simulação ou catálogo de ferramentas.
- Confirmações críticas não formavam uma camada reutilizável.
- Voz depende da página aberta e da Web Speech API.
- Ainda faltam planner multietapas, cancelamento, verificação, memória semântica e agente Playwright.
- O backend central está grande e deve receber apenas adaptadores para novos módulos.

## Fundação implementada

- Pacote modular `jarvis_core`.
- `ToolRegistry` com descrição, parâmetros, timeout, risco e confirmação.
- Riscos LOW, MEDIUM, HIGH e CRITICAL.
- Política central e confirmações de uso único com expiração.
- Auditoria persistente na tabela `jarvis_audit`.
- Estados IDLE, PLANNING, WAITING_CONFIRMATION, EXECUTING e ERROR.
- Modo `GOLDEN_JARVIS_DRY_RUN=1`.
- Ferramentas iniciais de programas, caminhos, status do sistema, screenshot, bloqueio,
  desligamento e reinicialização.

## Riscos de regressão

- O servidor mantém um singleton da Central; alterações exigem reiniciar o servidor.
- Executáveis podem ter nomes diferentes conforme a instalação do Windows.
- Captura de tela depende do Pillow.
- Ações críticas continuam deliberadamente supervisionadas.

## Próximas fases

1. Configuração persistente de programas e permissões.
2. Serviço local de microfone, wake word e faster-whisper.
3. Planner e executor de tarefas compostas com cancelamento e verificação.
4. Atualização em tempo real por SSE ou WebSocket.
5. Visão contextual e Windows UI Automation.
6. Playwright em navegador isolado.
7. Memória curta, longa e semântica.
8. Ferramentas somente leitura para MT5, mantendo trading real bloqueado.
