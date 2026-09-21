from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import EvidenceType, KnowledgeItem


class KnowledgeRepository:
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
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    knowledge_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_location TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    validation_status TEXT NOT NULL,
                    supersedes_id TEXT,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_links (
                    link_id TEXT PRIMARY KEY,
                    source_knowledge_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_revisions (
                    revision_id TEXT PRIMARY KEY,
                    knowledge_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    previous_json TEXT,
                    current_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    knowledge_a TEXT NOT NULL,
                    knowledge_b TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge_items(topic);
                CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_items(source_type, source_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_evidence ON knowledge_items(evidence_level);
                """
            )
            con.commit()
        finally:
            con.close()

    def save(self, item: KnowledgeItem) -> KnowledgeItem:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO knowledge_items(
                    knowledge_id, topic, statement, evidence_level, evidence_type, source_type,
                    source_id, source_location, confidence, validation_status, supersedes_id,
                    tags_json, metadata_json, archived, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.knowledge_id,
                    item.topic,
                    item.statement,
                    item.normalized_evidence_level(),
                    item.evidence_type.value if isinstance(item.evidence_type, EvidenceType) else str(item.evidence_type),
                    str(item.source_type),
                    item.source_id,
                    item.source_location,
                    float(item.confidence),
                    item.validation_status,
                    item.supersedes_id,
                    json.dumps(item.tags, ensure_ascii=False, sort_keys=True),
                    json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
                    1 if item.archived else 0,
                    item.created_at,
                    item.updated_at,
                ),
            )
            con.commit()
            return item
        finally:
            con.close()

    def add_revision(self, revision_id: str, knowledge_id: str, action: str, current: dict[str, Any], created_at: str, previous: dict[str, Any] | None = None) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT INTO knowledge_revisions(revision_id, knowledge_id, action, previous_json, current_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    knowledge_id,
                    action,
                    json.dumps(previous, ensure_ascii=False, sort_keys=True) if previous else None,
                    json.dumps(current, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            con.commit()
        finally:
            con.close()

    def add_link(self, link_id: str, knowledge_id: str, target_type: str, target_id: str, relationship: str, metadata: dict[str, Any], created_at: str) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO knowledge_links(
                    link_id, source_knowledge_id, target_type, target_id, relationship, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (link_id, knowledge_id, target_type, target_id, relationship, json.dumps(metadata, ensure_ascii=False, sort_keys=True), created_at),
            )
            con.commit()
        finally:
            con.close()

    def add_conflict(self, conflict_id: str, topic: str, knowledge_a: str, knowledge_b: str, reason: str, created_at: str) -> None:
        con = self.connect()
        try:
            exists = con.execute(
                """
                SELECT 1 FROM knowledge_conflicts
                WHERE (knowledge_a = ? AND knowledge_b = ?) OR (knowledge_a = ? AND knowledge_b = ?)
                """,
                (knowledge_a, knowledge_b, knowledge_b, knowledge_a),
            ).fetchone()
            if not exists:
                con.execute(
                    """
                    INSERT INTO knowledge_conflicts(conflict_id, topic, knowledge_a, knowledge_b, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (conflict_id, topic, knowledge_a, knowledge_b, reason, created_at),
                )
            con.commit()
        finally:
            con.close()

    def get(self, knowledge_id: str) -> dict[str, Any] | None:
        con = self.connect()
        try:
            row = con.execute("SELECT * FROM knowledge_items WHERE knowledge_id = ?", (knowledge_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            con.close()

    def search(
        self,
        topic: str = "",
        text: str = "",
        tags: list[str] | None = None,
        source_type: str = "",
        evidence_level: str = "",
        experiment_id: str = "",
        symbol: str = "",
        timeframe: str = "",
        limit: int = 20,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if not include_archived:
            clauses.append("archived = 0")
        if topic:
            clauses.append("lower(topic) LIKE ?")
            params.append(f"%{topic.lower()}%")
        if text:
            clauses.append("(lower(statement) LIKE ? OR lower(topic) LIKE ? OR lower(metadata_json) LIKE ?)")
            value = f"%{text.lower()}%"
            params.extend([value, value, value])
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type)
        if evidence_level:
            clauses.append("evidence_level = ?")
            params.append(evidence_level)
        if experiment_id:
            clauses.append("(source_id = ? OR lower(metadata_json) LIKE ?)")
            params.extend([experiment_id, f"%{experiment_id.lower()}%"])
        if symbol:
            clauses.append("lower(metadata_json) LIKE ?")
            params.append(f"%{symbol.lower()}%")
        if timeframe:
            clauses.append("lower(metadata_json) LIKE ?")
            params.append(f"%{timeframe.lower()}%")
        for tag in tags or []:
            clauses.append("lower(tags_json) LIKE ?")
            params.append(f"%{tag.lower()}%")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        con = self.connect()
        try:
            rows = con.execute(
                f"""
                SELECT * FROM knowledge_items
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*params, int(limit)),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            con.close()

    def conflicts_for_topic(self, topic: str) -> list[dict[str, Any]]:
        con = self.connect()
        try:
            rows = con.execute(
                "SELECT * FROM knowledge_conflicts WHERE lower(topic) LIKE ? ORDER BY created_at DESC",
                (f"%{topic.lower()}%",),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            con.close()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["tags"] = json.loads(data.pop("tags_json") or "[]")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        data["archived"] = bool(data["archived"])
        return data
