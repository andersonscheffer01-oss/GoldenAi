"""Golden Memory Engine V2 — stores (M1.0 + M1.1).

SQLiteMemoryStore é a persistência canônica. MarkdownMemoryStore é a
projeção Obsidian (M1.1): nunca fonte de verdade, nunca importada.
"""
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .migrations import ensure_v2_schema, v2_connect
from .graph_store import GraphStoreMixin
from .record import EntityV2, MemoryRecordV2, RelationV2
from .types import RecordStatus
from .vault import SyncStatus


class MemoryStore(ABC):
    @abstractmethod
    def save(self, record: MemoryRecordV2) -> MemoryRecordV2:
        ...

    @abstractmethod
    def load(self, record_id: int) -> Optional[MemoryRecordV2]:
        ...

    @abstractmethod
    def update(self, record: MemoryRecordV2) -> MemoryRecordV2:
        ...

    @abstractmethod
    def set_status(self, record_id: int, status: RecordStatus) -> bool:
        ...

    @abstractmethod
    def find_by_hash(self, content_hash: str, namespace_project: str = "") -> Optional[MemoryRecordV2]:
        ...

    @abstractmethod
    def find_by_canonical(self, canonical_key: str,
                          namespace_project: str = "") -> Optional[MemoryRecordV2]:
        ...

    @abstractmethod
    def versions(self, record_id: int) -> List[Dict[str, Any]]:
        ...


def _tags_to_json(tags: List[str]) -> str:
    return json.dumps(list(tags or []), ensure_ascii=False)


def _tags_from_json(raw: str) -> List[str]:
    try:
        items = json.loads(raw or "[]")
        return [str(x) for x in items] if isinstance(items, list) else []
    except Exception:
        return []


class SQLiteMemoryStore(GraphStoreMixin, MemoryStore):
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        ensure_v2_schema(self.db_path)

    # ── records ──────────────────────────────────────────────────

    def save(self, record: MemoryRecordV2) -> MemoryRecordV2:
        record.validate()
        now = time.time()
        record.created_at = record.created_at or now
        record.updated_at = now
        record.last_accessed_at = record.last_accessed_at or now
        with v2_connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO v2_memories (memory_type, title, content, summary, status,"
                " created_at, updated_at, last_accessed_at, version, confidence,"
                " confidence_basis, privacy, source_type, source_ref, source_timestamp,"
                " project, tags, metadata, embedding_status, embedding_model,"
                " content_hash, canonical_key)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record.memory_type.value, record.title, record.content, record.summary,
                 record.status.value, record.created_at, record.updated_at,
                 record.last_accessed_at, record.version, float(record.confidence),
                 record.confidence_basis.value, record.privacy.value,
                 record.source_type.value, record.source_ref, record.source_timestamp,
                 record.project, _tags_to_json(record.tags),
                 json.dumps(record.metadata, ensure_ascii=False),
                 record.embedding_status, record.embedding_model,
                 record.content_hash, record.canonical_key),
            )
            record.id = int(cur.lastrowid)
            return record

    def load(self, record_id: int) -> Optional[MemoryRecordV2]:
        with v2_connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM v2_memories WHERE id=?",
                               (record_id,)).fetchone()
            if not row:
                return None
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_memories LIMIT 0").description]
            return self._row_to_record(dict(zip(cols, row)))

    def update(self, record: MemoryRecordV2) -> MemoryRecordV2:
        """Nova versão: snapshot da anterior em v2_memory_versions + UPDATE.

        Tudo na mesma transação (commit/rollback pelo contexto).
        """
        if not record.id:
            raise ValueError("update exige id")
        record.validate()
        with v2_connect(self.db_path) as conn:
            current = conn.execute("SELECT * FROM v2_memories WHERE id=?",
                                   (record.id,)).fetchone()
            if not current:
                raise KeyError("memória %s inexistente" % record.id)
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_memories LIMIT 0").description]
            old = dict(zip(cols, current))
            conn.execute(
                "INSERT INTO v2_memory_versions (memory_id, version, memory_type, title,"
                " content, summary, status, confidence, confidence_basis, privacy,"
                " source_type, source_ref, project, tags, metadata, content_hash, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record.id, old["version"], old["memory_type"], old["title"],
                 old["content"], old["summary"], old["status"], old["confidence"],
                 old["confidence_basis"], old["privacy"], old["source_type"],
                 old["source_ref"], old["project"], old["tags"], old["metadata"],
                 old["content_hash"], old["updated_at"]),
            )
            record.version = int(old["version"]) + 1
            record.updated_at = time.time()
            conn.execute(
                "UPDATE v2_memories SET memory_type=?, title=?, content=?, summary=?,"
                " status=?, updated_at=?, version=?, confidence=?, confidence_basis=?,"
                " privacy=?, source_type=?, source_ref=?, source_timestamp=?, project=?,"
                " tags=?, metadata=?, embedding_status=?, embedding_model=?,"
                " content_hash=?, canonical_key=? WHERE id=?",
                (record.memory_type.value, record.title, record.content, record.summary,
                 record.status.value, record.updated_at, record.version,
                 float(record.confidence), record.confidence_basis.value,
                 record.privacy.value, record.source_type.value, record.source_ref,
                 record.source_timestamp, record.project, _tags_to_json(record.tags),
                 json.dumps(record.metadata, ensure_ascii=False),
                 record.embedding_status, record.embedding_model,
                 record.content_hash, record.canonical_key, record.id),
            )
            return record

    def set_status(self, record_id: int, status: RecordStatus) -> bool:
        with v2_connect(self.db_path) as conn:
            cur = conn.execute("UPDATE v2_memories SET status=?, updated_at=? WHERE id=?",
                               (status.value, time.time(), record_id))
            return cur.rowcount > 0

    def find_by_hash(self, content_hash: str, namespace_project: str = "") -> Optional[MemoryRecordV2]:
        if not content_hash:
            return None
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_memories LIMIT 0").description]
            row = conn.execute(
                "SELECT * FROM v2_memories WHERE content_hash=? AND project=?"
                " AND status='active' ORDER BY id DESC LIMIT 1",
                (content_hash, namespace_project)).fetchone()
            return self._row_to_record(dict(zip(cols, row))) if row else None

    def find_by_canonical(self, canonical_key: str,
                          namespace_project: str = "") -> Optional[MemoryRecordV2]:
        if not canonical_key:
            return None
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_memories LIMIT 0").description]
            row = conn.execute(
                "SELECT * FROM v2_memories WHERE canonical_key=? AND project=?"
                " AND status='active' ORDER BY id DESC LIMIT 1",
                (canonical_key, namespace_project)).fetchone()
            return self._row_to_record(dict(zip(cols, row))) if row else None

    def versions(self, record_id: int) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_memory_versions LIMIT 0").description]
            rows = conn.execute(
                "SELECT * FROM v2_memory_versions WHERE memory_id=? ORDER BY version",
                (record_id,)).fetchall()
            return [dict(zip(cols, row)) for row in rows]

    def lexical_search(self, query: str, limit: int = 20,
                       memory_type: Optional[str] = None) -> List[MemoryRecordV2]:
        tokens = [t.strip().lower() for t in str(query or "").split() if len(t.strip()) >= 3]
        if not tokens:
            return []
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_memories LIMIT 0").description]
            if memory_type:
                rows = conn.execute(
                    "SELECT * FROM v2_memories WHERE status='active' AND memory_type=?"
                    " ORDER BY updated_at DESC LIMIT 500", (memory_type,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM v2_memories WHERE status='active'"
                    " ORDER BY updated_at DESC LIMIT 500").fetchall()
            scored = []
            for row in rows:
                record = self._row_to_record(dict(zip(cols, row)))
                haystack = (record.title + " " + record.content).lower()
                hits = sum(1 for token in tokens if token in haystack)
                if hits:
                    scored.append((hits / len(tokens), record))
            scored.sort(key=lambda x: (x[0], x[1].updated_at), reverse=True)
            return [record for _, record in scored[:limit]]

    # ── embeddings ───────────────────────────────────────────────

    def save_embedding(self, memory_id: int, vector: List[float], model: str) -> None:
        import json as _json
        blob = _json.dumps(vector, separators=(",", ":")).encode("utf-8")
        with v2_connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO v2_embeddings (memory_id, embedding, model, created_at)"
                " VALUES (?,?,?,?)", (memory_id, blob, model, time.time()))
            conn.execute("UPDATE v2_memories SET embedding_status='ok',"
                         " embedding_model=? WHERE id=?", (model, memory_id))

    def load_embedding(self, memory_id: int) -> Optional[List[float]]:
        import json as _json
        with v2_connect(self.db_path) as conn:
            row = conn.execute("SELECT embedding FROM v2_embeddings WHERE memory_id=?",
                               (memory_id,)).fetchone()
            if not row or not row[0]:
                return None
            try:
                vector = _json.loads(row[0])
                return vector if isinstance(vector, list) and vector else None
            except Exception:
                return None

    def vector_search(self, vector: List[float], limit: int = 20) -> List[tuple]:
        """Cosine sobre v2_embeddings (id, similaridade). Dimensão validada."""
        import json as _json
        if not vector:
            return []
        scored = []
        with v2_connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT e.memory_id, e.embedding FROM v2_embeddings e"
                " JOIN v2_memories m ON m.id=e.memory_id WHERE m.status='active'").fetchall()
            for memory_id, blob in rows:
                try:
                    other = _json.loads(blob)
                except Exception:
                    continue
                if not isinstance(other, list) or len(other) != len(vector):
                    continue
                denom = (sum(x * x for x in vector) ** 0.5) * (sum(x * x for x in other) ** 0.5)
                sim = sum(x * y for x, y in zip(vector, other)) / denom if denom else 0.0
                scored.append((memory_id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    # ── entities / relations ─────────────────────────────────────

    def upsert_entity(self, entity: EntityV2) -> EntityV2:
        """Get-or-create idempotente. Não versiona (mudança material vai
        por update_entity). Mescla aliases sem duplicar."""
        from .graph import normalize_alias, normalize_name
        entity.validate()
        now = time.time()
        norm = normalize_name(entity.canonical_name)
        with v2_connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO v2_entities (entity_type, canonical_name, normalized_name,"
                " privacy, confidence, confidence_basis, source_type, source_ref,"
                " version, metadata, created_at, updated_at, status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(entity_type, canonical_name) DO UPDATE SET"
                " normalized_name=excluded.normalized_name,"
                " privacy=excluded.privacy, confidence=excluded.confidence,"
                " confidence_basis=excluded.confidence_basis,"
                " source_type=excluded.source_type, source_ref=excluded.source_ref,"
                " metadata=excluded.metadata, updated_at=excluded.updated_at,"
                " status=excluded.status",
                (entity.entity_type.value, entity.canonical_name.strip(), norm,
                 entity.privacy.value, float(entity.confidence),
                 entity.confidence_basis.value, entity.source_type.value,
                 entity.source_ref, int(entity.version or 1),
                 json.dumps(entity.metadata or {}, ensure_ascii=False),
                 entity.created_at or now, now, entity.status.value),
            )
            row = conn.execute(
                "SELECT id, created_at, version FROM v2_entities"
                " WHERE entity_type=? AND canonical_name=?",
                (entity.entity_type.value, entity.canonical_name.strip())).fetchone()
            entity.id = int(row[0])
            entity.created_at = float(row[1])
            entity.version = int(row[2])
            entity.updated_at = now
            for alias in dict.fromkeys(a.strip() for a in entity.aliases if a.strip()):
                conn.execute(
                    "INSERT OR IGNORE INTO v2_entity_aliases"
                    " (entity_id, alias, normalized_alias, created_at)"
                    " VALUES (?,?,?,?)",
                    (entity.id, alias, normalize_alias(alias), now))
            return entity

    def get_entity(self, entity_id: int) -> Optional[EntityV2]:
        from .record import EntityV2 as _E
        with v2_connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM v2_entities WHERE id=?", (entity_id,)).fetchone()
            if not row:
                return None
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_entities LIMIT 0").description]
            data = dict(zip(cols, row))
            aliases = [r[0] for r in conn.execute(
                "SELECT alias FROM v2_entity_aliases WHERE entity_id=? ORDER BY alias",
                (entity_id,))]
            return self._row_to_entity(data, aliases)

    def update_entity(self, entity: EntityV2) -> EntityV2:
        """Mudança material: snapshot em v2_entity_versions + UPDATE +
        version++. Mesma transação."""
        if not entity.id:
            raise ValueError("update_entity exige id")
        entity.validate()
        with v2_connect(self.db_path) as conn:
            current = conn.execute("SELECT * FROM v2_entities WHERE id=?",
                                   (entity.id,)).fetchone()
            if not current:
                raise KeyError("entidade %s inexistente" % entity.id)
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_entities LIMIT 0").description]
            old = dict(zip(cols, current))
            old_aliases = [r[0] for r in conn.execute(
                "SELECT alias FROM v2_entity_aliases WHERE entity_id=?",
                (entity.id,))]
            conn.execute(
                "INSERT INTO v2_entity_versions (entity_id, version, entity_type,"
                " canonical_name, aliases_json, privacy, confidence, source_ref,"
                " metadata, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entity.id, old.get("version", 1), old["entity_type"],
                 old["canonical_name"], json.dumps(old_aliases, ensure_ascii=False),
                 old["privacy"], old.get("confidence", 0.5), old.get("source_ref", ""),
                 old.get("metadata", "{}"), old["updated_at"]),
            )
            from .graph import normalize_alias, normalize_name
            entity.version = int(old.get("version", 1)) + 1
            entity.updated_at = time.time()
            conn.execute(
                "UPDATE v2_entities SET canonical_name=?, normalized_name=?,"
                " privacy=?, confidence=?, confidence_basis=?, source_type=?,"
                " source_ref=?, version=?, metadata=?, updated_at=?, status=?"
                " WHERE id=?",
                (entity.canonical_name.strip(),
                 normalize_name(entity.canonical_name),
                 entity.privacy.value, float(entity.confidence),
                 entity.confidence_basis.value, entity.source_type.value,
                 entity.source_ref, entity.version,
                 json.dumps(entity.metadata or {}, ensure_ascii=False),
                 entity.updated_at, entity.status.value, entity.id),
            )
            for alias in dict.fromkeys(a.strip() for a in entity.aliases if a.strip()):
                conn.execute(
                    "INSERT OR IGNORE INTO v2_entity_aliases"
                    " (entity_id, alias, normalized_alias, created_at)"
                    " VALUES (?,?,?,?)",
                    (entity.id, alias, normalize_alias(alias), entity.updated_at))
            return entity

    def entity_versions(self, entity_id: int) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            try:
                cols = [d[0] for d in conn.execute(
                    "SELECT * FROM v2_entity_versions LIMIT 0").description]
                rows = conn.execute(
                    "SELECT * FROM v2_entity_versions WHERE entity_id=? ORDER BY version",
                    (entity_id,)).fetchall()
                return [dict(zip(cols, row)) for row in rows]
            except Exception:
                return []

    def link_entities(self, relation: RelationV2) -> RelationV2:
        """Idempotente por (src, type, dst). Simétricas canonicalizadas
        (menor id primeiro); reverso conta como duplicata. Endpoints
        precisam estar ativos/disputados (nunca merged/arquivados)."""
        from .graph import canonical_edge
        from ...orchestrator.models import DataClassification as _DC
        relation.validate()
        src, dst = canonical_edge(relation.relation_type.value,
                                  relation.source_entity_id,
                                  relation.target_entity_id)
        if src == dst:
            raise ValueError("relação resultaria em self-edge")
        now = time.time()
        with v2_connect(self.db_path) as conn:
            for eid in (src, dst):
                row = conn.execute(
                    "SELECT status FROM v2_entities WHERE id=?", (eid,)).fetchone()
                if not row or row[0] not in ("active", "disputed"):
                    raise KeyError("entidade %s inexistente/inativa p/ relação" % eid)
            conn.execute(
                "INSERT INTO v2_relations (source_entity_id, relation_type, target_entity_id,"
                " confidence, confidence_basis, privacy, source_type, source_ref,"
                " version, metadata, created_at, updated_at, status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(source_entity_id, relation_type, target_entity_id) DO UPDATE SET"
                " confidence=excluded.confidence,"
                " confidence_basis=excluded.confidence_basis,"
                " privacy=excluded.privacy, source_type=excluded.source_type,"
                " source_ref=excluded.source_ref, metadata=excluded.metadata,"
                " updated_at=excluded.updated_at",
                (src, relation.relation_type.value, dst,
                 float(relation.confidence), relation.confidence_basis.value,
                 relation.privacy.value, relation.source_type.value,
                 relation.source_ref, int(relation.version or 1),
                 json.dumps(relation.metadata or {}, ensure_ascii=False),
                 now, now, relation.status.value),
            )
            row = conn.execute(
                "SELECT id, created_at, version FROM v2_relations"
                " WHERE source_entity_id=? AND relation_type=?"
                " AND target_entity_id=?", (src, relation.relation_type.value, dst)
            ).fetchone()
            relation.id = int(row[0])
            relation.source_entity_id = src
            relation.target_entity_id = dst
            relation.created_at = float(row[1])
            relation.updated_at = now
            relation.version = int(row[2])
            return relation

    def get_relation(self, relation_id: int) -> Optional[RelationV2]:
        with v2_connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM v2_relations WHERE id=?",
                               (relation_id,)).fetchone()
            if not row:
                return None
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_relations LIMIT 0").description]
            return self._row_to_relation(dict(zip(cols, row)))

    def update_relation(self, relation: RelationV2) -> RelationV2:
        """Mudança material (confidence/privacy/status/...): snapshot +
        version++. Mesma transação."""
        if not relation.id:
            raise ValueError("update_relation exige id")
        relation.validate()
        with v2_connect(self.db_path) as conn:
            current = conn.execute("SELECT * FROM v2_relations WHERE id=?",
                                   (relation.id,)).fetchone()
            if not current:
                raise KeyError("relação %s inexistente" % relation.id)
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_relations LIMIT 0").description]
            old = dict(zip(cols, current))
            conn.execute(
                "INSERT INTO v2_relation_versions (relation_id, version, relation_type,"
                " source_entity_id, target_entity_id, confidence, privacy, status,"
                " source_ref, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (relation.id, old.get("version", 1), old["relation_type"],
                 old["source_entity_id"], old["target_entity_id"],
                 old.get("confidence", 0.5), old["privacy"], old["status"],
                 old.get("source_ref", ""), old.get("updated_at", 0)),
            )
            relation.version = int(old.get("version", 1)) + 1
            relation.updated_at = time.time()
            conn.execute(
                "UPDATE v2_relations SET confidence=?, confidence_basis=?, privacy=?,"
                " source_type=?, source_ref=?, version=?, metadata=?,"
                " updated_at=?, status=? WHERE id=?",
                (float(relation.confidence), relation.confidence_basis.value,
                 relation.privacy.value, relation.source_type.value,
                 relation.source_ref, relation.version,
                 json.dumps(relation.metadata or {}, ensure_ascii=False),
                 relation.updated_at, relation.status.value, relation.id),
            )
            return relation

    def relation_versions(self, relation_id: int) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            try:
                cols = [d[0] for d in conn.execute(
                    "SELECT * FROM v2_relation_versions LIMIT 0").description]
                rows = conn.execute(
                    "SELECT * FROM v2_relation_versions WHERE relation_id=?"
                    " ORDER BY version", (relation_id,)).fetchall()
                return [dict(zip(cols, row)) for row in rows]
            except Exception:
                return []

    def get_relations(self, entity_id: int, direction: str = "both",
                      relation_type: Optional[str] = None,
                      statuses: tuple = ("active",)) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute("SELECT * FROM v2_relations LIMIT 0").description]
            clauses = []
            params: list = []
            if direction == "outgoing":
                clauses.append("source_entity_id=?")
                params.append(entity_id)
            elif direction == "incoming":
                clauses.append("target_entity_id=?")
                params.append(entity_id)
            else:
                clauses.append("(source_entity_id=? OR target_entity_id=?)")
                params += [entity_id, entity_id]
            if relation_type:
                clauses.append("relation_type=?")
                params.append(relation_type)
            if statuses:
                clauses.append("status IN (%s)" % ",".join("?" * len(statuses)))
                params += list(statuses)
            rows = conn.execute(
                "SELECT * FROM v2_relations WHERE %s" % " AND ".join(clauses),
                params).fetchall()
            return [dict(zip(cols, row)) for row in rows]

    # ── M1.2 graph: resolve / merge / links / evidence / query ────

    @staticmethod
    def _row_to_entity(data: Dict[str, Any],
                       aliases: List[str]) -> EntityV2:
        from .record import EntityV2 as _E
        from .types import ConfidenceBasis, EntityType, RecordStatus, SourceType
        return _E(id=data.get("id"),
                  entity_type=EntityType(data.get("entity_type", "other")),
                  canonical_name=data.get("canonical_name", ""),
                  aliases=list(aliases or []),
                  privacy=SQLiteMemoryStore._privacy(
                      data.get("privacy", "INTERNAL")),
                  confidence=float(data.get("confidence", 0.5) or 0.0),
                  confidence_basis=ConfidenceBasis(
                      data.get("confidence_basis", "inferred")),
                  source_type=SourceType(data.get("source_type", "system")),
                  source_ref=data.get("source_ref", "") or "",
                  version=int(data.get("version", 1) or 1),
                  metadata=json.loads(data.get("metadata") or "{}"),
                  created_at=data.get("created_at", 0),
                  updated_at=data.get("updated_at", 0),
                  status=RecordStatus(data.get("status", "active")))

    @staticmethod
    def _row_to_relation(data: Dict[str, Any]) -> RelationV2:
        from .types import ConfidenceBasis, RecordStatus, RelationType, SourceType
        return RelationV2(
            id=data.get("id"),
            source_entity_id=int(data.get("source_entity_id", 0)),
            relation_type=RelationType(data.get("relation_type", "related_to")),
            target_entity_id=int(data.get("target_entity_id", 0)),
            confidence=float(data.get("confidence", 0.5) or 0.0),
            confidence_basis=ConfidenceBasis(
                data.get("confidence_basis", "inferred")),
            privacy=SQLiteMemoryStore._privacy(data.get("privacy", "INTERNAL")),
            source_type=SourceType(data.get("source_type", "system")),
            source_ref=data.get("source_ref", "") or "",
            version=int(data.get("version", 1) or 1),
            metadata=json.loads(data.get("metadata") or "{}"),
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
            status=RecordStatus(data.get("status", "active")))

    def _entity_by_row(self, row, cols) -> EntityV2:
        data = dict(zip(cols, row))
        return data  # placeholder nunca usado (ver _entity_from_id)

    def _entity_from_id(self, conn, entity_id: int) -> Optional[EntityV2]:
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM v2_entities LIMIT 0").description]
        row = conn.execute("SELECT * FROM v2_entities WHERE id=?",
                           (entity_id,)).fetchone()
        if not row:
            return None
        aliases = [r[0] for r in conn.execute(
            "SELECT alias FROM v2_entity_aliases WHERE entity_id=? ORDER BY alias",
            (entity_id,))]
        return self._row_to_entity(dict(zip(cols, row)), aliases)

    def resolve_entity(self, name: str, entity_type: Optional[str] = None,
                       clearance: str = "INTERNAL"):
        """exact canonical → normalized canonical → exact alias →
        normalized alias. >1 candidato = AMBIGUOUS (nunca chuta)."""
        from .graph import (EntityResolution, ResolutionStatus, normalize_alias,
                            normalize_name, privacy_allows)
        text = str(name or "").strip()
        if not text:
            return EntityResolution(status=ResolutionStatus.NOT_FOUND)
        norm = normalize_name(text)
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_entities LIMIT 0").description]
            clauses = ["status IN ('active','disputed')"]
            params: list = []
            if entity_type:
                clauses.append("entity_type=?")
                params.append(entity_type)
            base = "SELECT * FROM v2_entities WHERE %s" % " AND ".join(clauses)

            def _visible(rows) -> list:
                out = []
                for row in rows:
                    ent = self._entity_from_id(conn, row[0])
                    if ent is not None and privacy_allows(
                            clearance, ent.privacy.value):
                        out.append(ent)
                return out

            exact = _visible(conn.execute(
                base + " AND canonical_name=?", params + [text]).fetchall())
            if len(exact) == 1:
                return EntityResolution(status=ResolutionStatus.FOUND,
                                        entity=self._to_node(exact[0]))
            candidates = list(exact)
            if not candidates:
                candidates = _visible(conn.execute(
                    base + " AND normalized_name=?", params + [norm]).fetchall())
            if not candidates:
                seen_ids = set()
                alias_ids: list = []
                for query in (text,):
                    alias_ids += [r[0] for r in conn.execute(
                        "SELECT entity_id FROM v2_entity_aliases WHERE alias=?",
                        (query,)).fetchall()]
                alias_ids += [r[0] for r in conn.execute(
                    "SELECT entity_id FROM v2_entity_aliases"
                    " WHERE normalized_alias=?", (normalize_alias(text),)
                ).fetchall()]
                for eid in alias_ids:
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    ent = self._entity_from_id(conn, int(eid))
                    if ent is None or ent.status.value not in ("active", "disputed"):
                        continue
                    if entity_type and ent.entity_type.value != entity_type:
                        continue
                    if privacy_allows(clearance, ent.privacy.value):
                        candidates.append(ent)
            if len(candidates) == 1:
                return EntityResolution(status=ResolutionStatus.FOUND,
                                        entity=self._to_node(candidates[0]))
            if candidates:
                ordered = sorted(candidates, key=lambda e: e.canonical_name)
                return EntityResolution(
                    status=ResolutionStatus.AMBIGUOUS,
                    candidates=[self._to_node(e) for e in ordered])
            return EntityResolution(status=ResolutionStatus.NOT_FOUND)

    @staticmethod
    def _to_node(entity: EntityV2):
        from .graph import GraphNode, source_trust
        return GraphNode(entity_id=int(entity.id or 0),
                         entity_type=entity.entity_type.value,
                         canonical_name=entity.canonical_name,
                         aliases=list(entity.aliases or []),
                         privacy=entity.privacy.value,
                         status=entity.status.value,
                         trust=source_trust(entity.source_type.value).value,
                         confidence=float(entity.confidence))

    def merge_entities(self, source_id: int, target_id: int,
                       source_ref: str = "") -> Dict[str, Any]:
        """Transacional: rewiring sem duplicatas (evidência preservada),
        aliases/memórias movidos, source → MERGED. Sem merge automático
        (sempre chamada explícita)."""
        from .graph import canonical_edge, relation_direction  # noqa
        if int(source_id) == int(target_id):
            raise ValueError("merge exige IDs distintos")
        now = time.time()
        summary: Dict[str, Any] = {"moved_relations": 0, "dropped_duplicates": 0,
                                   "moved_aliases": 0, "moved_memories": 0}
        with v2_connect(self.db_path) as conn:
            src = self._entity_from_id(conn, int(source_id))
            dst = self._entity_from_id(conn, int(target_id))
            if src is None or dst is None:
                raise KeyError("entidade origem/destino inexistente")
            if src.status.value != "active":
                raise ValueError("origem precisa estar ativa p/ merge")
            if dst.status.value not in ("active", "disputed"):
                raise ValueError("destino precisa estar ativo/disputado")
            # aliases → destino (conflito ignora, nunca sobrescreve)
            from .graph import normalize_alias as _na
            for alias in src.aliases:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO v2_entity_aliases"
                    " (entity_id, alias, normalized_alias, created_at)"
                    " VALUES (?,?,?,?)",
                    (dst.id, alias, _na(alias), now))
                summary["moved_aliases"] += cur.rowcount
            # nome canônico da origem vira alias do destino (histórico)
            cur = conn.execute(
                "INSERT OR IGNORE INTO v2_entity_aliases"
                " (entity_id, alias, normalized_alias, created_at)"
                " VALUES (?,?,?,?)",
                (dst.id, src.canonical_name, _na(src.canonical_name), now))
            summary["moved_aliases"] += cur.rowcount
            # relations → rewiring
            rel_cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_relations LIMIT 0").description]
            rows = conn.execute(
                "SELECT * FROM v2_relations WHERE source_entity_id=?"
                " OR target_entity_id=?", (src.id, src.id)).fetchall()
            for row in rows:
                rel = dict(zip(rel_cols, row))
                new_src = dst.id if rel["source_entity_id"] == src.id else rel[
                    "source_entity_id"]
                new_dst = dst.id if rel["target_entity_id"] == src.id else rel[
                    "target_entity_id"]
                if new_src == new_dst:
                    summary["dropped_duplicates"] += 1
                    conn.execute("DELETE FROM v2_relations WHERE id=?",
                                 (rel["id"],))
                    continue
                new_src, new_dst = canonical_edge(rel["relation_type"],
                                                  new_src, new_dst)
                dup = conn.execute(
                    "SELECT id FROM v2_relations WHERE source_entity_id=?"
                    " AND relation_type=? AND target_entity_id=? AND id<>?",
                    (new_src, rel["relation_type"], new_dst, rel["id"])).fetchone()
                if dup:
                    # preserva evidências antes de remover duplicata
                    conn.execute(
                        "UPDATE OR IGNORE v2_relation_evidence SET relation_id=?"
                        " WHERE relation_id=?", (dup[0], rel["id"]))
                    conn.execute("DELETE FROM v2_relations WHERE id=?", (rel["id"],))
                    summary["dropped_duplicates"] += 1
                    continue
                conn.execute(
                    "UPDATE v2_relations SET source_entity_id=?,"
                    " target_entity_id=?, updated_at=? WHERE id=?",
                    (new_src, new_dst, now, rel["id"]))
                summary["moved_relations"] += 1
            # memory links → destino
            for (mid, role) in conn.execute(
                    "SELECT memory_id, link_role FROM v2_memory_entities"
                    " WHERE entity_id=? AND status='active'", (src.id,)).fetchall():
                cur = conn.execute(
                    "INSERT OR IGNORE INTO v2_memory_entities"
                    " (memory_id, entity_id, link_role, created_at, status)"
                    " VALUES (?,?,?,?,?)", (mid, dst.id, role, now, "active"))
                summary["moved_memories"] += cur.rowcount
            conn.execute("UPDATE v2_memory_entities SET status='merged'"
                         " WHERE entity_id=?", (src.id,))
            # origem → MERGED (snapshot p/ histórico)
            conn.execute(
                "INSERT INTO v2_entity_versions (entity_id, version, entity_type,"
                " canonical_name, aliases_json, privacy, confidence, source_ref,"
                " metadata, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (src.id, src.version, src.entity_type.value, src.canonical_name,
                 json.dumps(src.aliases, ensure_ascii=False), src.privacy.value,
                 float(src.confidence), src.source_ref,
                 json.dumps(src.metadata, ensure_ascii=False), src.updated_at))
            merged_meta = dict(dst.metadata or {})
            merged_from = list(merged_meta.get("merged_from", []) or [])
            if src.id not in merged_from:
                merged_from.append(src.id)
            merged_meta["merged_from"] = merged_from
            conn.execute(
                "UPDATE v2_entities SET status='merged', updated_at=?,"
                " version=version+1 WHERE id=?", (now, src.id))
            conn.execute(
                "UPDATE v2_entities SET metadata=?, updated_at=? WHERE id=?",
                (json.dumps(merged_meta, ensure_ascii=False), now, dst.id))
            summary.update({"source_id": src.id, "target_id": dst.id,
                            "source_ref": source_ref})
            return summary

    # ── internos ─────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(data: Dict[str, Any]) -> MemoryRecordV2:
        from .record import MemoryRecordV2 as _R
        from .types import (ConfidenceBasis, MemoryKind, RecordStatus, SourceType)
        from ...orchestrator.models import DataClassification as _DC
        return _R(id=data.get("id"), memory_type=MemoryKind(data["memory_type"]),
                  title=data.get("title", ""), content=data.get("content", ""),
                  summary=data.get("summary", ""),
                  status=RecordStatus(data.get("status", "active")),
                  created_at=data.get("created_at", 0), updated_at=data.get("updated_at", 0),
                  last_accessed_at=data.get("last_accessed_at", 0),
                  version=int(data.get("version", 1)),
                  confidence=float(data.get("confidence", 0.5)),
                  confidence_basis=ConfidenceBasis(data.get("confidence_basis", "inferred")),
                  privacy=_DC(data.get("privacy", "INTERNAL")),
                  source_type=SourceType(data.get("source_type", "system")),
                  source_ref=data.get("source_ref", ""),
                  source_timestamp=data.get("source_timestamp", 0),
                  project=data.get("project", ""),
                  tags=_tags_from_json(data.get("tags", "[]")),
                  metadata=json.loads(data.get("metadata") or "{}"),
                  embedding_status=data.get("embedding_status", "pending"),
                  embedding_model=data.get("embedding_model", ""),
                  content_hash=data.get("content_hash", ""),
                  canonical_key=data.get("canonical_key", ""))

    @staticmethod
    def _entity_type(value: str):
        from .types import EntityType as _ET
        return _ET(value)

    @staticmethod
    def _privacy(value: str):
        from ...orchestrator.models import DataClassification as _DC
        return _DC(value)

    @staticmethod
    def _status(value: str):
        from .types import RecordStatus as _RS
        return _RS(value)


class MarkdownMemoryStore(MemoryStore):
    """Projeção Markdown/Obsidian (M1.1). NÃO é fonte de verdade.

    - Identidade: frontmatter `id` (mem_<id> / ent_<id>); nome do arquivo
      pode mudar sem quebrar o vínculo (resolve via v2_projections + scan).
    - Escrita: single-writer (lock por record) + atomic_write.
    - Falha de disco/vault nunca levanta para o engine quando usada via
      `project_record` com `degraded=True` (marca ERROR/PENDING).
    - Edição externa nunca é importada; `check_drift` só classifica.
    """

    def __init__(self, vault_root: Path | str, db_path: Path | str):
        from . import vault as _vault
        from .migrations import ensure_v2_schema as _ensure
        self.vault_root = Path(vault_root)
        self.db_path = Path(db_path)
        _ensure(self.db_path)
        _vault.ensure_vault(self.vault_root)
        self._locks = _vault.RecordLockRegistry()

    # ── contrato MemoryStore (opera sobre a projeção) ─────────────

    def save(self, record: MemoryRecordV2) -> MemoryRecordV2:
        self.project_record(record)
        return record

    def load(self, record_id: int) -> Optional[MemoryRecordV2]:
        text = self.read_record(int(record_id))
        if text is None:
            return None
        from . import vault as _vault
        from .record import MemoryRecordV2 as _R
        front, body = _vault.split_note(text)
        return _R(id=int(record_id),
                  title=self._body_title(body),
                  content=body,
                  tags=list(front.get("tags", []) or []))

    def update(self, record: MemoryRecordV2) -> MemoryRecordV2:
        self.project_record(record)
        return record

    def set_status(self, record_id: int, status: RecordStatus) -> bool:
        from . import vault as _vault
        with self._locks.acquire("memory:%d" % int(record_id)):
            state = self._projection_state(int(record_id), "memory")
            path = Path(state["path"]) if state and state.get("path") else None
            if path is None:
                path = self._scan_for_id("mem_%d" % int(record_id))
            if path is None or not path.exists():
                return False
            if status == RecordStatus.ARCHIVED:
                return bool(self._move_to_archive(path, int(record_id), "memory"))
            self._patch_front_field(path, "status", status.value)
            return True

    def find_by_hash(self, content_hash: str, namespace_project: str = "") -> Optional[MemoryRecordV2]:
        return None  # hash canônico vive no SQLite; projeção não indexa

    def find_by_canonical(self, canonical_key: str,
                          namespace_project: str = "") -> Optional[MemoryRecordV2]:
        if not canonical_key:
            return None
        for note_id, path in self.list_records(kind="memory"):
            try:
                from . import vault as _vault
                front, _ = _vault.split_note(path.read_text(encoding="utf-8"))
                if (str(front.get("canonical_key", "") or "") == canonical_key
                        and str(front.get("project", "") or "") == namespace_project):
                    return self.load(int(note_id.split("_", 1)[1]))
            except Exception:
                continue
        return None

    def versions(self, record_id: int) -> List[Dict[str, Any]]:
        return []  # histórico completo vive em v2_memory_versions

    # ── projeção (API estendida M1.1) ─────────────────────────────

    def project_record(self, record: MemoryRecordV2,
                       related: Optional[List[str]] = None,
                       degraded: bool = True) -> Dict[str, Any]:
        """Gera/atualiza a nota. Retorna {path, sync_status, detail}.
        Com degraded=True nunca levanta (marca ERROR/PENDING)."""
        from . import vault as _vault
        from .migrations import v2_set_projection
        ref = int(record.id or 0)
        if not ref:
            raise ValueError("projeção exige record.id (SQLite primeiro)")
        try:
            ok, reason = _vault.export_decision(record)
            if not ok:
                v2_set_projection(self.db_path, ref, "memory", "",
                                  "", int(record.version or 0),
                                  SyncStatus.IGNORED.value, reason)
                return {"path": "", "sync_status": SyncStatus.IGNORED.value,
                        "detail": reason}
            _vault.scrub_for_projection(record)
            with self._locks.acquire("memory:%d" % ref):
                folder = _vault.folder_for_record(
                    str(getattr(record.memory_type, "value",
                                record.memory_type)),
                    project=str(getattr(record, "project", "") or ""),
                    tags=list(getattr(record, "tags", []) or []),
                    metadata=dict(getattr(record, "metadata", None) or {}))
                date_prefix = ""
                mtype = str(getattr(record.memory_type, "value",
                                    record.memory_type)).lower()
                if mtype == "episodic":
                    date_prefix = time.strftime("%Y-%m-%d",
                                                time.localtime(record.created_at or
                                                               time.time()))
                if record.status == RecordStatus.ARCHIVED:
                    folder = "90_Archive"
                filename = _vault.record_filename(
                    str(getattr(record, "title", "") or ""), ref, date_prefix)
                path = self.vault_root / folder / filename
                old = self._known_path(ref, "memory", "mem_%d" % ref)
                if old is not None and old != path and old.exists():
                    try:
                        old.unlink()
                    except OSError:
                        pass
                text = _vault.render_record_note(record, related)
                _vault.atomic_write(path, text)
                v2_set_projection(self.db_path, ref, "memory", str(path),
                                  _vault.projection_hash(text),
                                  int(record.version or 0),
                                  SyncStatus.SYNCED.value, "projected")
                return {"path": str(path),
                        "sync_status": SyncStatus.SYNCED.value, "detail": "projected"}
        except Exception as exc:
            try:
                from .migrations import v2_set_projection as _set
                _set(self.db_path, ref, "memory", "", "",
                     int(getattr(record, "version", 0) or 0),
                     SyncStatus.ERROR.value, "%s: %s" % (
                         type(exc).__name__, str(exc)[:200]))
            except Exception:
                pass
            if degraded:
                return {"path": "", "sync_status": SyncStatus.ERROR.value,
                        "detail": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
            raise

    def project_entity(self, entity, related: Optional[List] = None,
                       memories: Optional[List[str]] = None,
                       degraded: bool = True) -> Dict[str, Any]:
        from . import vault as _vault
        from .migrations import v2_set_projection
        ref = int(entity.id or 0)
        if not ref:
            raise ValueError("projeção exige entity.id (SQLite primeiro)")
        try:
            with self._locks.acquire("entity:%d" % ref):
                folder = _vault.folder_for_entity(
                    str(getattr(entity.entity_type, "value",
                                entity.entity_type)))
                filename = _vault.entity_filename(
                    str(getattr(entity, "canonical_name", "") or ""), ref)
                path = self.vault_root / folder / filename
                old = self._known_path(ref, "entity", "ent_%d" % ref)
                if old is not None and old != path and old.exists():
                    try:
                        old.unlink()
                    except OSError:
                        pass
                text = _vault.render_entity_note(entity, related, memories)
                _vault.atomic_write(path, text)
                v2_set_projection(self.db_path, ref, "entity", str(path),
                                  _vault.projection_hash(text),
                                  int(getattr(entity, "version", 1) or 1),
                                  SyncStatus.SYNCED.value, "projected")
                return {"path": str(path),
                        "sync_status": SyncStatus.SYNCED.value, "detail": "projected"}
        except Exception as exc:
            try:
                from .migrations import v2_set_projection as _set
                _set(self.db_path, ref, "entity", "", "", 1,
                     SyncStatus.ERROR.value, "%s: %s" % (
                         type(exc).__name__, str(exc)[:200]))
            except Exception:
                pass
            if degraded:
                return {"path": "", "sync_status": SyncStatus.ERROR.value,
                        "detail": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
            raise

    def read_record(self, record_id: int) -> Optional[str]:
        path = self._known_path(int(record_id), "memory",
                                "mem_%d" % int(record_id))
        if path is not None and path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def resolve_path(self, kind: str, ref_id: int) -> Optional[str]:
        path = self._known_path(int(ref_id), kind,
                                "%s_%d" % ("mem" if kind == "memory" else "ent",
                                           int(ref_id)))
        return str(path) if path is not None else None

    def list_records(self, kind: str = "memory") -> List[tuple]:
        """[(note_id, Path)] de notas gerenciadas. Humanas nunca listadas."""
        from . import vault as _vault
        prefix = "mem_" if kind == "memory" else "ent_"
        found = []
        if not self.vault_root.exists():
            return found
        for path in sorted(self.vault_root.rglob("*.md")):
            try:
                if path.name == "README.md":
                    continue
                front, _ = _vault.split_note(
                    path.read_text(encoding="utf-8"))
                if front.get("managed_by") != _vault.MANAGED_BY:
                    continue
                note_id = str(front.get("id", "") or "")
                if note_id.startswith(prefix):
                    found.append((note_id, path))
            except Exception:
                continue
        return found

    def archive_record(self, record_id: int) -> bool:
        with self._locks.acquire("memory:%d" % int(record_id)):
            path = self._known_path(int(record_id), "memory",
                                    "mem_%d" % int(record_id))
            if path is None or not path.exists():
                return False
            return bool(self._move_to_archive(path, int(record_id), "memory"))

    def archive_entity(self, entity_id: int) -> bool:
        with self._locks.acquire("entity:%d" % int(entity_id)):
            path = self._known_path(int(entity_id), "entity",
                                    "ent_%d" % int(entity_id))
            if path is None or not path.exists():
                return False
            return bool(self._move_to_archive(path, int(entity_id), "entity"))

    def delete_projection_if_safe(self, record_id: int,
                                  kind: str = "memory") -> bool:
        """Só apaga nota gerenciada com ID conhecido. Humana: nunca."""
        from . import vault as _vault
        prefix = "mem_" if kind == "memory" else "ent_"
        with self._locks.acquire("%s:%d" % (kind, int(record_id))):
            path = self._known_path(int(record_id), kind,
                                    "%s%d" % (prefix, int(record_id)))
            if path is None or not path.exists():
                return False
            try:
                front, _ = _vault.split_note(path.read_text(encoding="utf-8"))
            except Exception:
                return False
            if (front.get("managed_by") != _vault.MANAGED_BY
                    or str(front.get("id", "")) != "%s%d" % (prefix,
                                                             int(record_id))):
                return False
            path.unlink()
            return True

    def check_drift(self, record, kind: str = "memory") -> Dict[str, Any]:
        """Compara SQLite canônico vs projeção. Nunca altera conteúdo;
        só classifica (+ persiste o status detectado)."""
        from . import vault as _vault
        from .migrations import v2_set_projection
        ref = int(getattr(record, "id", 0) or 0)
        note_id = "%s%d" % ("mem_" if kind == "memory" else "ent_", ref)
        state = self._projection_state(ref, kind)
        if state is None:
            return {"sync_status": SyncStatus.PENDING.value,
                    "detail": "never-projected"}
        path = Path(state["path"]) if state.get("path") else None
        if path is None or not path.exists():
            found = self._scan_for_id(note_id)
            if found is None:
                v2_set_projection(self.db_path, ref, kind, "", "",
                                  int(getattr(record, "version", 1) or 1),
                                  SyncStatus.PENDING.value, "file-missing")
                return {"sync_status": SyncStatus.PENDING.value,
                        "detail": "file-missing"}
            path = found
        try:
            text = path.read_text(encoding="utf-8")
            front, _ = _vault.split_note(text)
        except Exception as exc:
            return {"sync_status": SyncStatus.ERROR.value,
                    "detail": "unreadable: %s" % type(exc).__name__}
        if (front.get("managed_by") != _vault.MANAGED_BY
                or str(front.get("id", "")) != note_id):
            return {"sync_status": SyncStatus.CONFLICT.value,
                    "detail": "identity-mismatch"}
        current_version = int(getattr(record, "version", 1) or 1)
        record_changed = current_version != int(state.get("projection_version", -1))
        file_changed = (_vault.projection_hash(text)
                        != str(state.get("projection_hash", "")))
        if record_changed and file_changed:
            status, detail = SyncStatus.CONFLICT, "both-changed"
        elif file_changed:
            status, detail = SyncStatus.DRIFT, "external-edit"
        elif record_changed:
            status, detail = SyncStatus.PENDING, "record-updated"
        else:
            return {"sync_status": SyncStatus.SYNCED.value, "detail": "ok",
                    "path": str(path)}
        v2_set_projection(self.db_path, ref, kind, str(path),
                          str(state.get("projection_hash", "")),
                          int(state.get("projection_version", 0)),
                          status.value, detail)
        return {"sync_status": status.value, "detail": detail,
                "path": str(path)}

    # ── internos ─────────────────────────────────────────────────

    def _projection_state(self, ref_id: int, kind: str) -> Optional[Dict[str, Any]]:
        from .migrations import v2_get_projection
        try:
            return v2_get_projection(self.db_path, int(ref_id), kind)
        except Exception:
            return None

    def _known_path(self, ref_id: int, kind: str,
                    note_id: str) -> Optional[Path]:
        state = self._projection_state(ref_id, kind)
        if state and state.get("path"):
            candidate = Path(state["path"])
            if candidate.exists():
                return candidate
        return self._scan_for_id(note_id)

    def _scan_for_id(self, note_id: str) -> Optional[Path]:
        from . import vault as _vault
        if not self.vault_root.exists():
            return None
        for path in self.vault_root.rglob("*.md"):
            try:
                front, _ = _vault.split_note(
                    path.read_text(encoding="utf-8"))
                if (front.get("managed_by") == _vault.MANAGED_BY
                        and str(front.get("id", "")) == note_id):
                    return path
            except Exception:
                continue
        return None

    def _move_to_archive(self, path: Path, ref_id: int, kind: str) -> Optional[Path]:
        from . import vault as _vault
        from .migrations import v2_set_projection
        dest = self.vault_root / "90_Archive" / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest != path:
            stem, suffix = path.stem, path.suffix
            cand = self.vault_root / "90_Archive" / ("%s--%s%s" % (
                stem, kind, suffix))
            dest = cand
        self._patch_front_field(path, "status", RecordStatus.ARCHIVED.value)
        text = path.read_text(encoding="utf-8")
        _vault.atomic_write(dest, text)
        try:
            path.unlink()
        except OSError:
            pass
        try:
            state = self._projection_state(ref_id, kind)
            v2_set_projection(self.db_path, ref_id, kind, str(dest),
                              _vault.projection_hash(text),
                              int((state or {}).get("projection_version", 0)),
                              SyncStatus.SYNCED.value, "archived")
        except Exception:
            pass
        return dest

    @staticmethod
    def _patch_front_field(path: Path, field: str, value: str) -> None:
        from . import vault as _vault
        text = path.read_text(encoding="utf-8")
        front, _ = _vault.split_note(text)
        front[field] = value
        ordered = [(k, front[k]) for k in front]
        new_text = _vault.render_frontmatter(ordered) + "\n" + _vault.split_note(
            text)[1].lstrip("\n")
        if not new_text.endswith("\n"):
            new_text += "\n"
        _vault.atomic_write(path, new_text)

    @staticmethod
    def _body_title(body: str) -> str:
        for line in str(body or "").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""
