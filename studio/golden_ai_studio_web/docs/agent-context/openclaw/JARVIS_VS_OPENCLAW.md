# Jarvis vs OpenClaw — Matriz de Auditoria Completa

> **MISSÃO: AUDITORIA PRESERVE-FIRST**
> Data: 2026-09-17
> OpenClaw: commit `ecc4c992` (main, shallow clone)
> License: MIT (OpenClaw Foundation, 2026)
> Git Root: NO GIT REPOSITORY FOUND

---

## Resumo Executivo

| Item | Valor |
|------|-------|
| Jarvis | Sistema de IA local para trading, automação PC, MQL5 |
| OpenClaw | Assistente pessoal open-source (389k stars, TypeScript/Node.js) |
| Linguagem Jarvis | Python 3.11+ |
| Linguagem OpenClaw | TypeScript (Node.js) |
| Relação | OpenClaw = REFERÊNCIA. Jarvis = PRODUTO PRINCIPAL |

---

## Matriz de Componentes

### CORE / ORCHESTRATION

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Core Service | JarvisService (~1540 linhas) | `jarvis_core/service.py` | N/A (OpenClaw é gateway, não service) | N/A | None | KEEP | N/A | Python | stdlib | None | N/A | N/A | YES | NONE | NONE |
| Orchestrator | CentralOrchestrator com regex + LLM fallback | `jarvis_core/orchestrator/orchestrator.py` | Embedded agent runner com model routing | `src/agents/embedded-agent-runner.ts` | OpenClaw tem model routing mais sofisticado | EXTEND | Model routing patterns, provider failover logic | TypeScript→Python | openai/anthropic SDKs | Low | HIGH | MEDIUM | YES (preservar regex fast-path) | `jarvis_core/orchestrator/model_router.py` | NONE |
| Brain | JarvisBrain com Ollama + tools | `jarvis_core/brain.py` | System prompt composition, context engine | `src/agents/system-prompt.ts`, `src/context-engine/` | Jarvis Brain já é maduro | KEEP | Context composition patterns | TypeScript→Python | None | Low | MEDIUM | LOW | YES | NONE | NONE |
| Model Router | ModelRouter com provider adapters | `jarvis_core/orchestrator/model_router.py` | Model catalog, failover, auth profiles | `src/plugins/provider-runtime.ts`, `src/agents/model-fallback.ts` | OpenClaw tem failover mais robusto | EXTEND | Failover chain pattern, cooldown logic | TypeScript→Python | None | Low | HIGH | MEDIUM | YES | `jarvis_core/orchestrator/model_router.py` | NONE |
| Skills Router | SkillsRouter (regex-based) | `jarvis_core/orchestrator/skills_router.py` | Plugin-based skill system | `src/plugins/`, `skills/` | OpenClaw tem lifecycle completo | ADAPT | Skill discovery concept, not implementation | TypeScript→Python | None | Low | MEDIUM | MEDIUM | YES | NONE | NONE |

### TOOL REGISTRY / SECURITY / AUDIT

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| ToolRegistry | ToolRegistry (~74 linhas, maduro) | `jarvis_core/registry.py` | Plugin-based tool registration | `src/plugins/tool-factory-runtime.ts` | Jarvis já tem registry funcional | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| SecurityManager | SecurityManager com rules + confirmation | `jarvis_core/security.py` | Approval system, operator approvals | `src/gateway/exec-approval-manager.ts` | OpenClaw tem approval mais granular | EXTEND | Approval token lifecycle pattern | TypeScript→Python | None | Low | HIGH | LOW | YES | `jarvis_core/security.py` | NONE |
| AuditLog | AuditLog SQLite com sanitização | `jarvis_core/audit.py` | Audit system extensivo | `src/audit/` | Jarvis audit é funcional mas simples | EXTEND | Severity levels, structured events | TypeScript→Python | None | Low | MEDIUM | LOW | YES | `jarvis_core/audit.py` | NONE |
| Permissions | PermissionsManager v2 | `core/permissions/` | Role-based access | `src/gateway/role-policy.ts` | Jarvis já tem permissions | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Confirmations | Token-based confirmation flow | `jarvis_core/security.py` | Operator approval system | `src/gateway/operator-approval-store.ts` | Jarvis confirmation é adequado | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |

### GATEWAY / PROTOCOL

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Gateway | server_agent.py (HTTPServer threaded, ~6000 linhas) | `server_agent.py` | WebSocket gateway com typed protocol | `src/gateway/server.ts` | OpenClaw tem WebSocket + sessions | ADAPT | Typed message envelope, reconnect patterns | TypeScript→Python | websockets | Medium | VERY HIGH | HIGH | YES (manter HTTPServer) | `server_agent.py` (extender) | `jarvis_core/gateway/` |
| REST API | 50+ endpoints HTTP | `server_agent.py` | HTTP routes | `src/gateway/server-http.ts` | Jarvis REST já é extenso | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| WebSocket | Não implementado | N/A | WebSocket protocol bidirecional | `src/gateway/websocket-protocol.ts` | GAP REAL | PORT | Message envelope, reconnection, keepalive | TypeScript→Python | websockets | Medium | VERY HIGH | HIGH | N/A (novo) | NONE | `jarvis_core/gateway/websocket.py` |
| Sessions | Não implementado | N/A | Session management completo | `src/gateway/session-*.ts` | GAP REAL | ADAPT | Session lifecycle concepts | TypeScript→Python | None | Low | HIGH | HIGH | N/A (novo) | NONE | `jarvis_core/gateway/sessions.py` |
| Devices/Pairing | device_service.py (básico) | `jarvis/backend/app/services/device_service.py` | Device auth + pairing protocol | `src/gateway/device-*.ts` | OpenClaw tem device auth robusto | REFERENCE | Pairing flow concepts | N/A | N/A | Low | MEDIUM | N/A | YES | NONE | NONE |
| Auth | Bearer token (básico) | `jarvis/backend/app/security.py` | Multi-mode auth | `src/gateway/auth.ts` | Jarvis auth é simples | REFERENCE | Auth mode patterns | N/A | N/A | Low | MEDIUM | N/A | YES | NONE | NONE |
| Health | health_checks.py (básico) | `jarvis/pc_agent/health_checks.py` | Health probe system | `src/gateway/health/` | Jarvis health é básico | EXTEND | Health probe contract | TypeScript→Python | None | Low | MEDIUM | LOW | YES | `jarvis/pc_agent/health_checks.py` | NONE |

### PLUGINS

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Plugin System | PluginLoader (~192 linhas, file-based) | `plugins/plugin_loader.py` | Plugin SDK com lifecycle completo | `src/plugins/` (1122 files!) | OpenClaw tem plugin system massivo | ADAPT | Plugin lifecycle (register/start/stop/health), manifest concept | TypeScript→Python | None | Medium | VERY HIGH | HIGH | YES (preservar loader atual) | `plugins/plugin_loader.py` (extender) | `jarvis_core/plugins/` |
| Plugin Registry | PluginRegistry (básico) | `plugins/plugin_loader.py` | Plugin registry com snapshot | `src/plugins/plugin-registry.ts` | OpenClaw tem registry sofisticado | ADAPT | Registry snapshot pattern | TypeScript→Python | None | Low | HIGH | MEDIUM | YES | `plugins/plugin_loader.py` | NONE |
| Plugin Discovery | Auto-load de .py files | `plugins/plugin_loader.py`` | Discovery com manifest | `src/plugins/discovery.ts` | OpenClaw usa manifests | ADAPT | Manifest-based discovery | TypeScript→Python | None | Low | HIGH | MEDIUM | YES | `plugins/plugin_loader.py` | NONE |
| Plugin Permissions | Nenhuma | N/A | Plugin permission scoping | `src/plugins/tool-grant-allowlist.ts` | GAP REAL | PORT | Permission scoping concept | TypeScript→Python | None | Medium | HIGH | MEDIUM | N/A (novo) | NONE | `jarvis_core/plugins/permissions.py` |

### BROWSER

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Browser Service | BrowserService (Playwright headless) | `core/browser/service.py` | Browser extension com Chrome native | `extensions/browser/` | Jarvis já tem Playwright | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Browser Architecture | Headless Chromium | `core/browser/service.py` | Chrome extension + native host | `extensions/browser/chrome-extension/` | OpenClaw usa Chrome extenso | REFERENCE | DOM/ARIA extraction patterns | N/A | N/A | Low | MEDIUM | N/A | YES | NONE | NONE |

### WHATSAPP

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| WhatsApp | Route regex existe (`r"whatsapp"`) | `jarvis_core/orchestrator/orchestrator.py` | WhatsApp extension completa | `extensions/whatsapp/` | GAP REAL | REFERENCE | Session management, reconnection patterns | N/A | N/A | Low | HIGH | N/A | N/A (novo futuro) | NONE | NONE |

### AUTOMATION / SCHEDULER

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Job Manager | JobManager (ThreadPoolExecutor) | `core/jobs/manager.py` | Cron system completo | `src/cron/` (214 files) | OpenClaw tem scheduler maduro | ADAPT | Job lifecycle, heartbeat, delivery patterns | TypeScript→Python | None | Low | HIGH | HIGH | YES | `core/jobs/manager.py` | `jarvis_core/automation/` |
| Task Manager | TaskManager com planner/runner | `jarvis_core/task_manager/` | Task registry + flow | `src/tasks/` (134 files) | Jarvis já tem TaskManager | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Scheduler | Nenhum | N/A | Cron scheduler | `src/cron/service.ts` | GAP REAL | ADAPT | Cron expression parsing, job scheduling | TypeScript→Python | None | Low | HIGH | MEDIUM | N/A (novo) | NONE | `jarvis_core/automation/scheduler.py` |

### MEMORY

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Memory V2 | SQLite + FTS5 + embeddings + semantic | `jarvis_core/memory/` | Memory artifact provenance | `src/memory/` (3 files apenas) | Jarvis memory É MAIS maduro que OpenClaw | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Knowledge Graph | Project Memory + Obsidian | `jarvis_core/memory/` | N/A | N/A | Jarvis tem capabilities que OpenClaw não tem | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Embeddings | nomic-embed-text via Ollama | `jarvis_core/memory/embeddings.py` | Embedding providers | `src/plugins/embedding-providers.ts` | Jarvis já tem embeddings | REFERENCE | Provider abstraction pattern | N/A | N/A | Low | LOW | N/A | YES | NONE | NONE |

### VOICE

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Voice P1.4C | VoiceService + streaming + barge-in (PAUSADO) | `jarvis_core/voice_service.py`, `streaming/` | Voice extension | `extensions/talk-voice/` | Pausado - não mexer | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES (PAUSADO) | NONE | NONE |

### WINDOWS TOOLS

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Windows Tools | 38+ tools (open_program, volume, filesystem, etc.) | `jarvis_core/service.py`, `core/computer/` | Node-host linux commands | `extensions/linux-node/` | Jarvis tem Windows tools que OpenClaw não tem | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Computer Use | analyze_screen | `jarvis_core/service.py` | Computer use extension | `extensions/cua-computer/` | Jarvis tem screen analysis | REFERENCE | Computer use patterns | N/A | N/A | Low | LOW | N/A | YES | NONE | NONE |

### MULTI-AGENT

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Agents | 11 agentes especializados | `agents/` | Subagent system | `src/agents/subagents/` | Jarvis já tem agents | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Agent Orchestration | orchestrator.py | `agents/orchestrator.py` | Agent harness | `src/agents/embedded-agent*.ts` | OpenClaw tem harness mais robusto | REFERENCE | Agent lifecycle patterns | N/A | N/A | Low | MEDIUM | N/A | YES | NONE | NONE |

### SANDBOX

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Sandbox | `sandbox/` directory existe | `sandbox/` | Docker sandbox | `src/agents/sandbox/` | Jarvis tem sandbox dir vazio | REFERENCE | Sandbox isolation patterns | N/A | N/A | Low | MEDIUM | N/A | N/A (futuro) | NONE | NONE |

### GOLDEN / MT5

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Golden Scanner | golden_scanner.py (~2000 linhas) | `golden_scanner.py` | N/A | N/A | N/A | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| MT5 | mt5_connector.py + mt5_trader.py | `mt5_connector.py`, `mt5_trader.py` | N/A | N/A | N/A | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |
| Risk Engine | risk_engine.py | `risk_engine.py` | N/A | N/A | N/A | KEEP | N/A | N/A | N/A | None | N/A | N/A | YES | NONE | NONE |

### OBSERVABILITY / HEALTH

| COMPONENT | JARVIS CURRENT | JARVIS FILES | OPENCLAW APPROACH | OPENCLAW FILES | GAP | DECISION | WHAT EXACTLY TO REUSE | LANGUAGE | DEPENDENCIES | SECURITY RISK | BENEFIT | EFFORT | PRESERVE EXISTING? | FILES THAT WOULD CHANGE | NEW FILES |
|-----------|---------------|-------------|-------------------|---------------|-----|----------|----------------------|----------|-------------|--------------|---------|--------|-------------------|------------------------|-----------|
| Health | health_checks.py (básico) | `jarvis/pc_agent/health_checks.py` | Health probe system | `src/gateway/health/` | Jarvis health é básico | EXTEND | Health contract (OK/DEGRADED/OFFLINE) | TypeScript→Python | None | Low | MEDIUM | LOW | YES | `jarvis/pc_agent/health_checks.py` | NONE |
| Observability | AuditLog apenas | `jarvis_core/audit.py` | Observability stack | `extensions/diagnostics-otel/` | GAP REAL | REFERENCE | Structured logging patterns | N/A | N/A | Low | MEDIUM | N/A | YES | NONE | NONE |

---

## Resumo de Decisões

| Decisão | Quantidade | Componentes |
|---------|-----------|-------------|
| KEEP | 24 | Core Service, Brain, ToolRegistry, Permissions, Confirmations, REST API, Browser Service, Memory V2, Knowledge Graph, Embeddings, Voice P1.4C, Windows Tools, Computer Use, Agents, Agent Orchestration, Golden, MT5, Risk Engine, Task Manager, Plugins (base), AuditLog (base), SecurityManager (base), Health (base), Observability (base) |
| EXTEND | 7 | Orchestrator, Model Router, SecurityManager, AuditLog, Health, Plugin System, Job Manager |
| ADAPT | 5 | Gateway, Sessions, Plugin System, Plugin Discovery, Scheduler |
| PORT | 2 | WebSocket, Plugin Permissions |
| REFERENCE | 8 | Devices/Pairing, Auth, Browser Architecture, WhatsApp, Embeddings Provider, Computer Use Patterns, Sandbox, Observability |
| IGNORE | 0 | N/A |
| REPLACE_CANDIDATE | 0 | NONE |

---

## Top 10 Reuse Opportunities (por Development Leverage)

| # | Componente | Leverage | Por quê |
|---|-----------|----------|---------|
| 1 | Plugin Architecture | VERY HIGH | Desbloqueia todas as extensões futuras; OpenClaw tem 1122 files de plugins |
| 2 | Gateway Patterns | VERY HIGH | Typed WebSocket, sessions, reconnect — padrões maduros |
| 3 | Model Router / Failover | HIGH | Provider failover chain, cooldown, auth profiles |
| 4 | Scheduler/Cron | HIGH | Job scheduling, heartbeat, delivery — OpenClaw tem 214 files |
| 5 | Security Audit Patterns | HIGH | Structured security checks, severity levels |
| 6 | WhatsApp Channel | HIGH | Session management, reconnection, message handling |
| 7 | Browser Architecture | HIGH | DOM/ARIA patterns, Chrome extension model |
| 8 | Device Pairing | MEDIUM | Pairing protocol, device auth |
| 9 | Health Contract | MEDIUM | OK/DEGRADED/OFFLINE/ERROR standardization |
| 10 | Task Flow Registry | MEDIUM | Task lifecycle, progress tracking |

---

## Top 10 Things NOT to Reuse

| # | Componente | Por quê |
|---|-----------|---------|
| 1 | OpenClaw Gateway (como runtime) | Jarvis tem server_agent.py; OpenClaw é REFERÊNCIA apenas |
| 2 | TypeScript/Node.js runtime | Jarvis é Python; não misturar ecossistemas |
| 3 | OpenClaw Memory | Jarvis memory V2 é MAIS maduro |
| 4 | OpenClaw Voice | Jarvis voice P1.4C pausado, não substituir |
| 5 | OpenClaw Windows Tools | Jarvis tem 38+ tools Windows que OpenClaw não tem |
| 6 | OpenClaw Agents (como runtime) | Jarvis já tem 11 agentes especializados |
| 7 | OpenClaw Golden/MT5 | OpenClaw não tem trading |
| 8 | OpenClaw Browser (como plugin) | Jarvis já tem Playwright; adaptor conceitos apenas |
| 9 | OpenClaw Plugin SDK completo | Portar conceitos, não o SDK inteiro |
| 10 | OpenClaw Docker/sandbox patterns | Jarvis é desktop-first; sandbox futuro |

---

## REPLACE_CANDIDATES

**NONE**

Nenhum componente do Jarvis deve ser substituído pelo OpenClaw nesta fase.
