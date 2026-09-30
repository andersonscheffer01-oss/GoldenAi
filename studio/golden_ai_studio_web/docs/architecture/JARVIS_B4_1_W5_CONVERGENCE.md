# Jarvis B4.1 Wave 5 Convergence

Status: `PASS_WITH_RESTRICTIONS`

## Scope

Wave 5 audited the active legacy provider and high-risk surfaces after the
Wave 4R visual closure. No provider request, MT5 initialization, trading,
Strategy Tester, MQL5 compilation, Voice initialization, microphone access, or
database migration was performed by the validation work.

## Provider authority

| Route | Before | Wave 5 decision | Result |
|---|---|---|---|
| `/api/chat` | Direct Ollama call and local conversation store | `DELEGATE` | Compatibility route calls `JarvisService.generate_response`, which owns Brain, ModelRouter, conversation history, and AuditLog correlation. |
| `/api/agent` | Direct legacy `_execute_tool` dispatch | `DELEGATE` | Compatibility route calls `JarvisService.execute_tool` with HTTP/session correlation and canonical SecurityManager approval semantics. |
| `/stream/chat` | Direct provider branches with SSE | `FREEZE` | HTTP auth remains in front of the route; the route remains for Studio compatibility because canonical ModelRouter has no equivalent streaming contract yet. |

No new provider policy was introduced. Existing provider adapters remain
available to the canonical ModelRouter and to the explicitly frozen streaming
compatibility path.

The remaining direct provider call sites are limited to the frozen SSE handler
and provider adapter implementations. They are not reclassified as canonical:

- Ollama, Gemini, Groq, Claude/OpenRouter, Cline, and Codex branches remain in
  `handle_stream` for the legacy Studio SSE contract.
- The canonical `/api/jarvis/chat`, `/api/market/analyze`, and
  `/api/jarvis/golden/*` surfaces continue to use the Jarvis service boundary.
- No provider priority or fallback policy was changed by this wave.

## High-risk containment

The runtime profile continues to fail closed for MT5, scanner, risk,
validation, trading, Strategy Tester, MQL5 compile, and Voice surfaces under
`web-ai-safe`. The existing mutation handlers retain their authorization gate;
this wave did not invoke them. Desktop and filesystem tool calls reached from
the migrated `/api/agent` route are evaluated by Jarvis `SecurityManager`,
including approval, target, TTL, single-use, stale-target, and audit behavior
where the canonical tool contract provides those checks.

| Surface | Safe-profile result | Wave 5 classification |
|---|---|---|
| MT5 status/data, scanner, risk, validation | Blocked before handler dispatch | `LEGACY_CONTAINED` |
| Auto-trade, positions, close-position, strategy manager | Blocked before handler dispatch | `FREEZE_REQUIRED` |
| Strategy Tester, real backtest, MQL5 compile | Blocked before handler dispatch | `FREEZE_REQUIRED` |
| Desktop/filesystem/process tools through `/api/agent` | Canonical service gate | `CANONICAL_SAFE` for migrated tool contracts |
| Legacy direct high-risk handlers in the default profile | Not invoked or changed | `LEGACY_DIRECT_REMAINING` / follow-up scope |

## Remaining restrictions

- `/stream/chat` is still a direct-provider compatibility exception and is
  frozen until a canonical streaming adapter can preserve SSE, cancellation,
  history, and audit semantics without creating a second model authority.
- Some older route handlers and root `ExecutionService` compatibility code
  remain in the repository and require later caller-by-caller migration. They
  are not silently reclassified as canonical by this checkpoint.
- Real provider execution was intentionally not used for proof; runtime
  validation used static characterization and safe boundaries only.

## Architecture invariant

The migrated routes reuse the existing `JarvisService`, `Brain`,
`ModelRouter`, `SecurityManager`, and `AuditLog`. No parallel Core, model,
security, audit, task, memory, or trading authority was added.
