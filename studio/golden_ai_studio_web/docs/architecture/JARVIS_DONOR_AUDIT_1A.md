# JARVIS Donor Audit 1A

Status: `IN_PROGRESS` (audit phase complete; no donor integration authorized)
Date: 2026-09-26
Scope: read-only comparison of Golden/JARVIS, OpenClaw, and Hermes Agent.

## Executive Summary

This audit reviewed the canonical OpenClaw and Hermes Agent repositories and
compared their extension, skills, MCP, browser, provider, scheduling, and
security patterns with the existing Golden runtime. The result is a
reuse-first recommendation: keep the Golden control plane and security
boundaries, adapt narrow manifest/discovery ideas behind a Jarvis-owned
contract, and use donor behavior as reference material where the trust model
or lifecycle is materially different.

No donor package was installed in Golden. No donor source was copied into
Golden. No runtime Python/JavaScript, dependency manifest, database,
`device_registry.json`, scheduler, memory, Computer Use, MT5, or provider
implementation was changed by this audit.

The donor repositories are MIT licensed at their roots, but that does not
clear third-party code, bundled skills, provider SDKs, or plugin-local notices
for future code porting. A future port must pass a file-level license and
supply-chain review.

## Repository Verification

| Donor | Canonical repository | Owner | Default branch | Verified HEAD | License | Activity evidence |
| --- | --- | --- | --- | --- | --- | --- |
| OpenClaw | https://github.com/openclaw/openclaw | `openclaw` | `main` | `374f893b896c5445598d47541a4cc6b8d4eb2762` | MIT | HEAD commit dated 2026-09-26; `fix: stop compaction recovery when a run times out (#159105)` |
| Hermes Agent | https://github.com/NousResearch/hermes-agent | `NousResearch` | `main` | `802ae8544b59f62c97468ed31b55f417ba12e9f2` | MIT | HEAD commit dated 2026-09-26; `test(docker): a mounted host dir follows the fallback mount` |

Verification used `git ls-remote --symref`, shallow clones outside Golden, the
root `LICENSE` files, and package metadata. The clones are at:

- `C:\JarvisDonors\openclaw`
- `C:\JarvisDonors\hermes-agent`

Official references: [OpenClaw repository](https://github.com/openclaw/openclaw),
[OpenClaw documentation](https://docs.openclaw.ai/), [Hermes Agent repository](https://github.com/NousResearch/hermes-agent),
and [Hermes Agent documentation](https://hermes-agent.nousresearch.com/docs/).

## Jarvis Current Architecture

The audit treated these Golden files as the current source of truth:

| Boundary | Golden implementation | Finding |
| --- | --- | --- |
| Tool registration and JSON schema | `jarvis_core/registry.py` | `ToolRegistry` owns registration, duplicate rejection, LLM catalog, risk validation, confirmation metadata, and handler/schema checks. |
| Runtime composition | `jarvis_core/service.py` | `JarvisService` composes the registry, `SecurityManager`, `AuditLog`, memory, orchestrator, browser session, and `TaskManager` rather than starting parallel cores. |
| Security | `jarvis_core/security.py` | `SecurityManager` owns allow/confirm/deny decisions, public read-only browser scope, Computer Use pre-save scope, and expiring confirmation tokens. |
| Audit | `jarvis_core/audit.py` | SQLite `AuditLog` sanitizes sensitive keys and large/binary payloads before persistence. |
| Durable tasks | `jarvis_core/task_manager/database.py` | `TaskDatabase` persists background tasks, runs, approvals, missions, events, and recovery state. |
| Scheduler | `jarvis_core/task_manager/scheduler.py` | One canonical `BackgroundTaskScheduler` performs claims, leases, recovery, recurrence, condition checks, and execution dispatch. |
| Read-only operations view | `jarvis_core/task_manager/control_center.py` | `BackgroundControlCenter` exposes task/run/approval snapshots without becoming a second scheduler or executor. |
| Mission state | `jarvis_core/computer_use_mission.py` | `MissionContext` carries mission-scoped state, authorization, provenance, and checkpoints. |
| Browser | `jarvis_core/browser.py` | `BrowserSession`, navigation barriers, public URL policy, page provenance, and stale element references already define the Golden browser boundary. |
| Model routing | `jarvis_core/orchestrator/model_router.py` | `ModelRouter` owns provider selection, classification-aware routing, cooldown, timeout, fallback, and attempt telemetry. |
| Memory | `jarvis_core/memory/` | Legacy and V2 memory engines coexist under the Golden manager and are not replaceable by a donor memory subsystem in this phase. |

Current implementation history relevant to this audit includes `45955ab`
(`docs: close Computer Use 7D`), `d08c288` (`fix: execute condition tasks
without computer use`), and `a4fcf00` (`feat: add read-only background control
center`).

## OpenClaw Audit

Reviewed source and docs include:

- `docs/tools/skills.md`, `docs/tools/creating-skills.md`, and
  `docs/tools/skills-config.md`;
- `docs/plugins/architecture.md`, SDK entrypoint and tool-policy/sandbox docs;
- `docs/tools/tool-search.md`;
- gateway sandbox, device/node pairing, RPC approval, and security docs;
- browser security docs and plugin examples under `extensions/`;
- root `package.json`, `pnpm-workspace.yaml`, `LICENSE`, and
  `THIRD_PARTY_NOTICES.md`.

Material findings:

1. Skills are directory contracts centered on `SKILL.md`, YAML frontmatter,
   filtered discovery, precedence, collision reporting, allowlists, and
   environment/binary eligibility. Explicit skill invocation is distinct from
   host authorization.
2. Plugin capabilities are registered through a public API such as provider,
   speech, web search, channel, or gateway discovery registration. Plugin
   shape is inspected from actual registration behavior, not only static
   metadata.
3. Tool search reduces the model-visible tool surface, but it is a context
   optimization and must not be treated as a security authorization boundary.
4. Gateway, node pairing, device tokens, sandbox policy, and operator approvals
   form a distributed control plane. That is broader than the single-core
   Golden trust model and should not be embedded by copying Gateway code.
5. Skills Workshop/ClawHub provide an ingestion lifecycle. Automatic remote
   skill installation or update is explicitly outside the current Golden
   security envelope.

## Hermes Audit

Reviewed source and docs include:

- `plugins/plugin_loader.py`, `plugins/*/plugin.yaml`, and
  `hermes_cli/agent_plugins.py`;
- `hermes_cli/agent_import.py` and related import tests;
- `agent/transports/hermes_tools_mcp_server.py`;
- `agent/tool_guardrails.py`, `agent/tool_executor.py`, `agent/skill_utils.py`;
- `cron/jobs.py`, cron execution/incident/delivery modules, and cron tests;
- MCP E2E tests under `tests/e2e/core/mcp_plugins/`;
- `pyproject.toml`, `uv.lock`, and the root `LICENSE`.

Material findings:

1. Hermes has a real MCP lifecycle with stdio and streamable HTTP paths,
   tool discovery, tool filtering, trust tiers, and approval behavior.
2. Its conformance tests are valuable negative-security evidence: on an
   untrusted server, a `readOnlyHint` tool may be allowed while a destructive
   tool is refused before RPC. The tests also cover argument normalization,
   401 recovery, crash isolation, and the rule that an uncertain write-capable
   call is not replayed.
3. Plugin loading is convention-based around `plugin.yaml` and loader helpers.
   That is useful as a design reference, but it is not a drop-in contract for
   Golden's Python runtime or its existing SecurityManager.
4. Hermes cron has durable execution records, profile/workdir isolation,
   delivery, incident deduplication, and restart behavior. Golden already has
   its own canonical scheduler and durable task schema; importing a second
   scheduler would violate single-core invariants.
5. Hermes provider and credential abstractions are broad and dependency-heavy.
   Golden's ModelRouter and provider policy are already the authoritative
   routing boundary.
6. `pyproject.toml` uses exact-pinned core dependencies and optional provider
   extras. This is a useful supply-chain practice, not a reason to import the
   Hermes dependency graph.

## Component Matrix

Classification is deliberately applied to the component as a future reuse
decision, not as permission to integrate it now.

| # | Component/pattern | Donor evidence | Golden boundary | Decision | Rationale |
| ---: | --- | --- | --- | --- | --- |
| 1 | Tool registry and risk schema | OpenClaw plugin/tool model; Hermes tool executor | `jarvis_core/registry.py` | KEEP_OURS | Existing registry is small, explicit, and coupled to Golden risk metadata. |
| 2 | Security and confirmation | OpenClaw approvals/sandbox; Hermes guardrails | `jarvis_core/security.py` | KEEP_OURS | Golden owns authorization and confirmation tokens; donor policy cannot bypass it. |
| 3 | Audit and redaction | Donor security/audit patterns | `jarvis_core/audit.py` | KEEP_OURS | Existing sanitization and SQLite audit are already runtime contracts. |
| 4 | Durable task store | OpenClaw/Hermes durable jobs | `task_manager/database.py` | KEEP_OURS | Golden schema and recovery are canonical. |
| 5 | Scheduler | OpenClaw automation; Hermes cron | `task_manager/scheduler.py` | KEEP_OURS | A second scheduler would create duplicate claims and runs. |
| 6 | Mission context/checkpoints | Donor session/job state patterns | `computer_use_mission.py` | KEEP_OURS | Mission authorization and provenance are Golden-specific. |
| 7 | Computer Use safety | OpenClaw nodes/browser approvals | `computer_use_mission.py`, tools | KEEP_OURS | Golden has tested Windows focus, stale target, save, and user-activity gates. |
| 8 | Browser public-read boundary | OpenClaw browser/security docs | `browser.py`, `security.py` | KEEP_OURS | Existing URL, barrier, provenance, and stale-reference controls are stronger fit. |
| 9 | Model routing/providers | OpenClaw provider plugins; Hermes providers | `orchestrator/model_router.py` | KEEP_OURS | Existing policy covers secret/local, vision, quality, fast, fallback, and cooldown. |
| 10 | `SKILL.md` manifest concept | OpenClaw skills docs; Hermes skills catalog | future extension package | ADAPT | Adopt a narrow declarative manifest after Jarvis permission validation. |
| 11 | Skill precedence and eligibility | OpenClaw loading order and gating | future skill catalog | ADAPT | Useful deterministic discovery; do not adopt remote install or host auth assumptions. |
| 12 | Tool-search/context reduction | OpenClaw `docs/tools/tool-search.md`; Hermes tool search bridge | `ToolRegistry.get_llm_tools` | ADAPT | Reduce prompt surface while retaining registry/security as authority. |
| 13 | MCP trust/read-only hints | Hermes MCP E2E conformance | future MCP adapter | ADAPT | Use as input to a Jarvis policy decision, never as sole authorization. |
| 14 | MCP stdio/HTTP reconnect semantics | Hermes MCP transport tests | future MCP adapter | ADAPT | Adopt bounded failure/reconnect/no-unsafe-replay rules. |
| 15 | Plugin manifest/lifecycle | OpenClaw plugin capabilities; Hermes `plugin.yaml` | future extension package | ADAPT | Adapt lifecycle fields, but load only through Jarvis-owned gates. |
| 16 | Immutable skill revision/provenance | OpenClaw managed library | future skill store | ADAPT | Revision hash and provenance are useful before any managed catalog exists. |
| 17 | Jarvis extension contract | Neither donor is a Golden contract | new design document | REIMPLEMENT_PATTERN | Define Jarvis-owned name, version, capabilities, permissions, schemas, and teardown. |
| 18 | MCP registry/adapter | Hermes transport and filtering | new Jarvis adapter | REIMPLEMENT_PATTERN | Keep MCP external and normalized into ToolRegistry/SecurityManager. |
| 19 | Plugin loader isolation | OpenClaw plugin SDK; Hermes loader | new loader boundary | REIMPLEMENT_PATTERN | Separate discovery, validation, import, registration, and rollback. |
| 20 | Provenance/license gate | OpenClaw notices; Hermes pinned deps | extension validation | REIMPLEMENT_PATTERN | Require source, license, digest, dependency, and maintainer metadata. |
| 21 | OpenClaw Gateway/nodes/device plane | OpenClaw architecture and pairing docs | single Jarvis core | REFERENCE_ONLY | Distributed trust domain is useful reference, not a Golden subsystem. |
| 22 | OpenClaw browser plugin | OpenClaw browser docs/plugins | `BrowserSession` | REFERENCE_ONLY | Compare capabilities only; preserve Golden browser safety and provenance. |
| 23 | Hermes cron/delivery/incident model | `cron/` and tests | canonical scheduler | REFERENCE_ONLY | Useful future UX ideas, but no scheduler duplication. |
| 24 | Hermes agent import ecosystem | `hermes_cli/agent_import.py` | future migration tooling | REFERENCE_ONLY | Migration is a later, explicit operation with license and secret review. |
| 25 | ClawHub/remote skill ingestion | OpenClaw skills workshop/ClawHub | future controlled catalog | REFERENCE_ONLY | No remote code/content installation in this phase. |
| 26 | Donor core replacement | Both complete runtimes | all Golden core boundaries | REJECT | Would break single-core, session, audit, and security invariants. |
| 27 | Direct external execution from model/MCP | Donor tool ecosystems | `SecurityManager`/`ToolRegistry` | REJECT | No external component may invoke host actions outside the Golden pipeline. |
| 28 | Automatic remote skill/plugin install/update | OpenClaw/Hermes extension ecosystems | future supply-chain gate | REJECT | Requires explicit review, provenance, pinning, approval, and rollback. |
| 29 | Donor scheduler/memory/credential pool | Hermes cron/memory/credentials | Golden task/memory/provider boundaries | REJECT | Creates competing state stores and policy owners. |

Counts: `KEEP_OURS=9`, `PORT=0`, `ADAPT=7`, `REIMPLEMENT_PATTERN=4`,
`REFERENCE_ONLY=5`, `REJECT=4`. Total matrix rows: `29`.

### Required audit fields

The matrix above gives the source path, current equivalent, classification,
and rationale. This compact crosswalk supplies the remaining required fields
for every row without hiding them in prose.

| # | Purpose | License | Dependencies | Security impact | Complexity | Expected benefit | Target Jarvis module | Priority |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Register typed tools | MIT/root; Golden-owned | none new | preserves risk gate | low | high | `registry.py` | P0 |
| 2 | Authorize actions | MIT/root; Golden-owned | none new | highest; sole gate | low | very high | `security.py` | P0 |
| 3 | Record/redact events | MIT/root; Golden-owned | SQLite existing | preserves evidence | low | very high | `audit.py` | P0 |
| 4 | Persist tasks/runs | MIT/root; Golden-owned | SQLite existing | preserves identity | medium | very high | `task_manager/database.py` | P0 |
| 5 | Schedule work | MIT/root; Golden-owned | existing scheduler | prevents duplicate execution | medium | very high | `task_manager/scheduler.py` | P0 |
| 6 | Carry mission state | MIT/root; Golden-owned | existing models | scopes permissions | medium | very high | `computer_use_mission.py` | P0 |
| 7 | Control desktop missions | MIT/root; Golden-owned | Windows/UIA stack existing | protects foreground/files | high | very high | Computer Use tools | P0 |
| 8 | Browse safely | MIT/root; Golden-owned | Playwright existing | protects public-read boundary | high | very high | `browser.py` | P0 |
| 9 | Select providers | MIT/root; Golden-owned | existing adapters | enforces secret policy | medium | very high | `model_router.py` | P0 |
| 10 | Describe skills | MIT donor pattern | manifest parser later | no grant by itself | medium | high | future extension package | P1 |
| 11 | Select eligible skills | MIT donor pattern | filesystem/config later | avoid accidental exposure | medium | high | future skill catalog | P1 |
| 12 | Reduce tool context | MIT donor pattern | registry existing | visibility only; no auth | medium | high | registry/orchestrator | P1 |
| 13 | Classify MCP tools | MIT donor pattern | MCP adapter later | blocks unsafe untrusted writes | high | very high | future MCP adapter | P0 |
| 14 | Recover MCP transport | MIT donor pattern | stdio/HTTP client later | prevents unsafe replay | high | high | future MCP adapter | P0 |
| 15 | Describe extension lifecycle | MIT donor pattern | loader later | gate before import | medium | high | future extension package | P1 |
| 16 | Pin skill revisions | MIT donor pattern | digest store later | provenance and rollback | medium | high | future skill store | P1 |
| 17 | Define Jarvis contract | independent design | none new | centralizes all gates | medium | very high | `docs/architecture` | P0 |
| 18 | Normalize MCP tools | independent design | MCP client later | prevents direct execution | high | very high | future MCP adapter | P0 |
| 19 | Isolate plugin loading | independent design | loader sandbox later | limits import blast radius | high | very high | future extension loader | P0 |
| 20 | Verify provenance/license | independent design | digest/SBOM tooling later | supply-chain gate | medium | very high | extension validation | P0 |
| 21 | Study distributed control | donor reference | large Gateway graph | expands trust domain | very high | medium | future remote control | P3 |
| 22 | Compare browser plugin | donor reference | donor browser stack | could bypass current policy | high | medium | `browser.py` review only | P2 |
| 23 | Study cron delivery | donor reference | second scheduler risk | duplicate-run risk | high | medium | scheduler UX only | P2 |
| 24 | Study ecosystem import | donor reference | conversion tooling | imported content untrusted | high | medium | future migration tooling | P3 |
| 25 | Study remote catalog | donor reference | network/store/pinning | supply-chain risk | very high | medium | future controlled catalog | P3 |
| 26 | Replace Golden core | prohibited | donor runtimes | breaks all ownership gates | extreme | negative | none | IGNORE |
| 27 | Bypass security for tools | prohibited | external execution | direct unsafe host action | extreme | negative | none | IGNORE |
| 28 | Auto-install/update | prohibited | remote code/deps | unreviewed code execution | extreme | negative | none | IGNORE |
| 29 | Add donor state owners | prohibited | DB/cron/credentials | split-brain and leakage | extreme | negative | none | IGNORE |

## License Matrix

| Surface | License/notice result | Gate |
| --- | --- | --- |
| OpenClaw root | MIT; root `LICENSE`; `THIRD_PARTY_NOTICES.md` exists | PASS for audit; file-level review required for port |
| Hermes root | MIT; root `LICENSE` | PASS for audit; dependency/plugin notices required for port |
| OpenClaw extensions/skills | Mixed operational surface; individual package and notice review required | NOT CLEARED for port |
| Hermes optional/provider/plugin dependencies | Broad optional graph; exact-pinned core in `pyproject.toml`/`uv.lock` | NOT CLEARED for port |
| Golden project | No donor license change | UNCHANGED |

`LICENSE_GATE_COMPLETED` means repository root licenses were verified. It does
not mean any donor file is approved for copying.

## Security Matrix

| Risk | Donor observation | Jarvis control/decision |
| --- | --- | --- |
| Tool visibility mistaken for authorization | OpenClaw allowlists/tool search shape the prompt | Registry and SecurityManager remain authoritative; ADAPT only. |
| Untrusted MCP writes | Hermes tests refuse destructive calls before RPC | Reimplement trust classification plus Golden confirmation; no direct MCP writes. |
| Replay after uncertain failure | Hermes tests distinguish read-only from write-capable calls | Adopt bounded replay rules; never replay unknown writes. |
| Plugin import code execution | Both ecosystems load extension code | Validate manifest, digest, license, permissions, and process boundary before load. |
| Remote skill supply chain | OpenClaw offers managed/remote skill lifecycle | REJECT automatic installation/update in Golden. |
| Credential leakage | Donor provider/credential pools are extensive | Keep Golden secret policy, redaction, and local/cloud classification. |
| Duplicate control plane | OpenClaw Gateway/nodes and Hermes cron are independent runtimes | Preserve one Golden core and one task scheduler. |

## Dependency Matrix

| Area | Donor dependency signal | Golden decision |
| --- | --- | --- |
| OpenClaw | Node/pnpm workspace with many extensions | Do not add Node runtime or workspace dependency to Golden. |
| Hermes core | Python `>=3.11,<3.15`, exact-pinned core dependencies | Do not import the Hermes lock graph. |
| Hermes optional providers/browser | Optional extras and provider-specific packages | Evaluate only per future adapter, one dependency at a time. |
| MCP transport | stdio/HTTP libraries in donor | Add nothing in 1A; first define adapter and security contract. |
| Golden runtime | Existing Python requirements and provider stack | Unchanged by this audit. |

## Recommended and Rejected Components

Recommended for a later isolated design phase:

1. A Jarvis-owned extension manifest inspired by `SKILL.md` frontmatter and
   explicit plugin capabilities.
2. A read-only-first MCP adapter that normalizes discovery into the existing
   registry and sends every invocation through SecurityManager and AuditLog.
3. Tool catalog reduction modeled on tool search, with no authorization meaning.
4. Immutable extension provenance: source URL, revision/digest, license,
   dependency list, maintainer, permission scopes, and load decision.
5. Negative tests for destructive refusal, no unsafe replay, auth recovery,
   crash isolation, and duplicate registration.

Rejected for this phase:

- replacing `JarvisService`, `TaskManager`, `SecurityManager`, `AuditLog`,
  `ModelRouter`, memory, browser, or Computer Use with donor equivalents;
- adding a second scheduler, gateway, websocket/control plane, or credential
  resolver;
- auto-installing, auto-updating, or executing remote skills/plugins;
- allowing model/MCP metadata to grant host permissions;
- importing the donor dependency trees or storing donor runtime databases in
  Golden.

## Jarvis Extension Contract Proposal

This is a proposal only. It is not implemented by 1A.

```yaml
id: vendor.skill-name
version: 1.0.0
kind: skill | tool_provider | mcp_adapter | provider
entrypoint: package.module:factory
source:
  url: https://example.invalid/source
  revision: immutable-revision-or-digest
license: MIT
maintainer: verified-owner
capabilities:
  - name: example_read
    input_schema: {}
    output_schema: {}
permissions:
  network: [https://example.com]
  filesystem: []
  computer_use: false
  secrets: []
security:
  trust: untrusted
  read_only: true
  confirmation: per_invocation
```

Required load pipeline:

`discover -> parse -> validate schema/license/digest -> resolve dependencies ->
security decision -> register in ToolRegistry -> expose filtered catalog ->
invoke through SecurityManager -> AuditLog -> teardown/rollback`.

Required invariants:

- extension code cannot register a duplicate tool or bypass risk metadata;
- manifest permissions are upper bounds, never grants;
- read-only is explicit and independently checked at invocation;
- external content is untrusted data and never instructions;
- failures are isolated to the extension invocation and do not create a second
  core, scheduler, memory store, or provider policy;
- every load, denial, invocation, failure, and unload is auditable;
- no secret is embedded in a skill, manifest, prompt, or audit payload.

## Implementation Order

1. Keep 8D.1 Background Control Center read-only and stable.
2. Write and review the extension contract and threat model.
3. Add manifest parsing and validation tests without loading external code.
4. Add a read-only skill catalog backed by the existing ToolRegistry.
5. Add MCP discovery in a separate adapter with explicit trust/approval gates.
6. Add plugin/provider loading only after provenance, rollback, and isolation
   tests pass.
7. Consider a controlled catalog/import workflow only after a separate license
   and supply-chain review.

Roadmap impact: this audit does not change the active roadmap or close 8D.2.
The next safe implementation unit is the contract/test design, not donor code
integration. Skills/MCP/plugin work belongs after the control-center follow-up
and an explicit authorization for the next phase.

## Risk Register

| ID | Risk | Severity | Mitigation | Owner/status |
| --- | --- | --- | --- | --- |
| R1 | Second scheduler or gateway creates duplicate execution | P0 | Keep Golden TaskManager/Scheduler as sole owner | Closed for 1A; enforce in future reviews |
| R2 | MCP trust metadata bypasses host authorization | P0 | SecurityManager decision plus per-tool scopes and AuditLog | Open; contract gate required |
| R3 | Remote skill/plugin supply-chain compromise | P0 | No auto-install; digest/license/review/rollback | Open; reject in 1A |
| R4 | Donor code carries undiscovered third-party license | P1 | File-level notices and SBOM before any port | Open |
| R5 | Tool search hides a dangerous tool but does not deny it | P1 | Keep search separate from authorization | Mitigated by design |
| R6 | Replaying an uncertain write duplicates an external action | P0 | Fail closed; replay only explicitly safe reads | Open for MCP adapter |
| R7 | Donor dependency graph increases attack/maintenance surface | P1 | One dependency at a time, pinned and scanned | Mitigated for 1A |
| R8 | New extension stores state outside canonical stores | P1 | Extension contract forbids competing DB/scheduler/memory | Open; test required |

## Expected Development Savings

These are planning estimates, not measured benchmarks. Reuse of patterns can
reduce design time, while preserving Golden boundaries avoids expensive
regressions.

| Area | Qualitative saving | Planning estimate | Basis |
| --- | --- | ---: | --- |
| Skill manifest/discovery design | HIGH | 1-2 weeks | OpenClaw precedence, eligibility, and revision model |
| MCP negative-security test plan | HIGH | 1-2 weeks | Hermes trust, 401, crash, and replay tests |
| Plugin lifecycle vocabulary | MEDIUM | 3-5 days | Both donor manifest/loader patterns |
| Tool catalog reduction | MEDIUM | 3-5 days | OpenClaw tool search and Golden catalog primitives |
| Durable scheduler/control plane | NONE | 0 weeks | Golden already owns this; do not port donor scheduler |

Net expected savings after security review: approximately `2-4 weeks` for
design/test planning, not a promise of reduced implementation time.

## Next Donor Wave

Wave 1B: audit only the smallest OpenClaw skill manifest and Hermes MCP
contract details against a proposed Jarvis schema.

Wave 1C: create a no-network, no-import contract test harness for manifest
validation, permission upper bounds, duplicate registration, provenance, and
audit redaction.

Wave 2: evaluate one read-only MCP adapter and one local skill fixture. Do not
enable host writes or remote installation until the security gates are signed
off.

## Audit Results

```yaml
JARVIS_DONOR_AUDIT: IN_PROGRESS
DONOR_AUDIT_1A: PASS
GOLDEN_RUNTIME_MODIFIED: NO
DONOR_CODE_COPIED_INTO_GOLDEN: NO
SINGLE_CORE_PRESERVED: PASS
OPENCLAW_REPOSITORY_VERIFIED: YES
OPENCLAW_LICENSE: MIT
OPENCLAW_COMPONENTS_REVIEWED: skills, precedence, allowlists, plugin SDK/capabilities, tool search, sandbox/policy, Gateway/nodes/approvals, browser, automation, notices
HERMES_REPOSITORY_VERIFIED: YES
HERMES_LICENSE: MIT
HERMES_COMPONENTS_REVIEWED: MCP stdio/HTTP, trust/readOnlyHint, tool filtering, plugin loader/plugin.yaml, skills, agent import, providers, cron, browser/plugin tests, replay/error handling
KEEP_OURS_COUNT: 9
PORT_COUNT: 0
ADAPT_COUNT: 7
REIMPLEMENT_PATTERN_COUNT: 4
REFERENCE_ONLY_COUNT: 5
REJECT_COUNT: 4
TOP_P0_COMPONENTS: SecurityManager gate, MCP adapter, extension provenance/license gate, single scheduler/core, no unsafe replay
EXTENSION_CONTRACT: proposed, not implemented
SKILL_RECOMMENDATION: ADAPT manifest/eligibility concepts behind Jarvis SecurityManager
MCP_RECOMMENDATION: ADAPT read-only-first adapter; no direct host invocation
PLUGIN_RECOMMENDATION: ADAPT lifecycle vocabulary; REIMPLEMENT loader and rollback
SECURITY_GATE: PASS for audit; implementation gate remains open
LICENSE_GATE: PASS for repository roots; port clearance remains file-level
SUPPLY_CHAIN_STATUS: PASS for no integration; open for future port
EXPECTED_SAVINGS: 2-4 weeks planning/design estimate
FILES_CREATED: docs/architecture/JARVIS_DONOR_AUDIT_1A.md, docs/architecture/REUSE_FIRST_POLICY.md
FILES_MODIFIED: documentation only
SECRET_SCAN: PASS for new docs
DEVICE_REGISTRY_TOUCHED: NO
COMMIT: documentation-only commit, if created by the closing task
PUSH: NO
ROADMAP_CHANGES: none; 8D.2 remains next, donor extension work deferred
NEXT_STEP: review this audit and authorize a separate contract/test phase
```
