"""Coordinator for independent simulation agents."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .contracts import MarketSnapshot, StrategySignal
from .validation import validate_ticks
from .virtual_execution import VirtualExecution, VirtualExecutionConfig


class GoldenScalperArena:
    """Broadcasts one immutable snapshot to isolated virtual portfolios."""

    def __init__(self, agents: Mapping[str, Callable], execution_config=None,
                 journal=None, strategy_version: str = "arena-v2"):
        if not agents:
            raise ValueError("AGENTS_REQUIRED")
        self.agents = {str(name).strip().lower(): callback for name, callback in agents.items()}
        if any(not name or not callable(callback) for name, callback in self.agents.items()):
            raise ValueError("AGENT_CALLBACK_INVALID")
        self.execution_config = execution_config or VirtualExecutionConfig()
        self.journal = journal
        self.strategy_version = str(strategy_version)
        self._journal_started = False
        self.execution: VirtualExecution | None = None
        self.last_snapshot: MarketSnapshot | None = None
        self.last_signals: dict[str, StrategySignal | None] = {}
        self.last_closed_trades = []

    def _ensure_execution(self, snapshot: MarketSnapshot) -> VirtualExecution:
        if self.execution is None:
            self.execution = VirtualExecution(snapshot.spec, self.execution_config)
            if self.journal is not None and not self._journal_started:
                self.journal.start_run(snapshot.run_id, snapshot.spec.symbol, self.strategy_version)
                self._journal_started = True
        elif self.execution.spec != snapshot.spec:
            raise ValueError("SYMBOL_SPEC_CHANGED")
        return self.execution

    @property
    def portfolios(self):
        return self.execution.portfolios if self.execution else {}

    def step(self, snapshot: MarketSnapshot) -> dict:
        execution = self._ensure_execution(snapshot)
        if self.last_snapshot is not None:
            validate_ticks((self.last_snapshot.tick, snapshot.tick), snapshot.spec.symbol)
            if snapshot.run_id != self.last_snapshot.run_id:
                raise ValueError("RUN_ID_CHANGED")
        self.last_closed_trades = execution.on_tick(snapshot)
        if self.journal is not None:
            for trade in self.last_closed_trades:
                self.journal.record_trade(snapshot.run_id, trade.as_dict())
        self.last_snapshot = snapshot
        signals = {}
        # Every callback sees the exact same immutable object. Signals are
        # collected before any new position is opened, so no agent can observe
        # another agent's decision during the official competition.
        for name, callback in self.agents.items():
            view = execution.portfolio_view(name)
            signal = callback(snapshot, view)
            if signal is not None and not isinstance(signal, StrategySignal):
                raise TypeError("AGENT_MUST_RETURN_STRATEGY_SIGNAL_OR_NONE")
            if signal is not None and signal.agent != name:
                raise ValueError("SIGNAL_AGENT_MISMATCH")
            signals[name] = signal
            if self.journal is not None and signal is not None:
                self.journal.record_signal(
                    snapshot.run_id, name, snapshot.event_index, signal.as_dict()
                )
        self.last_signals = signals
        results = {}
        for name, signal in signals.items():
            results[name] = execution.open(name, snapshot, signal) if signal else None
        return results

    def finalize(self, snapshot: MarketSnapshot | None = None) -> list:
        """Close remaining positions at the last observable quote."""
        if self.execution is None:
            return []
        snapshot = snapshot or self.last_snapshot
        if snapshot is None:
            return []
        closed = self.execution.close_all(snapshot)
        self.last_closed_trades = closed
        if self.journal is not None:
            for trade in closed:
                self.journal.record_trade(snapshot.run_id, trade.as_dict())
        return closed

    def run(self, snapshots, finalize: bool = False):
        snapshots = tuple(snapshots)
        results = [self.step(snapshot) for snapshot in snapshots]
        if finalize and snapshots:
            self.finalize(snapshots[-1])
        return results


__all__ = ["GoldenScalperArena"]


