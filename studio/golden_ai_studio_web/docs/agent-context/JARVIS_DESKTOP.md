# Golden Jarvis Desktop — App Nativo Windows (PySide6/Qt)

> Cliente do backend Golden existente. Não cria Brain/Orchestrator/VoiceService.
> Orchestrator permanece `SHADOW`.

## Executar (dev, sem EXE)

```bat
start_jarvis_desktop.bat
```

Usa `C:\GoldenAI\.venv\Scripts\python.exe -m jarvis_desktop.app`.
Backend precisa estar em `http://127.0.0.1:8765` (`server_agent.py --port 8765`).

## Arquitetura

```text
MainWindow (shell fino)
→ JarvisApiClient (único HTTP; jarvis_desktop/api_client.py)
→ Golden Backend → CentralOrchestrator → SkillsRouter → ModelRouter
→ Planner/TaskManager → JarvisService → SecurityManager → Tools
```

- Nenhum request pesado no main thread (`workers.py` + `QThreadPool`).
- Polling leve/cacheado (`/api/status`, tasks, orchestrator, skills, providers).
- Chat nunca é usado para refresh.

## Backend (patch mínimo, aditivo)

Novos endpoints em `server_agent.py` (nenhuma lógica existente alterada):

| Endpoint | Tipo |
|---|---|
| `/api/jarvis/tasks/list` | leitura TaskManager real |
| `/api/jarvis/tasks/get` | leitura task + steps + eventos |
| `/api/jarvis/tasks/cancel` | cancelamento cooperativo (única mutação; não executa tools) |
| `/api/jarvis/orchestrator/status` | telemetria sanitizada (sem prompt/payload) |
| `/api/jarvis/skills/status` | catálogo real READY/PARTIAL/NOT_IMPLEMENTED |
| `/api/jarvis/providers/status` | saúde real com probe leve cacheado 45s + primary/fallback, sem chaves |
| `/api/radar/status` | monitor persistente real (running, last_run, counts) |

## V3 (2026-09-13) — Futuristic HUD, só visual

- Janela frameless + title bar própria + background tecnológico discreto.
- HUD protagonista (4 anéis, ticks, núcleo, entrada ~900ms, por estado).
- Painéis HUD (cantos parciais, etiquetas, telemetria mono), chat console
  integrado, command bar sci-fi, nav por underline, 1450x880.
- **Zero alteração** em backend/Brain/Orchestrator/TaskManager/providers/
  endpoints/lógica/status. SHADOW mantido.

## V2 (2026-09-12)

- Providers honestos sem depender do primeiro chat (Ollama ao vivo;
  cloud UNKNOWN com chave / OFFLINE sem chave até execução real).
- PRIMARY com requested/actual/fallback/reason; DEV estendido.
- RADAR ACTIVE só com monitor rodando; MT5 com conta mascarada;
  GPU AMD real (nome/VRAM via CIM) com N/D honesto no uso.
- Visual: header GOLDEN/JARVIS + SHADOW MODE, HUD animado leve,
  cards SISTEMA+SERVIÇOS / AI CORE+TASKS, chat bubbles, route bar
  normal/dev, janela 1400x850.

## UI

- Header `GOLDEN JARVIS ● ONLINE/OFFLINE` + `TENTAR NOVAMENTE` quando offline.
- Esquerda: CPU/RAM/DISCO reais; GPU/VRAM `N/D` honesto; GOLDEN/MT5/RADAR/VOICE/INTERNET reais.
- Centro: HUD + estados OFFLINE/ONLINE/OUVINDO/PENSANDO/PLANEJANDO/EXECUTANDO/
  AGUARDANDO CONFIRMAÇÃO/CONCLUÍDO/ERRO.
- Direita: modelo primário + GROQ/OPENROUTER/GEMINI/OLLAMA + tasks ativas.
- Chat real com linha `ROUTE/BRAIN/CONF`.
- Abas: CHAT | TASKS | RADAR | MT5 | SKILLS | CONFIG | DEV (SHADOW explícito).
- Tray: fechar minimiza; Sair não mata o backend.
- Drag-and-drop: recebe arquivos e informa que ingestão ainda não implementada.

## Limites

- Pausar/retomar tasks escondido (TaskManager só suporta cancelar).
- Providers mostram `OFFLINE` até o primeiro chat registrar adapters (comportamento legado).
- Sem EXE; sem LAN; sem Computer Use/WhatsApp/geração de mídia.

## P1 Voice Performance (2026-09-13)

A aba DEV mostra modelo/compute/beam, warmup, piso de ruído, limiar adaptativo, silêncio,
`utterance_id` e latências de captura, STT, normalização, primeiro áudio TTS e turno total.
São dados do VoiceService existente; nenhum segundo pipeline de voz foi criado.
