# 🏗️ Arquitetura do Golden AI

## Visão Geral

Golden AI é um agente de IA local com acesso completo ao sistema do usuário, projetado para trading algoritmico e desenvolvimento de robôs MQL5.

## Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────┐
│                    USUÁRIO                              │
│              (Browser / Terminal)                       │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/SSE
┌──────────────────────▼──────────────────────────────────┐
│                 STUDIO WEB                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  server_    │  │  studio_v7   │  │  streaming    │  │
│  │  agent.py   │  │  .html       │  │  (SSE)        │  │
│  └──────┬──────┘  └──────────────┘  └───────────────┘  │
└─────────┼───────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│              PERMISSION MANAGER (core/)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ can_read │  │ can_write│  │ can_exec │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────┬───────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│              TOOL REGISTRY (core/tools/)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ execute  │  │ register │  │ list     │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────┬───────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│              SERVIÇOS (core/)                            │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐           │
│  │Browser │ │Document│ │ Audio  │ │ Vision │           │
│  └────────┘ └────────┘ └────────┘ └────────┘           │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐           │
│  │ Memory │ │Internet│ │  MT5   │ │  PDF   │           │
│  │(Qdrant)│ │        │ │        │ │(PyMuPDF│           │
│  └────────┘ └────────┘ └────────┘ └────────┘           │
└─────────┬───────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│              OLLAMA (localhost:11434)                    │
│  ┌──────────────────────────────────────────┐           │
│  │  qwen2.5-coder:14b (ou outro modelo)    │           │
│  └──────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

## Módulos

### app/modules/ (14 módulos)

| Módulo | Responsabilidade |
|--------|------------------|
| `context.py` | Estado compartilhado (CFG, SERVICES, SESSION) |
| `utils.py` | Funções utilitárias (normalização, hashing) |
| `mt5.py` | Operações MetaTrader 5 |
| `files.py` | Operações de arquivo |
| `intent.py` | Classificação de intenção |
| `internet.py` | Chat de internet |
| `browser.py` | Wrappers de mídia |
| `panel.py` | Painel de comandos |
| `market_chat.py` | Chat de mercado |
| `memory_chat.py` | Chat de memória |
| `media_chat.py` | Chat de mídia |
| `quant_chat.py` | Chat quant |
| `report.py` | Relatórios e estado |
| `audit_deterministic.py` | Auditoria determinística |
| `auto_fix.py` | Correção automática |

### core/ (25 módulos)

| Módulo | Responsabilidade |
|--------|------------------|
| `permissions/` | Sistema de permissões |
| `tools/` | Registry de ferramentas |
| `memory/` | Memória vetorial (Qdrant) |
| `audit/` | Auditoria |
| `browser/` | Browser headless |
| `documents/` | Extração de documentos |
| `audio/` | Transcrição (Whisper) |
| `video/` | Análise de vídeo |
| `vision/` | Análise de imagens |
| `internet/` | Busca web |
| `computer/` | Info do sistema |
| `config/` | Configuração |
| `models/` | Roteamento de modelos |
| `safety/` | Políticas de segurança |
| `coding/` | Agente de código |
| `execution/` | Execução de comandos |
| `intent/` | Classificação de intenção |
| `activity/` | Atividade do usuário |
| `attachments/` | Anexos |
| `jobs/` | Trabalhos assíncronos |
| `project_intelligence/` | Inteligência de projeto |
| `self_development/` | Auto-desenvolvimento |

### agents/ (11 agentes)

| Agente | Especialidade |
|--------|---------------|
| `market_analyst/` | Análise de mercado |
| `mql5/` | Programação MQL5 |
| `programmer/` | Programação geral |
| `risk/` | Gestão de risco |
| `statistician/` | Estatística |
| `reviewer/` | Revisão de código |
| `architect/` | Arquitetura |
| `backtest/` | Backtesting |
| `python_quant/` | Quant Python |
| `media_study/` | Estudo de mídia |

## Fluxo de uma Requisição

```
1. Usuário envia mensagem
   ↓
2. Server Agent recebe (HTTP POST)
   ↓
3. PermissionManager verifica permissão
   ↓
4. Tool Registry executa ferramentas
   ↓
5. Ollama gera resposta (streaming SSE)
   ↓
6. Resposta enviada ao usuário
```

## Segurança

- **PermissionManager**: Verifica cada operação
- **Paths protegidos**: app/, studio/, backups/
- **Read-only mode**: Pode ser ativado
- **Backup automático**: Antes de qualquer edição
- **Auditoria**: Todas as operações são logadas
