"""Read-only adapters over the existing MT5 and Golden implementations.

This module deliberately imports the legacy integrations lazily.  The Jarvis
ToolRegistry remains the only execution boundary; these adapters only read
terminal, scanner and risk state and return JSON-safe dictionaries.
"""
from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_TERMINAL_PATHS = (
    Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
    Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\terminal64.exe"),
)
_TIMEFRAMES = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5",
               "M15": "TIMEFRAME_M15", "H1": "TIMEFRAME_H1",
               "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1"}
_MAX_CANDLES = 200
_MAX_RESULTS = 10


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
        "ok": True,
        "status": "DISABLED_BY_PROFILE" if disabled else "OFFLINE",
        "connected": False,
        "reason": str(reason or "MT5 desconectado"),
        "availability": "SOURCE_DISABLED" if disabled else "OFFLINE",
        "timestamp": _timestamp(),
        **extra,
    }


def _terminal_available() -> bool:
    return any(path.is_file() for path in _TERMINAL_PATHS)


def _connection() -> tuple[Any, Any, Any, str]:
    """Return the existing MT5 client, terminal, account and error reason."""
    try:
        from jarvis_core.runtime_profile import active_runtime_profile
        if not active_runtime_profile().mt5_enabled:
            return None, None, None, "SOURCE_DISABLED: MT5_DISABLED_BY_PROFILE"
        import MetaTrader5 as mt5
        from mt5_connector import ensure_connection

        connected = bool(ensure_connection())
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if not connected or not terminal or not getattr(terminal, "connected", False):
            return mt5, terminal, account, "MT5 desconectado"
        return mt5, terminal, account, ""
    except Exception as exc:
        return None, None, None, f"MT5 indisponível: {type(exc).__name__}"


def mt5_status() -> dict[str, Any]:
    mt5, terminal, account, reason = _connection()
    if reason:
        return _offline(reason, terminal_available=bool(terminal) or _terminal_available(),
                        account_available=bool(account), server=_field(account, "server"))
    return {
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
    return {
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
        return {"ok": True, "status": "CONNECTED", "positions": positions,
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
        return {"ok": True, "status": "CONNECTED", "orders": orders,
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
        return {"ok": True, "status": "NOT_FOUND", "requested_symbol": symbol,
                "suggestions": suggestions, "reason": resolve_error,
                "timestamp": _timestamp()}
    try:
        info, tick = mt5.symbol_info(resolved), mt5.symbol_info_tick(resolved)
        if tick is None:
            return {"ok": True, "status": "DEGRADED", "symbol": resolved,
                    "reason": "Tick indisponível", "timestamp": _timestamp()}
        bid, ask = float(tick.bid or 0), float(tick.ask or 0)
        point = float(_field(info, "point", 0) or 0)
        return {"ok": True, "status": "CONNECTED", "symbol": resolved,
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
        return {"ok": True, "status": "NOT_FOUND", "requested_symbol": symbol,
                "suggestions": suggestions, "reason": resolve_error,
                "timestamp": _timestamp()}
    try:
        info = mt5.symbol_info(resolved)
        return {"ok": True, "status": "CONNECTED", "symbol": resolved,
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
        return {"ok": True, "status": "NOT_FOUND", "requested_symbol": symbol,
                "timeframe": timeframe, "suggestions": suggestions,
                "reason": resolve_error, "candles": [], "timestamp": _timestamp()}
    constant_name = _TIMEFRAMES.get(timeframe)
    if not constant_name or not hasattr(mt5, constant_name):
        return {"ok": True, "status": "INVALID_TIMEFRAME", "symbol": resolved,
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
        return {"ok": True, "status": "CONNECTED", "symbol": resolved,
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
