# Manifesto da versão entregue

## Identificação exata

- Checkout em execução: `C:\GoldenAI`.
- Branch: `main`, acompanhando `origin/main`, `ahead 1, behind 4` no momento
  da inspeção.
- HEAD local: `71054ea0b6e0baf05c106ed88b2c4698f189e4fb` —
  `fix: keep Gemini Live as Jarvis voice provider`.
- O checkout estava limpo em `E:\CodexHome\worktrees\4e21\GoldenAI`, mas
  não é ele que o processo em execução usa. O checkout efetivo em
  `C:\GoldenAI` tinha alterações locais e arquivos não rastreados.
- Remote: `https://github.com/andersonscheffer01-oss/GoldenAi.git`.

## Relação Desktop/Core

- Desktop em execução: `C:\GoldenAI\studio\golden_ai_studio_web\dist\Jarvis\Jarvis.exe`.
- SHA-256 do `Jarvis.exe`: `E92EF4C762502D616945DD024A7005B9A442B7DB18B3F765550E004941C65AED`.
- Tamanho do executável: `11,052,989` bytes.
- O Desktop usa Qt WebEngine e navega para o Core; não embute o HTML do Painel.
- Core em execução: `C:\GoldenAI\.venv\Scripts\python.exe
  C:\GoldenAI\studio\golden_ai_studio_web\server_agent.py --port 8765
  --runtime-profile web-ai-safe`.
- UI efetivamente carregada: `https://127.0.0.1:8765/jarvis_ui/jarvis.html`.
- Health observado: HTTP `200`, perfil `web-ai-safe`, capabilities
  `CORE_LIFECYCLE_CONTROL` e `golden_market_live`.

## Prova do Painel

O Core respondeu HTTP `200` para o shell HTML e para
`/jarvis_ui/src/desktop-shell.js`. No arquivo JS servido, o bloco atual é:

- linha 5400: `Análise Profunda do Ativo`;
- linhas 5409–5410: `Monitoramento contínuo do ativo`;
- linhas 5414–5415: `Plano condicional monitorado`.

A janela JARVIS já aberta expôs as três strings na árvore de acessibilidade,
com `PAINEL · LEITURA SOMENTE`, `ANÁLISE · SEM EXECUÇÃO` e “Simulação
somente; sem envio de ordem.” O contrato local de `jarvis_core/arena_panel.py`
declara `read_only=true`, `simulation_only=true`, `execution_authority=NONE`,
`real_orders=false` e `trading_enabled=false`. O perfil `web-ai-safe` também
desabilita trading, MT5 mutável, teste de estratégia e compilação MQL5.

Hashes HTTP observados no runtime desta máquina:

- `/jarvis_ui/jarvis.html`: SHA-256
  `F96DF16C5675FDE578479D5D5EA0551AC9734E1FBED4708A1F2F4234341820C1`.
- `/jarvis_ui/src/desktop-shell.js`: SHA-256
  `AB2EFC445B3CE19FFFE9C36C7266F2A80D051F628611AE6E5CAA432B817A763F`.
- `/health`: SHA-256
  `40FFF8D9591F2DF8462910D451A0DD727CC9A236FFB499DE1C1206D9C5D79D0F`.

## GitHub e compatibilidade

Não foi encontrado no GitHub um commit contendo o Painel dessas três seções.
O commit solicitado como comparação,
[ad64512994976f1cc979608d3f36b128e6ca0133](https://github.com/andersonscheffer01-oss/GoldenAi/commit/ad64512994976f1cc979608d3f36b128e6ca0133),
e o `main` remoto ainda contêm o Painel antigo “GoldenAI — Análise do
Mercado”. O workflow desse commit gera `GoldenJarvisDesktop-ONEDIR.zip`, mas
esse pacote é compatível com o Painel antigo, não com o snapshot entregue.

O Desktop compatível com esta versão local é o `Desktop/Jarvis` incluído neste
ZIP, copiado do `dist/Jarvis` que estava em execução. O build do executável é
anterior às alterações do UI porque o binário carrega o UI servido pelo Core.

## Alterações locais relevantes

O snapshot não é um commit publicável; ele combina o HEAD acima com trabalho
local não publicado.

Tracked modificados na área do Core/Desktop/UI incluem:

`server_agent.py`; `jarvis_core/service.py`, `runtime_profile.py`,
`security.py`, `http_perimeter.py`, `mcp_client.py`, `brain.py`, `browser.py`,
`computer_use_mission.py`, `config.py`, `golden_bridge.py`,
`golden_analysis_repository.py`, `golden_trend_scan_repository.py`,
`memory/v2/__init__.py`, `memory/project_memory.py`, `memory/v2/research.py`,
`orchestrator/__init__.py`, `orchestrator/model_router.py`,
`orchestrator/models.py`, `orchestrator/orchestrator.py`,
`orchestrator/policies.py`, `orchestrator/providers.py`,
`orchestrator/skills_router.py`, `realtime_voice/audio_input.py`,
`realtime_voice/integration.py`, `task_manager/manager.py`,
`task_manager/scheduler.py`, `tools/market_readonly.py`,
`tools/ui_automation.py`, `jarvis_desktop/core_launcher.py`,
`jarvis_desktop/tray.py`, `jarvis_desktop/web_window.py`,
`jarvis_ui/jarvis.html`, `jarvis_ui/src/desktop-shell.css`,
`jarvis_ui/src/desktop-shell.js`, `jarvis_ui/src/desktop-voice.js`,
`jarvis_ui/src/gateway-adapter.js`, `jarvis_ui/src/styles.css` e
`jarvis_ui/src/trend-ranking-state.js`.

Não rastreados relevantes incluem `jarvis_core/arena_panel.py`,
`audio_experience.py`, `confirmation_presenter.py`, `credential_vault.py`,
`extension_catalog.py`, `gemini_live_provider.py`, `jarvis_core/http/`,
`market_multi_agent.py`, `mcp_external.py`, `memory/v2/conversation_store.py`,
`official_market_sources.py`, `operator_escape.py`, `personality_profiles.py`,
`tools/code_execution.py`, `tools/codex_adapter.py`,
`tools/image_generation.py`, `voice_confirmation.py`,
`voice_feature_flags.py`, `whatsapp_bridge.py`, `whatsapp_contract.py`, os
arquivos `xauusd_*` locais, `jarvis_desktop/release_updater.py` e os dois PNG
em `jarvis_ui/assets/`.

O pacote preserva o conteúdo de código dessas áreas relevantes, mas exclui
estado e dados locais. Nenhum desses arquivos foi publicado ou alterado por
esta entrega.

## Exclusões de segurança

Ficaram fora do ZIP: `.env`, `config/api_keys.json`, `certs/`, bancos
`*.db`/WAL/journal, `logs/`, `device_registry`, credenciais DPAPI, relatórios
da Arena, dados de backtest, arquivos MQL5 e qualquer chave privada. O Core
de destino deve gerar seus próprios certificados e criar seu próprio estado.

## Limites da validação

Foi confirmado nesta máquina que o processo existente abre como aplicativo
Windows e que o Core serve o Painel atual. Não foi feita uma segunda execução
para evitar conflito nas portas 8765/8766. No computador de destino ainda
devem ser validados CA/HTTPS, pareamento, GPU/Qt e a aparência pixel a pixel;
MT5 e envio de ordens não fazem parte da validação.
