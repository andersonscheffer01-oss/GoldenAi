"""Deterministic, read-only strategy agents for the simulation arena.

The agents intentionally consume only closed bars and the current Bid/Ask. They
are research rules, not validated investment advice and not live trading code.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import MarketSnapshot, Side, StrategySignal


def _bars(snapshot: MarketSnapshot, timeframe: str, minimum: int) -> tuple:
    rows = tuple(snapshot.closed_bars.get(timeframe, ()))
    return rows if len(rows) >= minimum else ()


def _atr(rows: tuple, length: int = 5) -> float:
    sample = rows[-length:]
    if not sample:
        return 0.0
    return sum(max(bar.high - bar.low, abs(bar.high - bar.close), abs(bar.low - bar.close))
               for bar in sample) / len(sample)


def _signal(snapshot: MarketSnapshot, name: str, side: Side, distance: float,
            reason: str, confidence: float | None = None) -> StrategySignal:
    distance = max(float(distance), snapshot.spec.point * 5)
    if side is Side.BUY:
        entry = snapshot.tick.ask
        stop, take = entry - distance, entry + distance * 1.5
    else:
        entry = snapshot.tick.bid
        stop, take = entry + distance, entry - distance * 1.5
    return StrategySignal(
        agent=name, side=side, stop_price=stop, take_price=take,
        observed_event_index=snapshot.event_index, reason=reason,
        confidence=confidence,
    )


@dataclass(frozen=True, slots=True)
class MomentumAgent:
    name: str = "momentum"

    def __call__(self, snapshot: MarketSnapshot, _portfolio: dict) -> StrategySignal | None:
        rows = _bars(snapshot, "M1", 5)
        if not rows:
            return None
        atr = _atr(rows)
        if atr <= 0:
            return None
        movement = rows[-1].close - rows[-4].close
        current_delta = snapshot.tick.bid - rows[-1].close
        threshold = max(snapshot.spec.point * 3, atr * 0.5)
        if threshold <= abs(movement) <= atr * 3 and movement > 0 and current_delta >= -atr * 0.2:
            return _signal(snapshot, self.name, Side.BUY, atr * 0.8,
                           "momentum_acceleration_confirmed", 65.0)
        if threshold <= abs(movement) <= atr * 3 and movement < 0 and current_delta <= atr * 0.2:
            return _signal(snapshot, self.name, Side.SELL, atr * 0.8,
                           "momentum_acceleration_confirmed", 65.0)
        return None


@dataclass(frozen=True, slots=True)
class DefenseAgent:
    name: str = "defense"

    def __call__(self, snapshot: MarketSnapshot, _portfolio: dict) -> StrategySignal | None:
        rows = _bars(snapshot, "M1", 3)
        if not rows:
            return None
        lower = 0
        upper = 0
        for bar in rows[-3:]:
            span = max(bar.high - bar.low, snapshot.spec.point)
            body_floor = min(bar.open, bar.close)
            body_ceiling = max(bar.open, bar.close)
            if (body_floor - bar.low) / span >= 0.45:
                lower += 1
            if (bar.high - body_ceiling) / span >= 0.45:
                upper += 1
        atr = _atr(rows)
        if atr <= 0:
            return None
        if lower >= 2 and lower > upper and snapshot.tick.bid > min(bar.low for bar in rows[-3:]):
            return _signal(snapshot, self.name, Side.BUY, atr * 0.8,
                           "repeated_lower_rejection_absorption_inferred", 58.0)
        if upper >= 2 and upper > lower and snapshot.tick.ask < max(bar.high for bar in rows[-3:]):
            return _signal(snapshot, self.name, Side.SELL, atr * 0.8,
                           "repeated_upper_rejection_absorption_inferred", 58.0)
        return None


@dataclass(frozen=True, slots=True)
class BreakoutAgent:
    name: str = "breakout"

    def __call__(self, snapshot: MarketSnapshot, _portfolio: dict) -> StrategySignal | None:
        rows = _bars(snapshot, "M1", 6)
        if not rows:
            return None
        previous = rows[-6:-1]
        last = rows[-1]
        upper = max(bar.high for bar in previous)
        lower = min(bar.low for bar in previous)
        range_size = max(upper - lower, snapshot.spec.point)
        margin = max(snapshot.spec.point * 2, range_size * 0.1)
        atr = _atr(previous)
        if last.close > upper + margin and snapshot.tick.ask >= last.close:
            return _signal(snapshot, self.name, Side.BUY, max(atr * 0.8, range_size * 0.35),
                           "structural_breakout_persistent", 62.0)
        if last.close < lower - margin and snapshot.tick.bid <= last.close:
            return _signal(snapshot, self.name, Side.SELL, max(atr * 0.8, range_size * 0.35),
                           "structural_breakout_persistent", 62.0)
        return None


@dataclass(frozen=True, slots=True)
class PullbackAgent:
    name: str = "pullback"

    def __call__(self, snapshot: MarketSnapshot, _portfolio: dict) -> StrategySignal | None:
        htf = _bars(snapshot, "H1", 3)
        rows = _bars(snapshot, "M1", 3)
        if not htf or not rows:
            return None
        atr = _atr(rows)
        if atr <= 0:
            return None
        trend = htf[-1].close - htf[0].close
        first, middle, last = rows[-3:]
        if trend > 0 and first.close > middle.close and last.close > middle.close and last.close >= first.close:
            return _signal(snapshot, self.name, Side.BUY, atr * 0.9,
                           "higher_timeframe_trend_pullback_recovered", 60.0)
        if trend < 0 and first.close < middle.close and last.close < middle.close and last.close <= first.close:
            return _signal(snapshot, self.name, Side.SELL, atr * 0.9,
                           "higher_timeframe_trend_pullback_recovered", 60.0)
        return None


@dataclass(frozen=True, slots=True)
class LiquiditySweepAgent:
    name: str = "liquidity"

    def __call__(self, snapshot: MarketSnapshot, _portfolio: dict) -> StrategySignal | None:
        rows = _bars(snapshot, "M1", 3)
        if not rows:
            return None
        previous = rows[:-1]
        last = rows[-1]
        prior_low = min(bar.low for bar in previous)
        prior_high = max(bar.high for bar in previous)
        atr = _atr(rows)
        if atr <= 0:
            return None
        if last.low < prior_low - snapshot.spec.point and last.close > prior_low and snapshot.tick.bid >= last.close:
            return _signal(snapshot, self.name, Side.BUY, atr * 0.9,
                           "observable_low_sweep_return_inferred", 56.0)
        if last.high > prior_high + snapshot.spec.point and last.close < prior_high and snapshot.tick.ask <= last.close:
            return _signal(snapshot, self.name, Side.SELL, atr * 0.9,
                           "observable_high_sweep_return_inferred", 56.0)
        return None


def build_default_agents() -> dict[str, object]:
    """Return fresh independent instances in the official competition order."""
    return {
        "momentum": MomentumAgent(),
        "defense": DefenseAgent(),
        "breakout": BreakoutAgent(),
        "pullback": PullbackAgent(),
        "liquidity": LiquiditySweepAgent(),
    }


__all__ = [
    "BreakoutAgent", "DefenseAgent", "LiquiditySweepAgent", "MomentumAgent",
    "PullbackAgent", "build_default_agents",
]

