# Tester Result Ownership and Security

## Ownership proof

An artifact is owned only when all applicable checks pass:

- path is inside the selected terminal data root's `Tester\\logs` directory;
- file is a bounded `.log` artifact below the configured size limit;
- artifact timestamp is not stale for the controlled run window;
- exact native testing block matches expert path, symbol, timeframe, and dates;
- terminal build matches the planned terminal identity when observed;
- one and only one matching block/artifact is found;
- plan identities remain attached: test run, campaign, robot, source hash,
  compiled hash, parameter fingerprint, and config hash.

The provider does not trust a filename, a user-supplied result, or a metric
without the surrounding native evidence. Ambiguity fails closed.

## Security boundary

The bridge is read-only. It cannot launch MT5, compile MQL5, send orders,
change broker state, access credentials, write runtime databases, or mutate
the Robot Catalog. Path traversal and oversized files are rejected. Raw and
normalized hashes are retained for audit and later provenance joins.

## Integration boundary

`StrategyTesterAdapter` remains the execution and human-gate authority.
`NativeTesterLogProvider` is a bounded result reader behind that authority;
it is not a second execution path. The production EA source and compiled
artifact are not modified by B4.5A.
