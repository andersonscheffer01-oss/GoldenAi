"""Explicit net-performance metrics for virtual trade records."""

from __future__ import annotations

from datetime import datetime


def _row(value) -> dict:
    return value if isinstance(value, dict) else value.as_dict()


def _timestamp(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def summarize_trades(trades, initial_balance: float = 10_000.0,
                     tick_size: float = 1.0) -> dict:
    rows = [_row(trade) for trade in (trades or ())]
    pnl = [float(row.get("net_pnl") or 0.0) for row in rows]
    costs = sum(float(row.get("costs") or 0.0) for row in rows)
    winners = [value for value in pnl if value > 0]
    losers = [value for value in pnl if value < 0]
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    balance = 0.0
    peak = 0.0
    max_drawdown = 0.0
    current_drawdown_trades = 0
    max_drawdown_trades = 0
    recovery_start = None
    max_recovery_seconds = 0.0
    for index, value in enumerate(pnl):
        balance += value
        if balance >= peak:
            if recovery_start is not None and rows:
                recovered_at = _timestamp(rows[index].get("closed_at"))
                if recovered_at is not None:
                    max_recovery_seconds = max(
                        max_recovery_seconds,
                        (recovered_at - recovery_start).total_seconds(),
                    )
            peak = balance
            current_drawdown_trades = 0
            recovery_start = None
        else:
            current_drawdown_trades += 1
            if recovery_start is None:
                recovery_start = _timestamp(rows[index].get("closed_at"))
            if peak - balance > max_drawdown:
                max_drawdown = peak - balance
                max_drawdown_trades = current_drawdown_trades

    max_win_streak = max_loss_streak = win_streak = loss_streak = 0
    for value in pnl:
        if value > 0:
            win_streak += 1
            loss_streak = 0
        elif value < 0:
            loss_streak += 1
            win_streak = 0
        else:
            win_streak = loss_streak = 0
        max_win_streak = max(max_win_streak, win_streak)
        max_loss_streak = max(max_loss_streak, loss_streak)

    point_rows = []
    for row in rows:
        entry = row.get("entry_price")
        exit_ = row.get("exit_price")
        if entry is None or exit_ is None:
            continue
        direction = 1 if str(row.get("side", "BUY")).upper() == "BUY" else -1
        point_rows.append((float(exit_) - float(entry)) * direction / float(tick_size))
    winning_points = sum(value for value in point_rows if value > 0)
    losing_points = abs(sum(value for value in point_rows if value < 0))
    holding = []
    for row in rows:
        opened = _timestamp(row.get("opened_at"))
        closed = _timestamp(row.get("closed_at"))
        if opened is not None and closed is not None:
            holding.append(max(0.0, (closed - opened).total_seconds()))

    return {
        "trades": len(rows),
        "net_pnl": round(sum(pnl), 10),
        "gross_profit": round(gross_profit, 10),
        "gross_loss": round(gross_loss, 10),
        "costs": round(costs, 10),
        "win_rate": round((len(winners) / len(rows) * 100) if rows else 0.0, 4),
        "profit_factor": round(gross_profit / gross_loss, 10) if gross_loss else None,
        "expectancy": round(sum(pnl) / len(pnl), 10) if pnl else 0.0,
        "payoff": round((sum(winners) / len(winners)) / (gross_loss / len(losers)), 10)
        if winners and losers else None,
        "net_pnl_pct": round((sum(pnl) / initial_balance * 100) if initial_balance else 0.0, 10),
        "max_drawdown": round(max_drawdown, 10),
        "max_drawdown_pct": round((max_drawdown / initial_balance * 100) if initial_balance else 0.0, 10),
        "max_drawdown_trades": max_drawdown_trades,
        "max_recovery_seconds": round(max_recovery_seconds, 4),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "net_points": round(sum(point_rows), 10),
        "gross_points": round(winning_points, 10),
        "losing_points": round(losing_points, 10),
        "avg_holding_seconds": round(sum(holding) / len(holding), 4) if holding else 0.0,
        "max_holding_seconds": round(max(holding), 4) if holding else 0.0,
        "initial_balance": float(initial_balance),
    }


def rank_agents(agent_trades: dict[str, list], initial_balance: float = 10_000.0,
                tick_size: float = 1.0) -> list[dict]:
    rows = []
    for agent, trades in agent_trades.items():
        metrics = summarize_trades(trades, initial_balance, tick_size)
        rows.append({"agent": agent, "metrics": metrics})
    rows.sort(key=lambda item: (
        item["metrics"]["net_pnl"],
        item["metrics"]["profit_factor"] if item["metrics"]["profit_factor"] is not None else -1,
        -item["metrics"]["max_drawdown"],
    ), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


__all__ = ["rank_agents", "summarize_trades"]

