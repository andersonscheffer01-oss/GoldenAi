from __future__ import annotations

from statistics import mean
from typing import Any

from core.safety import EvidenceLevel

from .models import (
    MarketObservation,
    MarketSnapshot,
    MultiTimeframeContext,
    RegimeState,
    SignalContext,
    StructureState,
    deterministic_hash,
    new_id,
    now_iso,
)


REGIMES = {"TREND_UP", "TREND_DOWN", "RANGE", "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNCERTAIN"}


def true_ranges(rows: list[dict[str, Any]]) -> list[float]:
    return [float(row["high"]) - float(row["low"]) for row in rows]


def snapshot_from_rows(symbol: str, timeframe: str, rows: list[dict[str, Any]], source: str) -> MarketSnapshot:
    last = rows[-1]
    ranges = true_ranges(rows)
    data_hash = deterministic_hash(rows)
    return MarketSnapshot(
        snapshot_id=new_id("snapshot"),
        symbol=symbol,
        timestamp=str(last["timestamp"]),
        timeframe=timeframe,
        ohlc={key: float(last[key]) for key in ("open", "high", "low", "close")},
        spread=float(last["spread"]) if "spread" in last and last["spread"] not in (None, "") else None,
        volume=float(last["volume"]) if "volume" in last and last["volume"] not in (None, "") else None,
        tick_volume=float(last["tick_volume"]) if "tick_volume" in last and last["tick_volume"] not in (None, "") else None,
        volatility_metrics={
            "average_range": mean(ranges) if ranges else 0.0,
            "last_range": ranges[-1] if ranges else 0.0,
        },
        source=source,
        data_hash=data_hash,
    )


def swings(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    highs = []
    lows = []
    for index in range(1, len(rows) - 1):
        prev_, cur, next_ = rows[index - 1], rows[index], rows[index + 1]
        if float(cur["high"]) > float(prev_["high"]) and float(cur["high"]) > float(next_["high"]):
            highs.append({"index": index, "time": cur["timestamp"], "price": float(cur["high"])})
        if float(cur["low"]) < float(prev_["low"]) and float(cur["low"]) < float(next_["low"]):
            lows.append({"index": index, "time": cur["timestamp"], "price": float(cur["low"])})
    return highs, lows


def structure_from_rows(symbol: str, timeframe: str, rows: list[dict[str, Any]], ma_period: int = 20) -> StructureState:
    highs = [float(row["high"]) for row in rows]
    lows = [float(row["low"]) for row in rows]
    closes = [float(row["close"]) for row in rows]
    swing_highs, swing_lows = swings(rows)
    first = closes[0]
    last = closes[-1]
    avg_range = mean(true_ranges(rows)) if rows else 0.0
    trend = "TREND_UP" if last > first else "TREND_DOWN" if last < first else "RANGE"
    if len(closes) >= 4 and abs(last - first) <= avg_range:
        trend = "RANGE"
    ma = mean(closes[-ma_period:]) if len(closes) >= ma_period else mean(closes)
    return StructureState(
        symbol=symbol,
        timeframe=timeframe,
        recent_high=max(highs) if highs else None,
        recent_low=min(lows) if lows else None,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        basic_trend=trend,
        range_high=max(highs) if highs else None,
        range_low=min(lows) if lows else None,
        moving_average_distance=last - ma,
        volatility=avg_range,
        support=min(lows[-5:]) if lows else None,
        resistance=max(highs[-5:]) if highs else None,
        previous_high=highs[-2] if len(highs) > 1 else None,
        previous_low=lows[-2] if len(lows) > 1 else None,
    )


def regime_from_structure(snapshot: MarketSnapshot, structure: StructureState, rows: list[dict[str, Any]]) -> RegimeState:
    ranges = true_ranges(rows)
    avg = mean(ranges) if ranges else 0.0
    last_range = ranges[-1] if ranges else 0.0
    reasons: list[str] = []
    evidence: list[str] = []
    regime = structure.basic_trend if structure.basic_trend in ("TREND_UP", "TREND_DOWN", "RANGE") else "UNCERTAIN"
    confidence = 0.55
    if avg and last_range > avg * 2.0:
        regime = "HIGH_VOLATILITY"
        confidence = 0.75
        reasons.append("ultimo range acima de 2x a media")
    elif avg and last_range < avg * 0.5:
        regime = "LOW_VOLATILITY"
        confidence = 0.65
        reasons.append("ultimo range abaixo de 0.5x a media")
    else:
        reasons.append(f"estrutura basica: {structure.basic_trend}")
        confidence = 0.7 if regime != "UNCERTAIN" else 0.4
    evidence.append(f"data_hash={snapshot.data_hash}")
    return RegimeState(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        regime=regime if regime in REGIMES else "UNCERTAIN",
        confidence=confidence,
        evidence=evidence,
        reasons=reasons,
        evidence_level=EvidenceLevel.INFERRED,
    )


def observations_from(symbol: str, timeframe: str, snapshot: MarketSnapshot, structure: StructureState, regime: RegimeState) -> list[MarketObservation]:
    observations = [
        MarketObservation(new_id("obs"), symbol, timeframe, f"Fechamento atual: {snapshot.ohlc['close']}", EvidenceLevel.OBSERVED, snapshot.ohlc),
        MarketObservation(new_id("obs"), symbol, timeframe, f"Maxima recente: {structure.recent_high}", EvidenceLevel.OBSERVED, {"recent_high": structure.recent_high}),
        MarketObservation(new_id("obs"), symbol, timeframe, f"Regime inferido: {regime.regime}", EvidenceLevel.INFERRED, {"confidence": regime.confidence}),
    ]
    if structure.moving_average_distance is not None:
        relation = "acima" if structure.moving_average_distance > 0 else "abaixo" if structure.moving_average_distance < 0 else "em cima"
        observations.append(
            MarketObservation(new_id("obs"), symbol, timeframe, f"Preco {relation} da media configurada.", EvidenceLevel.OBSERVED, {"distance": structure.moving_average_distance})
        )
    return observations


def signal_from_regime(symbol: str, timeframe: str, regime: RegimeState) -> SignalContext:
    if regime.regime == "TREND_UP":
        signal = "POTENTIAL_LONG_CONTEXT"
        reasons = ["contexto compativel com tendencia de alta segundo regra simples"]
    elif regime.regime == "TREND_DOWN":
        signal = "POTENTIAL_SHORT_CONTEXT"
        reasons = ["contexto compativel com tendencia de baixa segundo regra simples"]
    else:
        signal = "NO_DIRECTIONAL_CONTEXT"
        reasons = ["regime nao direcional ou incerto"]
    return SignalContext(
        symbol=symbol,
        timeframe=timeframe,
        signal=signal,
        evidence_level=EvidenceLevel.HYPOTHESIS,
        reasons=reasons,
        risk_notes=["Sinal contextual nao e previsao e nao foi validado por backtest Quant nesta etapa."],
    )


def mtf_context(symbol: str, regimes: list[RegimeState]) -> MultiTimeframeContext:
    states = {regime.timeframe: regime.regime for regime in regimes}
    directional = [state for state in states.values() if state in ("TREND_UP", "TREND_DOWN")]
    conflicts = []
    if "TREND_UP" in directional and "TREND_DOWN" in directional:
        conflicts.append("timeframes direcionais em conflito")
        alignment = "CONFLICT"
    elif directional and len(set(directional)) == 1:
        alignment = directional[0]
    else:
        alignment = "MIXED_OR_UNCERTAIN"
    return MultiTimeframeContext(
        symbol=symbol,
        timeframes_used=list(states.keys()),
        states_by_timeframe=states,
        conflicts=conflicts,
        alignment=alignment,
        timestamp=now_iso(),
    )
