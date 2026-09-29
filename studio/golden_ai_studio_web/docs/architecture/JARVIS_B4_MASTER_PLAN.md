# Jarvis B4 Master Plan

Date: 2026-09-29
Baseline: `013ba7c700a5c62fc97aaab10541ed5a769b5d13`
Status: planning only. B4.1 is not started.

## Current state

B3 is closed and established the canonical Golden-to-Jarvis read boundary.
JarvisService owns the bridge, Brain owns contextual response generation,
ModelRouter owns provider selection, SecurityManager owns canonical tool
authorization, AuditLog owns receipts, and CanonicalMemoryBoundary remains the
memory authority. The Web AI safe profile blocks MT5, trading, Voice, tester
and MQL5 compile before initialization.

The remaining risk is not absence of code. It is split ownership: direct
legacy HTTP/provider handlers, parallel database roots, partially exposed
Golden semantics, and UI surfaces that can look more complete than their
canonical evidence.

## Target state

```text
One Jarvis Core
  -> one service/tool/security/audit/task/memory authority
  -> typed read adapters for Golden donors
  -> explicit provenance, freshness and evidence classes
  -> product UI with visible security/approval/empty/error states
  -> separate human gates for hardware, credentials, tester and money
```

Golden remains a donor. No Golden Brain, Golden Voice Brain, second scheduler,
second memory authority, second task database, or direct provider authority is
created.

## Planning principles

1. Audit Jarvis, Golden, archaeology and donor audits before each capability.
2. Prefer `KEEP_OURS` when Jarvis is already safer or more mature.
3. Use `PORT` for bounded read views, `ADAPT` for semantics/contracts, and
   `REFERENCE_ONLY` for lessons that cannot safely become runtime authority.
4. Every adapter must define owner, schema, source identity, freshness, failure,
   security state, AuditLog event and a no-legacy-execution test.
5. Never infer trade authorization from analysis, score, validation, or UI state.
6. Keep data migration and hardware/provider gates out of normal implementation.

## Candidate ordering

The order below follows dependency and risk, not feature novelty.

### B4.1 - Ownership, perimeter and observability contract

**Objective:** make the current owners and direct legacy boundaries explicit and
measurable before adding more recovered capability.

**Dependencies:** B3 runtime profile and read envelopes; existing SecurityManager,
AuditLog, ModelRouter, TaskManager and status endpoints.

**Reuse target:** existing `JarvisService.runtime_ownership_diagnostics`,
runtime profile status, provider telemetry and audit correlation.

**Likely files/systems:** architecture docs, read-only diagnostics, server route
inventory, provider/model telemetry and tests. No database rebind or migration.

**Security/runtime impact:** observation only; prove which legacy endpoints are
covered and which still bypass canonical SecurityManager.

**Tests:** ownership matrix, profile containment, direct-provider detection,
AuditLog correlation and no-provider/no-MT5 regression.

**Human gate:** approve any later change that deprecates or reroutes a legacy
endpoint.

**Stop conditions:** uncertain owner, unexpected mutation, security bypass, or
need for a schema migration.

**Checkpoint:** a reviewed ownership/perimeter report with no code behavior
change unless separately authorized.

### B4.2 - Canonical market intelligence depth

**Objective:** extend the B3 read bridge for Scanner, Radar, Deep Analysis, Risk,
Validation and Macro/Fundamental detail without copying engines.

**Dependencies:** B4.1 boundary contract; B3 MarketContext and provenance;
existing Golden scanner, analysis, meta strategy, risk and validation modules.

**Reuse target:** `GoldenReadBridge`, `market_data.py`, `analysis_engines.py`,
`meta_strategy.py`, `risk_engine.py`, `validation_engine.py`, and existing
Radar `market.html` read semantics.

**Likely files/systems:** read adapters, typed contracts, canonical endpoints,
Control Center read models and focused tests. `market.html` remains unchanged
unless a later explicit UI gate says otherwise.

**Security/runtime impact:** read-only; no auto-trade, order, broker mutation or
legacy write path.

**Tests:** deterministic fixtures, freshness/provenance, unavailable-source,
synthetic-evidence labels, score-versus-probability semantics and no-order tests.

**Human gate:** review of fields and semantics before any real market validation.

**Stop conditions:** fabricated live data, ambiguous source, missing freshness,
or an adapter that starts MT5 outside an approved profile.

**Checkpoint:** canonical read model and UI contract reviewed; no execution
authority added.

### B4.3 - Robot intelligence and evidence product surface

**Objective:** make catalog identity, repertoire state, tester evidence and
performance explainable in Jarvis while preserving the distinction between
`ACTIVE_IN_REPERTOIRE` and `AUTHORIZED_TO_TRADE`.

**Dependencies:** B4.1 ownership; B2 evidence contracts; existing catalog,
MQL5 evidence and controlled tester adapter; reconciled data inventory.

**Reuse target:** `robot_catalog.py`, `mql5_evidence.py`,
`strategy_tester_adapter.py`, fixture provenance and B3 evidence read models.

**Likely files/systems:** read-only catalog/evidence views, association models,
performance projections and tests. No production EA edits.

**Security/runtime impact:** catalog mutations need explicit SecurityManager
approval; tester execution is a separate human gate; no live trading.

**Tests:** identity/hash reconciliation, stale/missing artifact states,
association provenance and explicit action-state separation.

**Human gate:** separate authorization for any real Strategy Tester run or
repertoire mutation.

**Stop conditions:** production robot selection, broker access, artifact
ambiguity, or historical data mutation.

**Checkpoint:** evidence/read surface complete and all runtime artifacts remain
outside source authority.

### B4.4 - Scientific and temporal memory recovery

**Objective:** adapt typed evidence, revisions, conflicts, supersession,
experiment links and market observations behind CanonicalMemoryBoundary.

**Dependencies:** B4.1 ownership; B2 scientific contracts; data recovery map;
stable identifiers and explicit import manifests.

**Reuse target:** existing Jarvis Memory V2/boundary plus Golden scientific
memory semantics. Do not create a second MemoryService or database authority.

**Likely files/systems:** typed contracts, append-only adapters, provenance
receipts and isolated temporary validation stores. Runtime import is a separate
gate and is not implied by implementation.

**Security/runtime impact:** privacy and retention review; no silent overwrite,
no automatic import, no credential or external provider requirement.

**Tests:** conflict/supersession, revision identity, stale evidence, experiment
links, restart durability and no-import default.

**Human gate:** explicit approval for each validated data family before import.

**Stop conditions:** duplicate authority, unclear ownership, lost original IDs,
or migration pressure.

**Checkpoint:** contract and adapter proven with fixtures; production data still
untouched.

### B4.5 - Provider policy and control-center parity

**Objective:** formalize provider policy and expose capability state in the main
Jarvis UI without bypassing ModelRouter.

**Dependencies:** B4.1 telemetry; current ModelRouter/provider adapters; B3 UI
read contracts; user-approved provider configuration.

**Reuse target:** existing ModelRouter, Brain, provider adapters and Control
Center components.

**Policy requirement:** `GENERAL_CHAT`: Gemini primary, Groq online fallback,
Local offline fallback. `CODING`: future OpenAI/Codex preference when explicitly
configured, otherwise existing policy. `MARKET_ANALYSIS` and `TOOL_PLANNING`
remain ModelRouter policies, never direct provider calls.

**Likely files/systems:** policy/config contracts, status read models and UI
states for provider, fallback reason, security, progress, audit and provenance.

**Security/runtime impact:** no secret disclosure; no assumption that a ChatGPT
subscription grants API access; no provider call in the planning gate.

**Tests:** policy selection with mocked adapters, offline fallback, secret
classification, telemetry and direct-handler containment.

**Human gate:** provider credential/configuration approval is separate from code
implementation.

**Stop conditions:** hardcoded model bypass, undisclosed cloud routing, secret
leak, or direct provider call outside ModelRouter.

**Checkpoint:** policy and UI contract reviewed; runtime provider validation is
separately authorized.

## Explicitly separate gates

- Voice recovery: paused and blocked by `REAL_MIC_SIGNAL_PATH_INCONSISTENCY`.
  OpenJarvis is reference material only until a dedicated hardware gate.
- MT5 read validation: separate from implementation and provider policy.
- Strategy Tester and MQL5 compile: separate human-authorized gates.
- Live trading, broker mutation and credentials: never bundled with B4 normal work.
- Personal Finance: deferred and out of scope; no donor search, MCP or API.

## Quick wins

- Extend existing read-only bridge fields with explicit provenance/freshness.
- Add scanner/radar/deep-analysis semantic matrices and unavailable states.
- Expose evidence/catalog associations without executing them.
- Add ModelRouter policy tests using mocked providers only.
- Add Control Center states for `UNKNOWN`, `EMPTY`, `PARTIAL`, `STALE` and
  `UNAVAILABLE` using existing read models.

## High-risk gates

Live trading, broker/order paths, real Strategy Tester, MQL5 compilation, Voice
hardware, credential setup, external paid providers, data import/migration and
production robot changes.

## User decisions actually required

1. Approve which B4 subgate to authorize first after reviewing this plan.
2. Approve any later provider credential/configuration change; Gemini primary is
   a roadmap requirement, not a provider call in this gate.
3. Approve separately any production data recovery/import, hardware test,
   Strategy Tester execution or trading action.

## Pass boundary

This master plan is `PASS` as a planning artifact only. It does not authorize
B4.1, provider calls, hardware, MT5, trading, Strategy Tester, MQL5 compile,
Voice, MCP installation, data import, commit or push.
