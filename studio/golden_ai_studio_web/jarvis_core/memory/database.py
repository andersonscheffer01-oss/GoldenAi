import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .models import MemoryCategory, MemoryRecord, MemorySource, MemoryStatus, MemoryType


class Database:
    SCHEMA_VERSION = 1
    LOCK_TIMEOUT = 10

    def __init__(self, db_path: Path | str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._ensure_schema()

    @contextmanager
    def _connect(self, row_factory: bool = False, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        database = sqlite3.connect(
            str(self.path),
            timeout=self.LOCK_TIMEOUT,
            isolation_level='DEFERRED',
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        try:
            database.execute('PRAGMA journal_mode=WAL')
            database.execute('PRAGMA busy_timeout=' + str(self.LOCK_TIMEOUT * 1000))
            if row_factory:
                database.row_factory = sqlite3.Row
            yield database
            database.commit()
        finally:
            database.close()

    def _ensure_schema(self) -> None:
        self._migrate()

    def _migrate(self) -> None:
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS memory_schema_version (version INTEGER NOT NULL)')
            current = self._schema_version(db)
            if current >= self.SCHEMA_VERSION:
                return
            db.execute('DELETE FROM memory_schema_version')
            db.execute('INSERT INTO memory_schema_version (version) VALUES (?)', (self.SCHEMA_VERSION,))

            db.execute(
                'CREATE TABLE IF NOT EXISTS memory_sessions ('
                'session_id TEXT PRIMARY KEY,'
                'created_at REAL NOT NULL,'
                'last_activity REAL NOT NULL,'
                'ended_at REAL,'
                'status TEXT NOT NULL,'
                'metadata TEXT NOT NULL'
                ')'
            )
            db.execute(
                'CREATE TABLE IF NOT EXISTS memories ('
                'id INTEGER PRIMARY KEY AUTOINCREMENT,'
                'memory_type TEXT NOT NULL,'
                'category TEXT NOT NULL,'
                'content TEXT NOT NULL,'
                'summary TEXT NOT NULL,'
                'importance INTEGER NOT NULL,'
                'confidence REAL NOT NULL,'
                'source TEXT NOT NULL,'
                'source_id TEXT,'
                'session_id TEXT,'
                'namespace TEXT NOT NULL,'
                'created_at REAL NOT NULL,'
                'updated_at REAL NOT NULL,'
                'last_accessed_at REAL NOT NULL,'
                'access_count INTEGER NOT NULL,'
                'active INTEGER NOT NULL,'
                'metadata TEXT NOT NULL'
                ')'
            )
            db.execute(
                'CREATE TABLE IF NOT EXISTS memory_embeddings ('
                'id INTEGER PRIMARY KEY AUTOINCREMENT,'
                'memory_id INTEGER NOT NULL UNIQUE,'
                'embedding BLOB,'
                'model TEXT NOT NULL,'
                'created_at REAL NOT NULL,'
                'FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE'
                ')'
            )
            db.execute('CREATE INDEX IF NOT EXISTS idx_memories_type_category ON memories(memory_type, category)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(active)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id)')
            db.execute('CREATE INDEX IF NOT EXISTS idx_embeddings_memory ON memory_embeddings(memory_id)')

    def _schema_version(self, db: sqlite3.Connection) -> int:
        row = db.execute('SELECT version FROM memory_schema_version ORDER BY version DESC LIMIT 1').fetchone()
        return int(row[0]) if row else 0

    def session_upsert(self, session_id: str, created_at: float, last_activity: float,
                       ended_at: Optional[float], status: str, metadata: Dict[str, Any]) -> None:
        with self._connect() as db:
            exists = db.execute('SELECT 1 FROM memory_sessions WHERE session_id=?', (session_id,)).fetchone()
            if exists:
                db.execute(
                    'UPDATE memory_sessions SET last_activity=?, ended_at=?, status=? WHERE session_id=?',
                    (last_activity, ended_at, status, session_id),
                )
            else:
                db.execute(
                    'INSERT INTO memory_sessions (session_id, created_at, last_activity, ended_at, status, metadata) '
                    'VALUES (?,?,?,?,?,?)',
                    (session_id, created_at, last_activity, ended_at, status, json.dumps(metadata, ensure_ascii=False)),
                )

    def session_get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect(row_factory=True) as db:
            row = db.execute('SELECT * FROM memory_sessions WHERE session_id=?', (session_id,)).fetchone()
            if not row:
                return None
            return self._session_row_to_dict(db, row)

    def session_list(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect(row_factory=True) as db:
            rows = db.execute(
                'SELECT * FROM memory_sessions ORDER BY created_at DESC LIMIT ?', (limit,)
            ).fetchall()
            return [self._session_row_to_dict(db, r) for r in rows]

    def _session_row_to_dict(self, db: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            'session_id': row['session_id'],
            'created_at': float(row['created_at']),
            'last_activity': float(row['last_activity']),
            'ended_at': float(row['ended_at']) if row['ended_at'] else None,
            'status': row['status'],
            'metadata': json.loads(row['metadata']) if row['metadata'] else {},
        }

    def memory_upsert(self, record: MemoryRecord) -> int:
        with self._connect() as db:
            if record.id:
                now = time.time()
                db.execute(
                    'UPDATE memories SET memory_type=?, category=?, content=?, summary=?, '
                    'importance=?, confidence=?, source=?, source_id=?, session_id=?, '
                    'namespace=?, updated_at=?, last_accessed_at=?, access_count=access_count+1, '
                    'active=?, metadata=? WHERE id=?',
                    (record.memory_type.value, record.category.value, record.content, record.summary,
                     record.importance, record.confidence, record.source.value, record.source_id,
                     record.session_id, record.namespace, now, now,
                     record.active, json.dumps(record.metadata, ensure_ascii=False), record.id),
                )
                rid = record.id
                row = db.execute('SELECT id FROM memories WHERE id=?', (rid,)).fetchone()
                return int(row[0]) if row else rid
            now = time.time()
            db.execute(
                'INSERT INTO memories (memory_type, category, content, summary, importance, confidence, '
                'source, source_id, session_id, namespace, created_at, updated_at, last_accessed_at, '
                'access_count, active, metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (record.memory_type.value, record.category.value, record.content, record.summary,
                 record.importance, record.confidence, record.source.value, record.source_id,
                 record.session_id, record.namespace, now, now, now, 0, record.active,
                 json.dumps(record.metadata, ensure_ascii=False)),
            )
            rid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
            if record.embedding:
                self._upsert_embedding(db, rid, record.embedding, record.source_id or 'builtin')
            return rid

    def memory_get(self, rid: int) -> Optional[MemoryRecord]:
        with self._connect(row_factory=True) as db:
            row = db.execute('SELECT * FROM memories WHERE id=? AND active=1', (rid,)).fetchone()
            if not row:
                return None
            return self._memory_row_to_record(row, db)

    def memory_deactivate(self, rid: int) -> bool:
        with self._connect() as db:
            cur = db.execute('UPDATE memories SET active=0, updated_at=? WHERE id=?', (time.time(), rid))
            db.commit()
            return cur.rowcount > 0

    def memory_get_all(self, limit: int = 500, active: Optional[bool] = None) -> List[MemoryRecord]:
        with self._connect(row_factory=True) as db:
            where = 'WHERE 1=1'
            params: List[Any] = []
            if active is not None:
                where += ' AND active=?'
                params.append(int(active))
            rows = db.execute(
                f'SELECT * FROM memories {where} ORDER BY created_at DESC LIMIT ?',
                params + [limit],
            ).fetchall()
            return [self._memory_row_to_record(r, db) for r in rows]

    def memory_count(self, active: Optional[bool] = None) -> int:
        with self._connect() as db:
            where = 'WHERE 1=1'
            params: List[Any] = []
            if active is not None:
                where += ' AND active=?'
                params.append(int(active))
            row = db.execute(f'SELECT COUNT(*) FROM memories {where}', params).fetchone()
            return int(row[0])

    def _memory_row_to_record(self, row: sqlite3.Row, db: sqlite3.Connection) -> MemoryRecord:
        kind = row['memory_type']
        emb_row = db.execute('SELECT * FROM memory_embeddings WHERE memory_id=?', (row['id'],)).fetchone()
        emb = None
        if emb_row and emb_row['embedding']:
            emb = json.loads(emb_row['embedding'])
        return MemoryRecord(
            id=int(row['id']),
            memory_type=MemoryType(kind),
            category=MemoryCategory(row['category']),
            content=row['content'],
            summary=row['summary'],
            importance=int(row['importance']),
            confidence=float(row['confidence']),
            source=MemorySource(row['source']),
            source_id=row['source_id'],
            session_id=row['session_id'],
            namespace=row['namespace'],
            created_at=float(row['created_at']),
            updated_at=float(row['updated_at']),
            last_accessed_at=float(row['last_accessed_at']),
            access_count=int(row['access_count']),
            active=bool(row['active']),
            metadata=json.loads(row['metadata']) if row['metadata'] else {},
            embedding=emb,
        )

    def _upsert_embedding(self, db: sqlite3.Connection, memory_id: int,
                          embedding: List[float], model: str, created_at: Optional[float] = None) -> None:
        if not embedding:
            return
        created_at = created_at or time.time()
        embedding_blob = json.dumps(embedding, separators=(',', ':')).encode('utf-8')
        db.execute(
            'INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding, model, created_at) VALUES (?,?,?,?)',
            (memory_id, embedding_blob, model, created_at),
        )
