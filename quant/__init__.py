from .backtest import BacktestEngine
from .data_validation import DatasetValidationResult, validate_ohlc_rows
from .metrics import calculate_metrics
from .models import (
    BacktestResult,
    BacktestSpec,
    ComparisonResult,
    CostModel,
    DataSegment,
    DatasetSpec,
    ExperimentArtifact,
    ExperimentRecord,
    MetricsResult,
    StrategySpec,
    TradeRecord,
    deterministic_hash,
)
from .repository import QuantRepository
from .service import QuantService, build_backtest_spec

DatasetMetadata = DatasetSpec
MetricSet = MetricsResult
ValidationResult = DatasetValidationResult

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "BacktestSpec",
    "ComparisonResult",
    "CostModel",
    "DataSegment",
    "DatasetMetadata",
    "DatasetSpec",
    "DatasetValidationResult",
    "ExperimentArtifact",
    "ExperimentRecord",
    "MetricSet",
    "MetricsResult",
    "QuantRepository",
    "QuantService",
    "StrategySpec",
    "TradeRecord",
    "ValidationResult",
    "build_backtest_spec",
    "calculate_metrics",
    "deterministic_hash",
    "validate_ohlc_rows",
]
