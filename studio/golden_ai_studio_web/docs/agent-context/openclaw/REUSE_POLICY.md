# Reuse Policy — OpenClaw → Jarvis

> Regras para reaproveitamento de código/padrões do OpenClaw no Jarvis.

---

## Princípio Fundamental

**OpenClaw é REFERÊNCIA. Jarvis é PRODUTO.**

Nunca:
- Rodar OpenClaw como runtime
- Conectar Jarvis ao OpenClaw como dependência
- Usar plugins OpenClaw diretamente
- Substituir componentes Jarvis por equivalentes OpenClaw

---

## Níveis de Reuso

### NÍVEL A — IDEA
**Copiar apenas o conceito.**

Exemplo: "OpenClaw tem health probes com status DEGRADED" → Jarvis pode adoptar o contrato `OK/DEGRADED/OFFLINE/ERROR`.

### NÍVEL B — PATTERN
**Reproduzir contrato/arquitetura.**

Exemplo: "OpenClaw tem plugin manifest com lifecycle" → Jarvis pode criar `plugin.json` + `register/start/stop/health`.

### NÍVEL C — PORT
**Reescrever algoritmo pequeno no Jarvis.**

Exemplo: "OpenClaw tem failover chain com cooldown" → Portar lógica de cooldown para Python.

### NÍVEL D — SIDECAR
**Usar processo externo quando tecnologia exigir outro ecossistema.**

Exemplo: "WhatsApp via Baileys (Node.js)" → Sidecar Node.js restrito, communicates via HTTP com Jarvis Gateway.

---

## Reglas de Implementação

### Para cada gap:

1. **Verificar**: Jarvis já tem isso?
2. **Se SIM**: KEEP. Não mexer.
3. **Se JARVIS TEM PARCIALMENTE**: EXTEND. Adicionar apenas o que falta.
4. **Se JARVIS NÃO TEM**: Analisar OpenClaw e decidir nível A/B/C/D.
5. **NUNCA**: Substituir módulo inteiro sem necessidade extraordinária.

### Para cada decisão de reuso:

Obrigatório documentar:

```
WHAT TO REUSE:
  [componente/padrão específico]

WHY:
  [razão técnica concreta]

HOW IT ENTERS JARVIS:
  [implementação dentro da arquitetura Jarvis]

WHAT REMAINS JARVIS AUTHORITY:
  [o que continua sendo controlado pelo Jarvis]
```

---

## Exemplos de Aplicação

### Plugin Architecture

```
DECISION: ADAPT

WHAT TO REUSE:
  - Plugin manifest concept (name, version, capabilities, permissions)
  - Plugin lifecycle (register, start, stop, health)
  - Plugin registry with snapshots

WHY:
  Jarvis tem PluginLoader básico (192 linhas). OpenClaw tem 1122 files
  de plugin system. O conceito de manifest + lifecycle é valioso.

HOW IT ENTERS JARVIS:
  Python implementation dentro de jarvis_core/plugins/
  - plugin.json manifest
  - PluginBase class com register/start/stop/health
  - PluginRegistry extendido

WHAT REMAINS JARVIS AUTHORITY:
  - SecurityManager controla permissões
  - ToolRegistry controla tools
  - JarvisService controla execução
  - AuditLog registra tudo
```

### WebSocket Gateway

```
DECISION: PORT

WHAT TO REUSE:
  - Typed message envelope (JSON com type field)
  - Reconnection with exponential backoff
  - Keepalive ping/pong

WHY:
  Jarvis não tem WebSocket. OpenClaw tem protocolo maduro.
  WebSocket é prerequisite para PWA/mobile.

HOW IT ENTERS JARVIS:
  Python implementation com `websockets` library
  Dentro de jarvis_core/gateway/websocket.py
  Integrado com server_agent.py existente

WHAT REMAINS JARVIS AUTHORITY:
  - JarvisService processa comandos
  - SecurityManager valida
  - ToolRegistry gerencia tools
  - AuditLog registra
```

### Model Failover

```
DECISION: EXTEND

WHAT TO REUSE:
  - Provider cooldown pattern (state + last_failure_at + cooldown_seconds)
  - Recoverable states (RATE_LIMITED, TIMEOUT, DEGRADED)
  - Provider selection por profile

WHY:
  Jarvis ModelRouter já existe mas falta failover robusto.
  OpenClaw tem padrão maduro de cooldown + recovery.

HOW IT ENTERS JARVIS:
  Extensão de ModelRouter existente em model_router.py
  Adicionar: ProviderState enum, cooldown logic, recovery

WHAT REMAINS JARVIS AUTHORITY:
  - ModelRouter controla seleção
  - JarvisService controla execução
  - SecurityManager controla acesso
```

---

## O que NÃO Reusar

| Componente | Razão |
|-----------|-------|
| OpenClaw Gateway (runtime) | Jarvis tem server_agent.py |
| TypeScript/Node.js code | Jarvis é Python |
| OpenClaw Memory | Jarvis memory V2 é mais maduro |
| OpenClaw Voice | Jarvis voice pausado, não substituir |
| OpenClaw Windows Tools | Jarvis tem 38+ tools que OpenClaw não tem |
| OpenClaw Agents (runtime) | Jarvis já tem 11 agentes |
| OpenClaw Golden/MT5 | OpenClaw não tem trading |
| OpenClaw Plugin SDK (completo) | Portar conceitos, não o SDK |
| OpenClaw Docker patterns | Jarvis é desktop-first |
| OpenClaw UI | Jarvis tem studio_v7.html |

---

## Checklist de Reuso

Antes de reusar qualquer coisa do OpenClaw:

- [ ] Jarvis já tem isso? → KEEP
- [ ] Jarvis tem parcialmente? → EXTEND
- [ ] É conceito? → Nível A (IDEA)
- [ ] É padrão arquitetural? → Nível B (PATTERN)
- [ ] É algoritmo pequeno? → Nível C (PORT)
- [ ] Precisa de outro ecossistema? → Nível D (SIDECAR)
- [ ] Documentei WHAT/WHY/HOW/AUTHORITY?
- [ ] SecurityManager controla?
- [ ] AuditLog registra?
- [ ] ToolRegistry gerencia?
- [ ] Não estou criando segundo sistema paralelo?
