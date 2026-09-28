# Jarvis / Golden B2 Scientific Memory Contract

## Boundary

Canonical Memory V2 is the only memory authority. B2 adapts legacy Golden
scientific semantics into its existing records, versions, metadata, entities,
relations, and relation evidence. It does not import the legacy store.

## Contract Types

| Type | Meaning | Canonical representation |
| --- | --- | --- |
| `EVIDENCE` | observed or calculated support | record metadata and provenance |
| `HYPOTHESIS` | proposed explanation | record plus graph entity |
| `EXPERIMENT` | reproducible investigation | record metadata and links |
| `REVISION` | changed interpretation | version and `REVISES` relation |
| `CONFLICT` | incompatible claims retained together | `DISPUTED` status and `CONTRADICTS` |
| `SUPERSESSION` | newer record replaces an older one | version/status and `SUPERSEDES` |

## Required Preservation

Each adapted record retains source identity, source type, artifact identity,
created/observed timestamps when actually supplied, confidence, content
fingerprint, contract type, and provenance chain. Unknown confidence or
observation time remains unknown; it is never synthesized from bridge time.

Memory V2 has a required numeric storage column for historical compatibility.
The scientific adapter therefore stores missing confidence as explicit
`scientific_confidence: null` plus `confidence_state: UNKNOWN` metadata; the
numeric engine default is not treated as source confidence. Explicit `0.0`,
`0.5`, and `1.0` remain distinct values.

Conflicts and history are additive. An explicit conflict marks both canonical
records `DISPUTED` and creates `CONTRADICTS`. An explicit supersession keeps the
old record, marks it `SUPERSEDED`, and creates `SUPERSEDES`. A revision keeps
both records active and creates `REVISES`. No silent overwrite or destructive
supersession occurs in the adapter. Links use the existing graph relation
vocabulary: `SUPPORTS`, `CONTRADICTS`, `DERIVED_FROM`, `REVISES`, and
`SUPERSEDES`.

## Operational Rules

- `prepare` is deterministic and side-effect free.
- `remember` is explicit and delegates to Memory V2 only.
- `link` delegates to the existing graph boundary.
- `import_executed: false` is part of the B2 status contract.
- Existing schema version and migrations remain unchanged.

`PARALLEL_MEMORY_CREATED: NO`

`SCHEMA_CHANGE_REQUIRED: NO`

`DATABASE_MIGRATION: NO`
