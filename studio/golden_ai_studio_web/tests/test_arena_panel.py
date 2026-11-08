import json
from pathlib import Path

from jarvis_core import arena_panel


def _report():
    return {
        "run": {"run_id": "demo", "symbol": "XAUUSD", "status": "SIMULATION"},
        "security": {
            "read_only": True, "simulation_only": True,
            "execution_authority": "NONE", "real_orders": False,
        },
        "agents": [{"agent": "momentum", "metrics": {"net_pnl": 1.0}}],
        "validation": {"status": "NOT_VALIDATED", "winner": None},
    }


def test_arena_report_projection_reads_valid_report_with_fixed_security(monkeypatch, tmp_path):
    report_path = tmp_path / "latest_report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    monkeypatch.setattr(arena_panel, "ARENA_REPORT_PATH", report_path)

    result = arena_panel.load_arena_report()

    assert result["ok"] is True
    assert result["report"]["run"]["run_id"] == "demo"
    assert result["security"] == {
        "read_only": True, "simulation_only": True,
        "execution_authority": "NONE", "real_orders": False,
    }


def test_arena_report_projection_fails_closed_when_report_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_panel, "ARENA_REPORT_PATH", Path(tmp_path) / "missing.json")

    result = arena_panel.load_arena_report()

    assert result["ok"] is False
    assert result["status"] == "UNAVAILABLE"
    assert result["error_code"] == "ARENA_REPORT_NOT_FOUND"
    assert result["security"]["execution_authority"] == "NONE"

