# Jarvis / Golden B4.9 Scientific Campaign Design

Status: `PASS_WITH_RESTRICTIONS` (pre-registered design; no tester runs)

## Scope and authority

B4.9 adds a deterministic static campaign manifest and a read-only projection through the existing B4.3 Robot Intelligence endpoint and panel. It does not add a campaign runner, database, catalog writes, optimizer, matcher, ranking, execution authority, or parallel orchestrator. The design is analysis-only and uses the canonical Jarvis read model.

## Inventory and eligibility

The bounded Golden inventory identified multiple MQL5-looking source/binary pairs, but only `EA_Canal_Pullback_MT5` has reconciled production identity, a real `COMPILE_SUCCESS` evidence record, available historical tested compiled bytes, and a canonical parameter fingerprint suitable for a frozen design. It is the sole candidate. The current local compiled artifact `e6e35d84f26deb705b9ef90db3e3fa4d94c739e0d7109d8b45cb9831ecaa3a7e` is not substituted for the historical tested artifact `e239e0dfc1c6a10c4bd4f8758b1913946b2423cd0901b8f3486b910fe56267cc`.

Frozen identity:

- Robot: `EA_Canal_Pullback_MT5`, production logical identity.
- Source SHA-256: `0f1ba3526de5e7b679281e38136479beb99dd707fd1b02db1d960ffae103aff4`.
- Tested compiled SHA-256: `e239e0dfc1c6a10c4bd4f8758b1913946b2423cd0901b8f3486b910fe56267cc`.
- Compile evidence: `COMPILE_SUCCESS`; no new compile was run.
- Preset: `Setup_8_Robusto_Base.set`, SHA-256 `87868b176181d827272d442044a532ce8dde51d856fbb43db4c9cbc3c202562c`.
- Canonical parameter fingerprint: `7953a3fa4ca05b223411fca3`.

All other discovered EAs remain discovery-only because the full source/compile/test/parameter identity chain was not established. Fixtures, scripts, and indicators are excluded. No catalog record was changed.

## Dataset and time policy

Campaign `campaign_b49_xauusd_m1_temporal_01` pre-registers eight future XAUUSD M1, REAL_TICKS calendar windows, chronological and outcome-independent: four development, two validation, and two holdout. The Thanksgiving week is skipped. Holdout outcomes have not been accessed; no random shuffling, tuning, or performance-based window choice is used. B4.5 R1-R3 are prior evidence and are not re-counted as new samples.

Deterministic manifest SHA-256: `0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4`. Every run has a scientific configuration fingerprint over its frozen identity, parameters, symbol/timeframe/window, tester model, and safety flags. Materialized Tester and output-routing fingerprints remain `NOT_MATERIALIZED`. Planned run IDs are `run_b49_01_dev` through `run_b49_04_dev`, `run_b49_05_val`, `run_b49_06_val`, `run_b49_07_holdout`, and `run_b49_08_holdout`.

All 179 currently discovered legacy JSON backtests lack a complete robot/source/compiled/parameter/model identity contract. They are `DISCOVERY_REGRESSION_ONLY`, not campaign samples. Similar strategy-name text is not robot identity. Their ambiguous time coverage also prevents using them to claim an empirically clean holdout; the campaign therefore uses future calendar windows and remains gated until they elapse and context is frozen.

Regime diversity and macro coverage are `UNKNOWN` until point-in-time context evidence is acquired and frozen before execution. B4.8 archived macro context covers only its existing three windows; no extrapolation is made. Technical, macro, and any shared context must be frozen independent of robot outcomes. Outcome features are forbidden from context labels.

## Fingerprints and execution gate

The manifest hash is SHA-256 over canonical JSON via `content_fingerprint`. Scientific identity is frozen now. The materialized Tester config and output-routing fingerprints explicitly remain `NOT_MATERIALIZED`; they must be distinct and materialized in a later controlled gate. Context is `PENDING_PRE_EXECUTION_FREEZE`. These placeholders are not presented as computed fingerprints.

Every planned run has a unique stable ID, robot identity, source and tested compiled hashes, parameter fingerprint, market dimensions, date window, temporal split, tester model, and safety flags. Optimization, remote, cloud, and live trading are zero. Automatic retry is disabled. Failures must remain failed/unverified, never silently replaced. Result interpretation is restricted to native fields; the EA's `OnTester` value is a custom robustness score, not profit. No metric unsupported by native result evidence is invented.

Execution blockers: future windows have not elapsed; point-in-time technical/macro context is not frozen; materialized Tester config/output routing do not exist; a separate exact campaign-ID plus manifest-hash human authorization is required. No authorization is requested or implied by this design checkpoint.

Required future authorization envelope:

```text
HUMAN ACTION REQUIRED — AUTHORIZE CONTROLLED SCIENTIFIC TESTER CAMPAIGN
CAMPAIGN_ID: campaign_b49_xauusd_m1_temporal_01
MANIFEST_HASH: 0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4
ROBOTS: EA_Canal_Pullback_MT5
RUN_COUNT: 8
SYMBOLS: XAUUSD
TIMEFRAMES: M1
WINDOWS: 2026-11-02..06; 2026-11-09..13; 2026-11-16..20; 2026-11-30..2027-01-15 (individual windows in manifest)
TESTER_MODEL: REAL_TICKS
PARAMETERS_FROZEN: YES (7953a3fa4ca05b223411fca3)
OPTIMIZATION: 0
AUTO_RETRY: 0
LIVE_TRADING: 0
ORDER_SEND: 0
BROKER_MUTATION: 0
```

## Read-model UI

The existing Control Center B4.3 Robot Intelligence panel shows candidate identity, planned runs/splits/windows, manifest hash, evidence gaps, planning-only status, no backtest executed, and not-live-trading status. It has no run button or execution endpoint. If the manifest is unavailable or invalid, the read model fails closed and reports it unavailable.

## Matcher readiness

Empirical matcher: `NOT_READY`. Current eligible B4.9 samples: 0. Planned: 8, not outcomes. Robot diversity: 1. Regime diversity: unknown. Temporal diversity: planned only. Holdout: uninspected and future, but not yet available. These data do not support ranking, performance recommendation, suitability from empirical outcomes, or robot promotion.

## Safety and preservation

No MT5 or MetaEditor process was started; no Strategy Tester, EA, MQL5 compile, provider, order, trading, broker, personal-finance, Voice, database, catalog, or device-registry operation was performed. B4.5-B4.8 evidence and all pre-existing work remain untouched. This change is limited to the campaign loader, static manifest, B4.3 projection, existing B4.3 panel, focused tests, and this report.

Validation: 206 focused/regression tests passed (four existing pytest collection warnings); Python compile, Node syntax check, and `git diff --check` passed. MT5/Tester/EA/compiler were not invoked.
