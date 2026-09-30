# B4.5 Campaign Resume Plan

## Existing campaign

Campaign `campaign_073cebd5e7df446fa9c85bae75ffbe0a` remains unchanged. Its
three planned runs are:

- `run_1c8069dbd88842a4ad88cd9d6ae6fa7d`
- `run_a8180c7c559746da9b7a6863f6796292`
- `run_c078697fe9ce4892bc9665e6f276be58`

The production robot, source hash, compiled hash, parameter fingerprint,
campaign manifest, terminal, data root, and scientific windows remain those
of the existing campaign package. No run was started in B4.5A.

## Approval state

Because B4.5A changes the result contract from EA-specific output to a
provider-neutral native bridge, any prior B4.5 approval is
`STALE_BY_CONTRACT_CHANGE`. A fresh explicit approval is required for each
future controlled campaign gate. B4.5A does not consume or reuse that
approval.

## Resume sequence

For each existing plan, the future gate must:

1. re-read and hash the unchanged plan, config, campaign manifest, source,
   compiled artifact, and parameter fingerprint;
2. prove the selected terminal/data-root identity and a single-run window;
3. run only after a fresh human approval for the exact test run ID;
4. preserve the raw native log before normalization;
5. select `NativeTesterLogProvider`, verify ownership, normalize, reconcile,
   and persist the result through the existing canonical evidence path;
6. stop on missing, stale, ambiguous, conflicting, or incomplete evidence.

No automatic retry, batch start, EA edit, MQL5 compile, live trading, broker
mutation, or database migration belongs to this resume plan.

## Current gate result

B4.5A provider dry-runs cover all three plan identities without external
processes. The campaign is structurally resumable, but it is not authorized
to execute until the fresh approval gate is presented and accepted.
