"""Single task-database path policy for production and isolated runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CANONICAL_WORKSPACE_ROOT = Path(r"C:\GoldenAI\studio\golden_ai_studio_web")
CANONICAL_TASK_DB = CANONICAL_WORKSPACE_ROOT / "jarvis" / "golden_tasks.db"


@dataclass(frozen=True)
class TaskDatabaseResolution:
    requested_path: Path
    resolved_path: Path
    classification: str
    matches_canonical: bool


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def resolve_task_database_path(base_dir=None, database_path=None,
                               runtime_mode="compatibility") -> TaskDatabaseResolution:
    """Resolve one task DB without opening it.

    Production is deliberately strict. Test and compatibility modes are
    explicit escape hatches for isolated fixtures and legacy callers.
    """
    mode = str(runtime_mode or "").strip().lower()
    canonical = _resolved(CANONICAL_TASK_DB)
    base = _resolved(base_dir) if base_dir is not None else None
    requested = _resolved(database_path) if database_path is not None else None

    if mode == "production":
        candidate = requested or canonical
        if candidate != canonical:
            raise ValueError("NONCANONICAL_PRODUCTION_TASK_DB")
        classification = "PRODUCTION_CANONICAL"
    elif mode in {"test", "explicit_test_database"}:
        if requested is None and base is None:
            raise ValueError("EXPLICIT_TEST_DATABASE_PATH_REQUIRED")
        candidate = requested or (base / "jarvis" / "golden_tasks.db")
        classification = "EXPLICIT_TEST_DATABASE"
    elif mode == "compatibility":
        if requested is None and base is None:
            raise ValueError("COMPATIBILITY_DATABASE_PATH_REQUIRED")
        candidate = requested or (base / "jarvis" / "golden_tasks.db")
        classification = "LEGACY_READ_ONLY" if candidate != canonical else "COMPATIBILITY_CANONICAL"
    else:
        raise ValueError("UNKNOWN_TASK_DATABASE_RUNTIME_MODE")

    resolved = _resolved(candidate)
    return TaskDatabaseResolution(
        requested_path=requested or resolved,
        resolved_path=resolved,
        classification=classification,
        matches_canonical=resolved == canonical,
    )


__all__ = ["CANONICAL_TASK_DB", "CANONICAL_WORKSPACE_ROOT",
           "TaskDatabaseResolution", "resolve_task_database_path"]
