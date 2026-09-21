# JARVIS UI — Feature Inventory & Coverage Matrix

> **STEP 3** — Maps every UI feature to source, target component, security level, and integration status.
> **Date:** 2026-09-18

---

## Legend

- **Security Level:** `SAFE` = no security concern | `LOW` = minor | `MEDIUM` = needs review | `HIGH` = must replace | `CRITICAL` = blocker
- **Integration:** `KEEP` = use as-is | `ADAPT` = modify for Gateway | `REPLACE` = must rewrite | `REMOVE` = do not use | `BLOCKED` = depends on paused feature

---

## 1. HTML Structure (index.html)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| 3-column grid layout | index.html | ~50 | SAFE | KEEP | col1/col2/col3 CSS grid |
| Top bar (system name, controls) | index.html | ~30 | SAFE | KEEP | #sysName, #sysSub, theme/settings/fullscreen buttons |
| Boot overlay | index.html | ~20 | SAFE | KEEP | #bootOverlay with animation |
| Command input form | index.html | ~10 | LOW | ADAPT | #inputRow → must route through Gateway |
| Status pill (connection) | index.html | ~5 | MEDIUM | ADAPT | #statusPill → bridge status |
| Voice pill | index.html | ~10 | MEDIUM | BLOCKED | Voice P1.4C paused |
| Settings modal | index.html | ~100 | MEDIUM | ADAPT | backend URL, token, voice settings |
| HUD canvas | index.html | ~5 | SAFE | KEEP | #hudCanvas → pure rendering |
| Panel containers | index.html | ~200 | SAFE | KEEP | 27+ panel divs, all layout |
| Quick action chips | index.html | ~30 | SAFE | KEEP | #quickChips, #quickActions |
| Conversation area | index.html | ~20 | SAFE | KEEP | #conv, #stateHint |
| Bottom command bar | index.html | ~15 | SAFE | KEEP | #inputRow, mic button |
| Capability grid | index.html | ~50 | SAFE | KEEP | Capability cards in center stage |
| Theme grid | index.html | ~30 | SAFE | KEEP | Theme selection in settings |
| Voice settings | index.html | ~40 | MEDIUM | BLOCKED | Voice P1.4C paused |

---

## 2. Core App (app.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| `init()` boot sequence | app.js:1256-1304 | ~50 | SAFE | ADAPT | Remove direct bridge config |
| `wireUI()` event wiring | app.js:1184-1241 | ~60 | SAFE | KEEP | All DOM event listeners |
| `submitCommand()` | app.js | ~80 | MEDIUM | ADAPT | Must route through Gateway, not brain.js direct |
| `addMessage()` | app.js | ~30 | SAFE | KEEP | Conversation message display |
| `setState()` | app.js | ~20 | SAFE | KEEP | UI state management |
| `cycleTheme()` | app.js | ~15 | SAFE | KEEP | Theme cycling |
| `openSettings()` | app.js | ~20 | SAFE | KEEP | Settings modal |
| `closeSettings()` | app.js | ~10 | SAFE | KEEP | Settings modal |
| `persist()` / `loadSettings()` | app.js | ~40 | LOW | KEEP | localStorage read/write |
| `fillVoiceSelect()` | app.js | ~20 | MEDIUM | BLOCKED | Voice P1.4C paused |
| `renderCapabilities()` | app.js | ~30 | SAFE | KEEP | Capability grid |
| `renderQuickActions()` | app.js | ~20 | SAFE | KEEP | Quick action buttons |
| `renderChips()` | app.js | ~15 | SAFE | KEEP | Quick chips |
| `buildTelemetry()` | app.js | ~30 | SAFE | KEEP | Telemetry display |
| `updateModules()` | app.js | ~20 | SAFE | KEEP | Module list refresh |
| `paintTelemetry()` | app.js | ~40 | SAFE | KEEP | Telemetry gauge painting |
| `tickClock()` | app.js | ~10 | SAFE | KEEP | Clock display |
| `logLine()` | app.js | ~15 | SAFE | KEEP | Log line display |
| `toast()` | app.js | ~20 | SAFE | KEEP | Toast notifications |
| `speak()` | app.js | ~15 | MEDIUM | BLOCKED | Voice P1.4C paused |
| `rotateQuips()` | app.js | ~10 | SAFE | KEEP | Idle quip rotation |
| `setPlaceholder()` | app.js | ~5 | SAFE | KEEP | Input placeholder |
| `runBoot()` | app.js:1163-1181 | ~20 | SAFE | KEEP | Boot animation |
| `esc()` (XSS escape) | app.js | ~5 | SAFE | KEEP | HTML escaping |
| `$$()` / `$()` helpers | app.js | ~3 | SAFE | KEEP | DOM query shortcuts |
| Window event listeners | app.js:1218-1240 | ~25 | SAFE | KEEP | Keyboard, resize, visibility, online/offline |
| `window.jarvis` export | app.js:1306 | LOW | KEEP | Dev/debug global |

---

## 3. Bridge (bridge.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| WebSocket connect | bridge.js | ~80 | HIGH | REPLACE | Must use device auth, not X-Ja-Token |
| WebSocket reconnect | bridge.js | ~40 | HIGH | REPLACE | Exponential backoff → Gateway protocol |
| HTTP fallback | bridge.js | ~30 | HIGH | REPLACE | POST /api/command → Gateway |
| `sendHello()` | bridge.js | ~20 | HIGH | REPLACE | Token handshake → device pairing |
| `sendCommand()` | bridge.js | ~30 | HIGH | REPLACE | Command dispatch → Gateway |
| Message parsing | bridge.js | ~50 | HIGH | REPLACE | Protocol messages → Gateway |
| `onReply` callback | bridge.js | ~20 | SAFE | KEEP | Response handler |
| `onChunk` callback | bridge.js | ~15 | SAFE | KEEP | Streaming handler |
| `onAction` callback | bridge.js | ~25 | MEDIUM | ADAPT | UI actions → must validate |
| `onTelemetry` callback | bridge.js | ~20 | SAFE | KEEP | Telemetry data |
| `onState` callback | bridge.js | ~10 | SAFE | KEEP | State changes |
| `onError` callback | bridge.js | ~10 | SAFE | KEEP | Error display |
| `disconnect()` | bridge.js | ~15 | SAFE | KEEP | Clean disconnect |
| `configure()` | bridge.js | ~20 | HIGH | REPLACE | URL/token config → Gateway origin |
| `status` getter | bridge.js | ~5 | SAFE | KEEP | Connection status |

---

## 4. Brain (brain.js) — ⚠️ CRITICAL

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| Command parsing | brain.js | ~100 | CRITICAL | REPLACE | Must route through Gateway→ToolRegistry |
| `parseCommand()` | brain.js | ~80 | CRITICAL | REPLACE | Central dispatcher → Gateway |
| **App open/close** | brain.js | ~30 | CRITICAL | REMOVE | Direct OS control → ToolRegistry |
| **Volume control** | brain.js | ~20 | CRITICAL | REMOVE | Direct OS control → ToolRegistry |
| **Media control** | brain.js | ~20 | CRITICAL | REMOVE | Direct OS control → ToolRegistry |
| **Power controls** | brain.js | ~20 | CRITICAL | REMOVE | Shutdown/restart/sleep → ToolRegistry |
| **Screen lock** | brain.js | ~10 | CRITICAL | REMOVE | Direct OS control → ToolRegistry |
| **Screenshot** | brain.js | ~10 | CRITICAL | REMOVE | Direct OS control → ToolRegistry |
| **MT5 commands** | brain.js | ~20 | CRITICAL | REMOVE | Direct trading → ToolRegistry |
| **Browser commands** | brain.js | ~20 | CRITICAL | REMOVE | Direct browser control → ToolRegistry |
| **File operations** | brain.js | ~20 | CRITICAL | REMOVE | Direct file I/O → ToolRegistry |
| **Process listing** | brain.js | ~10 | CRITICAL | REMOVE | Direct process list → ToolRegistry |
| **Cache clearing** | brain.js | ~10 | CRITICAL | REMOVE | Direct system action → ToolRegistry |
| **Calculator** | brain.js | ~15 | CRITICAL | REPLACE | `eval()`/`Function()` → safe math parser |
| **Internet search** | brain.js | ~15 | HIGH | REPLACE | Direct search → Gateway Browser tool |
| **Weather** | brain.js | ~15 | HIGH | REPLACE | Direct API → Gateway |
| **Clock/time** | brain.js | ~10 | SAFE | KEEP | Browser-side, no backend |
| `formatReply()` | brain.js | ~30 | SAFE | KEEP | Response formatting |
| `formatError()` | brain.js | ~15 | SAFE | KEEP | Error formatting |
| Command registry | brain.js | ~40 | CRITICAL | REMOVE | All direct commands → ToolRegistry |

---

## 5. HUD Renderer (hud.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| Canvas rendering | hud.js | ~500 | SAFE | KEEP | 3D orb, particles, grid |
| `arc` mode | hud.js | ~100 | SAFE | KEEP | Default orb |
| `holo` mode | hud.js | ~80 | SAFE | KEEP | Holographic |
| `neural` mode | hud.js | ~80 | SAFE | KEEP | Neural network |
| `sentinel` mode | hud.js | ~80 | SAFE | KEEP | Guard mode |
| `nucleo` mode | hud.js | ~80 | SAFE | KEEP | Reactor |
| `avatar` mode | hud.js | ~80 | SAFE | KEEP | Avatar |
| `core` mode | hud.js | ~300 | SAFE | KEEP | Full core (3D, grid, scan, plasma) |
| Module node rendering | hud.js | ~100 | SAFE | KEEP | Orbital nodes with click |
| Click detection | hud.js | ~30 | SAFE | KEEP | Pointer-based, routes to submitCommand |
| Quality auto-adjust | hud.js | ~20 | SAFE | KEEP | FPS-based quality |
| `setHostNodes()` | hud.js | ~15 | SAFE | KEEP | External module data |
| `setAmplitude()` | hud.js | ~5 | SAFE | KEEP | Voice amplitude |
| `setPalette()` | hud.js | ~5 | SAFE | KEEP | Theme colors |
| `setTarget()` | hud.js | ~5 | SAFE | KEEP | Orb position |
| `setFrame()` | hud.js | ~5 | SAFE | KEEP | Bust frame |
| `pulse()` | hud.js | ~5 | SAFE | KEEP | Visual pulse |
| `setDataLines()` | hud.js | ~5 | SAFE | KEEP | Data overlay |
| `getFps()` | hud.js | ~3 | SAFE | KEEP | FPS counter |
| `setQuality()` | hud.js | ~5 | SAFE | KEEP | Manual quality lock |

---

## 6. GOLDEN Panel (golden.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| Mount/unmount lifecycle | golden.js | ~30 | SAFE | KEEP | Timer cleanup |
| `setView()` | golden.js | ~20 | SAFE | KEEP | Sub-view switching |
| `setShadow()` | golden.js | ~15 | SAFE | KEEP | Shadow mode |
| `setConnection()` | golden.js | ~20 | SAFE | KEEP | Connection status display |
| `setState()` | golden.js | ~20 | SAFE | KEEP | State display |
| `setTelemetry()` | golden.js | ~15 | SAFE | KEEP | Gauge data |
| `setMarket()` | golden.js | ~15 | SAFE | KEEP | Market data display |
| `setTask()` | golden.js | ~10 | SAFE | KEEP | Current task |
| `setObjective()` | golden.js | ~10 | SAFE | KEEP | Mission objective |
| `setAmplitude()` | golden.js | ~5 | SAFE | KEEP | Voice amplitude |
| Agent list rendering | golden.js | ~50 | SAFE | KEEP | Paint agents |
| Memory panel | golden.js | ~80 | SAFE | KEEP | Notes, projects, recent, tasks |
| Search panel | golden.js | ~40 | MEDIUM | ADAPT | Must route through Gateway |
| System panel | golden.js | ~40 | HIGH | ADAPT | probeOllama() → Gateway |
| Control panel | golden.js | ~30 | SAFE | KEEP | Connection, state, diag |
| Ollama model probe | golden.js:1069 | ~15 | HIGH | REPLACE | Direct Ollama → Gateway |
| Summarize button | golden.js:1057 | ~5 | HIGH | REMOVE | Tied to window.root.generateText |
| Network paint | golden.js | ~20 | SAFE | KEEP | Network info display |
| Diagnostics render | golden.js | ~30 | SAFE | KEEP | System diagnostics |
| Log display | golden.js | ~20 | SAFE | KEEP | Log lines |
| Quick actions render | golden.js | ~20 | SAFE | KEEP | Action buttons |
| Projects render | golden.js | ~30 | SAFE | KEEP | Project list |
| Tasks render | golden.js | ~20 | SAFE | KEEP | Task list |
| Recent render | golden.js | ~20 | SAFE | KEEP | Recent items |
| History render | golden.js | ~20 | SAFE | KEEP | Search history |
| Export memory | golden.js | ~10 | SAFE | KEEP | JSON export |
| Clear memory | golden.js | ~10 | SAFE | KEEP | Clear notes/history |

---

## 7. Metrics (metrics.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| CPU load (browser proxy) | metrics.js | ~15 | SAFE | KEEP | performance.now() based |
| RAM (performance.memory) | metrics.js | ~10 | LOW | KEEP | Chrome only, needs HTTPS |
| GPU (WebGL info) | metrics.js | ~15 | LOW | KEEP | WEBGL_debug_renderer_info |
| Battery (navigator.getBattery) | metrics.js | ~15 | LOW | KEEP | Needs HTTPS |
| Network (navigator.connection) | metrics.js | ~10 | LOW | KEEP | Needs HTTPS |
| Canvas FPS | metrics.js | ~15 | SAFE | KEEP | requestAnimationFrame based |
| Backend telemetry | metrics.js | ~30 | MEDIUM | ADAPT | Via bridge → Gateway |
| `start()` / `stop()` | metrics.js | ~10 | SAFE | KEEP | Lifecycle |
| `getSnapshot()` | metrics.js | ~20 | SAFE | KEEP | Current metrics |
| `subscribe()` | metrics.js | ~10 | SAFE | KEEP | Event subscription |

---

## 8. Search (search.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| Bing News RSS | search.js | ~40 | HIGH | REPLACE | Via superFetch → Gateway Browser tool |
| Wikipedia API | search.js | ~30 | HIGH | REPLACE | Via superFetch → Gateway |
| DuckDuckGo AI | search.js | ~30 | HIGH | REPLACE | Via superFetch → Gateway |
| Hacker News | search.js | ~30 | HIGH | REPLACE | Via superFetch → Gateway |
| Search history | search.js | ~20 | SAFE | KEEP | localStorage |
| `superFetch` dependency | search.js | ~10 | HIGH | REPLACE | Must use Gateway fetch proxy |
| Result rendering | search.js | ~40 | SAFE | KEEP | DOM display |

---

## 9. Voice (voice.js) — BLOCKED (P1.4C Paused)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| Speech recognition | voice.js | ~60 | MEDIUM | BLOCKED | P1.4C paused |
| Speech synthesis (TTS) | voice.js | ~50 | MEDIUM | BLOCKED | P1.4C paused |
| Wake word detection | voice.js | ~40 | MEDIUM | BLOCKED | P1.4C paused |
| Amplitude metering | voice.js | ~20 | SAFE | KEEP | For orb animation |
| Voice list fill | voice.js | ~15 | SAFE | KEEP | Browser voices |
| `start()` / `stop()` | voice.js | ~20 | MEDIUM | BLOCKED | P1.4C paused |
| `enableWake()` | voice.js | ~15 | MEDIUM | BLOCKED | P1.4C paused |
| `isListening()` | voice.js | ~5 | SAFE | KEEP | Status check |

---

## 10. Audio (audio.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| `tone()` oscillator | audio.js | ~20 | SAFE | KEEP | Web Audio API |
| `boot()` tone | audio.js | ~10 | SAFE | KEEP | Boot sound |
| `listenOn()` tone | audio.js | ~8 | SAFE | KEEP | Listen sound |
| `think()` tone | audio.js | ~8 | SAFE | KEEP | Think sound |
| `ok()` tone | audio.js | ~8 | SAFE | KEEP | Success sound |
| `err()` tone | audio.js | ~8 | SAFE | KEEP | Error sound |
| `click()` tone | audio.js | ~8 | SAFE | KEEP | Click sound |

---

## 11. Themes (themes.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| 7 theme definitions | themes.js | ~80 | SAFE | KEEP | golden/arc/holo/neural/sentinel/nucleo/avatar |
| Visual modes | themes.js | ~40 | SAFE | KEEP | 3D/minimal/noir/glass/neon/elegant |
| CSS variable injection | themes.js | ~30 | SAFE | KEEP | --accent, --bg, etc. |
| `applyTheme()` | themes.js | ~20 | SAFE | KEEP | Theme application |
| `getTheme()` | themes.js | ~5 | SAFE | KEEP | Current theme |
| Theme persistence | themes.js | ~10 | LOW | KEEP | localStorage |

---

## 12. Config (jarvis-config.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| `backendUrl` | jarvis-config.js | ~1 | HIGH | REPLACE | Must derive from location.origin |
| `aiUrl` | jarvis-config.js | ~1 | HIGH | REPLACE | Must route through Gateway |
| `fetchProxyUrl` | jarvis-config.js | ~1 | HIGH | REPLACE | Must route through Gateway |
| `themes` config | jarvis-config.js | ~20 | SAFE | KEEP | Theme definitions |
| `voice` config | jarvis-config.js | ~5 | MEDIUM | BLOCKED | P1.4C paused |
| `boot` flag | jarvis-config.js | ~1 | SAFE | KEEP | Boot animation toggle |
| `systemName` | jarvis-config.js | ~1 | SAFE | KEEP | Display name |
| `userName` | jarvis-config.js | ~1 | SAFE | KEEP | User name |
| `backendToken` | jarvis-config.js | ~1 | HIGH | REMOVE | Token → device auth |

---

## 13. Standalone Adapter (jarvis-standalone.js)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| `window.root.generateText` | jarvis-standalone.js | ~20 | CRITICAL | REMOVE | Direct Ollama calls |
| `window.root.superFetch` | jarvis-standalone.js | ~20 | CRITICAL | REMOVE | CORS proxy dependency |
| `window.root.env` | jarvis-standalone.js | ~10 | HIGH | REMOVE | Environment config |

---

## 14. CSS (styles.css)

| Feature | Source | Lines | Security | Integration | Notes |
|---------|--------|-------|----------|-------------|-------|
| Grid layout | styles.css | ~50 | SAFE | KEEP | 3-column responsive |
| Column styles | styles.css | ~80 | SAFE | KEEP | .col1, .col2, .col3 |
| Panel styles | styles.css | ~200 | SAFE | KEEP | All panel containers |
| Orb/HUD styles | styles.css | ~30 | SAFE | KEEP | Canvas positioning |
| Button styles | styles.css | ~60 | SAFE | KEEP | All buttons |
| Input styles | styles.css | ~30 | SAFE | KEEP | Command input |
| Modal styles | styles.css | ~40 | SAFE | KEEP | Settings modal |
| Boot overlay | styles.css | ~30 | SAFE | KEEP | Boot animation |
| Theme variables | styles.css | ~40 | SAFE | KEEP | CSS custom properties |
| Animations | styles.css | ~50 | SAFE | KEEP | @keyframes |
| Responsive | styles.css | ~80 | SAFE | KEEP | Media queries |
| Toast styles | styles.css | ~20 | SAFE | KEEP | Toast notifications |
| Conversation styles | styles.css | ~40 | SAFE | KEEP | Message display |
| Golden panel | styles.css | ~100 | SAFE | KEEP | GOLDEN theme |
| Scanlines/vignette | styles.css | ~20 | SAFE | KEEP | Visual effects |

---

## Summary Statistics

| Category | Total Features | KEEP | ADAPT | REPLACE | REMOVE | BLOCKED |
|----------|---------------|------|-------|---------|--------|---------|
| HTML Structure | 15 | 12 | 2 | 0 | 0 | 1 |
| Core App | 26 | 20 | 4 | 0 | 0 | 2 |
| Bridge | 15 | 4 | 0 | 11 | 0 | 0 |
| Brain | 16 | 2 | 0 | 4 | 10 | 0 |
| HUD | 20 | 20 | 0 | 0 | 0 | 0 |
| GOLDEN Panel | 22 | 18 | 2 | 1 | 1 | 0 |
| Metrics | 10 | 8 | 1 | 0 | 0 | 0 |
| Search | 7 | 1 | 0 | 5 | 0 | 0 |
| Voice | 8 | 3 | 0 | 0 | 0 | 5 |
| Audio | 7 | 7 | 0 | 0 | 0 | 0 |
| Themes | 6 | 6 | 0 | 0 | 0 | 0 |
| Config | 9 | 3 | 0 | 3 | 1 | 2 |
| Standalone | 3 | 0 | 0 | 0 | 3 | 0 |
| CSS | 15 | 15 | 0 | 0 | 0 | 0 |
| **TOTAL** | **179** | **119** | **9** | **24** | **15** | **10** |

---

## Critical Path (Must Complete Before Staging)

1. **brain.js** → Replace all direct commands with Gateway routing
2. **brain.js** → Replace `eval()`/`Function()` with safe math parser
3. **bridge.js** → Replace `X-Ja-Token` with device auth protocol
4. **bridge.js** → Replace backend URL with dynamic origin derivation
5. **jarvis-standalone.js** → Remove entirely, create Gateway adapter
6. **jarvis-config.js** → Remove `backendUrl`, `backendToken`, `aiUrl`, `fetchProxyUrl`
7. **golden.js** → Replace `probeOllama()` with Gateway model status
8. **search.js** → Replace `superFetch` with Gateway Browser/Research tool

---

**END OF STEP 3**
