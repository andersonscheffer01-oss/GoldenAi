"""Deterministic replay coordinator and report contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .agents import build_default_agents
from .arena import GoldenScalperArena
from .journal import ArenaJournal
from .performance import rank_agents
from .virtual_execution import VirtualExecutionConfig


SECURITY = {
    "read_only": True,
    "simulation_only": True,
    "execution_authority": "NONE",
    "real_orders": False,
}


@dataclass(frozen=True, slots=True)
class ReplayResult:
    report: dict

    def as_dict(self) -> dict:
        return self.report


def run_replay(snapshots, agents: Mapping[str, object] | None = None,
               execution_config: VirtualExecutionConfig | None = None,
               journal_path=None, strategy_version: str = "arena-v2",
               source_kind: str = "REPLAY", provenance: str = "validated replay input") -> ReplayResult:
    snapshots = tuple(snapshots)
    if not snapshots:
        raise ValueError("SNAPSHOTS_REQUIRED")
    if any(snapshot.run_id != snapshots[0].run_id for snapshot in snapshots):
        raise ValueError("RUN_ID_CHANGED")
    agents = dict(agents or build_default_agents())
    journal = ArenaJournal(journal_path) if journal_path is not None else None
    arena = GoldenScalperArena(
        agents=agents,
        execution_config=execution_config or VirtualExecutionConfig(),
        journal=journal,
        strategy_version=strategy_version,
    )
    arena.run(snapshots, finalize=True)
    execution = arena.execution
    assert execution is not None
    grouped = {
        name: [trade.as_dict() for trade in execution.trades(name)]
        for name in agents
    }
    ranked = rank_agents(
        grouped,
        initial_balance=execution.config.initial_balance,
        tick_size=execution.spec.tick_size,
    )
    for row in ranked:
        row["trades_detail"] = grouped[row["agent"]]
        state = execution.portfolios.get(row["agent"])
        row["balance"] = round(state.balance, 10) if state else execution.config.initial_balance
    all_trades = [trade for rows in grouped.values() for trade in rows]
    all_trades.sort(key=lambda row: float(row.get("net_pnl") or 0.0), reverse=True)
    report = {
        "schema_version": "golden-scalper-arena-report-v1",
        "run": {
            "run_id": snapshots[0].run_id,
            "symbol": snapshots[0].spec.symbol,
            "strategy_version": str(strategy_version),
            "snapshot_count": len(snapshots),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "SIMULATION",
            "source_kind": str(source_kind),
            "provenance": str(provenance),
        },
        "security": dict(SECURITY),
        "configuration": {
            "initial_balance": execution.config.initial_balance,
            "risk_per_trade": execution.config.risk_per_trade,
            "daily_loss_limit": execution.config.daily_loss_limit,
            "max_positions": execution.config.max_positions,
            "slippage_points": execution.config.slippage_points,
            "latency_points_proxy": execution.config.latency_points,
            "max_duration_seconds": execution.config.max_duration.total_seconds(),
        },
        "agents": ranked,
        "top_trades": all_trades[:5],
        "validation": {
            "status": "NOT_VALIDATED",
            "winner": None,
            "reason": "Replay isolado; critérios walk-forward/OOS ainda não aprovam vencedor.",
            "walk_forward": None,
            "out_of_sample": None,
            "stress": None,
            "paper_sessions": None,
        },
        "warnings": [
            "Resultados são de simulação e não comprovam rentabilidade real.",
            "Nenhum agente recebe autoridade de execução financeira.",
        ],
    }
    if journal is not None:
        report["run"]["journal_path"] = str(Path(journal.path))
    return ReplayResult(report)


__all__ = ["ReplayResult", "SECURITY", "run_replay"]

