# Jarvis / Golden B4.12 Deterministic Tester Materialization

**Status:** `PASS_WITH_RESTRICTIONS`
**Contract:** `jarvis-b4.12-deterministic-materialization-v1`
**Parent:** B4.10 `campaign_bf3389bc66f0ac7777a3a06719ac5851`, manifest `0df8521de44446de48141eb59b8ca884baca7fe483407239c4a952c2a25d7f0f`
**Authority:** read-only plan under the existing Robot Intelligence projection; no execution authority.

## Deterministic Materialization

The B4.10 campaign manifest and all B4.11 fingerprints remain immutable. B4.12 derives a subordinate plan and renders 16 expected INI payloads in memory. It creates no files and does not inspect or launch MT5. Each run contains three separate identities:

- B4.10 scientific fingerprint: robot, source/compiled identity, parameter identity, symbol, timeframe, window, split, model and safety semantics.
- INI scientific fingerprint: semantic fields actually represented in the `[Tester]` bytes, excluding report routing.
- Materialized fingerprint: SHA-256 of the exact expected UTF-8 bytes, UTF-8 without BOM, LF line endings and one final newline.
- Output-routing fingerprint: report/result destination plus campaign, run, robot, compiled/parameter identity and technical-window identity. This is distinct from the INI-only `Report`/`ReplaceReport` fingerprint.

The existing `jarvis-tester-config-materialization-v1` operation is retained unchanged. Canonical rendering preserves `[Experts]` then `[Tester]` order and a stable key order. No deposit, currency or leverage is invented because the scientific plan does not declare them. Canal refers to the already verified `Setup_8_Robusto_Base.set` name and B4.9 SHA-256 `87868b176181d827272d442044a532ce8dde51d856fbb43db4c9cbc3c202562c`. Tendencia uses its frozen compile-time-default parameter fingerprint; no `.set` is generated. For both robots, installed parameter bytes/default semantics and exact association with the target `.ex5` must be revalidated before launch. This is an execution-time restriction, not a fabricated serialization proof.

Expected deployment-relative expert paths are planning identifiers, not a claim that the current terminal contains those exact compiled bytes. The B4.10 compiled SHA-256 remains authoritative. The terminal executable and data-root target are bound to the B4.5 R23 execution evidence (`C:\Program Files\MetaTrader 5\terminal64.exe`, profile `D0E8209F77C8CF37AD8BF550E51FF075`) and must be revalidated at execution time; this gate did not inspect the active process or terminal filesystem.

## Output Ownership and Freshness

Each run has a unique logical MT5 report `Tester\Jarvis\<run>.htm` and managed evidence location `tester_runs\<campaign>\<run>\native_result.json`. Both are normalized with Windows case-insensitive collision semantics and reject traversal, absolute paths, reserved device names and unsafe characters. Pairwise collision count is zero. These routes are descriptions only; no path is created. If either expected destination exists at execution preflight, the run blocks as stale. Historical evidence is never overwritten or accepted as newly produced.

Native Tester evidence remains owned by the existing result-provider/adapter architecture. A native log does not prove fields it does not expose; process/run interval, exact config, robot/artifact and parameters must be joined only where the provider evidence supports them. The existing untracked adapter/runtime artifacts were not modified.

## Preflight and Authorization

The pure execution receipt binds the frozen campaign plan and checks observed artifact hash, parameter fingerprint, scientific identity, exact materialized bytes, route, window, frozen context, stale-output absence, process state, terminal/data-root observations and fresh SecurityManager approval. Unknown values fail closed. The receipt is immutable and `authorizes_execution=false`, even when all checks pass. This batch creates no SecurityManager confirmation or approval.

The later approval scope is one-use and bounded to all eligible DEVELOPMENT runs for one completed calendar window (the two robot runs). It binds manifest, run/robot identities, compiled and parameter hashes, all fingerprints, market-window IDs, model, terminal target and expiry. The canonical SecurityManager TTL is read at execution time (`confirmation_ttl`, default 60 seconds); this contract does not mint a token. Validation/holdout are not included; no automatic retry is allowed. A security/scientific invariant failure stops the batch.

Execution state order: `WINDOW_COMPLETE` -> frozen pre-window context -> independent post-window technical and descriptive macro context -> config/artifact/process preflight -> fresh human approval -> execution. Window completion alone is insufficient. B4.11's aware UTC clock remains authoritative: before 2026-11-02 is future, during 2026-11-02..06 is in progress, and completion begins 2026-11-07 UTC. No context is fabricated.

## Reuse Decisions

| Component | Decision | Boundary |
|---|---|---|
| B4.5 config reconciliation/materializer v1 | `KEEP` | Reused unchanged; exact byte hash added as a distinct plan identity. |
| B4.10 scientific identity | `KEEP` | Remains immutable and separate from INI-only semantics. |
| B4.11 shared temporal plan | `KEEP` | 16 technical windows, 8 macro identities, original fingerprints retained. |
| Fixture productization renderer | `REFERENCE_ONLY` | UTF-8/LF ordering pattern only; its fixture-only guard is not weakened or reused for production EAs. |
| StrategyTesterAdapter | `KEEP` | Sole future process boundary; never invoked here. |
| Native result providers | `KEEP` | No new provider architecture; field limits remain explicit. |
| B4.12 preflight composition | `ADAPT` | Pure subordinate read model delegates to frozen plans/materializer; no second executor/config authority. |
| Direct MT5/process discovery, file creation, retries | `REJECT` | Outside this no-runtime gate. |

## Verification and Current Readiness

Focused tests cover all 16 plans twice, deterministic bytes/encoding, robot/timeframe and parameter isolation, Windows path safety and collisions, stale output, routing changes, future-window behavior, non-authorizing receipts and one-window DEVELOPMENT-only approval scope. Provider counters in this pure materialization path remain zero for tester, market, model and MT5 launch.

The Control Center's existing Robot Intelligence view now displays scientific, materialized and routing fingerprints, run window/context state, authorization and blocked execution. It adds no execution controls. Visual runtime validation is not performed by this batch.

Current campaign state remains `PROPOSED_NOT_AUTHORIZED`. All windows are future at the B4.12 report clock; pre-window and post-window contexts are pending; execution-time terminal/data-root/process state, installed preset/default bytes and compiled deployment hashes are unverified; no human authorization exists. `campaign_executable_now=false`.

No MT5, MetaEditor, Strategy Tester, MQL5 compiler, trading, order/position, broker, database, device registry, Voice, market/model provider, or external provider was used. The broad-suite B4.11 baseline (2177 passed, 23 skipped, 45 failed, 4 errors) remains a comparison baseline; unrelated prior failures are not repaired here.
