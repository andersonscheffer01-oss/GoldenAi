"""Append-only SQLite journal for reproducible arena evidence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class ArenaJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                    strategy_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    agent TEXT NOT NULL, event_index INTEGER NOT NULL, payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    agent TEXT NOT NULL, payload_json TEXT NOT NULL
                );
                """
            )

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def start_run(self, run_id: str, symbol: str, strategy_version: str) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO runs(run_id,symbol,strategy_version) VALUES(?,?,?)",
                (str(run_id), str(symbol).upper(), str(strategy_version)),
            )

    def record_signal(self, run_id: str, agent: str, event_index: int, payload: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO signals(run_id,agent,event_index,payload_json) VALUES(?,?,?,?)",
                (str(run_id), str(agent), int(event_index), json.dumps(payload, sort_keys=True)),
            )

    def record_trade(self, run_id: str, payload: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO trades(run_id,agent,payload_json) VALUES(?,?,?)",
                (str(run_id), str(payload.get("agent") or ""), json.dumps(payload, sort_keys=True)),
            )

    def count(self, table: str) -> int:
        if table not in {"runs", "signals", "trades"}:
            raise ValueError("TABLE_NOT_ALLOWED")
        with self._connect() as db:
            return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def trades(self, run_id: str, agent: str | None = None) -> list[dict]:
        query = "SELECT payload_json FROM trades WHERE run_id=?"
        params = [str(run_id)]
        if agent:
            query += " AND agent=?"
            params.append(str(agent))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [json.loads(row[0]) for row in rows]


__all__ = ["ArenaJournal"]


