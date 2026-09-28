# Jarvis / Golden B2 Recovery Architecture

## Status

`B2` is a read-model and contract recovery batch. It preserves the B1
bridge and routes Golden capabilities through the existing Jarvis Core.

## Authority Chain

```text
Golden provider/read source
  -> GoldenReadBridge
  -> JarvisService tool registry
  -> SecurityManager / ToolRegistry / Jarvis Core
  -> Web/Desktop read clients
  -> AuditLog and canonical Memory V2 where applicable
```

Golden remains a donor or adapted provider. Jarvis Core remains the sole
execution, security, task, audit, and memory authority. B2 adds no second
brain, dispatcher, database, or VoiceService.

## Implemented Read Surfaces

- Scanner normalization preserves raw values, score semantics, status,
  alerts, movement, provenance, freshness, and fingerprints.
- Radar detail projects existing market, macro, calendar, ranking,
  validation, replay, and source-integrity data into a specialized read model.
- Risk detail exposes the existing risk calculation as read-only context.
- Validation detail preserves historical evidence classes and source context.
- Deep analysis uses deterministic existing Golden context and does not call a
  model when the read model is sufficient.
- The recovery manifest hashes known safe source artifacts without importing or
  modifying them.

## Scientific Memory Boundary

Scientific memory is adapted to the existing Memory V2 engine. Typed evidence,
hypotheses, experiments, revisions, conflicts, and supersession are represented
by canonical metadata, versions, entities, and graph relations. No parallel
memory service or mass import was created.

## Explicit Non-Goals

- No MT5, Strategy Tester, MQL5 compile, broker, order, or live-trading action.
- No voice, microphone, VAD, STT, TTS, or Windows audio change.
- No database migration, schema rewrite, or legacy-store modification.
- No new Robot/Market matcher or reconstructed Golden engine.
- No UI redesign; only proof rows for B2 read models are exposed.

`SCHEMA_CHANGE_REQUIRED: NO`
