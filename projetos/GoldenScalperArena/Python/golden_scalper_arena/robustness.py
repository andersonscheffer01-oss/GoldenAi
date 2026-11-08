"""Cost and adverse-fill stress tests over the same replay input."""

from __future__ import annotations

from dataclasses import replace

from .replay import run_replay


def run_cost_stress(snapshots, agents, base_config, multipliers=(1.0, 1.5, 2.0),
                    latency_points: float = 0.0) -> dict:
    scenarios = []
    for multiplier in tuple(float(value) for value in multipliers):
        if multiplier <= 0:
            raise ValueError("STRESS_MULTIPLIER_INVALID")
        config = replace(
            base_config,
            slippage_points=base_config.slippage_points * multiplier,
            commission_per_volume=base_config.commission_per_volume * multiplier,
            latency_points=latency_points * multiplier,
        )
        result = run_replay(
            snapshots, agents=agents, execution_config=config,
            strategy_version="arena-stress-v1", source_kind="STRESS_SIMULATION",
            provenance="replay with adverse spread/slippage cost multiplier",
        ).as_dict()
        scenarios.append({
            "spread_multiplier": multiplier,
            "slippage_points": config.slippage_points,
            "latency_points_proxy": config.latency_points,
            "execution_authority": "NONE",
            "net_pnl_by_agent": {
                row["agent"]: row["metrics"]["net_pnl"] for row in result["agents"]
            },
            "status": "SIMULATED",
        })
    return {
        "status": "COMPUTED",
        "scenarios": scenarios,
        "warning": "Latency is represented by an adverse price-points proxy in this replay.",
        "execution_authority": "NONE",
    }


__all__ = ["run_cost_stress"]

