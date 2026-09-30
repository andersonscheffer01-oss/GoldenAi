# JARVIS / GOLDEN Final Architecture Gaps - Post-B4.1

| Area | Current evidence | Gap | Severity | Next gate |
|---|---|---|---|---|
| Jarvis Core | `JarvisService` owns canonical tools, tasks, catalog, tester, audit | several donor capabilities still stop at adapters/read fragments | high | bounded read-model batches |
| Security | `SecurityManager` governs canonical tools; legacy perimeter remains broad | complete inbound route/legacy action convergence not proven | critical | B4.1 restriction gate |
| Audit | `AuditLog` exists; legacy market/root logs remain | one correlation/provenance contract for all compatibility paths | high | audit authority convergence |
| ModelRouter | canonical routing exists | `/stream/chat` direct provider branches remain | critical | canonical streaming design |
| Streaming | legacy SSE/tool loop frozen | no single policy-owned streaming implementation | critical | dedicated streaming gate |
| Memory | boundary and memory v2 exist | scientific evidence/revision/conflict/experiment semantics and active writer binding | high | scientific memory design gate |
| Tasks | TaskManager and task DB candidate exist | multiple DB roots and runtime copies | high | authority inventory |
| Market | Golden `market.html` is rich donor | full overview/news/macro/levels/sessions/source read models missing | high | Market Intelligence batch |
| Scanner | Golden scanner calculations exist | canonical structured read model and freshness/provenance incomplete | high | Scanner read-model batch |
| Risk | `risk_engine.py` and routes exist | explanation/read-only contract not fully canonical | high | Risk convergence batch |
| Validation | validation modules and commands exist | real/synthetic provenance and failure states incomplete | high | Validation convergence batch |
| Performance | journal/statistics foundations exist | association, calibration, and sample quality read model incomplete | medium | Performance batch |
| Robot Catalog | catalog/evidence foundation exists | full UI and market association absent | high | Robot Intelligence batch |
| Repertoire | production inventory remains protected | no approved canonical operational repertoire view beyond design | high | separate design gate |
| Strategy Tester | fixture/evidence adapter foundation exists | no full UI; real run remains separately authorized | high | fixture-only tester gate |
| MQL5 | evidence/source/artifact concepts exist | compile and production artifact proof not part of this audit | high | explicit MQL5 gate |
| Trading | legacy order/auto-trade paths remain | no canonical broker mutation authority | critical | freeze/convergence only |
| Voice | VoiceService and hardware-free tests exist | real microphone/VAD/STT/TTS proof incomplete; no audit execution here | high | voice hardware gate |
| Desktop/Web | canonical shell converges | legacy native and legacy HTML surfaces remain discoverable | medium | source/deployment inventory |
| Skills/MCP | local skills and MCP descriptors exist | permission/ownership/observability matrix incomplete | medium | integration inventory |
| Agents | agent/plugin trees exist | canonical registration and security metadata incomplete | medium | agent registry gate |
| Observability | status/health/logging foundations exist | freshness, correlation, and source status not universal | high | observability contract |
| Personal Finance | deferred/uncanonical | no current approved scope | low | defer |

## Non-negotiable architecture constraints

- One Jarvis Core, one SecurityManager authority, one AuditLog authority, one ModelRouter authority, one Task authority, and one canonical memory boundary.
- Golden code may supply read-only facts, formulas, UX evidence, and provenance-bearing artifacts, but it does not create a second brain or execution owner.
- Legacy action paths remain frozen until caller, auth, audit, rollback, and replacement evidence exists.
- No provider, MT5, trading, tester, MQL5, or Voice hardware action is implied by this document.
