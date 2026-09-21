"""
Golden AI - Chat de Mercado

Extraído de golden_ai.py (linhas 309-858).
Análise de mercado, datasets, regimes, sinais.
"""

import os
import json
from pathlib import Path

from .context import CFG, SERVICES, SESSION
from .utils import (
    normalizar_texto_intencao, detectar_idioma_resposta,
    extrair_studio_context_path,
)
from .files import caminho_seguro, nome_para_projetos

# Estado de sessão
MARKET_LAST_ANALYSIS_ID = None


# ============================================================
# SERVICE WRAPPERS
# ============================================================

def _market_service():
    """Retorna instância do MarketAnalysisService."""
    try:
        from market import MarketAnalysisService
        return MarketAnalysisService(CFG.ROOT if hasattr(CFG, 'ROOT') else r"C:\GoldenAI")
    except Exception:
        raise RuntimeError("Market V1 indisponivel.")


def _market_audit(action_type, status, target="", detail=""):
    """Registra auditoria de operação de mercado."""
    if not SERVICES.AUDIT_LOGGER:
        return
    try:
        SERVICES.AUDIT_LOGGER.record({
            "action_type": action_type,
            "status": status,
            "session_id": CFG.SESSION_ID,
            "agent": "golden_ai.market_chat.v1",
            "target": str(target or ""),
            "result": str(detail)[:600] if detail else "",
            "files_changed": [],
            "commands_executed": [],
        })
    except Exception:
        pass


# ============================================================
# DATA HELPERS
# ============================================================

def _market_synthetic_rows(direction="up"):
    """Gera dados sintéticos para teste."""
    closes = [100, 102, 104, 106, 108, 110] if direction != "down" else [110, 108, 106, 104, 102, 100]
    rows = []
    anterior = closes[0]
    for indice, close in enumerate(closes, start=1):
        rows.append({
            "timestamp": f"2026-01-{indice:02d}T00:00:00+00:00",
            "open": anterior,
            "high": max(anterior, close) + 0.5,
            "low": min(anterior, close) - 0.5,
            "close": close,
        })
        anterior = close
    return rows


def _market_report_from_tool_result(resultado):
    """Extrai report de um resultado de ferramenta."""
    if isinstance(resultado, dict) and "report" in resultado and isinstance(resultado["report"], dict):
        if "report" in resultado["report"] and isinstance(resultado["report"]["report"], dict):
            return resultado["report"]["report"]
        return resultado["report"]
    if isinstance(resultado, dict) and "symbol" in resultado and "inferred" in resultado:
        return resultado
    return None


def _market_analysis_id_from_result(resultado):
    """Extrai analysis_id de um resultado."""
    if isinstance(resultado, dict):
        return resultado.get("analysis_id") or resultado.get("report", {}).get("analysis_id")
    return None


def _evidence_text(value):
    """Formata texto de evidência."""
    texto = str(value or "")
    if "." in texto:
        return texto.rsplit(".", 1)[-1]
    return texto


# ============================================================
# MARKET OPERATIONS
# ============================================================

def market_analyze_dataset(nome="", symbol="DATASET", timeframe="H1", synthetic=""):
    """Executa análise de mercado em um dataset."""
    global MARKET_LAST_ANALYSIS_ID
    _market_audit("MARKET_ANALYSIS_STARTED", "STARTED", nome or synthetic, f"symbol={symbol}; timeframe={timeframe}")
    try:
        service = _market_service()
        if synthetic:
            from market import SyntheticMarketDataAdapter
            rows = _market_synthetic_rows(synthetic)
            adapter = SyntheticMarketDataAdapter({timeframe: rows})
            source = f"synthetic:{synthetic}"
        else:
            from market import LocalCsvMarketDataAdapter
            caminho = caminho_seguro(nome)
            if caminho is None:
                raise ValueError("dataset fora da pasta autorizada ou nome invalido")
            if not os.path.isfile(caminho):
                raise FileNotFoundError("dataset nao encontrado")
            if os.path.splitext(caminho)[1].lower() != ".csv":
                raise ValueError("Market V1 aceita apenas CSV local autorizado nesta rota")
            adapter = LocalCsvMarketDataAdapter(caminho, timeframe)
            source = f"csv:{os.path.basename(caminho)}"
        result = service.analyze(symbol or "DATASET", adapter, source=source)
        MARKET_LAST_ANALYSIS_ID = result.analysis_id
        _market_audit("MARKET_ANALYSIS_COMPLETED", "COMPLETED", result.analysis_id, result.result_hash)
        payload = result.report | {"analysis_id": result.analysis_id, "result_hash": result.result_hash}
        return payload
    except Exception as erro:
        _market_audit("MARKET_ANALYSIS_FAILED", "FAILED", nome or synthetic, str(erro))
        return {"ok": False, "erro": str(erro)}


def market_get_analysis(analysis_id=""):
    """Retorna uma análise de mercado."""
    service = _market_service()
    data = service.repository.get_analysis(analysis_id) if analysis_id else service.repository.get_latest_analysis()
    _market_audit("MARKET_RESULT_READ", "COMPLETED" if data else "FAILED", analysis_id or "latest", "analysis")
    return data or {"ok": False, "erro": "analise de mercado nao encontrada"}


def market_list_analyses(limit=10):
    """Lista análises de mercado."""
    data = _market_service().repository.list_analyses(int(limit))
    _market_audit("MARKET_RESULT_READ", "COMPLETED", "market_list_analyses", f"count={len(data)}")
    return data


def market_get_snapshot(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    return report.get("snapshots") if report else data


def market_get_regime(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    return report.get("inferred") if report else data


def market_get_multitimeframe_context(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    return report.get("multi_timeframe") if report else data


def market_get_structure(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    return report.get("structure") if report else data


def market_get_observations(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    return report.get("observed") if report else data


def market_get_signals(analysis_id=""):
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    return report.get("hypotheses") if report else data


def market_hypothesis_to_strategy_spec(analysis_id=""):
    """Converte hipótese de mercado em StrategySpec."""
    data = market_get_analysis(analysis_id)
    report = _market_report_from_tool_result(data)
    if not report:
        return data
    hipoteses = report.get("hypotheses") or []
    sinal = hipoteses[0] if hipoteses else {}
    spec = {
        "name": "Market hypothesis",
        "version": "1.0",
        "description": "Hipotese conceitual gerada a partir de Market V1; exige validacao Quant.",
        "symbol": report.get("symbol"),
        "timeframe": sinal.get("timeframe", ""),
        "entry_logic_identifier": "market_context_placeholder",
        "exit_logic_identifier": "hold_bars",
        "parameters": {
            "market_analysis_id": data.get("analysis_id") if isinstance(data, dict) else analysis_id,
            "alignment": (report.get("multi_timeframe") or {}).get("alignment"),
            "signal": sinal.get("signal", "NO_DIRECTIONAL_CONTEXT"),
        },
        "unknowns": {
            "validation_status": "NOT_BACKTESTED",
            "permission_required": "quant_backtest_before_use",
        },
    }
    _market_audit("MARKET_RESULT_READ", "COMPLETED", "market_hypothesis_to_strategy_spec", "NOT_BACKTESTED")
    return spec


# ============================================================
# CHAT RESponder
# ============================================================

def pergunta_pede_market(pergunta):
    """Verifica se a pergunta é sobre mercado."""
    texto = normalizar_texto_intencao(pergunta)
    if any(t in texto for t in ("nao quero falar de mercado", "nao vamos falar de mercado")):
        return False
    if any(t in texto for t in ("o que e tendencia", "o que significa volatilidade")):
        return False
    termos_dataset = ("este dataset", "esse dataset", "dataset de mercado", ".csv")
    termos_market = (
        "regime desse periodo", "regime da analise", "tendencia ou range",
        "timeframes estao alinhados", "estruturas foram detectadas",
        "observacoes", "sinal de compra", "sinal potencial", "analise de mercado",
        "ultima analise de mercado", "analise anterior", "voltando a analise",
        "transforme essa hipotese", "strategysp", "strategy spec", "validado",
    )
    return any(t in texto for t in termos_dataset) or any(t in texto for t in termos_market)


def _formatar_lista_regimes(regimes):
    if not regimes:
        return "Regime: nao encontrado."
    linhas = []
    for item in regimes:
        linhas.append(f"- {item.get('timeframe')}: {item.get('regime')} ({_evidence_text(item.get('evidence_level'))}, confianca {item.get('confidence')})")
    return "Regime\n" + "\n".join(linhas)


def _formatar_market_resposta(pergunta, resultado):
    """Formata resposta de análise de mercado."""
    texto = normalizar_texto_intencao(pergunta)
    report = _market_report_from_tool_result(resultado)
    if not report:
        return str(resultado.get("erro", resultado)) if isinstance(resultado, dict) else str(resultado)

    regimes = report.get("inferred") or []
    mtf = report.get("multi_timeframe") or {}
    estruturas = report.get("structure") or []
    observados = report.get("observed") or []
    hipoteses = report.get("hypotheses") or []
    limites = report.get("limitations") or []

    if "regime" in texto and "analise" not in texto:
        return _formatar_lista_regimes(regimes)
    if "timeframe" in texto or "alinhad" in texto:
        return f"Multi-timeframe: alinhamento {mtf.get('alignment')}. Conflitos: {', '.join(mtf.get('conflicts') or []) or 'nenhum'}."
    if "estrutura" in texto:
        partes = [f"- {e.get('timeframe')}: {e.get('basic_trend')}, suporte {e.get('support')}, resistencia {e.get('resistance')}" for e in estruturas]
        return "Estrutura detectada\n" + "\n".join(partes)
    if "observa" in texto:
        return "Observado\n" + "\n".join(f"- {o.get('timeframe')}: {o.get('statement')}" for o in observados[:8])
    if "sinal" in texto or "compra" in texto:
        return "Hipoteses/sinais\n" + "\n".join(f"- {h.get('timeframe')}: {h.get('signal')} ({_evidence_text(h.get('evidence_level'))}; nao validado)" for h in hipoteses)
    if "validado" in texto or "validated" in texto:
        return "Nenhum sinal foi marcado como VALIDATED sem teste Quant correspondente."

    return (
        f"Analise Market concluida: {report.get('symbol')}.\n\n"
        f"{_formatar_lista_regimes(regimes)}\n\n"
        f"Multi-timeframe: alinhamento {mtf.get('alignment')}.\n\n"
        "Estrutura\n"
        + "\n".join(f"- {e.get('timeframe')}: {e.get('basic_trend')}, suporte {e.get('support')}, resistencia {e.get('resistance')}" for e in estruturas)
        + "\n\nObservado\n"
        + "\n".join(f"- {o.get('timeframe')}: {o.get('statement')}" for o in observados[:6])
        + "\n\nHipoteses/sinais\n"
        + "\n".join(f"- {h.get('timeframe')}: {h.get('signal')} ({_evidence_text(h.get('evidence_level'))}; nao validado)" for h in hipoteses)
    )


def responder_market_chat(pergunta, historico, executar_tool_core_fn):
    """Responde a pergunta de mercado."""
    global MARKET_LAST_ANALYSIS_ID

    if not pergunta_pede_market(pergunta):
        return False

    texto = normalizar_texto_intencao(pergunta)
    caminho_contexto = extrair_studio_context_path(pergunta)
    analysis_id = MARKET_LAST_ANALYSIS_ID

    if "strategysp" in texto or "strategy spec" in texto or "transforme essa hipotese" in texto:
        resultado = market_hypothesis_to_strategy_spec(analysis_id or "")
        resposta = "StrategySpec preparado para teste Quant:\n" + json.dumps(resultado, ensure_ascii=False, indent=2)
    elif "ultima analise" in texto or "analise anterior" in texto:
        resultado = market_get_analysis(analysis_id or "")
        resposta = _formatar_market_resposta(pergunta, resultado)
    elif any(t in texto for t in ("regime", "timeframe", "alinhad", "estrutura", "sinal")) and analysis_id:
        resultado = market_get_analysis(analysis_id)
        resposta = _formatar_market_resposta(pergunta, resultado)
    else:
        if not caminho_contexto:
            resposta = "Preciso que voce selecione ou indique um dataset CSV de mercado autorizado primeiro."
        else:
            nome = nome_para_projetos(caminho_contexto)
            resultado = executar_tool_core_fn("market_analyze_dataset", {"nome": nome, "symbol": "DATASET", "timeframe": "H1"})
            resposta = _formatar_market_resposta(pergunta, resultado)

    historico.append({"role": "user", "content": pergunta})
    historico.append({"role": "assistant", "content": resposta})
    print()
    print("Golden AI:")
    print(resposta)
    print()
    return True
