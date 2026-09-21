"""
Meta-estrategia do Golden AI.

Esta camada nao inventa entradas. Ela usa o scanner existente, classifica o
ambiente do ativo, abre as carteiras compativeis e ranqueia os setups liberados.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional


PORTFOLIOS = {
    "trend": {
        "name": "Tendencia",
        "description": "Busca continuacao, rompimentos e pullbacks alinhados ao fluxo principal.",
        "timeframes": "M15 / H1 / H4",
        "regimes": ["trending"],
        "volatility": ["NORMAL", "HIGH"],
        "keywords": ["BRK", "BREAKOUT", "PULLBACK", "CONTINUATION", "BOS", "ORB", "VWAP_PULLBACK", "VWAP_ANCHORED", "MOMENTUM", "MA_CROSS", "STRUCT_BREAK", "TURTLE", "DARVAS", "CA_C1"],
    },
    "range": {
        "name": "Mercado lateral",
        "description": "Opera rejeicoes nas extremidades e retornos a media dentro do range.",
        "timeframes": "M5 / M15 / H1",
        "regimes": ["ranging"],
        "volatility": ["LOW", "NORMAL"],
        "keywords": ["FALSE", "FADE", "REJECTION", "MEAN_RETURN", "VWAP_FADE", "SR_REJECTION", "MACRO_REV", "GAP_FILL"],
    },
    "compression": {
        "name": "Rompimento de compressao",
        "description": "Aguarda acumulacao, contracao de volatilidade e rompimento confirmado por volume.",
        "timeframes": "M15 / H1 / H4",
        "regimes": ["compression", "low_vol"],
        "volatility": ["LOW", "NORMAL"],
        "keywords": ["SQUEEZE", "COMPRESSION", "TRIANGLE", "CONSOLIDATION", "BREAKOUT_BANDIT", "VOL_EXPANSION", "DARVAS", "CA_C1"],
    },
    "scalp_micro": {
        "name": "Scalping de baixa amplitude",
        "description": "Busca movimentos curtos com spread, sessao e risco controlados.",
        "timeframes": "M1 / M5 / M15",
        "regimes": ["trending", "ranging"],
        "volatility": ["LOW", "NORMAL"],
        "keywords": ["SCALP", "MICRO", "VWAP_REAL", "VWAP_PULLBACK", "SESSION_HL"],
    },
    "high_vol": {
        "name": "Alta volatilidade controlada",
        "description": "Trabalha impulsos fortes reduzindo exposicao e exigindo confirmacao de liquidez.",
        "timeframes": "M5 / M15 / H1",
        "regimes": ["volatile", "trending"],
        "volatility": ["HIGH"],
        "keywords": ["MOMENTUM", "BRK", "BREAKOUT", "ORB", "PA_SNIPER", "PULLBACK", "CONTINUATION"],
    },
    "reversal": {
        "name": "Reversao",
        "description": "Procura exaustao, varredura de liquidez e mudanca de estrutura.",
        "timeframes": "M5 / M15 / H1",
        "regimes": ["ranging", "transition", "volatile"],
        "volatility": ["NORMAL", "HIGH"],
        "keywords": ["REV", "REJECTION", "FALSE", "LIQ", "SWEEP", "CHOCH", "DIVERGENCE", "MACD_DIV", "MEAN_RETURN", "VOLUME_PROFILE"],
    },
}


SYMBOL_PROFILES = {
    "XAU": {"priority": ["trend", "high_vol", "compression"], "notes": "Ouro: sensivel a dolar, juros, CPI/FOMC/NFP e abertura de NY."},
    "EUR": {"priority": ["trend", "range", "compression"], "notes": "EURUSD: liquidez boa; respeita sessoes Londres/NY."},
    "GBP": {"priority": ["high_vol", "compression", "trend"], "notes": "GBPUSD: movimentos fortes e falsos rompimentos frequentes."},
    "JPY": {"priority": ["trend", "high_vol"], "notes": "JPY: sensivel a juros e politica monetaria."},
    "BTC": {"priority": ["trend", "compression", "reversal"], "notes": "Cripto: muda rapido de regime e opera 24/7."},
}


MISSING_IMPORTANT_STRATEGIES = [
    {"name": "Turtle Breakout", "portfolio": "Tendencia", "reason": "Bom para tendencias persistentes em H1/H4/D1."},
    {"name": "Darvas Box", "portfolio": "Compressao/Tendencia", "reason": "Organiza rompimentos apos caixa de acumulacao."},
    {"name": "CA + C1", "portfolio": "Abertura/Tendencia", "reason": "Especialmente util em XAUUSD, indices e sessoes Londres/NY."},
    {"name": "Volume Profile Rejection", "portfolio": "Reversao/Lateral", "reason": "Ajuda a filtrar rejeicao em regioes de alto volume."},
    {"name": "VWAP Ancorada", "portfolio": "Tendencia/Reversao", "reason": "Melhora leitura de preco justo apos noticias e impulsos."},
]


@dataclass
class RegimeProfile:
    symbol: str
    direction: str
    structure: str
    regime: str
    confidence: float
    volatility: str
    liquidity: str
    momentum: str
    session: str
    news_risk: str
    correlation: str
    notes: List[str]


def _symbol_key(symbol: str) -> str:
    s = (symbol or "").upper()
    for key in SYMBOL_PROFILES:
        if key in s:
            return key
    return ""


def _as_dict(obj):
    if obj is None:
        return None
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    return getattr(obj, "__dict__", {})


def _trend_direction(scan) -> str:
    trends = [getattr(scan, "trend_h4", ""), getattr(scan, "trend_h1", ""), getattr(scan, "trend_m15", ""), getattr(scan, "trend_m5", "")]
    up = sum(1 for t in trends if str(t).lower() == "alta")
    down = sum(1 for t in trends if str(t).lower() == "baixa")
    if up >= 3:
        return "BUY"
    if down >= 3:
        return "SELL"
    if up > down:
        return "BUY_WEAK"
    if down > up:
        return "SELL_WEAK"
    return "NEUTRAL"


def classify_regime(scan) -> RegimeProfile:
    regime = str(getattr(scan, "regime", "unknown") or "unknown").lower()
    volatility = str(getattr(scan, "volatility", "NORMAL") or "NORMAL").upper()
    adx = float(getattr(scan, "adx", 0) or 0)
    rsi_h1 = float(getattr(scan, "rsi_h1", 50) or 50)
    spread = float(getattr(scan, "spread", 0) or 0)
    spread_usd = float(getattr(scan, "spread_usd", 0) or 0)
    regime_score = float(getattr(scan, "regime_score", 0) or 0)
    session = str(getattr(scan, "session", "OFF") or "OFF")
    direction = _trend_direction(scan)
    notes = []

    if regime in ("low_vol",) and volatility == "LOW":
        structure = "compressao"
    elif regime in ("compression",):
        structure = "compressao"
    elif regime == "ranging":
        structure = "lateral"
    elif regime == "transition":
        structure = "transicao"
    elif regime in ("trending", "volatile"):
        structure = "tendencia" if direction != "NEUTRAL" else "transicao"
    else:
        structure = "indefinido"

    if adx >= 28:
        momentum = "STRONG"
    elif adx >= 18 or rsi_h1 >= 58 or rsi_h1 <= 42:
        momentum = "MEDIUM"
    else:
        momentum = "WEAK"

    liquidity = "GOOD"
    if spread_usd > 0.8 or spread > 80:
        liquidity = "POOR"
        notes.append("Spread/liquidez exige cautela.")
    elif spread_usd > 0.35 or spread > 35:
        liquidity = "ACCEPTABLE"

    if volatility == "EXTREME":
        notes.append("Volatilidade extrema: evitar perseguir preco.")
    if regime == "transition":
        notes.append("Regime em transicao: exigir confirmacao maior.")
    if not getattr(scan, "session_active", False):
        notes.append("Fora da melhor janela operacional do ativo.")

    news_risk = "NORMAL"
    try:
        from risk_engine import get_risk_engine
        news = get_risk_engine().check_news_proximity()
        if news.get("near_news"):
            news_risk = "BLOCKED" if news.get("impact") == "HIGH" else "CAUTION"
            notes.append("Evento macro proximo: %s." % news.get("event_name", "desconhecido"))
    except Exception:
        news_risk = "UNKNOWN"

    skey = _symbol_key(getattr(scan, "symbol", ""))
    if skey and SYMBOL_PROFILES[skey].get("notes"):
        notes.append(SYMBOL_PROFILES[skey]["notes"])

    confidence = max(0.0, min(100.0, regime_score))
    return RegimeProfile(
        symbol=getattr(scan, "symbol", ""),
        direction=direction,
        structure=structure,
        regime=regime.upper(),
        confidence=round(confidence, 1),
        volatility=volatility,
        liquidity=liquidity,
        momentum=momentum,
        session=session,
        news_risk=news_risk,
        correlation="NEUTRAL",
        notes=notes,
    )


def select_portfolios(regime: RegimeProfile, symbol: str) -> List[Dict]:
    active = []
    skey = _symbol_key(symbol)
    priority = SYMBOL_PROFILES.get(skey, {}).get("priority", [])
    for pid, cfg in PORTFOLIOS.items():
        score = 0
        reasons = []
        if regime.regime.lower() in cfg["regimes"]:
            score += 45
            reasons.append("regime compativel")
        if regime.volatility in cfg["volatility"]:
            score += 25
            reasons.append("volatilidade compativel")
        if pid in priority:
            score += 15
            reasons.append("perfil do ativo favorece")
        if pid == "trend" and regime.momentum in ("MEDIUM", "STRONG") and regime.direction in ("BUY", "SELL"):
            score += 15
            reasons.append("direcao e momentum alinhados")
        if pid == "scalp_micro" and regime.liquidity == "GOOD" and regime.news_risk == "NORMAL":
            score += 10
            reasons.append("liquidez boa para scalp")
        if regime.volatility == "EXTREME" and pid not in ("high_vol",):
            score -= 35
        score = max(0, min(100, score))
        if score >= 45:
            active.append({"id": pid, "name": cfg["name"], "score": score, "reasons": reasons})
    active.sort(key=lambda x: x["score"], reverse=True)
    return active


def _portfolio_match(setup, active_portfolios) -> Dict:
    setup_id = str(getattr(setup, "setup_id", "") or "").upper()
    setup_name = str(getattr(setup, "name", "") or "").upper()
    text = setup_id + " " + setup_name
    best = {"portfolio": None, "score": 25, "reason": "sem carteira ideal"}
    for p in active_portfolios:
        cfg = PORTFOLIOS.get(p["id"], {})
        matched = any(k in text for k in cfg.get("keywords", []))
        if matched:
            score = min(100, 50 + p["score"] * 0.5)
            if score > best["score"]:
                best = {"portfolio": p["id"], "score": score, "reason": "setup pertence a carteira ativa"}
    return best


def portfolio_catalog() -> List[Dict]:
    """Expõe as carteiras e os setups cadastrados para a tela operacional."""
    try:
        from strategy_engine import list_strategies
        strategies = list_strategies()
    except Exception:
        strategies = []
    catalog = []
    for pid, cfg in PORTFOLIOS.items():
        keywords = cfg.get("keywords", [])
        items = []
        for strategy in strategies:
            text = f"{strategy.get('id', '')} {strategy.get('name', '')}".upper()
            if any(k in text for k in keywords):
                items.append({
                    "id": strategy.get("id", ""),
                    "name": strategy.get("name", ""),
                    "mode": strategy.get("mode", ""),
                    "tier": strategy.get("tier", ""),
                    "description": strategy.get("description", ""),
                })
        catalog.append({
            "id": pid,
            "name": cfg["name"],
            "description": cfg.get("description", ""),
            "timeframes": cfg.get("timeframes", ""),
            "strategies": items,
        })
    return catalog


def _historical_score(setup_id: str, performance: Optional[Dict]) -> float:
    if not performance:
        return 50.0
    item = performance.get(setup_id, {}) if isinstance(performance, dict) else {}
    pf = float(item.get("profit_factor", 0) or 0)
    exp = float(item.get("expectancy_r", 0) or 0)
    total = float(item.get("total", 0) or 0)
    if total < 10:
        return 50.0
    score = 50 + min(25, max(-20, (pf - 1.0) * 20)) + min(25, max(-15, exp * 25))
    return max(0.0, min(100.0, score))


def rank_setups(scan, regime: RegimeProfile, active_portfolios: List[Dict], performance: Optional[Dict] = None) -> List[Dict]:
    ranked = []
    for setup in getattr(scan, "setups", []) or []:
        if not getattr(setup, "enabled", True):
            continue
        readiness = float(getattr(setup, "readiness", 0) or 0)
        confluence = float(getattr(setup, "confluence_score", 0) or 0)
        rr = float(getattr(setup, "rr_ratio", 0) or 0)
        spread_ok = bool(getattr(setup, "spread_ok", True))
        regime_match = bool(getattr(setup, "regime_match", False))
        session_match = bool(getattr(setup, "session_match", False))
        setup_id = str(getattr(setup, "setup_id", ""))
        setup_direction = str(getattr(setup, "direction", "NEUTRO") or "NEUTRO").upper()
        pm = _portfolio_match(setup, active_portfolios)
        hist = _historical_score(setup_id, performance)
        strong_direction = regime.direction in ("BUY", "SELL") and regime.confidence >= 70 and regime.structure == "tendencia"
        contra_regime = strong_direction and setup_direction in ("BUY", "SELL") and setup_direction != regime.direction

        regime_score = 85 if regime_match else pm["score"]
        if contra_regime:
            regime_score = min(regime_score, 25)
        vol_score = 90 if regime.volatility in ("NORMAL", "HIGH") else 65 if regime.volatility == "LOW" else 35
        session_score = 90 if session_match else 55
        mtf_score = confluence
        compatibility = (
            0.30 * regime_score
            + 0.20 * vol_score
            + 0.15 * session_score
            + 0.15 * hist
            + 0.10 * mtf_score
            + 0.10 * readiness
        )

        rr_score = 100 if rr >= 3 else 80 if rr >= 2 else 60 if rr >= 1.5 else 35 if rr > 0 else 0
        liquidity_score = 95 if spread_ok and regime.liquidity == "GOOD" else 70 if spread_ok else 20
        force_score = 90 if regime.momentum == "STRONG" else 70 if regime.momentum == "MEDIUM" else 45
        trigger_score = 90 if getattr(setup, "level_label", "") == "OPORTUNIDADE" else 70 if readiness >= 60 else 45
        quality = (
            0.35 * readiness
            + 0.20 * confluence
            + 0.15 * rr_score
            + 0.10 * liquidity_score
            + 0.10 * force_score
            + 0.10 * trigger_score
        )

        gates = []
        if contra_regime:
            gates.append("direcao contraria ao regime dominante")
        if compatibility < 60:
            gates.append("compatibilidade abaixo de 60")
        if not spread_ok:
            gates.append("spread alto")
        if regime.volatility == "EXTREME":
            gates.append("volatilidade extrema")
        if regime.regime == "TRANSITION" and compatibility < 75:
            gates.append("transicao sem score suficiente")
        if rr > 0 and rr < 1.2:
            gates.append("R:R fraco")

        final_score = round((compatibility * 0.55) + (quality * 0.45), 1)
        if gates:
            status = "BLOQUEADO"
        elif compatibility >= 85 and quality >= 85:
            status = "OPORTUNIDADE"
        elif compatibility >= 75 and quality >= 70:
            status = "PRE_ENTRADA"
        elif compatibility >= 60:
            status = "MONITORAR"
        else:
            status = "BLOQUEADO"

        ranked.append({
            "setup_id": setup_id,
            "name": getattr(setup, "name", ""),
            "mode": getattr(setup, "mode", ""),
            "tier": getattr(setup, "tier", ""),
            "direction": setup_direction,
            "portfolio": pm["portfolio"],
            "portfolio_reason": pm["reason"],
            "compatibility_score": round(compatibility, 1),
            "entry_quality_score": round(quality, 1),
            "final_score": final_score,
            "status": status,
            "blocks": gates,
            "rr_ratio": rr,
            "readiness": readiness,
            "confluence_score": confluence,
            "expectancy": float(getattr(setup, "expectancy", 0) or 0),
            "details": getattr(setup, "details", ""),
        })
    status_rank = {"OPORTUNIDADE": 0, "PRE_ENTRADA": 1, "MONITORAR": 2, "BLOQUEADO": 3}
    ranked.sort(key=lambda x: (status_rank.get(x["status"], 9), -x["final_score"]))
    return ranked


def risk_summary(scan, ranked: List[Dict], regime: RegimeProfile) -> Dict:
    blockers = []
    if regime.liquidity == "POOR":
        blockers.append("liquidez/spread ruim")
    if regime.volatility == "EXTREME":
        blockers.append("volatilidade extrema")
    if regime.news_risk == "BLOCKED":
        blockers.append("noticia bloqueando")
    if getattr(scan, "session_active", False) is False:
        blockers.append("fora da melhor sessao")
    best = next((x for x in ranked if x.get("status") != "BLOQUEADO"), None)
    if best is None and ranked:
        blockers.extend(ranked[0].get("blocks", []))
    risk_pct = 0.5
    if regime.regime == "TRANSITION" or blockers:
        risk_pct = 0.25
    best_candidate = next((x for x in ranked if x.get("status") != "BLOQUEADO"), None)
    if best_candidate is None and ranked:
        best_candidate = ranked[0]
    operational = {"allowed": True, "reason": "nao consultado", "details": {}, "positions_count": 0}
    try:
        from mt5_connector import get_positions
        from risk_engine import get_risk_engine
        raw_positions = get_positions() or []
        positions = [{"symbol": getattr(p, "symbol", ""), "entry": float(getattr(p, "price_open", 0) or 0),
                      "sl": float(getattr(p, "sl", 0) or 0), "current_price": float(getattr(p, "price_current", 0) or 0)} for p in raw_positions]
        engine = get_risk_engine()
        if best_candidate:
            allowed, reason, details = engine.can_trade(getattr(scan, "symbol", ""), best_candidate.get("direction"), positions)
            operational = {"allowed": allowed, "reason": reason, "details": details, "positions_count": len(positions)}
            if not allowed:
                blockers.extend(details.values())
    except Exception as exc:
        operational = {"allowed": False, "reason": "risco operacional indisponivel", "details": {"error": str(exc)}, "positions_count": 0}
        blockers.append("risco operacional indisponivel")
    blockers = list(dict.fromkeys(blockers))
    if best and best["status"] == "OPORTUNIDADE" and not blockers and operational["allowed"]:
        action = "PODE_PREPARAR_ORDEM"
    elif best and best["status"] in ("PRE_ENTRADA", "MONITORAR"):
        action = "MONITORAR"
    else:
        action = "BLOQUEAR"
    return {
        "action": action,
        "suggested_risk_pct": risk_pct,
        "blockers": blockers,
        "operational": operational,
        "news_risk": regime.news_risk,
        "rules": ["limite por ativo", "limite por moeda", "limite diario", "bloqueio apos sequencia de stops"],
    }


def analyze_symbol(symbol: str, scanner=None, performance: Optional[Dict] = None) -> Dict:
    if scanner is None:
        from golden_scanner import GoldenScanner
        scanner = GoldenScanner()
    scan = scanner.scan_symbol(symbol)
    regime = classify_regime(scan)
    portfolios = select_portfolios(regime, symbol)
    ranked = rank_setups(scan, regime, portfolios, performance)
    best = next((x for x in ranked if x.get("status") != "BLOQUEADO"), None)
    top_candidate = ranked[0] if ranked else None
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "symbol": symbol,
        "regime": asdict(regime),
        "active_portfolios": portfolios,
        "portfolio_catalog": portfolio_catalog(),
        "monitored_symbols": list(getattr(scanner, "RADAR_SYMBOLS", []) or []),
        "best_opportunity": best,
        "top_candidate": top_candidate,
        "ranked_setups": ranked,
        "blocked_setups": [x for x in ranked if x["status"] == "BLOQUEADO"][:12],
        "risk": risk_summary(scan, ranked, regime),
        "market_snapshot": {
            "price": getattr(scan, "price", 0),
            "spread": getattr(scan, "spread", 0),
            "score_total": getattr(scan, "score_total", 0),
            "trend_h4": getattr(scan, "trend_h4", ""),
            "trend_h1": getattr(scan, "trend_h1", ""),
            "trend_m15": getattr(scan, "trend_m15", ""),
            "trend_m5": getattr(scan, "trend_m5", ""),
            "adx": getattr(scan, "adx", 0),
            "bb_width": getattr(scan, "bb_width", 0),
            "volume_ratio": getattr(scan, "volume_ratio", 0),
        },
        "missing_important_strategies": MISSING_IMPORTANT_STRATEGIES,
    }


def analyze_radar(symbols: Optional[List[str]] = None, limit: int = 8) -> Dict:
    from golden_scanner import GoldenScanner
    try:
        from statistics_engine import StatisticsEngine
        performance = StatisticsEngine().get_strategy_performance()
    except Exception:
        performance = {}
    scanner = GoldenScanner()
    if not symbols:
        symbols = list(getattr(scanner, "RADAR_SYMBOLS", []))[:limit]
    items = []
    for symbol in symbols[:limit]:
        try:
            items.append(analyze_symbol(symbol, scanner=scanner, performance=performance))
        except Exception as e:
            items.append({"ok": False, "symbol": symbol, "error": str(e)})
    opportunities = [x for x in items if x.get("ok") and x.get("best_opportunity")]
    opportunities.sort(key=lambda x: x["best_opportunity"]["final_score"], reverse=True)
    return {"ok": True, "generated_at": datetime.now().isoformat(), "items": items, "top_opportunities": opportunities[:5]}
