from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import MediaDocument, MediaSegment, MediaSource, SourceClaim, StudyResult, TestableHypothesis


class MediaStudyRepository:
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
                CREATE TABLE IF NOT EXISTS media_sources (
                    source_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    author TEXT NOT NULL,
                    source_date TEXT NOT NULL,
                    language TEXT NOT NULL,
                    duration_seconds REAL,
                    source_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_documents (
                    document_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    text_length INTEGER NOT NULL,
                    line_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_segments (
                    segment_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    segment_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_claims (
                    claim_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    segment_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    claim_kind TEXT NOT NULL,
                    evidence_level TEXT NOT NULL,
                    timestamp_start TEXT NOT NULL,
                    timestamp_end TEXT NOT NULL,
                    line_start INTEGER,
                    line_end INTEGER,
                    confidence REAL NOT NULL,
                    numbers_json TEXT NOT NULL,
                    units_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_study_results (
                    study_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    hypothesis_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_links (
                    link_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    from_type TEXT NOT NULL,
                    from_id TEXT NOT NULL,
                    to_type TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_media_sources_hash ON media_sources(source_hash);
                CREATE INDEX IF NOT EXISTS idx_media_segments_source ON media_segments(source_id, order_index);
                CREATE INDEX IF NOT EXISTS idx_media_claims_source ON media_claims(source_id);
                CREATE INDEX IF NOT EXISTS idx_media_claims_segment ON media_claims(segment_id);
                """
            )
            con.commit()
        finally:
            con.close()

    def save_source(self, source: MediaSource, document: MediaDocument, segments: list[MediaSegment]) -> MediaSource:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO media_sources(
                    source_id, source_type, title, origin, author, source_date, language,
                    duration_seconds, source_hash, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.source_id,
                    source.source_type,
                    source.title,
                    source.origin,
                    source.author,
                    source.source_date,
                    source.language,
                    source.duration_seconds,
                    source.source_hash,
                    source.created_at,
                    json.dumps(source.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            con.execute(
                """
                INSERT OR REPLACE INTO media_documents(document_id, source_id, content_hash, text_length, line_count, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.document_id,
                    document.source_id,
                    document.content_hash,
                    document.text_length,
                    document.line_count,
                    document.created_at,
                    json.dumps(document.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            con.execute("DELETE FROM media_segments WHERE source_id = ?", (source.source_id,))
            for segment in segments:
                con.execute(
                    """
                    INSERT INTO media_segments(
                        segment_id, source_id, order_index, text, start_time, end_time,
                        line_start, line_end, segment_hash, created_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment.segment_id,
                        segment.source_id,
                        segment.order_index,
                        segment.text,
                        segment.start_time,
                        segment.end_time,
                        segment.line_start,
                        segment.line_end,
                        segment.segment_hash,
                        segment.created_at,
                        json.dumps(segment.metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )
            con.commit()
            return source
        finally:
            con.close()

    def save_claims(self, claims: list[SourceClaim]) -> None:
        con = self.connect()
        try:
            for claim in claims:
                con.execute(
                    """
                    INSERT OR REPLACE INTO media_claims(
                        claim_id, source_id, segment_id, statement, claim_kind, evidence_level,
                        timestamp_start, timestamp_end, line_start, line_end, confidence,
                        numbers_json, units_json, tags_json, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.claim_id,
                        claim.source_id,
                        claim.segment_id,
                        claim.statement,
                        claim.claim_kind,
                        claim.evidence_level,
                        claim.timestamp_start,
                        claim.timestamp_end,
                        claim.line_start,
                        claim.line_end,
                        claim.confidence,
                        json.dumps(claim.numbers, ensure_ascii=False, sort_keys=True),
                        json.dumps(claim.units, ensure_ascii=False, sort_keys=True),
                        json.dumps(claim.tags, ensure_ascii=False, sort_keys=True),
                        json.dumps(claim.metadata, ensure_ascii=False, sort_keys=True),
                        claim.created_at,
                    ),
                )
            con.commit()
        finally:
            con.close()

    def save_study_result(self, result: StudyResult) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO media_study_results(study_id, source_id, summary, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (result.study_id, result.source_id, result.summary, json.dumps(asdict(result), ensure_ascii=False, sort_keys=True), result.created_at),
            )
            con.commit()
        finally:
            con.close()

    def save_hypothesis(self, hypothesis: TestableHypothesis) -> None:
        con = self.connect()
        try:
            con.execute(
                """
                INSERT OR REPLACE INTO media_hypotheses(
                    hypothesis_id, claim_id, source_id, statement, hypothesis_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.hypothesis_id,
                    hypothesis.claim_id,
                    hypothesis.source_id,
                    hypothesis.statement,
                    json.dumps(asdict(hypothesis), ensure_ascii=False, sort_keys=True),
                    hypothesis.status,
                    hypothesis.created_at,
                ),
            )
            con.commit()
        finally:
            con.close()

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        con = self.connect()
        try:
            row = con.execute("SELECT * FROM media_sources WHERE source_id = ?", (source_id,)).fetchone()
            return self._source_row(row) if row else None
        finally:
            con.close()

    def find_source_by_hash(self, source_hash: str, origin: str = "") -> dict[str, Any] | None:
        con = self.connect()
        try:
            row = con.execute(
                "SELECT * FROM media_sources WHERE source_hash = ? ORDER BY created_at DESC LIMIT 1",
                (source_hash,),
            ).fetchone()
            return self._source_row(row) if row else None
        finally:
            con.close()

    def list_sources(self, limit: int = 20) -> list[dict[str, Any]]:
        con = self.connect()
        try:
            rows = con.execute(
                "SELECT * FROM media_sources ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [self._source_row(row) for row in rows]
        finally:
            con.close()

    def get_segments(self, source_id: str, limit: int = 200) -> list[dict[str, Any]]:
        con = self.connect()
        try:
            rows = con.execute(
                "SELECT * FROM media_segments WHERE source_id = ? ORDER BY order_index LIMIT ?",
                (source_id, int(limit)),
            ).fetchall()
            return [self._segment_row(row) for row in rows]
        finally:
            con.close()

    def search_segments(self, source_id: str = "", query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if source_id:
            clauses.append("source_id = ?")
            params.append(source_id)
        if query:
            clauses.append("lower(text) LIKE ?")
            params.append(f"%{query.lower()}%")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        con = self.connect()
        try:
            rows = con.execute(
                f"SELECT * FROM media_segments {where} ORDER BY source_id, order_index LIMIT ?",
                (*params, int(limit)),
            ).fetchall()
            return [self._segment_row(row) for row in rows]
        finally:
            con.close()

    def get_claims(self, source_id: str = "", claim_id: str = "") -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if source_id:
            clauses.append("source_id = ?")
            params.append(source_id)
        if claim_id:
            clauses.append("claim_id = ?")
            params.append(claim_id)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        con = self.connect()
        try:
            rows = con.execute(f"SELECT * FROM media_claims {where} ORDER BY created_at DESC", params).fetchall()
            return [self._claim_row(row) for row in rows]
        finally:
            con.close()

    def get_study_result(self, study_id: str) -> dict[str, Any] | None:
        con = self.connect()
        try:
            row = con.execute("SELECT * FROM media_study_results WHERE study_id = ?", (study_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["result"] = json.loads(data.pop("result_json") or "{}")
            return data
        finally:
            con.close()

    def _source_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _segment_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _claim_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["numbers"] = json.loads(data.pop("numbers_json") or "[]")
        data["units"] = json.loads(data.pop("units_json") or "[]")
        data["tags"] = json.loads(data.pop("tags_json") or "[]")
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data
