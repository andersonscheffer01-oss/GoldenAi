from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.audit import AuditLogger

from .backtest import BacktestEngine, result_hash
from .data_validation import validate_ohlc_rows
from .models import (
    BacktestSpec,
    ComparisonResult,
    CostModel,
    DatasetSpec,
    StrategySpec,
    deterministic_hash,
    new_id,
    now_iso,
)
from .repository import QuantRepository


class QuantService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.repo = QuantRepository(self.root)
        self.engine = BacktestEngine()
        self.audit = AuditLogger(self.root / "logs")

    def _audit(self, action_type: str, status: str, target: str = "", detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "quant.v1",
            "target": target,
            "result": detail[:1000],
            "files_changed": [],
            "commands_executed": [],
        })

    def dataset_from_rows(
        self,
        rows: list[dict[str, Any]],
        source: str,
        symbol: str,
        timeframe: str,
        timezone: str = "UTC",
    ) -> DatasetSpec:
        validation = validate_ohlc_rows(rows)
        if not validation.ok:
            self._audit("QUANT_DATASET_VALIDATED", "FAILED", source, "; ".join(validation.errors))
            raise ValueError("; ".join(validation.errors))
        data_hash = deterministic_hash(rows)
        spec = DatasetSpec(
            dataset_id=new_id("dataset"),
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            start=str(rows[0]["timestamp"]),
            end=str(rows[-1]["timestamp"]),
            timezone=timezone,
            columns=list(rows[0].keys()),
            row_count=len(rows),
            data_hash=data_hash,
            created_at=now_iso(),
        )
        self.repo.save_dataset(spec)
        self._audit("QUANT_DATASET_VALIDATED", "COMPLETED", source, data_hash)
        return spec

    def strategy(
        self,
        name: str,
        entry_logic_identifier: str,
        exit_logic_identifier: str = "hold_bars",
        parameters: dict[str, Any] | None = None,
        description: str = "",
        version: str = "1.0",
    ) -> StrategySpec:
        spec = StrategySpec(
            strategy_id=new_id("strategy"),
            name=name,
            version=version,
            description=description,
            parameters=parameters or {"hold_bars": 1},
            entry_logic_identifier=entry_logic_identifier,
            exit_logic_identifier=exit_logic_identifier,
            created_at=now_iso(),
        )
        self.repo.save_strategy(spec)
        return spec

    def run_backtest(self, spec: BacktestSpec, rows: list[dict[str, Any]]) -> tuple[str, dict]:
        experiment_id = new_id("experiment")
        self._audit("QUANT_EXPERIMENT_CREATED", "CREATED", experiment_id, spec.config_hash())
        self._audit("QUANT_BACKTEST_STARTED", "RUNNING", experiment_id)
        try:
            result = self.engine.run(experiment_id, spec, rows)
            artifact_dir = self.repo.save_backtest(spec, result)
            self._audit("QUANT_BACKTEST_COMPLETED", "COMPLETED", experiment_id, result_hash(result))
            return experiment_id, {
                "result": result,
                "artifact_dir": str(artifact_dir),
                "result_hash": result_hash(result),
            }
        except Exception as exc:
            self._audit("QUANT_BACKTEST_FAILED", "FAILED", experiment_id, str(exc))
            raise

    def compare(self, experiment_a: str, experiment_b: str) -> ComparisonResult:
        a = self.repo.get_backtest(experiment_a)
        b = self.repo.get_backtest(experiment_b)
        if not a or not b:
            raise KeyError("experimento nao encontrado")
        metrics_a = a["metrics_json"]
        metrics_b = b["metrics_json"]
        import json

        ma = json.loads(metrics_a)
        mb = json.loads(metrics_b)
        keys = [
            "total_trades",
            "net_profit",
            "win_rate",
            "expectancy",
            "profit_factor",
            "max_drawdown_abs",
            "payoff_ratio",
            "average_trade",
        ]
        differences = {
            key: {
                "a": ma.get(key),
                "b": mb.get(key),
                "delta": (mb.get(key) - ma.get(key)) if isinstance(ma.get(key), (int, float)) and isinstance(mb.get(key), (int, float)) else None,
            }
            for key in keys
        }
        comparison = ComparisonResult(
            comparison_id=new_id("comparison"),
            experiment_a=experiment_a,
            experiment_b=experiment_b,
            differences=differences,
            interpretation="Comparacao de trade-offs; nao declara vencedor absoluto.",
        )
        self.repo.save_comparison(comparison)
        self._audit("QUANT_COMPARISON_CREATED", "COMPLETED", comparison.comparison_id)
        return comparison


def build_backtest_spec(
    strategy: StrategySpec,
    dataset: DatasetSpec,
    initial_capital: float = 10000.0,
    quantity: float = 1.0,
    cost_model: CostModel | None = None,
    seed: int | None = 1,
) -> BacktestSpec:
    return BacktestSpec(
        strategy=strategy,
        dataset=dataset,
        period={"start": dataset.start, "end": dataset.end},
        initial_capital=initial_capital,
        position_sizing={"quantity": quantity},
        cost_model=cost_model or CostModel(spread=0.0, commission=0.0, slippage=0.0),
        seed=seed,
        created_at=now_iso(),
    )
