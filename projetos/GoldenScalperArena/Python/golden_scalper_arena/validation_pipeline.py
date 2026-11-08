"""Compose replay, temporal validation, cost stress and paper sessions."""

from __future__ import annotations

from pathlib import Path

from .agents import build_default_agents
from .replay import run_replay
from .robustness import run_cost_stress
from .session import run_paper_session
from .virtual_execution import VirtualExecutionConfig
from .walk_forward import build_walk_forward_plan, run_walk_forward


def _evaluation(train, test, is_oos, agents, config):
    if not test:
        return {"status": "NO_TEST_DATA", "is_oos": is_oos}
    report = run_replay(
        test, agents=agents, execution_config=config,
        strategy_version="arena-validation-v1", source_kind="VALIDATION_REPLAY",
        provenance="chronological test slice; no parameter fitting",
    ).as_dict()
    return {
        "status": "COMPUTED",
        "is_oos": bool(is_oos),
        "snapshots": len(test),
        "net_pnl_by_agent": {
            row["agent"]: row["metrics"]["net_pnl"] for row in report["agents"]
        },
    }


def run_validation_pipeline(snapshots, agents=None, execution_config=None,
                            journal_path=None, source_kind: str = "REPLAY",
                            provenance: str = "validated replay input",
                            train_size: int = 20, test_size: int = 10,
                            step: int = 10, oos_size: int = 20,
                            paper_session_count: int = 3) -> dict:
    snapshots = tuple(snapshots)
    agents = dict(agents or build_default_agents())
    config = execution_config or VirtualExecutionConfig()
    base = run_replay(
        snapshots, agents=agents, execution_config=config, journal_path=journal_path,
        strategy_version="arena-v2", source_kind=source_kind, provenance=provenance,
    ).as_dict()
    validation = {
        "status": "NOT_VALIDATED",
        "winner": None,
        "reason": "Critérios preliminares não transformam um replay sintético em validação de rentabilidade.",
        "criteria": {
            "oos_profit_factor_min": 1.20,
            "positive_net_expectancy": True,
            "drawdown_within_config": True,
            "stress_no_collapse": True,
            "paper_execution_faults": 0,
        },
        "walk_forward": None,
        "out_of_sample": None,
        "stress": None,
        "paper_sessions": [],
    }
    try:
        plan = build_walk_forward_plan(
            snapshots, train_size=train_size, test_size=test_size,
            step=step, oos_size=oos_size,
        )
        wf = run_walk_forward(
            plan, lambda train, test, is_oos: _evaluation(
                train, test, is_oos, agents, config
            ),
        )
        validation["walk_forward"] = {
            "status": wf["status"],
            "windows": wf["windows"],
            "window_count": len(wf["windows"]),
        }
        validation["out_of_sample"] = wf["oos"]
    except ValueError as exc:
        validation["walk_forward"] = {"status": "INSUFFICIENT_DATA", "reason": str(exc)}

    validation["stress"] = run_cost_stress(
        snapshots, agents, config, multipliers=(1.0, 1.5, 2.0), latency_points=1.0,
    )
    if paper_session_count > 0 and snapshots:
        size = max(1, len(snapshots) // paper_session_count)
        for index in range(paper_session_count):
            start = index * size
            end = len(snapshots) if index == paper_session_count - 1 else min(len(snapshots), start + size)
            if start >= len(snapshots):
                break
            paper = run_paper_session(
                snapshots[start:end], agents=agents,
                session_id=f"paper-{index + 1:02d}", execution_config=config,
            )
            validation["paper_sessions"].append({
                "session_id": paper["session_id"],
                "status": paper["status"],
                "execution_authority": paper["execution_authority"],
                "snapshots": end - start,
            })
    base["validation"] = validation
    base["run"]["validation_mode"] = "COMPUTED_PIPELINE"
    base["warnings"].append("A validação exibida só será aprovada após dados reais suficientes e OOS intocado.")
    return base


def write_report(report: dict, path) -> Path:
    import json

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


__all__ = ["run_validation_pipeline", "write_report"]

