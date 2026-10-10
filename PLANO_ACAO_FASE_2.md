# 🎯 Plano de Ação — FASE 2: Golden + MT5 READ-ONLY

**Data:** 21/09/2026
**Prioridade:** 🔴 CRÍTICA (Bloqueio para FASE 3+)
**Estimativa:** 2-3 semanas
**Objetivo:** Conectar TODOS os componentes Golden e MT5 ao ToolRegistry

---

## 📋 Contexto

### Situação Atual:
- ✅ ~12 componentes Golden com código implementado
- ✅ Estrutura MT5 presente (9 arquivos MQL5)
- 🔴 **Nenhum componente conectado ao ToolRegistry**
- 🔴 **Jarvis não consegue acessar Golden ou MT5**

### Impacto do Bloqueio:
- Impede FASE 3 (Computer Use)
- Impede uso de trading read-only
- Impede análise de mercado via Jarvis
- Impede backtesting via Jarvis
- Impede scanner de mercado via Jarvis

---

## 🔍 Etapa 1: Descoberta (2-3 dias)

### 1.1 Listar Componentes Golden Existentes

**Ação:** Auditar diretório Golden para identificar TODOS os componentes com código

```bash
# Buscar componentes Golden
find C:\GoldenAI -type f -name "*golden*" -o -name "*Golden*"
find C:\GoldenAI -type d -name "*golden*" -o -name "*Golden*"

# Buscar por imports/referências
grep -r "class Golden" C:\GoldenAI --include="*.py"
grep -r "def golden_" C:\GoldenAI --include="*.py"
```

**Output esperado:**
```
golden_components/
├── golden_status.py
├── golden_analyzer.py
├── golden_scanner.py
├── golden_risk.py
├── golden_strategy.py
├── golden_backtest.py
├── ... (6+ outros componentes)
```

**Deliverable:** `GOLDEN_COMPONENTS_INVENTORY.md`

---

### 1.2 Listar Funcionalidades MT5 Necessárias

**Ação:** Mapear funcionalidades MT5 requeridas contra código existente

**Tools MT5 Read-Only Necessários:**

| Tool | Descrição | Prioridade | Status Atual |
|------|-----------|------------|--------------|
| `mt5_status` | Status da conexão MT5 | 🔴 CRÍTICO | ❓ |
| `mt5_account_info` | Informações da conta (balance, equity, margin) | 🔴 CRÍTICO | ❓ |
| `mt5_positions` | Lista de posições abertas | 🔴 CRÍTICO | ❓ |
| `mt5_orders` | Lista de ordens pendentes | 🔴 CRÍTICO | ❓ |
| `mt5_market_tick` | Tick atual do mercado (bid, ask, spread) | 🔴 CRÍTICO | ❓ |
| `mt5_history_deals` | Histórico de negociações | 🟡 IMPORTANTE | ❓ |
| `mt5_history_orders` | Histórico de ordens | 🟡 IMPORTANTE | ❓ |
| `mt5_symbol_info` | Informações do símbolo (digits, spread, etc) | 🟡 IMPORTANTE | ❓ |
| `mt5_scanner` | Scanner de mercado (múltiplos símbolos) | 🟡 IMPORTANTE | ❓ |
| `mt5_risk` | Cálculo de risco (lot size, stop loss) | 🟡 IMPORTANTE | ❓ |
| `mt5_strategies` | Lista de estratégias disponíveis | 🟢 NORMAL | ❓ |
| `mt5_backtest` | Backtest de estratégias | 🟢 NORMAL | ❓ |

**Deliverable:** `MT5_TOOLS_SPECIFICATION.md`

---

### 1.3 Verificar Código MT5 Existente

**Ação:** Auditar os 9 arquivos MQL5 encontrados

```bash
# Listar arquivos MQL5
find C:\GoldenAI -name "*.mq5" -o -name "*.mqh"

# Verificar Python MT5 integration
grep -r "import MetaTrader5" C:\GoldenAI --include="*.py"
grep -r "mt5\." C:\GoldenAI --include="*.py"
```

**Verificar:**
- ✅ Biblioteca MetaTrader5 instalada?
- ✅ Código Python para MT5 connection existe?
- ✅ Expert Advisors funcionais?

**Deliverable:** `MT5_CODE_AUDIT.md`

---

## 🛠️ Etapa 2: Implementação Golden Tools (5-7 dias)

### 2.1 Estrutura do Arquivo golden_tools.py

**Localização:** `C:\GoldenAI\studio\golden_ai_studio_web\core\golden_tools.py`

```python
"""
Golden Tools - Integração dos componentes Golden ao ToolRegistry
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# GOLDEN STATUS
# ============================================================================

def golden_status() -> Dict[str, Any]:
    """
    Retorna status geral do sistema Golden

    Returns:
        Dict contendo:
        - status: "running" | "stopped" | "error"
        - version: versão do Golden
        - components: lista de componentes e seus status
        - last_update: timestamp do último update
    """
    try:
        # TODO: Implementar lógica real
        return {
            "status": "running",
            "version": "2.1.0",
            "components": [
                {"name": "analyzer", "status": "running"},
                {"name": "scanner", "status": "running"},
                {"name": "risk", "status": "running"},
            ],
            "last_update": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao obter golden_status: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# GOLDEN ANALYZER
# ============================================================================

def golden_analyze(
    symbol: str,
    timeframe: str = "M5",
    depth: int = 100
) -> Dict[str, Any]:
    """
    Analisa um símbolo usando Golden Analyzer

    Args:
        symbol: Símbolo a analisar (ex: "WINJ24")
        timeframe: Timeframe (M1, M5, M15, M30, H1, H4, D1)
        depth: Profundidade da análise (número de candles)

    Returns:
        Dict contendo:
        - symbol: símbolo analisado
        - timeframe: timeframe usado
        - trend: tendência detectada
        - signals: sinais de entrada/saída
        - indicators: valores dos indicadores
        - timestamp: timestamp da análise
    """
    try:
        # TODO: Implementar lógica real
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "trend": "bullish",
            "signals": {
                "buy": 0.75,
                "sell": 0.25
            },
            "indicators": {
                "rsi": 65.5,
                "macd": {"value": 12.3, "signal": 10.1},
                "ema_20": 125340,
                "ema_50": 125200
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao executar golden_analyze: {e}")
        return {"error": str(e)}


# ============================================================================
# GOLDEN SCANNER
# ============================================================================

def golden_scan(
    symbols: Optional[List[str]] = None,
    timeframe: str = "M5",
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Scanneia múltiplos símbolos buscando oportunidades

    Args:
        symbols: Lista de símbolos (None = todos os símbolos configurados)
        timeframe: Timeframe para análise
        filters: Filtros adicionais (volume, spread, etc)

    Returns:
        Dict contendo:
        - scanned: número de símbolos scaneados
        - opportunities: lista de oportunidades encontradas
        - timestamp: timestamp do scan
    """
    try:
        # TODO: Implementar lógica real
        return {
            "scanned": 10,
            "opportunities": [
                {
                    "symbol": "WINJ24",
                    "score": 0.85,
                    "trend": "bullish",
                    "entry": 125340
                },
                {
                    "symbol": "WDOJ24",
                    "score": 0.72,
                    "trend": "bearish",
                    "entry": 11520
                }
            ],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Erro ao executar golden_scan: {e}")
        return {"error": str(e)}


# ============================================================================
# GOLDEN RISK
# ============================================================================

def golden_risk(
    symbol: str,
    entry: float,
    stop_loss: float,
    target: float,
    risk_percent: float = 1.0
) -> Dict[str, Any]:
    """
    Calcula risco e position sizing para uma operação

    Args:
        symbol: Símbolo da operação
        entry: Preço de entrada
        stop_loss: Preço de stop loss
        target: Preço alvo
        risk_percent: Percentual de risco do capital (default 1%)

    Returns:
        Dict contendo:
        - lot_size: tamanho da posição em lotes
        - risk_amount: valor em risco (R$)
        - reward_amount: valor potencial de lucro (R$)
        - risk_reward: relação risco/retorno
        - max_loss: perda máxima em %
    """
    try:
        # TODO: Implementar lógica real com dados reais da conta
        risk_points = abs(entry - stop_loss)
        reward_points = abs(target - entry)

        return {
            "lot_size": 1,
            "risk_amount": 500.00,
            "reward_amount": 1500.00,
            "risk_reward": round(reward_points / risk_points, 2) if risk_points > 0 else 0,
            "max_loss": risk_percent,
            "valid": True
        }
    except Exception as e:
        logger.error(f"Erro ao calcular golden_risk: {e}")
        return {"error": str(e), "valid": False}


# ============================================================================
# GOLDEN STRATEGY
# ============================================================================

def golden_list_strategies() -> Dict[str, Any]:
    """
    Lista todas as estratégias disponíveis no Golden

    Returns:
        Dict contendo:
        - strategies: lista de estratégias
        - count: número total de estratégias
    """
    try:
        # TODO: Implementar lógica real
        return {
            "strategies": [
                {
                    "id": "rompimento_velas_m2",
                    "name": "Rompimento de Velas M2",
                    "timeframe": "M2",
                    "type": "breakout",
                    "status": "active"
                },
                {
                    "id": "ema_cross",
                    "name": "EMA Crossover",
                    "timeframe": "M5",
                    "type": "trend_following",
                    "status": "active"
                }
            ],
            "count": 2
        }
    except Exception as e:
        logger.error(f"Erro ao listar golden_list_strategies: {e}")
        return {"error": str(e)}


def golden_strategy_info(strategy_id: str) -> Dict[str, Any]:
    """
    Retorna informações detalhadas de uma estratégia

    Args:
        strategy_id: ID da estratégia

    Returns:
        Dict contendo informações da estratégia
    """
    try:
        # TODO: Implementar lógica real
        return {
            "id": strategy_id,
            "name": "Rompimento de Velas M2",
            "description": "Estratégia baseada em rompimento de candles no timeframe M2",
            "timeframe": "M2",
            "parameters": {
                "min_volume": 1000,
                "max_spread": 5,
                "breakout_threshold": 0.5
            },
            "performance": {
                "win_rate": 0.65,
                "profit_factor": 1.85,
                "avg_trade": 150.00,
                "total_trades": 150
            }
        }
    except Exception as e:
        logger.error(f"Erro ao obter golden_strategy_info: {e}")
        return {"error": str(e)}


# ============================================================================
# GOLDEN BACKTEST
# ============================================================================

def golden_backtest(
    strategy_id: str,
    symbol: str,
    start_date: str,
    end_date: str,
    initial_balance: float = 10000.0
) -> Dict[str, Any]:
    """
    Executa backtest de uma estratégia

    Args:
        strategy_id: ID da estratégia
        symbol: Símbolo para backtest
        start_date: Data inicial (YYYY-MM-DD)
        end_date: Data final (YYYY-MM-DD)
        initial_balance: Saldo inicial

    Returns:
        Dict contendo resultados do backtest
    """
    try:
        # TODO: Implementar lógica real
        return {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "period": f"{start_date} to {end_date}",
            "initial_balance": initial_balance,
            "final_balance": 15750.00,
            "total_return": 57.5,
            "total_trades": 45,
            "winning_trades": 30,
            "losing_trades": 15,
            "win_rate": 66.7,
            "profit_factor": 2.1,
            "max_drawdown": 12.5,
            "sharpe_ratio": 1.85,
            "trades": []  # Lista vazia por enquanto
        }
    except Exception as e:
        logger.error(f"Erro ao executar golden_backtest: {e}")
        return {"error": str(e)}


# ============================================================================
# TOOL REGISTRY
# ============================================================================

GOLDEN_TOOLS = {
    "golden_status": {
        "function": golden_status,
        "description": "Retorna status geral do sistema Golden",
        "parameters": {},
        "risk_level": "LOW"
    },
    "golden_analyze": {
        "function": golden_analyze,
        "description": "Analisa um símbolo usando Golden Analyzer",
        "parameters": {
            "symbol": {"type": "string", "required": True},
            "timeframe": {"type": "string", "required": False, "default": "M5"},
            "depth": {"type": "integer", "required": False, "default": 100}
        },
        "risk_level": "LOW"
    },
    "golden_scan": {
        "function": golden_scan,
        "description": "Scanneia múltiplos símbolos buscando oportunidades",
        "parameters": {
            "symbols": {"type": "array", "required": False},
            "timeframe": {"type": "string", "required": False, "default": "M5"},
            "filters": {"type": "object", "required": False}
        },
        "risk_level": "LOW"
    },
    "golden_risk": {
        "function": golden_risk,
        "description": "Calcula risco e position sizing para uma operação",
        "parameters": {
            "symbol": {"type": "string", "required": True},
            "entry": {"type": "number", "required": True},
            "stop_loss": {"type": "number", "required": True},
            "target": {"type": "number", "required": True},
            "risk_percent": {"type": "number", "required": False, "default": 1.0}
        },
        "risk_level": "LOW"
    },
    "golden_list_strategies": {
        "function": golden_list_strategies,
        "description": "Lista todas as estratégias disponíveis",
        "parameters": ,
        "risk_level": "LOW"
    },
    "golden_strategy_info": {
        "function": golden_strategy_info,
        "description": "Retorna informações detalhadas de uma estratégia",
        "parameters": {
            "strategy_id": {"type": "string", "required": True}
        },
        "risk_level": "LOW"
    },
    "golden_backtest": {
        "function": golden_backtest,
        "description": "Executa backtest de uma estratégia",
        "parameters": {
            "strategy_id": {"type": "string", "required": True},
            "symbol": {"type": "string", "required": True},
            "start_date": {"type": "string", "required": True},
            "end_date": {"type": "string", "required": True},
            "initial_balance": {"type": "number", "required": False, "default": 10000.0}
        },
        "risk_level": "LOW"
    }
}


def register_golden_tools(tool_registry):
    """
    Registra todos os Golden tools no ToolRegistry

    Args:
        tool_registry: Instância do ToolRegistry
    """
    for tool_name, tool_config in GOLDEN_TOOLS.items():
        tool_registry.register_tool(
            name=tool_name,
            function=tool_config["function"],
            description=tool_config["description"],
            parameters=tool_config["parameters"],
            risk_level=tool_config["risk_level"]
        )

    logger.info(f"Registrados {len(GOLDEN_TOOLS)} Golden tools no ToolRegistry")
```

**Deliverable:** `golden_tools.py` completo

---

### 2.2 Testes dos Golden Tools

**Localização:** `C:\GoldenAI\studio\golden_ai_studio_web\tests\test_golden_tools.py`

```python
"""
Testes para Golden Tools
"""
import pytest
from core.golden_tools import (
    golden_status,
    golden_analyze,
    golden_scan,
    golden_risk,
    golden_list_strategies,
    golden_strategy_info,
    golden_backtest
)


def test_golden_status():
    """Testa golden_status"""
    result = golden_status()
    assert result["status"] in ["running", "stopped", "error"]
    assert "version" in result
    assert "components" in result


def test_golden_analyze():
    """Testa golden_analyze"""
    result = golden_analyze(symbol="WINJ24", timeframe="M5")
    assert result["symbol"] == "WINJ24"
    assert result["timeframe"] == "M5"
    assert "trend" in result
    assert "signals" in result
    assert "indicators" in result


def test_golden_scan():
    """Testa golden_scan"""
    result = golden_scan(timeframe="M5")
    assert "scanned" in result
    assert "opportunities" in result
    assert isinstance(result["opportunities"], list)


def test_golden_risk():
    """Testa golden_risk"""
    result = golden_risk(
        symbol="WINJ24",
        entry=125000,
        stop_loss=124900,
        target=125300,
        risk_percent=1.0
    )
    assert "lot_size" in result
    assert "risk_amount" in result
    assert "reward_amount" in result
    assert "risk_reward" in result
    assert result["valid"] is True


def test_golden_list_strategies():
    """Testa golden_list_strategies"""
    result = golden_list_strategies()
    assert "strategies" in result
    assert "count" in result
    assert isinstance(result["strategies"], list)


def test_golden_strategy_info():
    """Testa golden_strategy_info"""
    result = golden_strategy_info(strategy_id="rompimento_velas_m2")
    assert result["id"] == "rompimento_velas_m2"
    assert "name" in result
    assert "parameters" in result
    assert "performance" in result


def test_golden_backtest():
    """Testa golden_backtest"""
    result = golden_backtest(
        strategy_id="rompimento_velas_m2",
        symbol="WINJ24",
        start_date="2024-01-01",
        end_date="2024-06-01",
        initial_balance=10000.0
    )
    assert result["strategy_id"] == "rompimento_velas_m2"
    assert result["symbol"] == "WINJ24"
    assert "final_balance" in result
    assert "total_return" in result
    assert "win_rate" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Deliverable:** `test_golden_tools.py` completo

---

## 🛠️ Etapa 3: Implementação MT5 Tools (5-7 dias)

### 3.1 Estrutura do Arquivo mt5_tools.py

**Localização:** `C:\GoldenAI\studio\golden_ai_studio_web\core\mt5_tools.py`

```python
"""
MT5 Tools - Integração MetaTrader 5 READ-ONLY ao ToolRegistry
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import MetaTrader5 as mt5

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURAÇÃO MT5
# ============================================================================

MT5_INITIALIZED = False

def _ensure_mt5_initialized() -> bool:
    """Garante que MT5 está inicializado"""
    global MT5_INITIALIZED
    if not MT5_INITIALIZED:
        if not mt5.initialize():
            logger.error(f"MT5 initialization failed: {mt5.last_error()}")
            return False
        MT5_INITIALIZED = True
    return True


# ============================================================================
# MT5 STATUS
# ============================================================================

def mt5_status() -> Dict[str, Any]:
    """
    Retorna status da conexão MT5

    Returns:
        Dict contendo:
        - connected: boolean
        - terminal_info: informações do terminal
        - last_error: último erro (se houver)
    """
    try:
        if not _ensure_mt5_initialized():
            return {
                "connected": False,
                "error": "Failed to initialize MT5"
            }

        terminal_info = mt5.terminal_info()
        if terminal_info is None:
            return {
                "connected": False,
                "error": str(mt5.last_error())
            }

        return {
            "connected": True,
            "terminal_info": {
                "company": terminal_info.company,
                "name": terminal_info.name,
                "path": terminal_info.path,
                "data_path": terminal_info.data_path,
                "connected": terminal_info.connected,
                "trade_allowed": terminal_info.trade_allowed,
                "community_account": terminal_info.community_account,
                "email": terminal_info.email
            }
        }
    except Exception as e:
        logger.error(f"Erro ao obter mt5_status: {e}")
        return {"connected": False, "error": str(e)}


# ============================================================================
# MT5 ACCOUNT INFO
# ============================================================================

def mt5_account_info() -> Dict[str, Any]:
    """
    Retorna informações da conta MT5

    Returns:
        Dict contendo:
        - login: número da conta
        - balance: saldo da conta
        - equity: patrimônio líquido
        - margin: margem utilizada
        - free_margin: margem livre
        - profit: lucro/prejuízo atual
        - currency: moeda da conta
        - leverage: alavancagem
        - trade_mode: modo de trading (demo/real)
    """
    try:
        if not _ensure_mt5_initialized():
            return {"error": "MT5 not initialized"}

        account_info = mt5.account_info()
        if account_info is None:
            return {"error": str(mt5.last_error())}

        return {
            "login": account_info.login,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "margin": account_info.margin,
            "free_margin": account_info.margin_free,
            "profit": account_info.profit,
            "currency": account_info.currency,
            "leverage": account_info.leverage,
            "trade_mode": "demo" if account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "real",
            "margin_level": account_info.margin_level
        }
    except Exception as e:
        logger.error(f"Erro ao obter mt5_account_info: {e}")
        return {"error": str(e)}


# ============================================================================
# MT5 POSITIONS
# ============================================================================

def mt5_positions(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna posições abertas

    Args:
        symbol: Filtrar por símbolo (None = todas as posições)

    Returns:
        Dict contendo lista de posições
    """
    try:
        if not _ensure_mt5_initialized():
            return {"error": "MT5 not initialized"}

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return {"error": str(mt5.last_error())}

        positions_list = []
        for pos in positions:
            positions_list.append({
                "ticket": pos.ticket,
                "time": datetime.fromtimestamp(pos.time).isoformat(),
                "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                "symbol": pos.symbol,
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "commission": pos.commission,
                "comment": pos.comment,
                "magic": pos.magic
            })

        return {
            "count": len(positions_list),
            "positions": positions_list
        }
    except Exception as e:
        logger.error(f"Erro ao obter mt5_positions: {e}")
        return {"error": str(e)}


# ============================================================================
# MT5 ORDERS
# ============================================================================

def mt5_orders(symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna ordens pendentes

    Args:
        symbol: Filtrar por símbolo (None = todas as ordens)

    Returns:
        Dict contendo lista de ordens
    """
    try:
        if not _ensure_mt5_initialized():
            return {"error": "MT5 not initialized"}

        if symbol:
            orders = mt5.orders_get(symbol=symbol)
        else:
            orders = mt5.orders_get()

        if orders is None:
            return {"error": str(mt5.last_error())}

        orders_list = []
        for order in orders:
            orders_list.append({
                "ticket": order.ticket,
                "time_setup": datetime.fromtimestamp(order.time_setup).isoformat(),
                "type": order.type,
                "type_filling": order.type_filling,
                "type_time": order.type_time,
                "symbol": order.symbol,
                "volume_initial": order.volume_initial,
                "volume_current": order.volume_current,
                "price_open": order.price_open,
                "sl": order.sl,
                "tp": order.tp,
                "price_current": order.price_current,
                "comment": order.comment,
                "magic": order.magic
            })

        return {
            "count": len(orders_list),
            "orders": orders_list
        }
    except Exception as e:
        logger.error(f"Erro ao obter mt5_orders: {e}")
        return {"error": str(e)}


# ============================================================================
# MT5 MARKET TICK
# ============================================================================

def mt5_market_tick(symbol: str) -> Dict[str, Any]:
    """
    Retorna tick atual do mercado

    Args:
        symbol: Símbolo do ativo

    Returns:
        Dict contendo tick atual
    """
    try:
        if not _ensure_mt5_initialized():
            return {"error": "MT5 not initialized"}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"error": f"Symbol {symbol} not found"}

        return {
            "symbol": symbol,
            "time": datetime.fromtimestamp(tick.time).isoformat(),
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "spread": tick.ask - tick.bid,
            "spread_points": int((tick.ask - tick.bid) / mt5.symbol_info(symbol).point)
        }
    except Exception as e:
        logger.error(f"Erro ao obter mt5_market_tick: {e}")
        return {"error": str(e)}


# ============================================================================
# MT5 SYMBOL INFO
# ============================================================================

def mt5_symbol_info(symbol: str) -> Dict[str, Any]:
    """
    Retorna informações do símbolo

    Args:
        symbol: Símbolo do ativo

    Returns:
        Dict contendo informações do símbolo
    """
    try:
        if not _ensure_mt5_initialized():
            return {"error": "MT5 not initialized"}

        info = mt5.symbol_info(symbol)
        if info is None:
            return {"error": f"Symbol {symbol} not found"}

        return {
            "symbol": symbol,
            "description": info.description,
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_contract_size": info.trade_contract_size,
            "trade_tick_size": info.trade_tick_size,
            "trade_tick_value": info.trade_tick_value,
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
            "currency_margin": info.currency_margin
        }
    except Exception as e:
        logger.error(f"Erro ao obter mt5_symbol_info: {e}")
        return {"error": str(e)}


# ============================================================================
# MT5 SCANNER (múltiplos símbolos)
# ============================================================================

def mt5_scanner(symbols: List[str]) -> Dict[str, Any]:
    """
    Scanneia múltiplos símbolos retornando ticks atuais

    Args:
        symbols: Lista de símbolos

    Returns:
        Dict contendo ticks de todos os símbolos
    """
    try:
        if not _ensure_mt5_initialized():
            return {"error": "MT5 not initialized"}

        results = []
        for symbol in symbols:
            tick_data = mt5_market_tick(symbol)
            if "error" not in tick_data:
                results.append(tick_data)

        return {
            "scanned": len(results),
            "symbols": results
        }
    except Exception as e:
        logger.error(f"Erro ao executar mt5_scanner: {e}")
        return {"error": str(e)}


# ============================================================================
# TOOL REGISTRY
# ============================================================================

MT5_TOOLS = {
    "mt5_status": {
        "function": mt5_status,
        "description": "Retorna status da conexão MT5",
        "parameters": {},
        "risk_level": "LOW"
    },
    "mt5_account_info": {
        "function": mt5_account_info,
        "description": "Retorna informações da conta MT5 (balance, equity, margin)",
        "parameters": {},
        "risk_level": "LOW"
    },
    "mt5_positions": {
        "function": mt5_positions,
        "description": "Retorna posições abertas",
        "parameters": {
            "symbol": {"type": "string", "required": False}
        },
        "risk_level": "LOW"
    },
    "mt5_orders": {
        "function": mt5_orders,
        "description": "Retorna ordens pendentes",
        "parameters": {
            "symbol": {"type": "string", "required": False}
        },
        "risk_level": "LOW"
    },
    "mt5_market_tick": {
        "function": mt5_market_tick,
        "description": "Retorna tick atual do mercado (bid, ask, spread)",
        "parameters": {
            "symbol": {"type": "string", "required": True}
        },
        "risk_level": "LOW"
    },
    "mt5_symbol_info": {
        "function": mt5_symbol_info,
        "description": "Retorna informações detalhadas do símbolo",
        "parameters": {
            "symbol": {"type": "string", "required": True}
        },
        "risk_level": "LOW"
    },
    "mt5_scanner": {
        "function": mt5_scanner,
        "description": "Scanneia múltiplos símbolos retornando ticks atuais",
        "parameters": {
            "symbols": {"type": "array", "required": True}
        },
        "risk_level": "LOW"
    }
}


def register_mt5_tools(tool_registry):
    """
    Registra todos os MT5 tools no ToolRegistry

    Args:
        tool_registry: Instância do ToolRegistry
    """
    for tool_name, tool_config in MT5_TOOLS.items():
        tool_registry.register_tool(
            name=tool_name,
            function=tool_config["function"],
            description=tool_config["description"],
            parameters=tool_config["parameters"],
            risk_level=tool_config["risk_level"]
        )

    logger.info(f"Registrados {len(MT5_TOOLS)} MT5 tools no ToolRegistry")
```

**Deliverable:** `mt5_tools.py` completo

---

### 3.2 Testes dos MT5 Tools

**Localização:** `C:\GoldenAI\studio\golden_ai_studio_web\tests\test_mt5_tools.py`

```python
"""
Testes para MT5 Tools
"""
import pytest
from core.mt5_tools import (
    mt5_status,
    mt5_account_info,
    mt5_positions,
    mt5_orders,
    mt5_market_tick,
    mt5_symbol_info,
    mt5_scanner
)


def test_mt5_status():
    """Testa mt5_status"""
    result = mt5_status()
    assert "connected" in result
    if result["connected"]:
        assert "terminal_info" in result


def test_mt5_account_info():
    """Testa mt5_account_info"""
    result = mt5_account_info()
    # Se MT5 não estiver conectado, vai retornar erro
    if "error" not in result:
        assert "login" in result
        assert "balance" in result
        assert "equity" in result
        assert "trade_mode" in result


def test_mt5_positions():
    """Testa mt5_positions"""
    result = mt5_positions()
    if "error" not in result:
        assert "count" in result
        assert "positions" in result
        assert isinstance(result["positions"], list)


def test_mt5_orders():
    """Testa mt5_orders"""
    result = mt5_orders()
    if "error" not in result:
        assert "count" in result
        assert "orders" in result
        assert isinstance(result["orders"], list)


def test_mt5_market_tick():
    """Testa mt5_market_tick"""
    result = mt5_market_tick(symbol="WINJ24")
    if "error" not in result:
        assert result["symbol"] == "WINJ24"
        assert "bid" in result
        assert "ask" in result
        assert "spread" in result


def test_mt5_symbol_info():
    """Testa mt5_symbol_info"""
    result = mt5_symbol_info(symbol="WINJ24")
    if "error" not in result:
        assert result["symbol"] == "WINJ24"
        assert "digits" in result
        assert "point" in result
        assert "volume_min" in result


def test_mt5_scanner():
    """Testa mt5_scanner"""
    symbols = ["WINJ24", "WDOJ24"]
    result = mt5_scanner(symbols=symbols)
    if "error" not in result:
        assert "scanned" in result
        assert "symbols" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Deliverable:** `test_mt5_tools.py` completo

---

## 🔗 Etapa 4: Integração com ToolRegistry (2-3 dias)

### 4.1 Modificar JarvisService para Registrar Tools

**Arquivo:** `C:\GoldenAI\studio\golden_ai_studio_web\core\jarvis_core.py`

```python
# Adicionar imports
from core.golden_tools import register_golden_tools
from core.mt5_tools import register_mt5_tools

class JarvisService:
    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.security_manager = SecurityManager()
        self.audit_log = AuditLog()
        self.brain = Brain()
        self.model_router = ModelRouter()

        # Registrar Golden Tools
        register_golden_tools(self.tool_registry)

        # Registrar MT5 Tools
        register_mt5_tools(self.tool_registry)

        logger.info("Jarvis Service initialized with Golden + MT5 tools")
```

---

### 4.2 Verificação de Registro

**Script de Verificação:**

```python
# verify_tools.py
from core.jarvis_core import JarvisService

jarvis = JarvisService()
tools = jarvis.tool_registry.list_tools()

print(f"\n📊 Total de Tools Registrados: {len(tools)}\n")

golden_tools = [t for t in tools if t.startswith("golden_")]
mt5_tools = [t for t in tools if t.startswith("mt5_")]

print(f"✅ Golden Tools: {len(golden_tools)}")
for tool in golden_tools:
    print(f"   - {tool}")

print(f"\n✅ MT5 Tools: {len(mt5_tools)}")
for tool in mt5_tools:
    print(f"   - {tool}")

print(f"\n🎯 FASE 2 Status: {'✅ COMPLETO' if len(golden_tools) >= 7 and len(mt5_tools) >= 7 else '🔴 INCOMPLETO'}")
```

---

## ✅ Etapa 5: Documentação (1-2 dias)

### 5.1 Atualizar AGENTS.md

**Seção a adicionar:**

```markdown
## 🔧 Golden Tools (READ-ONLY)

### Available Tools:

1. **golden_status()** - Status geral do Golden
2. **golden_analyze(symbol, timeframe, depth)** - Análise técnica
3. **golden_scan(symbols, timeframe, filters)** - Scanner de mercado
4. **golden_risk(symbol, entry, stop_loss, target, risk_percent)** - Cálculo de risco
5. **golden_list_strategies()** - Lista estratégias disponíveis
6. **golden_strategy_info(strategy_id)** - Informações de estratégia
7. **golden_backtest(strategy_id, symbol, start_date, end_date, initial_balance)** - Backtest

## 📊 MT5 Tools (READ-ONLY)

### Available Tools:

1. **mt5_status()** - Status da conexão MT5
2. **mt5_account_info()** - Informações da conta
3. **mt5_positions(symbol?)** - Posições abertas
4. **mt5_orders(symbol?)** - Ordens pendentes
5. **mt5_market_tick(symbol)** - Tick atual do mercado
6. **mt5_symbol_info(symbol)** - Informações do símbolo
7. **mt5_scanner(symbols)** - Scanner de múltiplos símbolos

### ⚠️ IMPORTANTE:
- TODOS os tools acima são READ-ONLY
- Nenhum tool permite abrir/fechar posições
- Trading actions serão implementados apenas na FASE 14
- Sempre verificar trading_mode antes de executar qualquer operação
```

---

### 5.2 Criar FASE_2_COMPLETED.md

```markdown
# ✅ FASE 2 COMPLETADA

**Data Conclusão:** [DATA]
**Duração:** [X] dias

## ✅ Objetivos Alcançados:

1. ✅ [X] Golden components conectados ao ToolRegistry
2. ✅ [Y] MT5 read-only tools implementados
3. ✅ [Z] testes criados e passing
4. ✅ Documentação atualizada
5. ✅ Integração verificada

## 📊 Métricas:

- Golden Tools: [X] tools registrados
- MT5 Tools: [Y] tools registrados
- Tests: [Z] tests passing
- Code Coverage: [X]%

## 🎯 Próximo Passo:

**FASE 3: Computer Use**
- Estimativa: 2 semanas
- Início: [DATA]
```

---

## ✅ Checklist Geral da FASE 2

### Descoberta (2-3 dias)
- [ ] Listar todos os Golden components existentes
- [ ] Mapear funcionalidades MT5 necessárias
- [ ] Auditar código MT5 existente
- [ ] Criar inventários e especificações

### Golden Tools (5-7 dias)
- [ ] Criar `golden_tools.py` com 7+ tools
- [ ] Implementar golden_status
- [ ] Implementar golden_analyze
- [ ] Implementar golden_scan
- [ ] Implementar golden_risk
- [ ] Implementar golden_list_strategies
- [ ] Implementar golden_strategy_info
- [ ] Implementar golden_backtest
- [ ] Criar `test_golden_tools.py`
- [ ] Executar testes e garantir passing

### MT5 Tools (5-7 dias)
- [ ] Criar `mt5_tools.py` com 7+ tools
- [ ] Implementar mt5_status
- [ ] Implementar mt5_account_info
- [ ] Implementar mt5_positions
- [ ] Implementar mt5_orders
- [ ] Implementar mt5_market_tick
- [ ] Implementar mt5_symbol_info
- [ ] Implementar mt5_scanner
- [ ] Criar `test_mt5_tools.py`
- [ ] Executar testes e garantir passing

### Integração (2-3 dias)
- [ ] Modificar JarvisService para registrar Golden tools
- [ ] Modificar JarvisService para registrar MT5 tools
- [ ] Criar script de verificação
- [ ] Testar integração end-to-end
- [ ] Verificar todos os tools acessíveis via Jarvis

### Documentação (1-2 dias)
- [ ] Atualizar AGENTS.md com novos tools
- [ ] Criar FASE_2_COMPLETED.md
- [ ] Atualizar CHANGELOG.md
- [ ] Criar exemplos de uso
- [ ] Commit final com tag de versão

### Validação Final
- [ ] Todos os tests passing (Golden + MT5)
- [ ] Jarvis consegue chamar todos os tools
- [ ] Logs confirmando registro correto
- [ ] Performance verificada
- [ ] Sem memory leaks
- [ ] Git commit criado
- [ ] FASE 2 marcada como ✅ COMPLETA

---

## 📅 Cronograma Sugerido

### Semana 1:
- **Dia 1-2:** Descoberta e inventário
- **Dia 3-5:** Implementação Golden Tools (50%)

### Semana 2:
- **Dia 6-7:** Completar Golden Tools + testes
- **Dia 8-10:** Implementação MT5 Tools

### Semana 3:
- **Dia 11-12:** Completar MT5 Tools + testes
- **Dia 13-14:** Integração + documentação
- **Dia 15:** Validação final + commit

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Golden components incompletos | MÉDIA | ALTO | Implementar stubs funcionais primeiro |
| MT5 não conecta | BAIXA | ALTO | Testar conexão MT5 no início |
| Performance ruim | BAIXA | MÉDIO | Otimizar queries e caching |
| Testes falham | MÉDIA | MÉDIO | Corrigir incrementalmente |
| Integração com ToolRegistry falha | BAIXA | ALTO | Testar registro isoladamente primeiro |

---

## 📈 Métricas de Sucesso

### Mínimo Viável (FASE 2 Completa):
- ✅ 7+ Golden tools funcionais
- ✅ 7+ MT5 read-only tools funcionais
- ✅ 14+ testes passing
- ✅ Jarvis consegue chamar todos os tools
- ✅ Documentação atualizada

### Ideal (Excelência):
- ✅ 12+ Golden tools
- ✅ 10+ MT5 tools
- ✅ 25+ testes passing
- ✅ Code coverage >80%
- ✅ Performance otimizada
- ✅ Logs estruturados
- ✅ Exemplos de uso documentados

---

**FIM DO PLANO DE AÇÃO FASE 2**

*Após completar este plano, o projeto estará pronto para FASE 3 (Computer Use)*
