from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .data_validation import validate_ohlc_rows
from .metrics import calculate_metrics
from .models import BacktestResult, BacktestSpec, TradeRecord, deterministic_hash


def signal_for(strategy_id: str, row: dict[str, Any]) -> str | None:
    open_ = float(row["open"])
    close = float(row["close"])
    if strategy_id == "close_above_open":
        return "LONG" if close > open_ else None
    if strategy_id == "close_below_open":
        return "LONG" if close < open_ else None
    if strategy_id == "always_long":
        return "LONG"
    if strategy_id == "always_short":
        return "SHORT"
    if strategy_id == "never":
        return None
    raise ValueError(f"entry_logic_identifier nao suportado: {strategy_id}")


class BacktestEngine:
    def run(self, experiment_id: str, spec: BacktestSpec, rows: list[dict[str, Any]]) -> BacktestResult:
        validation = validate_ohlc_rows(rows)
        if not validation.ok:
            raise ValueError("; ".join(validation.errors))

        initial_capital = float(spec.initial_capital)
        equity = initial_capital
        equity_curve = [{"index": -1, "time": spec.dataset.start, "equity": equity, "drawdown": 0.0}]
        trades: list[TradeRecord] = []
        quantity = float(spec.position_sizing.get("quantity", 1.0))
        hold_bars = int(spec.strategy.parameters.get("hold_bars", 1))
        hold_bars = max(1, hold_bars)
        i = 0
        while i < len(rows) - hold_bars:
            signal_row = rows[i]
            side = signal_for(spec.strategy.entry_logic_identifier, signal_row)
            if not side:
                i += 1
                continue

            entry_index = i + 1
            exit_index = min(entry_index + hold_bars - 1, len(rows) - 1)
            entry_row = rows[entry_index]
            exit_row = rows[exit_index]
            entry_price = float(entry_row["open"])
            exit_price = float(exit_row["close"])
            direction = 1.0 if side == "LONG" else -1.0
            gross = (exit_price - entry_price) * direction * quantity
            costs = (spec.cost_model.total_round_turn_cost_per_unit() * quantity) + float(spec.cost_model.commission)
            net = gross - costs
            equity += net
            trade = TradeRecord(
                trade_id=f"{experiment_id}_T{len(trades)+1:05d}",
                experiment_id=experiment_id,
                symbol=spec.dataset.symbol,
                side=side,
                signal_time=str(signal_row["timestamp"]),
                entry_time=str(entry_row["timestamp"]),
                entry_price=entry_price,
                exit_time=str(exit_row["timestamp"]),
                exit_price=exit_price,
                quantity=quantity,
                gross_pnl=gross,
                costs=costs,
                net_pnl=net,
                return_pct=net / initial_capital if initial_capital else 0.0,
                exit_reason=f"hold_bars_{hold_bars}",
                bars_held=hold_bars,
            )
            trades.append(trade)
            peak = max(point["equity"] for point in equity_curve)
            equity_curve.append({
                "index": len(trades),
                "time": trade.exit_time,
                "equity": equity,
                "drawdown": max(0.0, peak - equity),
            })
            i = exit_index + 1

        metrics = calculate_metrics(trades, equity_curve)
        return BacktestResult(
            experiment_id=experiment_id,
            strategy_hash=spec.strategy.config_hash(),
            dataset_hash=spec.dataset.config_hash(),
            backtest_hash=spec.config_hash(),
            status="COMPLETED",
            trades=trades,
            metrics=metrics,
            equity_curve=equity_curve,
            warnings=validation.warnings,
            limitations=[
                "Resultados observados em backtest nao garantem resultados futuros.",
                "Convencao temporal: sinal no fechamento N, entrada em N+1.",
            ],
        )


def result_hash(result: BacktestResult) -> str:
    return deterministic_hash(asdict(result))
