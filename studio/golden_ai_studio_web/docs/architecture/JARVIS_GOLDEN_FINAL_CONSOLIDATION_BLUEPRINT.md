# JARVIS / GOLDEN — Final Consolidation Blueprint

## Target architecture

```text
Jarvis Web / Jarvis Desktop
        -> canonical Jarvis read/control models
        -> JarvisService
        -> ToolRegistry
        -> SecurityManager
        -> ModelRouter / bounded domain adapters
        -> providers and read-only MT5/market boundaries
        -> AuditLog + provenance receipts
```

Golden remains a domain donor and legacy surface; it does not become a second Jarvis. There is one Core, one tool registry, one security authority, one audit authority, one task scheduler, one memory boundary, one model router and one VoiceService.

## Existing Golden Scanner trade path

The current path is:

```text
Scanner radar -> dashboard modal/timer -> /api/mt5/auto_trade
-> legacy mutation authorization -> mt5_trader -> risk_engine
-> mt5.order_send -> broker result -> journal/UI message
```

`Análise Profunda` adds:

```text
/api/mt5/full_analysis -> deterministic engines -> optional Cline/OpenRouter
-> journal/setup persistence -> optional trade button
```

This is valuable evidence of existing capability, but it is not a canonical Jarvis execution path. Keep it frozen, document it, and adapt scanner/deep-analysis output into read-only/proposal contracts before any control-center integration. Do not silently wire the dashboard mutation route into Jarvis.

## Canonical keep/port/freeze list

### Keep from Jarvis

`JarvisService`, `ToolRegistry`, `SecurityManager`, `AuditLog`, `TaskManager`/scheduler, mission persistence, memory boundary, `ModelRouter`, canonical VoiceService/realtime voice, browser/UIA security and read-only MT5 tools.

### Keep from Golden as bounded domain capability

Golden Scanner/setup definitions, regime and market calculations, macro/radar presentation, risk calculation inputs, validation vocabulary, journal/history read models, MQL5 source/artifact facts and existing MQL5 evidence contracts.

### Freeze or reject as new authority

Direct `/api/chat` tool loops, browser voice capture as Core voice, direct Cline/OpenRouter routing, legacy task/memory databases, direct shell/desktop paths, dashboard `AUTO-TRADE`, `ENTRAR NO TRADE`, `mt5_trader.order_send`, position-manager mutation, credential/config mutation, device registry changes and historical artifact rewriting.

## Recommended integration sequence

1. Complete read-only inventory and preserve current artifacts.
2. Establish Core read models for health, market/radar, scanner/opportunities, strategies, robot catalog, tester evidence, voice state and provenance.
3. Adapt Golden domain outputs with explicit source/version/hash/timestamp/stale metadata.
4. Make Web and Desktop consume the same read/control models.
5. Route model selection, tool calls, approvals and audit receipts through Core.
6. Reconcile historical backtests without rewriting them.
7. Prove parity and failure states in focused tests.
8. Design a separate, explicit broker-execution gate only after all read/provenance/security conditions pass.

## Gates and restrictions

`B1`: read models and containment review only.
`B2+`: parity/provenance/security validation.
`LIVE_EXECUTION`: separate approval, never implied by Scanner parity.
`VOICE_REAL_GATE`: real speech/VAD/barge-in remains pending and must not be bypassed by browser recognition.

## Final blueprint verdict

`ZERO_FEATURE_LOSS_STATUS: NOT YET PROVEN` because parity and runtime validation are incomplete.
`ARCHITECTURE_STATUS: CONSOLIDATION-READY FOR READ-ONLY DESIGN REVIEW`.
`BROKER_EXECUTION_STATUS: LEGACY_FREEZE`.
`VOICE_STATUS: ONE CANONICAL VOICESERVICE; REAL ACOUSTIC GATE PENDING`.
`PROVENANCE_STATUS: CANONICAL FOUNDATION PRESENT; FULL CROSS-SURFACE RECONCILIATION PENDING`.
