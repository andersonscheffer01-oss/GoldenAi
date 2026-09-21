from __future__ import annotations

import math
from statistics import mean, pstdev

from .models import MetricsResult, TradeRecord


def max_streak(values: list[bool]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def drawdown(equity_curve: list[dict]) -> tuple[float, float | None]:
    peak = None
    max_dd = 0.0
    max_dd_pct = 0.0
    for point in equity_curve:
        equity = float(point["equity"])
        peak = equity if peak is None else max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        if peak:
            max_dd_pct = max(max_dd_pct, dd / peak)
    return max_dd, max_dd_pct if peak else None


def calculate_metrics(trades: list[TradeRecord], equity_curve: list[dict]) -> MetricsResult:
    pnls = [float(trade.net_pnl) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    breakeven = [pnl for pnl in pnls if pnl == 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    total = len(pnls)
    max_dd, max_dd_pct = drawdown(equity_curve)
    returns = [float(trade.return_pct) for trade in trades]
    sharpe = None
    if len(returns) > 1 and pstdev(returns) > 0:
        sharpe = mean(returns) / pstdev(returns) * math.sqrt(len(returns))
    average_win = mean(wins) if wins else None
    average_loss = mean(losses) if losses else None
    payoff = abs(average_win / average_loss) if average_win is not None and average_loss not in (None, 0) else None
    expectancy = mean(pnls) if pnls else None
    profit_factor = gross_profit / abs(gross_loss) if gross_loss < 0 else (None if gross_profit == 0 else None)
    return MetricsResult(
        total_trades=total,
        wins=len(wins),
        losses=len(losses),
        breakeven=len(breakeven),
        win_rate=(len(wins) / total) if total else None,
        loss_rate=(len(losses) / total) if total else None,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=sum(pnls),
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=payoff,
        expectancy=expectancy,
        profit_factor=profit_factor,
        max_drawdown_abs=max_dd,
        max_drawdown_pct=max_dd_pct,
        consecutive_wins=max_streak([pnl > 0 for pnl in pnls]),
        consecutive_losses=max_streak([pnl < 0 for pnl in pnls]),
        average_trade=mean(pnls) if pnls else None,
        best_trade=max(pnls) if pnls else None,
        worst_trade=min(pnls) if pnls else None,
        sharpe_simplified=sharpe,
    )
