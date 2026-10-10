"""Local-only persistence contract tests; never open the production database."""

import copy
import hashlib
import json
import sqlite3
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from jarvis_core.golden_trend_scan_repository import GoldenTrendScanRepository
from jarvis_core.http_perimeter import HttpPerimeter
from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE
from jarvis_core.service import JarvisService
from jarvis_core.task_manager.database import TaskDatabase


ACTOR = "device:desktop-fixture"


def _summary(items):
    states = {"AVALIADO": "evaluated", "DADOS INSUFICIENTES": "insufficient",
              "INDISPONÍVEL": "unavailable", "FALHO": "failed", "PENDENTE": "pending"}
    counts = {name: 0 for name in states.values()}
    for item in items:
        counts[states[item["state"]]] += 1
    return counts


def _scan(count=79):
    items = []
    for index in range(count):
        symbol = f"FX{index:03d}"
        asset = {"provider": "MT5", "provider_asset_id": f"mt5:{symbol}",
                 "provider_symbol": symbol, "display_symbol": symbol,
                 "display_name": f"Fixture {symbol}", "asset_class": "FOREX",
                 "asset_class_source": "FIXTURE"}
        items.append({"asset": asset, "state": "PENDENTE", "result": None,
                      "error": "", "retry_count": 0, "batch_index": None})
    canonical = "\n".join("\0".join((item["asset"]["provider_asset_id"],
                                      item["asset"]["provider_symbol"],
                                      item["asset"]["asset_class"])) for item in items)
    return {"scan_id": str(uuid.uuid4()), "contract_version": "trend-scan-v1",
            "created_at": "2026-10-07T12:00:00+00:00", "universe_total": count,
            "asset_class_filter": "FOREX", "universe_hash": hashlib.sha256(
                canonical.encode()).hexdigest(), "excluded": [], "excluded_summary": {},
            "next_batch_index": 0, "paused": False, "items": items,
            "summary": _summary(items)}


def _ranked(asset, score):
    timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
    return {"asset": asset, "directional_score": score,
            "trend": "ALTA" if score > 0 else "BAIXA",
            "alignment": {"aligned": 7, "available": 7},
            "timeframe_divergence": False, "extended_trend_risk": "UNKNOWN",
            "freshness": "UNKNOWN", "absolute_utc_verified": "UNKNOWN",
            "temporal_authority": "UNKNOWN", "execution_authority": "NONE",
            "evaluated_timeframes": [
                {"timeframe": timeframe, "status": "AVAILABLE",
                 "directional_score": score, "trend_classification": "ALTA" if score > 0 else "BAIXA",
                 "snapshot_id": f"synthetic-{timeframe}", "candle_count": 100,
                 "freshness": "UNKNOWN", "raw_candle_time_end": 123456789}
                for timeframe in timeframes]}


@pytest.fixture
def repo(tmp_path):
    return GoldenTrendScanRepository(TaskDatabase(tmp_path / "golden_tasks.db"))


def test_79_asset_round_trip_and_idempotent_batch(repo):
    scan = _scan()
    original_id, original_hash = scan["scan_id"], scan["universe_hash"]
    created = repo.save(scan, ACTOR, 0)
    assert created["revision"] == 1
    for index, item in enumerate(scan["items"][:4]):
        item["state"] = "AVALIADO"
        item["result"] = _ranked(item["asset"], [27, -35, 42, -63][index])
        item["batch_index"] = 0
    scan["next_batch_index"] = 1
    scan["summary"] = _summary(scan["items"])
    saved = repo.save(scan, ACTOR, 1)
    assert saved["revision"] == 2
    assert repo.save(scan, ACTOR, 1)["duplicate"] is True
    reopened = GoldenTrendScanRepository(TaskDatabase(repo.database.path))
    recovered = reopened.latest(ACTOR)
    assert recovered["scan"]["scan_id"] == original_id
    assert recovered["scan"]["universe_hash_core"] == original_hash
    assert len(recovered["scan"]["items"]) == 79
    assert recovered["scan"]["summary"] == {"evaluated": 4, "insufficient": 0,
                                             "unavailable": 0, "failed": 0, "pending": 75}
    assert [row["result"]["directional_score"] for row in recovered["scan"]["items"][:4]] == [27, -35, 42, -63]
    for original, restored in zip(scan["items"][:4], recovered["scan"]["items"][:4]):
        assert restored["result"]["directional_score"] == original["result"]["directional_score"]
        assert restored["result"]["trend"] == original["result"]["trend"]
        assert restored["result"]["evaluated_timeframes"] == original["result"]["evaluated_timeframes"]
    assert recovered["scan"]["items"][0]["result"]["freshness"] == "UNKNOWN"
    assert recovered["scan"]["items"][0]["result"]["absolute_utc_verified"] == "UNKNOWN"
    assert recovered["scan"]["items"][0]["result"]["evaluated_timeframes"][0]["snapshot_id"] == "synthetic-M1"


def test_scope_integrity_and_immutable_results(repo):
    scan = _scan(5)
    repo.save(scan, ACTOR, 0)
    assert repo.latest("device:other-desktop") is None
    assert repo.get(scan["scan_id"], "device:other-desktop") is None
    with pytest.raises(ValueError, match="DESKTOP_DEVICE_IDENTITY_REQUIRED"):
        repo.latest("anonymous")
    wrong = copy.deepcopy(scan)
    wrong["universe_total"] = 4
    with pytest.raises(ValueError, match="UNIVERSE_TOTAL_MISMATCH"):
        repo.save(wrong, ACTOR, 1)
    wrong = copy.deepcopy(scan)
    wrong["items"][1]["asset"] = wrong["items"][0]["asset"]
    with pytest.raises(ValueError, match="DUPLICATE_SCAN_ASSET"):
        repo.save(wrong, ACTOR, 1)
    wrong = copy.deepcopy(scan)
    wrong["summary"]["pending"] = 4
    with pytest.raises(ValueError, match="SCAN_COUNTS_MISMATCH"):
        repo.save(wrong, ACTOR, 1)
    wrong = copy.deepcopy(scan)
    wrong["universe_hash"] = "0" * 64
    with pytest.raises(ValueError, match="UNIVERSE_HASH_MISMATCH"):
        repo.save(wrong, ACTOR, 1)
    scan["items"][0].update(state="AVALIADO", result=_ranked(scan["items"][0]["asset"], 27), batch_index=0)
    scan["next_batch_index"] = 1
    scan["summary"] = _summary(scan["items"])
    repo.save(scan, ACTOR, 1)
    changed = copy.deepcopy(scan)
    changed["items"][0]["result"]["directional_score"] = 90
    with pytest.raises(ValueError, match="SETTLED_RESULT_IMMUTABLE"):
        repo.save(changed, ACTOR, 2)


def test_repository_rejects_incompatible_asset_class_source(repo):
    scan = _scan(1)
    repo.save(scan, ACTOR, 0)
    result = _ranked(scan["items"][0]["asset"], 12)
    result["asset"] = copy.deepcopy(result["asset"])
    result["asset"]["asset_class_source"] = "WRONG_SOURCE"
    with pytest.raises(ValueError, match="RESULT_IDENTITY_MISMATCH"):
        repo.apply_batch_results(scan["scan_id"], ACTOR, 1, 0,
                                 [scan["items"][0]["asset"]["provider_asset_id"]],
                                 [result])


def test_result_asset_schema_is_exactly_frozen_identity():
    asset = {"provider": "MT5", "provider_asset_id": "mt5:EURAUD",
             "provider_symbol": "EURAUD", "display_symbol": "EURAUD",
             "display_name": "Euro vs Australian Dollar", "asset_class": "FOREX",
             "asset_class_source": "MT5_TRADE_CALC_MODE"}
    from jarvis_core.tools.market_readonly import rank_market_trend_frames
    result = rank_market_trend_frames(asset, {})
    assert result["asset"] == asset
    assert set(result["asset"]) == set(asset)


def test_rejects_unsupported_contract_and_more_than_four_batch_results(repo):
    scan = _scan(6)
    wrong = copy.deepcopy(scan)
    wrong["contract_version"] = "trend-scan-v99"
    with pytest.raises(ValueError, match="UNSUPPORTED_SCAN_CONTRACT"):
        repo.save(wrong, ACTOR, 0)
    repo.save(scan, ACTOR, 0)
    for item in scan["items"][:5]:
        item.update(state="AVALIADO", result=_ranked(item["asset"], 40), batch_index=0)
    scan["next_batch_index"] = 1
    scan["summary"] = _summary(scan["items"])
    with pytest.raises(ValueError, match="BATCH_LIMIT_EXCEEDED"):
        repo.save(scan, ACTOR, 1)
    assert repo.latest(ACTOR)["scan"]["summary"]["pending"] == 6


def test_preserves_rank_components_and_rejects_sensitive_nested_fields(repo):
    scan = _scan(1)
    repo.save(scan, ACTOR, 0)
    item = scan["items"][0]
    item.update(state="AVALIADO", result=_ranked(item["asset"], 27),
                batch_index=0, batch_correlation_id="ranking-fixture-1",
                batch_observed_at="2026-10-07T12:01:00+00:00")
    item["result"]["evaluated_timeframes"][0]["components"] = {
        "ma_spread_atr": 0.2, "price_location_atr": 0.3,
        "momentum_10_candles": 0.1, "directional_persistence_20": 0.4,
        "observed_breakout_20_candles": 1.0,
    }
    scan["next_batch_index"] = 1
    scan["summary"] = _summary(scan["items"])
    repo.save(scan, ACTOR, 1)
    restored = repo.latest(ACTOR)["scan"]["items"][0]
    assert restored["result"]["evaluated_timeframes"][0]["components"] == item["result"]["evaluated_timeframes"][0]["components"]
    assert restored["batch_correlation_id"] == "ranking-fixture-1"
    assert restored["batch_observed_at"] == "2026-10-07T12:01:00+00:00"
    forbidden = copy.deepcopy(scan)
    forbidden["items"][0]["result"]["evaluated_timeframes"][0]["components"]["api_key"] = "secret"
    with pytest.raises(ValueError, match="INVALID_SCAN_COMPONENTS"):
        repo.save(forbidden, ACTOR, 2)


def test_read_detects_corruption_and_preserves_existing_tables(repo):
    scan = _scan(2)
    repo.save(scan, ACTOR, 0)
    with repo.database.connect() as db:
        db.execute("INSERT INTO tasks(id,title,description,status,data_classification,created_at,"
                   "updated_at,error,metadata,timeout_seconds) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   ("legacy-task", "fixture", "fixture", "QUEUED", "PUBLIC", 1, 1, "", "{}", 10))
        db.execute("UPDATE golden_trend_scans SET state_json=? WHERE scan_id=?",
                   (json.dumps({"tampered": True}), scan["scan_id"]))
    with pytest.raises(ValueError, match="SCAN_STATE_CORRUPTED"):
        repo.latest(ACTOR)
    with repo.database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM tasks WHERE id='legacy-task'").fetchone()[0] == 1
        assert db.execute("SELECT version FROM task_schema_version").fetchone()[0] == 7


def test_read_accepts_exact_legacy_serialization_without_rewriting(repo):
    scan = _scan(2)
    repo.save(scan, ACTOR, 0)
    with repo.database.connect() as db:
        row = db.execute("SELECT state_json FROM golden_trend_scans WHERE scan_id=?",
                         (scan["scan_id"],)).fetchone()
        legacy = json.loads(row[0])
        legacy.pop("catalog_observation")
        legacy.pop("result_authority")
        encoded = json.dumps(legacy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        db.execute("UPDATE golden_trend_scans SET state_json=?, state_sha256=? WHERE scan_id=?",
                   (encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest(), scan["scan_id"]))

    before = repo.database.path.stat().st_mtime_ns
    recovered = repo.latest(ACTOR)

    assert recovered["scan"]["scan_id"] == scan["scan_id"]
    assert recovered["scan"]["catalog_observation"]["status"] == "UNKNOWN"
    assert recovered["scan"]["result_authority"] == "CLIENT_RETURNED_RANKING_NOT_REVALIDATED_AGAINST_MT5"
    assert repo.database.path.stat().st_mtime_ns == before


def test_read_revalidates_content_even_if_stored_digest_is_recomputed(repo):
    scan = _scan(2)
    repo.save(scan, ACTOR, 0)
    with repo.database.connect() as db:
        state = json.loads(db.execute("SELECT state_json FROM golden_trend_scans").fetchone()[0])
        state["summary"]["pending"] = 1
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        db.execute("UPDATE golden_trend_scans SET state_json=?,state_sha256=?",
                   (encoded, hashlib.sha256(encoded.encode()).hexdigest()))
    with pytest.raises(ValueError, match="SCAN_STATE_CORRUPTED"):
        repo.latest(ACTOR)


def test_additive_v6_to_v7_migration_preserves_existing_rows(tmp_path):
    path = tmp_path / "golden_tasks.db"
    db = TaskDatabase(path)
    with db.connect() as connection:
        connection.execute("INSERT INTO tasks(id,title,description,status,data_classification,"
                           "created_at,updated_at,error,metadata,timeout_seconds) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?)",
                           ("existing-task", "fixture", "fixture", "QUEUED", "PUBLIC",
                            1, 1, "", "{}", 10))
        connection.execute("DROP TABLE golden_trend_scans")
        connection.execute("UPDATE task_schema_version SET version=6")
    migrated = TaskDatabase(path)
    with migrated.connect() as connection:
        assert connection.execute("SELECT version FROM task_schema_version").fetchone()[0] == 7
        assert connection.execute("SELECT COUNT(*) FROM tasks WHERE id='existing-task'").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM golden_trend_scans").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM golden_analysis_results").fetchone()[0] == 0


def test_recovery_has_no_market_or_provider_dependencies(repo, monkeypatch):
    scan = _scan(1)
    repo.save(scan, ACTOR, 0)
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: pytest.fail("network used"))
    before = repo.database.path.stat().st_mtime_ns
    assert repo.latest(ACTOR)["scan"]["summary"]["pending"] == 1
    assert repo.get(scan["scan_id"], ACTOR)["revision"] == 1
    assert repo.database.path.stat().st_mtime_ns == before
    with repo.database.read_only() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM golden_trend_scans")


def test_desktop_snapshot_route_uses_existing_auth_without_registry_touch():
    auth = MagicMock()
    auth.authenticate.return_value = SimpleNamespace(
        authenticated=True, client_info={"device_type": "desktop", "device_id": "fixture"})
    perimeter = HttpPerimeter(auth_manager=auth,
                              runtime_profile_provider=lambda: WEB_AI_SAFE_PROFILE)
    headers = {"Authorization": "Bearer fixture-token"}
    decision = perimeter.authorize("POST", "/api/jarvis/golden/trend-scan",
                                   headers, "127.0.0.1")
    assert decision.allowed is True
    assert decision.context["actor_id"] == "device:fixture"
    auth.authenticate.assert_called_once_with(
        "fixture-token", source_ip="127.0.0.1", update_device_last_seen=False)
    auth.reset_mock()
    assert perimeter.authorize("POST", "/api/jarvis/golden/trend-scan",
                               headers, "192.0.2.10").allowed is False
    auth.authenticate.assert_not_called()


def test_canonical_tool_save_and_recover_are_device_scoped_and_audited(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        scan = _scan(4)
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "fixture-correlation"}
        service._active_audit_context = {**context, "actor_id": "device:unrelated-request"}
        service.golden_panel_market_snapshot = lambda **_kwargs: pytest.fail("MT5 read")
        service.generate_response = lambda *_args, **_kwargs: pytest.fail("model call")
        created = service.execute_tool("golden_trend_scan_save",
                                       {"scan": scan, "base_revision": 0},
                                       request_audit_context=context)
        assert created["ok"] is True and created["persisted"] is True
        recovered = service.execute_tool("golden_trend_scan_recover", {},
                                         request_audit_context=context)
        assert recovered["found"] is True
        assert recovered["data"]["scan"]["scan_id"] == scan["scan_id"]
        other_context = {**context, "actor_id": "device:other"}
        assert service.execute_tool("golden_trend_scan_recover", {},
                                    request_audit_context=other_context)["found"] is False
        service.security.rules["golden_trend_scan_save"] = "deny"
        assert service.execute_tool("golden_trend_scan_save",
                                    {"scan": scan, "base_revision": 1},
                                    request_audit_context=context)["ok"] is False
        with service.audit._connect() as db:
            rows = db.execute("SELECT arguments,result FROM jarvis_audit "
                              "WHERE tool IN ('golden_trend_scan_save','golden_trend_scan_recover')").fetchall()
        assert rows
        assert all("Fixture FX000" not in str(row[0]) for row in rows)
        assert any("PERSISTIDO" in str(row[1]) for row in rows)
        assert any("RECUPERADO" in str(row[1]) for row in rows)
    finally:
        service.close()


def test_apply_batch_reuses_save_authority_and_rejects_actor_or_batch_mismatch(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        scan = _scan(4)
        for index, item in enumerate(scan["items"]):
            item["state"] = "AVALIADO"
            item["result"] = _ranked(item["asset"], index + 1)
            item["batch_index"] = 0
        scan["next_batch_index"] = 1
        scan["summary"] = _summary(scan["items"])
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "apply-batch-fixture"}
        pending = _scan(4)
        created = service.execute_tool(
            "golden_trend_scan_save", {"scan": pending, "base_revision": 0},
            request_audit_context=context)
        assert created["ok"] is True and created["revision"] == 1
        scan["scan_id"] = pending["scan_id"]
        applied = service.execute_tool(
            "golden_trend_scan_apply_batch",
            {"scan": scan, "base_revision": 1, "batch_index": 0,
             "batch_asset_ids": [item["asset"]["provider_asset_id"] for item in scan["items"]]},
            request_audit_context=context)
        assert applied["ok"] is True and applied["persisted"] is True
        duplicate = service.execute_tool(
            "golden_trend_scan_apply_batch",
            {"scan": scan, "base_revision": 1, "batch_index": 0,
             "batch_asset_ids": [item["asset"]["provider_asset_id"] for item in scan["items"]]},
            request_audit_context=context)
        assert duplicate["duplicate"] is True
        mismatch = service.execute_tool(
            "golden_trend_scan_apply_batch",
            {"scan": scan, "base_revision": 0, "batch_index": 0,
             "batch_asset_ids": ["mt5:OTHER"]}, request_audit_context=context)
        assert mismatch["error_code"] == "BATCH_IDENTITY_MISMATCH"
    finally:
        service.close()


def test_apply_batch_results_is_headless_and_idempotent(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        scan = _scan(4)
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "headless-fixture"}
        created = service.execute_tool(
            "golden_trend_scan_save", {"scan": scan, "base_revision": 0},
            request_audit_context=context)
        results = [_ranked(item["asset"], index + 1) for index, item in enumerate(scan["items"])]
        ids = [item["asset"]["provider_asset_id"] for item in scan["items"]]
        applied = service.execute_tool(
            "golden_trend_scan_apply_batch_results",
            {"scan_id": scan["scan_id"], "base_revision": created["revision"],
             "batch_index": 0, "batch_asset_ids": ids, "results": results},
            request_audit_context=context)
        assert applied["ok"] is True and applied["persisted"] is True
        duplicate = service.execute_tool(
            "golden_trend_scan_apply_batch_results",
            {"scan_id": scan["scan_id"], "base_revision": created["revision"],
             "batch_index": 0, "batch_asset_ids": ids, "results": results},
            request_audit_context=context)
        assert duplicate["duplicate"] is True
        conflict = service.execute_tool(
            "golden_trend_scan_apply_batch_results",
            {"scan_id": scan["scan_id"], "base_revision": 1,
             "batch_index": 1, "batch_asset_ids": ids, "results": results},
            request_audit_context=context)
        assert conflict["error_code"] == "STALE_SCAN_REVISION"
        assert service.execute_tool(
            "golden_trend_scan_recover", {},
            request_audit_context={**context, "actor_id": "device:other"})["found"] is False
    finally:
        service.close()


def test_task_manager_uses_headless_canonical_apply_callback(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        scan = _scan(2)
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "monitor-headless"}
        created = service.execute_tool(
            "golden_trend_scan_save", {"scan": scan, "base_revision": 0},
            request_audit_context=context)
        assets = [item["asset"] for item in scan["items"]]
        service.golden_panel_trend_ranking = lambda batch, **_kwargs: {
            "ok": True, "data": {"ranked_assets": [_ranked(asset, 20)
                                                     for asset in batch]}}
        service.golden_trend_scan_apply_batch_results = lambda **kwargs: {
            "ok": True, "persisted": True, "revision": kwargs["base_revision"] + 1}
        service.task_manager.start_market_monitor(ACTOR)
        result = service.process_market_monitor_batch(
            ACTOR, scan["scan_id"], created["revision"], assets, batch_index=0)
        assert result["status"] == "BATCH_PERSISTED"
        assert result["next_batch_index"] == 1
        assert service.task_manager.monitor_status(ACTOR)["last_confirmed_batch"] == 0
    finally:
        service.close()


def test_monitor_uses_frozen_asset_identity_and_rejects_unknown_assets(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        scan = _scan(4)
        sources = ["MT5_TRADE_CALC_MODE", "MT5_TRADE_CALC_MODE",
                   "MT5_TRADE_CALC_MODE", "MT5_SYMBOL_PATH_GROUP"]
        for item, source in zip(scan["items"], sources):
            item["asset"]["provider_symbol"] = ["EURAUD", "EURCAD", "EURCHF", "EURGBP"][
                scan["items"].index(item)]
            item["asset"]["provider_asset_id"] = "mt5:" + item["asset"]["provider_symbol"]
            item["asset"]["display_symbol"] = item["asset"]["provider_symbol"]
            item["asset"]["asset_class_source"] = source
        canonical = "\n".join("\0".join((item["asset"]["provider_asset_id"],
                                             item["asset"]["provider_symbol"],
                                             item["asset"]["asset_class"]))
                              for item in scan["items"])
        scan["universe_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "monitor-identity"}
        created = service.execute_tool(
            "golden_trend_scan_save", {"scan": scan, "base_revision": 0},
            request_audit_context=context)
        service.task_manager.start_market_monitor(ACTOR)
        captured = []
        service.golden_panel_trend_ranking = lambda batch, **_kwargs: (
            captured.extend(batch) or {
                "ok": True, "data": {"ranked_assets": [
                    _ranked(asset, 20) for asset in batch]}})
        service.golden_trend_scan_apply_batch_results = lambda **kwargs: {
            "ok": True, "persisted": True, "revision": kwargs["base_revision"] + 1}

        requested = [copy.deepcopy(item["asset"]) for item in scan["items"]]
        requested[0]["display_name"] = "CLIENT VALUE MUST NOT WIN"
        result = service.process_market_monitor_batch(
            ACTOR, scan["scan_id"], created["revision"], requested, batch_index=0)
        assert result["status"] == "BATCH_PERSISTED"
        assert captured[0] == scan["items"][0]["asset"]
        assert captured[0]["display_name"] != "CLIENT VALUE MUST NOT WIN"
        assert [item["asset_class_source"] for item in captured] == sources

        before = service.task_manager.monitor_status(ACTOR)
        rejected = service.process_market_monitor_batch(
            ACTOR, scan["scan_id"], created["revision"],
            [{**scan["items"][0]["asset"], "provider_asset_id": "mt5:NOT_IN_SCAN"}],
            batch_index=1)
        after = service.task_manager.monitor_status(ACTOR)
        assert rejected["error_code"] == "RESULT_IDENTITY_MISMATCH"
        assert after["last_confirmed_batch"] == before["last_confirmed_batch"]
    finally:
        service.close()


def test_one_shot_monitor_action_uses_authenticated_actor_and_running_monitor(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        scan = _scan(2)
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "monitor-action"}
        created = service.execute_tool(
            "golden_trend_scan_save", {"scan": scan, "base_revision": 0},
            request_audit_context=context)
        assets = [item["asset"] for item in scan["items"]]
        service.task_manager.start_market_monitor(ACTOR)
        service.golden_panel_trend_ranking = lambda batch, **_kwargs: {
            "ok": True, "data": {"ranked_assets": [_ranked(asset, 20)
                                                     for asset in batch]}}
        service.golden_trend_scan_apply_batch_results = lambda **kwargs: {
            "ok": True, "persisted": True, "revision": kwargs["base_revision"] + 1}
        result = service.execute_tool(
            "golden_trend_scan_monitor_batch",
            {"scan_id": scan["scan_id"], "base_revision": created["revision"],
             "batch_index": 0, "assets": assets},
            request_audit_context=context)
        assert result["ok"] is True, result
        assert result["status"] == "BATCH_PERSISTED"
        assert service.task_manager.monitor_status(ACTOR)["last_confirmed_batch"] == 0

        service.task_manager.stop_market_monitor(ACTOR)
        blocked = service.execute_tool(
            "golden_trend_scan_monitor_batch",
            {"scan_id": scan["scan_id"], "base_revision": created["revision"],
             "batch_index": 1, "assets": assets}, request_audit_context=context)
        assert blocked["status"] == "MONITOR_NOT_RUNNING"
    finally:
        service.close()


def test_monitor_start_is_authenticated_idempotent_and_requires_own_scan(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "monitor-start"}
        blocked = service.execute_tool("golden_trend_monitor_start", {},
                                       request_audit_context=context)
        assert blocked["error_code"] == "COMPATIBLE_SCAN_NOT_FOUND"
        scan = _scan(1)
        created = service.execute_tool(
            "golden_trend_scan_save", {"scan": scan, "base_revision": 0},
            request_audit_context=context)
        started = service.execute_tool("golden_trend_monitor_start", {},
                                       request_audit_context=context)
        again = service.execute_tool("golden_trend_monitor_start", {},
                                     request_audit_context=context)
        assert started["ok"] is True, started
        assert started["scan_id"] == scan["scan_id"]
        assert started["revision"] == created["revision"]
        assert started["monitor"]["monitor_state"] == "RUNNING"
        assert again["monitor"]["task_id"] == started["monitor"]["task_id"]
        assert service.task_manager.monitor_status(ACTOR)["scan_id"] == scan["scan_id"]
    finally:
        service.close()


def test_monitor_status_is_successfully_verified_without_market_reads(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        context = {"route": "/api/jarvis/golden/trend-scan", "actor_id": ACTOR,
                   "correlation_id": "monitor-status"}
        scan = _scan(1)
        service.execute_tool(
            "golden_trend_scan_save", {"scan": scan, "base_revision": 0},
            request_audit_context=context)
        service.execute_tool("golden_trend_monitor_start", {},
                             request_audit_context=context)
        status = service.execute_tool("golden_trend_monitor_status", {},
                                      request_audit_context=context)
        assert status["ok"] is True
        assert status["verified"] is True
        assert status["verification"] == "monitor_state"
        assert status["monitor_state"] == "RUNNING"
        assert status["state"] == "IDLE"
    finally:
        service.close()
