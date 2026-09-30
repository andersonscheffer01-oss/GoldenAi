# Robot Repertoire Contract

The user owns repertoire membership. Discovery never promotes a robot to
`ACTIVE`; new observations remain `DISCOVERED` or `CANDIDATE`. Existing
catalog user overrides are preserved and are not rewritten by read
projections.

Allowed lifecycle states are `DISCOVERED`, `CANDIDATE`, `ACTIVE`, `INACTIVE`,
`BLOCKED`, and `ARCHIVED`. None of them grants trading permission. The
execution boundary remains a future explicit SecurityManager approval flow.

The B4.3 UI is read-only. Repertoire mutation remains outside this batch
because mutation history and approval semantics must not be improvised in the
Control Center.
