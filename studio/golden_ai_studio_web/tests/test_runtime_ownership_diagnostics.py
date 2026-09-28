from pathlib import Path

from jarvis_core.runtime_ownership import (
    CANONICAL_TASK_DB,
    RuntimeOwnershipDiagnostic,
    describe_task_database,
)
from jarvis_core.task_manager.database import TaskDatabase


def test_canonical_absolute_task_db_is_recognized():
    report = describe_task_database(CANONICAL_TASK_DB)
    assert report["status"] == "CANONICAL"
    assert report["matches_canonical"] is True


def test_noncanonical_absolute_task_db_is_reported_without_opening_it(tmp_path):
    path = tmp_path / "golden_tasks.db"
    report = describe_task_database(path)
    assert report["status"] == "NONCANONICAL"
    assert report["finding"] == "NONCANONICAL_TASK_DB_RESOLUTION"
    assert not path.exists()


def test_relative_task_db_resolution_is_explicit_and_cwd_dependent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = describe_task_database("golden_tasks.db")
    assert Path(report["resolved_absolute_path"]) == (tmp_path / "golden_tasks.db").resolve()
    assert report["status"] == "NONCANONICAL"
    assert not (tmp_path / "golden_tasks.db").exists()


def test_task_database_exposes_requested_and_resolved_paths(tmp_path):
    requested = tmp_path / "nested" / "golden_tasks.db"
    database = TaskDatabase(requested)
    assert database.requested_path == requested
    assert database.path == requested.resolve()
    assert database.ownership_diagnostic["status"] == "NONCANONICAL"
    assert database.ownership_diagnostic["caller"].endswith("TaskDatabase")


def test_owner_classification_handles_compatibility_and_unknown():
    class RootPermission:
        __module__ = "core.permissions"

    class ForeignOwner:
        pass

    root = RuntimeOwnershipDiagnostic.owner(
        "security", RootPermission(), "jarvis_core.security.SecurityManager")
    unknown = RuntimeOwnershipDiagnostic.owner(
        "security", ForeignOwner(), "jarvis_core.security.SecurityManager")
    assert root["status"] == "COMPATIBILITY"
    assert unknown["status"] == "UNKNOWN"


def test_diagnostic_failure_is_fail_open():
    report = RuntimeOwnershipDiagnostic.inspect_service(object())
    assert report["component"] == "runtime_ownership"
    assert report["findings"]
    assert report["findings"] == ["TASK_DATABASE_UNAVAILABLE"]
