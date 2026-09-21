from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deterministic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


@dataclass
class StrategySpec:
    strategy_id: str = ""
    name: str = ""
    version: str = "1.0"
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    entry_logic_identifier: str = "never"
    exit_logic_identifier: str = "hold_bars"
    created_at: str = ""
    symbol: str = ""
    timeframe: str = ""
    unknowns: dict[str, Any] = field(default_factory=dict)

    def config_hash(self) -> str:
        data = asdict(self)
        data.pop("created_at", None)
        return deterministic_hash(data)


@dataclass
class DatasetSpec:
    dataset_id: str
    source: str
    symbol: str
    timeframe: str
    start: str
    end: str
    timezone: str
    columns: list[str]
    row_count: int
    data_hash: str
    created_at: str = ""

    def config_hash(self) -> str:
        data = asdict(self)
        data.pop("created_at", None)
        return deterministic_hash(data)


@dataclass
class CostModel:
    spread: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    currency: str = "POINTS"

    def total_round_turn_cost_per_unit(self) -> float:
        return (float(self.spread) + float(self.slippage) * 2.0)

    def config_hash(self) -> str:
        return deterministic_hash(asdict(self))


@dataclass
class DataSegment:
    name: str
    start: str
    end: str
    role: str


@dataclass
class BacktestSpec:
    strategy: StrategySpec
    dataset: DatasetSpec
    period: dict[str, str]
    initial_capital: float
    position_sizing: dict[str, Any]
    cost_model: CostModel
    seed: int | None = None
    execution_assumptions: str = (
        "Signals are computed after candle N closes. Entries occur no earlier than candle N+1. "
        "No future candle is used to decide earlier entries."
    )
    segments: list[DataSegment] = field(default_factory=list)
    development_segment: str = "TRAIN"
    selection_segment: str = "VALIDATION"
    final_evaluation_segment: str = "HOLDOUT"
    created_at: str = ""

    def config_hash(self) -> str:
        data = asdict(self)
        data.pop("created_at", None)
        return deterministic_hash(data)


@dataclass
class TradeRecord:
    trade_id: str
    experiment_id: str
    symbol: str
    side: str
    signal_time: str
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    quantity: float
    gross_pnl: float
    costs: float
    net_pnl: float
    return_pct: float
    exit_reason: str
    mae: float | None = None
    mfe: float | None = None
    bars_held: int | None = None


@dataclass
class MetricsResult:
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float | None
    loss_rate: float | None
    gross_profit: float
    gross_loss: float
    net_profit: float
    average_win: float | None
    average_loss: float | None
    payoff_ratio: float | None
    expectancy: float | None
    profit_factor: float | None
    max_drawdown_abs: float
    max_drawdown_pct: float | None
    consecutive_wins: int
    consecutive_losses: int
    average_trade: float | None
    best_trade: float | None
    worst_trade: float | None
    sharpe_simplified: float | None


@dataclass
class BacktestResult:
    experiment_id: str
    strategy_hash: str
    dataset_hash: str
    backtest_hash: str
    status: str
    trades: list[TradeRecord]
    metrics: MetricsResult
    equity_curve: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class ExperimentRecord:
    experiment_id: str
    strategy_hash: str
    dataset_hash: str
    backtest_hash: str
    status: str
    result_summary: dict[str, Any]
    artifact_path: str
    created_at: str = field(default_factory=now_iso)


@dataclass
class ExperimentArtifact:
    artifact_id: str
    experiment_id: str
    artifact_path: str
    artifact_type: str
    sha256: str
    created_at: str = field(default_factory=now_iso)


@dataclass
class ComparisonResult:
    comparison_id: str
    experiment_a: str
    experiment_b: str
    differences: dict[str, Any]
    interpretation: str
    created_at: str = field(default_factory=now_iso)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"
