# Jarvis / Golden B2 Capability Parity

## Recovery Status

| Capability | B2 result | Boundary |
| --- | --- | --- |
| Scanner | preserved and enriched | read-only Golden bridge |
| Radar | specialized read model added | existing market/macro providers |
| Meta strategy | existing matching coverage exposed | no new matcher |
| Risk | existing calculation context exposed | no order or broker action |
| Validation | evidence classes and history preserved | provenance-aware read model |
| Deep analysis | deterministic context preserved | no unnecessary model call |
| Scientific memory | typed contract adapted | canonical Memory V2 |
| Provenance | envelope and fingerprints added | source-time aware |
| Freshness | provider/capability policy added | explicit unknown/unavailable |

## Integration

The service registers B2 as read-only, no-side-effect, no-trading tools. The
HTTP layer invokes those tools through the existing Jarvis service boundary.
The shared UI shows compact proof rows for Radar and scientific-memory status;
it does not become a second control center.

Security remains under the existing `SecurityManager` and `ToolRegistry`.
Audit and task authority remain in Jarvis Core. Robot and tester provenance
remain under their existing adapters and were not executed by B2.

## Explicit Non-Duplication

`DUPLICATED_ENGINES_CREATED: NO`

`PARALLEL_AUTHORITY_CREATED: NO`

`VOICE_CHANGED: NO`

`TRADING_MIGRATED: NO`

## Review Gate

B2 is ready for review only after protected regressions pass and the worktree
is reconciled against pre-existing changes. B3 is not started by this batch.
