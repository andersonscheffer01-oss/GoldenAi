# JARVIS / GOLDEN Final Unknown Register - Post-B4.1

Unknown means static source evidence is insufficient. It is not a positive claim that a path is safe, active, or equivalent.

| ID | Unknown | Why static audit cannot prove it | Safe validation later |
|---|---|---|---|
| U-01 | Active task/memory/catalog DB binding | multiple roots and runtime copies exist | read-only runtime/config inventory with no writes |
| U-02 | Current market data freshness | source freshness depends on runtime/provider state | read-only snapshot with source timestamps |
| U-03 | Active provider health and policy | credentials/config/runtime state were not read | sanitized policy/status inspection, no request |
| U-04 | Broker/account/live mode | MT5 and credentials are outside this audit | explicit human-gated status read |
| U-05 | Full legacy route reachability | source route map is broad; deployment callers are not fully proven | route inventory and auth characterization in isolated harness |
| U-06 | `/stream/chat` production caller population | frozen implementation is source-reachable | caller/deployment inventory before canonical replacement |
| U-07 | Exact Radar runtime payloads | no server/network/runtime call allowed | deterministic fixture/read-only payload capture |
| U-08 | Historical artifact semantic validity | filenames/manifests do not prove result meaning | hash/schema/manifest reconciliation |
| U-09 | Robot-to-Market empirical association | signals exist but no stable association dataset | read-only join design and fixture validation |
| U-10 | Complete canonical UI parity | static source cannot replace a human visual/runtime check | approved visual gate with safe profile |
| U-11 | Voice real microphone/VAD behavior | hardware was explicitly excluded | separate human hardware gate |
| U-12 | External MCP/agent deployment state | descriptors do not prove active registration | local registry/permission inventory |
| U-13 | Generated build/dist source-of-truth | outputs coexist with source and may be stale | deployment manifest/source hash comparison |
| U-14 | Runtime audit correlation coverage | multiple audit/logger families exist | sanitized event contract test |
| U-15 | Personal Finance capability status | no approved current scope | defer; do not infer from unrelated modules |

## Handling rule

Unknowns remain visible in the Control Center and audit reports. They must not be silently converted into `PASS`, `REAL`, `FRESH`, `SAFE`, or `CANONICAL`. A future validation gate must preserve no-provider/no-MT5/no-trading constraints unless it explicitly receives a narrower authorization.
