#!/usr/bin/env python3
"""Teste de estrategias sobre o grafico do Golden AI."""

from datetime import datetime, timezone

from mt5_backtest import run_backtest
from strategy_engine import resolve_strategy


def _fmt_time(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d/%m %H:%M")
    except Exception:
        return ""


def test_strategy_on_chart(symbol="XAUUSD", timeframe="M15", strategy="SWING_TURTLE_BREAKOUT", count=320):
    symbol = str(symbol or "XAUUSD").strip().upper()
    timeframe = str(timeframe or "M15").strip().upper()
    strategy = str(strategy or "SWING_TURTLE_BREAKOUT").strip()
    count = max(120, min(int(count or 320), 5000))
    _, meta = resolve_strategy(strategy)
    result = run_backtest(
        strategy,
        symbol,
        timeframe,
        {
            "count": count,
            "balance": 10000,
            "lot": 0.01,
            "sl": 500,
            "tp": 1000,
            "include_all_trades": True,
        },
    )
    if not result.get("ok"):
        return result

    markers = []
    for idx, trade in enumerate(result.get("trades", []), start=1):
        entry_time = int(trade.get("entry_time") or trade.get("time") or 0)
        exit_time = int(trade.get("exit_time") or trade.get("time") or 0)
        markers.append(
            {
                "trade_no": idx,
                "entry_time": entry_time,
                "entry_label": _fmt_time(entry_time),
                "exit_time": exit_time,
                "exit_label": _fmt_time(exit_time),
                "type": trade.get("type"),
                "entry": trade.get("entry"),
                "exit": trade.get("exit"),
                "sl": trade.get("sl"),
                "tp": trade.get("tp"),
                "strategy_levels": trade.get("strategy_levels", []),
                "result": trade.get("result"),
                "pnl": trade.get("pnl"),
                "pnl_points": trade.get("pnl_points"),
            }
        )

    stats = result.get("stats", {})
    return {
        "ok": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": strategy,
        "strategy_name": stats.get("strategy_name") or meta.get("name", strategy),
        "engine_adapter": stats.get("engine_adapter"),
        "strategy_note": stats.get("strategy_note", ""),
        "stats": stats,
        "markers": markers,
        "tested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
