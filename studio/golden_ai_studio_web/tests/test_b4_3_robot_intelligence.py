import inspect
from pathlib import Path

from jarvis_core.golden_bridge import GoldenReadBridge
from jarvis_core.robot_intelligence import (
    build_evidence_dataset,
    build_robot_intelligence_snapshot,
    build_suitability,
    normalize_robot_profile,
)
from jarvis_core.service import JarvisService


def _robot(robot_id="robot_alpha", **overrides):
    value = {
        "robot_id": robot_id,
        "name": "Alpha Breakout",
        "version": "1.0",
        "status": "CANDIDATE",
        "source_artifacts": [{"artifact_id": "src-alpha"}],
        "compiled_artifacts": [],
        "backtest_count": 1,
        "test_run_count": 0,
        "evidence_summary": {"BACKTEST_EVIDENCE": 1},
        "strategy_family": "BREAKOUT",
        "supported_symbols": ["XAUUSD"],
        "supported_timeframes": ["M15"],
        "preferred_market_regime": "TREND",
        "spread_constraints": "UNKNOWN",
        "risk_model": "UNKNOWN",
        "backtest_artifacts": [{
            "artifact_id": "bt-alpha", "association_status": "VERIFIED",
            "evidence_type": "BACKTEST_EVIDENCE", "symbol": "XAUUSD",
            "timeframe": "M15", "metrics": {"trades": 4},
            "date_range": {"period_start": 1, "period_end": 2},
            "provenance": [{"source_ref": "stored-report.json"}],
        }],
        "known_limitations": [], "conflicts": [], "provenance": [], "user_overrides": [],
    }
    value.update(overrides)
    return value


def _market():
    return {"ok": True, "snapshot_id": "market_1", "data": {
        "symbol": "XAUUSD", "timeframe": "M15", "regime": "TREND",
        "scanner": {"normalized_results": [{"symbol": "XAUUSD", "market_regime": "TREND"}]},
    }}


def test_profile_separates_repertoire_from_trading_authorization():
    profile = normalize_robot_profile(_robot(status="ACTIVE"))
    assert profile["repertoire_status"] == "ACTIVE"
    assert profile["trading_authorization"] == "NOT_GRANTED"
    assert profile["metadata"]["strategy_type"]["status"] == "OBSERVED"


def test_dataset_deduplicates_runs_and_keeps_unknown_market_labels():
    robot = _robot()
    robot["test_runs"] = [{"test_run_id": "bt-alpha", "evidence_type": "BACKTEST"}]
    dataset = build_evidence_dataset([robot])
    assert dataset["unique_samples"] == 1
    assert dataset["duplicate_runs_excluded"] == 1
    assert dataset["resolved_associations"] == 1
    assert dataset["rows"][0]["market_labels"]["regime"]["status"] == "UNKNOWN"


def test_suitability_is_structural_and_never_probability():
    profile = normalize_robot_profile(_robot())
    result = build_suitability([profile], _market(), "XAUUSD", "M15")
    item = result["results"][0]
    assert item["match_status"] == "SUPPORTED"
    assert result["empirical_matching"] == "NOT_IMPLEMENTED"
    assert result["opaque_ai_score"] is False
    assert result["fake_probability"] is False
    assert item["trading_authorization"] == "NOT_GRANTED"


def test_snapshot_has_temporal_contract_and_no_parallel_authority():
    catalog = {"ok": True, "data": {"robots": [_robot()]}}
    first = build_robot_intelligence_snapshot(catalog, _market(), "XAUUSD", "M15", "corr-1")
    second = build_robot_intelligence_snapshot(catalog, _market(), "XAUUSD", "M15", "corr-1")
    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["temporal_evidence_contract"]["immutable_context"] is True
    assert first["security"]["execution_authority"] == "NONE"
    assert first["suitability"]["trading_authorization"] == "NOT_GRANTED"


def test_bridge_composes_existing_catalog_without_provider_calls():
    class Catalog:
        def snapshot(self):
            return {"ok": True, "robots": [_robot()]}

    bridge = GoldenReadBridge(robot_catalog=Catalog())
    bridge.market_intelligence_snapshot = lambda *args: _market()
    result = bridge.robot_intelligence_snapshot("XAUUSD", "M15", correlation_id="corr-2")
    assert result["ok"] is True
    assert result["authority"] == "JarvisService"
    assert result["robots"][0]["robot_id"] == "robot_alpha"


def test_service_registers_read_only_robot_intelligence_tool(tmp_path):
    service = JarvisService(tmp_path)
    try:
        tool = next(item for item in service.registry.capability_catalog()
                    if item["name"] == "robot_intelligence_snapshot")
        assert tool["side_effect_class"] == "READ_ONLY"
        assert tool["security_requirements"] == ["READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING"]
    finally:
        service.close()


def test_route_and_ui_expose_analysis_only_surface():
    server = Path(__file__).parents[1].joinpath("server_agent.py").read_text(encoding="utf-8")
    ui = Path(__file__).parents[1].joinpath("jarvis_ui", "src", "app.js").read_text(encoding="utf-8")
    html = Path(__file__).parents[1].joinpath("jarvis_ui", "jarvis.html").read_text(encoding="utf-8")
    assert "/api/jarvis/golden/robot-intelligence" in server
    assert "robot_intelligence_snapshot" in server
    assert "B43_ROBOT_INTELLIGENCE_ENDPOINT" in ui
    assert "ANALYSIS ONLY" in ui
    assert "gB43RobotIntelligence" in html


def test_robot_intelligence_boundary_has_no_execution_surface():
    from jarvis_core import robot_intelligence

    source = inspect.getsource(robot_intelligence).casefold()
    for forbidden in ("subprocess", "metatrader5", "order_send", "send_order", "terminal64", "provider"):
        assert forbidden not in source
