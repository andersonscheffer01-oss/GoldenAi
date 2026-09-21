from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.experiments import ExperimentRepository, ExperimentStatus
from core.tools.hashing import sha256_file

from .models import BacktestResult, BacktestSpec, ComparisonResult, DatasetSpec, StrategySpec, now_iso


class QuantRepository:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.db_path = self.root / "data" / "golden_ai.db"
        self.artifacts_root = self.root / "data" / "experiments"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.experiments = ExperimentRepository(self.db_path)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def migrate(self) -> None:
        con = self.connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS quant_datasets (
                    dataset_id TEXT PRIMARY KEY,
                    spec_json TEXT NOT NULL,
                    data_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quant_strategies (
                    strategy_id TEXT PRIMARY KEY,
                    spec_json TEXT NOT NULL,
                    strategy_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quant_backtests (
                    experiment_id TEXT PRIMARY KEY,
                    strategy_hash TEXT NOT NULL,
                    dataset_hash TEXT NOT NULL,
                    backtest_hash TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quant_trades (
                    trade_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    trade_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quant_metrics (
                    experiment_id TEXT PRIMARY KEY,
                    metrics_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quant_comparisons (
                    comparison_id TEXT PRIMARY KEY,
                    experiment_a TEXT NOT NULL,
                    experiment_b TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            con.commit()
        finally:
            con.close()

    def save_dataset(self, spec: DatasetSpec) -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO quant_datasets(dataset_id, spec_json, data_hash, created_at) VALUES (?, ?, ?, ?)",
                (spec.dataset_id, json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True), spec.data_hash, spec.created_at or now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def save_strategy(self, spec: StrategySpec) -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO quant_strategies(strategy_id, spec_json, strategy_hash, created_at) VALUES (?, ?, ?, ?)",
                (spec.strategy_id, json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True), spec.config_hash(), spec.created_at or now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def save_backtest(self, spec: BacktestSpec, result: BacktestResult) -> Path:
        artifact_dir = self.artifacts_root / result.experiment_id
        artifact_dir.mkdir(parents=True, exist_ok=False)
        self._write_json(artifact_dir / "config.json", asdict(spec))
        self._write_json(artifact_dir / "metrics.json", asdict(result.metrics))
        self._write_json(artifact_dir / "report.json", {
            "strategy": asdict(spec.strategy),
            "dataset": asdict(spec.dataset),
            "period": spec.period,
            "costs": asdict(spec.cost_model),
            "hashes": {
                "strategy_hash": result.strategy_hash,
                "dataset_hash": result.dataset_hash,
                "backtest_hash": result.backtest_hash,
            },
            "observed_results": asdict(result.metrics),
            "interpretation": "Hipotese testada; resultado observado nao e garantia de resultado futuro.",
            "warnings": result.warnings,
            "limitations": result.limitations,
        })
        self._write_trades_csv(artifact_dir / "trades.csv", result)
        self._write_equity_csv(artifact_dir / "equity.csv", result)

        self.experiments.create_experiment(
            title=spec.strategy.name,
            hypothesis=spec.strategy.description,
            status=ExperimentStatus.PASSED,
            experiment_id=result.experiment_id,
            domain="quant",
            symbol=spec.dataset.symbol,
            timeframe=spec.dataset.timeframe,
            dataset_id=spec.dataset.dataset_id,
            parameters=asdict(spec),
            metrics=asdict(result.metrics),
            validation_method="deterministic_backtest_v1",
            conclusion="RESULTADOS OBSERVADOS; sem garantia futura.",
            limitations="; ".join(result.limitations),
            artifact_path=str(artifact_dir),
        )
        for path in artifact_dir.iterdir():
            self.experiments.add_artifact(result.experiment_id, str(path), path.suffix.lstrip("."), sha256_file(path))

        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO quant_backtests(
                    experiment_id, strategy_hash, dataset_hash, backtest_hash, spec_json, metrics_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.experiment_id,
                    result.strategy_hash,
                    result.dataset_hash,
                    result.backtest_hash,
                    json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True),
                    json.dumps(asdict(result.metrics), ensure_ascii=False, sort_keys=True),
                    result.status,
                    now_iso(),
                ),
            )
            con.execute(
                "INSERT OR REPLACE INTO quant_metrics(experiment_id, metrics_json) VALUES (?, ?)",
                (result.experiment_id, json.dumps(asdict(result.metrics), ensure_ascii=False, sort_keys=True)),
            )
            for trade in result.trades:
                con.execute(
                    "INSERT OR REPLACE INTO quant_trades(trade_id, experiment_id, trade_json) VALUES (?, ?, ?)",
                    (trade.trade_id, result.experiment_id, json.dumps(asdict(trade), ensure_ascii=False, sort_keys=True)),
                )
            con.commit()
        finally:
            con.close()
        return artifact_dir

    def get_backtest(self, experiment_id: str) -> dict[str, Any] | None:
        con = self.connect()
        try:
            row = con.execute("SELECT * FROM quant_backtests WHERE experiment_id = ?", (experiment_id,)).fetchone()
            if not row:
                return None
            trades = con.execute("SELECT trade_json FROM quant_trades WHERE experiment_id = ? ORDER BY trade_id", (experiment_id,)).fetchall()
            data = dict(row)
            data["trades"] = [json.loads(item["trade_json"]) for item in trades]
            return data
        finally:
            con.close()

    def save_comparison(self, comparison: ComparisonResult) -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT OR REPLACE INTO quant_comparisons(comparison_id, experiment_a, experiment_b, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    comparison.comparison_id,
                    comparison.experiment_a,
                    comparison.experiment_b,
                    json.dumps(asdict(comparison), ensure_ascii=False, sort_keys=True),
                    comparison.created_at,
                ),
            )
            con.commit()
        finally:
            con.close()

    def _write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _write_trades_csv(self, path: Path, result: BacktestResult) -> None:
        rows = [asdict(trade) for trade in result.trades]
        with path.open("w", newline="", encoding="utf-8") as handle:
            if not rows:
                handle.write("")
                return
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _write_equity_csv(self, path: Path, result: BacktestResult) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["index", "time", "equity", "drawdown"])
            writer.writeheader()
            writer.writerows(result.equity_curve)
