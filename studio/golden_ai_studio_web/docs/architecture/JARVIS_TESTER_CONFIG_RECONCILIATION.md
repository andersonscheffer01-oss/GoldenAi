# Strategy Tester Config Reconciliation

The canonical Strategy Tester flow has two distinct config identities:

- `SCIENTIFIC_CONFIG_FINGERPRINT` covers every field capable of changing the
  experiment, including EA, preset, symbol, timeframe, model, dates, capital,
  execution, optimization, and permissions.
- `MATERIALIZED_CONFIG_FINGERPRINT` is the SHA-256 of the exact UTF-8 bytes
  written and passed to MT5.
- `OUTPUT_ROUTING_FINGERPRINT` covers output-only routing such as `Report` and
  `ReplaceReport`.

`tester_config_reconciliation.py` materializes the existing adapter convention
`Tester\\Jarvis\\<test_run_id>.htm` deterministically and bounds the derived
path. It does not ignore output fields: it classifies, fingerprints, and
reconciles them. Unknown changed fields fail closed.

For B4.5R23A, the Run 2 byte mismatch is exactly one `Tester.Report` value:
the pre-registered `Tester\\Jarvis\\B45\\...` route and the adapter's
deterministic `Tester\\Jarvis\\...` route. Scientific fields and security
fields remain identical. The original stopped evidence remains historical;
the derived reconciliation records both fingerprints and the materialization
version.
