# Golden Jarvis Central Orchestrator

## Fluxo

`entrada -> CentralOrchestrator -> SkillsRouter -> ModelRouter -> ProviderAdapter -> Planner (quando necessário) -> TaskManager -> JarvisService -> SecurityManager -> ToolRegistry -> AuditLog`

Existe um único Jarvis e um único executor. O Orchestrator produz somente decisão tipada;
nenhum provider executa ferramentas. O Golden continua validando, autorizando e auditando.

## Componentes

- `OrchestratorDecision`: intent, route, confidence, flags de IA/planning/confirmação/
  esclarecimento, skill, perfil de modelo, steps, reason code, tools permitidas e classificação.
- `SkillsRouter`: registro de domínios e filtro dinâmico do catálogo do Registry.
- `ModelRouter`: perfis FAST, GENERAL, DEEP, CODING, VISION e OFFLINE; providers
  desacoplados; estados de saúde; retry transitório máximo 1; fallback local.
- `PlanStep`: contrato integrado com dependências, status, cancelamento e background.
- Política de dados: PUBLIC, INTERNAL, SENSITIVE e SECRET. SECRET nunca seleciona cloud.

## Rollout

Feature flag `JARVIS_ORCHESTRATOR_V2`: `off`, `shadow`, `on`. Padrão: `shadow`.

- off: Brain legado sem restrição por rota.
- shadow: decisão e auditoria sanitizada, sem alterar execução.
- on: fast path determinístico, CLARIFY obrigatório para referência ambígua e catálogo
  filtrado pela skill. Ferramenta fora da skill é rejeitada fail-closed.

## Modelos centralizados

Configuração inicial em `policies.py`: Groq Qwen 3.8 27B para geral/código,
Groq GPT-OSS 120B para deep/planner, Gemini para fast, Ollama Qwen 2.5 Coder 14B offline e
Qwen 2.5 VL 7B para visão. Nomic permanece exclusivo da memória.

Os adapters reais reutilizam os clientes existentes de Groq, OpenRouter, Gemini e Ollama.
Em `on`, o Brain usa o ModelRouter. Em `shadow`, o fluxo oficial continua legado enquanto
decisões e planos são validados sem executar ações.

## Segurança

Conteúdo externo não participa da classificação da instrução do usuário. Segredos não são
enviados a providers cloud. Auditoria do shadow registra apenas rota, confiança, skill,
perfil, provider/fallback e latência, nunca prompt, credencial ou payload.

## Testes

Cobrem rotas, ambiguidade, tool inexistente, injection externa, filtro de tools, rollout,
429, timeout, cloud offline, retry limitado, SECRET local-only, Planner e execução multi-step.
