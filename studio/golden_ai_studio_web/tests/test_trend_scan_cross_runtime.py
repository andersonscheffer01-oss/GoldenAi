import json
import subprocess

from jarvis_core.golden_trend_scan_repository import GoldenTrendScanRepository
from jarvis_core.task_manager.database import TaskDatabase


def test_js_fixture_is_accepted_by_python_repository(tmp_path):
    completed = subprocess.run(
        ["node", "tests/fixtures/emit_trend_scan_fixture.mjs"],
        capture_output=True, text=True, check=True,
    )
    scan = json.loads(completed.stdout)
    repo = GoldenTrendScanRepository(TaskDatabase(tmp_path / "golden_tasks.db"))
    saved = repo.save(scan, "device:cross-runtime-fixture", 0)
    assert saved["persisted"] is True
    restored = repo.get(scan["scan_id"], "device:cross-runtime-fixture")
    assert restored["scan"]["universe_hash"] == scan["universe_hash"]
    assert restored["scan"]["next_batch_index"] == 0


def test_cross_runtime_actor_and_frozen_universe_rejection(tmp_path):
    completed = subprocess.run(
        ["node", "tests/fixtures/emit_trend_scan_fixture.mjs"],
        capture_output=True, text=True, check=True,
    )
    scan = json.loads(completed.stdout)
    repo = GoldenTrendScanRepository(TaskDatabase(tmp_path / "golden_tasks.db"))
    repo.save(scan, "device:owner", 0)
    assert repo.get(scan["scan_id"], "device:other") is None
    changed = json.loads(json.dumps(scan))
    changed["items"][0]["asset"]["provider_symbol"] = "MUTATED"
    try:
        repo.save(changed, "device:owner", 1)
    except ValueError as exc:
        assert str(exc) in {"INVALID_ASSET_IDENTITY", "UNIVERSE_HASH_MISMATCH",
                            "FROZEN_ASSET_CONFLICT"}
    else:
        raise AssertionError("frozen universe mutation was accepted")
