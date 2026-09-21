# Golden Jarvis - Diagnostico da Arquitetura Atual

Data: 2026-08-30

## Escopo desta etapa

Esta etapa inspecionou o Golden AI Studio atual antes de implementar o Golden Jarvis.
Nenhuma rotina de trading, Scanner, MT5, estrategia, ordem ou backtest foi alterada.

Backup criado antes da documentacao:

`C:\GoldenAI\backups\golden_ai_studio_web_BEFORE_JARVIS_20260830_143627.zip`

## Projeto ativo encontrado

Diretorio principal do Golden usado no navegador:

`C:\GoldenAI\studio\golden_ai_studio_web`

URL local atual:

`http://127.0.0.1:8765/studio_v7.html`

## Arquivos encontrados no projeto ativo

- `_patch_scanner.py`
- `_rebuild_scanner.py`
- `analysis_engines.py`
- `app.js`
- `chart_audit.py`
- `chart_capture.py`
- `chart_data.py`
- `chart_strategy_test.py`
- `claude_provider.py`
- `cline_provider.py`
- `codex_provider.py`
- `dashboard_BEFORE_DASH_FIX_20260827.html`
- `dashboard.html`
- `Golden_Midas_VWAP.mq5`
- `golden_runtime.db`
- `golden_scanner.py`
- `index.html`
- `manifest.json`
- `meta_strategy.py`
- `mimo_strategy.py`
- `mini.html`
- `monitor_service.py`
- `mt5_backtest.py`
- `mt5_connector.py`
- `mt5_real_backtest.py`
- `mt5_trader.py`
- `position_manager.py`
- `risk_engine.py`
- `server_agent_BEFORE_DASH_FIX_20260827.py`
- `server_agent.py`
- `specialists.py`
- `statistics_engine_BEFORE_DASH_FIX_20260827.py`
- `statistics_engine.py`
- `strategy_audit.py`
- `strategy_engine.py`
- `strategy_panel.html`
- `studio.html`
- `studio_v7.html`
- `styles.css`
- `sw.js`
- `trade_journal_BEFORE_DASH_FIX_20260827.py`
- `trade_journal.py`
- `universal_backtest_ea.mq5`
- `validation_engine_BEFORE_DASH_FIX_20260827.py`
- `validation_engine.py`
- `walk_forward.py`

Tambem existe `__pycache__`, que contem apenas artefatos compilados Python.

## Backend atual

O backend ativo nao usa FastAPI ainda. Ele usa:

- `server_agent.py`
- `HTTPServer`
- `SimpleHTTPRequestHandler`
- `ThreadingMixIn`
- porta padrao `8765`

Entrada principal:

- `start_server(port=8765)`
- servidor local em `127.0.0.1`
- tela principal em `studio_v7.html`

Rotas importantes identificadas:

- `/api/status`
- `/api/chat`
- `/stream/chat`
- `/api/models/catalog`
- `/api/models/key`
- `/api/mt5/status`
- `/api/mt5/compile`
- `/api/mt5/backtest`
- `/api/mt5/full_analysis`
- `/api/mt5/positions`
- `/api/mt5/auto_trade`
- `/api/mt5/close_position`
- `/api/scanner/scan`
- `/api/scanner/radar`
- `/api/scanner/performance`
- `/api/scanner/details`
- `/api/meta_strategy`
- `/api/monitor/status`
- `/api/monitor/history`
- `/api/monitor/toggle`
- `/api/chart_data`
- `/api/chart_strategy_test`
- `/api/chart_audit`
- `/api/risk/status`
- `/api/risk/calculate_lot`
- `/api/risk/can_trade`
- `/api/validation/full`
- `/api/portfolio_backtest`

## Frontend atual

Arquivo principal:

`C:\GoldenAI\studio\golden_ai_studio_web\studio_v7.html`

Caracteristicas atuais:

- Interface single-file HTML/CSS/JS.
- Chat por texto.
- Upload de imagem, audio, video e documento no chat.
- Seletor de modelos.
- Painel de Meta-estrategia.
- Aba de graficos.
- Auditoria MT5.
- Chamadas `fetch()` para APIs locais.
- Historico de conversas principalmente em `localStorage`.

PWA atual:

- `manifest.json`
- `sw.js`

O PWA existe, mas ainda e basico e voltado ao Golden AI Studio, nao ao Golden Jarvis financeiro.

## Banco atual

Banco encontrado:

`C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db`

Tipo:

SQLite local.

Tabelas atuais:

- `monitor_runs`
- `signal_states`
- `signal_events`
- `sqlite_sequence`

Uso atual:

- Historico persistente de varreduras do radar.
- Estado atual de sinais.
- Eventos de mudanca de status de sinais.

Ainda nao existem tabelas financeiras do Jarvis, como gastos, comprovantes, categorias, orcamentos, faturas, bancos ou memoria pessoal.

## Ollama

O Ollama e usado de duas formas:

1. Biblioteca Python:
   - `from ollama import chat as ollama_chat`
   - chamadas diretas em `server_agent.py`

2. API local:
   - `http://127.0.0.1:11434/api/tags`
   - usada para detectar modelos locais.

Modelos ja mencionados/configurados no projeto:

- `qwen2.5-coder:14b`
- `qwen2.5vl:7b`
- `nomic-embed-text` planejado para memoria semantica.

## MetaTrader 5

Modulo central:

`C:\GoldenAI\studio\golden_ai_studio_web\mt5_connector.py`

Uso:

- `MetaTrader5` Python package.
- `mt5.initialize()`.
- `mt5.copy_rates_from_pos()`.
- `mt5.symbol_info()`.
- `mt5.symbol_info_tick()`.
- `mt5.positions_get()`.
- `mt5.order_send()`.

Modulos que usam MT5:

- `golden_scanner.py`
- `mt5_connector.py`
- `mt5_backtest.py`
- `mt5_real_backtest.py`
- `mt5_trader.py`
- `position_manager.py`
- `chart_data.py`
- `chart_audit.py`
- `analysis_engines.py`
- `specialists.py`
- `walk_forward.py`

Observacao critica:

Ja existem rotas capazes de enviar ou fechar ordem: `/api/mt5/auto_trade` e `/api/mt5/close_position`.
Para o Golden Jarvis, essas rotas nao devem ser chamadas automaticamente. Qualquer acao sensivel deve exigir confirmacao explicita.

## Segurança e permissoes atuais

Ha uma base de permissao em:

- `C:\GoldenAI\core\permissions\manager.py`
- `C:\GoldenAI\core\config\settings.py`
- `C:\GoldenAI\core\execution`

Configuracao padrao atual encontrada:

- `read_only=True`
- `write_enabled=False`
- `command_execution_enabled=False`
- `trading_mode="demo"`
- `mt5_integration_enabled=True`

Isso e positivo para o Jarvis, porque ja existe uma filosofia de bloqueio e aprovacao.

## Ponto correto de integracao do Golden Jarvis

O Golden Jarvis deve ser criado como modulo separado, sem substituir o Golden Scanner.

Ponto recomendado:

`C:\GoldenAI\jarvis`

Estrutura futura recomendada:

- `C:\GoldenAI\jarvis\backend`
- `C:\GoldenAI\jarvis\frontend`
- `C:\GoldenAI\jarvis\agent_pc`
- `C:\GoldenAI\jarvis\storage`
- `C:\GoldenAI\jarvis\integrations`
- `C:\GoldenAI\jarvis\docs`
- `C:\GoldenAI\jarvis\tests`

O backend Jarvis deve ser FastAPI, separado do `server_agent.py`.

Forma de comunicacao com o Golden atual:

- Criar um adaptador somente-leitura para consultar:
  - status do Golden Scanner
  - sinais monitorados
  - historico de eventos
  - posicoes abertas do MT5
  - status da conta MT5
- Bloquear por padrao qualquer chamada de ordem real.

## Decisao arquitetural recomendada

Nao transformar `server_agent.py` diretamente em Jarvis.

Motivo:

- O arquivo ja e grande e concentra chat, MT5, modelos, scanner, graficos, seguranca e sistema.
- Misturar financas pessoais, comprovantes, PWA, Open Finance e agente do PC nele aumentaria risco.
- O Golden Scanner precisa continuar estavel.

Melhor caminho:

1. Manter o Golden AI Studio atual rodando como modulo de trading.
2. Criar Golden Jarvis em FastAPI separado.
3. Fazer o Jarvis consultar o Golden por adaptadores internos ou HTTP local.
4. Migrar recursos comuns aos poucos, sem quebrar o radar.

## Primeira etapa de implementacao sugerida

Criar somente a fundacao do Jarvis:

- pacote Python separado;
- configuracao por `.env`;
- API FastAPI;
- SQLite local para desenvolvimento;
- modelos de usuario, sessao, logs e gastos;
- autenticacao basica segura;
- logs de auditoria;
- endpoint de saude;
- nenhum acesso bancario real;
- nenhuma ordem de trading.

## Testes executados nesta etapa

- Listagem do diretorio ativo do Golden.
- Localizacao de `studio_v7.html`.
- Localizacao de `server_agent.py`.
- Localizacao de `golden_runtime.db`.
- Inspecao do schema SQLite atual.
- Localizacao dos usos de Ollama.
- Localizacao dos usos de MT5.
- Criacao de backup zip antes da documentacao.

## Resultado

O Golden atual esta preservado.
O ponto mais seguro para evoluir para Golden Jarvis e criar um modulo separado em `C:\GoldenAI\jarvis`, integrado ao Golden Scanner apenas por consultas controladas e somente-leitura nesta fase.
