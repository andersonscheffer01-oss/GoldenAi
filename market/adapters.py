from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Protocol

from quant.data_validation import validate_ohlc_rows


class MarketDataAdapter(Protocol):
    def load(self) -> dict[str, list[dict[str, Any]]]:
        ...


class SyntheticMarketDataAdapter:
    def __init__(self, data_by_timeframe: dict[str, list[dict[str, Any]]]):
        self.data_by_timeframe = data_by_timeframe

    def load(self) -> dict[str, list[dict[str, Any]]]:
        return self.data_by_timeframe


class LocalCsvMarketDataAdapter:
    def __init__(self, path: str | Path, timeframe: str):
        self.path = Path(path)
        self.timeframe = timeframe

    def load(self) -> dict[str, list[dict[str, Any]]]:
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                converted = dict(row)
                for key in ("open", "high", "low", "close", "volume", "tick_volume", "spread"):
                    if key in converted and converted[key] not in ("", None):
                        converted[key] = float(converted[key])
                rows.append(converted)
        return {self.timeframe: rows}


class MT5MarketDataAdapter:
    def load(self) -> dict[str, list[dict[str, Any]]]:
        raise NotImplementedError("Leitura segura de candles MT5 ainda nao esta disponivel nesta V1")


def validate_market_data(data_by_timeframe: dict[str, list[dict[str, Any]]]) -> None:
    if not data_by_timeframe:
        raise ValueError("ausencia de dados")
    for timeframe, rows in data_by_timeframe.items():
        validation = validate_ohlc_rows(rows)
        if not validation.ok:
            raise ValueError(f"dataset invalido em {timeframe}: {'; '.join(validation.errors)}")
