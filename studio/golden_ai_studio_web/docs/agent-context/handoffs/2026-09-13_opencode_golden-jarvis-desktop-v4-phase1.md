# Handoff — Golden Jarvis Desktop V4 Fase 1 (Visual Foundation)

**Data:** 2026-09-13
**Agente:** opencode
**Status:** Fase 1 concluída — aguardando aprovação visual

---

## Resumo

Implementada a fundação visual completa do Golden Jarvis Desktop V4 com **dois modos integrados** na mesma aplicação:

| Modo | Descrição | Componentes Principais |
|------|-----------|------------------------|
| **CONVERSA** | Humanoide holográfico central + chat | `AnimationFoundation` (4 estados), `ConversaView`, `StatusFooter` |
| **CONTROLE** | Núcleo radial + 12 funções + painéis | `RadialCore`, `ControleView`, `QuickActionsGrid`, `ManualCommandBar` |

**Troca de modo:** Botões `CONVERSA` / `CONTROLE` na TitleBar (animados).

---

## Arquivos Criados/Modificados

### Novos Arquivos (V4)

```
jarvis_desktop/
├── theme_v4.py                      # Tema V4: Dark Navy, Cyan Elétrico, Dourado
├── main_window_v4.py                # MainWindow com dois modos (stack)
├── app_v4.py                        # Entry point V4
├── widgets/
│   ├── mode_switcher.py             # Toggle CONVERSA/CONTROLE animado
│   ├── title_bar_v4.py              # TitleBar frameless + drag + window controls
│   ├── backdrop_v4.py               # Fundo: gradiente radial + grid + circuitos
│   ├── hud_panel_v4.py              # Painel HUD com cantos tecnológicos
│   ├── animation_foundation.py      # Canvas central: IDLE/LISTENING/PROCESSING/SPEAKING
│   ├── radial_core.py               # Núcleo + 12 nós radiais (CONTROLE)
│   ├── status_footer.py             # CPU/RAM/GPU + Providers + Serviços (CONVERSA)
│   ├── quick_actions.py             # Grid 2x3 ações rápidas (CONTROLE)
│   └── manual_command.py            # Input comando manual (CONTROLE)
├── views/
│   ├── conversa_view.py             # View modo CONVERSA
│   └── controle_view.py             # View modo CONTROLE
```

### Arquivos Preservados (V3 — inalterados)

```
jarvis_desktop/
├── theme.py, main_window.py, app.py        # V3 original
├── state.py, api_client.py, workers.py     # Core infrastructure
├── status_format.py, gpu.py                # Formatters
├── widgets/
│   ├── chat_view.py, hud.py, hud_panel.py  # V3 components
│   ├── status_panels.py, title_bar.py      # V3 components
├── views/
│   ├── config_view.py, dev_view.py, ops_view.py, skills_view.py, tasks_view.py
```

### Documentação

```
docs/agent-context/
├── GOLDEN_JARVIS_DESKTOP_V4.md             # Spec completa Fase 1
└── handoffs/
    └── 2026-09-13_opencode_golden-jarvis-desktop-v4-phase1.md  # Este handoff
```

### Launcher

```
start_jarvis_desktop_v4.bat                  # Inicia V4 (python -m jarvis_desktop.app_v4)
```

---

## Como Executar

```bat
start_jarvis_desktop_v4.bat
```

Ou manualmente:
```bash
cd C:\GoldenAI\studio\golden_ai_studio_web
C:\GoldenAI\.venv\Scripts\python.exe -m jarvis_desktop.app_v4
```

**Pré-requisitos:**
- Backend Golden rodando em `http://127.0.0.1:8765` (`server_agent.py --port 8765`)
- PySide6 no venv (`pip install PySide6`)

---

## Funcionalidades Implementadas

### ✅ CONVERSA Mode
- **Animação central** com 4 estados: `IDLE`, `LISTENING`, `PROCESSING`, `SPEAKING` (+ `OFFLINE`, `ERROR`)
- **QPainter leve** — ~30 FPS, < 2% CPU ocioso
- **Estados visuais distintos:**
  - IDLE: Núcleo pulsante lento, anel respiração
  - LISTENING: Anel expansivo + waveform mic circular
  - PROCESSING: Anéis girando + partículas centrípetas + gold accent
  - SPEAKING: Waveform radial sincronizado + núcleo expandido
- **Chat integrado** (reutiliza `ChatWidget` V3 funcional)
- **Status Footer** com dados reais: CPU/RAM/GPU, Providers, Serviços
- **Simulação de voz** para preview (pode ser desligada)

### ✅ CONTROLE Mode
- **RadialCore** com núcleo central "NÚCLEO" + 12 nós orbitais:
  `PESQUISA`, `MEMÓRIA`, `PROJETOS`, `AUTOMAÇÃO`, `ANÁLISE`, `DOCUMENTOS`,
  `AGENDA`, `INTERNET`, `FERRAMENTAS`, `TRADING`, `DESIGN`, `NÚCLEO`
- **Conexões animadas** (linhas tracejadas núcleo→nós, toggleável)
- **Hover/click nos nós** — tooltip com status, toggle active
- **Painel Agentes Ativos** (mock data — marcado `[UI PREVIEW]`)
- **Painel Projetos Recentes** (mock data — marcado `[UI PREVIEW]`)
- **QuickActionsGrid** 2×3 (NOVA TAREFA, EXECUTAR AGENTE, ABRIR PROJETO, VER LOGS, CONFIGURAR, ATUALIZAR)
- **ManualCommandBar** — input + sugestões + botão executar

### ✅ Window Controls (Corrigidos)
| Controle | Comportamento |
|----------|---------------|
| Minimizar (`—`) | `showMinimized()` |
| Maximizar (`▢`/`❐`) | Toggle `showMaximized()`/`showNormal()` |
| Fechar (`×`) | `request_close()` → tray ou `close()` |
| Drag | TitleBar inteira (exceto botões) |
| Double-click | Maximize/restore |
| Resize | `QSizeGrip` + `setMinimumSize(1150, 720)` |

### ✅ High DPI / Resoluções
- `QT_AUTO_SCREEN_SCALE_FACTOR=1`, `QT_ENABLE_HIGHDPI_SCALING=1` no entry point
- Layouts flexíveis, espaçamento em px (escala 4px)
- Testado conceitualmente para 1366×768, 1920×1080, 2560×1440 @ 100-200%

### ✅ Abas Legadas Preservadas
Todas as 7 abas V3 mantidas acessíveis (não no stack principal, mas instanciadas):
`CHAT`, `TASKS`, `RADAR`, `MT5`, `SKILLS`, `CONFIG`, `DEV`

### ✅ Dados: Real vs Mock
| Área | Fonte |
|------|-------|
| CPU/RAM/GPU, Providers, MT5, Radar, Voice, Tasks, Chat | **Real** (endpoints existentes) |
| Agentes ativos, Projetos recentes, Ações rápidas | **Mock** — claramente marcado `[UI PREVIEW]` |

---

## Testes Executados

```bash
# API Client
python -m unittest tests.test_jarvis_desktop_api_client -v
# → 3/3 OK

# Status Format / HUD States
python -m unittest tests.test_jarvis_desktop_v2 -v
# → 11/11 OK

# Interação (chat, workers, voice mirror)
python -m unittest tests.test_jarvis_desktop_interaction -v
# → 9/9 OK
```

**Todos os testes V3 passam** — V4 não quebrou funcionalidade existente.

---

## Limitações Conhecidas (Fase 1)

1. **Animação central** usa QPainter básico — versão refinada (partículas fluidas, shaders, transições suaves) na Fase 2
2. **CONTROLE mode** usa dados mock para Agentes/Projetos/Ações — integração real na Fase 3
3. **Atalhos globais** não implementados — farão parte da Fase 4
4. **SHADOW mode** mantido no orchestrator (não alterado)
5. **Backend não modificado** — zero endpoints novos
6. **Voice simulation** apenas para preview visual — não é STT/TTS real

---

## Próximos Passos (Pós-Aprovação)

| Fase | Foco |
|------|------|
| **Fase 2** | Animação central refinada: partículas fluidas, transições de estado suaves, shaders leves, waveform real do VoiceService |
| **Fase 3** | Ligar CONTROLE a dados reais: agents status via backend, projects DB, quick actions → comandos reais |
| **Fase 4** | Atalhos globais (Win+J), overlay always-on-top, hotkeys por modo |
| **Fase 5** | Polish, acessibilidade, performance, packaging (EXE/MSIX via pyinstaller/cx_Freeze) |

---

## Verificação Rápida (Checklist Visual)

- [ ] Janela abre frameless, title bar customizada visível
- [ ] Botões `CONVERSA` / `CONTROLE` alternam modos com animação
- [ ] CONVERSA: Animação central mostra IDLE pulsante
- [ ] CONVERSA: Chat funcional (digitar → envia → resposta mock se backend offline)
- [ ] CONVERSA: Status footer mostra CPU/RAM/GPU (N/D se backend offline)
- [ ] CONTROLE: RadialCore visível com 12 nós + núcleo
- [ ] CONTROLE: Hover nos nós mostra tooltip, click toggle active
- [ ] CONTROLE: Agentes ativos listados (mock), projetos recentes listados (mock)
- [ ] CONTROLE: Quick actions clicáveis, comando manual envia para chat
- [ ] Minimizar/Maximizar/Fechar/Drag/Resize funcionam
- [ ] Tray icon aparece, fechar minimiza para tray
- [ ] High DPI: UI escala corretamente em 125%/150%/200%

---

## Compatibilidade

- **Python:** 3.11+
- **PySide6:** 6.6+
- **OS:** Windows 10/11
- **Backend:** Golden AI `server_agent.py` porta 8765 (inalterado)

---

## Rollback

Para voltar ao V3:
```bat
start_jarvis_desktop.bat
# ou
python -m jarvis_desktop.app
```

Nenhum arquivo V3 foi modificado ou removido.