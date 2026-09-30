# JARVIS / GOLDEN Final UI Parity - Post-B4.1

Static comparison of legacy Golden surfaces with the canonical Jarvis Web/Desktop Control Center. This report does not alter `market.html`, start services, or perform visual/runtime calls.

| Surface/feature | Golden source | Jarvis equivalent | Parity | Read/mutable | Security/provenance gap | Decision |
|---|---|---|---|---|---|---|
| Main chat/session | `studio_v7.html` | `jarvis_ui/jarvis.html` + Gateway | PARTIAL | mixed/read | B4.1 chat delegation is present; streaming remains frozen | KEEP/CONVERGE |
| Control Center navigation | `dashboard.html`, `studio_v7.html` | canonical Jarvis UI/Desktop | PARTIAL | read plus legacy actions | legacy routes remain visible | PORT read models |
| Market overview | `market.html`, `market.js` | limited MarketContext/cards | NOT_INTEGRATED | read | source/freshness model missing | PORT |
| Radar multi-asset panels | `market.html`, `operational_center.js` | no full equivalent | NOT_INTEGRATED | read | no canonical provenance/read model | PORT |
| Chart and levels | market chart/levels code | recent candle/read tools | PARTIAL | read | replay and formula evidence absent | CONNECT |
| News and macro | market news/fundamental code | no full panel | NOT_INTEGRATED | read | provider/source/stale states missing | ADAPT |
| Scanner/opportunities | dashboard scanner and Radar | partial tools/read cards | PARTIAL | read | score/risk explanation incomplete | CONNECT |
| Deep analysis | analysis drawer/Golden prompts | chat/MarketContext | PARTIAL | read/synthesis | canonical context/evidence contract incomplete | ADAPT |
| Risk/validation/performance | operational center + legacy modules | partial tools/audit | PARTIAL | read | unknown/real-vs-synthetic states incomplete | MERGE |
| Robot catalog/evidence | dashboard robot views | RobotCatalog foundation | PARTIAL | read | full UI association missing | PORT |
| Strategy Tester evidence | tester legacy/UI artifacts | adapter/read foundations | PARTIAL | read | no complete Control Center view | PORT |
| MQL5 builder/compile | studio controls | evidence tools | PARTIAL | mutable legacy | compile action needs separate gate | FREEZE |
| Positions/order actions | dashboard | intentionally no canonical equivalent | LEGACY_DANGEROUS | mutable | broker mutation and approval surface | LEGACY_FREEZE |
| Voice chat | studio/Radar browser APIs | VoiceService UI/service | PARTIAL/BLOCKED | mutable hardware | real mic/VAD gate incomplete | REFERENCE_ONLY |

## Required state model for future UI work

Every recovered read panel needs:

- explicit `READ_ONLY`, `DISABLED_BY_PROFILE`, `AUTH_REQUIRED`, `APPROVAL_REQUIRED`, and `MUTATION_NOT_AVAILABLE` states;
- source/provider label, observation time, freshness/stale state, and missing-data reason;
- provenance receipt or correlation ID tied to AuditLog;
- empty, loading, error, partial, and stale rendering states;
- distinction between calculated fact, imported observation, model synthesis, hypothesis, and unknown;
- no action button unless the canonical ToolRegistry, SecurityManager, and approval contract already own that action.

## Missing parity list

1. Full Radar/Macro read model and chart/news/levels/session panels.
2. Canonical source registry, freshness policy, and provider attribution.
3. Scanner detail, deep analysis, risk, validation, and performance read models.
4. Robot-to-market evidence association and Strategy Tester evidence views.
5. Scientific-memory evidence/revision/conflict/experiment views.
6. Canonical streaming UI and route.
7. Complete disabled/approval/audit/provenance behavior across legacy-looking controls.

The legacy surfaces remain preserved as donor/reference material. Visual similarity alone is not parity; a feature is recovered only when the data contract, authority, security state, provenance, and failure behavior are equivalent.
