# JARVIS UI — Complete Static Audit

> **Package:** `C:\GoldenAI\references\jarvis-ui\`
> **Date:** 2026-09-18
> **Status:** STEP 2 COMPLETE — Full static audit of all files

---

## 1. File Inventory

| File | Lines | Purpose |
|------|-------|---------|
| `index.html` | ~620 | Main HTML shell — 3-column layout, panels, overlays |
| `src/app.js` | 1306 | Core orchestrator — boot, init, DOM wiring, state |
| `src/bridge.js` | ~550 | WebSocket/HTTP communication layer |
| `src/brain.js` | ~480 | Command parser + direct OS actions (CRITICAL) |
| `src/hud.js` | 1820 | Canvas orb renderer (arc/holo/neural/sentinel/nucleo/avatar/core) |
| `src/golden.js` | 1146 | GOLDEN JARVIS panel — metrics, agents, memory, projects |
| `src/metrics.js` | ~320 | Browser + backend telemetry (CPU, RAM, GPU, battery, network) |
| `src/search.js` | ~280 | Internet search (Bing RSS, Wikipedia, DuckDuckGo, HN) |
| `src/voice.js` | ~300 | Web Speech API — recognition + TTS + wake word |
| `src/audio.js` | ~180 | SFX tones via Web Audio API |
| `src/themes.js` | ~200 | 7 themes with visual modes |
| `src/styles.css` | ~1300 | Full visual design — grid, 3-col, CSS vars, animations |
| `src/fonts.css` | ~30 | Font-face declarations |
| `src/fonts/*.woff2` | 6 files | Orbitron, Rajdhani, Share Tech Mono |
| `src/jarvis-config.js` | ~50 | Config object (backend URL, theme defaults) |
| `src/jarvis-standalone.js` | ~60 | Standalone adapter (window.root) |
| `serve_ui.py` | ~300 | Standalone HTTP+Ollama proxy server |
| `backend/jarvis_server.py` | ~800 | Standalone backend (shell, volume, MT5, telemetry) |

---

## 2. HTML Structure (`index.html`)

### Layout
- **Body:** `<div id="app">` → `<header>` + `<div class="grid">` → 3 columns
- **Column 1 (`.col1`):** Voice, Orb, HUD canvas, Control pills
- **Column 2 (`.col2`):** Menu tabs, Center stage (main content areas)
- **Column 3 (`.col3`):** Right panels (tools, memory, settings, etc.)

### Key DOM Elements
| ID | Type | Purpose |
|----|------|---------|
| `hudCanvas` | `<canvas>` | Main HUD/orb rendering surface |
| `cmdInput` | `<input>` | Command input field |
| `inputRow` | `<form>` | Command form (submits via submitCommand) |
| `micBtn` | `<button>` | Microphone toggle |
| `bootOverlay` | `<div>` | Boot animation overlay |
| `settingsModal` | `<div>` | Settings modal |
| `statusPill` | `<span>` | Connection status indicator |
| `stateHint` | `<span>` | State hint / idle quip |
| `voicePill` | `<div>` | Voice status pill |

### Panels Defined
- `panelHome`, `panelGolden`, `panelChat`, `panelHub`, `panelTasks`, `panelProjects`, `panelMemoria`
- `panelSystem`, `panelControl`, `panelPower`, `panelNetwork`, `panelDiag`, `panelLogs`
- `panelTools`, `panelSearch`, `panelBrowser`, `panelShell`, `panelScript`, `panelCalendar`
- `panelDocs`, `panelNotes`, `panelMedia`, `panelCamera`, `panelFiles`, `panelCode`, `panelConfig`

### Event Listeners (HTML inline)
- `inputRow.onsubmit` → `submitCommand(cmdInput.value)`
- `micBtn.onclick` → voice start/stop
- `#voiceToggleBtn.onclick` → speak toggle
- `#themeBtn.onclick` → `cycleTheme()`
- `#settingsBtn.onclick` → `openSettings()`
- `#fullscreenBtn.onclick` → fullscreen toggle
- `#statusPill.onclick` → bridge connect/disconnect
- `#bootSkipBtn.onclick` → skip boot animation
- `document.addEventListener("keydown")` → keyboard shortcuts (Space=mic, T=theme, M=voice, S=shadow, /=focus input)
- `window.addEventListener("resize")` → HUD resize + orb update
- `document.addEventListener("visibilitychange")` → HUD start/stop
- `window.addEventListener("online"/"offline")` → network status log

---

## 3. Communication Layer (`bridge.js`)

### Transport
- **WebSocket:** `ws://{host}:{port}/ws` or `wss://` (auto-detect)
- **HTTP fallback:** `POST /api/command`
- **Auth header:** `X-Ja-Token` (sent with every WS message and HTTP request)

### Protocol Messages
| Direction | Type | Purpose |
|-----------|------|---------|
| Client→Server | `hello` | Initial handshake with token |
| Client→Server | `command` | User command |
| Client→Server | `ready` | Client ready |
| Server→Client | `reply` | Full response |
| Server→Client | `chunk` | Streaming chunk |
| Server→Client | `action` | UI action (toast, open panel, set state) |
| Server→Client | `telemetry` | System metrics |
| Server→Client | `state` | State change |
| Server→Client | `error` | Error |

### Reconnection
- Auto-reconnect with exponential backoff (1s → 2s → 4s → 8s → 16s → 30s max)
- Max 30s between attempts

### ⚠️ CRITICAL: Auth Header
- Uses `X-Ja-Token` header — **MUST replace with device auth via Gateway**
- Token stored in `localStorage` settings

---

## 4. Command Parser (`brain.js`) — ⚠️ CRITICAL SECURITY CONCERN

### Direct OS Actions (no backend)
`brain.js` contains a hardcoded command parser that executes **directly in the browser**:

| Category | Commands | Risk |
|----------|----------|------|
| **Apps** | `abrir chrome`, `abrir notepad`, `abrir calculator` | Direct OS control |
| **Close** | `fechar chrome`, `fechar notepad` | Direct OS control |
| **Volume** | `volume up`, `volume down`, `mute` | Direct OS control |
| **Media** | `play`, `pause`, `next`, `previous` | Media keys |
| **Power** | `desligar`, `reiniciar`, `sleep`, `hibernar` | **DANGEROUS** |
| **Screen** | `bloquear tela`, `screenshot` | Screen control |
| **MT5** | `status mt5`, `abrir mt5` | Trading system |
| **Browser** | `abrir site X`, `fechar aba` | Browser control |
| **Files** | `listar pasta`, `criar pasta`, `deletar arquivo` | File system |
| **Search** | `pesquisar X`, `buscar X` | Internet |
| **Math** | `calcular X` | Uses `eval()` / `Function()` |
| **System** | `processos`, `limpar cache` | System info |

### `eval()` / `Function()` Usage
```javascript
// brain.js — calculator
result = Function('"use strict"; return (' + expr + ')')();
// or
result = eval(expr);
```
**THIS MUST BE REPLACED** with a safe math parser (e.g., `math.js` or custom expression parser).

### ⚠️ Command Routing
All commands in `brain.js` are parsed and routed **entirely in the browser** without any backend validation. The bridge only sends `command` messages to the backend, but `brain.js` intercepts them first and handles many locally.

---

## 5. Config (`jarvis-config.js`)

```javascript
window.JARVIS_CONFIG = {
  backendUrl: "http://localhost:8765",     // ← MUST replace with Gateway
  aiUrl: "/api/chat",                      // ← MUST route through Gateway
  fetchProxyUrl: "/api/fetch",             // ← MUST route through Gateway
  themes: { golden, arc, holo, neural, sentinel, nucleo, avatar },
  voice: { lang: "pt-BR", rate: 1, pitch: 1 },
  boot: true,
  systemName: "JARVIS",
  userName: "Anderson",
};
```

### localStorage Keys Used
| Key | Purpose |
|-----|---------|
| `jarvis-settings` | All settings (theme, backend URL, token, voice, wake) |
| `jarvis-conversation` | Conversation history |
| `jarvis-search-history` | Search history |
| `jarvis-notes` | User notes |

---

## 6. Standalone Adapter (`jarvis-standalone.js`)

```javascript
// Creates window.root with direct Ollama access
window.root = {
  generateText: async (prompt, onChunk) => {
    // DIRECT OLLAMA CALL — MUST NOT USE
    const res = await fetch("http://localhost:11434/api/generate", { ... });
  },
  superFetch: async (url, opts) => {
    // Calls /api/fetch proxy endpoint
    const res = await fetch(proxyUrl, { body: JSON.stringify({ url, options }) });
  }
};
```

**`window.root.generateText`** makes **direct Ollama calls** bypassing Gateway/Brain/ModelRouter. **MUST NOT BE USED** in production.

---

## 7. HUD Renderer (`hud.js`)

### Canvas Modes
- `arc` — Default orb with rings and particles
- `holo` — Holographic mode
- `neural` — Neural network visualization
- `sentinel` — Guard/surveillance mode
- `nucleo` — Core reactor
- `avatar` — Avatar mode
- `core` — Full core renderer with 3D particles, grid, scan beam, golden plasma

### Features
- 3D perspective projection of sphere particles
- Meridian/parallel grid lines
- Rotating scan beam
- Orbital rings with sparks
- Core plasma glow (golden)
- Module nodes on orbit (clickable via `nodeHits`)
- Quality auto-adjustment based on FPS
- `setHostNodes(nodes)` — external system modules rendered on orbit
- `getNodes()` — returns clickable node hit areas

### External Integration Points
- `hud.setTheme(id, mode)` — from `themes.js`
- `hud.setState(s)` — from `app.js`
- `hud.setAmplitude(v)` — from voice/metrics
- `hud.setHostNodes(nodes)` — from golden.js (agent list)
- `hud.setHoverNode(id)` — from pointer events
- `hud.setDataLines(lines)` — from metrics/telemetry

### No Security Concerns
- Pure canvas rendering, no eval, no fetch, no DOM manipulation beyond canvas
- Click detection is pointer-based, commands go through `submitCommand()`

---

## 8. GOLDEN Panel (`golden.js`)

### Sub-views
- `home` — Mission, objective, task, quick actions
- `agents` — Agent list with status
- `memory` — Memory panel (notes, projects, recent, tasks, stats, history)
- `control` — System controls (connection, state, diag, logs)
- `search` — Internet search panel
- `system` — System info (ollama models, metrics)

### Features
- Mount/unmount lifecycle (clean timers on unmount)
- `setShadow(bool)` — shadow mode (dims UI)
- `setView(view)` — switch sub-views
- `setConnection(status)` — online/connecting/local
- `setState(s)` — idle/listening/thinking/executing/speaking
- `setTelemetry(data)` — paint gauges
- `setMarket(rows)` — market data
- `setTask(text)` — current task
- `setObjective(text)` — mission objective

### Ollama Probe
```javascript
async function probeOllama() {
  // DIRECT OLLAMA CALL — port 11434
  const res = await fetch("http://localhost:11434/api/tags");
}
```
**MUST replace with Gateway-mediated Ollama status.**

### Timer Intervals
- 1s: clock, tasks
- 3s: agents, memory, diag, memoria
- 4s: models (Ollama probe)
- 6s: network
- 15s: Ollama probe + model paint

### Summarize Button
```javascript
el.sumBtn.hidden = !window.root?.generateText;
// Only shown if standalone adapter loaded — ties to direct Ollama
```

---

## 9. Metrics (`metrics.js`)

### Browser-Side (Real)
- `performance.memory` — JS heap (Chrome only)
- `navigator.getBattery()` — battery level, charging
- `navigator.connection` — network info (downlink, RTT, type)
- WebGL renderer info — GPU vendor/renderer
- Canvas FPS measurement

### Backend-Side (via bridge telemetry)
- CPU load, RAM total/used/free
- GPU utilization, GPU memory, GPU temperature (via `nvidia-smi`)
- Disk I/O, network I/O
- Process count, uptime

### External Calls
- `navigator.getBattery()` — requires HTTPS/localhost
- `navigator.connection` — requires HTTPS
- WebGL `getExtension("WEBGL_debug_renderer_info")` — blocked in some browsers

---

## 10. Search (`search.js`)

### Sources
- Bing News RSS (via `superFetch` proxy)
- Wikipedia API
- DuckDuckGo AI (via `superFetch` proxy)
- Hacker News (via `superFetch` proxy)

### Dependency on `superFetch`
All external searches go through `window.root.superFetch()` which calls `/api/fetch` proxy. **MUST replace with official Browser/Research tool.**

### Search History
- Stored in localStorage (`jarvis-search-history`)
- Exportable, clearable

---

## 11. Voice (`voice.js`)

### Features
- Web Speech API recognition (continuous mode)
- SpeechSynthesis TTS (configurable voice, rate, pitch)
- Wake word detection (configurable word, default "Jarvis")
- Amplitude metering (for orb animation)

### ⚠️ Voice P1.4C is PAUSED
- Voice module is **reference only** — do NOT activate
- Wake word detection must NOT be enabled in production
- TTS is optional cosmetic feature only

---

## 12. Audio (`audio.js`)

- Web Audio API oscillators for SFX
- Tones: boot, listen, think, ok, err, click, listenOn
- No external calls, no security concerns

---

## 13. Themes (`themes.js`)

- 7 themes: golden, arc, holo, neural, sentinel, nucleo, avatar
- Visual modes: 3D, minimal, noir, glass, neon, elegant
- CSS variable injection (`--accent`, `--accent2`, `--bg`, `--text`, etc.)
- Theme persistence in localStorage

---

## 14. `serve_ui.py` — DO NOT USE

### What It Does
- Standalone HTTP server (port 8000)
- Static file serving for `index.html` and `src/`
- `/api/chat` → Ollama proxy (bypasses Gateway)
- `/api/fetch` → CORS proxy (arbitrary URL fetch)
- `/api/status` → fake status

### Why NOT To Use
- Bypasses all security (Gateway, Device Auth, SecurityManager)
- Direct Ollama access
- Arbitrary URL fetch proxy (security risk)
- No auth, no TLS

---

## 15. `backend/jarvis_server.py` — DO NOT USE

### What It Does
- Standalone backend (port 8765)
- Shell command execution
- Power controls (shutdown, restart, sleep, hibernate)
- Volume/media control
- Browser control (open URLs, tabs)
- MT5 status
- Telemetry (psutil, nvidia-smi)
- WebSocket server

### Why NOT To Use
- Duplicates existing Gateway/JarvisService functionality
- No SecurityManager integration
- No auth enforcement
- Direct shell/eval execution
- Would create second Jarvis (violates invariant)

---

## 16. Security Findings Summary

| # | Finding | File | Severity | Action Required |
|---|---------|------|----------|-----------------|
| 1 | `eval()` / `Function()` in calculator | `brain.js` | **CRITICAL** | Replace with safe math parser |
| 2 | Direct OS commands in browser | `brain.js` | **CRITICAL** | Route through ToolRegistry via Gateway |
| 3 | `X-Ja-Token` auth header | `bridge.js` | **HIGH** | Replace with device auth via Gateway |
| 4 | Direct Ollama calls | `jarvis-standalone.js` | **CRITICAL** | Remove, route through Gateway→Brain |
| 5 | Direct Ollama probe | `golden.js` | **HIGH** | Replace with Gateway-mediated status |
| 6 | `superFetch` proxy dependency | `search.js` | **HIGH** | Replace with official Browser/Research tool |
| 7 | Arbitrary URL fetch proxy | `serve_ui.py` | **CRITICAL** | DO NOT USE |
| 8 | Shell command execution | `jarvis_server.py` | **CRITICAL** | DO NOT USE |
| 9 | Power controls (shutdown, etc.) | `jarvis_server.py` | **CRITICAL** | DO NOT USE |
| 10 | `backendUrl` with `http://localhost:8765` | `jarvis-config.js` | **MEDIUM** | Replace with Gateway origin derivation |
| 11 | `aiUrl: "/api/chat"` | `jarvis-config.js` | **HIGH** | Replace with Gateway route |
| 12 | localStorage for settings/tokens | `app.js` | **LOW** | Acceptable (client-side only) |
| 13 | `navigator.getBattery()` | `metrics.js` | **LOW** | Acceptable (browser API) |
| 14 | Wake word detection | `voice.js` | **MEDIUM** | PAUSED — do not activate |
| 15 | `window.jarvis` global export | `app.js` | **LOW** | Acceptable (dev/debug) |

---

## 17. Integration Points Map

### Must Replace (Runtime Dependency → Gateway)
1. `bridge.js` WS auth → Device Auth via Gateway
2. `brain.js` command routing → Gateway command endpoint
3. `brain.js` direct OS actions → ToolRegistry via Gateway
4. `brain.js` calculator `eval()` → Safe math parser
5. `jarvis-standalone.js` `window.root` → Gateway adapter
6. `jarvis-config.js` `backendUrl` → Dynamic origin derivation
7. `jarvis-config.js` `aiUrl` → Gateway chat endpoint
8. `jarvis-config.js` `fetchProxyUrl` → Gateway fetch proxy
9. `golden.js` `probeOllama()` → Gateway model status
10. `search.js` `superFetch` → Gateway Browser/Research tool
11. `metrics.js` backend telemetry → Gateway telemetry stream

### Keep As-Is (Browser-Side)
1. `hud.js` — pure canvas rendering
2. `themes.js` — CSS variable injection
3. `audio.js` — Web Audio SFX
4. `voice.js` — Web Speech API (reference only, P1.4C paused)
5. `app.js` — DOM wiring (minus bridge config)
6. `golden.js` — panel layout (minus probeOllama)
7. `metrics.js` — browser-side metrics (performance.memory, battery, WebGL, connection)
8. All CSS/fonts — visual design

### Do Not Use
1. `serve_ui.py` — standalone server
2. `backend/jarvis_server.py` — standalone backend
3. `brain.js` direct command routing (in current form)
4. `jarvis-standalone.js` (entire file)

---

## 18. localStorage Keys

| Key | Type | Contents |
|-----|------|----------|
| `jarvis-settings` | Object | theme, backendUrl, token, autoConnect, speak, wake, wakeWord, lang, rate, pitch, boot, volume, themeMode |
| `jarvis-conversation` | Array | [{role, content, time}] |
| `jarvis-search-history` | Array | [{query, ts}] |
| `jarvis-notes` | Array | [{text, ts}] |

---

## 19. Boot Sequence (`app.js`)

1. `DOMContentLoaded` → `init()`
2. `wireUI()` — all event listeners
3. `wireSettings()` — settings modal
4. `renderThemeGrid()` — theme selection
5. `renderQuickActions()` — quick action buttons
6. `renderChips()` — capability chips
7. `buildTelemetry()` — telemetry display
8. `updateModules()` — module list
9. `metrics.start()` — begin metrics collection
10. `applyTheme()` — apply saved theme
11. `hud.start()` — begin canvas rendering
12. `setState("idle")` — initial state
13. `initBattery()` — battery API
14. `setInterval(paintTelemetry, 1000)` — telemetry paint
15. `setInterval(tickClock, 1000)` — clock
16. `setInterval(updateModules, 5000)` — module refresh
17. `runBoot()` — boot animation
18. If `autoConnect` → `bridge.connect()`
19. If `wake` → `voice.enableWake()`

---

## 20. Global Exports

```javascript
window.jarvis = {
  submitCommand,
  applyTheme,
  bridge,
  voice,
  hud,
  brain,
  metrics,
  golden,
  settings,
  notes,
  addMessage,
  toast,
  clearConversation,
};

window.root = {
  generateText,  // ← DIRECT OLLAMA — MUST REPLACE
  superFetch,    // ← CORS proxy — MUST REPLACE
};
```

---

**END OF AUDIT — STEP 2 COMPLETE**
