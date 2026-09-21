from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .project_models import CodingProjectTask, now_iso


class CodingProjectRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def migrate(self) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_project_tasks (
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    files_in_scope TEXT DEFAULT '[]',
                    source_hashes TEXT DEFAULT '{}',
                    workspace_path TEXT DEFAULT '',
                    analysis TEXT DEFAULT '',
                    plan TEXT DEFAULT '',
                    affected_files TEXT DEFAULT '[]',
                    diff_hashes TEXT DEFAULT '{}',
                    test_command TEXT DEFAULT '[]',
                    test_status TEXT DEFAULT '',
                    approval_status TEXT DEFAULT 'PENDING',
                    approval_manifest_hash TEXT DEFAULT '',
                    checkpoint_ids TEXT DEFAULT '{}',
                    apply_status TEXT DEFAULT '',
                    rollback_status TEXT DEFAULT '',
                    iteration_count INTEGER NOT NULL DEFAULT 0,
                    result TEXT DEFAULT '',
                    project_map_json TEXT DEFAULT '{}',
                    manifest_json TEXT DEFAULT '[]'
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_project_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_project_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    approval_manifest_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            con.commit()
        finally:
            con.close()

    def save_task(self, task: CodingProjectTask) -> None:
        data = task.to_row()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        updates = ", ".join(f"{key}=excluded.{key}" for key in data if key != "task_id")
        con = self.connect()
        try:
            con.execute(
                f"INSERT INTO coding_project_tasks ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT(task_id) DO UPDATE SET {updates}",
                tuple(data.values()),
            )
            con.commit()
        finally:
            con.close()

    def get_task(self, task_id: str) -> CodingProjectTask | None:
        row = self.fetchone("SELECT * FROM coding_project_tasks WHERE task_id = ?", (task_id,))
        return CodingProjectTask.from_row(dict(row)) if row else None

    def latest_open_task(self) -> CodingProjectTask | None:
        row = self.fetchone(
            "SELECT * FROM coding_project_tasks WHERE status IN ('AWAITING_APPROVAL','APPROVED','APPLYING') ORDER BY updated_at DESC LIMIT 1"
        )
        return CodingProjectTask.from_row(dict(row)) if row else None

    def add_event(self, task_id: str, event_type: str, status: str, detail: str = "") -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT INTO coding_project_events(task_id, event_type, status, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (task_id, event_type, status, detail[:4000], now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def add_approval(self, task_id: str, approval_manifest_hash: str, status: str) -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT INTO coding_project_approvals(task_id, approval_manifest_hash, status, timestamp) VALUES (?, ?, ?, ?)",
                (task_id, approval_manifest_hash, status, now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def latest_approval(self, task_id: str):
        return self.fetchone(
            "SELECT * FROM coding_project_approvals WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        )

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        con = self.connect()
        try:
            return con.execute(sql, params).fetchone()
        finally:
            con.close()
