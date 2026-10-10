# Trend Scan v1 Contract Characterization

## Responsibilities

| Layer | Produces | Validates/owns |
|---|---|---|
| `trend-ranking-state.js` | Canonical client shape, ordered universe, pending/terminal transitions, `next_batch_index` | Client projection only |
| `desktop-shell.js` | Batch metadata, correlation, authenticated request | Does not own persistence |
| `JarvisService` / `APPLY_BATCH` | Authenticated boundary and actor injection | Request contract and security policy |
| `GoldenTrendScanRepository` | Normalized persisted state | Identity, universe hash, revision, atomicity, idempotency, immutability |

## Characterized fields

The shared payload is `contract_version`, `scan_id`, `created_at`, `universe_total`,
`asset_class_filter`, `universe_hash`, `excluded`, `excluded_summary`,
`next_batch_index`, `paused`, `items`, and `summary`. Each item contains the
canonical MT5 identity, state, result, error, retry count, and batch metadata.

The repository recomputes the canonical universe hash and serialized state hash.
`base_revision` is optimistic concurrency control; unchanged payloads are
idempotent. Actor identity is injected from authenticated request context.

## Future producer boundary

Input: frozen scan identity/universe, expected revision, batch index, batch asset
IDs, and bounded ranked rows. Output: complete `trend-scan-v1` state plus the
repository save result. Desktop and TaskManager must use this boundary; neither
may reimplement persistence validation.
