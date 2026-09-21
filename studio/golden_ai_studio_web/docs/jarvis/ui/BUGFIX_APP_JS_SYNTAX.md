# BUG FIX — app.js Syntax Error

**Date:** 2026-09-18
**Status:** FIXED

---

## Final Report

| Field | Value |
|-------|-------|
| ROOT_CAUSE | Orphaned `} catch (e) {` block at line 561 with no matching `try`. Left over from UI-1.1 rewrite of `aiAsk` — original had `msg.finalize()` in catch, but Gateway rewrite removed the try/catch structure while leaving the catch block. |
| APP_JS_ERROR_LINE_BEFORE | 561 |
| FILES_MODIFIED | `jarvis_ui/src/app.js` (1 line removed) |
| JS_SYNTAX_ERRORS | **0/11** |
| BOOT_SKIP_BUTTON | PASS (PULAR button functional) |
| BOOT_AUTO_COMPLETE | PASS (boot overlay completes) |
| MAIN_UI_RENDERED | PASS (interface loads after boot) |
| CONSOLE_ERRORS | **0** |
| REFERENCE_ORIGINAL_MODIFIED | NO |
| REGRESSION | 99 passed / 0 failed / 0 skipped (core tests) |

---

## Root Cause Detail

The `aiAsk` function in `app.js` was rewritten in UI-1.1 to use Gateway instead of `window.root.generateText`. The original code had:

```javascript
aiAsk: async (text) => {
  const gen = window.root?.generateText;
  if (!gen) return null;
  const msg = addMessage("jarvis", "");
  msg.body.classList.add("typing");
  let full = "";
  try {
    await gen({ instruction: ..., onChunk: ... });
    msg.finalize(full.trim() || "…");
    return { text: full.trim(), streamed: true };
  } catch (e) {
    msg.finalize("Não consegui consultar o núcleo de IA agora.");
    return null;
  }
},
```

The Gateway rewrite replaced the body but left the old `catch` block (lines 561-564):

```javascript
aiAsk: async (text) => {
  if (!window.Gateway || !window.Gateway.isAuthenticated) return null;
  try {
    const result = await window.Gateway.sendCommand(text);
    if (result && result.text) {
      return { text: result.text, streamed: false };
    }
  } catch(e) { console.warn('Gateway AI ask failed:', e); }
  return null;
  } catch (e) {  // <-- ORPHANED: no matching try
    msg.finalize("Não consegui consultar o núcleo de IA agora.");
    return null;
  }
},
```

---

## Fix Applied

Removed the orphaned catch block (lines 561-564). The corrected function:

```javascript
aiAsk: async (text) => {
  if (!window.Gateway || !window.Gateway.isAuthenticated) return null;
  try {
    const result = await window.Gateway.sendCommand(text);
    if (result && result.text) {
      return { text: result.text, streamed: false };
    }
  } catch(e) { console.warn('Gateway AI ask failed:', e); }
  return null;
},
```

---

## Validation

| Check | Result |
|-------|--------|
| node --check app.js | OK |
| node --check bridge.js | OK |
| node --check brain.js | OK |
| node --check gateway-adapter.js | OK |
| node --check command-router.js | OK |
| node --check math-parser.js | OK |
| node --check telemetry-adapter.js | OK |
| node --check golden.js | OK |
| node --check search.js | OK |
| node --check trading-panels.js | OK |
| node --check markdown-sanitizer.js | OK |
| Server serves fixed app.js | OK |
| aiAsk ends cleanly at line 561 | OK |
| No SyntaxError in console | OK |

---

## Staging URL

```
https://192.168.1.100:8765/jarvis_ui/jarvis.html
```
