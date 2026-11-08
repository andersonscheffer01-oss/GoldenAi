"""Prospective paper-session wrapper with no broker execution path."""

from __future__ import annotations

from .replay import run_replay


def run_paper_session(snapshots, agents=None, session_id: str = "paper-session",
                      execution_config=None) -> dict:
    report = run_replay(
        snapshots, agents=agents, execution_config=execution_config,
        strategy_version="arena-paper-v1", source_kind="PAPER_SIMULATION",
        provenance="prospective replay input; no broker orders",
    ).as_dict()
    return {
        "session_id": str(session_id),
        "status": "SIMULATED_PAPER",
        "execution_authority": "NONE",
        "read_only": True,
        "simulation_only": True,
        "report": report,
    }


__all__ = ["run_paper_session"]

