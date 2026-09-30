# Strategy Tester Security Contract

Strategy Tester execution is a controlled action owned by JarvisService and
guarded by the canonical SecurityManager. `SingleUseApproval` is a target
binding contract for tests; it is not a replacement SecurityManager.

Approval binds action, run ID, fixture, terminal, data root and config hash,
has a bounded TTL and is single-use. A stale target, expired approval or
reused approval fails closed. No credentials are accepted, no AutoTrading flag
is changed, and no order path is reachable from this capability.
