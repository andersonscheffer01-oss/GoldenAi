# Jarvis Post-B3 Gap Register

Date: 2026-09-29
Baseline: `013ba7c700a5c62fc97aaab10541ed5a769b5d13`
Nature: read-only planning register. No gap below authorizes implementation.

## Priority and status

| ID | Gap | Status | Priority | Evidence | Candidate gate |
|---|---|---|---|---|---|
| P3-01 | Direct provider and legacy route ownership | PARTIAL | P0 | `server_agent.py` still contains direct Gemini/Groq/Ollama and broad legacy routes | B4.1 |
| P3-02 | Security perimeter split | PARTIAL | P0 | Jarvis `SecurityManager` coexists with root permission/execution paths | B4.1 |
| P3-03 | Audit/observability split | PARTIAL | P0 | Jarvis `AuditLog` is canonical internally; root audit and direct records remain | B4.1 |
| P3-04 | Parallel task/memory/runtime database roots | PARTIAL | P0 | multiple DB families and historical copies are present | B4.1/B4.4 |
| P3-05 | Scanner semantic depth | PARTIAL | P1 | normalized B3 fields exist; scoring/readiness/confluence meaning is not fully canonical | B4.2 |
| P3-06 | Radar feature depth | PARTIAL | P1 | B3 overview exists; chart/news/macro/session/replay parity is incomplete | B4.2 |
| P3-07 | Deep analysis explanation | PARTIAL | P1 | context/detail adapters exist; complete MTF/statistical evidence is incomplete | B4.2 |
| P3-08 | Risk and validation evidence detail | PARTIAL | P1 | read models exist; synthetic/real/freshness labels need stronger contracts | B4.2 |
| P3-09 | Robot/performance association | FOUNDATION_ONLY | P1 | catalog, backtests and evidence exist without one reconciled suitability model | B4.3 |
| P3-10 | Strategy Tester product lifecycle | FOUNDATION_ONLY | P1 | controlled adapter/evidence exists; normal UI run action is intentionally absent | B4.3 |
| P3-11 | Scientific evidence semantics | PARTIAL | P1 | Golden typed semantics documented; Jarvis boundary lacks full public contract | B4.4 |
| P3-12 | Temporal market memory | DESIGN_ONLY | P1 | need is identified; no second memory authority is permitted | B4.4 |
| P3-13 | Declarative provider policy | DESIGN_ONLY | P1 | current router has ordering/fallback; policy by capability needs a contract | B4.5 |
| P3-14 | Control Center parity | PARTIAL | P1 | B3 summary/read models exist; full state/action/provenance panels do not | B4.5 |
| P3-15 | MCP integrated ownership | FOUNDATION_ONLY | P2 | definitions/scaffolding exist; complete canonical client proof is absent | later |
| P3-16 | Agent capability need | FOUNDATION_ONLY | P2 | legacy descriptors exist; no concrete subordinate-worker need is approved | later |
| P3-17 | Vision real-world evidence | FOUNDATION_ONLY | P2 | tools/models exist; broad semantic validation is not established | later |
| P3-18 | Mobile client | MISSING | P2 | PWA/LAN is not a dedicated validated mobile client | later |
| P3-19 | Voice real microphone path | BLOCKED | P1 | `REAL_MIC_SIGNAL_PATH_INCONSISTENCY` / low signal restriction | separate hardware gate |
| P3-20 | Personal Finance | DEFERRED | out of scope | explicitly excluded from B4 | never in active B4 |

## No silent loss after B3

Resolved or bounded by B3:

- Market Intelligence entry and desktop integration.
- Main Chat, Market Chat and Deep Analysis canonical response boundary.
- MarketContext shape and read-only semantics.
- Golden read bridge provenance/freshness envelope.
- Web AI safe runtime profile and MT5 lazy-init containment.
- Control Center summary and evidence/catalog read visibility.

Still open:

- richer Radar/Scanner/Deep Analysis/Risk/Validation read models;
- scientific memory adaptation and temporal market observations;
- data recovery/reconciliation without automatic import;
- repertoire/performance association and tester lifecycle UI;
- provider policy, direct-handler containment and perimeter observability;
- voice hardware restriction and full UI parity.

## Data recovery constraints

Potential data families include scientific evidence, trade/setup JSONL, market AI
audit, robot/evidence catalog, task/audit receipts, backtests and auxiliary
conversations. Each family must first be classified as `UNIQUE`, `DUPLICATED`,
`SUPERSEDED`, `UNKNOWN`, `FIXTURE`, `RUNTIME` or `BACKUP`.

Only validated `UNIQUE` records may become a future recovery candidate. Original
IDs, timestamps, hashes, source, owner and freshness must remain intact.
No data import, database migration, compaction or deletion is part of this gate.

## High-risk exclusions

The following are separate gates and are not hidden inside B4 normal work:

- live trading, broker mutation, order send and auto-trade;
- real Strategy Tester or MQL5 compile;
- production robot changes or repertoire authorization;
- Voice hardware, microphone, speaker, VAD retuning or model download;
- external credential setup and paid provider calls;
- database migration and production data import.

## User decision boundary

Only these decisions require a future explicit user action:

1. Which B4 subgate to authorize first.
2. Whether to authorize a later provider configuration/credential gate.
3. Whether to authorize a specific data family import, hardware test, tester run,
   or trading action.

Architecture decisions already treated as approved: Jarvis sovereignty, reuse of
Golden as donor, Market visual preservation, Gemini as desired primary, future
Codex capability, local offline fallback, active MT5 roadmap, deferred Personal
Finance and one canonical authority chain.

## Gate condition

`RESULT: PASS_WITH_RESTRICTIONS` for planning. B3 remains closed. B4.1 is not
started and no implementation, provider call, hardware access, MT5 action,
Strategy Tester run, MQL5 compile, Voice test, MCP install, data import, commit
or push occurred while producing this register.
