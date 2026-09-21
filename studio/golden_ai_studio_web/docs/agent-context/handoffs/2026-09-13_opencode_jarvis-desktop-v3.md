# Handoff — Golden Jarvis Desktop V3 (Futuristic HUD)

## Estado

Redesenho visual total do app; **zero alteração** em backend, Brain,
Orchestrator, TaskManager, providers, VoiceService, endpoints, lógica de
chat, status reais, MT5/Radar, segurança. Orchestrator segue `SHADOW`.

## O que mudou (só UX)

- Janela frameless com title bar própria (GOLDEN JARVIS + ONLINE/SHADOW +
  _ ▢ × + TENTAR NOVAMENTE); drag, minimize, maximize/restore, QSizeGrip,
  tray preservado (X minimiza ou sai conforme config; nunca mata backend).
- Background tecnológico discreto (gradiente radial + grid + pontos +
  circuitos, estático, repinta só no resize).
- HUD protagonista com 4 anéis (fixo, ticks, rotativo, pulso), núcleo
  luminoso, animação de entrada ~900ms, comportamento por estado, 25fps
  com repaint só quando visível.
- Painéis `HudPanel` (cantos parciais + etiquetas SYS·01/NET·02/AI·03/
  TSK·04) com telemetria mono; barras ▰▱ só re-renderizam (sem animação
  contínua).
- Chat console integrado (sem bubbles): entradas com filete lateral +
  divisórias finas; command bar sci-fi (mic circular com pulso, input com
  glow no foco, SEND); route bar mono (normal/dev).
- Nav HUD fina (underline cyan no selecionado); janela 1450x880
  (mín. 1150x720); painéis laterais fixos 250px, centro elástico.
- Views Tasks/Skills/Radar/MT5/Config/DEV no mesmo tema.

## Arquivos

- `jarvis_desktop/theme.py` V3, `main_window.py` V3 (frameless)
- `widgets/`: `hud.py` V3, `hud_panel.py`, `backdrop.py`, `title_bar.py`,
  `status_panels.py` V3, `chat_view.py` V3
- `views/`: fundo console nas áreas de texto (lógica intacta)

## Validação

- `py_compile` OK (24 arquivos). Suíte **109/109 OK**, zero regressão.
- Screenshots offscreen analisados e refinados (pane sutil no console,
  saudação + hint, abas compactas). Tofu = fonte ausente só no offscreen;
  Segoe UI/Consolas existem no display real.
- App V3 real aberto (frameless) + backend ONLINE; cotação USD R$ 5,13 real.
- "abra ele": decisão determinística `CLARIFY conf 0.2 SHADOW` verificada
  em processo (nada executa); formulação via LLM hoje excede 45s
  (Ollama a 21s até p/ prompt trivial — lentidão ambiental, sem regressão;
  sem toque no backend por regra da fase).

## Limites

- Ollama lento no momento afeta chats que exigem geração longa.
- Sem EXE/LAN/anexos; sem som; sem OpenGL.

## Próximo

OpenCode Coding Skill / EXE posteriormente. Nada iniciado.
