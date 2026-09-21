#!/usr/bin/env python3
"""
Auditoria MT5 do Golden AI.

Compara a leitura do scanner com candles fechados do MetaTrader 5 e retorna
valores tecnicos suficientes para validar o sinal no grafico.
"""

from datetime import datetime, timezone
from dataclasses import asdict

import MetaTrader5 as mt5

from golden_scanner import GoldenScanner, SETUP_DEFINITIONS
from mt5_connector import ensure_connection


TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def _round_value(value, digits=5):
    try:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return round(float(value), digits)
    except Exception:
        pass
    return value


def _round_tree(obj, digits=5):
    if isinstance(obj, dict):
        return {str(k): _round_tree(v, digits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_tree(v, digits) for v in obj]
    return _round_value(obj, digits)


def _candle_dict(rate):
    return {
        "time": int(rate["time"]),
        "time_utc": datetime.fromtimestamp(int(rate["time"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "open": float(rate["open"]),
        "high": float(rate["high"]),
        "low": float(rate["low"]),
        "close": float(rate["close"]),
        "tick_volume": int(rate["tick_volume"]),
        "spread": int(rate["spread"]) if "spread" in rate.dtype.names else 0,
    }


def _fidelity_checks(candles, analysis):
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    add(
        "Candle fechado",
        len(candles) > 0,
        "A auditoria usa MT5 copy_rates_from_pos com posicao 1; o candle aberto fica fora.",
    )
    add(
        "Historico suficiente",
        len(candles) >= 120,
        "%d candles fechados carregados." % len(candles),
    )
    add(
        "Volume relativo",
        float(analysis.get("volume_ratio") or 0) > 0,
        "Volume do ultimo candle fechado contra a media anterior: %.2fx." % float(analysis.get("volume_ratio") or 0),
    )
    add(
        "Medias calculadas",
        all(float(analysis.get(k) or 0) > 0 for k in ("ema9", "ema20", "ema50")),
        "EMA 9, EMA 20 e EMA 50 disponiveis para comparacao visual.",
    )
    add(
        "Estruturas avancadas",
        bool(analysis.get("donchian_high_20")) and bool(analysis.get("anchored_vwap", {}).get("defined")),
        "Donchian, Darvas, Volume Profile e VWAP ancorada retornados quando ha dados suficientes.",
    )

    passed = sum(1 for item in checks if item["ok"])
    score = int(round((passed / max(len(checks), 1)) * 100))
    return checks, score


def audit_chart(symbol="XAUUSD", timeframe="M15", count=220, limit=12):
    """Retorna auditoria de fidelidade do scanner contra candles fechados do MT5."""
    symbol = str(symbol or "XAUUSD").strip().upper()
    timeframe = str(timeframe or "M15").strip().upper()
    count = max(80, min(int(count or 220), 1000))
    limit = max(3, min(int(limit or 12), 30))
    if timeframe not in TF_MAP:
        return {"ok": False, "error": "Timeframe nao suportado: %s" % timeframe}
    if not ensure_connection():
        return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}

    info = mt5.symbol_info(symbol)
    if info is None:
        return {"ok": False, "error": "Ativo nao encontrado no MT5: %s" % symbol}
    if not info.visible:
        mt5.symbol_select(symbol, True)

    tf_const = TF_MAP[timeframe]
    closed_rates = mt5.copy_rates_from_pos(symbol, tf_const, 1, count)
    forming_rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, 1)
    if closed_rates is None or len(closed_rates) < 20:
        return {"ok": False, "error": "Poucos candles fechados retornados pelo MT5 para %s %s." % (symbol, timeframe)}

    scanner = GoldenScanner()
    scanner._candle_cache = {}
    analysis = scanner._analyze_tf(symbol, timeframe, count)
    regime = scanner._detect_regime(symbol)
    full_scan = scanner.scan_symbol(symbol)

    tf_data_cache = {}
    setup_rows = []
    for setup_id, setup_def in SETUP_DEFINITIONS.items():
        if timeframe not in setup_def.get("timeframes", []):
            continue
        state = scanner._evaluate_setup(symbol, setup_id, setup_def, regime, tf_data_cache)
        state_dict = asdict(state)
        setup_rows.append(
            {
                "setup_id": setup_id,
                "name": state_dict.get("name"),
                "tier": state_dict.get("tier"),
                "mode": state_dict.get("mode"),
                "direction": state_dict.get("direction"),
                "status": state_dict.get("level_label"),
                "readiness": state_dict.get("readiness"),
                "score": state_dict.get("score"),
                "rr_ratio": state_dict.get("rr_ratio"),
                "conditions_met": state_dict.get("conditions_met", []),
                "conditions_missing": state_dict.get("conditions_missing", []),
                "details": state_dict.get("details"),
            }
        )
    setup_rows.sort(key=lambda item: (item.get("readiness") or 0, item.get("score") or 0), reverse=True)

    last_closed = _candle_dict(closed_rates[-1])
    previous_closed = _candle_dict(closed_rates[-2]) if len(closed_rates) > 1 else None
    forming = _candle_dict(forming_rates[-1]) if forming_rates is not None and len(forming_rates) else None
    tick = mt5.symbol_info_tick(symbol)
    checks, fidelity_score = _fidelity_checks(closed_rates, analysis)

    key_levels = {
        "ema9": analysis.get("ema9"),
        "ema20": analysis.get("ema20"),
        "ema50": analysis.get("ema50"),
        "vwap_20": analysis.get("vwap"),
        "vwap_upper": analysis.get("vwap_upper"),
        "vwap_lower": analysis.get("vwap_lower"),
        "donchian_high_20": analysis.get("donchian_high_20"),
        "donchian_low_20": analysis.get("donchian_low_20"),
        "donchian_high_55": analysis.get("donchian_high_55"),
        "donchian_low_55": analysis.get("donchian_low_55"),
        "anchored_vwap": analysis.get("anchored_vwap", {}).get("value"),
        "anchored_vwap_upper": analysis.get("anchored_vwap", {}).get("upper"),
        "anchored_vwap_lower": analysis.get("anchored_vwap", {}).get("lower"),
        "darvas_top": analysis.get("darvas_box", {}).get("top"),
        "darvas_bottom": analysis.get("darvas_box", {}).get("bottom"),
        "volume_profile_poc": analysis.get("volume_profile", {}).get("poc"),
        "volume_profile_vah": analysis.get("volume_profile", {}).get("vah"),
        "volume_profile_val": analysis.get("volume_profile", {}).get("val"),
    }

    return _round_tree(
        {
            "ok": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "MetaTrader 5",
            "closed_candle_position": 1,
            "count": int(len(closed_rates)),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_closed_candle": last_closed,
            "previous_closed_candle": previous_closed,
            "forming_candle_reference": forming,
            "tick": {
                "bid": float(tick.bid) if tick else 0,
                "ask": float(tick.ask) if tick else 0,
                "last": float(tick.last) if tick else 0,
            },
            "fidelity_score": fidelity_score,
            "checks": checks,
            "market": {
                "price_from_scanner": analysis.get("price"),
                "trend": analysis.get("trend"),
                "structure": analysis.get("structure"),
                "atr": analysis.get("atr"),
                "rsi": analysis.get("rsi"),
                "adx": analysis.get("adx"),
                "bb_width": analysis.get("bb_width"),
                "volume_ratio": analysis.get("volume_ratio"),
                "candle_pattern": analysis.get("candle"),
            },
            "key_levels": key_levels,
            "advanced": {
                "darvas_box": analysis.get("darvas_box", {}),
                "opening_range": analysis.get("opening_range", {}),
                "volume_profile": analysis.get("volume_profile", {}),
                "anchored_vwap": analysis.get("anchored_vwap", {}),
                "sr_zones": analysis.get("sr_zones", [])[:5],
                "swing_highs": analysis.get("swing_highs", [])[-3:],
                "swing_lows": analysis.get("swing_lows", [])[-3:],
            },
            "best_setup": asdict(full_scan.best_setup) if getattr(full_scan, "best_setup", None) else None,
            "setups": setup_rows[:limit],
        }
    )
