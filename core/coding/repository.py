from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import CodingTask, now_iso


class CodingRepository:
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
                CREATE TABLE IF NOT EXISTS coding_tasks (
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    workspace_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    analysis TEXT DEFAULT '',
                    plan TEXT DEFAULT '',
                    diff TEXT DEFAULT '',
                    diff_hash TEXT DEFAULT '',
                    validation_status TEXT DEFAULT '',
                    approval_status TEXT DEFAULT 'PENDING',
                    approval_token TEXT DEFAULT '',
                    checkpoint_id TEXT DEFAULT '',
                    result TEXT DEFAULT '',
                    rollback_status TEXT DEFAULT ''
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_task_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT DEFAULT ''
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    diff_hash TEXT NOT NULL,
                    approval_token TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    output TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS coding_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
                """
            )
            con.commit()
        finally:
            con.close()

    def save_task(self, task: CodingTask) -> None:
        data = asdict(task)
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        updates = ", ".join(f"{key}=excluded.{key}" for key in data if key != "task_id")
        con = self.connect()
        try:
            con.execute(
                f"INSERT INTO coding_tasks ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT(task_id) DO UPDATE SET {updates}",
                tuple(data.values()),
            )
            con.commit()
        finally:
            con.close()

    def get_task(self, task_id: str) -> CodingTask | None:
        row = self.fetchone("SELECT * FROM coding_tasks WHERE task_id = ?", (task_id,))
        return CodingTask(**dict(row)) if row else None

    def latest_awaiting_approval(self) -> CodingTask | None:
        row = self.fetchone(
            "SELECT * FROM coding_tasks WHERE status = 'AWAITING_APPROVAL' ORDER BY updated_at DESC LIMIT 1"
        )
        return CodingTask(**dict(row)) if row else None

    def add_file(self, task_id: str, role: str, path: str, sha256: str = "") -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT INTO coding_task_files(task_id, role, path, sha256) VALUES (?, ?, ?, ?)",
                (task_id, role, path, sha256),
            )
            con.commit()
        finally:
            con.close()

    def add_approval(self, task_id: str, source_path: str, source_hash: str, diff_hash: str, token: str, status: str) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT INTO coding_approvals(task_id, source_path, source_hash, diff_hash, approval_token, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, source_path, source_hash, diff_hash, token, status, now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def latest_approval(self, task_id: str):
        return self.fetchone(
            "SELECT * FROM coding_approvals WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        )

    def add_validation(self, task_id: str, phase: str, ok: bool, status: str, output: str = "") -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT INTO coding_validations(task_id, phase, ok, status, output, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, phase, 1 if ok else 0, status, output[:4000], now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def add_event(self, task_id: str, event_type: str, status: str, detail: str = "") -> None:
        con = self.connect()
        try:
            con.execute(
                "INSERT INTO coding_events(task_id, event_type, status, detail, timestamp) VALUES (?, ?, ?, ?, ?)",
                (task_id, event_type, status, detail[:2000], now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()):
        con = self.connect()
        try:
            return con.execute(sql, params).fetchone()
        finally:
            con.close()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        con = self.connect()
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()
