# Jarvis / Golden Legacy Strategy Tester Reuse Audit

This document records reusable knowledge from the legacy MT5 tester path. It does not authorize a tester run, production compile, EA selection, retry or repair of prior runs.

## Current evidence boundary

- `STRATEGY_TESTER_EXECUTED: NO` in this audit.
- `run_43d56ac94e5249f0b9a9500a9b3d7946`: `FAILED / UNVERIFIED / RESULT_ARTIFACT_MISSING`.
- `run_768b88bd9efd480e96ab5a64a3051f9e`: `FAILED / MISMATCH`.
- `run_0fc66205f9614ff98f5801614e0d910a`: `FAILED / UNVERIFIED / RESULT_ARTIFACT_MISSING`.
- Run 3 preflight manifest config hash: `79bb714e3ecda278289eee80038054b99f723be7e8efffedc97079a004ed6ecb`.
- Run 3 executed adapter config hash: `e2f035de730226aaf251137a7c8cbd2eed0be594ccbb9bde894c908fe5a37d21`.
- The adapter regenerated `tester.ini` with a different report path and direct invocation did not create a separate Jarvis `AuditLog` receipt. This is proven config drift, not a reason to weaken reconciliation.
- Run 2 showed real MT5 output under the Agent profile `MQL5\\Files`, but fixture identity and result counts did not reconcile. This is proven Agent output discovery evidence, not a valid success.

## Legacy tester knowledge matrix

Classification: `KEEP_OURS`, `PORT`, `ADAPT`, `REIMPLEMENT_PATTERN`, `REFERENCE_ONLY`, `REJECT`.

| KNOWLEDGE_AREA | LEGACY_BEHAVIOR | CANONICAL_BEHAVIOR | OBSERVED_REAL_MT5_BEHAVIOR | BEST_PATTERN | RECOMMENDATION |
|---|---|---|---|---|---|
| Config generation | `mt5_real_backtest.py` writes/opens manual tester setup | adapter hashes config and manifest | tester path can be overwritten by later invocation | immutable canonical config | KEEP_OURS |
| Terminal discovery | tries several install/profile fallbacks | explicit terminal/data-root contract | correct D0... data root was known | retain explicit allowlist only | ADAPT |
| MetaEditor | may open GUI and return “Press F7”; not proof of compile | compile evidence requires real success/hash | GUI/manual compile is not deterministic evidence | never treat launch as compile | REJECT legacy behavior |
| Process lifecycle | starts terminal/manual UI if absent | bounded process boundary and cleanup | manual close caused missing result | single owned process + evidence wait | KEEP_OURS |
| Agent output | legacy discovery did not bind one output root | adapter restricts allowed result roots | Run 2 emitted under `Agent-127.0.0.1-3000\\MQL5\\Files` | record actual root and identity | ADAPT |
| Result discovery | returns path/opens tester without verified result | result artifact required, stale checked | Run 1/3 missing result JSON | fail closed | KEEP_OURS |
| Report format | manual report path/instructions | hashed config and result manifest | report path drifted in Run 3 | bind report path before launch | KEEP_OURS |
| History/data root | hard-coded D0... plus fallbacks | explicit data-root preflight | old profile must never be fallback | allowlisted root only | ADAPT |
| EA/preset/parameters | regex-generated `GoldenAI_Backtest_*` EA; no full identity | source/compiled/preset/parameter fingerprints | fixture mismatch surfaced | fixture identity first | REIMPLEMENT_PATTERN |
| Timeout/cleanup | manual instructions; no reliable timeout | bounded wait, process state, cleanup evidence | close/manual interruption leaves unverifiable run | preserve failed state | KEEP_OURS |
| Provenance/security | no complete source/compile/run receipt | fixture gates, hashes, manifest and reconciliation | direct adapter lacked separate AuditLog | one Core receipt chain | KEEP_OURS |
| Legacy strategy substitution | creates EA from universal template and strategy text | dedicated fixture cannot reuse production logic | production identity would contaminate evidence | fixture-only gate | REJECT |

## Reuse decisions

Keep canonical adapter evidence gates. Adapt only path knowledge, explicit D0... data-root discovery, Agent output observation and manual lifecycle lessons. Port no manual compile behavior, no fallback to the old REAL profile, no direct live connector, no report-path mutation, and no “zero bars means success” interpretation. The old `mt5_connector.py`, `mt5_trader.py` and `mt5_real_backtest.py` remain legacy authorities and are not wired around Jarvis security.

## Required future gate

Any future controlled fixture run must reconcile, before tester launch: fixture identity, source artifact/hash, `COMPILE_SUCCESS` and compiled artifact/hash, `test_run_id`, parameter fingerprint, preset/config/manifest hashes, terminal/data root, report/result paths and audit receipt. A failed run remains immutable history; a retry is a new run linked by `RETRY_OF`.
