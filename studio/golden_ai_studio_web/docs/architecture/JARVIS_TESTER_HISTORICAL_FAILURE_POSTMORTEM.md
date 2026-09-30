# Historical Tester Failure Postmortem

Runs `run_43d56ac94e5249f0b9a9500a9b3d7946`,
`run_768b88bd9efd480e96ab5a64a3051f9e` and
`run_0fc66205f9614ff98f5801614e0d910a` are preserved and were not retried.

Read-only facts: each run directory contains `manifest.json` and `tester.ini`
but no result JSON. The current config bytes for the first two runs match the
full SHA-256 values recorded in their provenance. The latest run,
`run_0fc66205f9614ff98f5801614e0d910a`, does not: its current `tester.ini`
hash is `e2f035de730226aaf251137a7c8cbd2eed0be594ccbb9bde894c908fe5a37d21`,
while the manifest records `79bb714e3ecda278289eee80038054b99f723be7e8efffedc97079a004ed6ecb`.
The latest manifest records an expected `Agent-*` output pattern, but no
matching artifact is present in the bounded data-root locations inspected.

The historical root cause is therefore `UNKNOWN` beyond these proven facts.
The mismatch may reflect an artifact/config lifecycle problem, but that is not
claimed as fact. Historical manifests, configs, catalog rows and retry links
remain immutable.
