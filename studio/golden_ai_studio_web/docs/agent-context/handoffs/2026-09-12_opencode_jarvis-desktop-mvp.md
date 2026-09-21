# Handoff — Golden Jarvis Desktop Nativo (MVP)

## Estado

App PySide6 criado como cliente do backend; nenhum Brain/Orchestrator/Voice
novo. Patch mínimo e aditivo no `server_agent.py` (6 endpoints; nenhuma lógica
existente alterada). Orchestrator segue `SHADOW`.

## Arquivos

- `jarvis_desktop/` (`app.py`, `main_window.py`, `api_client.py`, `state.py`,
  `theme.py`, `workers.py`, `widgets/`, `views/`)
- `server_agent.py` (+6 rotas e handlers de leitura + cancel seguro)
- `tests/test_jarvis_desktop_api_client.py` (3 testes)
- `start_jarvis_desktop.bat`, `C:\GoldenAI\requirements.txt` (+PySide6)
- `docs/agent-context/JARVIS_DESKTOP.md`

## Validação

- `py_compile` OK em todos os arquivos novos + `server_agent.py`.
- Suíte: **99 tests OK** (96 existentes + 3 novos), zero regressão.
- Smoke real: backend ONLINE (MT5 True, Ollama True), mode `shadow`,
  17 skills, tasks reais, providers honestos.
- Chat: "qual a cotacao do dolar" → `get_exchange_rate` USD R$ 5,13.
- Chat: "abra ele" → pede esclarecimento, nada executado.
- Boot Qt offscreen: 7 abas, ONLINE, SHADOW.
- Backend + app deixados abertos (processos python vivos).

## Limites

- GPU/VRAM exibem N/D (backend não expõe).
- Pausar/retomar tasks não suportado (só cancelar).
- Providers OFFLINE até primeiro chat (registro lazy legado).
- Sem EXE; sem ingestão de anexos; sem LAN.

## Próximo

Embalagem EXE, ingestão de anexos, health probe periódico de providers,
Radar/MT5 profundos no desktop. Nada iniciado.
