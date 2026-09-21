from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.config import load_settings


class ExperimentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExperimentRepository:
    def __init__(self, db_path: str | Path | None = None):
        settings = load_settings()
        self.db_path = Path(db_path) if db_path else settings.data_dir / "golden_ai.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    parent_experiment_id TEXT,
                    title TEXT NOT NULL,
                    hypothesis TEXT,
                    status TEXT NOT NULL,
                    domain TEXT,
                    symbol TEXT,
                    timeframe TEXT,
                    dataset_id TEXT,
                    code_version TEXT,
                    parameters_json TEXT,
                    metrics_json TEXT,
                    validation_method TEXT,
                    conclusion TEXT,
                    limitations TEXT,
                    artifact_path TEXT
                );
                CREATE TABLE IF NOT EXISTS experiment_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    experiment_id TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    artifact_type TEXT,
                    sha256 TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_experiment(
        self,
        title: str,
        hypothesis: str = "",
        status: ExperimentStatus = ExperimentStatus.PENDING,
        **fields: Any,
    ) -> str:
        experiment_id = fields.pop("experiment_id", str(uuid.uuid4()))
        row = {
            "experiment_id": experiment_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "parent_experiment_id": fields.get("parent_experiment_id"),
            "title": title,
            "hypothesis": hypothesis,
            "status": status.value,
            "domain": fields.get("domain"),
            "symbol": fields.get("symbol"),
            "timeframe": fields.get("timeframe"),
            "dataset_id": fields.get("dataset_id"),
            "code_version": fields.get("code_version"),
            "parameters_json": json.dumps(fields.get("parameters", {}), ensure_ascii=False),
            "metrics_json": json.dumps(fields.get("metrics", {}), ensure_ascii=False),
            "validation_method": fields.get("validation_method"),
            "conclusion": fields.get("conclusion"),
            "limitations": fields.get("limitations"),
            "artifact_path": fields.get("artifact_path"),
        }
        columns = ", ".join(row)
        placeholders = ", ".join("?" for _ in row)
        conn = self.connect()
        try:
            conn.execute(
                f"INSERT INTO experiments ({columns}) VALUES ({placeholders})",
                list(row.values()),
            )
            conn.commit()
        finally:
            conn.close()
        return experiment_id

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM experiments WHERE experiment_id = ?",
                (experiment_id,),
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row else None

    def add_artifact(
        self,
        experiment_id: str,
        artifact_path: str,
        artifact_type: str = "",
        sha256: str = "",
    ) -> str:
        artifact_id = str(uuid.uuid4())
        conn = self.connect()
        try:
            conn.execute(
                """
                INSERT INTO experiment_artifacts (
                    artifact_id, experiment_id, artifact_path, artifact_type, sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    experiment_id,
                    artifact_path,
                    artifact_type,
                    sha256,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return artifact_id
