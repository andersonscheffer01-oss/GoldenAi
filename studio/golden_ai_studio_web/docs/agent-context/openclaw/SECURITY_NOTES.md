# Security Notes — Auditoria OpenClaw

> Padrões de segurança observados no OpenClaw aplicáveis ao Jarvis.

---

## Modelo de Segurança OpenClaw

**"Trusted gateway, untrusted execution, deterministic policy"**

### Princípios

1. **Gateway é trusted** — Controla tudo
2. **Execução é untrusted** — Plugins/tools são sandboxed
3. **Policy é determinística** — Regras claras, sem ambiguidade

---

## Padrões Úteis para Jarvis

### 1. Security Audit System

OpenClaw tem 92 files de audit em `src/security/`.

**Checks disponíveis:**

| Check | Descrição | Jarvis Applicável |
|-------|-----------|-------------------|
| Gateway auth | Modos de autenticação | SIM - server_agent.py |
| Plugin trust | Segurança de código de plugins | SIM - plugins/ |
| Exec sandbox | Segurança de execução | SIM - execution/ |
| Filesystem | Políticas de acesso a arquivos | SIM - filesystem_tools |
| Dangerous flags | Análise de flags de config | SIM - config/ |
| Model hygiene | Validação de referências de modelos | SIM - model_router |
| Channel metadata | Segurança de canais | FUTURO - WhatsApp/etc |
| External content | Conteúdo não confiável | SIM - internet/ |

**Severidade:** INFO, WARNING, HIGH, CRITICAL

### 2. Tool Policy Pipeline

OpenClaw tem `agent-tools.before-tool-call.ts` com pipeline:

```
Tool Call
  → Policy Check (allow/deny/confirm)
    → Approval Check (se necessário)
      → Execution
        → Result Validation
```

**Jarvis já tem:** SecurityManager.decision() com allow/deny/confirm
**Jarvis pode adicionar:** Pipeline de validação pós-execução

### 3. External Content Isolation

OpenClaw trata conteúdo externo como DATA, nunca INSTRUCTION.

**Aplicação Jarvis:**
- Web content = UNTRUSTED DATA
- WhatsApp messages = UNTRUSTED DATA
- File content = UNTRUSTED DATA
- Nunca permitir que conteúdo externo vire system instruction

### 4. Prompt Injection Defense

OpenClaw tem `external-content-source.ts` para marcar conteúdo externo.

**Jarvis pode adicionar:**
- Marcação de proveniência (user vs external vs tool)
- Sandboxing de conteúdo externo
- Validação de input antes de processamento

### 5. Credential Isolation

OpenClaw tem `secrets/` directory e `secret-equal.ts`, `secret-mask.ts`.

**Jarvis já tem:**
- AuditLog.SENSITIVE redaction
- config/api_keys.json protegido

**Jarvis pode adicionar:**
- Secret masking em logs
- Equal-time comparison para tokens

---

## Riscos de Segurança Identificados

### Para Jarvis (ao adicionar capacidades OpenClaw)

| Risco | Severidade | Mitigação |
|-------|-----------|-----------|
| WebSocket exposure | HIGH | Autenticação obrigatória, rate limiting |
| Plugin code execution | HIGH | Sandboxing, permission scoping |
| External content injection | MEDIUM | Content isolation, sanitization |
| Credential exposure | HIGH | Secret masking, AuditLog redaction |
| MT5 access via plugins | CRITICAL | NUNCA permitir plugins acessarem MT5 diretamente |
| Golden access via plugins | CRITICAL | NUNCA permitir plugins acessarem Golden diretamente |
| Shell execution | HIGH | Allowlist, approval para comandos perigosos |

### Para Jarvis (ao considerar SIDECAR Node.js)

| Risco | Severidade | Mitigação |
|-------|-----------|-----------|
| Sidecar access to PC | HIGH | Sidecar só via HTTP com Jarvis Gateway |
| Sidecar own memory | MEDIUM | Jarvis controla toda memória |
| Sidecar bypass Gateway | CRITERAL | NUNCA permitir acesso direto |
| Sidecar credentials | HIGH | Sidecar não acessa credenciais |

---

## Recomendações de Segurança

### FASE 1: Plugin Kernel (futuro)

```python
# Contrato de segurança para plugins
class PluginSecurity:
    def can_execute(self, plugin, tool, context) -> bool:
        """Verifica se plugin pode executar tool"""
        # 1. Plugin tem permissão para tool?
        # 2. Tool está no allowlist do plugin?
        # 3. Contexto é seguro?
        # 4. Approvação necessária?

    def sandbox_plugin(self, plugin) -> Sandbox:
        """Cria sandbox para execução"""
        # Isolamento de filesystem
        # Isolamento de rede
        # Isolamento de processos
```

### FASE 2: Gateway Security (futuro)

```python
# Security policy para WebSocket
class GatewaySecurity:
    def authenticate(self, token) -> AuthResult:
        """Autenticação de cliente"""

    def authorize(self, session, action) -> bool:
        """Autorização de ação"""

    def rate_limit(self, client) -> bool:
        """Rate limiting"""
```

### FASE 3: Content Isolation (futuro)

```python
# Isolamento de conteúdo externo
class ContentIsolation:
    def classify(self, content) -> DataClassification:
        """Classifica conteúdo: INTERNAL/EXTERNAL/UNTRUSTED"""

    def sanitize(self, content, classification) -> str:
        """Sanitiza conteúdo baseado na classificação"""

    def audit(self, content, source) -> None:
        """Registra proveniência do conteúdo"""
```

---

## Auditoria de Segurança OpenClaw (Referência)

OpenClaw executa checks como:

- `audit-gateway-exposure.ts` — Verifica exposição do gateway
- `audit-plugins-trust.ts` — Verifica confiança de plugins
- `audit-exec-surface.ts` — Verifica superfície de execução
- `audit-filesystem-windows.ts` — Verifica acesso a filesystem
- `audit-model-hygiene.ts` — Verifica higiene de modelos
- `audit-deep-code-safety.ts` — Verifica segurança de código

**Para Jarvis futuro:**
Criar `jarvis_security_audit.py` com checks similares:

```python
class JarvisSecurityAudit:
    def check_ports(self) -> list[Finding]:
        """Verifica portas expostas"""

    def check_credentials(self) -> list[Finding]:
        """Verifica vazamento de credenciais"""

    def check_plugins(self) -> list[Finding]:
        """Verifica segurança de plugins"""

    def check_tools(self) -> list[Finding]:
        """Verifica tools perigosas"""

    def check_filesystem(self) -> list[Finding]:
        """Verifica acesso a filesystem"""

    def check_mtls(self) -> list[Finding]:
        """Verifica acesso MT5"""

    def check_golden(self) -> list[Finding]:
        """Verifica acesso Golden"""
```
