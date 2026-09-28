# Jarvis Capability Platform: Batch E E1 Audit

Baseline: `9c231d4`

## E1 status

`PASS_WITH_RESTRICTIONS`

The active Jarvis web runtime has one clear execution path. Skills and
external providers are capability metadata/adapters; they are not additional
brains or authorities.

## Ownership matrix

| Concern | Canonical owner | Classification | Evidence |
|---|---|---|---|
| Skill discovery and routing | `jarvis_core.orchestrator.skills_router.SkillsRouter` | `KEEP_CANONICAL` | Builds the route-to-tool skill catalog from the active registry. |
| Tool registration and schemas | `jarvis_core.registry.ToolRegistry` plus `jarvis_core.models.Tool` | `KEEP_CANONICAL` | Rejects duplicate names, exposes LLM schemas, validates handler/schema/risk alignment. |
| Tool execution boundary | `JarvisService.execute_tool` | `KEEP_CANONICAL` | Resolves the registered tool, validates arguments, checks cancellation and dispatches with a bounded timeout. |
| Security authority | `jarvis_core.security.SecurityManager` | `KEEP_CANONICAL` | Owns allow/deny/confirmation decisions and single-use expiring confirmation tokens. |
| Audit authority | `jarvis_core.audit.AuditLog` | `KEEP_CANONICAL` | Records accepted, rejected, confirmed and failed tool paths with payload redaction. |
| Tasks and scheduler | `jarvis_core.task_manager.TaskManager` | `KEEP_CANONICAL` | Owns task lifecycle, background execution and scheduler state. |
| Memory boundary | `jarvis_core.memory.boundary.CanonicalMemoryBoundary` | `KEEP_CANONICAL` | Keeps V2 SQLite canonical and controls retrieval/promotion boundaries. |
| Computer Use/browser | Internal `Tool` entries and `JarvisService.execute_tool` | `ADAPT` | Existing tools already pass through the canonical security/audit path. |
| Legacy plugins | `plugins.plugin_loader.PluginRegistry` | `COMPATIBILITY` / `LEGACY_FREEZE` | Mature isolated plugin kernel used by `server_agent`; not wired as a second active Jarvis web executor. |
| External tool metadata | `core.tools.external.ExternalToolRegistry` | `COMPATIBILITY` / `LEGACY_FREEZE` | Permission-aware metadata/adapter layer; no direct execution and not the active web registry. |
| MCP | None currently | `NOT_STARTED` | No MCP client/server/configuration or MCP runtime dependency is present. |

## Capability execution trace

The active path is:

```text
request
  -> JarvisService / Brain plan
  -> ToolRegistry lookup and schema validation
  -> SecurityManager decision
  -> optional single-use confirmation
  -> JarvisService.execute_tool
  -> bounded handler execution
  -> postcondition verification
  -> AuditLog.add with redaction
  -> structured result / synthesis
```

The registry owns discovery, registration and schema presentation. It does not
grant permission. `Tool` metadata describes risk, timeout, confirmation,
response policy and browser authorization scope; authority remains with
`SecurityManager`.

The execution path handles unknown tools, invalid arguments, denied actions,
cancellation, handler exceptions and timeouts. Mutation-capable paths retain
the existing confirmation semantics. Audit occurs for accepted and rejected
paths, with sensitive keys and binary payloads redacted.

Computer Use and browser tools are ordinary entries in the same registry. They
do not own a second SecurityManager, ToolRegistry or execution loop.

`server_agent.py` is a compatibility surface: it initializes the legacy
`PermissionManager`, `PluginRegistry` and `ExecutionService` for the older
agent server. It must not be expanded into the canonical Jarvis Core path.

## Duplication audit

| Surface | Decision | Reason |
|---|---|---|
| `ToolRegistry` vs `ExternalToolRegistry` | `KEEP_CANONICAL` + `LEGACY_FREEZE` | The former is the active Jarvis runtime owner; the latter remains a compatibility metadata/adapter API. |
| `SkillsRouter` vs plugin registry | `KEEP_CANONICAL` + `COMPATIBILITY` | Skills route active capabilities; plugins remain providers behind their legacy boundary. |
| `SecurityManager` vs `PermissionManager` | `KEEP_CANONICAL` + `LEGACY_FREEZE` | `SecurityManager` owns Jarvis web execution; `PermissionManager` remains for `server_agent`/core compatibility. |
| AuditLog vs legacy audit surfaces | `KEEP_CANONICAL` for Jarvis web | New capability execution must use the Jarvis `AuditLog`; legacy paths are not silently merged. |
| MCP registry/executor | `NONE` | Must be introduced as a provider adapter, never as a competing registry or authority. |

## MCP donor/specialist audit

No local MCP SDK is installed (`mcp` and `fastmcp` are absent), and no
configured MCP server was found. No external MCP server was contacted.

The current official MCP material was consulted read-only. The current
specification describes tools as provider-exposed executable capabilities and
documents discovery/listing, invocation, schema validation, cancellation,
health/error handling and security boundaries. The specification has evolved
from the legacy initialize/session lifecycle to a stateless 2026-07-28 model;
the implementation gate must therefore pin one protocol revision instead of
mixing lifecycle models. The first local fixture should use the smallest
justified transport, explicit server configuration, deterministic tool
listing, namespaced identities and bounded calls. Resources/prompts/tasks are
out of scope until the core tool path is proven.

Reference material:

- Model Context Protocol specification overview: <https://modelcontextprotocol.io/specification/draft/server/index>
- Official specification changelog and lifecycle changes: <https://modelcontextprotocol.io/specification/draft/changelog>
- Official 2026-07-28 specification release notes: <https://blog.modelcontextprotocol.io/posts/2026-07-28/>

## E1 checkpoint

```yaml
E1_STATUS: PASS_WITH_RESTRICTIONS
SKILLS_STATUS: WORKING_VALIDATED
MCP_START_STATUS: NOT_STARTED
CANONICAL_SKILL_REGISTRY: SkillsRouter
CANONICAL_TOOL_BOUNDARY: JarvisService.execute_tool -> ToolRegistry
DUPLICATE_REGISTRIES: ToolRegistry(active),PluginRegistry(compatibility),ExternalToolRegistry(compatibility)
DONORS_SPECIALISTS_AUDITED: OFFICIAL_MCP_SPECIFICATION_READ_ONLY
MCP_ROLE: EXPLICITLY_CONFIGURED_CAPABILITY_PROVIDER
PLUGIN_ROLE: LEGACY_COMPATIBILITY_PROVIDER
CONNECTOR_ROLE: FUTURE_PROVIDER_ADAPTER_BEHIND_CANONICAL_BOUNDARY
SECURITY_OWNER: SecurityManager
AUDIT_OWNER: AuditLog
MEMORY_OWNER: CanonicalMemoryBoundary
ARBITRARY_MCP_AUTO_TRUST: NO
EXTERNAL_MCP_CONTACTED: NO
```

The restriction is intentional: legacy compatibility paths remain separate
until a later adapter gate proves ownership and regression coverage. E2 may
continue because the active execution authority is unambiguous.

## E2 checkpoint

The existing `Tool` and `ToolRegistry` were adapted instead of introducing a
second capability registry. `Tool` now carries provider, side-effect,
security/approval, availability, health and provenance metadata. The registry
exposes a normalized capability descriptor and catalog while keeping the
existing LLM schema and duplicate-name rejection behavior.

The descriptor is governance metadata only. It does not grant permission,
change confirmation policy or bypass the `SecurityManager`. Invocation still
enters `JarvisService.execute_tool`, which performs validation, cancellation,
security decision, bounded dispatch, postcondition verification and one
canonical audit receipt.

```yaml
E2_STATUS: PASS
BOUNDARY_OWNER: JarvisService.execute_tool
REGISTRY_OWNER: jarvis_core.registry.ToolRegistry
SECURITY_OWNER: jarvis_core.security.SecurityManager
AUDIT_OWNER: jarvis_core.audit.AuditLog
SIDE_EFFECT_CLASSIFICATION: NORMALIZED_METADATA_ONLY
EXISTING_SKILLS_PRESERVED: YES
LEGACY_COMPATIBILITY: PRESERVED
DUPLICATE_EXECUTION: NOT_OBSERVED
TESTS: 26_PASSED_22_SUBTESTS
```
