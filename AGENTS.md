# Golden AI — Regras Universais para Agentes

> **Este é o arquivo de autoridade principal.** Todos os agentes (Freebuff, Codex, Claude, etc.) DEVEM respeitar estas regras.
>
> `knowledge.md` contém contexto e conhecimento do projeto.
> A documentação governada canônica está exclusivamente em
> `C:\GoldenAI\studio\golden_ai_studio_web\docs\agent-context\`.
> A árvore `C:\GoldenAI\docs\agent-context\` é legada e não recebe novos handoffs.

---

## Identidade do Projeto

**Golden AI** é um sistema de IA local para trading algoritmico, desenvolvimento MQL5 e automação de PC. É um sistema de produção com trading real — NÃO é um projeto genérico.

- **Backend**: Python (server_agent.py, porta 8765)
- **Frontend**: HTML/JS/CSS single-file (studio_v7.html, dashboard.html)
- **IA**: Ollama local (qwen2.5-coder:14b) + APIs externas (OpenRouter, Cline, Gemini)
- **Trading**: MetaTrader 5 (mt5_connector.py)
- **Banco**: SQLite (golden_runtime.db)

---

## Regras Fundamentais

### 1. NÃO QUEBRE O SISTEMA DE TRADING

- Nunca altere lógica de entrada/saída de trades sem confirmação explícita
- Nunca altere gerenciamento de risco sem confirmação
- Nunca remova proteções de ordem
- Sempre preserve: stop loss, take profit, breakeven, trailing, limites diários
- **NUNCA altere lógica de entrada MQL5 quando a solicitação for somente gerenciamento**

### 2. NÃO EXPOSA SEGREDOS

NUNCA coloque em nenhum arquivo Markdown, handoff ou documentação:
- Senhas, API keys, tokens, credenciais, chaves privadas, cookies

Arquivos protegidos: `.env`, `config/api_keys.json`

### 3. PRESERVE O QUE EXISTE

- Não sobrescreva arquivos sem antes verificar `git status`
- **NÃO use `git reset`, `git clean`, `git checkout .`, `git restore .`**
- **Não apague ou restaure alterações do usuário**
- Antes de modificar arquivo importante, verifique `git diff`

### 4. VERIFIQUE ANTES DE IMPLEMENTAR

- Rode `python -c "import py_compile; py_compile.compile('arquivo.py')"` após alterar Python
- Verifique se o servidor inicia corretamente
- Verifique se o frontend carrega
- Não considere código pronto apenas porque "parece correto"

### 5. SEJA CONCISO

- Handoffs: máximo 200 linhas
- knowledge.md: máximo 300 linhas
- Skills: máximo 100 linhas

---

## Onde Encontrar Informação

| Preciso de... | Consulte... |
|---------------|-------------|
| Regras obrigatórias | `AGENTS.md` (este arquivo) |
| Contexto do projeto | `knowledge.md` |
| **Roteiro rápido (economia de tokens)** | **`C:\GoldenAI\vault\Segundo Cerebro\00_INDEX.md`** |
| Arquitetura | `studio/golden_ai_studio_web/docs/agent-context/` |
| Trabalho atual | `studio/golden_ai_studio_web/docs/agent-context/CURRENT_WORK.md` |
| Último handoff | `studio/golden_ai_studio_web/docs/agent-context/HANDOFF.md` |
| Handoffs anteriores | `studio/golden_ai_studio_web/docs/agent-context/handoffs/` |
| Decisões tomadas | `studio/golden_ai_studio_web/docs/agent-context/DECISIONS.md` |
| Problemas conhecidos | `studio/golden_ai_studio_web/docs/agent-context/KNOWN_ISSUES.md` |
| Skills disponíveis | `.agents/skills/*/SKILL.md` |
| Config Codex | `.codex/instructions.md` |

---

## Segundo Cerebro (Context Index)

Para tarefas que exigem contexto de projeto, ANTES de varrer o repositório:

1. Ler `C:\GoldenAI\vault\Segundo Cerebro\00_INDEX.md`
2. Identificar o ramo relevante (projeto/domínio)
3. Abrir o índice correspondente
4. Abrir `CURRENT_STATE` / `FILE_MAP` / `DECISIONS` somente se necessário
5. Só então abrir os arquivos de código

**NÃO** ler todo o Vault, todos os índices, ou todo o repositório sem necessidade.
**NÃO** carregar áreas não relacionadas à tarefa.
**Fast path**: para tarefas triviais (rodar teste, abrir arquivo, corrigir typo), vá direto ao código.

Fallback: se o Segundo Cerebro estiver ausente/stale, usar `docs/agent-context/`.

---

## Antes de Qualquer Tarefa

1. Ler este `AGENTS.md`
2. Ler `knowledge.md`
3. Ler `studio/golden_ai_studio_web/docs/agent-context/CURRENT_WORK.md`
4. Ler `studio/golden_ai_studio_web/docs/agent-context/HANDOFF.md` (se existir)
5. Verificar `git status`
6. Carregar skill apropriada de `.agents/skills/`

---

## Handoff entre Agentes

Quando uma tarefa precisar ser transferida:

1. Ler `.agents/skills/golden-handoff/SKILL.md` (template)
2. Criar arquivo datado em `studio/golden_ai_studio_web/docs/agent-context/handoffs/`
3. Atualizar `studio/golden_ai_studio_web/docs/agent-context/HANDOFF.md` como ponteiro
4. Atualizar `studio/golden_ai_studio_web/docs/agent-context/CURRENT_WORK.md`

**O agente receptor DEVE:**
- Conferir informações contra o código atual
- Verificar `git status` e `git diff`
- NUNCA tratar memória/handoff como verdade absoluta
- Verificar que arquivos mencionados existem

---

## Estrutura do Projeto

```
C:\GoldenAI\
├── AGENTS.md                    ← ESTE ARQUIVO (autoridade principal)
├── knowledge.md                 ← Contexto do projeto
├── .agents/skills/*/SKILL.md    ← Skills reutilizáveis
├── .codex/instructions.md       ← Config Codex
├── docs/agent-context/          ← Documentação governada
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── CURRENT_WORK.md
│   ├── HANDOFF.md               ← Ponteiro do último handoff
│   ├── KNOWN_ISSUES.md
│   └── handoffs/                ← Histórico de handoffs
├── vault/Segundo Cerebro/       ← Context Index (economia de tokens)
│   ├── 00_INDEX.md              ← Roteador principal
│   ├── Projetos/Golden/         ← Índice do projeto principal
│   ├── Trading/                 ← Domínio trading
│   ├── Coding/                  ← Domínio coding
│   └── ...
├── studio/golden_ai_studio_web/ ← Frontend + Backend
├── core/                        ← Módulos centrais (25+)
├── agents/                      ← Agentes especializados (11)
├── config/                      ← Configurações (PROTEGIDO)
├── data/                        ← Dados e estatísticas
├── projetos/                    ← Robôs MQL5
└── jarvis/                      ← Golden Jarvis
```

---

## Portas e Serviços

| Serviço | Porta |
|---------|-------|
| Golden AI Studio | 8765 |
| Golden Jarvis | 8780 |
| Ollama | 11434 |

---

## Regras por Tecnologia

### MQL5
- Nunca altere lógica de entrada sem confirmação
- Separe: ENTRADA / GERENCIAMENTO / RISCO / STOP / TAKE / BREAKEVEN / TRAILING
- Risco percentual: verifique balance/equity, stop em pontos, tick size, tick value, contract size, volume
- Sempre compile após alteração
- Use `projetos/` para desenvolvimento

### Python
- Identifique dependências antes de alterar
- Não remova endpoints HTTP existentes
- Não altere assinaturas de funções públicas
- Rode syntax check após alterações
- Teste inicialização do componente

### HTML/JS
- Não quebre endpoints existentes
- Verifique se o JS compila
- Não remova funções JavaScript

---

## Segurança

- NÃO leia, exponha ou grave segredos em documentação
- NÃO execute comandos destrutivos automaticamente
- NÃO altere firewall, registro, serviços do Windows ou credenciais sem autorização
- NÃO execute `npm install -g`, `pip install global`, `winget`, `choco` sem informar

---

## Compatibilidade

### Freebuff
- Lê: `AGENTS.md`, `knowledge.md`, `.agents/skills/*/SKILL.md`
- Handoffs em `docs/agent-context/`

### Codex
- Lê: `AGENTS.md`, `.codex/instructions.md`
- Handoffs em `docs/agent-context/`

### Ambos
- Respeitam as mesmas regras (este arquivo)
- Compartilham contexto via `docs/agent-context/`
- Usam as mesmas skills
