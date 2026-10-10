# JARVIS / GOLDEN — Security Authority Map

## Canonical security chain

```text
Web/Desktop request
  -> JarvisService / canonical command router
  -> ToolRegistry risk and side-effect metadata
  -> SecurityManager policy/approval
  -> provider/tool execution
  -> AuditLog receipt and redaction
```

`SecurityManager` is fail-closed and approvals are scoped/expiring where required. `AuditLog` redacts sensitive fields. `ModelRouter` applies provider/privacy policy; secret-classified work must remain local. Computer Use and task scheduling reuse the same service/security/audit ownership.

## Legacy security surfaces

| Surface | Static behavior | Classification |
|---|---|---|
| `server_agent.py` mutation helpers | route-specific `_authorize_api_mutation` checks exist | legacy gate; not canonical authority |
| Dashboard confirmations | some full-analysis/auto actions use browser confirmation; Scanner modal path posts directly | UX guard, not sufficient policy |
| `/api/mt5/auto_trade` | invokes `mt5_real_order` authorization when `auto_execute` is true | broker side effect; frozen |
| `mt5_trader.py` | risk engine and broker request construction | domain/trading legacy authority |
| Direct provider calls | Cline/OpenRouter in deep analysis; legacy chat/provider code elsewhere | duplicate model-routing authority |
| Browser voice | browser permission and browser provider | not Core security/audit owner |
| Direct shell/PowerShell/desktop helpers | legacy operational surfaces | dangerous; do not migrate directly |
| MCP | provider/tool source | never independent security or execution authority |

## Existing Golden Scanner trade path

The scanner’s read endpoint is mixed with `ensure_connection()` and can return `integrated_robots`, but the read itself is not a broker mutation. The `ENTRAR NO TRADE` and `AUTO-TRADE` paths cross the mutation boundary via `/api/mt5/auto_trade`. The backend’s authorization call is an important guard, but it does not make the legacy route canonical: route reachability, UI timer state, confirmation behavior, policy scope, AuditLog receipt and broker result association still require explicit Core containment.

The target model is a Jarvis proposal/read model for scanner evidence. A live execution command, if ever authorized, must be a distinct ToolRegistry entry with explicit `Risk.CRITICAL`, confirmation/approval, account/symbol/volume/SL/TP validation, idempotency/duplicate protection, broker result receipt and AuditLog provenance. No such canonical live-order tool is claimed by this audit.

## Security decisions

- `SecurityManager`, `ToolRegistry`, `JarvisService` and `AuditLog`: `KEEP_OURS`.
- Legacy route checks and UI confirmations: `REFERENCE_ONLY`/`ADAPT` as defense-in-depth, never authority.
- Direct Golden broker routes: `LEGACY_FREEZE`.
- Credentials, `.env`, `config/api_keys.json`, cookies and device registry: protected and untouched.
- Production EAs, historical backtests, broker/account state and live settings: untouched.
