# Strategy Tester Evidence Pipeline

The evidence sequence is:

`TestPlan -> config bytes/hash -> approved process boundary -> bounded result
artifact -> parser -> manifest reconciliation -> RobotCatalog evidence`.

The fixture writes deterministic JSON only for pipeline proof. A successful
fixture result is classified as `FIXTURE`, not a production performance sample.
Failed historical runs remain immutable and useful as operational evidence,
but `FAILED_RUN != PERFORMANCE_SAMPLE`.
