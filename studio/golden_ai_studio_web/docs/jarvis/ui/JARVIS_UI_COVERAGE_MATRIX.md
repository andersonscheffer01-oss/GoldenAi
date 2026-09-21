# JARVIS UI — Coverage Matrix: jarvis-ui vs Production UI

> **STEP 6** — Maps jarvis-ui features against existing studio_v7.html, dashboard.html, mobile.html
> **Date:** 2026-09-18

---

## 1. Production UI Inventory

### studio_v7.html (Main Chat Interface)
- **Layout:** Sidebar + Main content (chat)
- **Features:** Chat messages, code highlighting (highlight.js), markdown (marked.js), file drag-drop, conversation history, search, new chat, theme toggle (dark/light), PWA manifest, service worker
- **Backend:** WebSocket connection to Gateway (`ws://` or `wss://`), device auth with pairing code
- **Security:** Frame-busting script, service worker registration, HTTPS-aware protocol detection

### dashboard.html (Robot/Strategy Dashboard)
- **Layout:** Header + tabs + content areas
- **Features:** Robot list (MQL5 EAs), backtest panel, scanner panel, strategy comparison, validation, strategy list, Jarvis panel, security panel, status bar (MT5/Ollama/OpenRouter/Cline), compilation form
- **Backend:** REST API calls to Gateway (`/api/status`, `/api/compile`, `/api/robots`, etc.)
- **Security:** Same frame-busting, same auth

### mobile.html (Mobile Chat)
- **Layout:** Full-screen chat with status bar
- **Features:** Chat messages, confirmation buttons, pairing screen (code input), WebSocket connection, protocol auto-detection (ws/wss)
- **Backend:** WebSocket to Gateway, device auth flow
- **Security:** HTTPS/WSS when `GOLDEN_SSL=1`, token via WS message

---

## 2. Feature-by-Feature Comparison

### A. Layout & Structure

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| 3-column grid | ✅ col1/col2/col3 | ❌ sidebar+main | ❌ header+tabs+content | ❌ full chat | **NEW** |
| Top bar with controls | ✅ theme/settings/fullscreen | ✅ header with brand | ✅ header with back-btn | ✅ status-bar | OVERLAP |
| Boot animation | ✅ boot overlay | ❌ none | ❌ none | ❌ none | **NEW** |
| Panel containers (27+) | ✅ 27+ panels | ❌ no panels | ✅ tab panels | ❌ no panels | **NEW** |
| Quick action chips | ✅ quickChips | ❌ none | ❌ none | ❌ none | **NEW** |
| Capability grid | ✅ capability cards | ❌ none | ❌ none | ❌ none | **NEW** |
| Conversation area | ✅ conv + stateHint | ✅ messages div | ❌ no chat | ✅ messages div | OVERLAP |
| Command input form | ✅ inputRow | ✅ input area | ❌ no input | ✅ input-bar | OVERLAP |
| Settings modal | ✅ settingsModal | ❌ none | ❌ none | ❌ none | **NEW** |
| HUD canvas (orb) | ✅ hudCanvas | ❌ none | ❌ none | ❌ none | **NEW** |

### B. Communication

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| WebSocket connect | ✅ bridge.js | ✅ inline JS | ❌ REST only | ✅ inline JS | OVERLAP |
| Device auth (pairing) | ❌ X-Ja-Token | ✅ pairing flow | ✅ token | ✅ pairing flow | **MISSING** |
| HTTP REST API | ✅ bridge HTTP fallback | ❌ WS only | ✅ fetch calls | ❌ WS only | OVERLAP |
| Protocol auto-detect | ❌ hardcoded | ✅ ws/wss auto | N/A | ✅ ws/wss auto | **MISSING** |
| Reconnect logic | ✅ exponential backoff | ✅ inline | N/A | ✅ inline | OVERLAP |

### C. AI/Chat

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| Command input | ✅ submitCommand | ✅ inline send | ❌ none | ✅ inline send | OVERLAP |
| Message display | ✅ addMessage | ✅ msg rendering | ❌ none | ✅ msg rendering | OVERLAP |
| Markdown rendering | ❌ plain text | ✅ marked.js | ❌ none | ✅ marked.js | **MISSING** |
| Code highlighting | ❌ none | ✅ highlight.js | ❌ none | ✅ highlight.js | **MISSING** |
| Streaming chunks | ✅ bridge onChunk | ✅ inline | ❌ none | ✅ inline | OVERLAP |
| Conversation history | ✅ localStorage | ✅ localStorage | ❌ none | ✅ localStorage | OVERLAP |
| Confirmation flow | ❌ none | ✅ confirm buttons | ❌ none | ✅ confirm buttons | **MISSING** |

### D. Voice & Audio

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| Speech recognition | ✅ voice.js | ❌ none | ❌ none | ❌ none | **NEW** (BLOCKED) |
| TTS | ✅ voice.js | ❌ none | ❌ none | ❌ none | **NEW** (BLOCKED) |
| Wake word | ✅ voice.js | ❌ none | ❌ none | ❌ none | **NEW** (BLOCKED) |
| SFX tones | ✅ audio.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Voice amplitude | ✅ metrics.js | ❌ none | ❌ none | ❌ none | **NEW** |

### E. Visual Effects

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| Canvas orb/HUD | ✅ hud.js (1820 lines) | ❌ none | ❌ none | ❌ none | **NEW** |
| 7 themes | ✅ themes.js | ✅ dark/light toggle | ✅ dark only | ✅ dark only | **NEW** (7 vs 2) |
| Visual modes (6) | ✅ themes.js | ❌ none | ❌ none | ❌ none | **NEW** |
| CSS variables | ✅ 40+ vars | ✅ 10+ vars | ✅ 7 vars | ✅ 7 vars | OVERLAP |
| Scanlines/vignette | ✅ styles.css | ❌ none | ❌ none | ❌ none | **NEW** |
| Boot animation | ✅ boot overlay | ❌ none | ❌ none | ❌ none | **NEW** |
| Responsive design | ✅ media queries | ✅ basic | ✅ basic | ✅ mobile-first | OVERLAP |

### F. System/Metrics

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| CPU/RAM metrics | ✅ metrics.js | ❌ none | ✅ status bar | ❌ none | OVERLAP |
| GPU metrics | ✅ metrics.js (WebGL) | ❌ none | ❌ none | ❌ none | **NEW** |
| Battery status | ✅ metrics.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Network info | ✅ metrics.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Ollama model probe | ✅ golden.js | ❌ none | ✅ status bar | ❌ none | OVERLAP |
| MT5 status | ✅ brain.js | ❌ none | ✅ status bar | ❌ none | OVERLAP |
| Telemetry gauges | ✅ golden.js | ❌ none | ✅ stat cards | ❌ none | OVERLAP |
| Clock display | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |

### G. Search & Internet

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| Bing News RSS | ✅ search.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Wikipedia | ✅ search.js | ❌ none | ❌ none | ❌ none | **NEW** |
| DuckDuckGo AI | ✅ search.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Hacker News | ✅ search.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Search history | ✅ search.js | ❌ none | ❌ none | ❌ none | **NEW** |

### H. Trading/Dashboard

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| Robot list (MQL5) | ❌ none | ❌ none | ✅ robot-grid | ❌ none | **MISSING** |
| Backtest panel | ❌ none | ❌ none | ✅ backtest | ❌ none | **MISSING** |
| Scanner panel | ❌ none | ❌ none | ✅ scanner | ❌ none | **MISSING** |
| Strategy comparison | ❌ none | ❌ none | ✅ compare | ❌ none | **MISSING** |
| Validation panel | ❌ none | ❌ none | ✅ validation | ❌ none | **MISSING** |
| Compilation form | ❌ none | ❌ none | ✅ compile | ❌ none | **MISSING** |
| Market ticker | ❌ none | ❌ none | ✅ ticker | ❌ none | **MISSING** |
| Security panel | ❌ none | ❌ none | ✅ security | ❌ none | **MISSING** |

### I. Golden Panel (jarvis-ui only)

| Feature | jarvis-ui | studio_v7 | dashboard | mobile | Status |
|---------|-----------|-----------|-----------|--------|--------|
| Mission/objective | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Agent list | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Memory panel | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Projects panel | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Tasks panel | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Control panel | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Diagnostics | ✅ golden.js | ❌ none | ✅ status bar | ❌ none | OVERLAP |
| Logs display | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |
| Shadow mode | ✅ golden.js | ❌ none | ❌ none | ❌ none | **NEW** |

---

## 3. Summary: What's NEW vs What's OVERLAP vs What's MISSING

### NEW in jarvis-ui (not in production)
1. **3-column layout** with panels
2. **Canvas orb/HUD** (1820 lines of 3D rendering)
3. **7 themes** + 6 visual modes
4. **Boot animation**
5. **Quick action chips**
6. **Capability grid**
7. **Settings modal** (backend URL, voice, theme)
8. **GOLDEN panel** (mission, agents, memory, projects, tasks, control, logs)
9. **Voice** (recognition, TTS, wake word) — BLOCKED
10. **SFX tones**
11. **Search** (Bing, Wikipedia, DuckDuckGo, HN)
12. **Metrics** (GPU, battery, network, canvas FPS)
13. **Clock display**
14. **Shadow mode**
15. **Visual effects** (scanlines, vignette, orb rings)

### OVERLAP (exists in both)
1. WebSocket communication
2. Chat messages
3. Command input
4. Conversation history
5. Theme support (basic)
6. Status indicators
7. Responsive design
8. CSS variables
9. Reconnect logic
10. Ollama status
11. MT5 status

### MISSING from jarvis-ui (exists in production only)
1. **Markdown rendering** (marked.js)
2. **Code highlighting** (highlight.js)
3. **Confirmation flow** (approve/reject buttons)
4. **Device auth pairing** (code input screen)
5. **Protocol auto-detection** (ws/wss)
6. **Frame-busting** (clickjacking protection)
7. **Robot list** (MQL5 EAs)
8. **Backtest panel**
9. **Scanner panel**
10. **Strategy comparison**
11. **Validation panel**
12. **Compilation form**
13. **Market ticker**
14. **Security panel**
15. **PWA manifest/service worker**

---

## 4. Integration Strategy

### Phase A: Core Visual Shell (Staging)
- Adopt jarvis-ui 3-column layout + panels
- Keep studio_v7.html as fallback (replace later)
- Add markdown rendering + code highlighting from production
- Add confirmation flow from production
- Add device auth pairing from production
- Add protocol auto-detection from production
- Add frame-busting from production

### Phase B: Security Hardening
- Replace bridge.js X-Ja-Token with device auth
- Replace brain.js direct commands with Gateway routing
- Replace eval() with safe math parser
- Replace jarvis-standalone.js with Gateway adapter
- Remove probeOllama() direct calls

### Phase C: Feature Parity
- Add robot list from dashboard.html
- Add backtest/scanner/comparison from dashboard.html
- Add market ticker from dashboard.html
- Add security panel from dashboard.html

### Phase D: Visual Polish
- 7 themes + visual modes
- Canvas orb/HUD
- Boot animation
- SFX tones
- Visual effects

---

**END OF STEP 6**
