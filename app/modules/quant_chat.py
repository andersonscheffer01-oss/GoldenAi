"""
Golden AI - Chat Quant

Extraído de golden_ai.py (linhas 900-1200).
Backtesting, métricas, experimentos.
"""

import os
import json

from .context import CFG, SERVICES
from .utils import normalizar_texto_intencao
from .files import caminho_seguro

# Estado de sessão
QUANT_LAST_EXPERIMENT_ID = None
QUANT_PREVIOUS_EXPERIMENT_ID = None
QUANT_LAST_STRATEGY_SPEC = None
QUANT_LAST_DATASET_PATH = None


# ============================================================
# SERVICE WRAPPERS
# ============================================================

def _quant_service():
    try:
        from quant import QuantService
        return QuantService(r"C:\GoldenAI")
    except Exception:
        raise RuntimeError("Quant V1 indisponivel.")


def _quant_audit(action_type, status, target="", detail=""):
    if not SERVICES.AUDIT_LOGGER:
        return
    try:
        SERVICES.AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CFG.SESSION_ID,
            "agent": "golden_ai.quant_chat.v1",
            "target": str(target or ""),
            "result": str(detail)[:600] if detail else "",
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


def _csv_rows_autorizado(nome):
    caminho = caminho_seguro(nome)
    if caminho is None:
        raise ValueError("dataset fora da pasta autorizada ou nome invalido")
    if not os.path.isfile(caminho):
        raise FileNotFoundError("dataset nao encontrado")
    if os.path.splitext(caminho)[1].lower() != ".csv":
        raise ValueError("Quant Chat V1 aceita apenas CSV local autorizado")
    from market import LocalCsvMarketDataAdapter
    return LocalCsvMarketDataAdapter(caminho, "H1").load()["H1"], caminho


def _strategy_spec_from_dict(data):
    from quant import StrategySpec
    if isinstance(data, StrategySpec):
        return data
    data = dict(data or {})
    if data.get("entry_logic_identifier") == "market_context_placeholder":
        signal = str((data.get("parameters") or {}).get("signal", ""))
        if "SHORT" in signal:
            entry = "close_below_open"
        elif "LONG" in signal:
            entry = "close_above_open"
        else:
            entry = "never"
    else:
        entry = data.get("entry_logic_identifier") or "never"
    params = dict(data.get("parameters") or {})
    params.setdefault("hold_bars", 1)
    return StrategySpec(
        strategy_id=data.get("strategy_id", ""),
        name=data.get("name", "Chat StrategySpec"),
        version=data.get("version", "1.0"),
        description=data.get("description", "StrategySpec executada via Quant Chat V1."),
        parameters=params,
        entry_logic_identifier=entry,
        exit_logic_identifier=data.get("exit_logic_identifier", "hold_bars"),
        created_at=data.get("created_at", ""),
        symbol=data.get("symbol", "DATASET"),
        timeframe=data.get("timeframe", "H1") or "H1",
        unknowns=data.get("unknowns", {}),
    )


# ============================================================
# QUANT OPERATIONS
# ============================================================

def quant_run_backtest(nome="", strategy_spec=None, initial_capital=10000.0,
                       quantity=1.0, spread=0.0, commission=0.0, slippage=0.0):
    global QUANT_LAST_EXPERIMENT_ID, QUANT_PREVIOUS_EXPERIMENT_ID
    global QUANT_LAST_STRATEGY_SPEC, QUANT_LAST_DATASET_PATH

    _quant_audit("QUANT_EXPERIMENT_REQUESTED", "REQUESTED", nome, "run_backtest")
    try:
        from quant import CostModel, build_backtest_spec
        rows, caminho = _csv_rows_autorizado(nome)
        service = _quant_service()
        spec_obj = _strategy_spec_from_dict(strategy_spec or QUANT_LAST_STRATEGY_SPEC)
        dataset = service.dataset_from_rows(rows, f"csv:{os.path.basename(caminho)}", spec_obj.symbol or "DATASET", spec_obj.timeframe or "H1")
        cost_model = CostModel(spread=float(spread), commission=float(commission), slippage=float(slippage))
        backtest_spec = build_backtest_spec(spec_obj, dataset, initial_capital=float(initial_capital), quantity=float(quantity), cost_model=cost_model, seed=1)
        experiment_id, payload = service.run_backtest(backtest_spec, rows)
        QUANT_PREVIOUS_EXPERIMENT_ID = QUANT_LAST_EXPERIMENT_ID
        QUANT_LAST_EXPERIMENT_ID = experiment_id
        QUANT_LAST_STRATEGY_SPEC = strategy_spec or QUANT_LAST_STRATEGY_SPEC
        QUANT_LAST_DATASET_PATH = caminho
        result = payload["result"]
        _quant_audit("QUANT_EXPERIMENT_COMPLETED", "COMPLETED", experiment_id, payload.get("result_hash", ""))
        return {
            "ok": True, "experiment_id": experiment_id, "status": "TESTED",
            "metrics": result.metrics.__dict__,
            "trades": [trade.__dict__ for trade in result.trades],
            "equity_curve": result.equity_curve,
            "limitations": result.limitations,
        }
    except Exception as erro:
        _quant_audit("QUANT_EXPERIMENT_FAILED", "FAILED", nome, str(erro))
        return {"ok": False, "erro": str(erro)}


def quant_get_experiment(experiment_id=""):
    experiment_id = experiment_id or QUANT_LAST_EXPERIMENT_ID
    if not experiment_id:
        return {"ok": False, "erro": "experimento Quant nao encontrado"}
    data = _quant_service().repo.get_backtest(experiment_id)
    return data or {"ok": False, "erro": "experimento Quant nao encontrado"}


def quant_get_metrics(experiment_id=""):
    data = quant_get_experiment(experiment_id)
    if isinstance(data, dict) and data.get("metrics_json"):
        return json.loads(data["metrics_json"])
    return data


def quant_get_trades(experiment_id=""):
    data = quant_get_experiment(experiment_id)
    if isinstance(data, dict) and data.get("trades_json"):
        return json.loads(data["trades_json"])
    return []


def quant_get_equity(experiment_id=""):
    data = quant_get_experiment(experiment_id)
    if isinstance(data, dict) and data.get("equity_json"):
        return json.loads(data["equity_json"])
    return []


def quant_list_experiments(limit=10):
    return _quant_service().repo.list_backtests(int(limit))


def quant_compare_experiments(experiment_a="", experiment_b=""):
    a = quant_get_experiment(experiment_a)
    b = quant_get_experiment(experiment_b)
    return {"experiment_a": a, "experiment_b": b}


# ============================================================
# CHAT RESponder
# ============================================================

def pergunta_pede_quant(pergunta):
    texto = normalizar_texto_intencao(pergunta)
    termos = (
        "backtest", "equity", "drawdown", "sharpe", "retorno",
        "rentabilidade", "metricas", "trade", "trades", "operacao",
        "operacoes", "capital", "posicao", "experimento quant",
    )
    return any(t in texto for t in termos)


def _formatar_quant_result(resultado):
    """Formata resultado de backtest."""
    if not isinstance(resultado, dict) or not resultado.get("ok"):
        return str(resultado.get("erro", resultado)) if isinstance(resultado, dict) else str(resultado)

    metrics = resultado.get("metrics", {})
    linhas = [
        f"Backtest concluido: {resultado.get('experiment_id', '?')}",
        f"Status: {resultado.get('status', '?')}",
        "",
        "Metricas:",
        f"  Retorno total: {metrics.get('total_return_pct', '?')}%",
        f"  Sharpe: {metrics.get('sharpe_ratio', '?')}",
        f"  Max Drawdown: {metrics.get('max_drawdown_pct', '?')}%",
        f"  Total trades: {metrics.get('total_trades', '?')}",
    ]

    limitations = resultado.get("limitations", [])
    if limitations:
        linhas.append("\nLimitacoes:")
        for l in limitations[:3]:
            linhas.append(f"  - {l}")

    return "\n".join(linhas)


def responder_quant_chat(pergunta, historico, executar_tool_core_fn):
    """Responde a pergunta quant."""
    texto = normalizar_texto_intencao(pergunta)

    if not pergunta_pede_quant(pergunta):
        return False

    if "backtest" in texto or "teste" in texto:
        resultado = executar_tool_core_fn("quant_run_backtest", {"nome": ""})
        resposta = _formatar_quant_result(resultado)
    elif "metrica" in texto or "metrics" in texto:
        resultado = executar_tool_core_fn("quant_get_metrics", {"experiment_id": ""})
        resposta = str(resultado)
    elif "trade" in texto:
        resultado = executar_tool_core_fn("quant_get_trades", {"experiment_id": ""})
        resposta = str(resultado)
    elif "equity" in texto:
        resultado = executar_tool_core_fn("quant_get_equity", {"experiment_id": ""})
        resposta = str(resultado)
    elif "listar" in texto or "lista" in texto:
        resultado = executar_tool_core_fn("quant_list_experiments", {"limit": 10})
        resposta = str(resultado)
    else:
        resultado = executar_tool_core_fn("quant_get_experiment", {"experiment_id": ""})
        resposta = _formatar_quant_result(resultado)

    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True
