from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return str(uuid.uuid4())


@dataclass
class ProjectTestResult:
    runner: str
    command: list[str]
    cwd: str
    exit_code: int
    status: str
    duration_ms: int
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    stdout: str = ""
    stderr: str = ""
    output_path: str = ""


@dataclass
class ProjectFileManifest:
    path: str
    original_hash: str
    working_hash: str = ""
    diff_hash: str = ""
    status: str = "UNCHANGED"
    checkpoint_id: str = ""
    validation_status: str = ""


@dataclass
class ProjectMap:
    project_root: str
    files: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    imports: dict[str, list[str]] = field(default_factory=dict)
    related_files: list[str] = field(default_factory=list)


@dataclass
class CodingProjectTask:
    task_id: str
    created_at: str
    updated_at: str
    status: str
    user_request: str
    project_root: str
    files_in_scope: list[str] = field(default_factory=list)
    source_hashes: dict[str, str] = field(default_factory=dict)
    workspace_path: str = ""
    analysis: str = ""
    plan: str = ""
    affected_files: list[str] = field(default_factory=list)
    diff_hashes: dict[str, str] = field(default_factory=dict)
    test_command: list[str] = field(default_factory=list)
    test_status: str = ""
    approval_status: str = "PENDING"
    approval_manifest_hash: str = ""
    checkpoint_ids: dict[str, str] = field(default_factory=dict)
    apply_status: str = ""
    rollback_status: str = ""
    iteration_count: int = 0
    result: str = ""
    project_map_json: str = "{}"
    manifest_json: str = "{}"

    def project_map(self) -> dict[str, Any]:
        return json.loads(self.project_map_json or "{}")

    def manifest(self) -> list[dict[str, Any]]:
        return json.loads(self.manifest_json or "[]")

    def to_row(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("files_in_scope", "source_hashes", "affected_files", "diff_hashes", "test_command", "checkpoint_ids"):
            data[key] = json.dumps(data[key], ensure_ascii=False, sort_keys=True)
        return data

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CodingProjectTask":
        data = dict(row)
        for key, default in (
            ("files_in_scope", []),
            ("source_hashes", {}),
            ("affected_files", []),
            ("diff_hashes", {}),
            ("test_command", []),
            ("checkpoint_ids", {}),
        ):
            raw = data.get(key)
            data[key] = json.loads(raw) if raw else default
        return cls(**data)


def approval_manifest_payload(task: CodingProjectTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "project_root": task.project_root,
        "affected_files": task.affected_files,
        "source_hashes": task.source_hashes,
        "diff_hashes": task.diff_hashes,
    }
