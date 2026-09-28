# Jarvis / Golden B2 Data Recovery Manifest

## Purpose

The B2 manifest is a deterministic, read-only inventory for later human review.
It is not an import queue and does not authorize data mutation.

## Entry Contract

Every candidate entry may include:

- `source_store`
- `source_record_identity`
- `source_type`
- `target_domain`
- `proposed_target`
- content or artifact fingerprint
- provenance and classification
- `recovery_decision`
- `conflict_state`
- `validation_required`

The manifest itself has a stable hash. File content is hashed for identity but
is not copied into the manifest. Protected files such as credentials,
`api_keys.json`, `.env`, and `device_registry.json` are excluded.

## Classification and Decision

Classification describes evidence. Recovery decision is a separate, fail-closed
policy and never means that data was imported.

| Classification | Deterministic evidence | Default decision |
| --- | --- | --- |
| `UNIQUE` | known evidence domain, no duplicate/supersession evidence | `NEEDS_VALIDATION`; `RECOVER` only with explicit validation marker |
| `DUPLICATED` | identical content fingerprint appears more than once | `REFERENCE_ONLY` |
| `SUPERSEDED` | explicit status or supersession relation/version marker | `REFERENCE_ONLY` |
| `UNKNOWN` | insufficient evidence | `NEEDS_VALIDATION` |
| `FIXTURE` | fixture/test path evidence | `DO_NOT_IMPORT` |
| `RUNTIME` | runtime database/store artifact | `DO_NOT_IMPORT` |
| `BACKUP` | backup path evidence | `PRESERVE_IN_PLACE` |

The allowed decisions are `RECOVER`, `REFERENCE_ONLY`,
`PRESERVE_IN_PLACE`, `DO_NOT_IMPORT`, and `NEEDS_VALIDATION`. `RECOVER` is
only a future controlled-gate candidate; B2 never performs recovery.

## B2 Safety Boundary

No data is imported, migrated, deduplicated, archived, deleted, or rewritten
by B2. Legacy stores are read-only. A later recovery batch must separately
authorize target selection, conflict handling, validation, and any schema
change.

`DATA_IMPORTED: NO`

`LEGACY_DATA_MODIFIED: NO`

`SCHEMA_CHANGE_REQUIRED: NO`
