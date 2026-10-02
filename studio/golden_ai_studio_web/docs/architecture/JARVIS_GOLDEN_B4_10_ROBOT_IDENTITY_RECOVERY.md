# JARVIS / GOLDEN B4.10 - Robot Identity Recovery

Date: 2026-10-02  
Mode: bounded, read-only forensic recovery and proposed campaign design  
Result: `PASS_WITH_RESTRICTIONS`

## Baseline and Safety

- Branch: `main`
- HEAD before B4.10: `b91fa33f8e6a56615ff353312efae6109166574d`
- B4.9 campaign: `campaign_b49_xauusd_m1_temporal_01`
- B4.9 manifest SHA-256: `0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4`
- B4.9 manifest, windows, robot list and parameters: unchanged.
- Audited roots were limited to `C:\GoldenAI\projetos`, the Golden Studio project/evidence tree, `C:\GoldenAI\config\backtest_results`, and exact known candidate artifact paths under MT5 data root `D0E8209F77C8CF37AD8BF550E51FF075`.
- Legacy results: 179 JSON files, zero candidate identity matches and zero complete scientific identities. Outcomes were not used to determine identity.
- Catalog was queried using SQLite read-only/query-only mode. Existing records observed: Canal and the tester fixture. No candidate rows or associations were found.
- No MT5, MetaEditor, Strategy Tester, MQL5 compiler, provider, voice, trading, broker, or external service was started. No database, registry, historical result, or production EA was modified.
- Pre-existing worktree changes remain unstaged and outside this checkpoint.

## Candidate 1: EA_Rompimento_Range_MTF_MT5

- `LOGICAL_ID`: `EA_Rompimento_Range_MTF_MT5`; candidate not cataloged, no execution identity.
- `SOURCE_PATHS`: `C:\GoldenAI\projetos\EA_Rompimento_Range_MTF_MT5\EA_Rompimento_Range_MTF_MT5.mq5`
- `SOURCE_HASHES`: `3d7b5d1fc890d83fd684e5f3202effaed011dff91289f0690e0639baee38468e`
- `SOURCE_STATUS`: `ONE_UNAMBIGUOUS_SOURCE`; exact listed bytes rehashed successfully.
- `COMPILED_PATHS`: project copy `C:\GoldenAI\projetos\EA_Rompimento_Range_MTF_MT5\EA_Rompimento_Range_MTF_MT5.ex5`; known D0 copy `C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\EA_Rompimento_Range_MTF_MT5\EA_Rompimento_Range_MTF_MT5.ex5`.
- `COMPILED_HASHES`: project `2af3dbe3e80ce4e9f589f729cfbf4aabdf9cc5aab07e36fbdaae8964dc2592c9`; D0 `31c0055174c4d6959793621cf7812b0f6b84ad3c441c42f846309e995c3a1fc7`.
- `COMPILED_STATUS`: `MULTIPLE_COMPILED_VERSIONS`; no choice made.
- `SOURCE_COMPILED_RELATIONSHIP`: `PARTIAL`; compile log path and project artifact timestamp correlate, but neither compiled hash is recorded and the two compiled hashes differ.
- `PARAMETER_STATUS`: `PARAMETERS_FROZEN_VERIFIED`; preset `Range_M15_Entrada_M1.set`, SHA-256 `2b59c8ea95a901175e2a89110f4b2eb71fb789705f6d99cfd7485da572cf12c7`, fingerprint `55b4ef689456d9f5e10ae1b4`, 61/61 inputs. Enum normalization shows semantic equality to source defaults.
- `SYMBOL_SCOPE`: XAUUSD from the existing preset; source allows configured symbol.
- `TIMEFRAME_SCOPE`: reference M15 plus entry M1 from preset; configurable inputs.
- `DEPENDENCIES`: known standard MT5 `Trade/Trade.mqh`, chart/time-series and CTrade APIs; no custom indicators, external files, DLL, or network calls.
- `ONTESTER_SEMANTICS`: not defined.
- Compile evidence: `compilacao.log`, SHA-256 `9dda9bfe0ba726b7634a0a92c9aa3d61a6ea75b02c3fd4f2e360d1627414535c`; recorded 0 errors/0 warnings, MetaEditor version absent, compiled hash absent.
- Existing candidate test evidence: none.
- `FINAL_READINESS`: `IDENTITY_AMBIGUOUS`.
- `BLOCKERS`: two distinct compiled artifacts prevent a unique compiled identity.

## Candidate 2: Robo_Tendencia_MA9_21_50_Volume

- `LOGICAL_ID`: `Robo_Tendencia_MA9_21_50_Volume`; candidate not cataloged, no execution identity.
- `SOURCE_PATHS`: `C:\GoldenAI\projetos\Robo_Tendencia_MA9_21_50_Volume.mq5`
- `SOURCE_HASHES`: `e7bcba2bb39dc6ab7a7389e32fa50f665e2caf62b1f2ecec6c4d6d5362d1130f`
- `SOURCE_STATUS`: `ONE_UNAMBIGUOUS_SOURCE`; exact listed bytes rehashed successfully.
- `COMPILED_PATHS`: `C:\GoldenAI\projetos\Robo_Tendencia_MA9_21_50_Volume.ex5`
- `COMPILED_HASHES`: `22f243a500aaf567f291cbaecf11ca87db89986e1be28c1e405009e9034629f4`
- `COMPILED_STATUS`: `ONE_UNAMBIGUOUS_COMPILED_ARTIFACT`; exact bytes rehashed successfully; exact known D0 candidate path contained no copy.
- `SOURCE_COMPILED_RELATIONSHIP`: `PARTIAL`; existing compile log names this source and its timestamp correlates with the unique project artifact. The log does not record output hash or compiler version, so there is no cryptographic source-to-binary link.
- `PARAMETER_STATUS`: `DEFAULT_PARAMETERS_VERIFIED`; 31 source input defaults, fingerprint `9da7c5af45bacfb4f62de780`; no `.set` or competing parameter evidence found.
- `SYMBOL_SCOPE`: chart symbol (`_Symbol`), no source allowlist; XAUUSD is an explicit proposed campaign selection, not a recovered hard-coded restriction.
- `TIMEFRAME_SCOPE`: M15 default via configurable `PeriodoGrafico` input.
- `DEPENDENCIES`: known standard MT5 Trade API and built-in iMA/iATR/iVolumes; no custom indicators, external files, DLL, or network calls.
- `ONTESTER_SEMANTICS`: not defined.
- Compile evidence: `Robo_Tendencia_MA9_21_50_Volume_compile.log`, SHA-256 `ba9007541c2000c4bd395ac4001d12cc1da7b55e9d7efb9767f62c95dba6145c`; recorded compile success, 0 errors/0 warnings, MetaEditor version and output hash absent.
- Existing candidate test evidence: none.
- `FINAL_READINESS`: `READY_WITH_RESTRICTIONS`.
- Restrictions: rehash exact source/binary before any future use; source-to-binary correlation is path/timestamp based, not hash-bound; compiler version is unavailable. No identity was inferred from performance.

## Candidate 3: Robo_XAUUSD_EMA_ATR_VWAP_TESTE

- `LOGICAL_ID`: `Robo_XAUUSD_EMA_ATR_VWAP_TESTE`; candidate not cataloged, no execution identity.
- `SOURCE_PATHS`: `C:\GoldenAI\projetos\Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5`
- `SOURCE_HASHES`: `9216c5053f9d19f4c99d28c73ec91e4d722c5b86e4e637a23c3d5c33786d06b7`
- `SOURCE_STATUS`: `ONE_UNAMBIGUOUS_SOURCE`; exact listed bytes rehashed successfully.
- `COMPILED_PATHS`: `C:\GoldenAI\projetos\Robo_XAUUSD_EMA_ATR_VWAP_TESTE.ex5`
- `COMPILED_HASHES`: `6140f67c06a4ecf0b9c2b71c69b685313e60410faceae7f6f4ec59139cf528fa`
- `COMPILED_STATUS`: `ONE_UNAMBIGUOUS_COMPILED_ARTIFACT`; exact bytes rehashed successfully.
- `SOURCE_COMPILED_RELATIONSHIP`: `UNKNOWN`; no compile log/linkage evidence found. No compile was performed.
- `PARAMETER_STATUS`: `DEFAULT_PARAMETERS_VERIFIED`; 52 source defaults, fingerprint `523b72353293cd9daaceaac1`.
- `SYMBOL_SCOPE`: chart symbol (`_Symbol`); filename suggests XAUUSD but source has no symbol allowlist, so filename was not accepted as proof.
- `TIMEFRAME_SCOPE`: chart timeframe (`_Period`), no source restriction.
- `DEPENDENCIES`: known standard MT5 Trade API and built-in iMA/iATR/time-series APIs; no custom indicators, external files, DLL, or network calls.
- `ONTESTER_SEMANTICS`: not defined.
- Existing candidate test evidence: none.
- `FINAL_READINESS`: `NOT_READY`.
- `BLOCKERS`: source-to-compiled relationship unknown and compile-success evidence absent.

## Recovery and Campaign Impact

- Candidates at start: 3 ambiguous; after forensic review: 1 remains identity-ambiguous, 1 is ready with restrictions, 1 remains not ready.
- Newly resolved for controlled evidence: 1 (`Robo_Tendencia_MA9_21_50_Volume`, restricted).
- Ready without restrictions: 0. Ready with restrictions: 1. Still excluded: 2.
- `OUTCOME_USED_FOR_IDENTITY_RECOVERY`: `NO`.
- Dry-run catalog association: one proposed `DISCOVERED` record for Tendencia only; not persisted. Persisted associations: 0. Schema/DB migration: none. Repertoire and trading authorization: unchanged / not granted.
- B4.9 remains the immutable single-robot registration. A distinct proposed campaign is possible and is not a mutation of B4.9.
- New campaign ID: `campaign_bf3389bc66f0ac7777a3a06719ac5851`.
- New manifest SHA-256: `0df8521de44446de48141eb59b8ca884baca7fe483407239c4a952c2a25d7f0f` (fingerprint of nested manifest).
- Campaign state: `PROPOSED_NOT_AUTHORIZED`; 2 robots (Canal M1 and Tendencia M15), XAUUSD, same 8 calendar windows, 16 planned runs; splits: 8 development, 4 validation, 4 holdout.
- The robots preserve their own timeframe and parameter semantics. Shared windows support calendar alignment, not direct like-for-like performance comparison: M1 vs M15 contexts are timeframe-specific.
- B4.9 retains 8 future planned single-robot runs. B4.10 proposes 16 multi-robot runs. Planned runs are not samples.
- Existing canonical production samples: 3 B4.5 Canal runs. Current eligible B4.9 samples: 0. Legacy unresolved artifacts remain excluded. Empirical matcher: `NOT_READY` / `NOT_IMPLEMENTED`.

## Configuration, Context, Memory, and Preflight

- Scientific config fingerprints are deterministic, include campaign identity and frozen robot/source/binary/parameter/market/window/split/tester safety semantics, and are revalidated on load.
- The existing B4.5 `materialize_config` helper is reused in an in-memory preview. Materialized and output-routing fingerprints are **not** created for planned runs; they remain `NOT_MATERIALIZED` until a future execution gate. No runtime paths or files are fabricated.
- Preflight contract: rehash source, compiled bytes, preset and campaign; validate scientific config; materialize and rehash config/routing; verify terminal/data root without fallback and no conflicting MT5 process; obtain fresh SecurityManager approval bound to campaign/run/artifact/config/window and TTL; execute one bounded run; verify ownership and reconcile; stop on any invariant failure. `AUTO_RETRY=0`.
- Future windows: 2026-11-02..06, 2026-11-09..13, 2026-11-16..20, 2026-11-30..2026-12-04, 2026-12-07..11, 2026-12-14..18, 2027-01-04..08, 2027-01-11..15. First begins 2026-11-02; earliest post-window execution consideration is 2026-11-07, only after context/config reconciliation and new human authorization.
- Current technical and future macro context is not frozen. Policy: pre-window context may be collected only from evidence available by its cutoff; after each window, freeze technical and macro description with provenance/version before joining tester outcome. Future event schedules are versioned when observed; none were fabricated now.
- Future-time guard states: `WINDOW_PRE_REGISTERED`, `WINDOW_IN_PROGRESS`, then `WINDOW_COMPLETE_CONTEXT_PENDING`; it never marks execution-ready and rejects a naive (timezone-free) injected clock.
- Canonical Scientific Memory V2 can represent typed robot/experiment evidence and graph relations without another memory engine or schema migration. Temporal snapshots are content-fingerprinted by symbol/timeframe/cutoff. A canonical shared macro-context link across separate robot runs is not implemented/validated; the proposed campaign records this as a blocker and does not claim context reuse. No memory writes were made.
- Holdout remains inaccessible to development/outcome analysis and marked uninspected.

## UI and Tests

- Existing B4.3 Robot Intelligence surface now includes the read-only candidate readiness matrix, B4.9 pre-registered/not-executable state and B4.10 proposed/not-authorized campaign. No run controls were added.
- B4.10 test file covers identical/different source copies, multiple/missing compiled artifacts, ambiguous/resolved parameters, dependency ambiguity, OnTester isolation, performance independence, versioning/B4.9 immutability, scientific/materialized/routing fingerprints, frozen-clock future guard, holdout, and UI state.
- Focused regression across B4.10, B4.9, B4.8, B4.7D/C/7, B4.6, B4.3/B4.2, B3, B4.1, Robot Catalog, MQL5/Tester evidence, Scientific Memory, Security and Audit: **302 passed, 5 existing pytest collection warnings**.
- Warnings are pytest collection notices for dataclasses `TestRunIdentity` and `TesterConfiguration` in existing evidence tests; no test failure.
- Static checks: Python `py_compile` passed; frontend `node --check` passed; `git diff --check` passed; secret scan over B4.10 content found no matches. Cached diff check is performed after exact staging.

## B4.10 Required Report

```text
JARVIS_B4_10_ROBOT_IDENTITY_RECOVERY
HEAD_START: b91fa33f8e6a56615ff353312efae6109166574d
HEAD_END: see checkpoint commit
RESULT: PASS_WITH_RESTRICTIONS

B4_9_CAMPAIGN_ID: campaign_b49_xauusd_m1_temporal_01
B4_9_MANIFEST_HASH: 0f09221134098dc0979867ec1fe1ab4429f864c9f870d2e195b6cd848b61aab4
MANIFEST_CHANGED: NO
WINDOWS_CHANGED: NO
ROBOT_LIST_CHANGED: NO
PARAMETERS_CHANGED: NO
B4_9_EXECUTABLE_NOW: NO
WHY_NOT: FUTURE WINDOWS + POINT-IN-TIME CONTEXT + MATERIALIZED CONFIG/ROUTING + FRESH HUMAN AUTHORIZATION PENDING

TOTAL_CANDIDATES: 4 (1 existing resolved + 3 audited ambiguous)
ALREADY_RESOLVED: EA_Canal_Pullback_MT5
AMBIGUOUS_AT_START: 3
AMBIGUOUS_AFTER: 1
NEWLY_RESOLVED: Robo_Tendencia_MA9_21_50_Volume (with restrictions)
READY_FOR_CONTROLLED_EVIDENCE: 0 without restrictions
READY_WITH_RESTRICTIONS: 1
STILL_EXCLUDED: 2
OUTCOME_USED_FOR_IDENTITY_RECOVERY: NO

NEW_DISCOVERED_RECORDS: 1 proposed DISCOVERED dry-run only
DRY_RUN_ASSOCIATIONS: 1
PERSISTED_ASSOCIATIONS: 0
SCHEMA_CHANGED: NO
DB_MIGRATION: NO
REPERTOIRE_CHANGED: NO
TRADING_AUTHORIZATION_CHANGED: NO

SINGLE_ROBOT_DESIGN_STILL_CORRECT: YES for immutable B4.9
MULTI_ROBOT_CAMPAIGN_POSSIBLE: YES as a separate proposal
NEW_CAMPAIGN_PROPOSED: YES, PROPOSED_NOT_AUTHORIZED
NEW_CAMPAIGN_ID: campaign_bf3389bc66f0ac7777a3a06719ac5851
NEW_MANIFEST_HASH: 0df8521de44446de48141eb9b8ca884baca7fe483407239c4a952c2a25d7f0f
ROBOTS_INCLUDED: EA_Canal_Pullback_MT5; Robo_Tendencia_MA9_21_50_Volume
ROBOT_COUNT: 2
WINDOW_COUNT: 8
PLANNED_RUN_COUNT: 16
SYMBOLS: XAUUSD
TIMEFRAMES: M1; M15
DEVELOPMENT: 8
VALIDATION: 4
HOLDOUT: 4

SCIENTIFIC_CONFIG_READY: YES
MATERIALIZATION_LOGIC_READY: YES, existing deterministic B4.5 helper
OUTPUT_ROUTING_READY: YES, existing bounded helper
MATERIALIZED_FINGERPRINTS_CREATED_NOW: NO
WHY_OR_WHY_NOT: Actual routing is execution-time state; fabricated runtime paths are forbidden.

FUTURE_WINDOWS: B4.9 eight registered windows, reused without mutation
FIRST_WINDOW_START: 2026-11-02
TECHNICAL_CONTEXT_AVAILABLE_NOW: NO, future windows
MACRO_CONTEXT_AVAILABLE_NOW: NO, future schedules/context are not frozen
PRE_WINDOW_CONTEXT_POLICY: only point-in-time evidence available by cutoff
POST_WINDOW_CONTEXT_POLICY: freeze versioned technical/macro context before outcome join
FUTURE_TIME_GUARD: PASS; injected UTC lifecycle, never executable-ready

CURRENT_CANONICAL_PRODUCTION_SAMPLES: 3 B4.5 Canal runs
CURRENT_ELIGIBLE_SAMPLES: 0 B4.9 completed/reconciled runs
PLANNED_SINGLE_ROBOT_SAMPLES: 8 (not evidence)
PLANNED_MULTI_ROBOT_SAMPLES: 16 (not evidence)
LEGACY_UNRESOLVED_EXCLUDED: 179
EMPIRICAL_MATCHER_READY: NO
WHY_NOT: no new run evidence; planned runs do not count as samples

ROBOT_READINESS_MATRIX: visible in existing B4.3 read surface
B4_9_PRE_REGISTERED_VISIBLE: YES
B4_9_NOT_EXECUTABLE_YET_VISIBLE: YES
NEW_CAMPAIGN_PROPOSED_VISIBLE: YES
NOT_AUTHORIZED_VISIBLE: YES

MT5_STARTED: NO
METAEDITOR_STARTED: NO
STRATEGY_TESTER_RUNS: 0
EA_EXECUTIONS: 0
MQL5_COMPILES: 0
LIVE_TRADING: NO
ORDER_SEND: NO
POSITION_MUTATION: NO
BROKER_MUTATION: NO
DEVICE_REGISTRY_CHANGED: NO
DATABASE_SCHEMA_CHANGED: NO
VOICE_INITIALIZED: NO
PERSONAL_FINANCE_TOUCHED: NO

B4_10_TESTS: 15 passed
FORENSIC_TESTS: passed
LEAKAGE_TESTS: passed
CAMPAIGN_VERSION_TESTS: passed
CONFIG_TESTS: passed
FUTURE_TIME_TESTS: passed
HOLDOUT_TESTS: passed
B4_9_REGRESSION: passed
B4_8_REGRESSION: passed
B4_7D_REGRESSION: passed
B4_7_REGRESSION: passed
B4_6_REGRESSION: passed
B4_5_REGRESSION: passed via tester evidence/productization/config/result suites
CATALOG_REGRESSION: passed
ROBOT_INTELLIGENCE_REGRESSION: passed
TESTER_EVIDENCE_REGRESSION: passed
MEMORY_REGRESSION: passed
SECURITY_REGRESSION: passed
AUDIT_REGRESSION: passed
BROAD_REGRESSION: 302 passed, 5 collection warnings
NEW_REGRESSIONS: none
PY_COMPILE: PASS
NODE_CHECK: PASS
GIT_DIFF_CHECK: PASS
SECRET_SCAN: PASS, no matches

FILES_CHANGED: exact B4.10 source/read-model/UI/data/test/report files only in checkpoint
COMMIT_CREATED: see isolated B4.10 checkpoint in Git history
COMMIT_HASH: recorded by final checkpoint response
STAGED_FILES_AFTER: expected empty after commit
PUSH: NO
PRE_EXISTING_WORK_PRESERVED: YES; unrelated work remains unstaged

CAN_WORK_CONTINUE_BEFORE_NOVEMBER: YES, context-policy and canonical shared-context-link design only
NEXT_NON_EXECUTION_GATE: resolve shared macro-context provenance/linking, then fresh artifact/context/config preflight
FIRST_POSSIBLE_EXECUTION_DATE: 2026-11-07 at earliest, conditional on completed window, all gates, and authorization
FRESH_HUMAN_AUTHORIZATION_REQUIRED_AT_EXECUTION: YES, exact campaign/run/manifest/artifact/parameter/config/window/TTL bound

B4_10_STATUS: PASS_WITH_RESTRICTIONS
ROBOT_DIVERSITY_IMPROVED: YES, one candidate recovered with restrictions
CAMPAIGN_READINESS_IMPROVED: YES, separate versioned proposal only
REMAINING_RESTRICTIONS: partial source-to-binary linkage for Tendencia; compiler version absent; distinct M1/M15 scientific contexts
REMAINING_BLOCKERS: future windows/context/config; shared macro-context link not validated; catalog association not persisted; fresh human authorization required
RECOMMENDED_NEXT_GATE: B4.10 shared-context provenance design and proposal review; no execution authorization
```

## Checkpoint

The isolated B4.10 source checkpoint is intended to contain only the changed read-model/design/UI code, forensic/campaign JSON, focused tests, and this report. All unrelated dirty work remains outside the commit. No push is permitted.
