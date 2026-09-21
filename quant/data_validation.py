from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


REQUIRED_OHLC = ("timestamp", "open", "high", "low", "close")


@dataclass
class DatasetValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def validate_ohlc_rows(rows: list[dict[str, Any]], required_columns: tuple[str, ...] = REQUIRED_OHLC) -> DatasetValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not rows:
        return DatasetValidationResult(False, ["periodo vazio"], [])

    columns = set(rows[0].keys())
    missing = [col for col in required_columns if col not in columns]
    if missing:
        return DatasetValidationResult(False, [f"colunas obrigatorias ausentes: {', '.join(missing)}"], [])

    previous_time = None
    seen = set()
    for index, row in enumerate(rows):
        timestamp = parse_time(row.get("timestamp"))
        if timestamp is None:
            errors.append(f"timestamp invalido na linha {index}")
            continue
        if row.get("timestamp") in seen:
            errors.append(f"timestamp duplicado na linha {index}: {row.get('timestamp')}")
        seen.add(row.get("timestamp"))
        if previous_time and timestamp <= previous_time:
            errors.append(f"timestamp fora de ordem na linha {index}")
        previous_time = timestamp

        values = {}
        for col in ("open", "high", "low", "close"):
            value = row.get(col)
            if value is None or value == "":
                errors.append(f"valor ausente em {col} na linha {index}")
                continue
            try:
                values[col] = float(value)
            except Exception:
                errors.append(f"valor numerico invalido em {col} na linha {index}")

        if len(values) == 4:
            high = values["high"]
            low = values["low"]
            open_ = values["open"]
            close = values["close"]
            if not (high >= open_ and high >= close and low <= open_ and low <= close and high >= low):
                errors.append(f"OHLC inconsistente na linha {index}")

    return DatasetValidationResult(not errors, errors, warnings)
