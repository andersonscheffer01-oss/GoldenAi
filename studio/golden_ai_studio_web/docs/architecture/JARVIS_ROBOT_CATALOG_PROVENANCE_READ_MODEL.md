# Jarvis Robot Catalog and Provenance Read Model

**Gate:** `ROBOT_CATALOG_AND_PROVENANCE_READ_MODEL`
**Baseline:** `4362c53`
**Status:** `PASS_WITH_RESTRICTIONS`

## Ownership and boundary

The canonical owner is `jarvis_core.robot_catalog.RobotCatalogReadModel`,
exposed by the existing `JarvisService`. Discovery is explicit and bounded to
the approved Golden roots:

- `C:\GoldenAI\projetos`
- `C:\GoldenAI\studio\golden_ai_studio_web`
- `C:\GoldenAI\config\backtest_results`

The module performs filesystem reads and hashes only. It does not import MT5,
open a terminal, run Strategy Tester, start an EA, place orders, invoke legacy
order surfaces, call the network, or write robot files.

The first gate uses an in-process read model. No new database was created and
no SQLite schema was migrated. Durable catalog persistence is intentionally
deferred until an authorized canonical schema decision exists. User status
overrides are preserved across rescans within the read-model lifetime and are
never interpreted as trade authority.

## Read model contract

`RobotRecord` supports identity, version, source/compiled/preset/documentation
artifacts, backtest and optimization evidence, strategy family, symbols,
timeframes, declared safeguards, limitations, lifecycle, and claim-level
provenance. The detail view separates:

- what is known;
- why Jarvis thinks it;
- what remains unknown;
- conflicting claims;
- explicit user overrides.

Stable identity is content-based for source and compiled artifacts. Source,
compiled, preset, and documentation association uses exact stems first, then a
single unambiguous approved directory owner. Ambiguous or weak matches remain
unassociated.

Evidence distinguishes source, documentation, configuration, observed
artifacts, backtests, optimization, user-defined values, Jarvis inference,
test results, and unknowns. Conflicting claims are retained instead of being
silently resolved. `ACTIVE` means active in the user's repertoire only; it
never means authorized to trade.

## Controlled tools

The existing registry exposes three read-only, non-LLM tools:

- `robot_catalog_discover`
- `robot_catalog_list`
- `robot_catalog_detail`

`JarvisService.status()` includes the non-scanning catalog snapshot for future
Control Center integration. No major UI change is part of this gate.

## Real project validation

The approved-root scan inspected 198 relevant artifacts and found:

- 9 logical source-backed identities;
- 4 parameter presets associated by unambiguous directory ownership;
- 176 parseable backtest artifacts;
- 0 confidently associated backtests;
- 176 unassociated backtests retained as evidence with unknown robot mapping;
- 0 conflicts in the current approved roots;
- 0 optimization artifacts;
- 0 compiled-only identities in the current roots.

No performance ranking or winner selection is performed.

## Tests

`tests/test_robot_catalog.py` covers stable identity, source/compiled/preset
association, compiled-only and source-only records, unknown handling,
idempotent rescans, user override preservation, conflict visibility, service
registration, bounded roots, and absence of MT5/order execution surfaces.

The focused catalog suite and the existing market-intelligence, capability,
governance, hardening, and startup suites must remain green before a later
gate extends this read model.
