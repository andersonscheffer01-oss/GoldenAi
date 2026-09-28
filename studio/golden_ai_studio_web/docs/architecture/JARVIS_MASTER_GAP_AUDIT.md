# JARVIS / GOLDEN MASTER GAP AUDIT

Data da auditoria: 2026-09-28
Baseline oficial: `4195731` (`docs: record real mic VAD gate failure`)
Escopo: inventario arquitetural read-only, reuse-first. Nenhum hardware foi aberto.

## Veredito

`PASS_WITH_RESTRICTIONS`

O produto possui um caminho Jarvis funcional e uma base extensa de testes, mas ainda nao esta consolidado como um unico plano arquitetural. O caminho ativo usa `server_agent.py` -> `desktop_center.py` -> um `JarvisService` compartilhado, com o mesmo servico tambem entregue ao Gateway e ao VoiceService. Ao mesmo tempo, o processo importa e mantem handlers do stack raiz (`core.permissions`, `core.execution`, `plugins.plugin_loader`, `core.audio`, `core.video`, `core.documents`) e o servidor ainda contem rotas diretas legadas.

## Metodo e launch path real

O launch path observado e:

```text
start_golden.bat / ABRIR_GOLDEN_AI_STUDIO*.bat
  -> C:\GoldenAI\.venv\Scripts\python.exe
  -> studio\golden_ai_studio_web\server_agent.py --port 8765
  -> desktop_center.DESKTOP_CENTER
  -> JarvisService(C:\GoldenAI\studio\golden_ai_studio_web)
  -> TaskManager + SecurityManager + AuditLog + CentralOrchestrator
```

`start_server()` tambem inicia, no mesmo processo, o monitor, o VoiceService e o Gateway. `jarvis_desktop\web_app.py` e o launcher Desktop atual sao caminhos de apresentacao; `app_v4.py` e `start_jarvis_desktop_v4.bat` sao caminhos legados.

Classificacoes usam somente o taxonomy solicitado. Cada item tem uma classificacao primaria; a evidencia distingue existencia de validacao real.

## Arquitetura invariants

| Invariante | Resultado | Confianca | Evidencia |
|---|---|---:|---|
| ONE_JARVIS | PARTIAL | HIGH | Um `JarvisService` e compartilhado pelo `DesktopCenter`, mas handlers diretos e o stack raiz coexistem no mesmo servidor. |
| ONE_CORE | PARTIAL | HIGH | `jarvis_core` e o caminho Jarvis atual; `core/`, `app/` e `agents/` continuam importaveis e alguns sao usados por `server_agent.py`. |
| ONE_SECURITY_MODEL | PARTIAL | HIGH | O caminho Jarvis usa `jarvis_core.security.SecurityManager`; o mesmo processo instancia `core.permissions.PermissionManager` para rotas antigas. |
| ONE_TASK_SYSTEM | PARTIAL | HIGH | `JarvisService` usa `jarvis_core.task_manager.TaskManager`, mas ha instancias e bancos em outros roots. |
| ONE_CANONICAL_TASK_DB | PARTIAL | HIGH | O path canonicamente pretendido e o workspace `jarvis/golden_tasks.db`; outros DBs identicos por nome existem e o `base_dir` determina qual e aberto. |
| ONE_AUDIT_MODEL | PARTIAL | HIGH | `jarvis_core.audit.AuditLog` e ativo no Jarvis; `core.audit.AuditLogger` permanece ativo no stack raiz. |

## Subsystem summary

| Subsystem | Classificacao | Confianca | Estado resumido |
|---|---|---:|---|
| Core | PARTIAL | HIGH | `JarvisService` e real; Core V3/root nao esta completamente consolidado. |
| Security | PARTIAL | HIGH | SecurityManager Jarvis e fail-closed em gates, mas ha segunda camada raiz. |
| Audit/observability | PARTIAL | HIGH | AuditLog SQLite ativo e sanitiza payloads; logger raiz ainda existe. |
| Tasks/scheduler | WORKING_VALIDATED | HIGH | TaskManager, scheduler, retries, approvals e durable state tem testes dedicados. |
| Computer Use | WORKING_VALIDATED | HIGH | Missions 6D/7D/8D, UIA, recovery e gates foram validados; hardware nao foi reaberto nesta auditoria. |
| Desktop Control Center | WORKING_VALIDATED | HIGH | DesktopCenter compartilha o JarvisService canonicamente. |
| Web | WORKING_VALIDATED | HIGH | Studio HTTP/SSE/HTTPS possui launchers e validacoes anteriores; handlers antigos ainda aumentam risco. |
| Voice | PARTIAL | HIGH | Provider/TTS local validado; Gate 3A bloqueado por `REAL_MIC_SIGNAL_PATH_INCONSISTENCY`. |
| Memory/RAG | PARTIAL | HIGH | Memory V2 e testes existem, mas coexistem manager legado, V2, root memory e varios DBs. |
| Skills | WORKING_VALIDATED | MEDIUM | `SkillsRouter` e catalogo de tools existem; cobertura funcional ampla ainda e desigual. |
| MCP | SCAFFOLD_ONLY | HIGH | Ha enum/definition e referencia Playwright MCP; nao foi encontrado cliente MCP canonicamente integrado ao Jarvis. |
| Plugins/connectors | PARTIAL | HIGH | `plugins.plugin_loader` e `core.tools.external` coexistem; ownership runtime nao esta consolidado. |
| Vision | WORKING_NOT_REAL_WORLD_VALIDATED | MEDIUM | `jarvis_core.vision` e tools estruturadas existem; validacao semantica real abrangente nao foi feita. |
| File intelligence | WORKING_NOT_REAL_WORLD_VALIDATED | MEDIUM | Docling/PyMuPDF/DOCX/PPTX/XLSX e AttachmentService existem; cobertura de documentos reais e limitada. |
| Agents | SCAFFOLD_ONLY | MEDIUM | Agentes raiz possuem contratos/skeletons; nao sao o caminho principal do Jarvis runtime. |
| Finance | MISSING | HIGH | Integracoes pessoais de gastos, bancos, faturas e orcamentos nao existem no caminho canonicamente validado. |
| MT5 | PARTIAL | HIGH | Leitura/market intelligence foi validada; trading e ordens permanecem sem validacao real nesta auditoria. |
| Mobile | MISSING | MEDIUM | Ha PWA/rotas LAN e menções a mobile, mas nao ha cliente mobile dedicado validado. |
| Personal integrations | MISSING | HIGH | WhatsApp/Telegram aparecem em routing/catalogo, mas nao ha adapter funcional validado. |
| Model/LLM layer | DUPLICATED | HIGH | ModelRouter canonico existe, mas server_agent ainda possui caminhos diretos Gemini/Groq/Ollama. |
| Local AI | WORKING_VALIDATED | HIGH | Ollama direto e Jarvis -> OmniRoute -> Ollama foram validados em fases anteriores. |
| Configuration | PARTIAL | HIGH | `config/`, env e policies coexistem; nao ha manifest unico de runtime por app. |
| Databases | PARTIAL | HIGH | SQLite local funciona, mas existem DBs de tasks/memory/runtime em roots paralelos. |
| Tests | WORKING_VALIDATED | HIGH | Ha suite extensa e gates especializados; muitos testes sao mocks e nao equivalem a validacao de mundo real. |
| Documentation | LEGACY | HIGH | `README_CANONICAL_DOCS.md` marca a arvore antiga como stale, mas varios docs ativos ainda contradizem o runtime atual. |

## Runtime paths and ownership

### Core, orchestration and model routing

`JarvisService.__init__` cria o `SecurityManager`, `AuditLog`, memory legacy/V2, `TaskManager`, `CentralOrchestrator` e `JarvisRuntimeCoordinator`. O `TaskManager` recebe o mesmo `base_dir` do DesktopCenter e resolve `base_dir/jarvis/golden_tasks.db`.

O `ModelRouter` canonico esta em `jarvis_core/orchestrator/model_router.py`, mas `server_agent.py` tambem contem funcoes e rotas diretas de providers. Resultado: routing funcional, ownership duplicado.

### Security and audit

O Jarvis canonico usa `jarvis_core.security.SecurityManager` e `jarvis_core.audit.AuditLog`; este ultimo sanitiza chaves sensiveis e payloads binarios. O processo ativo tambem importa `core.permissions.PermissionManager`, `core.execution.ExecutionService` e `plugins.plugin_loader`. Isso impede afirmar um unico modelo de seguranca/auditoria sem consolidacao futura.

### Tasks and databases

O schema canonico de tasks e `TaskDatabase.SCHEMA_VERSION = 5`, com `tasks`, `task_steps`, `task_events`, `background_tasks`, `task_runs` e `task_approvals`. O banco pretendido pelo handoff e:

`C:\GoldenAI\studio\golden_ai_studio_web\jarvis\golden_tasks.db`

Nenhuma migracao, limpeza ou rebind foi executado. A lista de DBs mostra roots paralelos, alguns criados por execucoes standalone/testes. Isso e uma restricao de governanca, nao uma autorizacao para migrar agora.

### Computer Use, web and desktop

Computer Use tem tools de mouse/keyboard, UI Automation, vision grounding, path-not-found recovery, stale-target protection, mission checkpoints e scheduler duravel. Os gates anteriores provaram missoes reais de Notepad/Chrome e scheduler, com aprovacoes. O caminho Desktop atual e `jarvis_desktop.web_app`; V4 permanece como arvore legacy explicitamente separada.

### Voice checkpoint

Voice foi auditado, nao continuado. O baseline `4195731` registra `VOICE_STATUS: PAUSED_WITH_KNOWN_RESTRICTION` e bloqueio `REAL_MIC_SIGNAL_PATH_INCONSISTENCY`/`MIC_SIGNAL_TOO_LOW`. Nenhum microfone, speaker ou camera foi aberto nesta auditoria.

## High priority findings

1. **P0 - Ownership split:** `server_agent.py` ainda e um monolito com handlers diretos e imports do stack raiz ao lado do `JarvisService` canonicamente compartilhado.
2. **P0 - Data split:** multiplos `golden_tasks.db`, `golden_memory.db` e `golden_runtime.db` existem fora do path canonicamente declarado.
3. **P1 - Security/audit split:** `core.permissions`/`core.audit` e `jarvis_core.security`/`jarvis_core.audit` precisam de fronteira formal ou depreciação.
4. **P1 - Voice gate:** voz nao esta pronta para fechamento; a restricao do microfone permanece o checkpoint oficial.
5. **P1 - Documentation drift:** `CORE_V3_ARCHITECTURE.md`, `ARCHITECTURE.md`, `JARVIS_VOICE_SERVICE.md` e docs raiz apresentam estados/fases anteriores e nao devem ser usados isoladamente como source of truth.
6. **P2 - Provider/plugin/MCP ambiguity:** catalogo externo, plugins, skills e routing descrevem capacidades que nao possuem a mesma prova de runtime.

## Reuse-first decisions

Audits e handoffs reutilizaveis encontrados:

- `docs/architecture/JARVIS_LOCAL_TTS_PROVIDER_AUDIT.md`: gates de TTS/SAPI/voz.
- `docs/agent-context/handoffs/`: Memory V2/M1.x, voice service, data e model benchmark.
- `docs/CODEX_CAPABILITY_AUDIT_V1.md` e `V2.md`: capability/test runner/sandbox.
- `docs/VISION_ATTACHMENTS_EXTERNAL_ACCESS_AUDIT_V1.md`: attachments, external access e vision.
- `AUDITORIA_OMNIROUTE.md` (preexistente, fora do commit desta auditoria): integracao e limites OmniRoute.

Decisoes: reutilizar `JarvisService`, `TaskManager`, `SecurityManager`, `AuditLog`, `ModelRouter`, `SkillsRouter`, Computer Use mission store e os adapters existentes. Nao criar novo scheduler, novo Core, novo banco, novo provider ou novo sistema de permissao.

## Inventory counts

Contagem primaria de 41 unidades auditadas no registro complementar:

```yaml
WORKING_VALIDATED: 14
WORKING_NOT_REAL_WORLD_VALIDATED: 7
PARTIAL: 7
SCAFFOLD_ONLY: 2
DEAD_OR_UNUSED: 1
LEGACY: 4
DUPLICATED: 3
MISSING: 2
UNKNOWN_REQUIRES_VALIDATION: 1
```

## Safety boundary

Nenhum pacote foi instalado, modelo baixado, conta acessada, trade executado, mensagem enviada, hardware aberto, arquivo runtime removido ou `device_registry.json` tocado. O audit foi de leitura; o unico output pretendido sao os documentos desta tarefa.

## Next gate

`REAL_MIC_SIGNAL_PATH_INVESTIGATION` permanece o proximo gate oficial de Voice, mas esta auditoria nao o executa. Antes de qualquer nova fase de produto, o roadmap recomenda consolidar ownership e declarar o banco canonicamente sem migrar dados automaticamente.
