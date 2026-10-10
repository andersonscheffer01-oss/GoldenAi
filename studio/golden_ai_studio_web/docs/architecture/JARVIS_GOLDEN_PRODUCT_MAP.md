# JARVIS / GOLDEN Product Map

This is an audit map of ownership and integration. `PARTIAL` means the backend or capability exists but the canonical Control Center path is incomplete; it does not authorize implementation or live execution.

| Capability | Canonical owner | Current surface | Governance | Web/Desktop | Status and gap |
|---|---|---|---|---|---|
| Golden Web backend | `server_agent.py` plus shared `JarvisService` | `dashboard.html`, `studio_v7.html`, APIs | Mixed; canonical calls are governed, legacy calls need containment | Web; Desktop can reuse Core | `PARTIAL`: broad legacy route authority remains |
| Jarvis Control Center | `jarvis_ui` -> Gateway -> JarvisService | `jarvis_ui/jarvis.html` | Canonical security and audit path | Web and Desktop WebView | `PASS_WITH_RESTRICTIONS`: shared shell exists |
| Desktop shell | `jarvis_desktop` + `CoreLauncher` | QtWebEngine canonical WebView | Reuses Core and Gateway | Desktop | `PASS_WITH_RESTRICTIONS`: native compatibility UI remains |
| Scanner and risk | Jarvis tools and existing trading modules | Web legacy panels and Jarvis commands | High-risk actions require governance | Web/Desktop | `PARTIAL`: legacy presentation and action paths coexist |
| MT5 read-only status | Jarvis tools plus legacy connector | Gateway telemetry and legacy `/api/mt5/*` | Canonical status is auditable; legacy probes remain | Web/Desktop | `PARTIAL`: read model not fully unified |
| Live trading | `JarvisService` governed tools; legacy `mt5_trader.py` | Legacy dashboard actions and canonical commands | Confirmation/risk gates exist | Web/Desktop | `RESTRICTED`: contain legacy direct action surface |
| Backtest | `StrategyTesterAdapter` for controlled evidence | Legacy real backtest endpoint plus Jarvis command | Adapter is canonical for new gate | Web/Desktop | `PARTIAL`: UI still reaches legacy real backtest |
| Robot catalog | `RobotCatalogReadModel` and catalog DB | Core tools | ToolRegistry and AuditLog | Backend; no full UI | `PARTIAL`: catalog views absent from Control Center |
| Strategy Tester | `StrategyTesterAdapter` and MQL5 evidence | Core tools/fixture flow | Provenance and confirmation gates | Backend; no full UI | `PARTIAL`: controlled run UI and status view absent |
| MQL5 compile/evidence | `mql5_evidence.py` | Fixture and Core evidence tools | Source/compiled hashes and compile evidence | Backend; legacy builder UI exists | `PARTIAL`: builder can bypass evidence UX |
| Memory | `CanonicalMemoryBoundary` -> V2 preferred | Core retrieval, vault, graph, hybrid | Provenance-aware V2 path | Backend and UI consumers | `PARTIAL`: legacy compatibility fallback remains |
| Tasks and scheduler | `TaskManager`, scheduler, BackgroundControlCenter | Task APIs/UI | Canonical task DB and audit | Web/Desktop | `PASS_WITH_RESTRICTIONS`: legacy DB artifacts remain |
| Computer Use | Core computer-use tools and security scopes | Jarvis commands/Desktop context | SecurityManager and audit | Web/Desktop | `PARTIAL`: capability exists; surface coverage varies |
| Voice | `voice_service.py`, voice and realtime modules | Core/Web/Desktop hooks | Existing service boundary | Web/Desktop | `PARTIAL`: real VAD/STT gate unresolved |
| Skills | `SkillsRouter` and local skills | Core capability routing | Registry/security boundary | Web/Desktop through commands | `PARTIAL`: some capability mappings are empty |
| MCP | `McpClientManager` | Explicit stdio configured providers | Core remains execution boundary | Web/Desktop through Core | `PARTIAL`: provider set is intentionally narrow |
| Providers | Jarvis providers and configured external/local models | Core provider layer | Core/audit path | Web/Desktop | `PASS_WITH_RESTRICTIONS`: legacy status probes coexist |
| Audit and provenance | `AuditLog`, evidence artifacts, catalog DB | Core and evidence stores | Sanitization and hashes | Backend; UI evidence view incomplete | `PARTIAL`: UI does not expose the full chain |

## Product conclusion

The product map is complete as an audit inventory, not as proof that every row is fully integrated. The strongest shared path is the canonical Jarvis Web UI reused by Desktop. The highest-value next step is to make catalog, tester, evidence, and legacy-action state visible through that same Control Center while preserving existing artifacts and gates.
