from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import MarketAnalysisResult, now_iso


class MarketRepository:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.db_path = self.root / "data" / "golden_ai.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def migrate(self) -> None:
        con = self.connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    data_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_regimes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_level TEXT NOT NULL,
                    regime_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_multitimeframe (
                    context_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_observations (
                    observation_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    signal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    source TEXT NOT NULL,
                    result_hash TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            con.commit()
        finally:
            con.close()

    def save_analysis(self, result: MarketAnalysisResult) -> None:
        payload = asdict(result)
        created_at = result.created_at or now_iso()
        con = self.connect()
        try:
            for snapshot in result.snapshots:
                con.execute(
                    """
                    INSERT OR REPLACE INTO market_snapshots(
                        snapshot_id, symbol, timeframe, timestamp, snapshot_json, data_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_id,
                        snapshot.symbol,
                        snapshot.timeframe,
                        snapshot.timestamp,
                        json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True),
                        snapshot.data_hash,
                        snapshot.created_at,
                    ),
                )
            snapshot_by_timeframe = {snapshot.timeframe: snapshot.snapshot_id for snapshot in result.snapshots}
            for regime in result.regimes:
                con.execute(
                    """
                    INSERT INTO market_regimes(
                        snapshot_id, symbol, timeframe, regime, confidence, evidence_level, regime_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_by_timeframe.get(regime.timeframe, ""),
                        regime.symbol,
                        regime.timeframe,
                        regime.regime,
                        regime.confidence,
                        regime.evidence_level.value,
                        json.dumps(asdict(regime), ensure_ascii=False, sort_keys=True),
                        created_at,
                    ),
                )
            con.execute(
                """
                INSERT OR REPLACE INTO market_multitimeframe(context_id, symbol, context_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    result.analysis_id,
                    result.symbol,
                    json.dumps(asdict(result.mtf_context), ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            for observation in result.observations:
                con.execute(
                    """
                    INSERT OR REPLACE INTO market_observations(
                        observation_id, analysis_id, symbol, timeframe, evidence_level, observation_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation.observation_id,
                        result.analysis_id,
                        observation.symbol,
                        observation.timeframe,
                        observation.evidence_level.value,
                        json.dumps(asdict(observation), ensure_ascii=False, sort_keys=True),
                        created_at,
                    ),
                )
            for signal in result.signals:
                con.execute(
                    """
                    INSERT INTO market_signals(
                        analysis_id, symbol, timeframe, signal, evidence_level, signal_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.analysis_id,
                        signal.symbol,
                        signal.timeframe,
                        signal.signal,
                        signal.evidence_level.value,
                        json.dumps(asdict(signal), ensure_ascii=False, sort_keys=True),
                        created_at,
                    ),
                )
            con.execute(
                """
                INSERT OR REPLACE INTO market_analyses(
                    analysis_id, symbol, source, result_hash, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.analysis_id,
                    result.symbol,
                    result.source,
                    result.result_hash,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            con.commit()
        finally:
            con.close()

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        con = self.connect()
        try:
            row = con.execute("SELECT * FROM market_analyses WHERE analysis_id = ?", (analysis_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["report"] = json.loads(data["report_json"])
            return data
        finally:
            con.close()

    def list_analyses(self, limit: int = 10) -> list[dict[str, Any]]:
        con = self.connect()
        try:
            rows = con.execute(
                """
                SELECT analysis_id, symbol, source, result_hash, created_at
                FROM market_analyses
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            con.close()

    def get_latest_analysis(self) -> dict[str, Any] | None:
        rows = self.list_analyses(1)
        if not rows:
            return None
        return self.get_analysis(rows[0]["analysis_id"])
