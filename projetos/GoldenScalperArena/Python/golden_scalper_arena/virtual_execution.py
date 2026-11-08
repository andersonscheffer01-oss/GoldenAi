"""Virtual-only execution and risk engine for the Golden Scalper Arena."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from .contracts import (
    MarketSnapshot,
    PortfolioState,
    Side,
    StrategySignal,
    TradeRecord,
    VirtualPosition,
)


@dataclass(frozen=True, slots=True)
class VirtualExecutionConfig:
    initial_balance: float = 10_000.0
    risk_per_trade: float = 0.0025
    daily_loss_limit: float = 0.015
    max_positions: int = 1
    slippage_points: float = 0.0
    commission_per_volume: float = 0.0
    latency_points: float = 0.0
    max_duration: timedelta = timedelta(seconds=90)

    def __post_init__(self) -> None:
        if self.initial_balance <= 0:
            raise ValueError("INITIAL_BALANCE_INVALID")
        if not 0 < self.risk_per_trade <= 1:
            raise ValueError("RISK_PER_TRADE_INVALID")
        if not 0 < self.daily_loss_limit <= 1:
            raise ValueError("DAILY_LOSS_LIMIT_INVALID")
        if self.max_positions < 1:
            raise ValueError("MAX_POSITIONS_INVALID")
        if self.slippage_points < 0 or self.commission_per_volume < 0 or self.latency_points < 0:
            raise ValueError("EXECUTION_COST_INVALID")


@dataclass(frozen=True, slots=True)
class OpenResult:
    accepted: bool
    reason: str
    position: VirtualPosition | None = None


class VirtualExecution:
    """Owns only virtual portfolios; it has no MetaTrader execution path."""

    def __init__(self, spec, config: VirtualExecutionConfig | None = None):
        self.spec = spec
        self.config = config or VirtualExecutionConfig()
        self.portfolios: dict[str, PortfolioState] = {}
        self._signal_reasons: dict[str, str] = {}

    def _state(self, agent: str, timestamp=None) -> PortfolioState:
        key = str(agent or "").strip().lower()
        if not key:
            raise ValueError("AGENT_REQUIRED")
        state = self.portfolios.get(key)
        if state is None:
            state = PortfolioState(key, self.config.initial_balance, self.config.initial_balance)
            self.portfolios[key] = state
        if timestamp is not None:
            day = timestamp.date().isoformat()
            if state.current_day and state.current_day != day:
                state.daily_realized_pnl = 0.0
            state.current_day = day
        return state

    def portfolio_view(self, agent: str) -> dict:
        state = self._state(agent)
        return {
            "agent": state.agent, "balance": state.balance,
            "initial_balance": state.initial_balance,
            "daily_realized_pnl": state.daily_realized_pnl,
            "open_position": state.open_position,
            "closed_trades": tuple(state.closed_trades),
        }

    def open(self, agent: str, snapshot: MarketSnapshot, signal: StrategySignal) -> OpenResult:
        state = self._state(agent, snapshot.timestamp)
        if state.open_position is not None:
            return OpenResult(False, "POSITION_ALREADY_OPEN")
        if not signal.data_valid:
            return OpenResult(False, "SIGNAL_DATA_INVALID")
        if signal.observed_event_index > snapshot.event_index:
            return OpenResult(False, "LOOKAHEAD_SIGNAL")
        if state.daily_realized_pnl <= -(state.initial_balance * self.config.daily_loss_limit):
            return OpenResult(False, "DAILY_LOSS_LIMIT")
        if signal.agent != state.agent:
            return OpenResult(False, "SIGNAL_AGENT_MISMATCH")

        slippage = (self.config.slippage_points + self.config.latency_points) * self.spec.point
        entry = (snapshot.tick.ask + slippage if signal.side is Side.BUY
                 else snapshot.tick.bid - slippage)
        stop = signal.stop_price
        take = signal.take_price
        if stop is None or take is None:
            return OpenResult(False, "STOP_AND_TAKE_REQUIRED")
        if signal.side is Side.BUY and not (stop < entry < take):
            return OpenResult(False, "BUY_LEVELS_INVALID")
        if signal.side is Side.SELL and not (take < entry < stop):
            return OpenResult(False, "SELL_LEVELS_INVALID")

        volume = signal.volume
        if volume is None:
            risk_budget = state.balance * self.config.risk_per_trade
            risk_per_volume = abs(entry - float(stop)) / self.spec.tick_size * self.spec.tick_value
            if risk_per_volume <= 0:
                return OpenResult(False, "RISK_DISTANCE_INVALID")
            volume = self.spec.normalize_volume(risk_budget / risk_per_volume)
        else:
            volume = self.spec.normalize_volume(volume)
        if volume <= 0:
            return OpenResult(False, "VOLUME_BELOW_MINIMUM")
        risk_amount = abs(entry - float(stop)) / self.spec.tick_size * self.spec.tick_value * volume
        if risk_amount > state.balance * self.config.risk_per_trade * 1.02:
            return OpenResult(False, "RISK_BUDGET_EXCEEDED")
        position = VirtualPosition(
            agent=state.agent, side=signal.side, volume=volume,
            entry_price=entry, stop_price=float(stop), take_price=float(take),
            opened_event_index=snapshot.event_index, opened_at=snapshot.timestamp,
            risk_amount=risk_amount, entry_spread=snapshot.tick.spread,
            slippage_points=self.config.slippage_points + self.config.latency_points,
        )
        state.open_position = position
        self._signal_reasons[state.agent] = signal.reason
        return OpenResult(True, "OPENED", position)

    def on_tick(self, snapshot: MarketSnapshot) -> list[TradeRecord]:
        closed: list[TradeRecord] = []
        for state in tuple(self.portfolios.values()):
            position = state.open_position
            if position is None:
                continue
            exit_reason = ""
            if position.side is Side.BUY:
                if snapshot.tick.bid <= position.stop_price:
                    exit_price, exit_reason = snapshot.tick.bid - self.config.slippage_points * self.spec.point, "STOP_LOSS"
                elif snapshot.tick.bid >= position.take_price:
                    exit_price, exit_reason = snapshot.tick.bid - self.config.slippage_points * self.spec.point, "TAKE_PROFIT"
                elif snapshot.timestamp - position.opened_at >= self.config.max_duration:
                    exit_price, exit_reason = snapshot.tick.bid - self.config.slippage_points * self.spec.point, "TIME_EXIT"
            else:
                if snapshot.tick.ask >= position.stop_price:
                    exit_price, exit_reason = snapshot.tick.ask + self.config.slippage_points * self.spec.point, "STOP_LOSS"
                elif snapshot.tick.ask <= position.take_price:
                    exit_price, exit_reason = snapshot.tick.ask + self.config.slippage_points * self.spec.point, "TAKE_PROFIT"
                elif snapshot.timestamp - position.opened_at >= self.config.max_duration:
                    exit_price, exit_reason = snapshot.tick.ask + self.config.slippage_points * self.spec.point, "TIME_EXIT"
            if exit_reason:
                trade = self._close(state, snapshot, float(exit_price), exit_reason)
                closed.append(trade)
        return closed

    def _close(self, state, snapshot, exit_price: float, reason: str) -> TradeRecord:
        position = state.open_position
        assert position is not None
        direction = 1 if position.side is Side.BUY else -1
        gross = ((exit_price - position.entry_price) / self.spec.tick_size
                 * self.spec.tick_value * position.volume * direction)
        costs = self.config.commission_per_volume * position.volume * 2
        net = gross - costs
        trade = TradeRecord(
            run_id=snapshot.run_id, agent=state.agent, side=position.side,
            volume=position.volume, entry_price=position.entry_price,
            exit_price=exit_price, opened_event_index=position.opened_event_index,
            closed_event_index=snapshot.event_index, opened_at=position.opened_at,
            closed_at=snapshot.timestamp, gross_pnl=gross, costs=costs,
            net_pnl=net, exit_reason=reason,
            signal_reason=self._signal_reasons.pop(state.agent, ""),
            risk_amount=position.risk_amount, entry_spread=position.entry_spread,
            slippage_points=position.slippage_points,
        )
        state.balance += net
        state.daily_realized_pnl += net
        state.closed_trades.append(trade)
        state.open_position = None
        return trade

    def trades(self, agent: str | None = None) -> tuple[TradeRecord, ...]:
        rows = []
        states = (self.portfolios.get(str(agent).strip().lower()),) if agent else self.portfolios.values()
        for state in states:
            if state is not None:
                rows.extend(state.closed_trades)
        return tuple(rows)

    def close_all(self, snapshot: MarketSnapshot, reason: str = "END_OF_RUN") -> list[TradeRecord]:
        """Close every open virtual position at the observable opposite quote."""
        closed: list[TradeRecord] = []
        for state in tuple(self.portfolios.values()):
            if state.open_position is None:
                continue
            position = state.open_position
            exit_price = (
                snapshot.tick.bid - self.config.slippage_points * self.spec.point
                if position.side is Side.BUY
                else snapshot.tick.ask + self.config.slippage_points * self.spec.point
            )
            closed.append(self._close(state, snapshot, float(exit_price), reason))
        return closed


__all__ = ["OpenResult", "VirtualExecution", "VirtualExecutionConfig"]


