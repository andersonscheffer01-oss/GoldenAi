"""Golden Memory Engine V2 — migrations idempotentes (M1.0).

Mesmo arquivo do legado (golden_memory.db). Tabelas novas com prefixo
`v2_`; schema legado NUNCA é alterado. Roda em instalação nova, banco
existente, reinício e chamada duplicada.
"""
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

V2_SCHEMA_VERSION = 4
_LOCK = threading.Lock()


@contextmanager
def v2_connect(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10,
                           isolation_level="DEFERRED",
                           detect_types=sqlite3.PARSE_DECLTYPES)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _v2_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS v2_schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM v2_schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return int(row[0]) if row else 0


def _migrate_to_1(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_memories ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "memory_type TEXT NOT NULL,"
        "title TEXT NOT NULL DEFAULT '',"
        "content TEXT NOT NULL,"
        "summary TEXT NOT NULL DEFAULT '',"
        "status TEXT NOT NULL DEFAULT 'active',"
        "created_at REAL NOT NULL,"
        "updated_at REAL NOT NULL,"
        "last_accessed_at REAL NOT NULL,"
        "version INTEGER NOT NULL DEFAULT 1,"
        "confidence REAL NOT NULL DEFAULT 0.5,"
        "confidence_basis TEXT NOT NULL DEFAULT 'inferred',"
        "privacy TEXT NOT NULL DEFAULT 'INTERNAL',"
        "source_type TEXT NOT NULL DEFAULT 'system',"
        "source_ref TEXT NOT NULL DEFAULT '',"
        "source_timestamp REAL NOT NULL DEFAULT 0,"
        "project TEXT NOT NULL DEFAULT '',"
        "tags TEXT NOT NULL DEFAULT '[]',"
        "metadata TEXT NOT NULL DEFAULT '{}',"
        "embedding_status TEXT NOT NULL DEFAULT 'pending',"
        "embedding_model TEXT NOT NULL DEFAULT '',"
        "content_hash TEXT NOT NULL DEFAULT '',"
        "canonical_key TEXT NOT NULL DEFAULT ''"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_memory_versions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "memory_id INTEGER NOT NULL,"
        "version INTEGER NOT NULL,"
        "memory_type TEXT NOT NULL,"
        "title TEXT NOT NULL DEFAULT '',"
        "content TEXT NOT NULL,"
        "summary TEXT NOT NULL DEFAULT '',"
        "status TEXT NOT NULL DEFAULT 'active',"
        "confidence REAL NOT NULL DEFAULT 0.5,"
        "confidence_basis TEXT NOT NULL DEFAULT 'inferred',"
        "privacy TEXT NOT NULL DEFAULT 'INTERNAL',"
        "source_type TEXT NOT NULL DEFAULT 'system',"
        "source_ref TEXT NOT NULL DEFAULT '',"
        "project TEXT NOT NULL DEFAULT '',"
        "tags TEXT NOT NULL DEFAULT '[]',"
        "metadata TEXT NOT NULL DEFAULT '{}',"
        "content_hash TEXT NOT NULL DEFAULT '',"
        "created_at REAL NOT NULL,"
        "FOREIGN KEY (memory_id) REFERENCES v2_memories(id) ON DELETE CASCADE"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_entities ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "entity_type TEXT NOT NULL,"
        "canonical_name TEXT NOT NULL,"
        "privacy TEXT NOT NULL DEFAULT 'INTERNAL',"
        "created_at REAL NOT NULL,"
        "updated_at REAL NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'active',"
        "UNIQUE(entity_type, canonical_name)"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_entity_aliases ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "entity_id INTEGER NOT NULL,"
        "alias TEXT NOT NULL,"
        "created_at REAL NOT NULL,"
        "UNIQUE(entity_id, alias),"
        "FOREIGN KEY (entity_id) REFERENCES v2_entities(id) ON DELETE CASCADE"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_relations ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "source_entity_id INTEGER NOT NULL,"
        "relation_type TEXT NOT NULL,"
        "target_entity_id INTEGER NOT NULL,"
        "confidence REAL NOT NULL DEFAULT 0.5,"
        "privacy TEXT NOT NULL DEFAULT 'INTERNAL',"
        "source_ref TEXT NOT NULL DEFAULT '',"
        "created_at REAL NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'active',"
        "UNIQUE(source_entity_id, relation_type, target_entity_id),"
        "FOREIGN KEY (source_entity_id) REFERENCES v2_entities(id) ON DELETE CASCADE,"
        "FOREIGN KEY (target_entity_id) REFERENCES v2_entities(id) ON DELETE CASCADE"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_embeddings ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "memory_id INTEGER NOT NULL UNIQUE,"
        "embedding BLOB NOT NULL,"
        "model TEXT NOT NULL,"
        "created_at REAL NOT NULL,"
        "FOREIGN KEY (memory_id) REFERENCES v2_memories(id) ON DELETE CASCADE"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_memories_type ON v2_memories(memory_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_memories_status ON v2_memories(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_memories_hash ON v2_memories(content_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_memories_canonical ON v2_memories(canonical_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_versions_memory ON v2_memory_versions(memory_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_aliases_entity ON v2_entity_aliases(entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_relations_src ON v2_relations(source_entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_relations_dst ON v2_relations(target_entity_id)")


MIGRATIONS = {1: _migrate_to_1}


def _migrate_to_2(conn: sqlite3.Connection) -> None:
    """M1.1 (Obsidian vault): estado de sincronização das projeções
    Markdown. Aditiva; nunca toca tabelas v1 nem legado."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_projections ("
        "memory_id INTEGER NOT NULL,"
        "kind TEXT NOT NULL DEFAULT 'memory',"  # memory | entity
        "path TEXT NOT NULL DEFAULT '',"
        "projection_hash TEXT NOT NULL DEFAULT '',"
        "projection_version INTEGER NOT NULL DEFAULT 0,"
        "sync_status TEXT NOT NULL DEFAULT 'pending',"
        "detail TEXT NOT NULL DEFAULT '',"
        "last_sync_at REAL NOT NULL DEFAULT 0,"
        "UNIQUE(memory_id, kind)"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_projections_status"
                 " ON v2_projections(sync_status)")


MIGRATIONS[2] = _migrate_to_2


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}


def _migrate_to_3(conn: sqlite3.Connection) -> None:
    """M1.2 (Knowledge Graph): identidade/proveniência/versionamento de
    entidades e relações + links memória↔entidade + evidências.
    Aditiva; política soft-delete (sem cascade destrutivo em código)."""
    from .graph import normalize_alias, normalize_name
    for column, ddl in (
            ("normalized_name", "TEXT NOT NULL DEFAULT ''"),
            ("confidence", "REAL NOT NULL DEFAULT 0.5"),
            ("confidence_basis", "TEXT NOT NULL DEFAULT 'inferred'"),
            ("source_type", "TEXT NOT NULL DEFAULT 'system'"),
            ("source_ref", "TEXT NOT NULL DEFAULT ''"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("metadata", "TEXT NOT NULL DEFAULT '{}'")):
        if column not in _columns(conn, "v2_entities"):
            conn.execute("ALTER TABLE v2_entities ADD COLUMN %s %s"
                         % (column, ddl))
    if "normalized_alias" not in _columns(conn, "v2_entity_aliases"):
        conn.execute("ALTER TABLE v2_entity_aliases ADD COLUMN"
                     " normalized_alias TEXT NOT NULL DEFAULT ''")
    for column, ddl in (
            ("confidence_basis", "TEXT NOT NULL DEFAULT 'inferred'"),
            ("source_type", "TEXT NOT NULL DEFAULT 'system'"),
            ("updated_at", "REAL NOT NULL DEFAULT 0"),
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("metadata", "TEXT NOT NULL DEFAULT '{}'")):
        if column not in _columns(conn, "v2_relations"):
            conn.execute("ALTER TABLE v2_relations ADD COLUMN %s %s"
                         % (column, ddl))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_entity_versions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "entity_id INTEGER NOT NULL,"
        "version INTEGER NOT NULL,"
        "entity_type TEXT NOT NULL,"
        "canonical_name TEXT NOT NULL,"
        "aliases_json TEXT NOT NULL DEFAULT '[]',"
        "privacy TEXT NOT NULL DEFAULT 'INTERNAL',"
        "confidence REAL NOT NULL DEFAULT 0.5,"
        "source_ref TEXT NOT NULL DEFAULT '',"
        "metadata TEXT NOT NULL DEFAULT '{}',"
        "created_at REAL NOT NULL,"
        "FOREIGN KEY (entity_id) REFERENCES v2_entities(id) ON DELETE CASCADE"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_relation_versions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "relation_id INTEGER NOT NULL,"
        "version INTEGER NOT NULL,"
        "relation_type TEXT NOT NULL,"
        "source_entity_id INTEGER NOT NULL,"
        "target_entity_id INTEGER NOT NULL,"
        "confidence REAL NOT NULL DEFAULT 0.5,"
        "privacy TEXT NOT NULL DEFAULT 'INTERNAL',"
        "status TEXT NOT NULL DEFAULT 'active',"
        "source_ref TEXT NOT NULL DEFAULT '',"
        "created_at REAL NOT NULL,"
        "FOREIGN KEY (relation_id) REFERENCES v2_relations(id) ON DELETE CASCADE"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_memory_entities ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "memory_id INTEGER NOT NULL,"
        "entity_id INTEGER NOT NULL,"
        "link_role TEXT NOT NULL DEFAULT 'related',"
        "created_at REAL NOT NULL,"
        "status TEXT NOT NULL DEFAULT 'active',"
        "UNIQUE(memory_id, entity_id, link_role)"
        ")"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS v2_relation_evidence ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "relation_id INTEGER NOT NULL,"
        "memory_id INTEGER NOT NULL,"
        "note TEXT NOT NULL DEFAULT '',"
        "created_at REAL NOT NULL,"
        "UNIQUE(relation_id, memory_id)"
        ")"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_entities_norm"
                 " ON v2_entities(normalized_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_aliases_norm"
                 " ON v2_entity_aliases(normalized_alias)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_mem_entities_mem"
                 " ON v2_memory_entities(memory_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_mem_entities_ent"
                 " ON v2_memory_entities(entity_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v2_rel_evidence_rel"
                 " ON v2_relation_evidence(relation_id)")
    # Backfill conservador (só onde vazio; nunca reescreve dado real).
    for eid, name in conn.execute(
            "SELECT id, canonical_name FROM v2_entities"
            " WHERE normalized_name='' OR normalized_name IS NULL").fetchall():
        conn.execute("UPDATE v2_entities SET normalized_name=? WHERE id=?",
                     (normalize_name(name), eid))
    for aid, alias in conn.execute(
            "SELECT id, alias FROM v2_entity_aliases"
            " WHERE normalized_alias='' OR normalized_alias IS NULL").fetchall():
        conn.execute("UPDATE v2_entity_aliases SET normalized_alias=? WHERE id=?",
                     (normalize_alias(alias), aid))


MIGRATIONS[3] = _migrate_to_3


def _migrate_to_4(conn: sqlite3.Connection) -> None:
    """M1.3 (Hybrid retrieval): índice FTS5 derivado e reconstruível.
    Sem FTS5 compilado: ignora silenciosamente (fallback lexical).
    Nunca altera dado canônico; reconstruível via rebuild."""
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS v2_memories_fts USING fts5("
            "title, content, summary, tags, project, tokenize='unicode61')")
    except Exception:
        pass  # FTS5 indisponível: retrieval degrada p/ lexical


MIGRATIONS[4] = _migrate_to_4


def ensure_v2_schema(db_path: Path | str) -> int:
    """Garante schema V2; retorna versão. Idempotente e concorrente-segura."""
    with _LOCK:
        with v2_connect(db_path) as conn:
            current = _v2_version(conn)
            if current >= V2_SCHEMA_VERSION:
                return current
            for version in sorted(MIGRATIONS):
                if version > current:
                    MIGRATIONS[version](conn)
            conn.execute("DELETE FROM v2_schema_version")
            conn.execute("INSERT INTO v2_schema_version (version) VALUES (?)",
                         (V2_SCHEMA_VERSION,))
            return V2_SCHEMA_VERSION


def v2_schema_version(db_path: Path | str) -> int:
    with v2_connect(db_path) as conn:
        return _v2_version(conn)


def v2_pending_embeddings(db_path: Path | str) -> int:
    with v2_connect(db_path) as conn:
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM v2_memories WHERE status='active' "
                "AND embedding_status='pending'").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0


def v2_get_projection(db_path: Path | str, memory_id: int,
                      kind: str = "memory") -> dict | None:
    """Estado de sync de uma projeção (None = nunca projetada)."""
    with v2_connect(db_path) as conn:
        try:
            cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_projections LIMIT 0").description]
            row = conn.execute(
                "SELECT * FROM v2_projections WHERE memory_id=? AND kind=?",
                (int(memory_id), kind)).fetchone()
            return dict(zip(cols, row)) if row else None
        except Exception:
            return None


def v2_set_projection(db_path: Path | str, memory_id: int, kind: str,
                      path: str, projection_hash: str,
                      projection_version: int, sync_status: str,
                      detail: str = "") -> None:
    import time as _time
    with v2_connect(db_path) as conn:
        conn.execute(
            "INSERT INTO v2_projections (memory_id, kind, path,"
            " projection_hash, projection_version, sync_status, detail,"
            " last_sync_at) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(memory_id, kind) DO UPDATE SET"
            " path=excluded.path, projection_hash=excluded.projection_hash,"
            " projection_version=excluded.projection_version,"
            " sync_status=excluded.sync_status, detail=excluded.detail,"
            " last_sync_at=excluded.last_sync_at",
            (int(memory_id), kind, str(path or ""), str(projection_hash or ""),
             int(projection_version or 0), str(sync_status),
             str(detail or "")[:500], _time.time()))


def v2_list_projections(db_path: Path | str,
                        status: str = "") -> list:
    with v2_connect(db_path) as conn:
        try:
            cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_projections LIMIT 0").description]
            if status:
                rows = conn.execute(
                    "SELECT * FROM v2_projections WHERE sync_status=?",
                    (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM v2_projections").fetchall()
            return [dict(zip(cols, row)) for row in rows]
        except Exception:
            return []
