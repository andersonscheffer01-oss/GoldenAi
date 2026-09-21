# OpenClaw Component Map

> Referência: commit `ecc4c992` (main, shallow clone)
> License: MIT (OpenClaw Foundation, 2026)
> Linguagem: TypeScript (Node.js, pnpm workspace)

---

## Visão Geral

OpenClaw é um assistente pessoal open-source com ~44.500 arquivos.
Arquitetura: **Gateway central + Plugins + Channels + Extensions**

---

## Estrutura Principal

```
openclaw/
├── src/                          # Core do gateway (123 módulos)
│   ├── gateway/                  # Gateway server (1629 entries!)
│   ├── agents/                   # Agent runtime (1690 entries!)
│   ├── plugins/                  # Plugin system (1122 entries!)
│   ├── security/                 # Security audit (92 entries)
│   ├── sessions/                 # Session management (90 entries)
│   ├── cron/                     # Scheduler (214 entries)
│   ├── tasks/                    # Task registry (134 entries)
│   ├── memory/                   # Memory (3 entries - mínimo)
│   ├── channels/                 # Channel abstraction
│   ├── llm/                      # LLM integration
│   ├── mcp/                      # MCP protocol
│   ├── web/                      # Web tools
│   ├── browser-lifecycle-cleanup # Browser lifecycle
│   └── ...
├── extensions/                   # 168 extensões/plugins
│   ├── browser/                  # Browser automation
│   ├── whatsapp/                 # WhatsApp channel
│   ├── discord/                  # Discord channel
│   ├── telegram/                 # Telegram channel
│   ├── slack/                    # Slack channel
│   ├── anthropic/                # Anthropic provider
│   ├── openai/                   # OpenAI provider
│   ├── ollama/                   # Ollama provider
│   ├── memory-core/              # Memory plugins
│   ├── memory-lancedb/           # Vector DB memory
│   ├── cua-computer/             # Computer use
│   ├── talk-voice/               # Voice
│   └── ... (168 total)
├── packages/                     # Shared packages (23)
│   ├── plugin-sdk/               # Plugin SDK
│   ├── gateway-protocol/         # Gateway protocol
│   ├── agent-core/               # Agent core
│   ├── llm-core/                 # LLM core
│   └── ...
├── skills/                       # Skill definitions
├── ui/                           # Control UI
├── apps/                         # Native apps (iOS, Android, macOS)
├── docs/                         # Documentation
├── test/                         # Tests
└── config/                       # Configuration
```

---

## Gateway (src/gateway/)

**1629 entries** — O componente maior do OpenClaw.

### Contratos Principais

| Conceito | Arquivos Chave | Descrição |
|----------|---------------|-----------|
| Server | `server.ts`, `server-*.ts` | HTTP + WebSocket server |
| Auth | `auth.ts`, `auth-*.ts` | Multi-mode authentication |
| Sessions | `session-*.ts` | Session lifecycle completa |
| Devices | `device-*.ts` | Device pairing, auth, revocation |
| Plugins | `server-plugin-*.ts` | Plugin loading, reload, lifecycle |
| Channels | `server-channels.ts` | Channel management |
| Cron | `server-cron-*.ts` | Scheduled jobs |
| Health | `health/` | Health probes |
| WebSocket | `websocket-protocol.ts` | Typed WS protocol |
| Approvals | `exec-approval-*.ts`, `operator-approval-*.ts` | Execution approvals |
| Control UI | `control-ui-*.ts` | Web dashboard |

### Fluxo de Requisição

```
Client → WebSocket/HTTP
  → Auth (token/device/pairing)
    → Session resolution
      → Agent dispatch
        → Tool execution
          → Security check
            → Approval (se necessário)
              → Result
```

---

## Agent System (src/agents/)

**1690 entries** — Sistema de agentes embeddado.

### Componentes Chave

| Componente | Arquivos | Descrição |
|-----------|---------|-----------|
| Embedded Agent | `embedded-agent*.ts` | Agent runner principal |
| Tool System | `agent-tools*.ts`, `bash-tools*.ts` | Tool definitions + execution |
| Model Selection | `model-*.ts` | Model catalog, routing, fallback |
| Auth | `model-auth*.ts`, `auth-profiles*.ts` | Provider authentication |
| Sandbox | `sandbox*.ts` | Code execution sandbox |
| MCP | `mcp-*.ts` | Model Context Protocol |
| Skills | `skill-*.ts` | Skill system |
| Compaction | `compaction*.ts` | Context window management |
| Prompt | `system-prompt*.ts`, `prompt-*.ts` | Prompt composition |

### Tool Execution Flow

```
Agent Tool Call
  → Tool Policy Check
    → Security Validation
      → Approval Check (se necessário)
        → Execution (bash/file/web/etc)
          → Result Processing
            → Memory Write (se aplicável)
```

---

## Plugin System (src/plugins/)

**1122 entries** — Sistema de plugins mais maduro.

### Ciclo de Vida

```
Discovery (manifest scan)
  → Installation (npm/git)
    → Activation (config-based)
      → Runtime (lifecycle hooks)
        → Reload (hot-reload)
          → Uninstall
```

### Conceitos Chave

| Conceito | Descrição |
|----------|-----------|
| Manifest | Plugin metadata + contracts |
| Registry | Plugin registry com snapshots |
| Lifecycle | start/stop/health/reload |
| Permissions | Tool grants, scope isolation |
| Hooks | before/after tool call, agent reply |
| SDK | Plugin SDK for extensions |
| Bundled | Built-in plugins |
| External | npm-installed plugins |

### Plugin Types

- **Channel plugins**: Discord, WhatsApp, Telegram, etc.
- **Provider plugins**: Anthropic, OpenAI, Ollama, etc.
- **Capability plugins**: Browser, Memory, Voice, etc.
- **Tool plugins**: Custom tools

---

## Security (src/security/)

**92 entries** — Security audit system.

### Checks

| Check | Descrição |
|-------|-----------|
| Gateway auth | Authentication modes |
| Plugin trust | Plugin code safety |
| Exec sandbox | Command execution safety |
| Filesystem | File access policies |
| Dangerous flags | Config flag analysis |
| Model hygiene | Model reference validation |
| Channel metadata | Channel security |
| External content | Untrusted content handling |

### Severity Levels

- `INFO` — Informational
- `WARNING` — Potential issue
- `HIGH` — Significant risk
- `CRITICAL` — Immediate action needed

---

## Sessions (src/sessions/)

**90 entries** — Session management.

### Conceitos

| Conceito | Descrição |
|----------|-----------|
| Session lifecycle | Create, run, pause, resume, delete |
| History | Conversation history + transcripts |
| Compaction | Context window management |
| Model overrides | Per-session model selection |
| Sharing | Session sharing between users |
| Recovery | Session recovery on restart |

---

## Cron/Scheduler (src/cron/)

**214 entries** — Job scheduling system.

### Funcionalidades

| Feature | Descrição |
|---------|-----------|
| Cron expressions | Standard cron scheduling |
| Heartbeat | Periodic health checks |
| Delivery | Job result delivery to channels |
| Isolated agents | Independent agent execution |
| Run history | Job execution history |
| Failure alerts | Notification on failures |

---

## Tasks (src/tasks/)

**134 entries** — Task registry.

### Conceitos

| Conceito | Descrição |
|----------|-----------|
| Task registry | Central task tracking |
| Task flow | Multi-step task orchestration |
| Progress | Task progress tracking |
| Cancellation | Task cancellation |
| Retention | Task history retention |

---

## Extensions (168 total)

### Channels (20+)
Discord, WhatsApp, Telegram, Slack, Teams, Signal, iMessage, IRC, Matrix, LINE, etc.

### AI Providers (30+)
Anthropic, OpenAI, Google, Groq, Ollama, LMStudio, DeepSeek, Mistral, etc.

### Capabilities
- **Browser**: Chrome extension + Playwright
- **Voice**: Talk voice, TTS, STT
- **Memory**: Core, LanceDB, Wiki
- **Computer Use**: CUA computer
- **Media**: Image/video/music generation
- **Web**: Search, fetch, readability

---

## Observações para Jarvis

1. **Gateway é o coração** — Mas Jarvis já tem server_agent.py
2. **Plugin system é massivo** — 1122 files; portar conceitos, não código
3. **Security é extensivo** — 92 files de audit; padrões úteis
4. **Memory é mínimo** — Jarvis memory V2 é mais maduro
5. **Sessions são complexas** — 90 files; adaptar conceitos
6. **Cron é maduro** — 214 files; scheduler pattern valioso
7. **168 extensions** — Ecossistema vasto; referência para plugin architecture
