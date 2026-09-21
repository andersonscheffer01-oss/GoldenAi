# Handoff - Backend Golden Jarvis Consolidado

## Estado

CentralOrchestrator modular, providers reais, ModelRouter, SkillsRouter, Planner e TaskManager
estão integrados. O arquivo concorrente `jarvis_core/orchestrator.py`, deixado incompleto, foi
removido após confirmação de que os imports usam o pacote `jarvis_core/orchestrator/`.

O fluxo multi-step é:
`Orchestrator -> Planner -> TaskManager -> JarvisService -> SecurityManager -> ToolRegistry -> AuditLog`.
Jobs rodam em background, podem ser cancelados e entram em `WAITING_CONFIRMATION` quando a
camada de segurança exige confirmação. Planos inválidos falham fechados.

## Providers e modelos

- GENERAL/CODING: Groq `qwen/qwen3.8-27b`.
- DEEP/Planner: Groq `openai/gpt-oss-120b`.
- FAST: Gemini configurado pela policy.
- Fallback cloud: OpenRouter, conforme a cadeia do perfil.
- OFFLINE: Ollama `qwen2.5-coder:14b`.
- VISION: Ollama `qwen2.5vl:7b`.
- MEMORY: `nomic-embed-text`, sem alteração ou reindexação.

Adapters reutilizam os clientes existentes; nenhum provider executa tools. Smoke controlado:
Groq respondeu 429/RATE_LIMITED, OpenRouter respondeu com sucesso, Gemini respondeu 503 e
Ollama respondeu com sucesso. O ModelRouter confirmou fallback Groq -> OpenRouter.

## Rollout e segurança

`JARVIS_ORCHESTRATOR_V2` permanece `shadow` por padrão. Nesse modo o plano pode ser criado e
persistido, mas não é executado. Em `on`, o Brain usa o ModelRouter e tarefas planejadas seguem
o executor seguro. Conteúdo SECRET fica local, tools são filtradas por skill e retry é limitado.
O teste live criou “Preparação do Ambiente de Trading” em `QUEUED`, sem executar etapas.

## Validação

Suíte relevante: `96 passed, 50 subtests passed`. Inclui hardening, memória, voz, market data,
orchestrator, model router, skills router, planner, TaskManager e integração. Não há regressão
conhecida. Aviso opcional: plugin `system_info.py` precisa de `psutil` quando essa extensão for usada.

## Limitações conhecidas

- O rollout ainda requer ativação explícita para `on` após observação do shadow.
- A disponibilidade dos providers depende de cota, credenciais e rede; Gemini estava instável.
- Recuperação automática de provider degradado ainda não possui health probe periódico.
- Skills ainda não implementadas permanecem indisponíveis e não devem simular sucesso.

## Próxima fase

Golden Jarvis Desktop, app nativo Windows em PySide6/Qt: tray, wake word, chat/voz,
drag-and-drop, tasks, status dos providers e CPU/RAM/GPU, Radar, MT5, Skills, Config e Developer
Mode. A referência visual definida no briefing deve ser preservada. Não iniciar Computer Use,
WhatsApp real, trading, browser ou UI web paralela sem nova missão.
