# JARVIS B4.1A - Legacy Authority Map

Status: STATIC / READ-ONLY
Baseline: `c033b61dbbe684ee0943854e650f471bfd87a31b`

## Authority map

| Surface | Observed owner | Evidence | Classification | Target owner |
|---|---|---|---|---|
| Root permission policy | `core.permissions.PermissionManager` | Imported and instantiated by `server_agent.py`; used by root modules | `KEEP_READ_ONLY` during characterization | Jarvis `SecurityManager` via adapter |
| Root execution gate | `core.execution.ExecutionService` | `EXECUTION_SERVICE` and `_authorize_api_mutation` | `DELEGATE_FIRST` | JarvisService/ToolRegistry/SecurityManager |
| Root execution audit | `core.audit.AuditLogger` | Constructed by ExecutionService; daily JSONL output | `DELEGATE_FIRST` | `jarvis_core.audit.AuditLog` |
| Canonical tool security | `jarvis_core.security.SecurityManager` | Jarvis service/tool security flow | `KEEP_READ_ONLY` as target authority | Same |
| Canonical audit | `jarvis_core.audit.AuditLog` | Jarvis audit table and sanitizer | `KEEP_READ_ONLY` as target authority | Same |
| Golden read models | `jarvis_core` Golden bridge/read routes | `/api/jarvis/golden/*` routes and B3 docs | `KEEP_READ_ONLY` | Jarvis read models |
| Provider routing | ModelRouter plus direct server helpers | Canonical model router, legacy helper calls, and Gateway WS clients | `FREEZE_FIRST` | ModelRouter/provider policy gate |
| MT5 route authorization | Root execution helper on selected mutations | Compile, backtest, auto-trade, close-position handlers | `FREEZE_FIRST` | SecurityManager plus explicit approval |
| MT5 positions read | Direct `mt5_trader.get_open_positions` observed | Route body lacks visible mutation authorization | `DELEGATE_FIRST` | Jarvis read tool/provider adapter |
| Market audit telemetry | Direct `data/market_ai_audit.jsonl` write | `_api_market_analyze` source path | `DELEGATE_FIRST` | AuditLog-linked market event |
| Memory v2 | `jarvis_core.memory.v2` and boundary modules | `remember`/graph/evidence writes | `KEEP_READ_ONLY` pending writer inventory | CanonicalMemoryBoundary |
| Task stores | Jarvis task modules plus multiple runtime DB roots | Task routes and DB inventory | `DELEGATE_FIRST` pending ownership proof | Canonical task authority |

## Direct provider bypasses

The following classes were observed statically in `server_agent.py` or legacy
provider adapters:

| Bypass | Reachability | Current behavior | Risk | Decision |
|---|---|---|---|---|
| `/api/chat` legacy chat | Route exposed; legacy callers present | Compatibility adapter now calls `JarvisService.generate_response` | Legacy response compatibility remains; canonical history/audit path is used | `DELEGATED_W5` |
| `/api/agent` legacy agent | Route exposed | Compatibility adapter now calls `JarvisService.execute_tool` | Legacy payload remains; canonical SecurityManager/AuditLog own execution | `DELEGATED_W5` |
| `/stream/chat` | Streaming handler and SSE content type observed | Direct/legacy streaming provider path, explicitly frozen | Canonical ModelRouter has no streaming equivalent yet | `FROZEN_W5` |
| Gemini/Groq/Ollama/Cline/OpenRouter/Claude helpers | Imported/called by legacy server paths | Provider calls outside one proven policy gate | Provider and secret-boundary divergence | `DELEGATE_FIRST` |
| Canonical model router | Jarvis orchestrator path | Intended canonical route | Provider policy still future scope | `KEEP_READ_ONLY` |

The UI Gateway WebSocket at dynamic `ws(s)://<host>:8766/ws` is not classified
as a direct provider bypass. Its source protocol has a device-token handshake,
but its authorization and audit contract is separate from the HTTP 8765
perimeter and remains a convergence dependency.

"Active" here means source-reachable or referenced by a route; it does not
mean the endpoint was executed. "Dead" is not assigned where a current caller
was not proven. Dead/deprecated classification requires a separate reachability
and deployment inventory.

## Legacy trading paths

| Route | Observed action | Current gate observation | Target action |
|---|---|---|---|
| `/api/mt5/status` | MT5 status/read | Perimeter coverage not proven | Authenticated read adapter |
| `/api/mt5/positions` | Open positions read | Direct connector call observed | Canonical read tool and AuditLog |
| `/api/mt5/compile` | MetaEditor subprocess compile | `_authorize_api_mutation` uses root ExecutionService | Freeze then delegate |
| `/api/mt5/backtest` | Backtest path | Legacy mutation/side-effect surface | Freeze then delegate |
| `/api/mt5/real_backtest` | Real backtest connector | Root mutation helper observed | Freeze then delegate |
| `/api/mt5/auto_trade` | Optional auto execution | Root authorization only when `auto_execute` | Freeze and require explicit approval |
| `/api/mt5/close_position` | Close position | Root mutation helper observed | Freeze and require explicit approval |
| `/api/mt5/import_history` | History import | Data mutation path | Explicit approval and audit |

The static map does not authorize any of these actions and no trading or MT5
operation was performed.

## Parallel memory and task authority

Memory authority is classified `POTENTIAL/PARTIAL`: canonical memory boundary
and v2 writers exist, but multiple runtime databases and historical writer
surfaces require a complete caller inventory before a parallel final authority
can be proven.

Task authority is classified `POTENTIAL/PARTIAL` for the same reason. The
presence of several task/runtime DB roots is evidence of a convergence risk,
not evidence that all are active or equivalent.

## Classification rules

- `FREEZE_FIRST`: high-risk legacy behavior stays contained until ownership,
  authorization, and audit are characterized.
- `DELEGATE_FIRST`: install an observable compatibility boundary before policy
  or provider behavior is changed.
- `MIGRATE_DIRECTLY`: only a characterized, low-side-effect read contract.
- `KEEP_READ_ONLY`: preserve a canonical read surface without expanding it.
- `REMOVE_LATER`: only after caller, deployment, replacement, and rollback
  evidence exists.
- `REFERENCE_ONLY`: useful implementation evidence that must not execute.
