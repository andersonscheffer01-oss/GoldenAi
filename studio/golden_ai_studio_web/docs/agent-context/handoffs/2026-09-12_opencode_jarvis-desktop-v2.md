# Handoff — Golden Jarvis Desktop V2 (status reais + visual)

## Estado

MVP evoluído sem reconstrução. Arquitetura central intacta; Orchestrator
`SHADOW`; sem Brain/TaskManager/modelos/providers/credenciais alterados.

## FASE A — dados corretos

- `server_agent.py`: `/api/jarvis/providers/status` com probe leve cacheado
  (45s, sem LLM). Ollama checado ao vivo; cloud = chave + `last_health` real
  do ModelRouter (ONLINE/RATE_LIMITED/DEGRADED/TIMEOUT/AUTH_ERROR/OFFLINE/
  UNKNOWN). Inclui `primary` (requested/actual/fallback/reason) para DEV.
- Novo `/api/radar/status` (leitura do monitor persistente: running,
  last_run, signal_counts).
- Desktop: `status_format.py` (máscara de conta, badges, radar/MT5/voz,
  contagem de tasks, barras, N/D honesto) + `gpu.py` (nome/VRAM via CIM
  com cache 60s; uso N/D quando indisponível).
- MT5 com conta mascarada; RADAR ACTIVE só com monitor rodando.

## FASE B — visual V2

- Header GOLDEN claro + JARVIS cyan + ONLINE + SHADOW MODE.
- HUD com QPainter (anéis, arco rotativo, pulso por estado, 20fps leve).
- Cards SISTEMA+SERVIÇOS / AI CORE+TASKS; barras CPU/RAM/GPU.
- Chat em bubbles + route bar (normal/dev com SKILL/PROVIDER/PROFILE/
  FALLBACK/TOOLS); erros amigáveis no normal e detalhe no dev.
- Views Tasks/Skills/Radar/MT5/Config(switches reais)/DEV reestilizadas.
- Janela 1400x850 (mín. 1100x700); abas compactas.

## Arquivos

- `server_agent.py` (providers estendido + `/api/radar/status`)
- `jarvis_desktop/`: `api_client.py` (+radar), `state.py` (+radar/gpu/dev),
  `theme.py` V2, `main_window.py` V2, `status_format.py`, `gpu.py`,
  `widgets/hud.py`, `widgets/status_panels.py`, `widgets/chat_view.py`,
  `views/*` V2
- `tests/test_jarvis_desktop_v2.py` (10 testes)
- Handoff MVP renomeado `freebuff` → `opencode` (conteúdo preservado)

## Validação

- `py_compile` OK. Suíte **109 tests OK** (99 + 10 novos), zero regressão.
- Smoke: providers `groq/openrouter/gemini UNKNOWN + ollama ONLINE`;
  PRIMARY groq→ollama com fallback + reason; RADAR running True com counts
  reais; GPU `AMD Radeon RX 9060 XT`; cotação USD R$ 5,13 real;
  "abra ele" com Brain aquecido pede esclarecimento (frio: timeout 45s,
  limitação conhecida, retry resolve).
- Screenshot offscreen: layout dark correto (tofu = falta de fonte no
  offscreen; Segoe UI existe no display real).

## Limites

- GPU util/VRAM usada N/D (sem fonte confiável; sem nvidia-smi em AMD).
- Pausar/retomar tasks não suportado. Sem EXE/LAN/anexos.
- Primeira chamada com Ollama frio pode exceder 45s (retry resolve).

## Próximo

OpenCode Coding Skill / EXE posteriormente. Nada iniciado.
