# Arquitetura do Golden AI

## Visão Geral

```
USUÁRIO (Browser)
    ↓ HTTP/SSE
STUDIO WEB (porta 8765)
    ├── server_agent.py (backend)
    ├── studio_v7.html (frontend)
    └── streaming (SSE)
    ↓
PERMISSION MANAGER
    ↓
TOOL REGISTRY
    ↓
SERVIÇOS
    ├── Browser, Documents, Audio, Vision
    ├── Memory (Qdrant), Internet
    ├── MT5, PDF
    └── Jarvis (porta 8780)
    ↓
OLLAMA (localhost:11434)
```

## Módulos Principais

### Backend
- `server_agent.py` — Backend principal (~6000 linhas)
- `golden_scanner.py` — Scanner de oportunidades (~2000 linhas)
- `statistics_engine.py` — Motor estatístico
- `validation_engine.py` — Validação com Monte Carlo
- `risk_engine.py` — Gerenciamento de risco
- `trade_journal.py` — Diário de operações
- `mt5_connector.py` — Conexão MetaTrader 5
- `position_manager.py` — Gerenciamento de posições

### Frontend
- `studio_v7.html` — Interface principal (PWA)
- `dashboard.html` — Dashboard de trading
- `market.html` — Radar de mercado
- `desktop_center.js` — Central de controle do PC

### Core
- `core/permissions/` — Sistema de permissões
- `core/tools/` — Registry de ferramentas
- `core/memory/` — Memória vetorial
- `core/vision/` — Análise de imagens
- `core/audio/` — Transcrição de áudio
- `core/coding/` — Agente de código

### Agents
- `agents/mql5/` — Programação MQL5
- `agents/python_quant/` — Quant Python
- `agents/market_analyst/` — Análise de mercado
- `agents/risk/` — Gestão de risco
- `agents/backtest/` — Backtesting

### Jarvis
- `jarvis_core/service.py` — Agente de automação PC
- 38+ ferramentas de controle
- Parser de comandos naturais

## Portas

| Serviço | Porta |
|---------|-------|
| Golden Studio | 8765 |
| Golden Jarvis | 8780 |
| Ollama | 11434 |

## Banco de Dados

- `data/golden_runtime.db` — SQLite principal
  - monitor_runs
  - signal_states
  - signal_events
  - jarvis_audit
  - statistics_cache
