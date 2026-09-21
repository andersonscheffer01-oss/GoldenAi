# Jarvis Mobile — LAN Access + Device Pairing + PWA

> **Status:** V1 — Phase 6 Complete
> **Date:** 2026-09-17
> **Security:** LAN-only, opt-in, no public internet

---

## Architecture

```
iPhone/PWA
    ↓
LAN (Wi-Fi)
    ↓
Device Pairing
    ↓
Gateway WebSocket (8766)
    ↓
AuthManager (shared token OR device token)
    ↓
JarvisService
    ↓
SecurityManager
    ↓
ToolRegistry
```

**Key principle:** LAN access is OPT-IN. Default remains 127.0.0.1.

---

## Quick Start

### 1. Enable LAN Mode

On the PC, set environment variable:

```cmd
set GOLDEN_GATEWAY_LAN=1
```

Or in PowerShell:

```powershell
$env:GOLDEN_GATEWAY_LAN = "1"
```

Then start Jarvis normally. Gateway will bind to your private IP (e.g., 192.168.1.x).

### 2. Check Gateway Status

Open browser on PC:
```
http://127.0.0.1:8766/health
```

You should see:
```json
{
  "ok": true,
  "gateway": "running",
  "lan_enabled": true,
  "bind_address": "192.168.1.x"
}
```

### 3. Generate Pairing Code

On PC, the gateway will display a pairing code. Or call:
```
POST http://127.0.0.1:8766/pairing/code
```

Response:
```json
{
  "ok": true,
  "code": "ABCD1234",
  "ttl": 300
}
```

### 4. Pair iPhone

1. Open Safari on iPhone
2. Navigate to: `http://192.168.1.x:8765/mobile.html`
3. Enter the pairing code
4. Tap "Conectar"

### 5. Use Jarvis

Once paired, you can type commands:
- "qual o status do sistema?"
- "abra o browser"
- "leia a página atual"

---

## Device Pairing

### How It Works

1. PC generates 8-char code (e.g., `ABCD1234`)
2. Code is valid for 5 minutes
3. Code is single-use
4. iPhone enters code
5. Gateway validates and registers device
6. Device receives unique token
7. Future connections use device token (no code needed)

### Pairing Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pairing/code` | POST | Generate new pairing code |
| `/pairing/confirm` | POST | Confirm pairing with code |
| `/devices` | GET | List registered devices |

### Device Token

After pairing, device receives a 48-byte URL-safe token:
```
dj_AbCdEfGhIjKlMnOpQrStUvWxYz1234567890abcdefghijklmnop
```

This token:
- Is stored in browser localStorage
- Is sent with every WebSocket auth
- Is hashed for storage (never plaintext)
- Can be revoked from PC

### Revoking a Device

```python
from jarvis_core.device_pairing import get_device_pairing_service

svc = get_device_pairing_service()
svc.revoke_device("dev_xxxxxxxx")
```

---

## LAN Mode

### Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `GOLDEN_GATEWAY_LAN` | `0` | Enable LAN mode (1=on, 0=off) |

### Bind Address

When LAN mode is OFF:
```
127.0.0.1 (localhost only)
```

When LAN mode is ON:
```
192.168.x.x (private IP)
```

The system automatically detects the best private interface:
- Prefers 192.168.x.x (most common)
- Falls back to 10.x.x.x or 172.16.x.x

### Network Security

LAN mode ONLY accepts connections from private networks:
- 127.0.0.0/8 (loopback)
- 10.0.0.0/8 (Class A)
- 172.16.0.0/12 (Class B)
- 192.168.0.0/16 (Class C)
- fc00::/7 (IPv6 ULA)
- fe80::/10 (IPv6 link-local)

Public IPs are REJECTED.

---

## Firewall

If Windows Firewall blocks access, you need to add rules:

```cmd
netsh advfirewall firewall add rule name="Golden AI Studio" dir=in action=allow protocol=TCP localport=8765 profile=private
netsh advfirewall firewall add rule name="Golden AI Gateway" dir=in action=allow protocol=TCP localport=8766 profile=private
```

**Important:** Use `profile=private` only. Never use `profile=public`.

---

## PWA (Progressive Web App)

### Files

| File | Purpose |
|------|---------|
| `mobile.html` | Mobile interface |
| `manifest.json` | PWA manifest |
| `sw.js` | Service worker |

### Features

- Dark theme (matches Jarvis aesthetic)
- Pairing flow
- Command input
- Result display
- Confirmation dialogs
- Connection status
- Auto-reconnect
- Offline cache (static assets)

### Install on iPhone

1. Open Safari
2. Navigate to `http://192.168.1.x:8765/mobile.html`
3. Tap Share button
4. Tap "Add to Home Screen"
5. Name it "Jarvis"

The app will now appear on your home screen.

---

## Confirmation Flow

When a command requires confirmation:

1. PWA shows confirmation dialog
2. User sees: action, risk, summary
3. User taps "Confirmar" or "Cancelar"
4. Response sent to Gateway
5. Gateway forwards to SecurityManager
6. Command executed or cancelled

**Security:** PWA does NOT decide security. It only forwards user's choice.

---

## Secrets

iPhone NEVER receives:
- OpenAI API key
- Groq API key
- Gemini API key
- MT5 password
- config/api_keys.json
- Database secrets

Only the device-specific token.

---

## Reconnect

If iPhone loses Wi-Fi:
1. WebSocket closes
2. PWA shows "Desconectado"
3. Auto-reconnect attempts every 3 seconds
4. On reconnect, device token is re-sent
5. Session resumes (no re-auth needed)

Idempotency from Phase 4 prevents duplicate command execution.

---

## Troubleshooting

### "Origin not allowed"

Add your LAN origin to allowed list:
```python
from jarvis_core.lan_config import add_lan_origin
add_lan_origin("192.168.1.x")
```

### "Pairing code expired"

Generate a new code:
```
POST http://127.0.0.1:8766/pairing/code
```

### "Device revoked"

Re-pair the device from scratch.

### Gateway won't start on LAN

Check if port is already in use:
```cmd
netstat -ano | findstr 8766
```

---

## What's NOT in V1

- Internet exposure
- Cloud/VPS
- Push notifications
- Camera/microphone streaming
- File uploads/downloads
- Remote desktop
- WhatsApp integration

These are explicitly excluded for V1.
