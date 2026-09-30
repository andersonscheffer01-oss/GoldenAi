# Jarvis B4.3 Robot Intelligence Foundation

## Scope

B4.3 projects the existing `RobotCatalogReadModel`, stored MQL5/tester
evidence, and the B4.2 market snapshot into one Jarvis-owned read model.
It does not discover, compile, attach, enable, test, or trade a robot.

## Authority

`JarvisService -> GoldenReadBridge -> robot_intelligence.py` is the canonical
read path. `RobotCatalogReadModel` remains the single subordinate catalog and
`robot_catalog.db` remains its existing store. No second catalog, matcher,
brain, scheduler, security model, or database was introduced.

## Semantics

`DISCOVERED`, `CANDIDATE`, `ACTIVE`, `INACTIVE`, `BLOCKED`, and `ARCHIVED` are
repertoire states only. Every projection carries `trading_authorization:
NOT_GRANTED`. User overrides remain distinct from system inference and
evidence-derived fields.

## Evidence and suitability

Stored artifacts are fingerprint-deduplicated and retain evidence type,
association status, source, market labels, metrics, and limitations. Missing
labels remain `UNKNOWN`. Suitability is structural/declared and explainable;
empirical matching, opaque AI scores, and fake probabilities are explicitly
disabled.

## Current boundary

The route `/api/jarvis/golden/robot-intelligence` exposes catalog profiles,
evidence dataset status, temporal contract, and current-market suitability.
The Control Center labels the result `ANALYSIS ONLY` and keeps execution
outside this capability.

## Current evidence posture

The existing catalog snapshot observed one archived fixture with one source
and one compiled reference; its stored tester evidence remains historical and
does not authorize execution. This is insufficient for an empirical
Robot-to-Market matcher.
