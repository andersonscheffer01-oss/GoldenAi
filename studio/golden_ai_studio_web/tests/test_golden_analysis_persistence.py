import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jarvis_core.golden_analysis_repository import GoldenAnalysisRepository
from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE
from jarvis_core.service import JarvisService
from jarvis_core.task_manager.database import TaskDatabase


def _analysis(analysis_id="panel_analysis_fixture1", **overrides):
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc).isoformat()
    result = {
        "ok": True,
        "status": "COMPLETE",
        "analysis_status": "COMPLETE",
        "contract_version": "golden-analysis-v2",
        "analysis_id": analysis_id,
        "analysis_mode": "INDEPENDENT",
        "request_type": "ON_DEMAND",
        "analysis_style": "AUTO",
        "result_kind": "ANALYSIS",
        "opportunity_status": "NOT_RETURNED_BY_MODEL",
        "signal_status": "NOT_CONFIRMED",
        "execution_status": "NOT_EXECUTED",
        "timeframes_evaluated": [{"timeframe": "M15", "status": "AVAILABLE",
                                  "snapshot_id": "snap-fixture",
                                  "raw_timestamp_start": 1791200000,
                                  "raw_timestamp_end": 1791200900}],
        "horizon_assessments": [{"style": "DAY_TRADE", "status": "AVAILABLE"}],
        "opportunities": [],
        "symbol": "BTCUSD",
        "provider": "MT5",
        "provider_asset_id": "mt5:BTCUSD",
        "provider_symbol": "BTCUSD",
        "asset_class": "CRYPTO",
        "timeframe": "M15",
        "started_at": now,
        "completed_at": now,
        "snapshot_id": "snap-fixture",
        "correlation_id": "corr-fixture",
        "audit_correlation_id": "corr-fixture",
        "data_cutoff": 1791200900,
        "temporal_authority": "UNKNOWN",
        "context_availability": {"data_recency": "OBSERVED", "absolute_utc": "UNKNOWN"},
        "provenance": {"snapshot_ids": {"M15": "snap-fixture"},
                       "authorization_token": "must-not-be-stored"},
        "model": {"provider": "gemini", "name": "gemini-test"},
        "summary": "Fixture result; not a trade.",
        "confidence": 62,
        "execution_authority": "NONE",
        "private_prompt": "do not persist this prompt",
    }
    result.update(overrides)
    return result


def test_task_database_additive_analysis_schema_is_idempotent_and_preserves_existing_rows(tmp_path):
    path = tmp_path / "golden_tasks.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE legacy_sentinel(value TEXT NOT NULL)")
        db.execute("INSERT INTO legacy_sentinel(value) VALUES('preserve-me')")

    database = TaskDatabase(path)
    database._migrate()
    database._migrate()

    with database.connect(rows=True) as db:
        assert db.execute("SELECT value FROM legacy_sentinel").fetchone()[0] == "preserve-me"
        assert db.execute("SELECT version FROM task_schema_version").fetchone()[0] == TaskDatabase.SCHEMA_VERSION
        assert db.execute("SELECT COUNT(*) FROM golden_analysis_results").fetchone()[0] == 0
        columns = {row["name"] for row in db.execute(
            "PRAGMA table_info(golden_analysis_results)").fetchall()}
    assert {"analysis_id", "schema_version", "result_json", "result_sha256"} <= columns


def test_analysis_persists_and_recovers_after_new_connection_without_private_fields(tmp_path):
    database = TaskDatabase(tmp_path / "golden_tasks.db")
    repository = GoldenAnalysisRepository(database)
    result = _analysis()

    saved = repository.save(result, audit_correlation_id="corr-audit-1")
    recovered = GoldenAnalysisRepository(TaskDatabase(database.path)).get(result["analysis_id"])

    assert saved["persisted"] is True and saved["duplicate"] is False
    assert recovered["analysis"]["analysis_id"] == result["analysis_id"]
    assert recovered["analysis"]["snapshot_id"] == "snap-fixture"
    assert recovered["analysis"]["timeframes_evaluated"][0]["raw_timestamp_end"] == 1791200900
    assert recovered["analysis"]["temporal_authority"] == "UNKNOWN"
    assert recovered["correlation_id"] == "corr-audit-1"
    assert recovered["analysis"]["audit_correlation_id"] == "corr-audit-1"
    encoded = json.dumps(recovered["analysis"], ensure_ascii=False)
    assert "private_prompt" not in encoded
    assert "must-not-be-stored" not in encoded
    assert recovered["analysis"]["persistence"] == {"persisted": True, "status": "PERSISTED"}


def test_analysis_id_is_idempotent_but_conflicting_payload_is_rejected(tmp_path):
    repository = GoldenAnalysisRepository(TaskDatabase(tmp_path / "tasks.db"))
    result = _analysis()

    assert repository.save(result)["duplicate"] is False
    assert repository.save(result)["duplicate"] is True
    with pytest.raises(ValueError, match="ANALYSIS_ID_CONFLICT"):
        repository.save({**result, "summary": "different content"})
    assert repository.list()["total"] == 1


def test_analysis_list_is_bounded_paginated_and_filtered(tmp_path):
    repository = GoldenAnalysisRepository(TaskDatabase(tmp_path / "tasks.db"))
    for suffix, symbol, mode, status in (
        ("1", "BTCUSD", "INDEPENDENT", "COMPLETE"),
        ("2", "BTCUSD", "STRATEGY", "STRATEGY_UNAVAILABLE"),
        ("3", "XAUUSD", "INDEPENDENT", "ERROR"),
    ):
        stamp = datetime(2026, 10, int(suffix), 12, 0, tzinfo=timezone.utc).isoformat()
        repository.save(_analysis(
            f"panel_analysis_fixture{suffix}", symbol=symbol,
            provider_asset_id=f"mt5:{symbol}", provider_symbol=symbol,
            analysis_mode=mode, status=status, analysis_status=status,
            started_at=stamp, completed_at=stamp))

    first = repository.list(symbol="BTCUSD", date_from="2026-10-01",
                            date_to="2026-10-01", limit=1, offset=0)
    second = repository.list(symbol="BTCUSD", analysis_mode="STRATEGY",
                             status="STRATEGY_UNAVAILABLE", limit=10, offset=0)

    assert first["total"] == 1 and len(first["items"]) == 1
    assert first["has_more"] is False
    assert second["total"] == 1 and second["items"][0]["analysis_mode"] == "STRATEGY"
    with pytest.raises(ValueError, match="INVALID_PAGINATION"):
        repository.list(limit=51)
    with pytest.raises(ValueError, match="FILTER_TIMEZONE_REQUIRED"):
        repository.list(date_from="2026-10-01T12:00:00")


def test_canonical_read_tools_obey_security_and_never_call_market_or_model(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.golden_analysis_repository.save(_analysis())
        service.golden_panel_market_snapshot = lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("market source called during history read"))
        service.generate_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model called during history read"))
        read = service.registry.get("golden_panel_analysis_get")
        listing = service.registry.get("golden_panel_analysis_list")
        assert read and listing and read.llm_enabled is False and listing.llm_enabled is False
        assert read.side_effect_class.value == "READ_ONLY"
        assert "NO_MODEL" in read.security_requirements

        service.security.rules[read.name] = "deny"
        denied = service.execute_tool(read.name, {"analysis_id": "panel_analysis_fixture1"})
        assert denied["ok"] is False

        service.security.rules.pop(read.name)
        service._active_audit_context = {"correlation_id": "corr-read-test",
                                         "surface": "test"}
        recovered = service.execute_tool(
            read.name, {"analysis_id": "panel_analysis_fixture1"})
        page = service.execute_tool(listing.name, {"symbol": "BTCUSD", "limit": 10,
                                                   "offset": 0})
        assert recovered["status"] == "FOUND"
        assert recovered["analysis"]["analysis_id"] == "panel_analysis_fixture1"
        assert page["data"]["total"] == 1
        with service.audit._connect() as db:
            rows = db.execute("SELECT result FROM jarvis_audit WHERE tool IN (?,?)",
                              (read.name, listing.name)).fetchall()
        assert len(rows) >= 3
        assert any("corr-read-test" in str(row[0]) for row in rows)
    finally:
        service.close()


def test_persistence_failure_is_explicit_and_never_claims_saved(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.golden_analysis_repository.save = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("private filesystem detail"))
        result = service._persist_panel_analysis_result(_analysis(), "corr-store-failure")
        assert result["persistence"]["persisted"] is False
        assert result["persistence"]["status"] == "FAILED"
        assert result["persistence"]["error_code"] == "ANALYSIS_PERSISTENCE_UNAVAILABLE"
        assert "private filesystem detail" not in json.dumps(result)
    finally:
        service.close()


def test_recovery_actions_extend_only_the_existing_authenticated_analysis_route():
    source = (Path(__file__).resolve().parents[1] / "server_agent.py").read_text(
        encoding="utf-8")
    route = '"/api/jarvis/golden/panel-analysis": lambda d: self._api_jarvis_golden_panel_analysis(d)'
    start = source.index("    def _api_jarvis_golden_panel_analysis(self, data):")
    end = source.index("\n    def _api_jarvis_golden_symbol_discovery", start)
    handler = source[start:end]

    assert source.count(route) == 1
    assert 'if action == "GET"' in handler
    assert 'if action == "LIST"' in handler
    assert '"golden_panel_analysis_get"' in handler
    assert '"golden_panel_analysis_list"' in handler
    assert 'if action != "ANALYZE"' in handler
