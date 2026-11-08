"""CSV/JSONL ingestion with explicit provenance and fail-closed validation."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .contracts import Tick
from .validation import validate_ticks


@dataclass(frozen=True, slots=True)
class ValidationReport:
    path: str
    symbol: str
    rows: int
    first_event_index: int | None
    last_event_index: int | None
    first_timestamp: str | None
    last_timestamp: str | None
    status: str


def _timestamp(raw) -> datetime:
    value = str(raw or "").strip().replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def _tick(row: dict, fallback_index: int) -> Tick:
    raw_index = row.get("event_index", fallback_index)
    return Tick(
        symbol=str(row.get("symbol") or "").strip().upper(),
        event_index=int(raw_index),
        timestamp=_timestamp(row.get("timestamp")),
        bid=float(row["bid"]),
        ask=float(row["ask"]),
    )


def load_ticks(path, expected_symbol: str | None = None) -> tuple[Tick, ...]:
    """Load only the documented tick columns from CSV or JSONL."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    rows = []
    if source.suffix.casefold() in {".jsonl", ".ndjson"}:
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
    else:
        with source.open("r", encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    ticks = tuple(_tick(dict(row), index) for index, row in enumerate(rows))
    return validate_ticks(ticks, expected_symbol)


def validate_tick_file(path, expected_symbol: str | None = None) -> ValidationReport:
    ticks = load_ticks(path, expected_symbol)
    return ValidationReport(
        path=str(Path(path)), symbol=ticks[0].symbol if ticks else str(expected_symbol or "").upper(),
        rows=len(ticks), first_event_index=ticks[0].event_index if ticks else None,
        last_event_index=ticks[-1].event_index if ticks else None,
        first_timestamp=ticks[0].timestamp.isoformat() if ticks else None,
        last_timestamp=ticks[-1].timestamp.isoformat() if ticks else None,
        status="VALID" if ticks else "EMPTY",
    )


__all__ = ["ValidationReport", "load_ticks", "validate_tick_file"]


