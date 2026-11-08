from pathlib import Path

import pytest

from golden_scalper_arena.data_validator import load_ticks, validate_tick_file
from golden_scalper_arena.validation import MarketDataError


def test_csv_validator_reports_provenance_and_rejects_future_order(tmp_path: Path):
    valid = tmp_path / "ticks.csv"
    valid.write_text(
        "event_index,timestamp,symbol,bid,ask\n"
        "1,2026-01-02T12:00:01+00:00,XAUUSD,2300.0,2300.2\n"
        "2,2026-01-02T12:00:02+00:00,XAUUSD,2300.1,2300.3\n",
        encoding="utf-8",
    )
    report = validate_tick_file(valid, "XAUUSD")
    assert report.status == "VALID"
    assert report.rows == 2
    assert report.last_event_index == 2

    invalid = tmp_path / "invalid.csv"
    invalid.write_text(
        "event_index,timestamp,symbol,bid,ask\n"
        "2,2026-01-02T12:00:02+00:00,XAUUSD,2300.1,2300.3\n"
        "1,2026-01-02T12:00:03+00:00,XAUUSD,2300.0,2300.2\n",
        encoding="utf-8",
    )
    with pytest.raises(MarketDataError, match="EVENT_INDEX_NOT_MONOTONIC"):
        load_ticks(invalid, "XAUUSD")


