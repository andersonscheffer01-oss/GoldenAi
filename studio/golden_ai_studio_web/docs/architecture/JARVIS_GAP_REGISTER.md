# JARVIS GAP REGISTER

Baseline: `4195731`
Data: 2026-09-28
Natureza: registro de gaps descobertos em auditoria read-only.

## Taxonomy

- `WORKING_VALIDATED`: existe e tem evidencia de teste/uso suficiente para o escopo declarado.
- `WORKING_NOT_REAL_WORLD_VALIDATED`: caminho estrutural/testado, mas falta prova real ampla.
- `PARTIAL`: parte funcional com lacuna de ownership, cobertura ou integracao.
- `SCAFFOLD_ONLY`: contrato/catalogo/skeleton sem runtime integrado comprovado.
- `DEAD_OR_UNUSED`: artefato encontrado sem caminho ativo conhecido.
- `LEGACY`: preservado por compatibilidade ou historico, fora do caminho atual.
- `DUPLICATED`: capacidade com mais de um owner ativo ou quase-ativo.
- `MISSING`: capacidade nao encontrada no caminho canonicamente auditado.
- `UNKNOWN_REQUIRES_VALIDATION`: existencia indicada, mas o comportamento nao foi provado.

## Register

| ID | Area | Classification | Confidence | Evidence / gap |
|---|---|---|---:|---|
| G-001 | Launch/runtime | WORKING_VALIDATED | HIGH | Launchers chegam ao `server_agent.py`; single-instance e readiness existem. |
| G-002 | Jarvis core | WORKING_VALIDATED | HIGH | `DesktopCenter` cria um `JarvisService` e o reutiliza nas rotas. |
| G-003 | Orchestration | PARTIAL | HIGH | `CentralOrchestrator` existe, mas `server_agent.py` ainda possui caminhos diretos e shadow mode. |
| G-004 | Security | PARTIAL | HIGH | `jarvis_core.SecurityManager` ativo; `core.permissions.PermissionManager` tambem e importado pelo processo. |
| G-005 | Root permissions | DUPLICATED | HIGH | `core/permissions` e `jarvis_core/security.py` possuem owners diferentes. |
| G-006 | Audit | PARTIAL | HIGH | `jarvis_core.audit.AuditLog` e ativo; `core.audit.AuditLogger` permanece no stack raiz. |
| G-007 | Root audit | DUPLICATED | HIGH | Dois formatos/owners de audit convivem. |
| G-008 | Task scheduler | WORKING_VALIDATED | HIGH | Scheduler, retries, approvals, conditions e recovery possuem testes focados. |
| G-009 | Task DB | PARTIAL | HIGH | Schema V5 funciona, mas DBs paralelos existem. |
| G-010 | Computer Use missions | WORKING_VALIDATED | HIGH | Gates 6D, 7D e 8D documentam persistencia, retomada e closure. |
| G-011 | UI Automation | WORKING_VALIDATED | HIGH | UIA/vision grounding e protecao de alvo tem tests e gates reais anteriores. |
| G-012 | Browser | WORKING_NOT_REAL_WORLD_VALIDATED | MEDIUM | Read-only scope e browser tests existem; cobertura de sites/consentimentos reais e limitada. |
| G-013 | Desktop current | WORKING_VALIDATED | HIGH | `web_app.py` e `start_jarvis_desktop.bat` apontam ao caminho atual. |
| G-014 | Desktop V4 | LEGACY | HIGH | `app_v4.py`, `main_window_v4.py` e `start_jarvis_desktop_v4.bat` sao caminho separado e antigo. |
| G-015 | Voice service | PARTIAL | HIGH | TTS/SAPI e lifecycle existem; Gate 3A de mic falhou e Voice esta pausada. |
| G-016 | Realtime voice | WORKING_NOT_REAL_WORLD_VALIDATED | HIGH | Adaptadores, queues e barge-in tests existem; sinal de mic real nao foi validado. |
| G-017 | Memory legacy | LEGACY | HIGH | `jarvis_core/memory/manager.py` e DB legado continuam usados como compatibilidade. |
| G-018 | Memory V2 | WORKING_VALIDATED | HIGH | Engine V2, vault, knowledge graph e tests M1.x existem. |
| G-019 | Skills | WORKING_VALIDATED | MEDIUM | `SkillsRouter` categoriza tools e alimenta Planner/LLM. |
| G-020 | MCP | SCAFFOLD_ONLY | HIGH | Enum/definition e referencia Playwright MCP; cliente MCP Jarvis nao foi comprovado. |
| G-021 | Plugins | PARTIAL | HIGH | Loader raiz e registry externo existem; ownership canonicamente unico nao provado. |
| G-022 | Jarvis vision | WORKING_NOT_REAL_WORLD_VALIDATED | MEDIUM | `jarvis_core.vision`/tools locais existem; semantic vision real ampla nao foi executada. |
| G-023 | Root vision | LEGACY | HIGH | `core.vision.VisionService` permanece no stack raiz. |
| G-024 | File intelligence | WORKING_NOT_REAL_WORLD_VALIDATED | MEDIUM | DocumentService/Docling/PyMuPDF e attachment security existem; dataset real amplo falta. |
| G-025 | Root agents | SCAFFOLD_ONLY | MEDIUM | Agentes especializados possuem contratos, mas nao sao o runtime Jarvis principal. |
| G-026 | Research | WORKING_VALIDATED | HIGH | Tavily/EvidenceRecord/Gemini e market read-only foram cobertos em fases anteriores. |
| G-027 | MT5 read-only | WORKING_NOT_REAL_WORLD_VALIDATED | HIGH | Tools e testes de leitura existem; esta auditoria nao abriu MT5. |
| G-028 | MT5 trading | UNKNOWN_REQUIRES_VALIDATION | HIGH | `mt5_trader`, `position_manager` e `order_send` existem, sem validacao de trade real nesta fase. |
| G-029 | Mobile | MISSING | MEDIUM | PWA/LAN nao equivalem a cliente mobile dedicado validado. |
| G-030 | Personal integrations | MISSING | HIGH | WhatsApp/Telegram aparecem em routing, sem adapter funcional demonstrado. |
| G-031 | Model router | WORKING_VALIDATED | HIGH | Router canonico e politicas/provider adapters existem; providers foram testados em fases anteriores. |
| G-032 | Direct provider handlers | DUPLICATED | HIGH | `server_agent.py` mantem caminhos diretos alem do ModelRouter. |
| G-033 | Ollama local | WORKING_VALIDATED | HIGH | Ollama direto e Jarvis -> OmniRoute -> Ollama comprovados. |
| G-034 | STT | WORKING_NOT_REAL_WORLD_VALIDATED | HIGH | faster-whisper e contratos existem; Gate 3A bloqueado por sinal real baixo. |
| G-035 | Local TTS | WORKING_VALIDATED | HIGH | SAPI e provider contracts foram validados em gates documentados. |
| G-036 | Local vision model | WORKING_NOT_REAL_WORLD_VALIDATED | MEDIUM | qwen2.5vl path esta codificado; validacao real depende de modelo/ambiente. |
| G-037 | Configuration | PARTIAL | HIGH | `config/`, env, policies e launcher defaults nao estao descritos por um unico manifest. |
| G-038 | Database governance | PARTIAL | HIGH | Existem 12 DBs nomeados em roots distintos; nenhuma migracao foi autorizada. |
| G-039 | Test system | WORKING_VALIDATED | HIGH | Suite focada cobre tasks, browser, security, memory, research, voice e UIA. |
| G-040 | Canonical docs | LEGACY | HIGH | `docs/agent-context/README_CANONICAL_DOCS.md` marca parte da arvore como stale, e docs ativos ainda divergem. |
| G-041 | Historical server snapshot | DEAD_OR_UNUSED | HIGH | `server_agent_BEFORE_DASH_FIX_20260827.py` e snapshot, nao launch path. |

## Priority ordering

F1 refinou os gaps com dois achados de alta prioridade: `TaskManager(base_dir)` permite criacao relativa a roots arbitrarios em tooling/testes, e o legado `server_agent._execute_tool` autoriza acoes por `core.execution.ExecutionService` sem passar pelo `jarvis_core.SecurityManager`. Ambos devem ser tratados por diagnostico e adapter antes de qualquer migracao.

Validacao F1: regressao protegida sem hardware passou com `89 passed` e `3 subtests passed`. O caso `test_jarvis_memory_v2_runtime` teve uma falha de cleanup (`WinError 32`) ao remover DB temporario apos wiring de `JarvisService`; nenhum codigo foi alterado para mascarar esse achado.

### P0

- G-003/G-032: consolidar o ownership de orchestration/provider e reduzir handlers diretos.
- G-009/G-038: declarar e impor a politica de DB sem migrar automaticamente.
- G-004/G-005/G-006/G-007: estabelecer uma fronteira unica de security/audit.

### P1

- G-015/G-016/G-034: retomar Voice apenas no checkpoint do mic real.
- G-020/G-021/G-030: nao anunciar MCP/connectors como runtime completo sem adapter e gate.
- G-037/G-040: atualizar source of truth e launcher/config manifest.

### P2

- G-012/G-022/G-024/G-027/G-036: ampliar provas de mundo real com escopo controlado.
- G-029/G-030/G-028: somente iniciar apos prerequisitos de security/ownership.
