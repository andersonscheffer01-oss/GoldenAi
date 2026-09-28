# Jarvis MQL5 and Strategy Tester Evidence Foundation

**Gate:** `JARVIS_MQL5_TESTER_EVIDENCE_FOUNDATION`
**Baseline:** `ac548b1`
**Status:** `PASS_WITH_RESTRICTIONS`

## Boundary

This gate makes future MQL5 compile/test runs provable. It does not modify the
9 cataloged robots, rewrite the 177 historical JSON reports, open MT5, start an
EA, connect a broker, place orders, or run Strategy Tester. Historical reports
remain `UNRESOLVED` unless new deterministic evidence is appended later.

The canonical owner remains `jarvis_core.robot_catalog` and its existing
`robot_catalog.db`. There is no `strategy_tester.db`, `mql5.db`, or
`backtests.db`. Contracts live in
`jarvis_core/mql5_evidence.py`; they are data/provenance contracts, not a second
orchestrator or execution subsystem.

## M1 Existing Audit

| Existing component | Classification | Evidence and decision |
|---|---|---|
| `jarvis_core.robot_catalog` and `robot_catalog.db` | KEEP / ADAPT | Canonical identity, artifact history, overrides, evidence owner. Extended with compile/test evidence rows. |
| `app/modules/mt5.py` | ADAPT | Existing bounded path and MetaEditor log conventions are useful reference. It does not provide canonical provenance or Jarvis ownership, so it is not called by this gate. |
| `app/golden_ai.py` MQL5 compile helpers | COMPAT | Existing preflight/log parsing patterns remain legacy compatibility input; no direct new authority is granted. |
| `studio/.../mt5_backtest.py` | LEGACY_FREEZE | Python simulator with MT5 historical-data access. Its observed JSON shape informed the parser; it is not the MQL5 Strategy Tester adapter. |
| `studio/.../mt5_real_backtest.py` | LEGACY_FREEZE | Creates EA files, launches MetaEditor/terminal, and reports a user workflow. It does not prove compile/test success and is not invoked. |
| `mt5_connector.py` / `mt5_trader.py` | LEGACY_FREEZE | Direct/legacy MT5 and order surfaces. They remain outside this foundation. |
| `agents/mql5` | COMPAT | Read-only analysis boundary exists; it does not write `.mq5` directly. |
| `agents/backtest` | UNKNOWN | Empty coordinator shell; no reuseable canonical runner or parser found. |
| `universal_backtest_ea.mq5` | COMPAT | Existing template is a future controlled fixture candidate only; not modified or executed. |

No existing canonical Strategy Tester runner, run manifest, compile evidence
contract, stale-run policy, or result reconciliation contract was found.

## M2 Canonical Skill

The single canonical skill is `.agents/skills/golden-mql5/SKILL.md`. It now
teaches source inspection, evidence separation, parameter origins, run
identity, manifest binding, compile proof, result reconciliation, historical
preservation, and the Jarvis security boundary. No external skill was
installed, and no duplicate authority was created.

## M3-M5 Contracts

`mql5_evidence.py` provides:

- `TestRunIdentity` with a unique `run_<uuid>` ID and robot/source/compiled/
  preset/hash/parameter/timestamp/status fields;
- `GoldenTestRunManifest` binding identity, tester configuration, exact
  effective parameters, expected result artifacts, provenance, and a manifest
  hash before execution;
- `Mql5ParameterDefinition` and `EffectiveParameterSet` with typed defaults,
  source references, normalized values, deterministic fingerprints, and
  origins `EA_DEFAULT`, `PRESET`, `USER_DEFINED`, `OPTIMIZER_GENERATED`, and
  `JARVIS_SUGGESTED`;
- `CompileEvidence` with compiler log hash, source/compiled hashes, errors,
  warnings, status, and provenance. `COMPILE_SUCCESS` requires a parsed
  compiler result line; missing proof is `COMPILE_UNKNOWN`.

## M6-M8 Tester and Result Design

`StrategyTesterAdapterDesign` is deliberately design-only. It plans one managed
run directory, bounded lifecycle states (`START`, `TIMEOUT`, `CANCEL`,
`CLEANUP`, `VERIFY`), stale-run handling, and single-run parallelism, while
returning `start: NOT_IMPLEMENTED` and `trade_authority: NONE`.

The observed Golden JSON shape is supported: UTF-8 object, optional `stats`,
metrics, symbol/timeframe, period fields, optional parameters, and optional
tester metadata. `parse_result_json` records artifact hash and parser version;
missing identity/parameters/tester metadata remains `NOT_PRESENT`. It never
modifies the input report. `reconcile_result` requires `test_run_id` and
checks robot, symbol, timeframe, parameter fingerprint, duplicate hashes, and
explicit stale runs.

No unsupported MT5 custom field is assumed to survive the tester. The future
binding mechanism is a Golden-owned managed run directory plus manifest and
sidecar/result evidence, with artifact hashes as the reconciliation anchor.

## Security and catalog integration

Compile/test evidence attaches through `RobotCatalogReadModel` to the existing
`robot_catalog.db` store. Catalog detail exposes compile evidence, test runs,
parameter sets, and latest test status without ranking robots. The contracts do
not import or call MT5, MetaEditor, terminal processes, order APIs, broker
connections, credentials, or legacy order adapters.

Any future execution capability must pass through:

`JarvisService.execute_tool -> ToolRegistry -> SecurityManager -> executor -> AuditLog`

Strategy Tester simulation is never live-trade authority.

## Full-suite investigation

Bounded raw collection completed in 33.75 seconds with 2,009 items, so the
previous no-output observation is classified `COLLECTION_SLOW`, not a hang or a
catalog regression. The isolated `live_smoke_test.py` collected 2 tests and
failed immediately at setup because `question` is not a fixture; its functions
are an intentional executable live-provider smoke script accidentally shaped
like pytest tests. No Ollama, TTS, or external action was executed during this
investigation. This remains a pre-existing test-harness restriction.

## Safety result

- 177 historical reports modified: `NO`.
- False historical associations created: `NO`.
- Live trade, broker mutation, orders, EA activation, credentials, and legacy
  order paths used: `NO`.
- Strategy Tester started: `NO`.
- Push: `NO`.
