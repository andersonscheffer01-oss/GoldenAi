# Robot Profile Contract

Each profile is derived from the existing catalog and contains:

- stable `robot_id`, name and version;
- source/artifact status and artifact identities;
- strategy family, symbols, timeframes, sessions, regime and risk metadata;
- evidence counts, conflicts, limitations and provenance;
- `repertoire_status` separate from `trading_authorization`.

Each inferred field is represented with `value`, `source`, `status`, and
`inference_method`. Unknown fields are not replaced by defaults. Source status
is one of `SOURCE_AVAILABLE`, `SOURCE_MISSING`,
`COMPILED_REFERENCE_ONLY`, `HISTORICAL_ONLY`, or `UNKNOWN`.
