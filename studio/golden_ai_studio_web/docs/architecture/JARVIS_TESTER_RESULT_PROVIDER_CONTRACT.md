# Tester Result Provider Contract

## Provider-neutral result

`NormalizedTesterResult` is the canonical read model for tester outputs. It
contains:

- test run, campaign, robot, source, compiled, and parameter identities;
- symbol, timeframe, period, tester model, terminal version, data root, and
  run timestamps;
- raw artifact kind, bounded path, raw SHA-256, provider, and parser version;
- normalized metrics, per-metric provenance, warnings, limitations, and
  reconciliation status;
- a deterministic fingerprint of the normalized payload.

Each metric records `raw_field`, `raw_value`, `normalized_value`, `unit`,
`source_artifact`, `provider`, `confidence`, and `status`. The bridge never
converts an absent metric into zero.

## Provider outcome

`ProviderOutcome` carries the bounded status, provider, artifact identity,
normalized result when available, warnings, and limitations. Multiple
providers are compared without choosing a winner:

`MATCH`, `PARTIAL_MATCH`, `CONFLICT`, or `NOT_COMPARABLE`.

## Implemented providers

`NativeTesterLogProvider` is the B4.5A production-log provider.
`FixtureJsonResultProvider` is the B4.4 compatibility provider and delegates
identity checks to the existing `parse_result_json` and `reconcile_result`
contracts.

## Audit vocabulary

The provider contract recognizes:

`RESULT_PROVIDER_SELECTED`, `RAW_TESTER_ARTIFACT_DISCOVERED`,
`RAW_TESTER_ARTIFACT_REJECTED`, `RAW_TESTER_ARTIFACT_VERIFIED`,
`TESTER_RESULT_NORMALIZED`, `TESTER_RESULT_RECONCILED`, and
`TESTER_RESULT_CONFLICT`.

These names describe audit integration; this B4.5A read bridge does not
change the existing AuditLog authority or add a database migration.
