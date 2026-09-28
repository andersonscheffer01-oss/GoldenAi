# Jarvis Robot Catalog and Provenance Read Model

**Gate:** `ROBOT_CATALOG_AND_PROVENANCE_READ_MODEL`
**Baseline:** `778d6d5`
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

The catalog uses `NEW_SUBORDINATE_OPERATIONAL_STORE_JUSTIFIED`: the canonical
owner is still `jarvis_core.robot_catalog`, with a separate SQLite file at
`studio/golden_ai_studio_web/jarvis/robot_catalog.db`. This is not a second
Jarvis Core, memory database, task database, or audit database. Memory V2 owns
semantic knowledge, TaskDatabase owns missions and scheduler state, and
AuditLog owns execution audit; none owns catalog lifecycle, overrides, or
artifact identity. The catalog store has schema version 1, fails closed on an
unknown version, and is append-preserving for artifact history. It stores
operational records, explicit `USER_OVERRIDE` state, evidence payloads,
association status, and scan runs. Derived list/count views remain rebuildable.

User status overrides survive process restart and rescan. Discovery updates
observed facts but never overwrites an override. Catalog persistence has no
trade authority and does not write to memory automatically.

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

Artifact identity is `sha256(kind + content_sha256)`, so path movement keeps the
same artifact ID while content mutation creates a new artifact ID and retains
the previous row in history. Logical robot identity is normalized stem +
version + artifact role, keeping versioned executable identities distinct
without tying identity to an absolute path. Source, compiled, preset, and
documentation association uses exact stems first, then a single unambiguous
approved directory owner. Ambiguous or weak matches remain unassociated.

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

## Backtest association policy

The parser was adapted only to the observed local formats: UTF-8 JSON with a
top-level `stats` object, `trades`, `equity_curve`, and `timestamp`, plus the
observed `stats` metrics and optional `parameters`. Presets are observed UTF-8
`.set` key/value files; their normalized parameter maps produce deterministic
fingerprints. Raw reports are never modified.

Association statuses are `VERIFIED`, `HIGH_CONFIDENCE`, `AMBIGUOUS`,
`UNRESOLVED`, and `CONFLICTING`. Exact EA/robot identifiers and exact source
identities are verified. Documented aliases are accepted as evidence-backed
identity. A preset fingerprint can reach high confidence only with independent
source compatibility such as symbol or timeframe. Filename similarity, shared
directory, symbol alone, or generic strategy-family names never promote an
association. Competing strong evidence is preserved as ambiguous or
conflicting, never resolved by arbitrary percentages.

The zero-association root cause is evidenced by the real artifacts: all 177
current JSONs expose generic strategy labels and symbol/timeframe/metrics, but
none exposes an EA identifier, preset reference, parameter block, tester
metadata, or executable version. The four observed presets are separate `.set`
files and cannot be linked to those reports without additional evidence.

## Real project validation

The current approved-root scan inspected 199 relevant artifacts and found:

- 9 logical source-backed identities;
- 4 parameter presets associated by unambiguous directory ownership;
- 177 parseable backtest artifacts;
- 0 verified or high-confidence backtest associations;
- 177 unresolved backtests retained as evidence with unknown robot mapping;
- 0 conflicts in the current approved roots;
- 0 optimization artifacts;
- 0 compiled-only identities in the current roots.

No performance ranking or winner selection is performed.

## Tests

`tests/test_robot_catalog.py` covers stable identity, source/compiled/preset
association, compiled-only and source-only records, unknown handling,
idempotent rescans, SQLite restart/override persistence, path movement,
mutation history, aliases, parameter fingerprints, all association statuses,
conflict visibility, service registration, bounded roots, and absence of
MT5/order execution surfaces.

The focused catalog suite and the existing market-intelligence, capability,
governance, hardening, and startup suites must remain green before a later
gate extends this read model.
