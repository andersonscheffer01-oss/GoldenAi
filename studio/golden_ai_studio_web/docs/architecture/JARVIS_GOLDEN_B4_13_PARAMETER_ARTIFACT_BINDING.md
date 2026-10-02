# Jarvis / Golden B4.13 Parameter and Compiled Artifact Binding

Status: static filesystem/source reconciliation, read-only. No MT5, MetaEditor,
Strategy Tester, compilation, broker, provider, or database operation is part
of this contract.

## Authority and identities

The immutable B4.10 campaign remains the run authority. The existing
`robot_catalog.parameter_fingerprint` algorithm is reused without version or
semantic changes. Canal identity is its B4.9 verified preset map (151 explicit
values); Tendencia identity is the 31 defaults parsed from the exact frozen
source bytes. The B4.10 source, compiled, and parameter hashes are rechecked
before a materialization plan can be built.

Canal's project preset and D0 Tester-profile preset have distinct byte
identities (UTF-8-SIG and UTF-16 respectively), but parse to the same 151-value
map and reproduce the frozen fingerprint. Five source inputs absent from the
preset are made explicit as source-default-origin rows only in the derived
effective snapshot; the frozen 151-value campaign identity is not changed.
Unknown, duplicate, type-invalid, or unexpected missing input values block.
The B4.5 campaign manifest is rehashed and its robot/source/compiled
identities, project/runtime preset hashes, parameter fingerprint,
semantic-equivalence result, and COMPILE_SUCCESS status are checked before
Canal can be labeled historically bound. Its existing manifest SHA-256 is
`096e947e4ef3f86a2c7056197c57e19e63442836b2af43d62809feff11a3f668`.
Both frozen compile-log byte hashes are revalidated and parse as
`COMPILE_SUCCESS` (zero errors). Neither log records the compiled SHA itself;
Tendência therefore remains `PARTIAL_PATH_AND_TIMESTAMP_CORROBORATION`.

The canonical effective snapshot is sorted by case-folded source input name
and serialized as compact, sorted-key JSON, ASCII escapes, UTF-8, LF final
newline. JSON numeric formatting is locale independent; booleans are lowercase
JSON literals; enums are emitted as declared symbolic values after mapping
numeric `.set` enum ordinals; strings use JSON escaping. Its SHA-256 is a
separate provenance identity, not a replacement for either frozen campaign
fingerprint.

## Compiled artifact and runtime binding

Exact bytes are rehashed at plan construction. Canal selects the known D0 copy
with the campaign's historical hash and explicitly excludes the different
project `.ex5`. Its historical manifest/test association remains the strong
binding evidence. Tendencia's expected hash is present in the project root,
with B4.10's existing partial source/log path-and-timestamp relationship; the
matching file is absent at the known D0 Expert path. The plan reports this
installed-state restriction; any future execution preflight requires the exact
D0-installed hash and path and therefore fails closed until that state changes
and is freshly reconciled.

The INI remains `jarvis-tester-config-materialization-v1` (UTF-8, no BOM, LF,
final newline). B4.13 adds provenance identities to the read-only plan,
preflight receipt checks, and approval scope; it does not change the INI
materialization semantics or mint authorization. Receipt readiness is not
execution authorization. Parameter/source/binary drift, stale hashes, schema
mismatch, or cross-robot identity mismatch blocks.

The Control Center exposes read-only per-robot parameter authority/fingerprint,
parameter artifact hash, input-schema status, compiled status/hash, runtime
installation status, and drift status. No action controls are added.

## Current reconciliation

- Campaign: `campaign_bf3389bc66f0ac7777a3a06719ac5851`; immutable manifest hash
  `0df8521de44446de48141eb9b8ca884baca7fe483407239c4a952c2a25d7f0f`.
- Canal: parameter fingerprint reproduced; 156-input schema compatible with
  five explicit source defaults; D0 `.ex5` and D0 preset exact; project `.ex5`
  differs and is not selected.
- Tendencia: parameter fingerprint reproduced from all 31 source defaults;
  exact compiled bytes exist in project but are not installed in the known D0
  Expert path; source-to-compiled evidence remains explicitly partial.
- All 16 planned runs retain their original robot, compiled hash, parameter
  fingerprint, scientific config, windows, and tester semantics.
- Campaign remains non-executable: future windows/context, missing Tendencia
  installation, fresh preflight and separate future authorization remain.
