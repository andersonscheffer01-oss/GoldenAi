# Golden AI — Conhecimento do Projeto

> **IMPORTANTE:** Antes de modificar o Golden, leia e obedeça também o `AGENTS.md` da raiz do projeto. `AGENTS.md` contém as regras obrigatórias; este `knowledge.md` contém contexto e conhecimento do projeto.
>
> Contexto essencial para qualquer agente que trabalhe no Golden AI.
> Atualizado: Setembro 2026

---

## O que é o Golden AI

Sistema de IA local para **trading algoritmico**, **desenvolvimento MQL5** e **automação de PC**. Roda inteiramente na máquina do usuário com Ollama para processamento de linguagem natural.

**Não é um chatbot genérico.** É um sistema de produção com trading real no MetaTrader 5.

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.11+, HTTPServer threaded |
| Frontend | HTML/JS/CSS single-file (PWA) |
| IA Local | Ollama (qwen2.5-coder:14b, qwen2.5vl:7b) |
| IA Externa | OpenRouter, Cline, Gemini, Groq |
| Trading | MetaTrader 5 (Python API) |
| Banco | SQLite (golden_runtime.db) |
| Memória Vetorial | Qdrant (opcional) |
| STT | faster-whisper |
| TTS | Edge TTS |
| SO | Windows 10/11 |

---

## Componentes Principais

### Backend (server_agent.py)
- ~6000 linhas
- HTTPServer com ThreadingMixIn
- 50+ endpoints HTTP
- Streaming SSE para respostas de IA
- Integração com Ollama, MT5, Scanner

### Dashboard (dashboard.html)
- Scanner de mercado em tempo real
- 22 pares de moedas
- 47 estratégias (SCALP/DAY/SWING)
- Risk Engine integrado
- Validation Engine com Monte Carlo
- Strategy Manager com ON/OFF
- Aba de Backtest
- Aba de Validação

### Golden Scanner (golden_scanner.py)
- ~2000 linhas
- Motor de detecção de oportunidades
- 47 setups com IDs únicos
- Scoring com confluência multi-timeframe
- Normalização por ATR
- Regime de mercado detector

### Jarvis 2.0 (jarvis_core/)
- Agente de automação do PC
- 38+ ferramentas (abrir programas, pastas, processos, volume, etc.)
- Parser de comandos em linguagem natural
- Sistema de permissões com confirmações
- Auditoria persistente

### Core (core/)
- 25+ módulos
- Permissions, Tools, Memory, Vision, Audio, Coding, Execution
- Sistema de segurança com níveis de risco

### Agents (agents/)
- 11 agentes especializados
- MQL5, Python Quant, Market Analyst, Risk, Backtest, Reviewer, Architect

---

## Fluxo de Trading

```
Scanner detecta setup
    ↓
Risk Engine valida (daily loss, correlation, cooldown)
    ↓
Position Sizing calcula lote
    ↓
Score calibrado com dados reais
    ↓
Dashboard exibe oportunidade
    ↓
Usuário confirma OU Auto-Trade executa
    ↓
Trade Journal registra
    ↓
Statistics Engine aprende
```

---

## Estratégias (47 setups)

### SCALP (22)
- Breakout + Reteste, VWAP Pullback, ORB, Liquidity Sweep
- VWAP Reclaim/Flip, Falso Rompimento, Momentum Burst
- Session H/L Rejection, Order Block Scalp, etc.

### DAY TRADE (15)
- BOS Retest, CHoCH, FVG Fill, Order Block Entry
- SMT Divergence, Kill Zone Entry, etc.

### SWING (10)
- Fibonacci Retracement, Daily Breakout, Macro Reversão
- MA Crossover HTF, Fluxo Institucional, etc.

---

## Configurações Importantes

| Config | Valor | Arquivo |
|--------|-------|---------|
| Porta backend | 8765 | server_agent.py |
| Porta Jarvis | 8780 | jarvis/backend |
| Ollama | localhost:11434 | .env |
| API Keys | config/api_keys.json | PROTEGIDO |
| Banco | data/golden_runtime.db | SQLite |
| MT5 Path | C:\Program Files\MetaTrader 5 | mt5_connector.py |

---

## Erros Conhecidos e Corrigidos

1. **JSON serialization (numpy bool)** — Corrigido com _NumpyEncoder
2. **Pares zerados no Radar** — NAS100→US100, SPX500→US500, DAX40→GER40
3. **Pillow não instalado** — pip install Pillow
4. **EA Builder só gerava um tipo** — Corrigido para gerar múltiplos
5. **Backtest tela preta** — Corrigido com conteúdo real

---

## Decisões Arquiteturais Importantes

1. **Backend em HTTPServer** (não FastAPI) — manter compatibilidade
2. **Frontend single-file** — sem build tools, sem node_modules
3. **SQLite** — sem dependência de banco externo
4. **Ollama local** — sem dependência de nuvem para IA principal
5. **Jarvis separado** — módulo independente do Scanner
6. **Scanner como kernel** — todos os módulos dependem dele

---

## O que NÃO deve ser alterado sem confirmação

- `server_agent.py` (rotas principais)
- `studio_v7.html` (frontend principal)
- `config/api_keys.json` (chaves de API)
- Lógica de trading em `golden_scanner.py`
- Risk Engine (`risk_engine.py`)
- Position sizing em `risk_engine.py`
- Trade Journal (`trade_journal.py`)
