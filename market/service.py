from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from quant.models import StrategySpec

from .adapters import MarketDataAdapter, validate_market_data
from .analysis import (
    mtf_context,
    observations_from,
    regime_from_structure,
    signal_from_regime,
    snapshot_from_rows,
    structure_from_rows,
)
from .models import MarketAnalysisResult, deterministic_hash, new_id, now_iso
from .repository import MarketRepository


class MarketAnalysisService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.repository = MarketRepository(self.root)
        self.audit = AuditLogger(self.root / "logs")

    def _audit(self, action_type: str, status: str, target: str = "", detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "market.v1",
            "target": target,
            "result": detail[:1000],
            "files_changed": [],
            "commands_executed": [],
        })

    def analyze(
        self,
        symbol: str,
        adapter: MarketDataAdapter,
        source: str = "synthetic",
        ma_period: int = 20,
        as_of_timestamp: str | None = None,
    ) -> MarketAnalysisResult:
        analysis_id = new_id("market_analysis")
        self._audit("MARKET_ANALYSIS_CREATED", "CREATED", analysis_id, f"symbol={symbol}; source={source}")
        try:
            data_by_timeframe = self._load_data(adapter, as_of_timestamp)
            validate_market_data(data_by_timeframe)

            snapshots = []
            structures = []
            regimes = []
            observations = []
            signals = []

            for timeframe in sorted(data_by_timeframe):
                rows = data_by_timeframe[timeframe]
                snapshot = snapshot_from_rows(symbol, timeframe, rows, source)
                structure = structure_from_rows(symbol, timeframe, rows, ma_period)
                regime = regime_from_structure(snapshot, structure, rows)
                timeframe_observations = observations_from(symbol, timeframe, snapshot, structure, regime)
                signal = signal_from_regime(symbol, timeframe, regime)

                snapshots.append(snapshot)
                structures.append(structure)
                regimes.append(regime)
                observations.extend(timeframe_observations)
                signals.append(signal)

                self._audit("MARKET_SNAPSHOT_CREATED", "COMPLETED", snapshot.snapshot_id, snapshot.data_hash)
                self._audit("MARKET_REGIME_DETECTED", "COMPLETED", timeframe, regime.regime)

            context = mtf_context(symbol, regimes)
            context.timestamp = max(snapshot.timestamp for snapshot in snapshots)
            self._audit("MARKET_MTF_COMPLETED", "COMPLETED", analysis_id, context.alignment)

            report = self._build_report(symbol, source, snapshots, regimes, structures, observations, signals, context)
            result = MarketAnalysisResult(
                analysis_id=analysis_id,
                symbol=symbol,
                source=source,
                snapshots=snapshots,
                regimes=regimes,
                mtf_context=context,
                structures=structures,
                observations=observations,
                signals=signals,
                report=report,
                created_at=now_iso(),
            )
            result.result_hash = result.compute_hash()
            self.repository.save_analysis(result)
            self._audit("MARKET_ANALYSIS_COMPLETED", "COMPLETED", analysis_id, result.result_hash)
            return result
        except Exception as exc:
            self._audit("MARKET_ANALYSIS_FAILED", "FAILED", analysis_id, str(exc))
            raise

    def hypothesis_to_strategy_spec(self, result: MarketAnalysisResult, name: str = "Market hypothesis") -> StrategySpec:
        primary_signal = result.signals[0].signal if result.signals else "NO_DIRECTIONAL_CONTEXT"
        primary_timeframe = result.signals[0].timeframe if result.signals else ""
        return StrategySpec(
            strategy_id=new_id("strategy"),
            name=name,
            version="1.0",
            description="Hipotese conceitual gerada a partir de Market V1; exige validacao Quant antes de qualquer conclusao.",
            parameters={
                "market_analysis_id": result.analysis_id,
                "market_result_hash": result.result_hash,
                "alignment": result.mtf_context.alignment,
                "signal": primary_signal,
            },
            entry_logic_identifier="market_context_placeholder",
            exit_logic_identifier="hold_bars",
            created_at=now_iso(),
            symbol=result.symbol,
            timeframe=primary_timeframe,
            unknowns={
                "validation_status": "NOT_BACKTESTED",
                "permission_required": "quant_backtest_before_use",
            },
        )

    def _load_data(self, adapter: MarketDataAdapter, as_of_timestamp: str | None) -> dict[str, list[dict[str, Any]]]:
        loaded = adapter.load()
        if as_of_timestamp is None:
            return loaded
        filtered = {}
        for timeframe, rows in loaded.items():
            filtered[timeframe] = [row for row in rows if str(row.get("timestamp", "")) <= as_of_timestamp]
        return filtered

    def _build_report(
        self,
        symbol: str,
        source: str,
        snapshots: list,
        regimes: list,
        structures: list,
        observations: list,
        signals: list,
        context,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "source": source,
            "observed": [asdict(item) for item in observations if item.evidence_level.value == "OBSERVED"],
            "inferred": [asdict(item) for item in regimes],
            "hypotheses": [asdict(item) for item in signals],
            "structure": [asdict(item) for item in structures],
            "multi_timeframe": asdict(context),
            "snapshots": [asdict(item) for item in snapshots],
            "hashes": {
                "input_hash": deterministic_hash([{"timeframe": item.timeframe, "data_hash": item.data_hash} for item in snapshots]),
            },
            "limitations": [
                "Analise local sobre candles fornecidos pelo adapter; sem internet e sem leitura MT5 real nesta V1.",
                "Regimes sao inferencias heuristicas, nao previsoes.",
                "Sinais sao hipoteses contextuais; qualquer uso exige validacao Quant separada.",
                "Nenhuma ordem, trade real, alteracao em .mq5 ou execucao externa e realizada por Market V1.",
            ],
        }
