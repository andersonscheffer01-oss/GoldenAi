import csv
from datetime import timezone, timedelta

import pytest

from golden_scalper_arena.mt5_export import load_mt5_export


def _write_export(tmp_path, timestamp="2026.01.02 12:00:00"):
    with (tmp_path / "symbol_spec.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "run_id", "symbol", "digits", "point", "tick_size", "tick_value",
            "contract_size", "volume_min", "volume_max", "volume_step",
            "currency_base", "currency_quote",
        ])
        writer.writeheader()
        writer.writerow({
            "run_id": "mt5-run", "symbol": "XAUUSD", "digits": 2,
            "point": 0.01, "tick_size": 0.01, "tick_value": 1.0,
            "contract_size": 100, "volume_min": 0.01, "volume_max": 100,
            "volume_step": 0.01, "currency_base": "XAU", "currency_quote": "USD",
        })
    columns = [
        "run_id", "event_index", "timestamp", "symbol", "bid", "ask", "spread",
        "m1_available", "m1_time", "m1_open", "m1_high", "m1_low", "m1_close", "m1_tick_volume",
        "m5_available", "m5_time", "m5_open", "m5_high", "m5_low", "m5_close", "m5_tick_volume",
        "m15_available", "m15_time", "m15_open", "m15_high", "m15_low", "m15_close", "m15_tick_volume",
        "h1_available", "h1_time", "h1_open", "h1_high", "h1_low", "h1_close", "h1_tick_volume",
    ]
    with (tmp_path / "ticks.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for index in (1, 2):
            row = {column: "" for column in columns}
            row.update({
                "run_id": "mt5-run", "event_index": index, "timestamp": timestamp,
                "symbol": "XAUUSD", "bid": 2300 + index * 0.1,
                "ask": 2300.2 + index * 0.1, "spread": 0.2,
                "m1_available": "1", "m1_time": 1767355200 + index - 1,
                "m1_open": 2300, "m1_high": 2300.4, "m1_low": 2299.8,
                "m1_close": 2300.2, "m1_tick_volume": 10,
            })
            writer.writerow(row)


def test_mt5_reader_requires_explicit_server_timezone(tmp_path):
    _write_export(tmp_path)
    with pytest.raises(ValueError, match="SERVER_TIMEZONE_REQUIRED"):
        load_mt5_export(tmp_path)


def test_mt5_reader_builds_closed_bar_snapshots_read_only(tmp_path):
    _write_export(tmp_path)
    export = load_mt5_export(tmp_path, server_timezone=timezone(timedelta(hours=2)))
    assert export.run_id == "mt5-run"
    assert export.spec.symbol == "XAUUSD"
    assert len(export.snapshots) == 2
    assert export.snapshots[-1].tick.ask > export.snapshots[-1].tick.bid
    assert len(export.snapshots[-1].closed_bars["M1"]) == 2
    assert export.execution_authority == "NONE"

