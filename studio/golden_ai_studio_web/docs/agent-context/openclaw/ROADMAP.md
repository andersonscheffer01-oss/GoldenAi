# Roadmap — Jarvis Evolution (baseado em auditoria OpenClaw)

> Ordem de evolução recomendada após auditoria.
> Cada fase é INDEPENDENTE — pode ser pulada se não relevante.

---

## PHASE 0 — Voice P1.4C (PAUSADA)

**Status:** PAUSADA
**Ação:** NENHUMA nesta auditoria
**Nota:** Não reabrir voice, barge-in, streaming, STT/TTS

---

## PHASE 1 — Auditoria OpenClaw/Jarvis

**Status:** CONCLUÍDA (este documento)
**Objetivo:** Mapear componentes, identificar gaps, definir reuso
**Dependências:** Nenhuma
**Documentos:** JARVIS_VS_OPENCLAW.md, OPENCLAW_COMPONENT_MAP.md, REUSE_POLICY.md, SECURITY_NOTES.md, ROADMAP.md

---

## PHASE 2 — Plugin Kernel

**Status:** PENDENTE (alta prioridade)
**Objetivo:** Sistema de plugins unificado para Jarvis
**Por que agora:** Desbloqueia todas as extensões futuras; OpenClaw tem referência madura

### Current Jarvis Components
- `plugins/plugin_loader.py` (192 linhas, file-based)
- `plugins/PluginRegistry` (básico)
- Legacy inventory recorded 3 plugins at audit time; the external `crypto_price` plugin has since been retired. Current crypto reads use canonical MT5 read-only data.

### OpenClaw References
- `src/plugins/` (1122 files)
- `packages/plugin-sdk/`
- Plugin manifest, lifecycle, permissions, hooks

### What to Reuse (Nível B — PATTERN)
- Plugin manifest concept (name, version, capabilities, permissions)
- Plugin lifecycle (register, start, stop, health)
- Plugin registry com snapshots
- Permission scoping

### Architecture

```
jarvis_core/plugins/
├── __init__.py
├── base.py              # PluginBase class
├── manifest.py          # Plugin manifest parser
├── registry.py          # Plugin registry (extendido)
├── loader.py            # Plugin loader (evoluído)
├── permissions.py       # Plugin permissions
├── lifecycle.py         # Plugin lifecycle manager
└── hooks.py             # Plugin hooks system
```

### Plugin Contract

```python
class PluginBase:
    def register(self, registry) -> None:
        """Registra tools do plugin"""

    def start(self) -> None:
        """Inicia plugin"""

    def stop(self) -> None:
        """Para plugin"""

    def health(self) -> PluginHealth:
        """Retorna saúde do plugin"""

    def permissions(self) -> list[Permission]:
        """Retorna permissões necessárias"""
```

### Existing Files to Modify
- `plugins/plugin_loader.py` (evoluir)

### New Files
- `jarvis_core/plugins/` (diretório completo)

### Security Impact
- MEDIUM — Plugins executam código
- Mitigação: Sandboxing, permission scoping, AuditLog

### Tests
- Plugin discovery
- Plugin lifecycle (start/stop)
- Plugin permissions
- Plugin failure isolation
- Plugin health checks

### Failure Tests
- Plugin crash não derruba Jarvis
- Plugin loop não consome recursos
- Plugin denied não acessa tools restritas

### Permission Tests
- Plugin só acessa tools autorizadas
- Plugin não acessa MT5 diretamente
- Plugin não acessa Golden diretamente
- Plugin não acessa credenciais

### Rollback
- Desabilitar plugins via config
- Plugin loader com fallback

### Done Criteria
- [ ] PluginBase class definida
- [ ] Manifest parser funcionando
- [ ] Registry com snapshot
- [ ] Lifecycle manager
- [ ] Permission scoping
- [ ] 3 plugins de exemplo
- [ ] Todos os testes passando

---

## PHASE 3 — Security Audit Baseline

**Status:** PENDENTE
**Objetivo:** Criar JarvisSecurityAudit
**Por que agora:** Segurança deve entrar ANTES de exposição remota
**Dependências:** Nenhuma

### Current Jarvis Components
- `jarvis_core/audit.py` (AuditLog básico)
- `jarvis_core/security.py` (SecurityManager)
- `core/permissions/` (PermissionsManager)

### OpenClaw References
- `src/security/` (92 files)
- Audit checks, severity levels, findings

### What to Reuse (Nível A — IDEA)
- Severity levels (INFO, WARNING, HIGH, CRITICAL)
- Check categories (ports, auth, credentials, tools, filesystem, plugins)
- Structured findings

### Architecture

```
jarvis_core/security_audit.py
├── JarvisSecurityAudit
│   ├── check_ports()
│   ├── check_credentials()
│   ├── check_plugins()
│   ├── check_tools()
│   ├── check_filesystem()
│   ├── check_mtls()
│   ├── check_golden()
│   └── report() → SecurityReport
```

### Existing Files to Modify
- `jarvis_core/audit.py` (extender com severity)

### New Files
- `jarvis_core/security_audit.py`

### Security Impact
- POSITIVO — Melhora segurança existente

### Tests
- Cada check retorna findings corretos
- Severity levels corretos
- Report format válido

### Done Criteria
- [ ] SecurityAudit funcional
- [ ] Pelo menos 8 checks implementados
- [ ] Report format definido
- [ ] Integração com AuditLog

---

## PHASE 4 — Jarvis Gateway

**Status:** PENDENTE
**Objetivo:** WebSocket gateway para clientes remotas
**Por que agora:** Prerequisite para PWA, mobile, multi-device
**Dependências:** PHASE 3 (Security Audit)

### Current Jarvis Components
- `server_agent.py` (HTTPServer threaded)
- `jarvis/backend/` (FastAPI-based backend)

### OpenClaw References
- `src/gateway/server.ts` (1629 entries!)
- `src/gateway/websocket-protocol.ts`
- `src/gateway/session-*.ts`

### What to Reuse (Nível C — PORT)
- Typed message envelope (JSON com type field)
- Reconnection with exponential backoff
- Keepalive ping/pong
- Session lifecycle concepts

### Architecture

```
Client (PWA/Mobile/Desktop)
  ↓ WebSocket
Jarvis Gateway (jarvis_core/gateway/)
  ↓ Auth check
JarvisService
  ↓ Security check
ToolRegistry
  ↓ Execute
Tool
```

### Existing Files to Modify
- `server_agent.py` (adicionar WebSocket upgrade)

### New Files
- `jarvis_core/gateway/__init__.py`
- `jarvis_core/gateway/websocket.py`
- `jarvis_core/gateway/protocol.py`
- `jarvis_core/gateway/sessions.py`
- `jarvis_core/gateway/auth.py`

### Security Impact
- HIGH — Exposição remota
- Mitigação: Auth obrigatória, rate limiting, TLS

### Tests
- WebSocket connection
- Authentication
- Session management
- Reconnection
- Rate limiting

### Done Criteria
- [ ] WebSocket server funcionando
- [ ] Auth implementado
- [ ] Session management
- [ ] Client PWA conectando
- [ ] Rate limiting

---

## PHASE 5 — Browser Agent

**Status:** PENDENTE
**Objetivo:** Browser automation isolado
**Por que agora:** Web research, data extraction, automation
**Dependências:** PHASE 2 (Plugin Kernel)

### Current Jarvis Components
- `core/browser/service.py` (Playwright headless)

### OpenClaw References
- `extensions/browser/` (Chrome extension + native host)

### What to Reuse (Nível A — IDEA)
- DOM/ARIA first approach
- Structured references
- Screenshots/vision fallback
- Browser isolation patterns

### Architecture

```
Browser Request
  ↓
JarvisService
  ↓
SecurityManager (browser policy)
  ↓
Browser Plugin (via Plugin Kernel)
  ↓
Playwright (core/browser/service.py)
```

### Done Criteria
- [ ] Browser como plugin
- [ ] Policy de segurança
- [ ] DOM extraction
- [ ] Screenshot fallback

---

## PHASE 6 — Automation Engine

**Status:** PENDENTE
**Objetivo:** Automação programável
**Por que agora:** Scheduled tasks, event triggers, background jobs
**Dependências:** PHASE 2 (Plugin Kernel)

### Current Jarvis Components
- `core/jobs/manager.py` (JobManager básico)
- `jarvis_core/task_manager/` (TaskManager)

### OpenClaw References
- `src/cron/` (214 files)
- `src/tasks/` (134 files)

### What to Reuse (Nível B — PATTERN)
- Cron expression parsing
- Job lifecycle (queued/running/completed/failed)
- Heartbeat monitoring
- Delivery to channels

### Done Criteria
- [ ] Scheduler funcional
- [ ] Cron expressions suportados
- [ ] Job history
- [ ] Heartbeat monitoring

---

## PHASE 7 — WhatsApp

**Status:** FUTURO
**Objetivo:** Canal WhatsApp
**Por que agora:** Comunicação mobile
**Dependências:** PHASE 4 (Gateway), PHASE 2 (Plugin Kernel)

### OpenClaw References
- `extensions/whatsapp/` (32 entries)

### Architecture

```
iPhone → WhatsApp → WhatsApp Adapter (Sidecar Node.js)
  ↓ HTTP
Jarvis Gateway
  ↓
JarvisService
```

### Sidecar Rules
- Sidecar PODE: receive/send message, media, pair, health
- Sidecar NÃO PODE: execute tools, access MT5/Golden, bypass Gateway

---

## PHASE 8 — Mobile/PWA

**Status:** FUTURO
**Objetivo:** Progressive Web App
**Dependências:** PHASE 4 (Gateway)

### OpenClaw References
- `apps/ios/`, `apps/android/`
- `ui/` (Control UI)

### Done Criteria
- [ ] PWA funcionando
- [ ] WebSocket connection
- [ ] Pairing flow
- [ ] Approvals via mobile

---

## PHASE 9 — Model Router V2

**Status:** FUTURO
**Objetivo:** Router de modelos mais inteligente
**Dependências:** Nenhuma

### Current Jarvis Components
- `jarvis_core/orchestrator/model_router.py`

### OpenClaw References
- `src/agents/model-*.ts`
- `src/plugins/provider-runtime.ts`

### What to Reuse (Nível C — PORT)
- Provider failover chain
- Auth profile rotation
- Model catalog with capabilities

---

## PHASE 10 — Agent Isolation / Agents V2

**Status:** FUTURO
**Objetivo:** Isolamento entre agentes
**Dependências:** PHASE 2 (Plugin Kernel)

### Current Jarvis Components
- `agents/` (11 agentes)

### OpenClaw References
- `src/agents/subagents/`
- `src/agents/sandbox/`

### Arquitetura

```
Jarvis
  ↓
Orchestrator
  ↓
Specialized Agents (isolados)
  ↓
SecurityManager + AuditLog + ToolRegistry
```

---

## PHASE 11 — Sandbox

**Status:** FUTURO
**Objetivo:** Execução isolada de código gerado
**Dependências:** PHASE 2 (Plugin Kernel)

### OpenClaw References
- `src/agents/sandbox/`

### Modelo

```
Jarvis Core = HOST
Risky generated code = SANDBOX
Unknown scripts = SANDBOX
Dangerous shell = SANDBOX
```

---

## PHASE 12 — Memory Enhancements

**Status:** FUTURO
**Objetivo:** Melhorias pontuais na memória
**Dependências:** Nenhuma

### Current Jarvis Components
- `jarvis_core/memory/` (SQLite + FTS5 + embeddings)

### NOT to Replace
- SQLite, FTS5, embeddings, Knowledge Graph, Project Memory, Obsidian

### Possible Enhancements
- Recency weighting
- Importance scoring
- MMR diversification
- Promotion/forgetting curves
- Summarization
- Provenance tracking

---

## PHASE 13 — Golden/Trading Deeper Integration

**Status:** FUTURO
**Objetivo:** Integração mais profunda com trading
**Dependências:** Nenhuma

### Current Jarvis Components
- `golden_scanner.py`, `mt5_connector.py`, `risk_engine.py`
- 47 estratégias, 22 pares

### Architecture

```
TradingAgent
  ↓
Golden (analysis)
  ↓
Proposal
  ↓
Risk/Security Policy
  ↓
Approval (se necessário)
  ↓
MT5 Adapter
```

### Rule
LLM → NUNCA → MT5 direto
