# Jarvis / Golden B3 Zero Feature Loss

`ZERO_FEATURE_LOSS_STATUS: PASS_WITH_RESTRICTIONS`

This status means B3 preserves the useful recovered semantics in canonical
read models while intentionally leaving legacy authority and execution paths
untouched. It does not mean full visual or behavioral parity.

## Preserved in the Control Center

- Radar market map, asset detail context, macro/news metadata, source integrity,
  freshness, and replay/validation metadata when supplied.
- Scanner ranking, score semantics, readiness, setup, confluence, risk-reward,
  regime, volatility, session, trends, indicators, and opportunity detail.
- Robot identity, artifact presence, lifecycle, parameter/evidence counts,
  tester associations, and unresolved historical evidence.
- Validation and Strategy Tester evidence classifications and provenance.
- Scientific-memory status, contract vocabulary, graph summary, and relation
  gaps through the canonical Memory V2 adapter.
- Source/freshness/fingerprint visibility for each read model.

## Restrictions

The following remain outside B3 and are intentionally frozen or deferred:

- live trading, `order_send`, AUTO-TRADE, and `ENTRAR NO TRADE`;
- MT5 operational mutation, Strategy Tester execution, MQL5 compilation, and
  robot lifecycle mutation;
- legacy data import, memory migration, and database schema migration;
- voice, microphone, Windows audio, provider downloads, and dependency install;
- complete legacy visual parity and any unvalidated provider capability.

## Gate Assessment

`PARITY_FULL`: none claimed without evidence.

`PARITY_PARTIAL`: Radar, Scanner, Robots, Evidence, Scientific Memory, and
Provenance read surfaces.

`PARITY_DEFERRED`: execution, voice, legacy writes, migration, and full UI
parity.

`ZERO_FEATURE_LOSS_BLOCKERS`: full parity is blocked only by capabilities that
require a later explicit authority, migration, hardware, or runtime gate; no
B3 blocker requires duplicating Jarvis Core or activating a legacy authority.
