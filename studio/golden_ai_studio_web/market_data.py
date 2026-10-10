"""Normalized market snapshot for the Golden AI macro dashboard."""
from __future__ import annotations

import json
import csv
import io
import os
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

ASSETS = [
    ("Moedas", "DXY", "Indice dolar", ["DXY", "USDX"]),
    ("Moedas", "EUR/USD", "Euro / Dolar", ["EURUSD"]),
    ("Moedas", "GBP/USD", "Libra / Dolar", ["GBPUSD"]),
    ("Moedas", "USD/JPY", "Dolar / Iene", ["USDJPY"]),
    ("Emergentes", "USD/MXN", "Dolar / Peso mexicano", ["USDMXN"]),
    ("Emergentes", "USD/ZAR", "Dolar / Rand", ["USDZAR"]),
    ("Emergentes", "USD/BRL", "Dolar / Real", ["USDBRL", "USDBRL.r"]),
    ("Indices", "S&P 500", "Estados Unidos", ["US500", "SP500", "SPX500"]),
    ("Indices", "Nasdaq 100", "Tecnologia EUA", ["US100", "NAS100", "USTEC"]),
    ("Indices", "Dow Jones", "Industriais EUA", ["US30", "DJ30"]),
    ("Metais", "Ouro", "XAU/USD", ["XAUUSD", "GOLD"]),
    ("Metais", "Prata", "XAG/USD", ["XAGUSD", "SILVER"]),
    ("Energia", "Petroleo WTI", "WTI", ["USOIL", "WTI", "XTIUSD"]),
    ("Energia", "Petroleo Brent", "Brent", ["UKOIL", "BRENT", "XBRUSD"]),
    ("Brasil", "Ibovespa", "Indice B3", ["IBOV", "IBOVESPA"]),
    ("Brasil", "Dolar futuro", "Contrato continuo", ["WDO$N", "WDO", "DOL$N", "DOL"]),
]

_NEWS_CACHE = {"expires": 0, "items": [], "source": ""}
_PAIR_NEWS_CACHE = {}
_MACRO_CACHE = {"expires": 0, "data": None}
_STRENGTH_CACHE = {"expires": 0, "data": None}
_CALENDAR_CACHE = {"expires": 0, "items": [], "state": "configure"}
_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "BRL", "MXN", "ZAR", "CNH", "CNY", "SGD", "HKD", "NOK", "SEK", "DKK", "PLN", "HUF", "CZK", "TRY", "ILS", "INR", "THB", "GHS", "NGN", "KES", "TZS"}


def _mt5_enabled(override=None):
    if override is not None:
        return bool(override)
    try:
        from jarvis_core.runtime_profile import active_runtime_profile
        return bool(active_runtime_profile().mt5_enabled)
    except Exception:
        return True

def _forex_symbols(mt5):
    result = []
    for info in mt5.symbols_get() or []:
        clean = re.sub(r"[^A-Z]", "", info.name.upper())
        if len(clean) != 6 or clean[:3] not in _CURRENCIES or clean[3:] not in _CURRENCIES:
            continue
        daily_change = None
        try:
            mt5.symbol_select(info.name, True)
            rates = mt5.copy_rates_from_pos(info.name, mt5.TIMEFRAME_D1, 0, 2)
            if rates is not None and len(rates) >= 2 and float(rates[-2]["close"]):
                daily_change = round((float(rates[-1]["close"]) / float(rates[-2]["close"]) - 1) * 100, 4)
        except Exception:
            pass
        result.append({"symbol": info.name, "base": clean[:3], "quote": clean[3:],
                       "daily_change": daily_change,
                       "category": "Majors" if "Majors" in info.path or clean in {"EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD"} else "Cruzadas" if not clean.startswith("USD") and not clean.endswith("USD") else "Exoticas"})
    return sorted(result, key=lambda row: (row["category"], row["symbol"]))

def _currency_strength(mt5, pairs):
    now = datetime.now(timezone.utc).timestamp()
    if _STRENGTH_CACHE["data"] and now < _STRENGTH_CACHE["expires"]:
        return _STRENGTH_CACHE["data"]
    totals = {code: [] for code in _CURRENCIES}
    for pair in pairs:
        rates = mt5.copy_rates_from_pos(pair["symbol"], mt5.TIMEFRAME_D1, 0, 2)
        if rates is None or len(rates) < 2 or not rates[-2]["close"]:
            continue
        change = (float(rates[-1]["close"]) / float(rates[-2]["close"]) - 1) * 100
        totals[pair["base"]].append(change)
        totals[pair["quote"]].append(-change)
    raw = {code: sum(values) / len(values) for code, values in totals.items() if values}
    maximum = max((abs(value) for value in raw.values()), default=1) or 1
    result = {code: round(value / maximum * 100, 1) for code, value in raw.items()}
    _STRENGTH_CACHE.update({"expires": now + 900, "data": result})
    return result

def get_forex_analysis(symbol=None, mt5_enabled=None):
    try:
        if not _mt5_enabled(mt5_enabled):
            return {"ok": False, "error": "SOURCE_DISABLED: MT5_DISABLED_BY_PROFILE", "pairs": []}
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return {"ok": False, "error": "MetaTrader 5 desconectado", "pairs": []}
        pairs = _forex_symbols(mt5)
        if not symbol:
            return {"ok": True, "pairs": pairs, "count": len(pairs), "source": "MetaTrader 5"}
        if symbol not in {row["symbol"] for row in pairs}:
            return {"ok": False, "error": "Paridade nao encontrada", "pairs": pairs}
        mt5.symbol_select(symbol, True)
        info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
        frames = (("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1), ("H4", mt5.TIMEFRAME_H4), ("D1", mt5.TIMEFRAME_D1))
        trends, main_rates = [], None
        for label, timeframe in frames:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 120)
            if rates is None or len(rates) < 30:
                trends.append({"timeframe": label, "trend": "Sem dados", "change": 0})
                continue
            closes = [float(row["close"]) for row in rates]
            fast, slow = sum(closes[-20:]) / 20, sum(closes[-50:]) / 50
            trends.append({"timeframe": label, "trend": "Alta" if fast > slow else "Baixa",
                           "change": round((closes[-1] / closes[-2] - 1) * 100, 4),
                           "fast": round(fast, info.digits), "slow": round(slow, info.digits)})
            if label == "M15": main_rates = rates
        daily = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 16)
        if daily is None or len(daily) < 2 or main_rates is None:
            return {"ok": False, "error": "Historico insuficiente", "pairs": pairs}
        day, previous = daily[-1], daily[-2]
        price = float(tick.bid) if tick and tick.bid else float(main_rates[-1]["close"])
        high, low = float(day["high"]), float(day["low"])
        ranges = [float(row["high"] - row["low"]) for row in daily[-15:-1]]
        aligned = [item for item in trends if item["trend"] in ("Alta", "Baixa")]
        bulls = sum(item["trend"] == "Alta" for item in aligned)
        direction = "Alta" if bulls >= 3 else "Baixa" if bulls <= 1 else "Misto"
        clean = re.sub(r"[^A-Z]", "", symbol.upper())
        base, quote = clean[:3], clean[3:]
        strength = _currency_strength(mt5, pairs)
        base_strength, quote_strength = strength.get(base, 0), strength.get(quote, 0)
        advantage = round(base_strength - quote_strength, 1)
        macro = _macro_snapshot([])
        macro_map = {
            "USD": [item for item in macro["indicators"] if item["group"] in ("Juros longos", "Inflacao", "Juros EUA", "Dolar")],
            "BRL": [item for item in macro["indicators"] if item["group"] == "Brasil"],
        }
        policy_rates = {}
        for item in macro["indicators"]:
            if item["id"] == "DFEDTARU":
                policy_rates["USD"] = item
            elif item["id"] == "BCB432":
                policy_rates["BRL"] = item
        calendar, calendar_state = _economic_calendar()
        pair_events = [event for event in calendar if str(event.get("currency") or "").upper() in (base, quote)][:12]
        base_rate, quote_rate = policy_rates.get(base), policy_rates.get(quote)
        rate_differential = round(base_rate["value"] - quote_rate["value"], 3) if base_rate and quote_rate else None
        pair_news, pair_news_source = _pair_news(base, quote)
        spread_quality = 20 if (tick and info.point and (tick.ask-tick.bid)/info.point <= 20) else 10
        alignment_quality = int(bulls / len(aligned) * 30) if direction == "Alta" and aligned else int((len(aligned)-bulls) / len(aligned) * 30) if aligned else 0
        quality = min(100, 30 + alignment_quality + spread_quality + (20 if 15 <= ((price-low)/(high-low)*100 if high != low else 50) <= 85 else 10))
        return {"ok": True, "pairs": pairs, "analysis": {"symbol": symbol, "price": round(price, info.digits),
                "bid": round(float(tick.bid), info.digits) if tick else None, "ask": round(float(tick.ask), info.digits) if tick else None,
                "spread_points": round((tick.ask-tick.bid)/info.point, 1) if tick and info.point else None,
                "change_day": round((price/float(previous["close"])-1)*100, 3), "open": round(float(day["open"]), info.digits),
                "high": round(high, info.digits), "low": round(low, info.digits), "previous_close": round(float(previous["close"]), info.digits),
                "position": round((price-low)/(high-low)*100, 1) if high != low else 50, "average_range": round(sum(ranges)/len(ranges), info.digits),
                "direction": direction, "trends": trends, "series": [round(float(row["close"]), info.digits) for row in main_rates[-80:]],
                "candles": [{"time": int(row["time"]), "open": round(float(row["open"]), info.digits),
                             "high": round(float(row["high"]), info.digits), "low": round(float(row["low"]), info.digits),
                             "close": round(float(row["close"]), info.digits)} for row in main_rates[-80:]],
                "base": base, "quote": quote, "base_strength": base_strength, "quote_strength": quote_strength,
                "advantage": advantage, "stronger": base if advantage > 5 else quote if advantage < -5 else "Equilibrado",
                "strength_ranking": [{"currency": code, "score": value} for code, value in sorted(strength.items(), key=lambda x: x[1], reverse=True)],
                "base_macro": macro_map.get(base, []), "quote_macro": macro_map.get(quote, []), "quality": quality,
                "base_rate": base_rate, "quote_rate": quote_rate, "rate_differential": rate_differential,
                "events": pair_events, "calendar_state": calendar_state,
                "pair_news": pair_news, "pair_news_source": pair_news_source,
                "quality_label": "Alta" if quality >= 75 else "Media" if quality >= 55 else "Baixa",
                "updated_at": datetime.now(timezone.utc).isoformat(), "source": "MetaTrader 5"}}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "pairs": []}

def get_market_chart(symbol="XAUUSD", timeframe="M15", mt5_enabled=None):
    try:
        if not _mt5_enabled(mt5_enabled):
            return {"ok": False, "error": "SOURCE_DISABLED: MT5_DISABLED_BY_PROFILE",
                    "symbol": symbol, "timeframe": timeframe}
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return {"ok": False, "error": "MetaTrader 5 desconectado"}
        frames = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
                  "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1}
        timeframe = str(timeframe or "M15").upper()
        if timeframe not in frames:
            return {"ok": False, "error": "Timeframe invalido"}
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        rates = mt5.copy_rates_from_pos(symbol, frames[timeframe], 0, 260)
        if info is None or rates is None or len(rates) < 20:
            return {"ok": False, "error": "Historico insuficiente"}
        digits = info.digits
        candles = [{"time": int(row["time"]), "open": round(float(row["open"]), digits),
                    "high": round(float(row["high"]), digits), "low": round(float(row["low"]), digits),
                    "close": round(float(row["close"]), digits), "volume": int(row["tick_volume"])}
                   for row in rates[-100:]]
        first, last = candles[0]["open"], candles[-1]["close"]
        # Consolida pivôs em zonas e mantém níveis realmente separados dos dois lados do preço.
        analysis_candles = [{"high": float(row["high"]), "low": float(row["low"]),
                             "close": float(row["close"])} for row in rates[-240:]]
        true_ranges = [max(c["high"] - c["low"], abs(c["high"] - analysis_candles[i-1]["close"]),
                           abs(c["low"] - analysis_candles[i-1]["close"]))
                       for i, c in enumerate(analysis_candles[1:], 1)]
        atr = sum(true_ranges[-14:]) / min(14, len(true_ranges))
        tolerance = max(atr * 0.22, info.point * 30)
        min_spacing = max(atr * 0.70, tolerance * 2.5)
        pivots = []
        pivot_window = 3
        for index in range(pivot_window, len(analysis_candles) - pivot_window):
            row = analysis_candles[index]
            window = analysis_candles[index-pivot_window:index+pivot_window+1]
            if row["high"] == max(c["high"] for c in window):
                pivots.append((row["high"], index))
            if row["low"] == min(c["low"] for c in window):
                pivots.append((row["low"], index))
        clusters = []
        for price_level, pivot_index in pivots:
            cluster = next((c for c in clusters if abs(c["price"] - price_level) <= tolerance), None)
            if cluster:
                cluster["price"] = (cluster["price"] * cluster["touches"] + price_level) / (cluster["touches"] + 1)
                cluster["touches"] += 1
                cluster["last_index"] = max(cluster["last_index"], pivot_index)
            else:
                clusters.append({"price": price_level, "touches": 1, "last_index": pivot_index})
        for cluster in clusters:
            cluster["kind"] = "support" if cluster["price"] < last else "resistance"
            cluster["distance"] = abs(cluster["price"] - last)
            cluster["score"] = cluster["touches"] * 10 + cluster["last_index"] / len(analysis_candles) * 3
        def select_levels(kind):
            candidates = [c for c in clusters if c["kind"] == kind and c["distance"] >= tolerance * 1.25]
            candidates.sort(key=lambda c: (-c["score"], c["distance"]))
            selected = []
            for candidate in candidates:
                if all(abs(candidate["price"] - item["price"]) >= min_spacing for item in selected):
                    selected.append(candidate)
                if len(selected) == 3:
                    break
            return selected
        relevant = select_levels("support") + select_levels("resistance")
        for cluster in relevant:
            segment = analysis_candles[cluster["last_index"]:cluster["last_index"] + 9]
            if cluster["kind"] == "support":
                reaction = max((item["high"] - cluster["price"] for item in segment), default=0)
                false_breaks = sum(item["low"] < cluster["price"] - tolerance * 0.2 and item["close"] > cluster["price"] for item in analysis_candles)
            else:
                reaction = max((cluster["price"] - item["low"] for item in segment), default=0)
                false_breaks = sum(item["high"] > cluster["price"] + tolerance * 0.2 and item["close"] < cluster["price"] for item in analysis_candles)
            cluster["age_bars"] = len(analysis_candles) - 1 - cluster["last_index"]
            cluster["distance_points"] = cluster["distance"] / info.point if info.point else 0
            cluster["reaction_atr"] = reaction / atr if atr else 0
            cluster["false_breaks"] = false_breaks
            cluster["quality"] = min(100, round(cluster["touches"] * 14 + min(3, cluster["reaction_atr"]) * 12 + max(0, 20 - cluster["age_bars"] / 8)))
        relevant.sort(key=lambda c: c["price"], reverse=True)
        closes = [c["close"] for c in candles]
        structure_events = []
        swing_high = swing_low = None
        structure_direction = 0
        for index in range(2, len(candles) - 1):
            previous = candles[index - 1]
            neighborhood = candles[max(0, index-3):index+2]
            if previous["high"] >= max(item["high"] for item in neighborhood):
                swing_high = previous["high"]
            if previous["low"] <= min(item["low"] for item in neighborhood):
                swing_low = previous["low"]
            close = candles[index]["close"]
            if swing_high is not None and close > swing_high and candles[index-1]["close"] <= swing_high:
                structure_events.append({"time": candles[index]["time"], "price": swing_high,
                                         "type": "BOS" if structure_direction >= 0 else "CHoCH", "direction": "bullish"})
                structure_direction = 1
                swing_high = None
            elif swing_low is not None and close < swing_low and candles[index-1]["close"] >= swing_low:
                structure_events.append({"time": candles[index]["time"], "price": swing_low,
                                         "type": "BOS" if structure_direction <= 0 else "CHoCH", "direction": "bearish"})
                structure_direction = -1
                swing_low = None
        gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))][-14:]
        losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))][-14:]
        avg_gain, avg_loss = sum(gains) / 14, sum(losses) / 14
        rsi = 100 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        return {"ok": True, "symbol": symbol, "timeframe": timeframe, "candles": candles,
                "price": last, "change": round((last / first - 1) * 100, 3) if first else 0,
                "rsi": round(rsi, 1), "atr": round(atr, digits), "levels": [{"price": round(c["price"], digits), "kind": c["kind"],
                "touches": c["touches"], "relevance": "alta" if c["quality"] >= 65 else "media",
                "quality": c["quality"], "distance_points": round(c["distance_points"], 1),
                "age_bars": c["age_bars"], "reaction_atr": round(c["reaction_atr"], 2),
                "false_breaks": c["false_breaks"]} for c in relevant],
                "structure_events": structure_events[-8:],
                "source": "MetaTrader 5", "updated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def get_market_tick(symbol="XAUUSD", mt5_enabled=None):
    """Retorna o tick bruto do MT5 sem depender do cache dos candles."""
    try:
        if not _mt5_enabled(mt5_enabled):
            return {"ok": False, "error": "SOURCE_DISABLED: MT5_DISABLED_BY_PROFILE",
                    "symbol": symbol}
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return {"ok": False, "error": "MetaTrader 5 desconectado"}
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return {"ok": False, "error": "Tick indisponivel"}
        price = float(tick.bid or tick.last or tick.ask)
        return {"ok": True, "symbol": symbol, "bid": round(float(tick.bid), info.digits),
                "ask": round(float(tick.ask), info.digits), "price": round(price, info.digits),
                "spread": round((float(tick.ask) - float(tick.bid)) / info.point, 1) if info.point else 0,
                "time": int(tick.time), "time_msc": int(tick.time_msc), "source": "MetaTrader 5"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

def get_market_ai_context(symbol="XAUUSD", mt5_enabled=None):
    """Contexto verificável e multitemporal usado exclusivamente pela análise IA."""
    symbol = str(symbol or "XAUUSD")
    mt5_allowed = _mt5_enabled(mt5_enabled)
    if not mt5_allowed:
        return {
            "ok": False,
            "status": "SOURCE_DISABLED",
            "availability": "SOURCE_DISABLED",
            "reason": "MT5_DISABLED_BY_PROFILE",
            "symbol": symbol,
            "multitimeframe": {},
            "fundamentals": {
                "status": "SOURCE_DISABLED",
                "availability": "SOURCE_DISABLED",
                "reason": "MT5_DISABLED_BY_PROFILE",
                "events": [],
                "pair_news": [],
                "strength_ranking": "UNAVAILABLE",
            },
            "errors": ["MT5_DISABLED_BY_PROFILE"],
            "source": "MT5",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    timeframes = {}
    errors = []
    for timeframe in ("M5", "M15", "H1", "H4", "D1"):
        chart = get_market_chart(symbol, timeframe, mt5_enabled=mt5_allowed)
        if not chart.get("ok"):
            errors.append(f"{timeframe}: {chart.get('error', 'sem dados')}")
            continue
        candles = chart.get("candles", [])
        closes = [float(item["close"]) for item in candles]
        fast = sum(closes[-20:]) / min(20, len(closes))
        slow = sum(closes[-50:]) / min(50, len(closes))
        last = closes[-1]
        recent = candles[-20:]
        recent_high = max(float(item["high"]) for item in recent)
        recent_low = min(float(item["low"]) for item in recent)
        trend = "alta" if fast > slow and last >= fast else "baixa" if fast < slow and last <= fast else "lateral"
        structure = "topo do range" if last >= recent_low + (recent_high-recent_low)*0.7 else "fundo do range" if last <= recent_low + (recent_high-recent_low)*0.3 else "meio do range"
        timeframes[timeframe] = {
            "price": last, "trend": trend, "structure": structure,
            "change_pct": chart.get("change"), "rsi": chart.get("rsi"), "atr": chart.get("atr"),
            "sma20": round(fast, 8), "sma50": round(slow, 8),
            "recent_high": recent_high, "recent_low": recent_low,
            "levels": chart.get("levels", []), "updated_at": chart.get("updated_at")
        }
    clean = re.sub(r"[^A-Z]", "", symbol.upper())
    is_forex = len(clean) == 6 and clean[:3] in _CURRENCIES and clean[3:] in _CURRENCIES
    fundamentals = (get_forex_analysis(symbol, mt5_enabled=mt5_allowed).get("analysis")
                    if is_forex else None)
    if fundamentals:
        fundamentals = {key: fundamentals.get(key) for key in (
            "symbol", "base", "quote", "base_strength", "quote_strength", "advantage", "stronger",
            "direction", "trends", "spread_points", "change_day", "average_range", "position",
            "base_macro", "quote_macro", "base_rate", "quote_rate", "rate_differential",
            "events", "pair_news", "quality", "quality_label", "calendar_state", "updated_at", "source"
        )}
    else:
        macro = _macro_snapshot([])
        calendar, calendar_state = _economic_calendar()
        currencies = {"USD"} if clean.startswith(("XAU", "XAG")) else set()
        fundamentals = {
            "asset": symbol, "macro_reading": macro.get("reading"),
            "indicators": macro.get("indicators", []), "drivers": macro.get("drivers", []),
            "events": [item for item in calendar if str(item.get("currency", "")).upper() in currencies][:12],
            "calendar_state": calendar_state, "source": "FRED/BCB/Trading Economics configurado"
        }
    available = list(timeframes.values())
    bullish = sum(item["trend"] == "alta" for item in available)
    bearish = sum(item["trend"] == "baixa" for item in available)
    alignment = "alta alinhada" if bullish >= 4 else "baixa alinhada" if bearish >= 4 else "misto"
    return {"ok": bool(timeframes), "symbol": symbol, "multitimeframe": timeframes,
            "alignment": alignment, "bullish_timeframes": bullish, "bearish_timeframes": bearish,
            "fundamentals": fundamentals, "errors": errors,
            "updated_at": datetime.now(timezone.utc).isoformat(), "source": "MetaTrader 5 e fontes macro configuradas"}

FRED_SERIES = [
    ("DGS10", "Treasury 10 anos", "% a.a.", "Juros longos", "lower"),
    ("T10YIE", "Inflacao implicita 10 anos", "% a.a.", "Inflacao", "higher"),
    ("DFEDTARU", "Limite superior Fed Funds", "% a.a.", "Juros EUA", "lower"),
    ("DTWEXBGS", "Indice amplo do dolar", "indice", "Dolar", "lower"),
]

def _latest_fred(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    request = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))
    valid = [(row.get("observation_date"), row.get(series_id)) for row in rows if row.get(series_id) not in (None, ".", "")]
    if not valid:
        return None
    date, value = valid[-1]
    previous = float(valid[-2][1]) if len(valid) > 1 else float(value)
    return {"value": round(float(value), 3), "previous": round(previous, 3), "date": date}

def _latest_bcb(series_id):
    today = datetime.now().strftime("%d/%m/%Y")
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados/ultimos/12?formato=json"
    request = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        rows = json.load(response)
    eligible = [row for row in rows if datetime.strptime(row["data"], "%d/%m/%Y").date() <= datetime.now().date()]
    rows = eligible or rows
    if not rows:
        return None
    current, previous = rows[-1], rows[-2] if len(rows) > 1 else rows[-1]
    return {"value": round(float(current["valor"].replace(",", ".")), 3),
            "previous": round(float(previous["valor"].replace(",", ".")), 3), "date": current["data"]}

def _macro_snapshot(assets):
    now = datetime.now(timezone.utc).timestamp()
    if _MACRO_CACHE["data"] and now < _MACRO_CACHE["expires"]:
        return _MACRO_CACHE["data"]
    indicators, errors = [], []
    for series_id, name, unit, group, gold_bias in FRED_SERIES:
        try:
            item = _latest_fred(series_id)
            if item:
                item.update({"id": series_id, "name": name, "unit": unit, "group": group,
                             "gold_bias": gold_bias, "source": "FRED"})
                indicators.append(item)
        except Exception as exc:
            errors.append(f"FRED {series_id}: {exc}")
    for series_id, name, unit, group in (("432", "Selic meta", "% a.a.", "Brasil"), ("433", "IPCA mensal", "% a.m.", "Brasil")):
        try:
            item = _latest_bcb(series_id)
            if item:
                item.update({"id": f"BCB{series_id}", "name": name, "unit": unit, "group": group,
                             "gold_bias": "neutral", "source": "Banco Central do Brasil"})
                indicators.append(item)
        except Exception as exc:
            errors.append(f"BCB {series_id}: {exc}")
    asset_map = {row["symbol"]: row for row in assets}
    drivers = []
    for symbol, label, favorable_when in (("DXY", "Dolar", "down"), ("S&P 500", "Apetite a risco", "down"), ("Ouro", "Momentum do ouro", "up")):
        row = asset_map.get(symbol)
        if row:
            favorable = None if row["change"] == 0 else (row["change"] < 0 if favorable_when == "down" else row["change"] > 0)
            drivers.append({"name": label, "value": row["change"], "unit": "%", "favorable": favorable,
                            "detail": f"{symbol} varia {row['change']:+.3f}%", "source": row["source"]})
    for item in indicators:
        if item["gold_bias"] == "neutral":
            continue
        delta = item["value"] - item["previous"]
        favorable = None if delta == 0 else (delta > 0 if item["gold_bias"] == "higher" else delta < 0)
        drivers.append({"name": item["name"], "value": delta, "unit": item["unit"], "favorable": favorable,
                        "detail": f"{item['previous']} para {item['value']}", "source": item["source"]})
    score = sum(1 if d["favorable"] is True else -1 if d["favorable"] is False else 0 for d in drivers)
    result = {"indicators": indicators, "drivers": drivers, "score": score,
              "reading": "Favoravel ao ouro" if score >= 2 else "Contrario ao ouro" if score <= -2 else "Misto",
              "errors": errors, "updated_at": datetime.now(timezone.utc).isoformat()}
    _MACRO_CACHE.update({"expires": now + 900, "data": result})
    return result

def _mt5_snapshot(mt5_enabled=None):
    if not _mt5_enabled(mt5_enabled):
        return [], "SOURCE_DISABLED: MT5_DISABLED_BY_PROFILE"
    try:
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return [], "MT5 desconectado"
        rows = []
        for group, symbol, name, aliases in ASSETS:
            selected = next((alias for alias in aliases if mt5.symbol_info(alias) is not None), None)
            if not selected:
                continue
            mt5.symbol_select(selected, True)
            rates = mt5.copy_rates_from_pos(selected, mt5.TIMEFRAME_M5, 0, 32)
            series = [round(float(row["close"]), 6) for row in rates][-32:] if rates is not None else []
            tick = mt5.symbol_info_tick(selected)
            price = float(tick.bid) if tick and tick.bid else (series[-1] if series else 0.0)
            previous = series[0] if series else price
            rows.append({"group": group, "symbol": symbol, "provider_symbol": selected, "name": name,
                         "price": price, "change": round(((price / previous) - 1) * 100, 3) if previous else 0,
                         "series": series, "source": "MT5", "status": "live"})
        return rows, None
    except Exception as exc:
        return [], str(exc)

def _gold_levels(mt5_enabled=None):
    """Classic daily pivot levels calculated from the previous closed XAUUSD candle."""
    if not _mt5_enabled(mt5_enabled):
        return None
    try:
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return None
        symbol = next((name for name in ("XAUUSD", "GOLD") if mt5.symbol_info(name) is not None), None)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 1, 1) if symbol else None
        if rates is None or len(rates) == 0:
            return None
        high, low, close = (float(rates[0][key]) for key in ("high", "low", "close"))
        pivot = (high + low + close) / 3
        spread = high - low
        values = {
            "R4": pivot + 3 * spread, "R3": high + 2 * (pivot - low),
            "R2": pivot + spread, "R1": 2 * pivot - low, "PIVO": pivot,
            "S1": 2 * pivot - high, "S2": pivot - spread,
            "S3": low - 2 * (high - pivot), "S4": pivot - 3 * spread,
        }
        return {"symbol": symbol, "method": "Pivos classicos do candle D1 anterior",
                "reference_date": datetime.fromtimestamp(int(rates[0]["time"]), timezone.utc).date().isoformat(),
                "previous": {"high": high, "low": low, "close": close},
                "levels": [{"label": key, "price": round(value, 3),
                            "kind": "reference" if key == "PIVO" else "resistance" if key.startswith("R") else "support"}
                           for key, value in values.items()]}
    except Exception:
        return None

def _gold_snapshot(mt5_enabled=None):
    """Current XAUUSD context calculated only from broker data."""
    if not _mt5_enabled(mt5_enabled):
        return None
    try:
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection
        if not ensure_connection():
            return None
        symbol = next((name for name in ("XAUUSD", "GOLD") if mt5.symbol_info(name) is not None), None)
        if not symbol:
            return None
        mt5.symbol_select(symbol, True)
        daily = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 22)
        intraday = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 80)
        tick = mt5.symbol_info_tick(symbol)
        if daily is None or len(daily) < 2 or intraday is None or len(intraday) < 20:
            return None
        price = float(tick.bid) if tick and tick.bid else float(intraday[-1]["close"])
        day = daily[-1]
        previous = daily[-2]
        day_open, day_high, day_low = (float(day[key]) for key in ("open", "high", "low"))
        previous_close = float(previous["close"])
        closes = [float(row["close"]) for row in intraday]
        ranges = [float(row["high"] - row["low"]) for row in daily[-15:-1]]
        ema_fast = sum(closes[-20:]) / 20
        ema_slow = sum(closes[-50:]) / 50
        day_range = day_high - day_low
        position = ((price - day_low) / day_range * 100) if day_range else 50
        return {
            "symbol": symbol,
            "price": round(price, 3),
            "change": round(((price / previous_close) - 1) * 100, 3) if previous_close else 0,
            "change_value": round(price - previous_close, 3),
            "day_open": round(day_open, 3),
            "day_high": round(day_high, 3),
            "day_low": round(day_low, 3),
            "previous_close": round(previous_close, 3),
            "day_position": round(max(0, min(position, 100)), 1),
            "average_daily_range": round(sum(ranges) / len(ranges), 3) if ranges else 0,
            "trend": "Alta" if ema_fast > ema_slow else "Baixa",
            "trend_detail": "Media M15 curta acima da longa" if ema_fast > ema_slow else "Media M15 curta abaixo da longa",
            "series": [round(value, 3) for value in closes[-60:]],
            "candles": [{"time": int(row["time"]), "open": round(float(row["open"]), 3),
                         "high": round(float(row["high"]), 3), "low": round(float(row["low"]), 3),
                         "close": round(float(row["close"]), 3)} for row in intraday[-60:]],
            "source": "MetaTrader 5",
            "status": "live",
        }
    except Exception:
        return None

def _market_news():
    now = datetime.now(timezone.utc).timestamp()
    if _NEWS_CACHE["items"] and now < _NEWS_CACHE["expires"]:
        return _NEWS_CACHE["items"], _NEWS_CACHE["source"]
    query = urllib.parse.quote('ouro OR XAUUSD OR dolar OR "Federal Reserve" OR juros economia')
    url = f"https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    items = []
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            root = ET.fromstring(response.read())
        for node in root.findall("./channel/item")[:24]:
            title, link = (node.findtext("title") or "").strip(), (node.findtext("link") or "").strip()
            source_node = node.find("source")
            source = (source_node.text or "Google Noticias").strip() if source_node is not None else "Google Noticias"
            if not title or not link:
                continue
            try:
                published = parsedate_to_datetime(node.findtext("pubDate") or "").astimezone(timezone.utc).isoformat()
            except Exception:
                published = None
            items.append({"title": title, "url": link, "source": source, "published_at": published,
                          "topic": "Ouro" if any(x in title.lower() for x in ("ouro", "gold", "xau")) else "Macro"})
        _NEWS_CACHE.update({"expires": now + 60, "items": items, "source": "Google Noticias RSS"})
    except Exception:
        pass
    return _NEWS_CACHE["items"], _NEWS_CACHE["source"]


def _pair_news(base, quote):
    key = f"{base}{quote}"
    now = datetime.now(timezone.utc).timestamp()
    cached = _PAIR_NEWS_CACHE.get(key)
    if cached and now < cached["expires"]:
        return cached["items"], cached["source"]
    query = urllib.parse.quote(f'"{base}/{quote}" OR {key} OR "{base} {quote}" forex')
    url = f"https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    items = []
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            root = ET.fromstring(response.read())
        for node in root.findall("./channel/item")[:8]:
            title, link = (node.findtext("title") or "").strip(), (node.findtext("link") or "").strip()
            source_node = node.find("source")
            source = (source_node.text or "Google Noticias").strip() if source_node is not None else "Google Noticias"
            if not title or not link:
                continue
            try:
                published = parsedate_to_datetime(node.findtext("pubDate") or "").astimezone(timezone.utc).isoformat()
            except Exception:
                published = None
            items.append({"title": title, "url": link, "source": source, "published_at": published})
    except Exception:
        pass
    _PAIR_NEWS_CACHE[key] = {"expires": now + 120, "items": items, "source": "Google Noticias RSS" if items else "indisponivel"}
    return items, _PAIR_NEWS_CACHE[key]["source"]

def _economic_calendar():
    now = datetime.now(timezone.utc).timestamp()
    if now < _CALENDAR_CACHE["expires"]:
        return _CALENDAR_CACHE["items"], _CALENDAR_CACHE["state"]
    key = os.getenv("TRADING_ECONOMICS_KEY", "").strip()
    if not key:
        return [], "configure"
    try:
        url = "https://api.tradingeconomics.com/calendar?" + urllib.parse.urlencode({"c": key, "importance": 2, "lang": "pt", "values": "true", "f": "json"})
        request = urllib.request.Request(url, headers={"User-Agent": "GoldenAI/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            rows = json.load(response)
        events = [{"date": row.get("Date"), "country": row.get("Country"), "event": row.get("Event"),
                   "importance": row.get("Importance", 1), "actual": row.get("Actual"), "previous": row.get("Previous"),
                   "forecast": row.get("Forecast") or row.get("TEForecast"), "currency": row.get("Currency"),
                   "source": row.get("Source")} for row in rows[:80]]
        _CALENDAR_CACHE.update({"expires": now + 60, "items": events, "state": "online"})
        return events, "online"
    except Exception as exc:
        return [], f"erro: {exc}"

def get_market_overview(mt5_enabled=None):
    mt5_rows, mt5_error = _mt5_snapshot(mt5_enabled=mt5_enabled)
    te_ready = bool(os.getenv("TRADING_ECONOMICS_KEY"))
    td_ready = bool(os.getenv("TWELVE_DATA_API_KEY"))
    news, news_source = _market_news()
    assets = mt5_rows
    calendar, calendar_state = _economic_calendar()
    return {"ok": bool(assets), "updated_at": datetime.now(timezone.utc).isoformat(),
            "assets": assets, "gold_levels": _gold_levels(mt5_enabled=mt5_enabled),
            "gold": _gold_snapshot(mt5_enabled=mt5_enabled), "macro": _macro_snapshot(assets), "news": news,
            "news_source": news_source, "calendar": [],
            "economic_calendar": calendar, "calendar_state": calendar_state,
            "sources": [
                {"name": "MetaTrader 5", "state": "online" if mt5_rows else "offline", "detail": mt5_error or "Cotacoes da corretora"},
                {"name": "Trading Economics", "state": "ready" if te_ready else "configure", "detail": "Calendario economico"},
                {"name": "Twelve Data", "state": "ready" if td_ready else "configure", "detail": "Cobertura multiativos"},
            ], "configured": {"trading_economics": te_ready, "twelve_data": td_ready}}
