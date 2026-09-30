# Strategy Tester Control Center Surface

The Strategy Tester surface is a `BACKTEST / TESTER` read model, never a LIVE
trading surface. It should show tester availability, fixture identity, plan
fingerprint, run status, progress, result, evidence, provenance and a
deterministic failure reason.

B4.4 exposes the status contract as read-only while the current user-owned MT5
terminal prevents a safe real-run gate. No direct UI-to-subprocess path is
introduced and no production execution button is enabled by this document.
