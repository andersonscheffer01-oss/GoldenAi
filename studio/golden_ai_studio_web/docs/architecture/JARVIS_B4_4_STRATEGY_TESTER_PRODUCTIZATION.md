# B4.4 Controlled Strategy Tester Productization

Status: `PASS_WITH_RESTRICTIONS` for the contract and dry-run layer.

The canonical path is `Control Center -> JarvisService -> SecurityManager ->
StrategyTesterAdapter -> immutable evidence -> RobotCatalog`. The new
`strategy_tester_productization.py` module contains immutable TestPlan,
configuration, artifact and approval contracts plus a read-only Control Center
snapshot. It does not create a second executor or start a process.

The only permitted identity in this batch is
`fixture_golden_strategy_tester_v1` / `GoldenStrategyTesterFixture`.
Production robots, optimization, live trading, broker actions, Voice and
provider calls remain disabled. The existing terminal process prevents a safe
T15 isolation pass, so no real Strategy Tester run is started.

The dry-run contract covers success, configuration mismatch, fixture mismatch,
wrong terminal, missing or ambiguous artifact, parse failure, timeout, expired
approval, reused approval and stale target. Evidence remains separate from
production robot suitability and does not make the empirical matcher ready.
