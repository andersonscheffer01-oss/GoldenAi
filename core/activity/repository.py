from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ActivityEvent


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


class ActivityRepository:
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
                CREATE TABLE IF NOT EXISTS activity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT UNIQUE,
                    source TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    conversation_id TEXT,
                    actor TEXT,
                    tool TEXT,
                    status TEXT,
                    permission_class TEXT,
                    project_path TEXT,
                    model TEXT,
                    metadata_json TEXT DEFAULT '{}'
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    metadata_json TEXT DEFAULT '{}'
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS token_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT UNIQUE,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    conversation_id TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    exact INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS tool_usage_daily (
                    day TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    calls INTEGER NOT NULL DEFAULT 0,
                    allowed INTEGER NOT NULL DEFAULT 0,
                    denied INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(day, tool)
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_activity_events_ts ON activity_events(timestamp)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_activity_events_type ON activity_events(event_type)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_activity_events_tool ON activity_events(tool)")
            con.commit()
        finally:
            con.close()

    def insert_event(self, event_key: str, event: ActivityEvent) -> None:
        self.insert_events_batch([(event_key, event)])

    def insert_events_batch(self, items: list[tuple[str, ActivityEvent]]) -> None:
        if not items:
            return
        con = self.connect()
        try:
            con.executemany(
                """
                INSERT OR IGNORE INTO activity_events (
                    event_key, source, event_type, timestamp, session_id,
                    conversation_id, actor, tool, status, permission_class,
                    project_path, model, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        key,
                        event.source,
                        event.event_type,
                        to_iso(event.timestamp),
                        event.session_id,
                        event.conversation_id,
                        event.actor,
                        event.tool,
                        event.status,
                        event.permission_class,
                        event.project_path,
                        event.model,
                        event.metadata_json,
                    )
                    for key, event in items
                ],
            )
            con.commit()
        finally:
            con.close()

    def start_session(self, session_id: str) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR IGNORE INTO chat_sessions(session_id, started_at, metadata_json)
                VALUES (?, ?, '{}')
                """,
                (session_id, utc_now_iso()),
            )
            con.commit()
        finally:
            con.close()

    def end_session(self, session_id: str) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                UPDATE chat_sessions
                SET ended_at = COALESCE(ended_at, ?)
                WHERE session_id = ?
                """,
                (utc_now_iso(), session_id),
            )
            con.commit()
        finally:
            con.close()

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        con = self.connect()
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        con = self.connect()
        try:
            return con.execute(sql, params).fetchone()
        finally:
            con.close()
