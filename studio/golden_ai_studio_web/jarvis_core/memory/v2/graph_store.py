"""Golden Memory Engine V2 — mixin de grafo do SQLiteMemoryStore (M1.2).

Consultas, links memória↔entidade, evidências, integridade e stats.
Escrita canônica continua no engine (single-writer); aqui só SQL.
"""
import time
from typing import Any, Dict, List, Optional

from .migrations import v2_connect


class GraphStoreMixin:
    """Requer do hospedeiro: db_path, _entity_from_id, _row_to_entity,
    _row_to_relation, _to_node."""

    # ── links memória↔entidade ───────────────────────────────────

    def link_memory_entity(self, memory_id: int, entity_id: int,
                           link_role: str = "related") -> Dict[str, Any]:
        with v2_connect(self.db_path) as conn:
            mem = conn.execute("SELECT status FROM v2_memories WHERE id=?",
                               (memory_id,)).fetchone()
            if not mem or mem[0] == "deleted_logical":
                raise KeyError("memória %s inexistente" % memory_id)
            ent = conn.execute("SELECT status FROM v2_entities WHERE id=?",
                               (entity_id,)).fetchone()
            if not ent or ent[0] not in ("active", "disputed"):
                raise KeyError("entidade %s indisponível" % entity_id)
            conn.execute(
                "INSERT INTO v2_memory_entities (memory_id, entity_id, link_role,"
                " created_at, status) VALUES (?,?,?,?,?)"
                " ON CONFLICT(memory_id, entity_id, link_role) DO UPDATE SET"
                " status='active'",
                (memory_id, entity_id, str(link_role or "related"),
                 time.time(), "active"))
            return {"memory_id": memory_id, "entity_id": entity_id,
                    "link_role": str(link_role or "related")}

    def unlink_memory_entity(self, memory_id: int, entity_id: int,
                             link_role: str = "related") -> bool:
        with v2_connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE v2_memory_entities SET status='archived'"
                " WHERE memory_id=? AND entity_id=? AND link_role=?"
                " AND status='active'", (memory_id, entity_id, link_role))
            return cur.rowcount > 0

    def entities_for_memory(self, memory_id: int,
                            clearance: str = "INTERNAL") -> list:
        from .graph import privacy_allows
        with v2_connect(self.db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT entity_id FROM v2_memory_entities WHERE memory_id=?"
                    " AND status='active'", (memory_id,)).fetchall()
            except Exception:
                return []
            out = []
            for (eid,) in rows:
                ent = self._entity_from_id(conn, int(eid))
                if ent is not None and ent.status.value in ("active", "disputed") \
                        and privacy_allows(clearance, ent.privacy.value):
                    out.append(ent)
            out.sort(key=lambda e: e.canonical_name)
            return out

    def memories_for_entity(self, entity_id: int) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT memory_id, link_role, created_at FROM v2_memory_entities"
                    " WHERE entity_id=? AND status='active' ORDER BY created_at",
                    (entity_id,)).fetchall()
                return [{"memory_id": r[0], "link_role": r[1],
                         "created_at": r[2]} for r in rows]
            except Exception:
                return []

    # ── evidências de relação ────────────────────────────────────

    def add_evidence(self, relation_id: int, memory_id: int,
                     note: str = "") -> Dict[str, Any]:
        with v2_connect(self.db_path) as conn:
            rel = conn.execute("SELECT id FROM v2_relations WHERE id=?",
                               (relation_id,)).fetchone()
            if not rel:
                raise KeyError("relação %s inexistente" % relation_id)
            mem = conn.execute("SELECT id FROM v2_memories WHERE id=?",
                               (memory_id,)).fetchone()
            if not mem:
                raise KeyError("memória %s inexistente" % memory_id)
            conn.execute(
                "INSERT INTO v2_relation_evidence (relation_id, memory_id, note,"
                " created_at) VALUES (?,?,?,?)"
                " ON CONFLICT(relation_id, memory_id) DO UPDATE SET note=excluded.note",
                (relation_id, memory_id, str(note or "")[:500], time.time()))
            return {"relation_id": relation_id, "memory_id": memory_id}

    def evidences_for_relation(self, relation_id: int) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT memory_id, note, created_at FROM v2_relation_evidence"
                    " WHERE relation_id=? ORDER BY created_at",
                    (relation_id,)).fetchall()
                return [{"memory_id": r[0], "note": r[1],
                         "created_at": r[2]} for r in rows]
            except Exception:
                return []

    # ── listagem / vizinhança ────────────────────────────────────

    def list_entities(self, entity_type: Optional[str] = None,
                      status: str = "active", clearance: str = "INTERNAL",
                      limit: int = 100, offset: int = 0) -> list:
        from .graph import privacy_allows
        with v2_connect(self.db_path) as conn:
            cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_entities LIMIT 0").description]
            clauses = ["status=?"]
            params: list = [status]
            if entity_type:
                clauses.append("entity_type=?")
                params.append(entity_type)
            rows = conn.execute(
                "SELECT * FROM v2_entities WHERE %s ORDER BY canonical_name ASC"
                " LIMIT ? OFFSET ?" % " AND ".join(clauses),
                params + [int(limit), int(offset)]).fetchall()
            out = []
            for row in rows:
                ent = self._row_to_entity(
                    dict(zip(cols, row)),
                    [r[0] for r in conn.execute(
                        "SELECT alias FROM v2_entity_aliases WHERE entity_id=?"
                        " ORDER BY alias", (row[0],))])
                if privacy_allows(clearance, ent.privacy.value):
                    out.append(ent)
            return out

    def neighbors(self, entity_id: int, relation_type: Optional[str] = None,
                  direction: str = "both", entity_type: Optional[str] = None,
                  clearance: str = "INTERNAL", status: str = "active",
                  limit: int = 50) -> list:
        """Vizinhança com filtros. Ordem determinística: confidence DESC,
        updated_at DESC, canonical_name ASC."""
        from .graph import privacy_allows
        with v2_connect(self.db_path) as conn:
            rel_cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_relations LIMIT 0").description]
            clauses = ["status=?"]
            params: list = [status]
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
            rows = conn.execute(
                "SELECT * FROM v2_relations WHERE %s" % " AND ".join(clauses),
                params).fetchall()
            scored = []
            for row in rows:
                rel = self._row_to_relation(dict(zip(rel_cols, row)))
                if not privacy_allows(clearance, rel.privacy.value):
                    continue
                other_id = (rel.target_entity_id
                            if rel.source_entity_id == entity_id
                            else rel.source_entity_id)
                other = self._entity_from_id(conn, int(other_id))
                if other is None or other.status.value != "active":
                    continue
                if entity_type and other.entity_type.value != entity_type:
                    continue
                if not privacy_allows(clearance, other.privacy.value):
                    continue
                side = ("outgoing" if rel.source_entity_id == entity_id
                        else "incoming")
                scored.append((rel, other, side))
            scored.sort(key=lambda t: (-float(t[0].confidence),
                                       -(t[0].updated_at or 0),
                                       t[1].canonical_name))
            return scored[:int(limit)]

    # ── diagnóstico ──────────────────────────────────────────────

    def alias_conflicts(self) -> List[Dict[str, Any]]:
        with v2_connect(self.db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT normalized_alias FROM v2_entity_aliases"
                    " GROUP BY normalized_alias HAVING"
                    " COUNT(DISTINCT entity_id) > 1").fetchall()
            except Exception:
                return []
            conflicts = []
            for (norm,) in rows:
                ids = [r[0] for r in conn.execute(
                    "SELECT DISTINCT a.entity_id FROM v2_entity_aliases a"
                    " JOIN v2_entities e ON e.id=a.entity_id"
                    " WHERE a.normalized_alias=? AND e.status IN ('active','disputed')",
                    (norm,))]
                if len(ids) > 1:
                    conflicts.append({"normalized_alias": norm,
                                      "entity_ids": sorted(ids)})
            return conflicts

    def orphan_entities(self) -> List[int]:
        with v2_connect(self.db_path) as conn:
            try:
                rows = conn.execute(
                    "SELECT id FROM v2_entities WHERE status='active' AND id NOT IN"
                    " (SELECT source_entity_id FROM v2_relations"
                    " WHERE status='active') AND id NOT IN"
                    " (SELECT target_entity_id FROM v2_relations"
                    " WHERE status='active') AND id NOT IN"
                    " (SELECT entity_id FROM v2_memory_entities"
                    " WHERE status='active') ORDER BY id").fetchall()
                return [r[0] for r in rows]
            except Exception:
                return []

    def graph_counts(self) -> Dict[str, Any]:
        with v2_connect(self.db_path) as conn:
            try:
                ent = conn.execute(
                    "SELECT COUNT(*) FROM v2_entities WHERE status='active'").fetchone()
                rel = conn.execute(
                    "SELECT status, COUNT(*) FROM v2_relations GROUP BY status").fetchall()
                links = conn.execute(
                    "SELECT COUNT(*) FROM v2_memory_entities WHERE status='active'").fetchone()
                counts = {"entities_total": int(ent[0]) if ent else 0,
                          "relations_total": 0, "relations_active": 0,
                          "relations_disputed": 0, "memory_links": int(
                              links[0]) if links else 0}
                for status, total in rel:
                    counts["relations_total"] += int(total)
                    if status == "active":
                        counts["relations_active"] = int(total)
                    if status == "disputed":
                        counts["relations_disputed"] = int(total)
                counts["orphan_entities"] = len(self.orphan_entities())
                counts["duplicate_alias_conflicts"] = len(self.alias_conflicts())
                return counts
            except Exception:
                return {"entities_total": 0, "relations_total": 0}

    def validate_graph(self) -> Dict[str, Any]:
        """Integridade: dangling, duplicata simétrica, tipo/privacy/status
        inválidos, self-edge, alias ambíguo. Ciclos NÃO são erro."""
        from .graph import RELATION_CATALOG
        issues: List[Dict[str, Any]] = []
        with v2_connect(self.db_path) as conn:
            ent_cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_entities LIMIT 0").description]
            entities = {r[0]: dict(zip(ent_cols, r)) for r in conn.execute(
                "SELECT * FROM v2_entities").fetchall()}
            rel_cols = [d[0] for d in conn.execute(
                "SELECT * FROM v2_relations LIMIT 0").description]
            relations = [dict(zip(rel_cols, r)) for r in conn.execute(
                "SELECT * FROM v2_relations").fetchall()]
            seen_edges = set()
            for rel in relations:
                rid = rel["id"]
                if rel["relation_type"] not in RELATION_CATALOG:
                    issues.append({"code": "invalid-relation-type",
                                   "relation_id": rid})
                if str(rel.get("privacy", "")) not in ("PUBLIC", "INTERNAL",
                                                       "SENSITIVE", "SECRET"):
                    issues.append({"code": "invalid-privacy",
                                   "relation_id": rid})
                if str(rel.get("status", "")) not in ("active", "superseded",
                                                      "disputed", "archived",
                                                      "merged", "deleted_logical"):
                    issues.append({"code": "invalid-status",
                                   "relation_id": rid})
                if rel["source_entity_id"] == rel["target_entity_id"]:
                    issues.append({"code": "self-edge", "relation_id": rid})
                for side in ("source_entity_id", "target_entity_id"):
                    target = entities.get(rel[side])
                    if target is None:
                        issues.append({"code": "dangling-relation",
                                       "relation_id": rid, "side": side})
                    elif target.get("status") not in ("active", "disputed"):
                        issues.append({"code": "inactive-endpoint",
                                       "relation_id": rid, "side": side,
                                       "status": target.get("status")})
                key = (rel["relation_type"], rel["source_entity_id"],
                       rel["target_entity_id"])
                if key in seen_edges:
                    issues.append({"code": "duplicate-edge", "relation_id": rid})
                seen_edges.add(key)
                if rel["relation_type"] in ("related_to", "integrates_with"):
                    rev = (rel["relation_type"], rel["target_entity_id"],
                           rel["source_entity_id"])
                    if rev in seen_edges and rel["source_entity_id"] != rel[
                            "target_entity_id"]:
                        issues.append({"code": "duplicate-symmetric-edge",
                                       "relation_id": rid})
            for conflict in self.alias_conflicts():
                issues.append({"code": "alias-ambiguity", **conflict})
            for eid, ent in entities.items():
                if str(ent.get("privacy", "")) not in ("PUBLIC", "INTERNAL",
                                                       "SENSITIVE", "SECRET"):
                    issues.append({"code": "invalid-entity-privacy",
                                   "entity_id": eid})
        return {"ok": not issues, "issues": issues,
                "issue_count": len(issues)}
