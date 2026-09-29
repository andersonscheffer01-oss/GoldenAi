# Jarvis / Golden B3 Control Center

Status: implementation checkpoint, read-only product integration.

## Authority

B3 extends the existing Jarvis Control Center in `jarvis.html` and `app.js`.
The UI calls the Gateway, the HTTP layer calls `JarvisService.execute_tool`,
and the existing `SecurityManager`, `ToolRegistry`, `AuditLog`, Golden bridge,
Robot Catalog, and canonical Memory V2 remain the authorities.

There is no second frontend, Golden brain, scanner, radar, memory store, or
execution engine. Golden remains a subordinate provider of read models.

## Read Models

The Control Center requests independent projections:

| Product area | Endpoint | Boundary |
| --- | --- | --- |
| Overview | `/api/jarvis/golden/overview` | Jarvis control-center summary |
| Radar / market detail | `/api/jarvis/golden/radar` | `golden_radar_detail` |
| Scanner / opportunities | `/api/jarvis/golden/scanner` | `golden_scanner_snapshot` |
| Robot catalog | `/api/jarvis/golden/robots` | `robot_catalog_snapshot` |
| Robot detail | `/api/jarvis/golden/robot` | `robot_catalog_detail` |
| Validation and tester evidence | `/api/jarvis/golden/evidence` | existing evidence read tools |
| Scientific memory | `/api/jarvis/memory/scientific` | canonical Memory V2 adapter |

The evidence endpoint joins two existing read projections; it does not run a
backtest, compile MQL5, start a tester, discover robots, or mutate a database.

## UI Contract

The Control Center exposes overview metrics, Radar assets and detail context,
scanner ranking and opportunity detail, robot identity/evidence, unresolved
historical evidence, validation classes, scientific-memory contracts and a
provenance/source-integrity table. The score label remains `SCORE`; it is not a
probability.

Every panel preserves `UNKNOWN`, `EMPTY`, `PARTIAL`, `STALE`, `UNAVAILABLE`, and
`ERROR` semantics. `ACTIVE` is displayed as active in repertoire and never as
authorization to trade. There is no trade action, auto-trade action, or legacy
`ENTRAR NO TRADE` affordance in the B3 panel.

## Web and Desktop

Web and Desktop reuse the same `jarvis.html`, `app.js`, and Gateway boundary.
No Desktop-specific Control Center implementation was created.

## Validation Boundary

Runtime visual validation is not claimed by this document unless a separate
safe rendering gate produces evidence. Static validation must include Python
compile, Node syntax checks, B3 focused tests, protected regressions, secret
scan, and `git diff --check`.
