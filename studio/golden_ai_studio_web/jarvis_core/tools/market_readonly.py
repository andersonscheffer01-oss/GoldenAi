"""Read-only adapters over the existing MT5 and Golden implementations.

This module deliberately imports the legacy integrations lazily.  The Jarvis
ToolRegistry remains the only execution boundary; these adapters only read
terminal, scanner and risk state and return JSON-safe dictionaries.
"""
from __future__ import annotations

import importlib.util
import math
import re
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_TERMINAL_PATHS = (
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\terminal64.exe"),
)
_TERMINAL_PROCESS_NAMES = frozenset({"terminal64.exe", "terminal.exe"})
_TIMEFRAMES = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5",
               "M15": "TIMEFRAME_M15", "M30": "TIMEFRAME_M30",
               "H1": "TIMEFRAME_H1",
               "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1"}
_TIMEFRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900,
                      "M30": 1800, "H1": 3600, "H4": 14400,
                      "D1": 86400}
_MAX_CANDLES = 200
_MAX_RESULTS = 10
_READONLY_MT5_CONTRACT = {"provider": "MT5", "read_only": True,
                          "execution_authority": "NONE"}
_TREND_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
_TREND_WEIGHTS = {"M1": 0.05, "M5": 0.10, "M15": 0.15, "M30": 0.15,
                  "H1": 0.20, "H4": 0.20, "D1": 0.15}
_TREND_COMPONENT_WEIGHTS = {"structure": 0.30, "location": 0.20,
                            "momentum": 0.20, "persistence": 0.15,
                            "breakout": 0.15}
_TREND_METHOD = "ohlc-trend-v1"

# One canonical logical universe for new market reads. Broker aliases are
# explicit members of the same instrument; suffixes and partial matches are
# intentionally excluded.
AUTHORIZED_INSTRUMENT_ALIASES = {
    "SP500": frozenset({"SPX", "US500"}), "NASDAQ100": frozenset({"NDX", "US100"}),
    "DOWJONES": frozenset({"DJI", "US30"}), "EURUSD": frozenset({"EURUSD"}),
    "USDJPY": frozenset({"USDJPY"}), "GBPUSD": frozenset({"GBPUSD"}),
    "AUDUSD": frozenset({"AUDUSD"}), "USDCAD": frozenset({"USDCAD"}),
    "USDCHF": frozenset({"USDCHF"}), "NZDUSD": frozenset({"NZDUSD"}),
    "EURJPY": frozenset({"EURJPY"}), "GBPJPY": frozenset({"GBPJPY"}),
    "EURGBP": frozenset({"EURGBP"}), "AUDJPY": frozenset({"AUDJPY"}),
    "EURAUD": frozenset({"EURAUD"}), "EURCAD": frozenset({"EURCAD"}),
    "EURCHF": frozenset({"EURCHF"}), "GBPCAD": frozenset({"GBPCAD"}),
    "GBPCHF": frozenset({"GBPCHF"}), "CADJPY": frozenset({"CADJPY"}),
    "NZDJPY": frozenset({"NZDJPY"}), "USDCNH": frozenset({"USDCNH"}),
    "USDBRL": frozenset({"USDBRL"}), "USDMXN": frozenset({"USDMXN"}),
    "USDZAR": frozenset({"USDZAR"}), "USDSGD": frozenset({"USDSGD"}),
    "XAUUSD": frozenset({"XAUUSD"}), "XAGUSD": frozenset({"XAGUSD"}),
    "WTI": frozenset({"WTI", "USOIL"}), "BRENT": frozenset({"BRENT", "UKOIL"}),
    "BTCUSD": frozenset({"BTCUSD"}),
}
AUTHORIZED_INSTRUMENT_COUNT = len(AUTHORIZED_INSTRUMENT_ALIASES)
_AUTHORIZED_SYMBOL_TO_INSTRUMENT = {
    symbol: logical for logical, symbols in AUTHORIZED_INSTRUMENT_ALIASES.items()
    for symbol in symbols
}


def authorized_instrument_for_symbol(symbol: str) -> str | None:
    """Return the logical allowlisted instrument for one exact MT5 symbol."""
    return _AUTHORIZED_SYMBOL_TO_INSTRUMENT.get(str(symbol or "").strip().upper())


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if is_dataclass(value):
        return _json_value(asdict(value))
    if hasattr(value, "_asdict"):
        return _json_value(value._asdict())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except Exception:
            pass
    return str(value)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    marker = object()
    attribute = getattr(value, name, marker)
    if attribute is not marker:
        return _json_value(attribute)
    try:
        return _json_value(value[name])
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def _offline(reason: str, **extra: Any) -> dict[str, Any]:
    disabled = str(reason or "").startswith("SOURCE_DISABLED")
    return {
        **_READONLY_MT5_CONTRACT,
        "ok": True,
        "status": "DISABLED_BY_PROFILE" if disabled else "OFFLINE",
        "connected": False,
        "reason": str(reason or "MT5 desconectado"),
        "availability": "SOURCE_DISABLED" if disabled else "OFFLINE",
        "timestamp": _timestamp(),
        **extra,
    }


def _terminal_available() -> bool:
    return bool(_discover_open_mt5_terminals())


def _discover_open_mt5_terminals() -> list[dict[str, Any]]:
    """Enumerate active MT5 terminal processes without starting anything."""
    try:
        import psutil
    except Exception:
        return []
    candidates: dict[tuple[int, str], dict[str, Any]] = {}
    try:
        processes = psutil.process_iter(("name", "exe"))
        for process in processes:
            try:
                info = process.info or {}
                executable = str(info.get("exe") or "").strip()
                process_name = str(info.get("name") or "").strip().casefold()
                executable_name = Path(executable).name.casefold()
                if not executable or (process_name not in _TERMINAL_PROCESS_NAMES
                                      and executable_name not in _TERMINAL_PROCESS_NAMES):
                    continue
                resolved = str(Path(executable).resolve())
                pid = int(getattr(process, "pid", 0) or 0)
                key = (pid, resolved.casefold())
                candidates[key] = {
                    "pid": pid, "executable": resolved,
                    "process_name": process_name or executable_name,
                }
            except (AttributeError, KeyError, TypeError, ValueError, OSError):
                continue
    except Exception:
        return []
    return sorted(candidates.values(), key=lambda item: (
        str(item.get("executable") or "").casefold(), int(item.get("pid") or 0)))


def _shutdown_mt5(mt5: Any) -> None:
    """Release only the Python API attachment; never closes the terminal."""
    shutdown = getattr(mt5, "shutdown", None)
    if callable(shutdown):
        try:
            shutdown()
        except Exception:
            pass


def _candidate_is_still_open(candidate: dict[str, Any]) -> bool:
    """Revalidate the same PID/path immediately around the MT5 attach call."""
    try:
        pid = int(candidate.get("pid") or 0)
        executable = str(Path(str(candidate.get("executable") or "")).resolve())
        return any(
            int(item.get("pid") or 0) == pid
            and str(item.get("executable") or "").casefold() == executable.casefold()
            for item in _discover_open_mt5_terminals()
        )
    except (AttributeError, TypeError, ValueError, OSError):
        return False


def _attach_mt5_candidate(mt5: Any, candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Attach to one already-running candidate and collect read-only identity."""
    try:
        if not _candidate_is_still_open(candidate):
            return None
        if not mt5.initialize(path=str(candidate["executable"]), timeout=3000, portable=False):
            _shutdown_mt5(mt5)
            return None
        if not _candidate_is_still_open(candidate):
            _shutdown_mt5(mt5)
            return None
        terminal = mt5.terminal_info()
        if terminal is None or not bool(_field(terminal, "connected", False)):
            _shutdown_mt5(mt5)
            return None
        try:
            account = mt5.account_info()
        except Exception:
            account = None
        identity_values = [
            _field(account, "server", ""), _field(account, "company", ""),
            _field(terminal, "company", ""), _field(terminal, "name", ""),
            candidate.get("executable", ""),
        ]
        identity = " ".join(str(value or "") for value in identity_values)
        return {
            "candidate": candidate, "terminal": terminal, "account": account,
            "is_hantec": "hantec" in identity.casefold(),
        }
    except Exception:
        _shutdown_mt5(mt5)
        return None


def _connection() -> tuple[Any, Any, Any, str]:
    """Return the existing MT5 client, terminal, account and error reason."""
    try:
        mt5, terminal, reason = _market_data_connection()
        if reason or mt5 is None:
            return mt5, terminal, None, reason or "MT5 desconectado"
        account = mt5.account_info()
        if account is None:
            return mt5, terminal, account, "MT5 conta indisponível"
        return mt5, terminal, account, ""
    except Exception as exc:
        return None, None, None, f"MT5 indisponível: {type(exc).__name__}"


def _market_data_connection() -> tuple[Any, Any, str]:
    """Attach to an open terminal, preferring Hantec and never auto-launching."""
    try:
        from jarvis_core.runtime_profile import active_runtime_profile
        profile = active_runtime_profile()
        if not profile.market_data_read_enabled:
            return None, None, "SOURCE_DISABLED: MARKET_DATA_READ_DISABLED_BY_PROFILE"
        if not profile.mt5_market_data_read_enabled:
            return None, None, "SOURCE_DISABLED: MT5_MARKET_DATA_READ_DISABLED_BY_PROFILE"
        import MetaTrader5 as mt5
        candidates = _discover_open_mt5_terminals()
        if not candidates:
            return None, None, "NO_OPEN_MT5_TERMINAL"

        attached: list[dict[str, Any]] = []
        active_attachment: dict[str, Any] | None = None
        for candidate in candidates:
            if active_attachment is not None:
                _shutdown_mt5(mt5)
                active_attachment = None
            attachment = _attach_mt5_candidate(mt5, candidate)
            if attachment is not None:
                attached.append(attachment)
                active_attachment = attachment

        hantec = [item for item in attached if item["is_hantec"]]
        if len(hantec) > 1:
            _shutdown_mt5(mt5)
            return None, None, "MT5_HANTEC_TERMINAL_AMBIGUOUS"
        if len(hantec) == 1:
            selected = hantec[0]
        elif len(attached) == 1:
            selected = attached[0]
        elif len(attached) > 1:
            _shutdown_mt5(mt5)
            return None, None, "MT5_TERMINAL_AMBIGUOUS"
        else:
            return None, None, "MT5_TERMINAL_NOT_CONNECTED"

        if active_attachment is selected:
            return mt5, selected["terminal"], ""
        _shutdown_mt5(mt5)
        final_attachment = _attach_mt5_candidate(mt5, selected["candidate"])
        if final_attachment is None:
            return None, None, "EXISTING_TERMINAL_ATTACH_FAILED"
        return mt5, final_attachment["terminal"], ""
    except Exception as exc:
        return None, None, f"MARKET_DATA_ATTACH_FAILED:{type(exc).__name__}"


def get_readonly_mt5_connection() -> tuple[Any, Any, str]:
    """Public shared boundary for canonical market-data readers."""
    return _market_data_connection()


def _utc_iso(epoch: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _classify_mt5_instrument(info: Any, mt5: Any) -> tuple[str, str]:
    """Classify only from explicit MT5 group/type fields; never symbol labels."""
    path = str(_field(info, "path", "") or "")
    path_parts = [part.casefold() for part in re.split(r"[\\/>|]+", path) if part.strip()]
    groups = {re.sub(r"[^a-z0-9]", "", part) for part in path_parts}
    groups.update(token for part in path_parts for token in re.findall(r"[a-z0-9]+", part))
    path_classes = (
        ({"etf", "etfs", "exchangetradedfund", "exchangetradedfunds"}, "ETF"),
        ({"stock", "stocks", "share", "shares", "equity", "equities"}, "STOCKS"),
        ({"forex", "fx", "currency", "currencies"}, "FOREX"),
        ({"index", "indices"}, "INDICES"),
        ({"crypto", "cryptocurrency", "cryptocurrencies"}, "CRYPTO"),
        ({"metal", "metals", "gold", "silver", "platinum", "palladium",
          "preciousmetal", "preciousmetals"}, "METALS"),
        ({"commodity", "commodities"}, "COMMODITIES"),
    )
    path_class = next((asset_class for labels, asset_class in path_classes
                       if groups & labels), None)
    calc_mode = _field(info, "trade_calc_mode")
    calc_class = next((asset_class for constant, asset_class in (
        ("SYMBOL_CALC_MODE_EXCH_STOCKS", "STOCKS"),
        ("SYMBOL_CALC_MODE_CFDINDEX", "INDICES"),
        ("SYMBOL_CALC_MODE_FOREX", "FOREX"),
        ("SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE", "FOREX"),
        ("SYMBOL_CALC_MODE_FOREX_LEVERAGE", "FOREX"),
    ) if (expected := getattr(mt5, constant, None)) is not None
       and calc_mode == expected), None)
    base = str(_field(info, "currency_base", "") or "").strip().upper()
    quote = str(_field(info, "currency_profit", "") or "").strip().upper()
    verified_currency_pair = (bool(re.fullmatch(r"[A-Z]{3}", base))
                              and bool(re.fullmatch(r"[A-Z]{3}", quote))
                              and base != quote)

    # MT5 calculation mode describes pricing mechanics, not necessarily the
    # instrument category. Forex needs a distinct, explicit currency pair.
    if path_class == "FOREX" or (calc_class == "FOREX" and path_class is None):
        if not verified_currency_pair:
            return "OTHER_UNKNOWN", "INSUFFICIENT_CANONICAL_METADATA"
        if path_class == "FOREX" and calc_class in {"STOCKS", "INDICES"}:
            return "OTHER_UNKNOWN", "CONFLICTING_MT5_CLASS_METADATA"
        if path_class == "FOREX":
            return "FOREX", "MT5_SYMBOL_PATH_GROUP"
        return "FOREX", "MT5_TRADE_CALC_MODE"

    if path_class:
        return path_class, "MT5_SYMBOL_PATH_GROUP"
    if calc_class:
        return calc_class, "MT5_TRADE_CALC_MODE"
    if base in {"XAU", "XAG", "XPT", "XPD"}:
        return "METALS", "MT5_CURRENCY_BASE"
    if base in {"BTC", "XBT", "ETH"}:
        return "CRYPTO", "MT5_CURRENCY_BASE"
    if groups & {"other", "others", "misc", "miscellaneous"}:
        return "OTHER", "MT5_SYMBOL_PATH_GROUP"
    return "OTHER_UNKNOWN", "INSUFFICIENT_CANONICAL_METADATA"


_MT5_ASSET_CLASSES = {
    "FOREX", "INDICES", "STOCKS", "ETF", "CRYPTO", "COMMODITIES",
    "METALS", "OTHER", "OTHER_UNKNOWN",
}


def _technical_context(candles: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(row["close"]) for row in candles
              if isinstance(row.get("close"), (int, float)) and row["close"] > 0]
    if len(closes) < 50:
        return {"status": "INSUFFICIENT_HISTORY", "candles_used": len(closes),
                "trend": "UNKNOWN", "volatility_percent": None,
                "breakout": "UNKNOWN", "support_observed": None,
                "resistance_observed": None}
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    ranges = []
    for index, candle in enumerate(candles[-20:]):
        previous = candles[-21 + index].get("close") if index else candles[-21].get("close")
        high, low = candle.get("high"), candle.get("low")
        if all(isinstance(value, (int, float)) for value in (previous, high, low)):
            ranges.append(max(float(high) - float(low), abs(float(high) - float(previous)),
                              abs(float(low) - float(previous))))
    last_close = closes[-1]
    previous_window = candles[-21:-1]
    previous_high = max(float(row["high"]) for row in previous_window)
    previous_low = min(float(row["low"]) for row in previous_window)
    last_high, last_low = float(candles[-1]["high"]), float(candles[-1]["low"])
    breakout = ("ABOVE_OBSERVED_20_CANDLE_HIGH" if last_close > previous_high else
                "BELOW_OBSERVED_20_CANDLE_LOW" if last_close < previous_low else "WITHIN_OBSERVED_RANGE")
    return {
        "status": "AVAILABLE", "candles_used": len(closes),
        "trend": "UP" if sma20 > sma50 else "DOWN" if sma20 < sma50 else "RANGE",
        "sma20": sma20, "sma50": sma50,
        "volatility_percent": (sum(ranges) / len(ranges) / last_close * 100) if ranges else None,
        "breakout": breakout,
        "support_observed": min(float(row["low"]) for row in candles[-20:]),
        "resistance_observed": max(float(row["high"]) for row in candles[-20:]),
        "method": "OHLC-derived; price-unit agnostic; no pip conversion",
    }


def _clip_unit(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _trend_classification(score: int | float | None) -> str:
    if not isinstance(score, (int, float)) or not math.isfinite(score):
        return "UNKNOWN"
    if score >= 60:
        return "ALTA FORTE"
    if score >= 25:
        return "ALTA"
    if score <= -60:
        return "BAIXA FORTE"
    if score <= -25:
        return "BAIXA"
    return "LATERAL"


def _trend_frame_observation(timeframe: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    state = snapshot.get("state") if isinstance(snapshot.get("state"), dict) else {}
    freshness = str(state.get("freshness") or snapshot.get("freshness") or "UNKNOWN").upper()
    candles = snapshot.get("candles") if isinstance(snapshot.get("candles"), list) else []
    identity = snapshot.get("asset") if isinstance(snapshot.get("asset"), dict) else {}
    source_status = str(snapshot.get("status") or "UNKNOWN").upper()
    base = {
        "timeframe": timeframe,
        "snapshot_id": str(snapshot.get("snapshot_id") or "UNKNOWN"),
        "candle_count": len(candles),
        "raw_candle_time_start": candles[0].get("time_epoch") if candles else None,
        "raw_candle_time_end": candles[-1].get("time_epoch") if candles else None,
        "freshness": freshness,
        "temporal_authority": str(state.get("temporal_authority") or "UNKNOWN").upper(),
        "provider": str(identity.get("provider") or snapshot.get("provider") or "UNKNOWN"),
        "provider_symbol": str(identity.get("provider_symbol") or snapshot.get("provider_symbol") or ""),
    }
    if freshness == "STALE" or state.get("stale") is True:
        return {**base, "status": "STALE", "reason": "SOURCE_MARKED_STALE"}
    if (source_status in {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED", "INSTRUMENT_UNAVAILABLE"}
            or snapshot.get("ok") is False):
        return {**base, "status": "SOURCE_UNAVAILABLE",
                "reason": str(snapshot.get("reason") or source_status)}
    if len(candles) < 50 or not isinstance(snapshot.get("technical_context"), dict):
        return {**base, "status": "INSUFFICIENT_DATA", "reason": "MINIMUM_50_VALID_CANDLES_REQUIRED"}

    technical = snapshot["technical_context"]
    if technical.get("status") != "AVAILABLE":
        return {**base, "status": "INSUFFICIENT_DATA", "reason": "TECHNICAL_CONTEXT_UNAVAILABLE"}
    closes = [row.get("close") for row in candles]
    ranges = []
    for previous, candle in zip(candles[-15:-1], candles[-14:]):
        high, low, prior_close = candle.get("high"), candle.get("low"), previous.get("close")
        if not all(isinstance(value, (int, float)) and math.isfinite(value)
                   for value in (high, low, prior_close)):
            continue
        ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
    atr14 = sum(ranges) / len(ranges) if ranges else 0.0
    last_close = float(closes[-1])
    if atr14 <= 0 or last_close <= 0:
        return {**base, "status": "INSUFFICIENT_DATA", "reason": "ATR_NOT_COMPUTABLE"}

    trend_component = _clip_unit((technical["sma20"] - technical["sma50"]) / (2 * atr14))
    location_component = _clip_unit((last_close - technical["sma20"]) / (2 * atr14))
    momentum_component = _clip_unit((last_close - float(closes[-11])) /
                                    (2 * atr14 * math.sqrt(10)))
    breakout_state = str(technical.get("breakout") or "").upper()
    breakout_component = (1.0 if breakout_state == "ABOVE_OBSERVED_20_CANDLE_HIGH"
                          else -1.0 if breakout_state == "BELOW_OBSERVED_20_CANDLE_LOW"
                          else 0.0)
    recent_changes = [float(closes[index]) - float(closes[index - 1])
                      for index in range(len(closes) - 20, len(closes))]
    persistence_component = (sum(1 if value > 0 else -1 if value < 0 else 0
                                 for value in recent_changes) / len(recent_changes))
    score = round(100 * (
        _TREND_COMPONENT_WEIGHTS["structure"] * trend_component
        + _TREND_COMPONENT_WEIGHTS["location"] * location_component
        + _TREND_COMPONENT_WEIGHTS["momentum"] * momentum_component
        + _TREND_COMPONENT_WEIGHTS["persistence"] * persistence_component
        + _TREND_COMPONENT_WEIGHTS["breakout"] * breakout_component))
    score = max(-100, min(100, score))
    volume = [row.get("tick_volume") for row in candles[-40:]]
    valid_volume = [value for value in volume if isinstance(value, (int, float))
                    and math.isfinite(value) and value >= 0]
    volume_state = "AVAILABLE" if len(valid_volume) >= 20 else "UNAVAILABLE"
    volume_ratio = None
    if len(valid_volume) >= 40:
        earlier, recent = valid_volume[-40:-20], valid_volume[-20:]
        baseline = sum(earlier) / len(earlier)
        volume_ratio = round((sum(recent) / len(recent)) / baseline, 3) if baseline > 0 else None
    extension_atr = abs(last_close - float(technical["sma20"])) / atr14
    return {
        **base, "status": "AVAILABLE", "directional_score": score,
        "trend_classification": _trend_classification(score),
        "trend": technical.get("trend", "UNKNOWN"),
        "volatility_percent": technical.get("volatility_percent"),
        "breakout_context": technical.get("breakout", "UNKNOWN"),
        "volume_state": volume_state, "tick_volume_ratio": volume_ratio,
        "extension_distance_atr": round(extension_atr, 3),
        "extended_risk": extension_atr >= 2.0,
        "components": {"ma_spread_atr": round(trend_component, 4),
                       "price_location_atr": round(location_component, 4),
                       "momentum_10_candles": round(momentum_component, 4),
                       "directional_persistence_20": round(persistence_component, 4),
                       "observed_breakout_20_candles": breakout_component},
    }


def rank_market_trend_frames(asset: dict[str, Any], frames: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Deterministic OHLC-only directional intensity; never a win probability."""
    observations = [_trend_frame_observation(tf, frames.get(tf, {}))
                    for tf in _TREND_TIMEFRAMES]
    available = [item for item in observations if item["status"] == "AVAILABLE"]
    groups = {"FAST": {"M1", "M5", "M15"}, "MID": {"M30", "H1"},
              "SLOW": {"H4", "D1"}}
    covered_groups = sum(bool({item["timeframe"] for item in available} & values)
                         for values in groups.values())
    enough = len(available) >= 3 and covered_groups >= 2
    weight_total = sum(_TREND_WEIGHTS[item["timeframe"]] for item in available)
    applied_weights = ({item["timeframe"]: round(_TREND_WEIGHTS[item["timeframe"]] / weight_total, 6)
                        for item in available} if weight_total else {})
    score = None
    trend = "DADOS INSUFICIENTES"
    strength = "INDISPONÍVEL"
    alignment = {"aligned": 0, "available": len(available)}
    divergence = False
    extended = "UNKNOWN"
    if enough:
        score = round(sum(item["directional_score"] * applied_weights[item["timeframe"]]
                          for item in available))
        trend = _trend_classification(score)
        strength = "FORTE" if trend in {"ALTA FORTE", "BAIXA FORTE"} else (
            "MODERADA" if trend in {"ALTA", "BAIXA"} else "FRACA")
        dominant_direction = "UP" if score >= 25 else "DOWN" if score <= -25 else "FLAT"
        aligned = [item for item in available if
                   (dominant_direction == "UP" and item["directional_score"] >= 25)
                   or (dominant_direction == "DOWN" and item["directional_score"] <= -25)
                   or (dominant_direction == "FLAT" and abs(item["directional_score"]) < 25)]
        alignment = {"aligned": len(aligned), "available": len(available)}
        directions = {"UP" if item["directional_score"] >= 25 else
                      "DOWN" if item["directional_score"] <= -25 else "FLAT"
                      for item in available}
        divergence = "UP" in directions and "DOWN" in directions
        extended_rows = [item for item in available if item["extended_risk"]]
        extended = ("ELEVATED" if len(extended_rows) * 2 >= len(available) else "NOT_ELEVATED")
        broad_coverage = len(available) >= 4 and covered_groups == 3
        if not broad_coverage and strength == "FORTE":
            trend, strength = ("ALTA", "MODERADA") if score > 0 else ("BAIXA", "MODERADA")

    stale_count = sum(item["status"] == "STALE" for item in observations)
    missing_volume = sum(item["volume_state"] == "UNAVAILABLE"
                         for item in available if "volume_state" in item)
    freshness_states = {item["freshness"] for item in available}
    temporal_authorities = {item["temporal_authority"] for item in available}
    freshness = ("STALE" if stale_count and not available else
                 "UNKNOWN" if "UNKNOWN" in freshness_states or not freshness_states else
                 next(iter(freshness_states)))
    temporal_authority = ("UNKNOWN" if "UNKNOWN" in temporal_authorities
                          or not temporal_authorities else next(iter(temporal_authorities)))
    identity = asset if isinstance(asset, dict) else {}
    return {
        "asset": {key: identity.get(key) for key in
                  ("provider", "provider_asset_id", "provider_symbol",
                   "display_symbol", "display_name", "asset_class",
                   "asset_class_source") if key in identity},
        "trend": trend, "strength": strength, "directional_score": score,
        "score_semantics": "DIRECTIONAL_INTENSITY_NOT_PROBABILITY",
        "alignment": alignment, "timeframe_divergence": divergence,
        "applied_timeframe_weights": applied_weights,
        "extended_trend_risk": extended,
        "evaluated_timeframes": observations,
        "data_state": ("INSUFFICIENT_DATA" if not enough else
                       "PARTIAL_TIMEFRAMES_FRESHNESS_UNKNOWN"
                       if len(available) < len(_TREND_TIMEFRAMES) else
                       "AVAILABLE_FRESHNESS_UNKNOWN"),
        "freshness": freshness, "temporal_authority": temporal_authority,
        "absolute_utc_verified": "UNKNOWN",
        "tick_volume_state": "PARTIAL" if missing_volume else "AVAILABLE",
        "stale_timeframes": stale_count,
        "macro_news_inputs": "NOT_USED_UNVERIFIED_TEMPORAL_SOURCES",
        "snapshot_ids": [item["snapshot_id"] for item in available
                         if item.get("snapshot_id") != "UNKNOWN"],
        "methodology_version": _TREND_METHOD,
        "execution_authority": "NONE",
    }


def mt5_status() -> dict[str, Any]:
    mt5, terminal, account, reason = _connection()
    if reason:
        return _offline(reason, terminal_available=bool(terminal) or _terminal_available(),
                        account_available=bool(account), server=_field(account, "server"))
    return {**_READONLY_MT5_CONTRACT,
        "ok": True,
        "status": "CONNECTED",
        "connected": True,
        "terminal_available": True,
        "account_available": bool(account),
        "terminal": _field(terminal, "name"),
        "server": _field(account, "server"),
        "broker": _field(account, "server"),
        "timestamp": _timestamp(),
    }


def mt5_account_info() -> dict[str, Any]:
    _, _, account, reason = _connection()
    if reason or account is None:
        return _offline(reason or "Conta MT5 indisponível", account=None)
    login = _field(account, "login")
    masked_login = f"***{str(login)[-4:]}" if login is not None else None
    return {**_READONLY_MT5_CONTRACT,
        "ok": True,
        "status": "CONNECTED",
        "account": {
            "login": masked_login,
            "server": _field(account, "server"),
            "currency": _field(account, "currency"),
            "balance": _field(account, "balance"),
            "equity": _field(account, "equity"),
            "margin": _field(account, "margin"),
            "free_margin": _field(account, "margin_free"),
            "margin_level": _field(account, "margin_level"),
            "profit": _field(account, "profit"),
        },
        "timestamp": _timestamp(),
    }


def _position_side(value: Any) -> str:
    return "LONG" if int(value or 0) == 0 else "SHORT" if int(value or 0) == 1 else "UNKNOWN"


def mt5_positions() -> dict[str, Any]:
    mt5, _, _, reason = _connection()
    if reason or mt5 is None:
        return _offline(reason or "MT5 desconectado", positions=[])
    try:
        rows = mt5.positions_get() or []
        positions = [{
            "symbol": _field(row, "symbol"),
            "side": _position_side(_field(row, "type", 0)),
            "volume": _field(row, "volume"),
            "price_open": _field(row, "price_open"),
            "price_current": _field(row, "price_current"),
            "sl": _field(row, "sl"),
            "tp": _field(row, "tp"),
            "profit": _field(row, "profit"),
            "swap": _field(row, "swap"),
            "ticket": _field(row, "ticket"),
        } for row in rows]
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "CONNECTED", "positions": positions,
                "count": len(positions), "timestamp": _timestamp()}
    except Exception as exc:
        return _offline(f"Falha ao consultar posições: {type(exc).__name__}", positions=[])


def mt5_orders() -> dict[str, Any]:
    mt5, _, _, reason = _connection()
    if reason or mt5 is None:
        return _offline(reason or "MT5 desconectado", orders=[])
    try:
        rows = mt5.orders_get() or []
        orders = [{
            "symbol": _field(row, "symbol"),
            "type": _field(row, "type"),
            "volume": _field(row, "volume_current", _field(row, "volume_initial")),
            "price": _field(row, "price_open"),
            "sl": _field(row, "sl"),
            "tp": _field(row, "tp"),
            "ticket": _field(row, "ticket"),
        } for row in rows]
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "CONNECTED", "orders": orders,
                "count": len(orders), "timestamp": _timestamp()}
    except Exception as exc:
        return _offline(f"Falha ao consultar ordens: {type(exc).__name__}", orders=[])


def _resolve_symbol(mt5: Any, requested: str) -> tuple[str, list[str], str]:
    symbol = str(requested or "").strip()
    if not symbol:
        return "", [], "Símbolo obrigatório."
    try:
        if mt5.symbol_info(symbol) is not None:
            return symbol, [], ""
        rows: Iterable[Any] = mt5.symbols_get() or []
    except Exception as exc:
        return "", [], f"Falha ao resolver símbolo: {type(exc).__name__}"
    normalized = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    suggestions = []
    for row in rows:
        name = str(_field(row, "name", ""))
        clean = re.sub(r"[^A-Z0-9]", "", name.upper())
        if clean == normalized or normalized in clean or clean.startswith(normalized):
            suggestions.append(name)
    return "", suggestions[:10], "Símbolo não encontrado."


def mt5_symbol_tick(symbol: str) -> dict[str, Any]:
    mt5, _, _, reason = _connection()
    if reason or mt5 is None:
        return _offline(reason or "MT5 desconectado", requested_symbol=symbol, tick=None)
    resolved, suggestions, resolve_error = _resolve_symbol(mt5, symbol)
    if not resolved:
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "NOT_FOUND", "requested_symbol": symbol,
                "suggestions": suggestions, "reason": resolve_error,
                "timestamp": _timestamp()}
    try:
        info, tick = mt5.symbol_info(resolved), mt5.symbol_info_tick(resolved)
        if tick is None:
            return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "DEGRADED", "symbol": resolved,
                    "reason": "Tick indisponível", "timestamp": _timestamp()}
        bid, ask = float(tick.bid or 0), float(tick.ask or 0)
        point = float(_field(info, "point", 0) or 0)
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "CONNECTED", "symbol": resolved,
                "bid": bid, "ask": ask, "last": _field(tick, "last"),
                "spread": round((ask - bid) / point, 4) if point else None,
                "time": _field(tick, "time"), "timestamp": _timestamp(),
                "source": "MT5"}
    except Exception as exc:
        return _offline(f"Falha ao consultar tick: {type(exc).__name__}", symbol=resolved)


def mt5_symbol_info(symbol: str) -> dict[str, Any]:
    mt5, _, _, reason = _connection()
    if reason or mt5 is None:
        return _offline(reason or "MT5 desconectado", requested_symbol=symbol, info=None)
    resolved, suggestions, resolve_error = _resolve_symbol(mt5, symbol)
    if not resolved:
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "NOT_FOUND", "requested_symbol": symbol,
                "suggestions": suggestions, "reason": resolve_error,
                "timestamp": _timestamp()}
    try:
        info = mt5.symbol_info(resolved)
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "CONNECTED", "symbol": resolved,
                "info": {"symbol": _field(info, "name", resolved),
                         "description": _field(info, "description"),
                         "digits": _field(info, "digits"),
                         "point": _field(info, "point"),
                         "trade_tick_size": _field(info, "trade_tick_size"),
                         "trade_tick_value": _field(info, "trade_tick_value"),
                         "volume_min": _field(info, "volume_min"),
                         "volume_max": _field(info, "volume_max"),
                         "volume_step": _field(info, "volume_step"),
                         "trade_mode": _field(info, "trade_mode"),
                         "currency_base": _field(info, "currency_base"),
                         "currency_profit": _field(info, "currency_profit")},
                "timestamp": _timestamp(), "source": "MT5"}
    except Exception as exc:
        return _offline(f"Falha ao consultar símbolo: {type(exc).__name__}", symbol=resolved)


def mt5_search_symbols(query: str, asset_class: str = "ALL", limit: int = 40) -> dict[str, Any]:
    """Enumerate or search provider instruments using scoped read-only metadata."""
    query = str(query or "").strip()
    if len(query) > 64:
        return {**_READONLY_MT5_CONTRACT, "ok": False, "status": "INVALID_QUERY", "assets": [],
                "reason": "QUERY_TOO_LONG"}
    requested_class = str(asset_class or "ALL").strip().upper()
    if requested_class not in {"ALL", *_MT5_ASSET_CLASSES}:
        return {**_READONLY_MT5_CONTRACT, "ok": False,
                "status": "INVALID_ASSET_CLASS", "assets": []}
    mt5, _, reason = _market_data_connection()
    if reason or mt5 is None:
        status = "SOURCE_DISABLED" if "SOURCE_DISABLED" in str(reason) else "SOURCE_UNAVAILABLE"
        return {**_READONLY_MT5_CONTRACT, "ok": False, "status": status,
                "assets": [], "reason": str(reason or "MT5_UNAVAILABLE")[:120]}

    needle = re.sub(r"[^A-Z0-9]", "", query.upper())
    try:
        rows = mt5.symbols_get() or []
        assets = []
        classification_counts = {kind: 0 for kind in sorted(_MT5_ASSET_CLASSES)}
        for row in rows:
            name = str(_field(row, "name", "") or "")
            logical_instrument = authorized_instrument_for_symbol(name)
            if logical_instrument is None:
                continue
            description = str(_field(row, "description", "") or "")
            path = str(_field(row, "path", "") or "")
            base = str(_field(row, "currency_base", "") or "").upper()
            quote = str(_field(row, "currency_profit", "") or "").upper()
            haystack = re.sub(r"[^A-Z0-9]", "", " ".join((name, description, path, base, quote)).upper())
            if needle and needle not in haystack:
                continue
            kind, class_source = _classify_mt5_instrument(row, mt5)
            if requested_class not in {"ALL", kind}:
                classification_counts[kind] += 1
                continue
            info = mt5.symbol_info(name)
            if info is not None:
                kind, class_source = _classify_mt5_instrument(info, mt5)
                if requested_class not in {"ALL", kind}:
                    classification_counts[kind] += 1
                    continue
            else:
                info = row
            base = str(_field(info, "currency_base", "") or "").upper()
            quote = str(_field(info, "currency_profit", "") or "").upper()
            path = str(_field(info, "path", "") or path)
            description = str(_field(info, "description", "") or description)
            metadata_text = " ".join((description, path)).casefold()
            is_bitcoin = (kind == "CRYPTO" and "bitcoin" in metadata_text
                          and "bitcoin cash" not in metadata_text)
            try:
                tick = (mt5.symbol_info_tick(name)
                        if is_bitcoin else None)
            except Exception:
                tick = None
            tick_time = _utc_iso(_field(tick, "time")) if tick is not None else None
            crypto_identity = "Bitcoin" if is_bitcoin else (
                "Ethereum" if kind == "CRYPTO" and "ethereum" in metadata_text else None)
            assets.append({
                "provider": "MT5", "provider_asset_id": f"mt5:{name}",
                "provider_symbol": name, "symbol": name,
                "logical_instrument": logical_instrument,
                "canonical_symbol": f"{base}/{quote}" if kind == "FOREX" and base and quote else name,
                "canonical_pair": f"{base}/{quote}" if kind == "FOREX" and base and quote else None,
                "display_name": crypto_identity or description or name, "display_symbol": name,
                "asset_class": kind, "asset_class_source": class_source,
                "source_available": True,
                "market_data_available": False, "source_status": "DISCOVERED",
                "currency_base": base or None, "currency_quote": quote or None,
                "currency_base_reported": str(_field(info, "currency_base", "") or "") or None,
                "currency_profit_reported": str(_field(info, "currency_profit", "") or "") or None,
                "digits": _field(info, "digits"), "point_size": _field(info, "point"),
                "precision": _field(info, "digits"),
                "tick_size": _field(info, "trade_tick_size"),
                "contract_size": _field(info, "trade_contract_size"),
                "path": path, "description": description,
                "price_unit": f"{quote} per {base}" if base and quote and kind != "CRYPTO" else None,
                "last_tick_timestamp": tick_time,
                "session_metadata": {
                    "trade_mode": _field(info, "trade_mode"),
                    "trade_exemode": _field(info, "trade_exemode"),
                    "start_time": _field(info, "start_time"),
                    "expiration_time": _field(info, "expiration_time"),
                },
                "metadata_warnings": (["BROKER_CURRENCY_METADATA_CONFLICTS_WITH_BITCOIN_IDENTITY"]
                                      if is_bitcoin and base not in {"BTC", "XBT"}
                                      else []),
                "market_session": "UNKNOWN_PENDING_LIVE_PROVIDER_OBSERVATION",
            })
            classification_counts[kind] += 1
            if needle and len(assets) >= max(1, min(int(limit), 100)):
                break
        return {**_READONLY_MT5_CONTRACT, "ok": True,
                "status": "AVAILABLE" if assets else "NO_MATCH",
                "assets": assets, "query": query,
                "observed_at": _timestamp(), "read_only": True,
                "enumerated_count": len(rows), "classification_counts": classification_counts,
                "execution_authority": "NONE", "capability": "MT5_MARKET_DATA_READ"}
    except Exception as exc:
        return {**_READONLY_MT5_CONTRACT, "ok": False,
                "status": "SOURCE_UNAVAILABLE",
                "assets": [], "reason": type(exc).__name__,
                "observed_at": _timestamp(), "read_only": True}


def mt5_market_data_snapshot(symbol: str, timeframe: str = "M15", count: int = 120) -> dict[str, Any]:
    """Return one bounded quote/candle snapshot without touching account or trade APIs."""
    symbol = str(symbol or "").strip()[:64]
    timeframe = str(timeframe or "M15").strip().upper()
    try:
        count = max(50, min(int(count), _MAX_CANDLES))
    except (TypeError, ValueError):
        count = 120
    if not symbol or timeframe not in _TIMEFRAMES:
        return {**_READONLY_MT5_CONTRACT, "ok": False, "status": "INVALID_REQUEST",
                "provider_symbol": symbol, "reason": "SYMBOL_OR_TIMEFRAME_INVALID"}
    mt5, terminal, reason = _market_data_connection()
    if reason or mt5 is None:
        return {"ok": False, "status": "SOURCE_DISABLED" if "SOURCE_DISABLED" in reason else "SOURCE_UNAVAILABLE",
                "provider": "MT5", "provider_symbol": symbol, "candles": [],
                "reason": reason, "read_only": True, "execution_authority": "NONE"}
    try:
        info = mt5.symbol_info(symbol)
        if info is None or str(_field(info, "name", "")) != symbol:
            return {"ok": False, "status": "INSTRUMENT_UNAVAILABLE", "provider": "MT5",
                    "provider_symbol": symbol, "candles": [], "read_only": True,
                    "execution_authority": "NONE"}
        tick = mt5.symbol_info_tick(symbol)
        rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, _TIMEFRAMES[timeframe]), 1, count)
        candles = []
        for row in rates if rates is not None else []:
            epoch = _field(row, "time")
            values = {name: _field(row, name) for name in ("open", "high", "low", "close")}
            if (not _utc_iso(epoch)
                    or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                           or value <= 0 for value in values.values())
                    or values["high"] < max(values["open"], values["close"])
                    or values["low"] > min(values["open"], values["close"])):
                continue
            candles.append({"time": _utc_iso(epoch), "time_epoch": int(epoch),
                            "time_interpretation": "UTC_PROJECTION_UNVERIFIED", **values,
                            "tick_volume": _field(row, "tick_volume"),
                            "real_volume": _field(row, "real_volume")})
        candles.sort(key=lambda item: int(item.get("time_epoch") or 0))
        interval = _TIMEFRAME_SECONDS[timeframe]
        gaps = [{"from": candles[index - 1]["time"], "to": candles[index]["time"],
                 "missing_intervals_estimate": max(0, int(
                     (candles[index]["time_epoch"] - candles[index - 1]["time_epoch"])
                     // interval) - 1)}
                for index in range(1, len(candles))
                if candles[index]["time_epoch"] - candles[index - 1]["time_epoch"] > interval * 3]
        now = datetime.now(timezone.utc)
        raw_quote_time = _field(tick, "time") if tick is not None else None
        raw_quote_time_msc = _field(tick, "time_msc") if tick is not None else None
        quote_time = _utc_iso(raw_quote_time)
        try:
            quote_age = (now - datetime.fromisoformat(quote_time)).total_seconds() if quote_time else None
        except ValueError:
            quote_age = None
        last_candle = candles[-1] if candles else {}
        candle_age = None
        if last_candle.get("time"):
            candle_age = (now - datetime.fromisoformat(last_candle["time"])).total_seconds()
        # Provider epochs are retained, but freshness is not authoritative until
        # this terminal/broker's time convention is independently established.
        quote_freshness = candle_freshness = freshness = "UNKNOWN"
        bid = _field(tick, "bid") if tick is not None else None
        ask = _field(tick, "ask") if tick is not None else None
        last = _field(tick, "last") if tick is not None else None
        bid = bid if isinstance(bid, (int, float)) and bid > 0 else None
        ask = ask if isinstance(ask, (int, float)) and ask > 0 else None
        last = last if isinstance(last, (int, float)) and last > 0 else None
        point = float(_field(info, "point", 0) or 0)
        base = str(_field(info, "currency_base", "") or "").upper()
        quote_currency = str(_field(info, "currency_profit", "") or "").upper()
        path = str(_field(info, "path", "") or "")
        description = str(_field(info, "description", "") or "")
        metadata_text = " ".join((path, description, symbol)).casefold()
        asset_class, asset_class_source = _classify_mt5_instrument(info, mt5)
        technical = _technical_context(candles)
        quote_available = bool(tick is not None and bid is not None and ask is not None)
        candle_history_available = len(candles) >= 50
        market_data_available = bool(quote_available and candle_history_available)
        provider_epoch_relation = "UNKNOWN"
        if ((quote_age is not None and quote_age < -300)
                or (candle_age is not None and candle_age < -interval)):
            provider_epoch_relation = "AHEAD_OF_LOCAL_UTC_UNVERIFIED"
        elif quote_age is not None or candle_age is not None:
            provider_epoch_relation = "NOT_AHEAD_OF_LOCAL_UTC_UNVERIFIED"
        market_session = "UNKNOWN"
        partial_reasons = ["TEMPORAL_AUTHORITY_UNKNOWN",
                           "FRESHNESS_UNVERIFIED_WITHOUT_TEMPORAL_AUTHORITY",
                           "MARKET_SESSION_UNVERIFIED"]
        if not quote_available:
            partial_reasons.append("QUOTE_UNAVAILABLE_OR_INVALID")
        if not candle_history_available:
            partial_reasons.append("CANDLE_HISTORY_INSUFFICIENT")
        if provider_epoch_relation == "AHEAD_OF_LOCAL_UTC_UNVERIFIED":
            partial_reasons.append("PROVIDER_EPOCH_DIFFERS_FROM_LOCAL_UTC_UNVERIFIED")
        if gaps:
            partial_reasons.append("CANDLE_GAPS_OR_SESSION_BREAKS_OBSERVED")
        temporal_components = {
            "symbol": "VALID",
            "quote": "AVAILABLE" if quote_available else "UNAVAILABLE",
            "candles": "AVAILABLE" if candles else "UNAVAILABLE",
            "provenance": "AVAILABLE",
            "temporal_authority": "UNKNOWN",
            "freshness": "UNKNOWN",
            "session": "UNKNOWN",
        }
        return {
            "ok": True, "status": "PARTIAL", "provider": "MT5",
            "provider_symbol": symbol, "read_only": True,
            "snapshot_id": "market_snapshot_" + uuid.uuid4().hex,
            "asset": {"asset_id": f"mt5:{symbol}", "display_name": _field(info, "description") or symbol,
                      "canonical_symbol": (f"{base}/{quote_currency}"
                                           if asset_class == "FOREX" and base and quote_currency
                                           else symbol),
                      "provider_symbol": symbol, "asset_class": asset_class,
                      "asset_class_source": asset_class_source, "provider": "MT5"},
            "instrument": {"symbol": symbol, "digits": _field(info, "digits"),
                           "precision": _field(info, "digits"), "point_size": point or None,
                           "tick_size": _field(info, "trade_tick_size"),
                           "currency_base": base or None, "currency_quote": quote_currency or None,
                           "currency_base_reported": str(_field(info, "currency_base", "") or "") or None,
                           "currency_profit_reported": str(_field(info, "currency_profit", "") or "") or None,
                           "quote_currency": quote_currency or None,
                           "price_unit": (f"{quote_currency} per {base}" if base and quote_currency
                                          and asset_class != "CRYPTO" else None),
                           "trade_mode": _field(info, "trade_mode"),
                           "session_metadata": {"trade_exemode": _field(info, "trade_exemode"),
                                                "start_time": _field(info, "start_time"),
                                                "expiration_time": _field(info, "expiration_time")}},
            "quote": {"bid": bid, "ask": ask, "last": last,
                      "spread_price": (ask - bid) if isinstance(ask, (int, float)) and isinstance(bid, (int, float)) else None,
                      "spread_points": ((ask - bid) / point) if point and isinstance(ask, (int, float)) and isinstance(bid, (int, float)) else None,
                      "time": raw_quote_time, "time_epoch": raw_quote_time,
                      "time_msc": raw_quote_time_msc,
                      "timestamp": quote_time,
                      "timestamp_interpretation": "UTC_PROJECTION_UNVERIFIED",
                      "time_status": "UNKNOWN", "freshness": quote_freshness},
            "candles": candles, "timeframe": timeframe, "candle_count": len(candles),
            "candle_range": {"start": candles[0].get("time") if candles else None,
                             "end": last_candle.get("time") if candles else None},
            "gaps": gaps[:20], "gap_count": len(gaps),
            "requested_candle_count": count,
            "candles_complete": len(candles) >= count,
            "technical_context": technical,
            "state": {"source_available": True, "market_data_available": market_data_available,
                      "freshness": freshness,
                      "stale": None if freshness == "UNKNOWN" else freshness == "STALE",
                      "quote_freshness": quote_freshness, "candle_freshness": candle_freshness,
                      "market_session": market_session,
                      "provider_epoch_relation": provider_epoch_relation,
                      "timestamp_comparison": "UNVERIFIED_PROVIDER_EPOCH_VS_LOCAL_UTC",
                      "time_status": "UNKNOWN", "temporal_authority": "UNKNOWN",
                      "components": temporal_components,
                      "partial_reasons": partial_reasons,
                      "quote_epoch_delta_seconds_unverified": (
                          round(-quote_age, 3) if quote_age is not None else None),
                      "candle_epoch_delta_seconds_unverified": (
                          round(-candle_age, 3) if candle_age is not None else None)},
            "provenance": {"provider": "MT5", "source": "MetaTrader5 Python read APIs",
                           "fetched_at": now.isoformat(), "quote_timestamp": quote_time,
                           "quote_time_raw": raw_quote_time,
                           "quote_time_msc_raw": raw_quote_time_msc,
                           "temporal_authority": "UNKNOWN",
                           "timestamp_interpretation": "UTC_PROJECTION_UNVERIFIED",
                           "capability": "MT5_MARKET_DATA_READ", "read_only": True,
                           "terminal_data_root": str(_field(terminal, "data_path", "")),
                           "warnings": partial_reasons},
            "partial_reasons": partial_reasons,
            "execution_authority": "NONE", "orders_sent": 0,
            "positions_mutated": False, "broker_mutated": False,
        }
    except Exception as exc:
        return {"ok": False, "status": "SOURCE_UNAVAILABLE", "provider": "MT5",
                "provider_symbol": symbol, "candles": [], "reason": type(exc).__name__,
                "read_only": True, "execution_authority": "NONE"}


def mt5_market_data_update(symbol: str, timeframe: str = "M15") -> dict[str, Any]:
    """Read only the current quote and forming candle; never fetch history."""
    symbol = str(symbol or "").strip()[:64]
    timeframe = str(timeframe or "M15").strip().upper()
    if not symbol or timeframe not in _TIMEFRAMES:
        return {**_READONLY_MT5_CONTRACT, "ok": False, "status": "INVALID_REQUEST",
                "provider_symbol": symbol, "reason": "SYMBOL_OR_TIMEFRAME_INVALID"}
    mt5, _terminal, reason = _market_data_connection()
    if reason or mt5 is None:
        return {"ok": False, "status": "SOURCE_DISABLED" if "SOURCE_DISABLED" in reason else "SOURCE_UNAVAILABLE",
                "provider": "MT5", "provider_symbol": symbol,
                "reason": reason, "read_only": True, "execution_authority": "NONE"}
    try:
        info = mt5.symbol_info(symbol)
        if info is None or str(_field(info, "name", "")) != symbol:
            return {"ok": False, "status": "INSTRUMENT_UNAVAILABLE", "provider": "MT5",
                    "provider_symbol": symbol, "read_only": True, "execution_authority": "NONE"}
        base = str(_field(info, "currency_base", "") or "").upper()
        quote_currency = str(_field(info, "currency_profit", "") or "").upper()
        metadata_text = " ".join((str(_field(info, "path", "") or ""),
                                  str(_field(info, "description", "") or ""), symbol)).casefold()
        asset_class, asset_class_source = _classify_mt5_instrument(info, mt5)
        tick = mt5.symbol_info_tick(symbol)
        rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, _TIMEFRAMES[timeframe]), 0, 1)
        row = rates[0] if rates is not None and len(rates) else None
        epoch = _field(row, "time") if row is not None else None
        values = {name: _field(row, name) for name in ("open", "high", "low", "close")} if row is not None else {}
        valid_candle = bool(_utc_iso(epoch) and all(
            isinstance(value, (int, float)) and math.isfinite(value) and value > 0
            for value in values.values()) and values["high"] >= max(values["open"], values["close"])
            and values["low"] <= min(values["open"], values["close"]))
        quote_epoch = _field(tick, "time") if tick is not None else None
        quote_time_msc = _field(tick, "time_msc") if tick is not None else None
        quote = {name: _field(tick, name) if tick is not None else None
                 for name in ("bid", "ask", "last")}
        quote = {name: value if isinstance(value, (int, float)) and math.isfinite(value) and value > 0 else None
                 for name, value in quote.items()}
        candle = ({"time_epoch": int(epoch), "time": _utc_iso(epoch),
                   "time_interpretation": "UTC_PROJECTION_UNVERIFIED", **values,
                   "tick_volume": _field(row, "tick_volume"), "real_volume": _field(row, "real_volume")}
                  if valid_candle else None)
        return {"ok": bool(tick is not None and candle is not None),
                "status": "AVAILABLE" if tick is not None and candle else "PARTIAL",
                "provider": "MT5", "provider_symbol": symbol,
                "snapshot_id": "market_update_" + uuid.uuid4().hex,
                "asset_class": asset_class, "asset_class_source": asset_class_source,
                "timeframe": timeframe,
                "quote": {**quote, "time": quote_epoch,
                          "time_epoch": int(quote_epoch) if quote_epoch else None,
                          "time_msc": int(quote_time_msc) if quote_time_msc else None,
                          "timestamp": _utc_iso(quote_epoch),
                          "timestamp_interpretation": "UTC_PROJECTION_UNVERIFIED",
                          "time_status": "UNKNOWN"},
                "candle": candle, "received_at": _timestamp(),
                "received_monotonic_ns": time.monotonic_ns(),
                "freshness": "UNKNOWN", "time_status": "UNKNOWN",
                "temporal_authority": "UNKNOWN", "read_only": True,
                "execution_authority": "NONE", "capability": "MT5_MARKET_DATA_READ"}
    except Exception as exc:
        return {"ok": False, "status": "SOURCE_UNAVAILABLE", "provider": "MT5",
                "provider_symbol": symbol, "reason": type(exc).__name__,
                "read_only": True, "execution_authority": "NONE"}


def mt5_recent_candles(symbol: str, timeframe: str = "M15", count: int = 100) -> dict[str, Any]:
    timeframe = str(timeframe or "M15").upper()
    try:
        count = max(1, min(int(count), _MAX_CANDLES))
    except (TypeError, ValueError):
        count = 100
    mt5, _, _, reason = _connection()
    if reason or mt5 is None:
        return _offline(reason or "MT5 desconectado", requested_symbol=symbol,
                        timeframe=timeframe, candles=[])
    resolved, suggestions, resolve_error = _resolve_symbol(mt5, symbol)
    if not resolved:
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "NOT_FOUND", "requested_symbol": symbol,
                "timeframe": timeframe, "suggestions": suggestions,
                "reason": resolve_error, "candles": [], "timestamp": _timestamp()}
    constant_name = _TIMEFRAMES.get(timeframe)
    if not constant_name or not hasattr(mt5, constant_name):
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "INVALID_TIMEFRAME", "symbol": resolved,
                "timeframe": timeframe, "candles": [],
                "reason": "Timeframe não suportado.", "timestamp": _timestamp()}
    try:
        rates = mt5.copy_rates_from_pos(resolved, getattr(mt5, constant_name), 1, count)
        rows = rates if rates is not None else []
        candles = [{"time": _field(row, "time"), "open": _field(row, "open"),
                    "high": _field(row, "high"), "low": _field(row, "low"),
                    "close": _field(row, "close"),
                    "tick_volume": _field(row, "tick_volume"),
                    "volume": _field(row, "real_volume")} for row in rows]
        return {**_READONLY_MT5_CONTRACT, "ok": True, "status": "CONNECTED", "symbol": resolved,
                "timeframe": timeframe, "count": len(candles), "candles": candles,
                "timestamp": _timestamp(), "source": "MT5"}
    except Exception as exc:
        return _offline(f"Falha ao consultar candles: {type(exc).__name__}",
                        symbol=resolved, timeframe=timeframe, candles=[])


def golden_status() -> dict[str, Any]:
    mt5_state = mt5_status()
    modules = {
        "scanner_available": bool(importlib.util.find_spec("golden_scanner")),
        "risk_available": bool(importlib.util.find_spec("risk_engine")),
        "strategy_engine_available": bool(importlib.util.find_spec("strategy_engine")),
        "market_data_available": bool(importlib.util.find_spec("market_data")),
    }
    return {"ok": True, "status": "AVAILABLE" if all(modules.values()) else "DEGRADED",
            **modules, "mt5_connection_status": mt5_state.get("status"),
            "timestamp": _timestamp()}


def golden_scanner_status() -> dict[str, Any]:
    try:
        from golden_scanner import GoldenScanner
        scanner = GoldenScanner()
        summary = scanner.strategy_manager.get_status_summary()
        return {"ok": True, "status": "AVAILABLE", "scanner_available": True,
                "setup_count": len(scanner.setups), "strategy_manager": summary,
                "scan_started": False, "timestamp": _timestamp()}
    except Exception as exc:
        return {"ok": True, "status": "DEGRADED", "scanner_available": False,
                "scan_started": False, "reason": str(exc)[:160],
                "timestamp": _timestamp()}


def golden_scanner_results(symbol: str = "", limit: int = 3) -> dict[str, Any]:
    try:
        limit = max(1, min(int(limit), _MAX_RESULTS))
    except (TypeError, ValueError):
        limit = 3
    if not str(symbol or "").strip():
        return {"ok": True, "status": "NO_CACHE", "results": [],
                "reason": "Nenhum resultado recente em cache.", "timestamp": _timestamp()}
    mt5_state = mt5_status()
    if not mt5_state.get("connected"):
        return {"ok": True, "status": "DEGRADED", "results": [],
                "reason": "MT5 desconectado; scanner não executado.",
                "timestamp": _timestamp()}
    try:
        from golden_scanner import GoldenScanner
        scan = _json_value(GoldenScanner().scan_symbol(str(symbol).strip()))
        if isinstance(scan, dict) and isinstance(scan.get("setups"), list):
            scan["setups"] = scan["setups"][:limit]
        return {"ok": True, "status": "AVAILABLE", "symbol": symbol,
                "results": [scan], "timestamp": _timestamp()}
    except Exception as exc:
        return {"ok": True, "status": "DEGRADED", "results": [],
                "reason": f"Scanner indisponível: {type(exc).__name__}",
                "timestamp": _timestamp()}


def golden_risk_status() -> dict[str, Any]:
    try:
        from risk_engine import get_risk_engine
        engine = get_risk_engine()
        mt5_state = mt5_status()
        positions = []
        if mt5_state.get("connected"):
            raw = mt5_positions()
            positions = [{"entry": item.get("price_open", 0),
                          "sl": item.get("sl", 0),
                          "symbol": item.get("symbol", "")}
                         for item in raw.get("positions", [])]
        report = _json_value(engine.get_risk_report(positions))
        warnings = [] if mt5_state.get("connected") else ["MT5 desconectado; exposição real não confirmada."]
        return {"ok": True, "status": "AVAILABLE" if not warnings else "DEGRADED",
                "risk": report, "warnings": warnings, "timestamp": _timestamp()}
    except Exception as exc:
        return {"ok": True, "status": "DEGRADED", "risk": {},
                "warnings": [f"RiskEngine indisponível: {type(exc).__name__}"],
                "timestamp": _timestamp()}

