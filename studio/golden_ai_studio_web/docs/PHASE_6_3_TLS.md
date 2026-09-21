# Phase 6.3 — HTTPS/WSS LOCAL

**Date:** 2026-09-17
**Status:** COMPLETE

---

## Architecture

```
Root CA (self-signed, persistent)
    ↓ signs
Server Certificate (per-LAN-IP, SAN-based)

server_agent.py
  → LanConfig (GOLDEN_SSL=1)
  → SSLContext load (certs/golden-local-server.pem + key)
  → HTTPServer + ssl_context → HTTPS (8765)
  → Gateway + ssl_context → WSS (8766)
  → Dual bind preserved (loopback + LAN)
```

## Certificate Strategy

**LOCAL CA** — Root CA + Server Certificate signed by it.

### Files

```
C:\GoldenAI\certs\
  ├── golden-local-ca.pem          ← Root CA public cert
  ├── golden-local-ca.key          ← Root CA private key
  ├── golden-local-ca.cer          ← DER format (for device trust)
  ├── golden-local-server.pem      ← Server cert (signed by CA)
  ├── golden-local-server.key      ← Server private key
  └── metadata.json                ← fingerprints, dates, SANs
```

### Root CA

- RSA 4096 bits
- SHA-256
- BasicConstraints: CA=true, path_length=0, critical
- KeyUsage: keyCertSign=true, crlSign=true, critical
- Validity: 3650 days (10 years)
- NO serverAuth EKU

### Server Certificate

- RSA 2048 bits
- SHA-256
- BasicConstraints: CA=false, critical
- KeyUsage: digitalSignature=true, keyEncipherment=true, critical
- ExtendedKeyUsage: serverAuth ONLY (no clientAuth)
- SubjectAlternativeName: DNS:localhost, IP:127.0.0.1, IP:::1, IP:<LAN_IP>
- Validity: 365 days (< 825 mandatory)
- Signed by Root CA

## Usage

### 1. Initialize Certificates (one time)

```cmd
cd C:\GoldenAI\studio\golden_ai_studio_web
C:\GoldenAI\.venv\Scripts\python.exe -m jarvis_core.ssl_context init
```

### 2. Start with SSL

```cmd
set GOLDEN_GATEWAY_LAN=1
set GOLDEN_SSL=1
python server_agent.py
```

### 3. Access

- Dashboard: `https://192.168.1.100:8765/dashboard.html`
- Studio: `https://192.168.1.100:8765/studio_v7.html`
- Mobile: `https://192.168.1.100:8765/mobile.html`
- WebSocket: `wss://192.168.1.100:8766/ws`

## CLI Commands

### Init

```cmd
python -m jarvis_core.ssl_context init
```

Creates CA + server cert. Idempotent (does not regenerate CA if exists).

### Renew Server Certificate

```cmd
python -m jarvis_core.ssl_context renew-server
```

Regenerates server cert (same CA, new SANs if IP changed).

### Status

```cmd
python -m jarvis_core.ssl_context status
```

Shows certificate status, fingerprints, validation.

### Add Trust (Windows)

```cmd
python -m jarvis_core.ssl_context add-trust
```

Adds Root CA to Windows Current User trust store via `certutil`.

## Fail Closed

With `GOLDEN_SSL=1`:

| Condition | Behavior |
|---|---|
| Certificates missing | **FATAL ERROR, startup stops** |
| Certificates invalid | **FATAL ERROR, startup stops** |
| Server cert expired | **FATAL ERROR, startup stops** |
| SAN mismatch | **FATAL ERROR, startup stops** |
| SSLContext load error | **FATAL ERROR, startup stops** |

**NEVER** falls back to HTTP/WS silently.

## Private Key Protection

- Private keys NOT in `studio/` web root
- Private keys NOT served by HTTP/HTTPS
- Private keys NOT sent to PWA
- Private keys NOT logged
- Private keys NOT in API responses
- Private keys NOT in `metadata.json`

## Origin Validation (SSL Enabled)

| Origin | Allowed |
|---|---|
| `https://localhost:8765` | YES |
| `https://127.0.0.1:8765` | YES |
| `https://192.168.1.100:8765` | YES |
| `http://127.0.0.1:8765` | YES (localhost dev) |
| `http://192.168.1.100:8765` | **NO** (rejected) |

## Frontend Protocol Detection

```javascript
const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
const GATEWAY_WS = `${wsProto}//${location.hostname}:8766/ws`;
```

No hardcode. Automatic detection.

## Windows Trust Procedure

```cmd
certutil -addstore -user Root C:\GoldenAI\certs\golden-local-ca.cer
```

Or via CLI:

```cmd
python -m jarvis_core.ssl_context add-trust
```

**WINDOWS_CA_TRUSTED** must be YES before browser accepts cert without warning.

## iPhone Trust Procedure (NOT TESTED IN PHASE 6.3)

1. Transfer `golden-local-ca.cer` to iPhone (AirDrop, email, Safari)
2. Settings → General → Profiles → install CA profile
3. Settings → General → About → Certificate Trust Settings → enable full trust for Golden AI Local Root CA
4. Access `https://192.168.1.100:8765/mobile.html`

**Do NOT assume Safari accepts after one warning.** Must install CA explicitly.

## Server Certificate Rotation

If LAN IP changes:

```cmd
python -m jarvis_core.ssl_context renew-server
```

- Same Root CA (persists)
- New server cert with updated SANs
- Restart server

## Environment Variables

| Variable | Values | Default |
|---|---|---|
| `GOLDEN_SSL` | `0` / `1` | `0` (plain HTTP) |
| `GOLDEN_GATEWAY_LAN` | `0` / `1` | `0` (localhost only) |

## Dependency

```
cryptography>=42.0.0
```

Installed in `C:\GoldenAI\.venv` only. Registered in `C:\GoldenAI\requirements.txt`.

## Test Command

```bash
C:\GoldenAI\.venv\Scripts\python.exe -m pytest tests/test_phase6_3.py -v
```

## Prohibited Regressions

- Never fallback to HTTP when GOLDEN_SSL=1
- Never expose private keys via web
- Never auto-generate CA during normal startup
- Never test iPhone in this phase
- Never weaken SecurityManager
- Never bind 0.0.0.0 without explicit opt-in
