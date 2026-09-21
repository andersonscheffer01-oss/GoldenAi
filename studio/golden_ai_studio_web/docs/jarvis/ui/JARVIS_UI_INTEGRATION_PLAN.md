# JARVIS UI — Integration Plan

> **STEP 7** — Detailed implementation roadmap for integrating jarvis-ui as the future visual shell
> **Date:** 2026-09-18
> **Status:** PLANNING — Do NOT execute until user confirms

---

## Architecture Target

```
┌─────────────────────────────────────────────────────────┐
│                    JARVIS UI (jarvis-ui)                 │
│  3-column layout · Canvas orb · 7 themes · Panels       │
├─────────────┬───────────────────┬───────────────────────┤
│  Col 1      │  Col 2            │  Col 3                │
│  Voice/Orb  │  Menu/Stage       │  Panels               │
│  HUD Canvas │  Chat/Capabilities│  Golden/System/Control │
├─────────────┴───────────────────┴───────────────────────┤
│                    UI Adapter Layer                      │
│  bridge.js → Gateway WS · brain.js → Gateway commands   │
│  metrics.js → Gateway telemetry · search.js → Gateway   │
├─────────────────────────────────────────────────────────┤
│                    Gateway (existing)                    │
│  HTTPS :8765 · WSS :8766 · Device Auth · SecurityMgr   │
├─────────────────────────────────────────────────────────┤
│                    Backend (existing)                    │
│  JarvisService · ToolRegistry · Brain · ModelRouter     │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Create Gateway Adapter (bridge replacement)
**File:** `src/gateway-adapter.js` (NEW)
**Replaces:** `bridge.js` (X-Ja-Token) + `jarvis-standalone.js` (direct Ollama)

```javascript
// gateway-adapter.js
// Derives gateway origin from location, uses device auth protocol
const GATEWAY = {
  get wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.hostname}:8766/ws`;
  },
  get httpUrl() {
    return `${location.origin}`;
  },
  // Device auth: token from localStorage, sent in WS hello message
  get token() {
    return localStorage.getItem("jarvis-device-token") || "";
  },
  connect() { /* WS connect with device auth hello */ },
  sendCommand(cmd) { /* Route through Gateway, not brain.js direct */ },
  fetchMetrics() { /* GET /api/telemetry */ },
  fetchModels() { /* GET /api/models */ },
  search(query) { /* POST /api/search via Gateway Browser tool */ },
};
```

### Step 2: Create Safe Math Parser (eval replacement)
**File:** `src/math-parser.js` (NEW)
**Replaces:** `brain.js` eval()/Function()

```javascript
// math-parser.js — safe expression evaluator
// Supports: +, -, *, /, %, ^, (), sin, cos, tan, sqrt, abs, log, pi, e
// No eval(), no Function(), no dynamic code execution
export function evaluate(expr) {
  // Tokenize → Parse → Evaluate
  // Recursive descent parser
}
```

### Step 3: Create Command Router (brain.js replacement)
**File:** `src/command-router.js` (NEW)
**Replaces:** `brain.js` direct command routing

```javascript
// command-router.js
// All commands route through Gateway → ToolRegistry
// No direct OS actions, no direct shell, no direct app control
import { GATEWAY } from "./gateway-adapter.js";

export async function routeCommand(input) {
  // 1. Check if command is safe for browser-side (clock, theme, etc.)
  // 2. Otherwise, send to Gateway → ToolRegistry
  const response = await GATEWAY.sendCommand(input);
  return response;
}
```

### Step 4: Create Telemetry Adapter
**File:** `src/telemetry-adapter.js` (NEW)
**Replaces:** `golden.js` probeOllama() + metrics.js backend calls

```javascript
// telemetry-adapter.js
// All backend telemetry via Gateway
import { GATEWAY } from "./gateway-adapter.js";

export async function fetchTelemetry() {
  return await GATEWAY.fetchMetrics();
}

export async function fetchModels() {
  return await GATEWAY.fetchModels();
}
```

### Step 5: Modify bridge.js
**Changes:**
- Remove `X-Ja-Token` header
- Import and use `gateway-adapter.js`
- Remove direct URL configuration
- Use dynamic origin derivation

### Step 6: Modify brain.js
**Changes:**
- Remove ALL direct OS commands (open/close apps, volume, media, power, screen, MT5, browser, files, processes)
- Remove eval()/Function() calculator
- Import `math-parser.js` for safe calculation
- Import `command-router.js` for Gateway routing
- Keep only browser-side commands (clock, theme, state)
- All other commands → `routeCommand()` → Gateway

### Step 7: Modify golden.js
**Changes:**
- Remove `probeOllama()` direct fetch
- Import `telemetry-adapter.js`
- Remove `window.root?.generateText` dependency (summarize button)
- Use Gateway-mediated Ollama status

### Step 8: Modify search.js
**Changes:**
- Remove `superFetch` dependency
- Import `GATEWAY.search()` for internet searches
- Keep search history in localStorage

### Step 9: Modify jarvis-config.js
**Changes:**
- Remove `backendUrl` (derive from location)
- Remove `backendToken` (use device auth)
- Remove `aiUrl` (use Gateway)
- Remove `fetchProxyUrl` (use Gateway)
- Keep themes, voice config, boot flag, systemName, userName

### Step 10: Delete jarvis-standalone.js
**Action:** Remove entirely — all functionality moved to gateway-adapter.js

### Step 11: Add Production Features
**From studio_v7.html:**
- Add `marked.js` for markdown rendering
- Add `highlight.js` for code highlighting
- Add confirmation flow (approve/reject buttons)
- Add frame-busting script
- Add PWA manifest + service worker

**From dashboard.html:**
- Add robot list panel
- Add backtest panel
- Add scanner panel
- Add strategy comparison panel
- Add validation panel
- Add compilation form
- Add market ticker
- Add security panel

**From mobile.html:**
- Add device auth pairing screen
- Add protocol auto-detection (ws/wss)
- Add token via WS message (not URL)

### Step 12: Create Staging Entry Point
**File:** `jarvis.html` (NEW — staging route)
- Loads jarvis-ui `index.html` structure
- Loads all modified JS modules
- Served at `https://192.168.1.100:8765/jarvis/`
- Existing UI remains at `studio_v7.html`, `dashboard.html`, `mobile.html`

### Step 13: Integration Testing
- Verify jarvis-ui loads at `/jarvis/` staging URL
- Verify all panels render correctly
- Verify canvas orb renders
- Verify 7 themes work
- Verify chat messages display with markdown
- Verify code highlighting works
- Verify commands route through Gateway
- Verify no direct Ollama/shell/eval calls
- Verify device auth flow works
- Verify WSS connection under HTTPS
- Run full regression (453+ tests)

---

## File Change Summary

| Action | File | Lines Changed |
|--------|------|---------------|
| CREATE | `src/gateway-adapter.js` | ~150 |
| CREATE | `src/math-parser.js` | ~200 |
| CREATE | `src/command-router.js` | ~100 |
| CREATE | `src/telemetry-adapter.js` | ~80 |
| CREATE | `jarvis.html` (staging) | ~50 |
| MODIFY | `src/bridge.js` | ~80 lines |
| MODIFY | `src/brain.js` | ~300 lines (heavy) |
| MODIFY | `src/golden.js` | ~40 lines |
| MODIFY | `src/search.js` | ~60 lines |
| MODIFY | `src/jarvis-config.js` | ~20 lines |
| DELETE | `src/jarvis-standalone.js` | -60 lines |
| ADD | `marked.min.js` | (CDN or local) |
| ADD | `highlight.min.js` | (CDN or local) |
| ADD | `css/github-dark.min.css` | (CDN or local) |

---

## Security Verification Checklist

Before staging is considered PASS:

- [ ] No `eval()` or `Function()` anywhere in modified code
- [ ] No direct Ollama calls (all via Gateway)
- [ ] No direct shell/OS commands from browser
- [ ] No `X-Ja-Token` header (device auth only)
- [ ] No `backendUrl` hardcoding (derived from location)
- [ ] No `superFetch` dependency (Gateway fetch proxy)
- [ ] No `window.root.generateText` (Gateway adapter)
- [ ] No `serve_ui.py` or `backend/jarvis_server.py` usage
- [ ] All commands route through Gateway → ToolRegistry
- [ ] WSS works under HTTPS secure context
- [ ] Frame-busting present
- [ ] Markdown rendering works
- [ ] Code highlighting works
- [ ] Confirmation flow works
- [ ] Device auth pairing works
- [ ] 453+ tests pass, 0 failures

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| brain.js rewrite breaks command parsing | HIGH | Unit test every command before/after |
| Gateway adapter loses messages | MEDIUM | Buffer + retry logic |
| Canvas orb performance on mobile | LOW | Quality auto-adjust (already in hud.js) |
| Markdown XSS via marked.js | MEDIUM | Sanitize HTML output |
| Breaking existing 453 tests | HIGH | Run regression after every change |
| Voice P1.4C accidentally activated | LOW | Keep voice.js as reference only |

---

**END OF STEP 7 — INTEGRATION PLAN**
