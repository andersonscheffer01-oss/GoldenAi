# Golden Jarvis Desktop V4 — Fundação Visual (Fase 1)

> Cliente nativo PySide6/Qt para o backend Golden existente.
> **Fase 1 = apenas UI visual.** Nenhuma lógica de agente, Brain, Memory, M1.4, providers, STT/TTS, VoiceService, ToolRegistry, SecurityManager, Radar, MT5, trading, backend, rotas ou migrations alterados.

---

## Objetivo

Criar a fundação visual da nova interface do Golden Jarvis com **dois modos integrados**:

| Modo | Propósito | Visual |
|------|-----------|--------|
| **CONVERSA** | Interação por voz/texto com humanoide holográfico central | Dark navy, cyan/azul elétrico, dourado, figura central viva/fluida, chat abaixo |
| **CONTROLE** | Visão sistêmica: núcleo central + agentes/funções radiais | Núcleo Golden Jarvis, 12 funções conectadas, painel de tarefas, agentes ativos, projetos recentes, comando manual, ações rápidas |

**Troca de modo:** Botões claros `CONVERSA` / `CONTROLE` na title bar.

---

## Design System (Fase 1)

### Paleta

| Cor | Hex | Uso |
|-----|-----|-----|
| **BG_DEEP** | `#020610` | Fundo principal (quase-preto navy) |
| **BG_PANEL** | `#040c1a` | Painéis/cards |
| **BG_ELEVATED** | `#061224` | Elementos elevados (hover, active) |
| **CYAN** | `#00e5ff` | Accent principal (elétrico) |
| **CYAN_DIM** | `#007a8a` | Accent secundário/bordas |
| **CYAN_GLOW** | `#00ffff` | Glow/brilho |
| **BLUE_ELECTRIC** | `#1e90ff` | Azul elétrico (estados ativos) |
| **GOLD** | `#ffd700` | Detalhes dourados (brand, highlights) |
| **GOLD_DIM** | `#b8860b` | Dourado suave |
| **TEXT_PRIMARY** | `#e8f4fd` | Texto principal |
| **TEXT_SECONDARY** | `#8ab4d8` | Texto secundário/labels |
| **TEXT_MUTED** | `#4a6b8a` | Texto muted/desabilitado |
| **GOOD** | `#00ff88` | Sucesso/online |
| **WARN** | `#ffaa00` | Atenção/processando |
| **BAD** | `#ff4444` | Erro/offline |
| **GRID_LINE** | `#003344` | Grid sutil backdrop |

### Tipografia

- **Mono:** `Consolas, 'Cascadia Mono', 'JetBrains Mono', monospace` — telemetria, tags, dados técnicos
- **UI:** `Segoe UI, 'Inter', Arial, sans-serif` — labels, botões, chat
- **Display:** `Segoe UI, 'Inter', sans-serif` peso 800 — títulos grandes (GOLDEN JARVIS)

### Espaçamento (escala 4px)

`4, 8, 12, 16, 24, 32, 48, 64`

### Raio de borda

- `4px` — botões, inputs
- `8px` — cards, painéis
- `12px` — containers principais
- `50%` — elementos circulares (mic, avatar)

### Sombras/Glow

```css
glow-cyan: 0 0 24px rgba(0, 229, 255, 0.35), 0 0 48px rgba(0, 229, 255, 0.15);
glow-gold: 0 0 20px rgba(255, 215, 0, 0.3), 0 0 40px rgba(255, 215, 0, 0.1);
shadow-deep: 0 8px 32px rgba(0, 0, 0, 0.6), 0 2px 8px rgba(0, 0, 0, 0.4);
```

---

## Arquitetura de Componentes (Fase 1)

```
MainWindow (frameless, title bar custom)
├── TitleBarV4
│   ├── Brand (GOLDEN JARVIS)
│   ├── ModeSwitcher [CONVERSA] [CONTROLE]
│   ├── StatusNet (● ONLINE/OFFLINE)
│   └── WindowControls (min, max, close, drag)
├── CentralStack (QStackedWidget)
│   ├── ConversaMode
│   │   ├── BackdropV4 (grid + radial gradient + corner circuits)
│   │   ├── CentralAnimationArea (AnimationFoundation)
│   │   │   └── Estados: IDLE, LISTENING, PROCESSING, SPEAKING
│   │   ├── ChatPanel (reutiliza ChatWidget existente)
│   │   ├── InputBar (mic + input + send)
│   │   └── StatusFooter (CPU/RAM/GPU, providers, sys status)
│   └── ControleMode
│       ├── BackdropV4
│       ├── RadialCore (núcleo central + 12 nós radiais)
│       │   ├── Nós: Pesquisa, Memória, Projetos, Automação,
│       │   │        Análise, Documentos, Agenda, Internet,
│       │   │        Ferramentas, Trading, Design, [NÚCLEO]
│       │   └── Conexões animadas (linhas sutis)
│       ├── TaskPanel (tasks reais do backend)
│       ├── ActiveAgentsPanel (mock: UI preview)
│       ├── RecentProjectsPanel (mock: UI preview)
│       ├── ManualCommandBar (input + send)
│       └── QuickActionsGrid (botões de ação)
└── SystemTray (existente)
```

---

## Componentes Reutilizáveis (Novos)

| Componente | Arquivo | Responsabilidade |
|------------|---------|------------------|
| `ThemeV4` | `theme_v4.py` | Paleta, stylesheet global, helpers de cor |
| `TitleBarV4` | `widgets/title_bar_v4.py` | Brand, ModeSwitcher, WindowControls, drag |
| `ModeSwitcher` | `widgets/mode_switcher.py` | Toggle CONVERSA/CONTROLE com animação |
| `BackdropV4` | `widgets/backdrop_v4.py` | Fundo tecnológico (grid, gradient, circuitos) |
| `HudPanelV4` | `widgets/hud_panel_v4.py` | Painel com cantos tecnológicos, tag, body |
| `AnimationFoundation` | `widgets/animation_foundation.py` | Canvas central p/ IDLE/LISTENING/PROCESSING/SPEAKING |
| `RadialCore` | `widgets/radial_core.py` | Núcleo + 12 nós radiais (CONTROLE) |
| `StatusFooter` | `widgets/status_footer.py` | CPU/RAM/GPU, providers, serviços (CONVERSA) |
| `QuickActionsGrid` | `widgets/quick_actions.py` | Grid de botões ação (CONTROLE) |
| `ManualCommandBar` | `widgets/manual_command.py` | Input comando manual (CONTROLE) |

---

## Estados da Animação Central (AnimationFoundation)

| Estado | Visual (Fase 1 - leve, QPainter) |
|--------|----------------------------------|
| **IDLE** | Núcleo pulsante lento (0.8Hz), anel respiração, partículas mínimas |
| **LISTENING** | Anel externo expansivo (2.4Hz), waveform mic em tempo real, cyan brilhante |
| **PROCESSING** | Anéis girando (3Hz), segmentos "pensando", gold accent, partículas centrípetas |
| **SPEAKING** | Waveform radial sincronizado com áudio (2Hz), cyan+gold, núcleo expandido |

**Performance alvo:** UI ociosa < 2% CPU, 25-30 FPS animação, sem WebGL/vídeo.

---

## Dados: Real vs Mock (Fase 1)

| Área | Fonte | Nota |
|------|-------|------|
| CPU/RAM/GPU | Real (`/api/status`, `gpu.py`) | Já funcionando |
| Providers | Real (`/api/jarvis/providers/status`) | Já funcionando |
| MT5/Radar/Voice | Real (endpoints existentes) | Já funcionando |
| Tasks | Real (`/api/jarvis/tasks/list`) | Já funcionando |
| Chat | Real (`/api/jarvis/chat`) | Já funcionando |
| Agentes ativos (CONTROLE) | **Mock (UI Preview)** | Marcado claramente |
| Projetos recentes (CONTROLE) | **Mock (UI Preview)** | Marcado claramente |
| Ações rápidas (CONTROLE) | **Mock (UI Preview)** | Placeholders visuais |

---

## Janela & Controles (Correções Obrigatórias)

| Controle | Comportamento |
|----------|---------------|
| **Minimizar** | `showMinimized()` — funciona em frameless |
| **Maximizar** | `showMaximized()` / `showNormal()` — toggle correto |
| **Restaurar** | Mesmo botão do maximizar (toggle) |
| **Fechar** | `request_close()` → tray (se ativo) ou `close()` |
| **Drag** | TitleBar inteira (exceto botões) — `mousePress/Move/ReleaseEvent` |
| **Resize** | `QSizeGrip` no canto inf. dir. + `setMinimumSize(1150, 720)` |
| **High DPI** | `QT_AUTO_SCREEN_SCALE_FACTOR=1`, `QT_ENABLE_HIGHDPI_SCALING=1` |

---

## Abas Existentes (Preservadas)

As 7 abas atuais permanecem acessíveis **em ambos os modos** via `QTabWidget` (ou navegação lateral futura):

1. **CHAT** — `ChatWidget` (existente, funcional)
2. **TASKS** — `TasksView` (existente, funcional)
3. **RADAR** — `OpsView("radar")` (existente)
4. **MT5** — `OpsView("mt5")` (existente)
5. **SKILLS** — `SkillsView` (existente)
6. **CONFIG** — `ConfigView` (existente, switches reais)
7. **DEV** — `DevView` (existente, telemetria completa)

---

## Testes (Fase 1)

- Iniciar app: `start_jarvis_desktop.bat`
- Verificar: janela abre, title bar funcional, drag funciona
- Alternar modos: CONVERSA ↔ CONTROLE transição suave
- Verificar: HUD central anima nos 4 estados (mock trigger)
- Verificar: chat funciona (digitar + enter → backend)
- Verificar: abas existentes carregam dados reais
- Verificar: resize, maximize, minimize, close, tray
- High DPI: testar 100%, 125%, 150%, 200% (Windows Settings)
- Resoluções: 1366×768, 1920×1080, 2560×1440

---

## Limitações Conhecidas (Fase 1)

- Animação central usa QPainter leve — versão final virá na Fase 2
- Agentes/Projetos/Ações em CONTROLE são mock (UI preview)
- Nenhum atalho global criado ainda (faremos após aprovação visual)
- SHADOW mode mantido no orchestrator (não alterado)
- Backend não modificado

---

## Próximos Passos (Pós-Aprovação)

1. **Fase 2:** Animação central refinada (partículas fluidas, shaders leves, transições de estado suaves)
2. **Fase 3:** Ligar CONTROLE a dados reais (agents status, projects DB, quick actions → backend)
3. **Fase 4:** Atalhos globais, overlay, always-on-top, hotkeys
4. **Fase 5:** Polish, acessibilidade, performance, packaging (EXE/MSIX)

---

## Arquivos Principais (Fase 1)

```
jarvis_desktop/
├── app.py                    # Entry point (inalterado)
├── main_window_v4.py         # Nova MainWindow com dois modos
├── theme_v4.py               # Novo tema V4
├── state.py                  # Estado (inalterado)
├── api_client.py             # Cliente API (inalterado)
├── workers.py                # Workers (inalterado)
├── status_format.py          # Formatters (inalterado)
├── gpu.py                    # GPU info (inalterado)
├── widgets/
│   ├── __init__.py
│   ├── backdrop.py           # V3 (existente)
│   ├── backdrop_v4.py        # NOVO - fundo V4
│   ├── chat_view.py          # Existente
│   ├── hud.py                # V3 HUD (existente)
│   ├── hud_panel.py          # V3 (existente)
│   ├── hud_panel_v4.py       # NOVO - painel V4
│   ├── status_panels.py      # Existente
│   ├── title_bar.py          # V3 (existente)
│   ├── title_bar_v4.py       # NOVO - title bar V4
│   ├── mode_switcher.py      # NOVO - toggle CONVERSA/CONTROLE
│   ├── animation_foundation.py  # NOVO - animação central 4 estados
│   ├── radial_core.py        # NOVO - núcleo radial 12 nós
│   ├── status_footer.py      # NOVO - footer CONVERSA
│   ├── quick_actions.py      # NOVO - grid ações CONTROLE
│   └── manual_command.py     # NOVO - barra comando manual
├── views/
│   ├── __init__.py
│   ├── config_view.py        # Existente
│   ├── dev_view.py           # Existente
│   ├── ops_view.py           # Existente
│   ├── skills_view.py        # Existente
│   ├── tasks_view.py         # Existente
│   ├── conversa_view.py      # NOVO - view modo CONVERSA
│   └── controle_view.py      # NOVO - view modo CONTROLE
└── modes/
    ├── __init__.py
    ├── conversa_mode.py      # NOVO - lógica modo CONVERSA
    └── controle_mode.py      # NOVO - lógica modo CONTROLE
```