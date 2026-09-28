import sqlite3

import pytest

from jarvis_core.task_manager import (
    CANONICAL_TASK_DB,
    TaskManager,
    resolve_task_database_path,
)


def test_production_task_db_is_fixed_and_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resolution = resolve_task_database_path(tmp_path, runtime_mode="production")

    assert resolution.resolved_path == CANONICAL_TASK_DB.resolve()
    assert resolution.classification == "PRODUCTION_CANONICAL"
    assert resolution.matches_canonical is True


def test_noncanonical_production_db_is_blocked_before_open_or_create(tmp_path):
    candidate = tmp_path / "golden_tasks.db"

    with pytest.raises(ValueError, match="NONCANONICAL_PRODUCTION_TASK_DB"):
        resolve_task_database_path(tmp_path, candidate, runtime_mode="production")

    assert not candidate.exists()


def test_explicit_test_database_is_allowed_and_classified(tmp_path):
    manager = TaskManager(tmp_path, runtime_mode="test")
    try:
        assert manager.database.path == (tmp_path / "jarvis" / "golden_tasks.db").resolve()
        assert manager.database.ownership_diagnostic["runtime_classification"] == \
            "EXPLICIT_TEST_DATABASE"
    finally:
        manager.finalize_shutdown()


def test_legacy_database_is_only_classified_and_bytes_remain_unchanged(tmp_path):
    legacy = tmp_path / "legacy" / "golden_tasks.db"
    legacy.parent.mkdir()
    with sqlite3.connect(legacy) as db:
        db.execute("CREATE TABLE legacy_marker(value TEXT)")
        db.execute("INSERT INTO legacy_marker VALUES ('preserve')")
    before = legacy.read_bytes()

    resolution = resolve_task_database_path(
        database_path=legacy, runtime_mode="compatibility")

    assert resolution.classification == "LEGACY_READ_ONLY"
    assert legacy.read_bytes() == before
