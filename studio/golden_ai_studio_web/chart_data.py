#!/usr/bin/env python3
"""Dados de grafico do MT5 para renderizacao no Golden AI Studio."""

from datetime import datetime, timezone

import MetaTrader5 as mt5

from golden_scanner import GoldenScanner
from mt5_connector import ensure_connection


TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def _ema_series(values, period):
    if not values:
        return []
    multiplier = 2.0 / (period + 1)
    result = [float(values[0])]
    for value in values[1:]:
        result.append((float(value) - result[-1]) * multiplier + result[-1])
    return result


def _round(value, digits=5):
    try:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        return round(float(value), digits)
    except Exception:
        return value


def get_chart_data(symbol="XAUUSD", timeframe="M15", count=180):
    symbol = str(symbol or "XAUUSD").strip().upper()
    timeframe = str(timeframe or "M15").strip().upper()
    count = max(60, min(int(count or 180), 500))
    if timeframe not in TF_MAP:
        return {"ok": False, "error": "Timeframe nao suportado: %s" % timeframe}
    if not ensure_connection():
        return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}

    info = mt5.symbol_info(symbol)
    if info is None:
        return {"ok": False, "error": "Ativo nao encontrado no MT5: %s" % symbol}
    if not info.visible:
        mt5.symbol_select(symbol, True)

    rates = mt5.copy_rates_from_pos(symbol, TF_MAP[timeframe], 1, count)
    forming = mt5.copy_rates_from_pos(symbol, TF_MAP[timeframe], 0, 1)
    if rates is None or len(rates) < 30:
        return {"ok": False, "error": "Poucos candles fechados retornados pelo MT5."}

    candles = []
    for rate in rates:
        ts = int(rate["time"])
        candles.append(
            {
                "time": ts,
                "label": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m %H:%M"),
                "open": _round(rate["open"]),
                "high": _round(rate["high"]),
                "low": _round(rate["low"]),
                "close": _round(rate["close"]),
                "volume": int(rate["tick_volume"]),
            }
        )

    closes = [c["close"] for c in candles]
    scanner = GoldenScanner()
    scanner._candle_cache = {}
    raw = [{"time": c["time"], "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"], "vol": c["volume"]} for c in candles]
    analysis = scanner._analyze_tf(symbol, timeframe, count)
    last = candles[-1]
    tick = mt5.symbol_info_tick(symbol)

    overlays = {
        "ema9": [_round(v) for v in _ema_series(closes, 9)],
        "ema21": [_round(v) for v in _ema_series(closes, 21)],
        "ema50": [_round(v) for v in _ema_series(closes, 50)],
        "vwap": _round(analysis.get("vwap")),
        "donchian_high_20": _round(analysis.get("donchian_high_20")),
        "donchian_low_20": _round(analysis.get("donchian_low_20")),
        "donchian_high_55": _round(analysis.get("donchian_high_55")),
        "donchian_low_55": _round(analysis.get("donchian_low_55")),
        "anchored_vwap": _round(analysis.get("anchored_vwap", {}).get("value", 0)),
        "anchored_vwap_upper": _round(analysis.get("anchored_vwap", {}).get("upper", 0)),
        "anchored_vwap_lower": _round(analysis.get("anchored_vwap", {}).get("lower", 0)),
        "opening_range_high": _round(analysis.get("opening_range", {}).get("high", 0)),
        "opening_range_low": _round(analysis.get("opening_range", {}).get("low", 0)),
        "darvas_top": _round(analysis.get("darvas_box", {}).get("top", 0)),
        "darvas_bottom": _round(analysis.get("darvas_box", {}).get("bottom", 0)),
        "volume_profile_poc": _round(analysis.get("volume_profile", {}).get("poc", 0)),
        "volume_profile_vah": _round(analysis.get("volume_profile", {}).get("vah", 0)),
        "volume_profile_val": _round(analysis.get("volume_profile", {}).get("val", 0)),
    }
    signals = []
    scan = scanner.scan_symbol(symbol)
    if scan.best_setup and getattr(scan.best_setup, "readiness", 0) > 0:
        signals.append(
            {
                "index": len(candles) - 1,
                "price": last["close"],
                "name": scan.best_setup.name,
                "direction": scan.best_setup.direction,
                "status": scan.best_setup.level_label,
                "score": scan.best_setup.score,
            }
        )

    forming_ref = None
    if forming is not None and len(forming):
        rate = forming[-1]
        forming_ref = {
            "time": int(rate["time"]),
            "label": datetime.fromtimestamp(int(rate["time"]), tz=timezone.utc).strftime("%d/%m %H:%M"),
            "open": _round(rate["open"]),
            "high": _round(rate["high"]),
            "low": _round(rate["low"]),
            "close": _round(rate["close"]),
        }

    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "source": "MetaTrader 5",
        "closed_candle_position": 1,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candles": candles,
        "overlays": overlays,
        "signals": signals,
        "forming_candle_reference": forming_ref,
        "summary": {
            "last_close": last["close"],
            "trend": analysis.get("trend"),
            "rsi": _round(analysis.get("rsi"), 2),
            "adx": _round(analysis.get("adx"), 2),
            "atr": _round(analysis.get("atr")),
            "volume_ratio": _round(analysis.get("volume_ratio"), 2),
            "bid": _round(tick.bid) if tick else 0,
            "ask": _round(tick.ask) if tick else 0,
        },
    }
