# Jarvis Golden B1 Capability Bridge

## Scope

B1 adds a canonical, read-only projection from existing Golden engines into
the existing JarvisService, ToolRegistry and Control Center. It does not add a
second engine, provider router, execution authority, database migration or
runtime migration.

Canonical chain:

`Golden implementation -> GoldenReadBridge -> JarvisService -> ToolRegistry / HTTP read route -> Jarvis Web/Desktop Control Center`

Jarvis remains the authority for security, approvals, tool dispatch, audit and
provider routing. Golden remains the owner of domain calculations that are
only observed by this bridge.

## Registry contract

The registry is explicit for ten capabilities: scanner, radar, market data,
market regime, meta strategy, risk engine, validation, strategies, MQL5 and
deep analysis. Each entry records the canonical owner, implementation owner,
source module, read capabilities, mutation capabilities, side-effect level,
security requirement, audit requirement, provenance support, legacy status,
health and availability.

Every B1 envelope declares `read_only: true`, `side_effect_class: READ_ONLY`,
`security_state: READ_ONLY_NO_SIDE_EFFECT`, an evidence class and provenance.
Missing providers become `UNKNOWN`, `UNAVAILABLE` or `STALE`; they are not
represented as healthy live data.

## Safety boundary

The B1 tools are low-risk, excluded from unrestricted LLM tool exposure and
carry `READ_ONLY`, `NO_SIDE_EFFECT` and `NO_TRADING` requirements. The
Control Center route defaults to `include_live: false`. Legacy `AUTO-TRADE`,
`ENTRAR NO TRADE` and `order_send` paths remain frozen and are never called by
the bridge. Voice remains out of scope for this batch.

## Evidence policy

Historical tester records are read from the existing Robot Catalog projection;
B1 does not discover robots, compile MQL5, launch MT5 or run Strategy Tester.
Scanner scores are preserved with explicit `SCORE_NOT_PROBABILITY` semantics.
All read models expose source, calculation origin, timestamp and freshness
metadata where the underlying implementation provides it.

## Implemented surfaces

- `jarvis_core/golden_bridge.py`: normalization and read envelopes.
- `jarvis_core/service.py`: canonical service wrappers and read-only tools.
- `server_agent.py`: `/api/jarvis/golden/overview` projection route.
- `jarvis_ui/jarvis.html` and `jarvis_ui/src/app.js`: minimal Control Center
  read panel using the existing Gateway.
