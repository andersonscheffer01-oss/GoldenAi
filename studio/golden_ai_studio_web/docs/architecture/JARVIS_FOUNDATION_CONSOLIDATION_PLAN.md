# JARVIS / GOLDEN FOUNDATION CONSOLIDATION PLAN

Data: 2026-09-28
Baseline F1: `5acb200`
Baseline F2: `5acb200`
Modo: architecture / trace / consolidation / read-only diagnostics / reuse-first
Escopo: F1 design plus F2 read-only diagnostics. Nenhum ownership switch,
migracao ou refactor de comportamento foi executado.

## Design verdict

`PASS_WITH_RESTRICTIONS`

O caminho ativo ja centraliza uma parte importante do Jarvis, mas ainda existem owners paralelos. A menor convergencia segura e preservar os consumidores funcionais e introduzir fronteiras explicitas antes de mover qualquer comportamento.

## Canonical owner decision

```yaml
CANONICAL_CORE: JARVIS_CORE
CANONICAL_SECURITY: jarvis_core.security.SecurityManager
CANONICAL_AUDIT: jarvis_core.audit.AuditLog
CANONICAL_TASK_SYSTEM: jarvis_core.task_manager.TaskManager
CANONICAL_TASK_DB: C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db
CANONICAL_MODEL_ROUTER: jarvis_core.orchestrator.ModelRouter
CANONICAL_MEMORY: EXISTING_COMPONENT_TO_BE_CONSOLIDATED
```

### Why Jarvis Core wins

The decision is based on active call sites and validated behavior, not directory name:

- `desktop_center.py` creates `JarvisService(Path(__file__).resolve().parent)`.
- `JarvisService` constructs SecurityManager, AuditLog, TaskManager, CentralOrchestrator, Skills and ComputerMissionExecutor.
- `TaskManager` owns Scheduler, retries, approvals, durable runs and mission checkpoint integration.
- `server_agent.start_server()` gives the same `JarvisService` to VoiceService and Gateway.
- Computer Use, Scheduler, Desktop Control Center, browser scopes and Voice lifecycle have focused tests and prior real gates.
- `jarvis_core.orchestrator.ModelRouter` is the router used by the canonical Brain/Orchestrator path.

The root Core is not discarded. Its active capabilities become temporary adapters or migration sources where it has stronger existing behavior.

## Entry point inventory

| Entry point | Purpose | Active | Core | Security | Audit | Task DB | Provider | Memory |
|---|---|---|---|---|---|---|---|---|
| `start_golden.bat` | Main Studio launcher | YES | `server_agent` + `jarvis_core` and root compatibility imports | Root `ExecutionService` for old tools; Jarvis SecurityManager for Jarvis routes | Mixed | Workspace Jarvis DB through DesktopCenter | Direct legacy functions plus Jarvis adapters | Jarvis memory through DesktopCenter |
| `ABRIR_GOLDEN_AI_STUDIO.bat` | Studio launcher | YES | Same as above | Same | Same | Same | Same | Same |
| `ABRIR_GOLDEN_AI_STUDIO_WEB.vbs` | Hidden/desktop launch wrapper | YES | Same `server_agent` path | Same | Same | Same | Same | Same |
| `server_agent.py` | HTTP/SSE entrypoint and compatibility facade | YES | Mixed; Jarvis path plus root services | Mixed | Mixed | Delegates Jarvis task APIs | Direct Groq/Gemini/Ollama plus adapter registration | Jarvis memory routes plus old app paths |
| `desktop_center.py` | Runtime bridge for Desktop Center | YES when imported | `JarvisService` | `jarvis_core.SecurityManager` | `jarvis_core.AuditLog` | Canonical workspace DB | Canonical Orchestrator | Jarvis legacy+V2 DB |
| `start_jarvis_desktop.bat` | Current PySide desktop | YES | `jarvis_desktop.web_app` consuming server | Server/Jarvis boundary | Server/Jarvis boundary | Server/Jarvis DB | Server/Jarvis router | Server/Jarvis memory |
| `jarvis_desktop_launcher.py` | Frozen/current desktop launcher | YES | `jarvis_desktop.web_app` | Same | Same | Same | Same | Same |
| `start_jarvis_desktop_v4.bat` | Historical V4 desktop | LEGACY | `jarvis_desktop.app_v4` | V4-specific UI imports; not the canonical path | Unknown/legacy | Unknown | Unknown | Unknown |
| `JarvisService.__init__` | Creates runtime services | YES | `jarvis_core` | Jarvis SecurityManager | Jarvis AuditLog | TaskManager | CentralOrchestrator | GoldenMemoryManager + V2 |
| `TaskManager.start_scheduler` | Starts background scheduler | YES | Jarvis TaskManager | Injected Jarvis SecurityManager | TaskManager AuditLog | Canonical when base_dir is workspace | Planner/registry | No direct memory owner |
| `server_agent.start_server` voice block | Starts local VoiceService | YES when enabled | Jarvis VoiceService | Service execution boundary | VoiceService/Jarvis AuditLog | No separate task owner | Brain/ModelRouter | Voice session + Jarvis memory as configured |
| Gateway startup | WebSocket/WSS consumer | YES when enabled | Same `DESKTOP_CENTER.service` | Gateway delegates service boundary | Same service audit | Same task manager | Same orchestrator | Same memory |
| `app/golden_ai.py` / `app/main_loop.py` | Root Golden/legacy app path | NOT CURRENT LAUNCH | Root `core` and app modules | Root PermissionManager | Root AuditLogger/category logs | Root data repositories, not Jarvis TaskManager | Root `core.models.ModelRouter` and direct Ollama | Root `core.memory`/data DB |
| Test/benchmark constructors | Isolation and evidence | TEST ONLY | Usually direct `JarvisService`/TaskDatabase | Test fixtures | Test fixtures | `tmp_path` DBs | Mock/direct provider fixtures | Temporary memory DBs |

## Real call graph

```text
start_golden.bat / Studio wrappers
  -> server_agent.py
     -> import-time root compatibility: PermissionManager, ExecutionService, plugins
     -> desktop_center.DESKTOP_CENTER
        -> JarvisService(workspace_root)
           -> SecurityManager
           -> AuditLog(workspace_root/golden_runtime.db)
           -> GoldenMemoryManager(workspace_root/jarvis/golden_memory.db)
           -> Memory V2 on the same memory DB
           -> TaskManager(workspace_root)
              -> TaskDatabase(workspace_root/jarvis/golden_tasks.db)
              -> BackgroundTaskScheduler / Runner / Approvals
           -> ToolRegistry / SkillsRouter / CentralOrchestrator
              -> jarvis_core ModelRouter / provider adapters
           -> ComputerMissionExecutor
```

Consumers:

```text
Web API /api/jarvis/* -> DesktopCenter.service -> JarvisService -> Security -> Tool/Task/Model/Audit
Web legacy /api/chat -> server_agent streaming -> direct provider or Ollama -> root ExecutionService for legacy tools
Desktop web_app -> local/web server -> same JarvisService; it does not own a second Core
Voice startup -> get_voice_service().start(DESKTOP_CENTER.service) -> VoiceService -> Brain/Service -> same boundaries
Gateway -> Gateway(DESKTOP_CENTER.service) -> same service, same DB and same security boundary
Scheduler -> TaskManager.start_scheduler -> TaskDatabase -> ComputerMissionExecutor/handlers
Skills -> CentralOrchestrator.skills -> ToolRegistry -> Jarvis security/tool execution
Computer Use -> ComputerMissionExecutor -> mission/checkpoint DB + Jarvis tools/security
```

## `server_agent.py` role separation

Current roles proven in source:

| Role | Current status | F1 target |
|---|---|---|
| Entrypoint | Active | KEEP as launcher/facade while clients migrate |
| HTTP/SSE transport | Active | KEEP; keep transport-only |
| Orchestrator | Mixed; legacy loop plus Jarvis endpoints | ADAPT behind `CentralOrchestrator`, then remove sovereign decisions |
| Provider router | Mixed; direct Groq/Gemini/Ollama and registration into Jarvis router | ADAPT direct calls into provider adapters, then one router |
| Security layer | Mixed; root ExecutionService and Jarvis SecurityManager | Bridge root requests to Jarvis SecurityManager |
| Tool executor | Mixed; `_execute_tool` direct dispatch and Jarvis `execute_tool` | Keep facade, delegate to Jarvis ToolRegistry |
| Task owner | Facade only for `/api/jarvis/tasks/*`; actual owner is TaskManager | KEEP facade only |
| Memory owner | Facade to Jarvis memory for Jarvis routes; old paths use root memory | Jarvis Memory owner; freeze old path |
| Compatibility facade | Necessary for existing Studio routes | KEEP until every consumer is migrated |

The server must not remain a second sovereign brain. The first safe rule is: no new runtime capability may be added to direct server handlers.

## Root Core trace and disposition

| Root component | Current dependency | Disposition | Reason |
|---|---|---|---|
| `core/permissions` + `core/execution` | Imported at `server_agent` startup; gates legacy write/exec tools | ADAPT_BEHIND_JARVIS_CORE | Root approval mode/event APIs are useful, but one authority is required. |
| `core/audit` | Used by root app/services and agents | ADAPT_BEHIND_JARVIS_CORE | Preserve operational fields while emitting canonical action receipts. |
| `core/models` ModelRouter | Used by `app/golden_ai.py` and app modules | COMPATIBILITY_BRIDGE then LEGACY_FREEZE | Jarvis ModelRouter is active on the Jarvis path. |
| `core/tools` registry/external definitions | Used by root app and external catalog | ADAPT_BEHIND_JARVIS_CORE | Reuse definitions, but register/execute through Jarvis ToolRegistry. |
| `core/browser` | Root browser service exists; Jarvis browser is active in current path | ADAPT_BEHIND_JARVIS_CORE | Preserve stronger read/consent behavior only if parity is proven. |
| `core/documents` | Called directly by server legacy document endpoint | ADAPT_BEHIND_JARVIS_CORE | Keep parser implementation; route authorization/audit through Jarvis. |
| `core/audio` / `core/video` | Called by legacy server endpoints | ADAPT_BEHIND_JARVIS_CORE | Keep pure processing behind controlled tools; no second security owner. |
| `core/vision` | Legacy server endpoint and root video path | PORT_TO_JARVIS_CORE or ADAPT | Compare with `jarvis_core.vision` before moving; freeze duplicate ownership. |
| `core/memory` | Root app scientific memory and `data/golden_ai.db` | LEGACY_FREEZE | Do not merge into Jarvis Memory during F1. Preserve data. |
| `core/project_intelligence` / `core/coding` | Root app capability layer | COMPATIBILITY_BRIDGE | Keep existing sandbox/approval behavior until Jarvis owner is proven. |
| `app/modules` and `app/golden_ai.py` | Old Golden app path | LEGACY_FREEZE | Not the current Jarvis launch path; no deletion. |
| `agents/` | Skeleton/specialist contracts | LEGACY_FREEZE | Future agents attach to Jarvis Core; no development in F1. |

## Jarvis Core trace

Already centralized in the active path:

- runtime service construction in `JarvisService`;
- SecurityManager and confirmation token handling;
- AuditLog with secret/payload sanitization;
- TaskManager, background scheduler, approvals, recovery and mission persistence;
- ToolRegistry and SkillsRouter;
- ComputerMissionExecutor and checkpoint/receipt ownership;
- CentralOrchestrator and ModelRouter integration;
- VoiceService lifecycle and its bridge to Brain/Service;
- DesktopCenter sharing the same service with Web and Gateway.

Not yet exclusive:

- root ExecutionService/PermissionManager;
- root AuditLogger/category audit;
- server direct provider calls and streaming providers;
- root ModelRouter;
- root memory and root app databases;
- legacy direct document/audio/video/vision handlers.

## Security consolidation

### SecurityManager

Location: `studio/golden_ai_studio_web/jarvis_core/security.py`.

Capabilities observed: tool risk/confirmation decisions, public browser read scope, host matching, page barrier checks, Computer Use pre-save scope, confirmation token creation/consumption, and fail-closed confirmation behavior. It is injected into `TaskManager` and is the intended authority for Jarvis tools.

### PermissionManager / ExecutionService

Locations: `core/permissions`, `core/execution`.

Capabilities observed: root permission modes, action authorization, pending requests, grant once/task, execution events, and legacy file/command policy. `server_agent.py` creates these at import time and uses `ExecutionService.authorize_action()` in the legacy `_execute_tool` path.

Decision: do not merge now. Keep root services as an adapter source, then route their approval semantics through Jarvis SecurityManager. Do not keep two independent authorities after migration.

## Security bypass map

These are migration findings, not fixes performed in F1.

| ID | Call path | Action class | Current guard | Canonical guard required | Risk |
|---|---|---|---|---|---|
| SB-001 | `server_agent.api_chat` -> legacy streaming -> `_execute_tool` -> `_check_tool_permission` | write/execute/read legacy tools | Root `ExecutionService`; read set returns directly | `jarvis_core.SecurityManager` + ToolRegistry | HIGH |
| SB-002 | `server_agent._execute_tool` -> `PLUGIN_REGISTRY.execute` for unknown plugin tools | External/plugin action | No Jarvis SecurityManager call; only name-based legacy check | Jarvis tool registration, risk and confirmation | HIGH |
| SB-003 | Legacy server endpoints -> `core.vision`, `core.audio`, `core.video`, `core.documents` | file/media/browser-like reads | Root service-local permissions or none at endpoint | Jarvis tool boundary + AuditLog | MEDIUM/HIGH |
| SB-004 | `app/golden_ai.py` -> `core` services directly | file, command, market, memory and coding actions | Root PermissionManager/Core ToolRegistry | Jarvis boundary if app path remains supported | HIGH if launched |
| SB-005 | `jarvis_core.brain._call_llm` fallback -> direct `ollama.chat` when adapters absent | model invocation | ModelRouter is bypassed in fallback branch | Always execute via canonical ModelRouter adapter | MEDIUM |
| SB-006 | `jarvis_core.streaming.provider_stream` / streaming orchestrators -> direct Groq/OpenRouter/Ollama | streaming model invocation | Provider-specific code, not central router | Router-owned streaming adapter with same policy | MEDIUM |

`/api/jarvis/*`, VoiceService command execution, ComputerMissionExecutor, TaskManager and Gateway service calls are not classified as bypasses when they stay on the Jarvis `execute_tool`/TaskManager boundary.

## Audit consolidation

| Implementation | Storage | Active writers | Classification |
|---|---|---|---|
| `jarvis_core.audit.AuditLog` | `jarvis/golden_runtime.db`, table `jarvis_audit` | JarvisService, TaskManager, Memory manager, tool execution | CANONICAL_ACTION_AUDIT |
| `core.audit.AuditLogger` | Root `logs` JSONL/operational log path | Root services, agents, app Core | LEGACY_OPERATIONAL_AUDIT; bridge later |
| `app/golden_ai.py` category helpers | `data/*audit*.jsonl` and deterministic artifacts | Market/quant/memory/media flows | COMPATIBILITY_AUDIT; preserve evidence, normalize later |
| Task event tables | `golden_tasks.db` | TaskDatabase/scheduler/runner | CANONICAL_TASK_RECEIPT |
| Mission receipts/checkpoints | `golden_tasks.db` | ComputerMissionExecutor | CANONICAL_MISSION_RECEIPT |
| `jarvis_core.security_audit` | diagnostic result objects/reports | security audit checks | SECURITY_DIAGNOSTIC, not action audit |
| Python logging / server prints | process logs/stdout | all layers | OPERATIONAL_LOGGING, not security audit |

Canonical action audit is ready for Jarvis actions. Consolidation is required for legacy routes; debug logs do not need to become AuditLog rows.

## Database inventory

Inspection was read-only using SQLite `mode=ro`. No database was modified.

| Path | Purpose/schema | Readers | Writers | Policy |
|---|---|---|---|---|
| `C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db` | Task schema V5; tasks, background tasks, runs, approvals, missions | Jarvis TaskManager, scheduler, ComputerMissionExecutor | TaskDatabase, scheduler, runner, mission store | ACTIVE_CANONICAL |
| `C:\GoldenAI\jarvis\golden_tasks.db` | Task schema V1; no background task tables | Historical/standalone Jarvis tooling | Standalone TaskManager with root base_dir | ACTIVE_NONCANONICAL_REQUIRES_MIGRATION_PLAN |
| `C:\GoldenAI\jarvis\jarvis\golden_tasks.db` | Task schema V1; nested duplicate | Unknown/test or prior standalone | Unknown historical constructor | UNKNOWN_REQUIRES_INVESTIGATION |
| `C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_memory.db` | Memory schema V1 plus V2 tables | Jarvis GoldenMemoryManager, Memory V2, research/project memory | Jarvis memory manager/V2 migrations | ACTIVE_CANONICAL_MEMORY_CANDIDATE |
| `C:\GoldenAI\jarvis\golden_memory.db` | Memory V1 plus V2 tables | Standalone/legacy Jarvis paths | Standalone memory manager | LEGACY_READ_ONLY until provenance confirmed |
| `C:\GoldenAI\jarvis\jarvis\golden_memory.db` | Nested memory duplicate | Unknown | Unknown historical constructor | UNKNOWN_REQUIRES_INVESTIGATION |
| `C:\GoldenAI\data\jarvis\golden_memory.db` | Memory V1 only | Root data/app path if used | Root/legacy memory services | LEGACY_READ_ONLY |
| `C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_runtime.db` | Jarvis audit table | JarvisService, TaskManager, Memory | AuditLog | ACTIVE_CANONICAL_ACTION_AUDIT |
| `C:\GoldenAI\golden_runtime.db` | Jarvis audit table | Standalone Jarvis path | AuditLog | LEGACY_READ_ONLY pending provenance |
| `C:\GoldenAI\jarvis\golden_runtime.db` | Jarvis audit table | Standalone/legacy path | AuditLog | LEGACY_READ_ONLY pending provenance |
| `C:\GoldenAI\studio\golden_ai_studio_web\golden_runtime.db` | Monitor/signal tables plus `jarvis_audit` | Monitor and Studio legacy paths | `monitor_service`, legacy/runtime services | ACTIVE_NONCANONICAL_RUNTIME_DB |
| `C:\GoldenAI\data\golden_ai.db` | Root Core/App repositories: activity, approvals, coding, experiments, knowledge, market | `core/*`, `app/*` | Root Core/App repositories | LEGACY_READ_ONLY for Jarvis convergence |

### Task DB write-path finding

Production `DesktopCenter` passes the fixed workspace base directory, so the active server resolves the canonical DB. However, `TaskManager(base_dir)` intentionally derives `base_dir/jarvis/golden_tasks.db`, and standalone constructors/tests pass temporary or arbitrary roots. This creates a **relative-to-injected-root creation risk**, not a current active-server switch.

Required future enforcement: central resolver + explicit production dependency injection + startup assertion + warning for noncanonical production roots. Tests must retain temporary DB injection.

## Model/provider ownership

### Canonical path

`jarvis_core.orchestrator.ModelRouter` -> `ProviderAdapter` -> `register_real_adapters()` -> Groq/Gemini/OpenRouter/Ollama/optional OmniRoute. Brain calls the router when adapters are registered.

### Direct or parallel paths

- `server_agent.call_groq_model()` and `call_gemini_model()` call HTTP APIs directly; they are also passed as adapter callbacks during warmup.
- Legacy `server_agent` streaming calls Ollama directly in the old `/api/chat` loop.
- `jarvis_core.brain` calls Ollama directly when no adapters are available.
- `jarvis_core.streaming.provider_stream` and streaming orchestrators call Groq/OpenRouter/Ollama directly.
- Root `core.models.ModelRouter` and `app/golden_ai.py` form a second router/provider path.
- `jarvis_core.memory.v2.research` has direct Tavily/Groq research providers; this is a research-provider interface, not the chat ModelRouter, and should remain a distinct domain adapter.

Target: one chat/model router, with streaming adapters below it. Research providers remain behind `ResearchProvider` and must not become a second general LLM authority.

## Memory ownership

Active Jarvis path:

```text
JarvisService
  -> GoldenMemoryManager(base_dir/jarvis/golden_memory.db)
     -> legacy sessions/episodic/semantic/retrieval
  -> GoldenMemoryEngine(same DB)
     -> V2 memories/entities/relations/projections
  -> LearningEngine / ResearchEngine / ProjectMemoryManager
```

Server Jarvis memory routes delegate to `DESKTOP_CENTER.service`. Voice uses conversation context and can feed the same service/Brain. `server_agent.CONVERSATIONS` and `JarvisService._conversation_histories` are in-memory conversation buffers, not canonical durable memory.

Root `core.memory` and `data/golden_ai.db` belong to the older Golden/App path. They are not to be merged during F1. Memory implementation is explicitly not allowed now; first consolidate ownership and document provenance.

## Protected functionality and compatibility

The following are protected and must remain behaviorally unchanged during later waves:

- Computer Use missions, checkpoints, receipts, stale-target protection, browser read scope, Notepad/Chrome workflows and cross-app handoff.
- Task scheduler, durable runs, claim uniqueness, pause/resume, approvals, retries and condition execution.
- Current DesktopCenter/Web/Gateway shared service path.
- Skills catalog and ToolRegistry contracts.
- VoiceService owner, cancellation, TTS ownership and paused microphone gate.

## Compatibility bridges

| Bridge ID | Old owner | Canonical owner | Callers | Adapter needed | Removal condition |
|---|---|---|---|---|---|
| B-001 | `server_agent._execute_tool` + root ExecutionService | Jarvis ToolRegistry + SecurityManager | `/api/chat`, legacy Studio routes | `LegacyToolFacade` that asks Jarvis security and emits AuditLog | All legacy tool routes delegate to Jarvis registry |
| B-002 | Root PermissionManager/ExecutionService | Jarvis SecurityManager | Server startup and security panel routes | Permission decision/approval adapter | No active route reads root authority |
| B-003 | Root AuditLogger/category audit | Jarvis AuditLog | `app/*`, root services, legacy handlers | Canonical receipt sink retaining operational logs | Root app path frozen or migrated |
| B-004 | Root `core.models.ModelRouter` | Jarvis ModelRouter | `app/golden_ai.py`, app modules | Provider facade translating profiles/policies | Root app no longer launched/owned |
| B-005 | Direct provider streaming modules | Jarvis ModelRouter streaming adapters | Streaming orchestrators and legacy chat | Router-owned stream adapter | All chat/voice streams carry router decision |
| B-006 | Root `core.documents/audio/video/vision` | Jarvis ToolRegistry + service boundaries | Legacy server endpoints | Pure capability adapters with Jarvis guard/audit | Endpoint delegates fully to Jarvis tools |
| B-007 | Root memory/data DB | Jarvis Memory owner | Root app only | Read-only compatibility reader, no new writes | Root app retired or explicitly separated |
| B-008 | Arbitrary `TaskManager(base_dir)` | Canonical task DB resolver | Tests and standalone tools | Production resolver with test injection | Every production constructor asserts canonical path |

## Consolidation waves

### F1 - Design and evidence (this gate)

Completed in this document. No runtime change.

### F2 - Runtime ownership guardrails

Completed as the smallest implementation gate: a **read-only runtime
ownership diagnostic** and canonical path comparison contract, without
changing execution behavior.

Acceptance:

- report the active `JarvisService` identity, base_dir, TaskManager DB path, SecurityManager owner, AuditLog path and ModelRouter owner;
- assert only in diagnostic/test mode that production base_dir maps to the fixed task DB;
- warn, do not migrate, arbitrary standalone DB paths;
- add no second Core and no hardware activity.

Risk: LOW. This is the first gate because it reduces ambiguity and catches DB drift without moving a working capability.

### F2 implementation evidence

F2 was executed from baseline `5acb200` with a single bounded diagnostic
facility: `jarvis_core.runtime_ownership.RuntimeOwnershipDiagnostic`.
The facility is observation-only. It does not open databases, write audit
rows, migrate schemas, switch owners, redirect paths, or repair mismatches.

The active `TaskDatabase` now exposes its requested path, resolved absolute
path, canonical comparison and owner identity. `JarvisService` exposes the
same report through `runtime_ownership_diagnostics()`. The report covers the
canonical Core, SecurityManager, AuditLog, TaskManager, ModelRouter and
existing memory owner, and classifies compatibility, noncanonical and unknown
owners without raising into the runtime.

The canonical task database observed by the diagnostic is:

```text
C:\\GoldenAI\\studio\\golden_ai_studio_web\\jarvis\\golden_tasks.db
```

Absolute noncanonical paths and relative paths were tested in temporary
directories. Relative paths are explicitly reported as dependent on the
injected working root; no database was created by the diagnostic itself. The
inventory of same-name databases was read-only and no existing database was
mutated.

The earlier Windows `WinError 32` was reproduced during cleanup of the Memory
V2 runtime test. Its cause is a non-joined scheduler thread retaining a
SQLite handle after `shutdown(wait=False)`, not a missing delay. The F2 change
is test-only cleanup joining (`wait=True`) so the temporary directory can be
removed deterministically. The production `JarvisService.close()` lifecycle
still uses the existing non-joined shutdown contract and remains a separate
task-lifecycle gate; F2 does not silently change it.

```yaml
RUNTIME_OWNERSHIP_DIAGNOSTIC: READY
CANONICAL_TASK_DB_DETECTED: YES
NONCANONICAL_TASK_DB_DETECTED: YES
RELATIVE_PATH_RISK_REPRODUCED: YES
COMPATIBILITY_OWNER_CLASSIFICATION: PASS
UNKNOWN_OWNER_CLASSIFICATION: PASS
DATABASES_MUTATED: NO
SCHEMA_MIGRATION: NO
WINERROR_32_ROOT_CAUSE_IDENTIFIED: YES
PRODUCTION_LIFECYCLE_FIX: DEFERRED_TO_SEPARATE_GATE
```

Validation evidence for this gate:

```yaml
TARGETED_REGRESSION: 104 passed
SUBTESTS: 3 passed
PY_COMPILE: PASS
GIT_DIFF_CHECK: PASS
HARDWARE_OR_EXTERNAL_PROVIDER_TESTS: NOT_RUN
DEVICE_REGISTRY_TOUCHED: NO
```

No ownership convergence, security bypass repair, audit consolidation,
model-router consolidation, memory migration, device-registry change or
hardware activity was performed in F2.

### F2.1 task lifecycle evidence

F2.1 completed with an explicit two-phase lifecycle for the owned scheduler
and runner:

```yaml
REQUEST_STOP: TaskManager.request_shutdown() / shutdown(wait=False)
FINAL_JOIN_AND_CLOSE: TaskManager.finalize_shutdown() / shutdown(wait=True)
```

The scheduler no longer discards a live thread reference after a timed join.
The final path joins the worker without a timeout, then shuts down the task
runner pool with `wait=True`. `JarvisService.close()` now uses that final path.
Repeated finalization is idempotent. The nonblocking request path remains
available for callers that intentionally cannot wait immediately.

The F2 `WinError 32` cleanup failure was fixed at its ownership boundary:
the final shutdown joins the scheduler before the temporary/runtime directory
is removed. No sleep, delete retry, forced garbage collection, ignored error
or process termination was introduced. Focused tests verified normal
shutdown, nonblocking request semantics, final join, no live scheduler worker,
double shutdown, scheduler restart, and immediate temporary DB cleanup.

```yaml
F2_1_STATUS: PASS
THREAD_JOIN_CONFIRMED: YES
SQLITE_RELEASE_CONFIRMED: YES
DOUBLE_SHUTDOWN: PASS
ZOMBIE_WORKERS: NO
SCHEDULER_BEHAVIOR_CHANGED: NO
```

### F3 - Security convergence

F3 completed a bounded migration through
`jarvis_core.security_compatibility.LegacySecurityBridge`. The legacy
`server_agent` path now delegates the exact `open_file` and `delete_file`
contracts to the existing `JarvisService.execute_tool()` boundary. Decision,
single-use confirmation, execution and action audit therefore use the
canonical `SecurityManager` and `AuditLog`. Canonical requests are marked with
the `jarvis:` approval prefix so the existing security endpoints can route
them without changing root approval records; task-scoped approval is rejected
for this single-use contract rather than silently weakened.

The bridge fails closed when the canonical service is unavailable or when a
legacy call contains incompatible arguments. Unsupported legacy tools remain
on the compatibility path and are explicitly deferred. No plugin, provider,
root-app, document/media endpoint or ModelRouter migration was inferred from
this bounded proof.

```yaml
F3_STATUS: PASS_WITH_RESTRICTIONS
CANONICAL_SECURITY: jarvis_core.security.SecurityManager
PERMISSION_MANAGER_STATUS: COMPATIBILITY_RETAINED_FOR_UNMIGRATED_PATHS
SECURITY_BYPASSES_START: 6
SECURITY_BYPASSES_MIGRATED: 1_BOUNDED_SB001_SUBSET
SECURITY_BYPASSES_DEFERRED: SB001_REMAINDER, SB002, SB003
SECURITY_BYPASSES_INACTIVE_OR_OUT_OF_SCOPE: SB004, SB005, SB006
APPROVAL_SEMANTICS_PRESERVED: YES
READ_ONLY_SEMANTICS_PRESERVED: YES
DUPLICATE_SIDE_EFFECTS: NO
```

Focused security validation passed: `88 passed`. No external provider,
hardware or voice test was run.

### F4 - Audit convergence

F4 completed the audit checkpoint for the migrated F3 paths without adding a
second audit framework. `JarvisService.execute_tool()` already emits the
canonical `jarvis_core.audit.AuditLog` receipt after the SecurityManager
decision; the compatibility bridge therefore reuses that receipt path. Root
`core.audit.AuditLogger`, app category files and operational logs remain
compatibility/legacy sources for later migration and were not rewritten.

Focused tests verified one canonical receipt for a migrated read action,
single-use approval plus one execution receipt for a migrated mutation, and
redaction of API keys, tokens and authorization values. Request and execution
receipts remain distinct semantic events; duplicate approval does not execute
again or create a second execution receipt.

```yaml
F4_STATUS: PASS_WITH_RESTRICTIONS
CANONICAL_AUDIT: jarvis_core.audit.AuditLog
LEGACY_AUDIT_PATHS_START: 3_CLASSES
LEGACY_AUDIT_PATHS_MIGRATED: 0_GLOBAL_REWRITE; F3_MIGRATED_PATHS_USE_CANONICAL
LEGACY_AUDIT_PATHS_DEFERRED: root_core, app_category_audit, operational_logs
DUPLICATE_AUDIT_EVENTS: NO
TASK_RECEIPTS_PRESERVED: YES
MISSION_RECEIPTS_PRESERVED: YES
SECRET_SAFE: YES
```

No historical audit data was migrated, deleted or rewritten.

### F5 - Task DB enforcement

F5 completed the canonical task-database governance layer through the single
resolver `jarvis_core.task_manager.paths.resolve_task_database_path()`.
`DesktopCenter` is the production entrypoint and requests
`runtime_mode="production"`, which resolves only to:

```text
C:\\GoldenAI\\studio\\golden_ai_studio_web\\jarvis\\golden_tasks.db
```

An explicitly supplied noncanonical production path is rejected before
`TaskDatabase` opens or creates SQLite. Isolated test databases use
`runtime_mode="test"`; legacy/standalone callers remain classified as
compatibility and are not silently redirected. The existing runtime
ownership diagnostic now reports the runtime classification alongside the
resolved path.

No database was migrated, opened for governance-only path tests, modified,
deleted, renamed, copied or redirected. F5 validation passed: `78 passed`;
`py_compile` and the protected task/scheduler, Computer Use and ownership
tests passed.

```yaml
F5_STATUS: PASS
CANONICAL_TASK_DB: C:\\GoldenAI\\studio\\golden_ai_studio_web\\jarvis\\golden_tasks.db
CENTRAL_PATH_OWNER: jarvis_core.task_manager.paths.resolve_task_database_path
CWD_INDEPENDENT: YES
EXPLICIT_TEST_DB_SUPPORTED: YES
ACCIDENTAL_NONCANONICAL_PRODUCTION_DB_BLOCKED: YES
LEGACY_DATABASES_PRESERVED: YES
DATABASE_MIGRATION: NO
```

### F6 - ModelRouter convergence

Move direct chat/streaming calls behind router adapters. Keep research providers domain-specific. Validate fallback, SECRET policy, streaming and no duplicate provider invocation.

### F7 - Memory ownership cleanup

Only after task/security/audit ownership is stable: freeze root memory writes, document read compatibility, and propose a separate migration only if required. No Memory/RAG implementation in F1/F2.

### F7.1 - SQLite lifecycle checkpoint

F7.1 found that the active service shutdown was deterministic for the
TaskManager only after its final join, while the Brain shadow-retrieval
executor could still hold a context-managed SQLite connection during temporary
workspace cleanup. The bounded production fix is:

- `JarvisService.close()` remains the owner of scheduler, runner and matching
  global Brain shutdown;
- `TaskManager.shutdown(wait=False)` remains a non-blocking stop request, while
  `finalize_shutdown()` joins owned workers;
- `JarvisBrain.close()` now joins the shadow retrieval executor before the
  memory workspace can be removed;
- no cleanup retry, `PermissionError` suppression, process termination,
  migration or database deletion was added.

The F7.1 regression holds an owned shadow worker until close is entered,
verifies that close waits for it, asserts scheduler/worker termination, checks
idempotent shutdown, and lets `TemporaryDirectory` perform the actual cleanup.
F7.2 provenance/parity and F7.3 canonical-boundary decisions remain separate
gates.

### F7.2 - Provenance and parity checkpoint

The memory systems were audited read-only before any boundary change:

| System | Active role | Provenance/lifecycle | Decision |
|---|---|---|---|
| `GoldenMemoryManager` / V1 tables | Existing service compatibility tools, sessions, episodic and semantic records | `MemorySource`, `source_id`, `session_id`, namespace, confidence, active flag, importance/access count | Preserve; adapt at the boundary |
| `GoldenMemoryEngine` / V2 tables | Additive canonical candidate on the active Jarvis DB | `source_type`, `source_ref`, `source_timestamp`, confidence/basis, privacy, project, metadata, content hash, version and status | Canonical store for selected callers |
| `LegacyMemoryAdapter` | Read-only view of legacy records as V2 records | Explicit lossy mapping; no physical write or migration | Compatibility only |
| `ResearchEngine` / learning | Research evidence and promoted knowledge | provider/source URL, retrieval/fetched timestamps, trust, candidate state and evidence-backed promotion | Ready behind V2 promotion path |

Parity is therefore `BOUNDED`, not claimed as lossless. V2 supports durable
provenance, privacy, confidence, source references, temporal source timestamps,
content identity, versioning, supersession, dispute and archival. Legacy
`importance`, `access_count`, session lifecycle details and namespace semantics
do not have a one-to-one V2 field; they remain compatibility metadata or
deferred adapters. Conversation buffers are volatile context, not canonical
memory.

The current knowledge lifecycle is explicit: active records may be updated,
deduplicated, disputed, superseded, archived or logically deleted while
historical versions and consolidation evidence remain inspectable. Research
records retain source/trust/freshness evidence before promotion. SECRET is
rejected by the V2 memory contract and is not projected to the local vault.

```yaml
F7_2_STATUS: PASS_WITH_RESTRICTIONS
MEMORY_SYSTEMS_AUDITED: LEGACY_V1,V2,LEGACY_ADAPTER,RESEARCH
CANONICAL_PARITY: BOUNDED
PROVENANCE_CONTRACT: PASS
KNOWLEDGE_LIFECYCLE: PASS
RESEARCH_MEMORY_READY: YES
DESTRUCTIVE_MIGRATION_REQUIRED: NO
LEGACY_DATABASES_UNTOUCHED: YES
```

## Batch D checkpoints

### D1 - Memory-first retrieval

`CanonicalMemoryBoundary.retrieve()` now reuses the existing V2 Hybrid
Retrieval path before normal reasoning. Results remain context/evidence rather
than authority and carry source type/reference/timestamp, trust, privacy,
status and explicit freshness. Current/project-relevant records are ranked
ahead of explicit stale or superseded history; failure returns bounded empty
context and Brain falls back to the legacy context path without blocking Core.
Normal research checks promoted canonical research first. Time-sensitive
queries require explicit `CURRENT` freshness before reuse; otherwise the
existing provider path runs.

```yaml
D1_STATUS: PASS
RETRIEVAL_OWNER: CanonicalMemoryBoundary -> GoldenMemoryEngine.hybrid_search
HYBRID_RETRIEVAL_REUSED: YES
PROJECT_AWARE: YES
PROVENANCE_AWARE: YES
FRESHNESS_AWARE: YES
SUPERSESSION_AWARE: YES
RESEARCH_REUSE_READY: YES_BOUNDED
FAILURE_ISOLATION: PASS
```

### D2 - Cumulative knowledge learning

The existing candidate detector, project memory and research learning
pipeline remain the only learning path. A candidate is now promotable only
with an explicit `promote` verdict; neutral or rejected observations are not
persisted. V2 consolidation preserves user-explicit overrides, records
contradictions/disputes instead of silently overwriting, keeps versions and
supports research/project/decision/lesson knowledge through the existing
canonical store.

```yaml
D2_STATUS: PASS
CANDIDATE_LIFECYCLE: EXPLICIT_VERDICT_REQUIRED
USER_OVERRIDE_PROTECTION: PASS
CONFLICT_HISTORY: PRESERVED
SECRET_PERSISTENCE: BLOCKED
DUPLICATE_PERSISTENCE: PREVENTED
```


### F7.3 - Canonical memory boundary checkpoint

`jarvis_core.memory.boundary.CanonicalMemoryBoundary` is now the boundary for
the selected Jarvis service memory tools. When V2 is initialized, these calls
use `GoldenMemoryEngine` exclusively and translate its records to the stable
service response contract. There is no V1/V2 dual-write. If V2 cannot be
initialized, the same boundary reports `legacy_compatibility` and delegates to
the existing manager; this is an explicit compatibility fallback, not a
second active writer.

Migrated callers are `memory_search`, `memory_remember` and `memory_recent` on
`JarvisService`. Brain's legacy context reader, root Golden/App memory paths,
and unverified external callers remain deferred because their session,
importance and namespace semantics need a separately tested adapter. The
active Jarvis writers are known; no unknown writer was assumed safe. Project
memory and research learning already write through V2 and remain unchanged.

```yaml
F7_3_STATUS: PASS_WITH_RESTRICTIONS
CANONICAL_BOUNDARY: CanonicalMemoryBoundary
CANONICAL_STORE: GoldenMemoryEngine_V2
ACTIVE_WRITERS_MIGRATED: JarvisService.memory_search,memory_remember,memory_recent
ACTIVE_WRITERS_DEFERRED: Brain_legacy_context,root_Golden_App,external_legacy_callers
UNKNOWN_WRITERS: NONE_ON_ACTIVE_JARVIS_PATH
DUPLICATE_WRITES: NO
LEGACY_COMPATIBILITY: EXPLICIT_FALLBACK
PROJECT_MEMORY: V2
RESEARCH_MEMORY: V2
SECURITY_CLASSIFICATION: V2_DataClassification
LEGACY_DATABASES_UNTOUCHED: YES
```

### F8 - Optional downstream capabilities

MCP, Agents, Finance, Mobile, personal integrations and real trading remain downstream. They attach to canonical Core only after the foundational waves pass.

## Acceptance and restrictions

## Targeted validation evidence

No hardware or external service tests were run. The protected non-hardware regression set excluding the known Memory V2 lifecycle case passed:

```yaml
SECURITY_SCHEDULER_COMPUTERUSE_ROUTER: 89 passed
SUBTESTS: 3 passed
MEMORY_V2_RUNTIME: 1 failed during TemporaryDirectory cleanup
```

The earlier `WinError 32` was caused by cleanup racing an owned shadow worker
and by test teardown using only the non-blocking shutdown request. F7.1 fixes
the production owner path and aligns affected tests with `JarvisService.close()`
or an explicit final join. The old voice conversation failures remain outside
this gate and are reproduced independently in their own suite.

```yaml
ENTRYPOINTS_MAPPED: YES
CORE_OWNERS_MAPPED: YES
SECURITY_OWNERS_MAPPED: YES
AUDIT_OWNERS_MAPPED: YES
TASK_DB_PATHS_MAPPED: YES
PROVIDER_OWNERS_MAPPED: YES
MEMORY_OWNERS_MAPPED: YES
SECURITY_BYPASSES_IDENTIFIED: YES
COMPATIBILITY_BRIDGES_DESIGNED: YES
MIGRATION_WAVES_ORDERED: YES
FIRST_IMPLEMENTATION_GATE_SELECTED: YES
PRODUCTION_CODE_CHANGED: YES_F7_1_ONLY
DATABASES_MODIFIED: NO
```

No migration, deletion, rename, move, merge, copy, vacuum or repair was performed. No dependencies, models, accounts, credentials, microphone, speaker, camera, MT5 or device registry were touched.
