# 🥇 Golden AI

**Agente de IA para Trading Algoritmico e Desenvolvimento de Robos**

Golden AI e um assistente de IA local que conecta ao MetaTrader 5, oferece analise de mercado, backtesting, correcao automatica de codigo MQL5, e acesso completo ao sistema do usuario.

---

## 🚀 Funcionalidades Principais

| Recurso | Descricao |
|---------|-----------|
| **Chat com IA** | Streaming palavra por palavra, memoria de conversa, markdown rico |
| **Agente Completo** | Acesso a filesystem, executar comandos, limpeza de sistema |
| **MetaTrader 5** | Listar robos, analisar codigo, compilar, corrigir bugs |
| **Analise de Mercado** | Datasets CSV, regimes, sinais, multi-timeframe |
| **Backtesting** | Estrategias quant, metricas, equity curve |
| **Memoria Cientifica** | Armazenar e buscar conhecimento estruturado |
| **Midia** | Transcricao de audio, analise de video, extracao de PDF |
| **Internet** | Busca web, cotacoes em tempo real |
| **Edicao de PDF** | Corrigir e criar PDFs diretamente pelo chat |
| **Interface Web** | Layout profissional estilo Claude/ChatGPT |

---

## 🐳 Docker (Recomendado)

```bash
# Build e rodar com Ollama
ocker-compose up -d

# Ou manualmente
docker build -t golden-ai .
docker run -p 8765:8765 golden-ai
```

### Produção

```bash
# Deploy completo com backup automático
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📦 Instalacao Manual

### Requisitos
- Python 3.11+
- Ollama (para modelos locais)
- MetaTrader 5 (opcional, para trading)

### Passos

```bash
# 1. Clonar o repositorio
git clone <url-do-repositorio>
cd GoldenAI

# 2. Criar ambiente virtual
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar Ollama
ollama pull qwen2.5-coder:14b

# 5. Iniciar o servidor
cd studio/golden_ai_studio_web
python server_agent.py

# 6. Abrir no navegador
# Clique duas vezes em: ABRIR_GOLDEN_AI_STUDIO_WEB.vbs
```

---

## 🏗️ Arquitetura

```
GoldenAI/
├── app/
│   ├── golden_ai.py          # Engine principal (orquestrador)
│   └── modules/              # Modulos extraidos
│       ├── context.py        # Estado compartilhado (CFG, SERVICES)
│       ├── utils.py          # Funcoes utilitarias
│       ├── mt5.py            # Operacoes MetaTrader 5
│       ├── files.py          # Operacoes de arquivo
│       ├── intent.py         # Classificacao de intencao
│       ├── internet.py       # Chat de internet
│       ├── browser.py        # Wrappers de midia
│       ├── panel.py          # Painel de comandos
│       ├── market_chat.py    # Chat de mercado
│       ├── memory_chat.py    # Chat de memoria cientifica
│       ├── media_chat.py     # Chat de midia
│       └── quant_chat.py     # Chat quant (backtest)
├── core/                     # 25 modulos de infraestrutura
│   ├── permissions/          # Sistema de permissoes
│   ├── tools/                # Registry de ferramentas
│   ├── memory/               # Memoria vetorial (Qdrant)
│   ├── audit/                # Auditoria
│   ├── browser/              # Browser headless
│   ├── documents/            # Extracao de documentos
│   ├── audio/                # Transcricao (Whisper)
│   ├── video/                # Analise de video
│   ├── vision/               # Analise de imagens
│   └── ...
├── agents/                   # 11 agentes especializados
│   ├── market_analyst/       # Analise de mercado
│   ├── mql5/                 # Programacao MQL5
│   ├── programmer/           # Programacao geral
│   ├── risk/                 # Gestao de risco
│   └── ...
├── config/
│   ├── base.yaml             # Configuracao base
│   ├── security.yaml         # Permissoes e paths
│   ├── ollama.yaml           # Modelos de IA
│   ├── tools.yaml            # Ferramentas
│   └── config_loader.py      # Loader unificado
├── studio/
│   └── golden_ai_studio_web/
│       ├── server_agent.py   # Servidor HTTP com agente
│       └── studio_v7.html    # Interface web
├── tests/
│   ├── test_agent_tools.py   # Testes do agente
│   ├── test_modules.py       # Testes dos modulos
│   └── test_permissions.py   # Testes de seguranca
└── docs/
    └── README.md             # Este arquivo
```

---

## ⚙️ Configuracao

A configuracao esta em `config/` e pode ser editada:

| Arquivo | Descricao |
|---------|-----------|
| `base.yaml` | Caminhos e funcionalidades gerais |
| `security.yaml` | Permissoes, paths permitidos e protegidos |
| `ollama.yaml` | Modelos Ollama e multi-provider |
| `tools.yaml` | OpenCode, tools infrastructure |

### Modelos Disponiveis

| Perfil | Modelo | Uso |
|--------|--------|-----|
| FAST | qwen2.5-coder:14b | Respostas rapidas |
| CODER | qwen2.5-coder:14b | Programacao |
| EXPERT | Qwen3.8-27B-Uncensored | Analise complexa |

---

## 🧪 Testes

```bash
# Rodar todos os testes
python tests/test_agent_tools.py    # 14 testes do agente
python tests/test_modules.py        # 25 testes dos modulos
python tests/test_permissions.py    # 9 testes de seguranca

# Total: 48 testes
```

---

## 🔒 Seguranca

- **PermissionManager** verifica cada operacao de leitura/escrita/execucao
- **Paths protegidos**: app/, studio/, backups/ (sem escrita)
- **Paths permitidos**: projetos/, sandbox/, Desktop/, Downloads/
- **Read-only mode**: pode ser ativado em security.yaml
- **Backup automatico**: antes de qualquer edicao de arquivo

---

## 📝 Atalhos de Teclado (Studio Web)

| Atalho | Acao |
|--------|------|
| `Ctrl+Enter` | Enviar mensagem |
| `Ctrl+N` | Nova conversa |
| `Ctrl+K` | Buscar no historico |
| `Ctrl+M` | Ativar/desativar voz |
| `Ctrl+Shift+C` | Comparar respostas |

---

## 📄 Licenca

DMCA: Este software e protegido por direitos autorais.
