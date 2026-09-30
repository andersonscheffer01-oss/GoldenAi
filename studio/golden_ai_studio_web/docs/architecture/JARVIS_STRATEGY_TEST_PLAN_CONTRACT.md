# Strategy TestPlan Contract

`TestPlan` is immutable after creation and is fingerprinted from canonical
JSON. It binds `test_run_id`, fixture identity, source and compiled hashes,
symbol, timeframe, dates, tester model, parameters, terminal identity, data
root, expected result naming, timeout and purpose.

The only B4.4 purpose is `PIPELINE_VALIDATION_FIXTURE`. The approved fixture is
`fixture_golden_strategy_tester_v1`; any production robot, alternate terminal,
alternate data root or different purpose is rejected before execution.

Serialized plans are rehydrated with hash verification. A changed field is a
`PLAN_FINGERPRINT_MISMATCH`, not a new interpretation of the old approval.
