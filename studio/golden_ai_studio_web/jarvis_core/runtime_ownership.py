"""Read-only runtime ownership and task-database diagnostics.

This module observes constructed objects and resolved paths. It never changes
ownership, opens a database, emits audit rows, or corrects a mismatch.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .task_manager.paths import CANONICAL_TASK_DB

_CANONICAL_OWNERS = {
    "core": "jarvis_core",
    "security": "jarvis_core.security.SecurityManager",
    "audit": "jarvis_core.audit.AuditLog",
    "task_manager": "jarvis_core.task_manager.manager.TaskManager",
    "model_router": "jarvis_core.orchestrator.model_router.ModelRouter",
}


def _identity(value: Any) -> str:
    cls = value if isinstance(value, type) else type(value)
    return f"{cls.__module__}.{cls.__qualname__}"


def _status(observed: str, expected: str) -> str:
    if not observed:
        return "UNKNOWN"
    if observed == expected:
        return "CANONICAL"
    if observed.startswith("core.") or observed.startswith("app."):
        return "COMPATIBILITY"
    if observed.startswith("jarvis_core."):
        return "NONCANONICAL"
    return "UNKNOWN"


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def describe_task_database(requested_path: str | Path,
                           resolved_path: str | Path | None = None,
                           caller: str = "") -> dict[str, Any]:
    """Describe a task DB path without opening or modifying it."""
    requested = Path(requested_path).expanduser()
    resolved = _resolved(resolved_path if resolved_path is not None else requested)
    canonical = _resolved(CANONICAL_TASK_DB)
    matches = os.path.normcase(str(resolved)) == os.path.normcase(str(canonical))
    return {
        "component": "task_database",
        "requested_path": str(requested),
        "resolved_absolute_path": str(resolved),
        "canonical_path": str(canonical),
        "matches_canonical": matches,
        "status": "CANONICAL" if matches else "NONCANONICAL",
        "caller": str(caller or ""),
        "finding": "" if matches else "NONCANONICAL_TASK_DB_RESOLUTION",
    }


class RuntimeOwnershipDiagnostic:
    """Bounded, fail-open ownership report for an already-built runtime."""

    @staticmethod
    def owner(component: str, value: Any, expected: str | None = None) -> dict[str, str]:
        observed = _identity(value) if value is not None else ""
        expected = expected or _CANONICAL_OWNERS.get(component, "")
        return {"observed": observed, "expected": expected,
                "status": _status(observed, expected)}

    @classmethod
    def inspect_task_manager(cls, manager: Any) -> dict[str, Any]:
        try:
            database = getattr(manager, "database", None)
            if database is None:
                return {"status": "UNKNOWN", "finding": "TASK_DATABASE_UNAVAILABLE"}
            report = getattr(database, "ownership_diagnostic", None)
            if isinstance(report, dict):
                result = dict(report)
                result["caller"] = _identity(manager)
                return result
            path = getattr(database, "path", "")
            return describe_task_database(path, path, _identity(manager))
        except Exception as exc:
            return {"status": "UNKNOWN", "finding": "DIAGNOSTIC_FAILURE",
                    "error_type": type(exc).__name__}

    @classmethod
    def inspect_service(cls, service: Any, entrypoint: str = "") -> dict[str, Any]:
        """Return secret-free ownership data; never raise on diagnostics."""
        try:
            orchestrator = getattr(service, "orchestrator", None)
            models = getattr(orchestrator, "models", None)
            memory = getattr(service, "memory", None)
            task_manager = getattr(service, "task_manager", None)
            owners = {
                "core": {"observed": "jarvis_core", "expected": "jarvis_core",
                          "status": "CANONICAL"},
                "security": cls.owner("security", getattr(service, "security", None)),
                "audit": cls.owner("audit", getattr(service, "audit", None)),
                "task_manager": cls.owner("task_manager", task_manager),
                "model_router": cls.owner("model_router", models),
                "memory": {"observed": _identity(memory) if memory else "",
                            "expected": "jarvis_core.memory.GoldenMemoryManager + V2",
                            "status": "CANONICAL" if memory else "UNKNOWN"},
            }
            task_db = cls.inspect_task_manager(task_manager)
            compatibility = []
            for name in ("permission_manager", "execution_service", "plugin_registry"):
                value = getattr(service, name, None)
                if value is not None:
                    compatibility.append({"component": name, "owner": _identity(value),
                                          "status": "COMPATIBILITY"})
            findings = []
            if task_db.get("finding"):
                findings.append(task_db["finding"])
            return {
                "component": "runtime_ownership",
                "process_id": os.getpid(),
                "entrypoint": str(entrypoint or ""),
                "owners": owners,
                "task_database": task_db,
                "compatibility_owners": compatibility,
                "findings": findings,
            }
        except Exception as exc:
            return {
                "component": "runtime_ownership",
                "process_id": os.getpid(),
                "entrypoint": str(entrypoint or ""),
                "owners": {}, "task_database": {},
                "compatibility_owners": [],
                "findings": ["DIAGNOSTIC_FAILURE"],
                "error_type": type(exc).__name__,
            }


__all__ = ["CANONICAL_TASK_DB", "RuntimeOwnershipDiagnostic",
           "describe_task_database"]
