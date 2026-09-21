from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from core.tools.hashing import sha256_file


class CodingWorkspace:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.workspace_root = self.root / "workspace"
        self.projects_dir = self.root / "projetos"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def new_task_id(self) -> str:
        return str(uuid.uuid4())

    def is_inside(self, path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def is_authorized_source(self, path: str | Path) -> bool:
        source = Path(path).resolve()
        if not source.is_file():
            return False
        if not self.is_inside(source, self.projects_dir):
            return False
        if self.is_inside(source, self.root / "app"):
            return False
        if self.is_inside(source, self.root / "core"):
            return False
        if self.is_inside(source, self.root / "studio"):
            return False
        mt5_terminal = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        if mt5_terminal.exists() and self.is_inside(source, mt5_terminal):
            return False
        return source.suffix.lower() in {".py", ".mq5"}

    def language_for(self, path: str | Path) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix == ".mq5":
            return "mql5"
        return "unknown"

    def create(self, task_id: str, source_path: str | Path) -> dict:
        source = Path(source_path).resolve()
        task_root = self.workspace_root / task_id
        original_dir = task_root / "original"
        working_dir = task_root / "working"
        diff_dir = task_root / "diff"
        reports_dir = task_root / "reports"
        tests_dir = task_root / "tests"
        for folder in (original_dir, working_dir, diff_dir, reports_dir, tests_dir):
            folder.mkdir(parents=True, exist_ok=True)
        original = original_dir / source.name
        working = working_dir / source.name
        shutil.copy2(source, original)
        shutil.copy2(source, working)
        return {
            "task_root": str(task_root),
            "original": str(original),
            "working": str(working),
            "diff_dir": str(diff_dir),
            "reports_dir": str(reports_dir),
            "tests_dir": str(tests_dir),
            "source_hash": sha256_file(source),
            "original_hash": sha256_file(original),
            "working_hash": sha256_file(working),
        }

    def working_path(self, task_id: str, source_path: str | Path) -> Path:
        return self.workspace_root / task_id / "working" / Path(source_path).name

    def original_copy_path(self, task_id: str, source_path: str | Path) -> Path:
        return self.workspace_root / task_id / "original" / Path(source_path).name

    def diff_path(self, task_id: str) -> Path:
        return self.workspace_root / task_id / "diff" / "changes.diff"
