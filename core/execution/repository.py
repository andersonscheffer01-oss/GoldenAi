from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ApprovalRequest, ExecutionEvent, PermissionMode, now_iso


class ExecutionRepository:
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
                CREATE TABLE IF NOT EXISTS execution_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT DEFAULT '',
                    target TEXT DEFAULT '',
                    agent TEXT DEFAULT '',
                    tool_name TEXT DEFAULT '',
                    permission_level TEXT DEFAULT '',
                    risk_level TEXT DEFAULT '',
                    duration_ms INTEGER,
                    metadata_json TEXT DEFAULT '{}'
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_requests (
                    request_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    operation_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT DEFAULT '',
                    reason TEXT DEFAULT '',
                    risk_level TEXT NOT NULL,
                    permission_level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    decided_at TEXT DEFAULT '',
                    scope TEXT DEFAULT '',
                    consumed INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}'
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_execution_events_task ON execution_events(task_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_approval_task ON approval_requests(task_id)")
            con.commit()
        finally:
            con.close()

    def get_mode(self) -> str:
        row = self.fetchone("SELECT value FROM execution_settings WHERE key = 'permission_mode'")
        return str(row["value"]) if row else PermissionMode.READ_ONLY.value

    def set_mode(self, mode: str) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT INTO execution_settings(key, value, updated_at)
                VALUES ('permission_mode', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (mode, now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def add_event(self, event: ExecutionEvent) -> None:
        data = asdict(event)
        metadata = json.dumps(data.pop("metadata"), ensure_ascii=False, sort_keys=True)
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO execution_events (
                    event_id, task_id, timestamp, category, action, status, summary,
                    details, target, agent, tool_name, permission_level, risk_level,
                    duration_ms, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["event_id"], data["task_id"], data["timestamp"], data["category"],
                    data["action"], data["status"], data["summary"], data["details"],
                    data["target"], data["agent"], data["tool_name"], data["permission_level"],
                    data["risk_level"], data["duration_ms"], metadata,
                ),
            )
            con.commit()
        finally:
            con.close()

    def add_request(self, request: ApprovalRequest) -> None:
        data = asdict(request)
        metadata = json.dumps(data.pop("metadata"), ensure_ascii=False, sort_keys=True)
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO approval_requests (
                    request_id, task_id, operation_key, action, target, reason,
                    risk_level, permission_level, status, created_at, decided_at,
                    scope, consumed, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["request_id"], data["task_id"], data["operation_key"],
                    data["action"], data["target"], data["reason"], data["risk_level"],
                    data["permission_level"], data["status"], data["created_at"],
                    data["decided_at"], data["scope"], 1 if data["consumed"] else 0,
                    metadata,
                ),
            )
            con.commit()
        finally:
            con.close()

    def update_request(self, request_id: str, status: str, scope: str = "", consumed: bool | None = None) -> None:
        fields = ["status = ?", "decided_at = ?"]
        params: list[Any] = [status, now_iso()]
        if scope:
            fields.append("scope = ?")
            params.append(scope)
        if consumed is not None:
            fields.append("consumed = ?")
            params.append(1 if consumed else 0)
        params.append(request_id)
        con = self.connect()
        try:
            con.execute(f"UPDATE approval_requests SET {', '.join(fields)} WHERE request_id = ?", tuple(params))
            con.commit()
        finally:
            con.close()

    def pending_equivalent(self, task_id: str, operation_key: str) -> sqlite3.Row | None:
        return self.fetchone(
            """
            SELECT * FROM approval_requests
            WHERE task_id = ? AND operation_key = ? AND status = 'PENDING'
            ORDER BY created_at DESC LIMIT 1
            """,
            (task_id, operation_key),
        )

    def granted_once(self, task_id: str, operation_key: str) -> sqlite3.Row | None:
        return self.fetchone(
            """
            SELECT * FROM approval_requests
            WHERE task_id = ? AND operation_key = ? AND status = 'GRANTED_ONCE' AND consumed = 0
            ORDER BY decided_at DESC LIMIT 1
            """,
            (task_id, operation_key),
        )

    def granted_for_task(self, task_id: str, operation_key: str) -> sqlite3.Row | None:
        return self.fetchone(
            """
            SELECT * FROM approval_requests
            WHERE task_id = ? AND operation_key = ? AND status = 'GRANTED_TASK'
            ORDER BY decided_at DESC LIMIT 1
            """,
            (task_id, operation_key),
        )

    def latest_events(self, task_id: str = "", limit: int = 50) -> list[sqlite3.Row]:
        if task_id:
            return self.fetchall(
                "SELECT * FROM execution_events WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
                (task_id, limit),
            )
        return self.fetchall("SELECT * FROM execution_events ORDER BY timestamp DESC LIMIT ?", (limit,))

    def latest_requests(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.fetchall("SELECT * FROM approval_requests ORDER BY created_at DESC LIMIT ?", (limit,))

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
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
