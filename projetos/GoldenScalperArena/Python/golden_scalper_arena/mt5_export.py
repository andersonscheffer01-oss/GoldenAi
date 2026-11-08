"""Read-only reader for the GoldenArena MT5 FILE_COMMON export."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path

from .contracts import Bar, MarketDataError, MarketSnapshot, SymbolSpec, Tick
from .validation import validate_ticks


TIMEFRAMES = {
    "M1": "m1",
    "M5": "m5",
    "M15": "m15",
    "H1": "h1",
}


@dataclass(frozen=True, slots=True)
class MT5Export:
    run_id: str
    spec: SymbolSpec
    snapshots: tuple[MarketSnapshot, ...]
    source: str
    time_authority: str
    execution_authority: str = "NONE"
    read_only: bool = True
    simulation_only: bool = True


def _timestamp(raw: str, server_timezone: tzinfo | None):
    value = str(raw or "").strip().replace("Z", "+00:00")
    if not value:
        raise MarketDataError("TIMESTAMP_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y.%m.%d %H:%M:%S")
        except ValueError as exc:
            raise MarketDataError("TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        if server_timezone is None:
            raise MarketDataError("SERVER_TIMEZONE_REQUIRED")
        parsed = parsed.replace(tzinfo=server_timezone)
    return parsed.astimezone(timezone.utc)


def _bar_timestamp(raw: str, server_timezone: tzinfo | None):
    value = str(raw or "").strip()
    if not value:
        return None
    if value.isdigit():
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise MarketDataError("BAR_TIMESTAMP_INVALID") from exc
    return _timestamp(value, server_timezone)


def _float(row, name: str) -> float:
    value = row.get(name, "")
    if str(value).strip() == "":
        raise MarketDataError(f"{name.upper()}_REQUIRED")
    try:
        return float(value)
    except ValueError as exc:
        raise MarketDataError(f"{name.upper()}_INVALID") from exc


def _load_spec(path: Path, run_id: str | None, symbol: str | None) -> SymbolSpec:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    candidates = [row for row in rows if (not run_id or row.get("run_id") == run_id)]
    if symbol:
        candidates = [row for row in candidates if str(row.get("symbol", "")).upper() == symbol.upper()]
    if not candidates:
        raise MarketDataError("SYMBOL_SPEC_NOT_FOUND")
    row = candidates[-1]
    try:
        return SymbolSpec(
            symbol=row.get("symbol", ""), digits=int(row["digits"]),
            point=float(row["point"]), tick_size=float(row["tick_size"]),
            tick_value=float(row["tick_value"]), contract_size=float(row["contract_size"]),
            volume_min=float(row["volume_min"]), volume_max=float(row["volume_max"]),
            volume_step=float(row["volume_step"]),
            currency_base=row.get("currency_base", ""), currency_quote=row.get("currency_quote", ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketDataError("SYMBOL_SPEC_INVALID") from exc


def load_mt5_export(directory, server_timezone: tzinfo | None = None,
                    expected_symbol: str | None = None, run_id: str | None = None) -> MT5Export:
    """Load the current MT5 export without connecting to or mutating MT5.

    MT5's ``TimeToString`` output has no offset. A caller must supply the
    confirmed broker server timezone; this reader never guesses it.
    """
    root = Path(directory)
    tick_path = root / "ticks.csv"
    spec_path = root / "symbol_spec.csv"
    if not tick_path.is_file() or not spec_path.is_file():
        raise FileNotFoundError("MT5_EXPORT_FILES_REQUIRED")
    with tick_path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise MarketDataError("TICK_EXPORT_EMPTY")
    selected_run = run_id or str(rows[0].get("run_id") or "").strip()
    if not selected_run:
        raise MarketDataError("RUN_ID_REQUIRED")
    if any(str(row.get("run_id") or "").strip() != selected_run for row in rows):
        raise MarketDataError("RUN_ID_CHANGED")
    symbol = str(rows[0].get("symbol") or "").strip().upper()
    if expected_symbol and symbol != expected_symbol.strip().upper():
        raise MarketDataError("SYMBOL_MISMATCH")
    spec = _load_spec(spec_path, selected_run, symbol)
    ticks = tuple(Tick(
        symbol=symbol,
        event_index=int(row.get("event_index", index)),
        timestamp=_timestamp(row.get("timestamp", ""), server_timezone),
        bid=_float(row, "bid"), ask=_float(row, "ask"),
    ) for index, row in enumerate(rows))
    ticks = validate_ticks(ticks, symbol)

    histories: dict[str, list[Bar]] = {timeframe: [] for timeframe in TIMEFRAMES}
    seen: set[tuple[str, str]] = set()
    snapshots = []
    for row, tick in zip(rows, ticks):
        for timeframe, prefix in TIMEFRAMES.items():
            if str(row.get(f"{prefix}_available", "")).strip() != "1":
                continue
            close_time = _bar_timestamp(row.get(f"{prefix}_time", ""), server_timezone)
            if close_time is None:
                raise MarketDataError("BAR_TIMESTAMP_REQUIRED")
            key = (timeframe, close_time.isoformat())
            if key not in seen:
                seen.add(key)
                histories[timeframe].append(Bar(
                    symbol=symbol, timeframe=timeframe, event_index=tick.event_index,
                    close_time=close_time,
                    open=_float(row, f"{prefix}_open"), high=_float(row, f"{prefix}_high"),
                    low=_float(row, f"{prefix}_low"), close=_float(row, f"{prefix}_close"),
                ))
        snapshots.append(MarketSnapshot(
            run_id=selected_run, spec=spec, tick=tick,
            closed_bars={timeframe: tuple(rows_) for timeframe, rows_ in histories.items() if rows_},
        ))
    authority = "CONFIRMED_BY_CALLER" if server_timezone is not None else "UNKNOWN"
    return MT5Export(
        run_id=selected_run, spec=spec, snapshots=tuple(snapshots),
        source="MetaTrader5 FILE_COMMON GoldenArena exporter",
        time_authority=authority,
    )


__all__ = ["MT5Export", "TIMEFRAMES", "load_mt5_export"]

