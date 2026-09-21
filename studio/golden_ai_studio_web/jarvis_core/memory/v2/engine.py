"""Golden Memory Engine V2 — porta oficial de memória (M1.0 fundação + M1.1 vault).

Brain/Voice/Radar/futuras Skills falam com o engine; nunca com SQLite,
vetor ou Markdown diretamente. O legado (GoldenMemoryManager) segue
intocado; leitura legada via LegacyMemoryAdapter (compat, sem migração).

M1.1: projeção Markdown/Obsidian pós-commit (degradada, nunca desfaz o
SQLite). `vault_root=None` = modo SQLite-only (zero footprint).
"""
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...orchestrator.models import DataClassification
from .migrations import (V2_SCHEMA_VERSION, ensure_v2_schema,
                         v2_pending_embeddings, v2_schema_version)
from .record import (EntityV2, MemoryRecordV2, MemorySearchResult,
                     MemorySecurityError, RelationV2, content_hash)
from .store import SQLiteMemoryStore
from .types import (ConfidenceBasis, EmbeddingState, EntityType, MatchSource,
                    MemoryKind, RecordStatus, RelationType, SourceType)


class WorkingMemory:
    """Contexto volátil com TTL. Nunca persiste; sessões curtas/follow-up."""

    def __init__(self, default_ttl_seconds: float = 900):
        self.default_ttl = max(1.0, float(default_ttl_seconds))
        self._lock = threading.RLock()
        self._items: Dict[str, tuple] = {}

    def put(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        with self._lock:
            self._items[str(key)] = (value, time.time() + float(
                ttl_seconds if ttl_seconds is not None else self.default_ttl))

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            item = self._items.get(str(key))
            if not item:
                return default
            value, expires = item
            if time.time() > expires:
                self._items.pop(str(key), None)
                return default
            return value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._items.pop(str(key), None)

    def clear_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired = [k for k, (_, exp) in self._items.items() if now > exp]
            for key in expired:
                self._items.pop(key, None)
            return len(expired)


class GoldenMemoryEngine:
    """Fachada central V2. Thread-safe (RLock); falhas degradam, nunca crasham."""

    def __init__(self, db_path: Path | str,
                 embed: Optional[Callable[[str], Optional[List[float]]]] = None,
                 embedding_model: str = "",
                 audit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 vault_root: Optional[Path | str] = None):
        self.db_path = Path(db_path)
        ensure_v2_schema(self.db_path)
        self.store = SQLiteMemoryStore(self.db_path)
        self.working = WorkingMemory()
        self._embed = embed
        self._embedding_model = embedding_model
        self._audit = audit or (lambda event, extra: None)
        self._lock = threading.RLock()
        from .consolidation import MemoryConsolidator
        self.consolidator = MemoryConsolidator(self)
        self.last_consolidation = None
        # M1.1: vault opt-in. None = SQLite-only (zero footprint).
        # Caminho inválido = degradado (marca PENDING, nunca crasha).
        self.vault = None
        self.vault_root: Optional[Path] = None
        self._vault_error = ""
        if vault_root is not None:
            try:
                from .store import MarkdownMemoryStore
                self.vault = MarkdownMemoryStore(vault_root, self.db_path)
                self.vault_root = Path(vault_root)
            except Exception as exc:
                self.vault = None
                self._vault_error = "%s: %s" % (type(exc).__name__,
                                                str(exc)[:200])

    # ── write ────────────────────────────────────────────────────

    def remember(self, content: str, memory_type: MemoryKind = MemoryKind.SEMANTIC,
                 title: str = "", summary: str = "",
                 confidence: float = 0.5,
                 confidence_basis: ConfidenceBasis = ConfidenceBasis.INFERRED,
                 privacy: DataClassification = DataClassification.INTERNAL,
                 source_type: SourceType = SourceType.SYSTEM, source_ref: str = "",
                 project: str = "", tags: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None,
                 canonical_key: str = "") -> MemoryRecordV2:
        """Idempotente: canonical_key existente → update (nova versão);
        hash exato ativo → retorna existente sem duplicar."""
        with self._lock:
            record = MemoryRecordV2(
                memory_type=memory_type, title=title.strip(), content=str(content or ""),
                summary=summary.strip(), confidence=confidence,
                confidence_basis=confidence_basis, privacy=privacy,
                source_type=source_type, source_ref=source_ref,
                source_timestamp=time.time(), project=project,
                tags=list(tags or []), metadata=dict(metadata or {}),
                content_hash=content_hash(content), canonical_key=canonical_key.strip())
            record.validate()
            if record.privacy == DataClassification.SECRET:
                raise MemorySecurityError("SECRET usa vault dedicado, não memória comum")
            duplicate = self.store.find_by_hash(record.content_hash, project)
            if duplicate:
                from .consolidation import ConsolidationDecision, ConsolidationKind
                decision = ConsolidationDecision(
                    ConsolidationKind.EXACT_DUPLICATE, duplicate.id, "content_hash")
                self.last_consolidation = decision
                return self._reinforce_duplicate(duplicate, record, decision)
            canonical = (self.store.find_by_canonical(canonical_key.strip(), project)
                         if canonical_key.strip() else None)
            decision = self.consolidator.assess(record, canonical=canonical)
            self.last_consolidation = decision
            if decision.kind.value == "update" and canonical is not None:
                record.metadata = self._with_evidence(canonical, record, decision)
                record.privacy = self._max_privacy(canonical.privacy, record.privacy)
                return self._update_record(canonical, record,
                                           vector=decision.incoming_vector)
            if decision.kind.value == "semantic_duplicate" and decision.candidate_id:
                existing = self.store.load(decision.candidate_id)
                if existing is not None:
                    return self._reinforce_duplicate(existing, record, decision)
            if decision.candidate_id:
                record.metadata = self._with_relation(record.metadata, decision)
            uncertain_conflict = (decision.kind.value == "uncertain" and
                                  decision.reason in (
                                      "conflicting_claim",
                                      "canonical_update_from_lower_trust"))
            if ((decision.kind.value == "contradiction" and
                 not decision.supersede_candidate) or uncertain_conflict):
                record.status = RecordStatus.DISPUTED
                record.canonical_key = ""
            saved = self.store.save(record)
            self._embed_best_effort(saved, decision.incoming_vector)
            self._audit("MEMORY_CREATED", {"id": saved.id, "type": memory_type.value})
            self._project_best_effort(saved)
            self._fts_sync_best_effort(saved)
            if decision.supersede_candidate and decision.candidate_id:
                self.update(decision.candidate_id, status=RecordStatus.SUPERSEDED)
            return saved

    def update(self, record_id: int, content: Optional[str] = None,
               title: Optional[str] = None, summary: Optional[str] = None,
               confidence: Optional[float] = None,
               status: Optional[RecordStatus] = None,
               metadata: Optional[Dict[str, Any]] = None) -> MemoryRecordV2:
        with self._lock:
            current = self.store.load(record_id)
            if not current:
                raise KeyError("memória %s inexistente" % record_id)
            if content is not None:
                current.content = content
                current.content_hash = content_hash(content)
            if title is not None:
                current.title = title
            if summary is not None:
                current.summary = summary
            if confidence is not None:
                current.confidence = confidence
            if status is not None:
                current.status = status
            if metadata is not None:
                current.metadata = dict(metadata)
            current.validate()
            updated = self.store.update(current)
            self._audit("MEMORY_UPDATED", {"id": updated.id, "version": updated.version})
            self._project_best_effort(updated)
            self._fts_sync_best_effort(updated)
            return updated

    def _update_record(self, existing: MemoryRecordV2, incoming: MemoryRecordV2,
                       vector=None) -> MemoryRecordV2:
        existing.content = incoming.content
        existing.title = incoming.title or existing.title
        existing.summary = incoming.summary or existing.summary
        existing.confidence = incoming.confidence
        existing.confidence_basis = incoming.confidence_basis
        existing.privacy = self._max_privacy(existing.privacy, incoming.privacy)
        existing.source_type = incoming.source_type
        existing.source_ref = incoming.source_ref
        existing.content_hash = incoming.content_hash
        existing.metadata = incoming.metadata
        existing.tags = incoming.tags or existing.tags
        existing.validate()
        updated = self.store.update(existing)
        self._embed_best_effort(updated, vector)
        self._audit("MEMORY_UPDATED", {"id": updated.id, "version": updated.version,
                                      "canonical_key": updated.canonical_key})
        self._project_best_effort(updated)
        self._fts_sync_best_effort(updated)
        return updated

    def _reinforce_duplicate(self, existing, incoming, decision):
        existing.metadata = self._with_evidence(existing, incoming, decision)
        existing.privacy = self._max_privacy(existing.privacy, incoming.privacy)
        existing.confidence = max(existing.confidence, incoming.confidence)
        updated = self.store.update(existing)
        self._audit("MEMORY_DEDUP", {"id": updated.id,
                                      "kind": decision.kind.value})
        self._project_best_effort(updated)
        self._fts_sync_best_effort(updated)
        return updated

    @staticmethod
    def _with_evidence(existing, incoming, decision):
        metadata = dict(existing.metadata or {})
        evidence = list(metadata.get("consolidation_evidence") or [])
        item = {"source_type": incoming.source_type.value,
                "source_ref": incoming.source_ref,
                "source_timestamp": incoming.source_timestamp,
                "confidence": incoming.confidence,
                "basis": incoming.confidence_basis.value,
                "kind": decision.kind.value}
        if item not in evidence:
            evidence.append(item)
        metadata["consolidation_evidence"] = evidence[-20:]
        return metadata

    @staticmethod
    def _with_relation(metadata, decision):
        value = dict(metadata or {})
        value["consolidation"] = {
            "kind": decision.kind.value, "related_memory_id": decision.candidate_id,
            "reason": decision.reason,
            "lexical_similarity": round(decision.lexical_similarity, 4),
            "vector_similarity": (round(decision.vector_similarity, 4)
                                  if decision.vector_similarity is not None else None)}
        return value

    @staticmethod
    def _max_privacy(left, right):
        from .graph import PRIVACY_RANK
        return max((left, right), key=lambda p: PRIVACY_RANK.get(p.value, 0))

    def archive(self, record_id: int) -> bool:
        with self._lock:
            ok = self.store.set_status(record_id, RecordStatus.ARCHIVED)
            if ok:
                self._audit("MEMORY_ARCHIVED", {"id": record_id})
                self._archive_projection_best_effort(int(record_id))
                self._fts_sync_best_effort(self.store.load(int(record_id)))
            return ok

    def list_versions(self, record_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            return self.store.versions(record_id)

    # ── entities / relations ─────────────────────────────────────

    def upsert_entity(self, canonical_name: str,
                      entity_type: EntityType = EntityType.OTHER,
                      aliases: Optional[List[str]] = None,
                      privacy: DataClassification = DataClassification.INTERNAL,
                      confidence: float = 0.5,
                      confidence_basis: ConfidenceBasis = ConfidenceBasis.INFERRED,
                      source_type: SourceType = SourceType.SYSTEM,
                      source_ref: str = "",
                      metadata: Optional[Dict[str, Any]] = None) -> EntityV2:
        with self._lock:
            entity = self.store.upsert_entity(EntityV2(
                entity_type=entity_type, canonical_name=canonical_name,
                aliases=list(aliases or []), privacy=privacy,
                confidence=confidence, confidence_basis=confidence_basis,
                source_type=source_type, source_ref=source_ref,
                metadata=dict(metadata or {})))
            self._audit("ENTITY_CREATED", {"id": entity.id, "name": entity.canonical_name})
            self._project_entity_best_effort(entity)
            return entity

    def update_entity(self, entity_id: int, canonical_name: Optional[str] = None,
                      aliases: Optional[List[str]] = None,
                      privacy: Optional[DataClassification] = None,
                      confidence: Optional[float] = None,
                      confidence_basis: Optional[ConfidenceBasis] = None,
                      source_ref: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None,
                      status: Optional[RecordStatus] = None) -> EntityV2:
        """Mudança material versionada (snapshot preservado)."""
        with self._lock:
            current = self.store.get_entity(int(entity_id))
            if current is None:
                raise KeyError("entidade %s inexistente" % entity_id)
            if canonical_name is not None:
                current.canonical_name = canonical_name
            if aliases is not None:
                current.aliases = list(aliases)
            if privacy is not None:
                current.privacy = privacy
            if confidence is not None:
                current.confidence = confidence
            if confidence_basis is not None:
                current.confidence_basis = confidence_basis
            if source_ref is not None:
                current.source_ref = source_ref
            if metadata is not None:
                current.metadata = dict(metadata)
            if status is not None:
                current.status = status
            updated = self.store.update_entity(current)
            self._audit("ENTITY_UPDATED",
                        {"id": updated.id, "version": updated.version})
            self._project_entity_best_effort(updated)
            return updated

    def archive_entity(self, entity_id: int) -> bool:
        """Archive (nunca delete físico) mesmo com relações ativas."""
        with self._lock:
            current = self.store.get_entity(int(entity_id))
            if current is None:
                return False
            current.status = RecordStatus.ARCHIVED
            self.store.update_entity(current)
            self._audit("ENTITY_ARCHIVED", {"id": entity_id})
            if self.vault is not None:
                try:
                    self.vault.archive_entity(int(entity_id))
                except Exception:
                    pass
            return True

    def merge_entities(self, source_id: int, target_id: int,
                       source_ref: str = "") -> Dict[str, Any]:
        """Merge explícito e transacional (sem merge automático)."""
        with self._lock:
            summary = self.store.merge_entities(int(source_id), int(target_id),
                                                source_ref=source_ref)
            self._audit("ENTITY_MERGED", {"source": summary.get("source_id"),
                                          "target": summary.get("target_id")})
            if self.vault is not None:
                try:
                    self.vault.delete_projection_if_safe(int(source_id),
                                                         kind="entity")
                except Exception:
                    pass
                try:
                    target = self.store.get_entity(int(target_id))
                    if target is not None:
                        self._project_entity_best_effort(target)
                except Exception:
                    pass
            return summary

    def link_entities(self, source_id: int, relation_type: RelationType, target_id: int,
                      confidence: float = 0.5,
                      confidence_basis: ConfidenceBasis = ConfidenceBasis.INFERRED,
                      privacy: DataClassification = DataClassification.INTERNAL,
                      source_type: SourceType = SourceType.SYSTEM,
                      source_ref: str = "",
                      metadata: Optional[Dict[str, Any]] = None) -> RelationV2:
        with self._lock:
            effective_privacy = self._relation_privacy(
                int(source_id), int(target_id), privacy)
            relation = self.store.link_entities(RelationV2(
                source_entity_id=source_id, relation_type=relation_type,
                target_entity_id=target_id, confidence=confidence,
                confidence_basis=confidence_basis, privacy=effective_privacy,
                source_type=source_type, source_ref=source_ref,
                metadata=dict(metadata or {})))
            self._audit("RELATION_CREATED", {"id": relation.id,
                                             "type": relation_type.value})
            # Wikilinks são representação: re-projeta os dois lados.
            for eid in (source_id, target_id):
                try:
                    entity = self.store.get_entity(eid)
                    if entity is not None:
                        self._project_entity_best_effort(entity)
                except Exception:
                    pass
            return relation

    def _relation_privacy(self, source_id: int, target_id: int,
                          requested: DataClassification) -> DataClassification:
        """Nunca menos restritiva que o elo mais sensível (só sobe)."""
        from .graph import PRIVACY_RANK
        levels = [requested.value]
        try:
            src = self.store.get_entity(int(source_id))
            dst = self.store.get_entity(int(target_id))
            if src is not None:
                levels.append(src.privacy.value)
            if dst is not None:
                levels.append(dst.privacy.value)
        except Exception:
            pass
        top = max(levels, key=lambda v: PRIVACY_RANK.get(v, 0))
        return DataClassification(top)

    def get_relation(self, relation_id: int,
                     clearance: str = "INTERNAL"):
        from .graph import privacy_allows
        with self._lock:
            rel = self.store.get_relation(int(relation_id))
            if rel is None:
                return None
            if not privacy_allows(clearance, rel.privacy.value):
                return None
            return self._to_edge(rel)

    def supersede_relation(self, relation_id: int,
                           source_ref: str = "",
                           note: str = "") -> RelationV2:
        """SUPERSEDED com snapshot (histórico preservado, nunca apagado)."""
        with self._lock:
            current = self.store.get_relation(int(relation_id))
            if current is None:
                raise KeyError("relação %s inexistente" % relation_id)
            current.status = RecordStatus.SUPERSEDED
            if source_ref:
                current.source_ref = source_ref
            if note:
                meta = dict(current.metadata or {})
                meta["supersede_note"] = str(note)[:500]
                current.metadata = meta
            updated = self.store.update_relation(current)
            self._audit("RELATION_SUPERSEDED", {"id": updated.id})
            for eid in (updated.source_entity_id, updated.target_entity_id):
                try:
                    entity = self.store.get_entity(eid)
                    if entity is not None:
                        self._project_entity_best_effort(entity)
                except Exception:
                    pass
            return updated

    def get_relations(self, entity_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            return self.store.get_relations(entity_id)

    # ── M1.2 graph query API (limitada, com privacy filter) ──────

    @staticmethod
    def _to_edge(rel: RelationV2):
        from .graph import GraphEdge, relation_direction, EdgeDirection
        return GraphEdge(
            relation_id=int(rel.id or 0),
            source_id=int(rel.source_entity_id),
            target_id=int(rel.target_entity_id),
            relation_type=rel.relation_type.value,
            directed=relation_direction(rel.relation_type.value)
            == EdgeDirection.DIRECTED,
            confidence=float(rel.confidence),
            status=rel.status.value, privacy=rel.privacy.value)

    def get_entity(self, entity_id: int, clearance: str = "INTERNAL"):
        from .graph import privacy_allows
        with self._lock:
            ent = self.store.get_entity(int(entity_id))
            if ent is None:
                return None
            if not privacy_allows(clearance, ent.privacy.value):
                return None
            return self.store._to_node(ent)

    def find_entity(self, name: str, entity_type: Optional[str] = None,
                    clearance: str = "INTERNAL"):
        """Atalho estrito: só retorna quando FOUND (nunca chuta)."""
        with self._lock:
            from .graph import ResolutionStatus
            resolution = self.store.resolve_entity(
                name, entity_type=entity_type, clearance=clearance)
            if resolution.status == ResolutionStatus.FOUND:
                return resolution.entity
            return None

    def resolve_entity(self, name: str, entity_type: Optional[str] = None,
                       clearance: str = "INTERNAL"):
        with self._lock:
            return self.store.resolve_entity(name, entity_type=entity_type,
                                             clearance=clearance)

    def list_entities(self, entity_type: Optional[str] = None,
                      status: str = "active", clearance: str = "INTERNAL",
                      limit: int = 100, offset: int = 0):
        with self._lock:
            return [self.store._to_node(e) for e in self.store.list_entities(
                entity_type=entity_type, status=status, clearance=clearance,
                limit=limit, offset=offset)]

    def neighbors(self, entity_id: int, relation_type: Optional[str] = None,
                  direction: str = "both", entity_type: Optional[str] = None,
                  clearance: str = "INTERNAL", limit: int = 50):
        from .graph import GraphNeighbor
        with self._lock:
            out = []
            for rel, other, side in self.store.neighbors(
                    int(entity_id), relation_type=relation_type,
                    direction=direction, entity_type=entity_type,
                    clearance=clearance, limit=limit):
                out.append(GraphNeighbor(edge=self._to_edge(rel),
                                         node=self.store._to_node(other),
                                         direction=side))
            return out

    def incoming_relations(self, entity_id: int, **kwargs):
        return self.neighbors(int(entity_id), direction="incoming", **kwargs)

    def outgoing_relations(self, entity_id: int, **kwargs):
        return self.neighbors(int(entity_id), direction="outgoing", **kwargs)

    def traverse(self, entity_id: int, max_depth: int = 2,
                 max_nodes: int = 50, clearance: str = "INTERNAL",
                 relation_type: Optional[str] = None):
        """BFS limitado (visited set; ciclos não travam, não são erro)."""
        from .graph import GraphResult
        with self._lock:
            root = self.get_entity(int(entity_id), clearance=clearance)
            result = GraphResult(root_id=int(entity_id),
                                 depth=int(max_depth))
            if root is None:
                return result
            result.nodes.append(root)
            visited = {int(entity_id)}
            frontier = [(int(entity_id), 0)]
            truncated = False
            while frontier:
                current, depth = frontier.pop(0)
                if depth >= int(max_depth):
                    continue
                for rel, other, _side in self.store.neighbors(
                        current, relation_type=relation_type,
                        clearance=clearance, limit=max_nodes):
                    result.edges.append(self._to_edge(rel))
                    oid = int(other.id or 0)
                    if oid not in visited:
                        visited.add(oid)
                        if len(visited) > int(max_nodes):
                            truncated = True
                            break
                        result.nodes.append(self.store._to_node(other))
                        frontier.append((oid, depth + 1))
                if truncated or len(visited) >= int(max_nodes):
                    truncated = truncated or len(visited) >= int(max_nodes)
                    break
            result.truncated = truncated
            return result

    def get_subgraph(self, entity_id: int, depth: int = 2,
                     max_nodes: int = 50, clearance: str = "INTERNAL",
                     relation_type: Optional[str] = None):
        """Base p/ GraphRAG futuro (entities + relations + root + depth)."""
        return self.traverse(int(entity_id), max_depth=int(depth),
                             max_nodes=int(max_nodes), clearance=clearance,
                             relation_type=relation_type)

    def shortest_path(self, source_id: int, target_id: int,
                      max_depth: int = 6, clearance: str = "INTERNAL",
                      relation_type: Optional[str] = None):
        """BFS p/ caminho curto (privacy filter em cada salto)."""
        from .graph import GraphPath
        with self._lock:
            source_id, target_id = int(source_id), int(target_id)
            if source_id == target_id:
                node = self.get_entity(source_id, clearance=clearance)
                return GraphPath(nodes=[node] if node else [], edges=[])
            visited = {source_id: None}
            edge_to: Dict[int, Any] = {}
            frontier = [(source_id, 0)]
            found = False
            while frontier:
                current, depth = frontier.pop(0)
                if depth >= int(max_depth):
                    continue
                for rel, other, _side in self.store.neighbors(
                        current, relation_type=relation_type,
                        clearance=clearance, limit=100):
                    oid = int(other.id or 0)
                    if oid not in visited:
                        visited[oid] = current
                        edge_to[oid] = rel
                        if oid == target_id:
                            found = True
                            frontier = []
                            break
                        frontier.append((oid, depth + 1))
            if not found:
                return None
            node_ids = [target_id]
            while node_ids[-1] != source_id:
                node_ids.append(visited[node_ids[-1]])
            node_ids.reverse()
            nodes = [self.store._to_node(self.store.get_entity(nid))
                     for nid in node_ids]
            edges = [self._to_edge(edge_to[nid]) for nid in node_ids[1:]]
            return GraphPath(nodes=nodes, edges=edges)

    # ── M1.2 memory↔entity / evidence ────────────────────────────

    def link_memory(self, memory_id: int, entity_id: int,
                    link_role: str = "related") -> Dict[str, Any]:
        with self._lock:
            result = self.store.link_memory_entity(int(memory_id), int(entity_id),
                                                   link_role=link_role)
            try:
                record = self.store.load(int(memory_id))
                if record is not None:
                    self._project_best_effort(record)
            except Exception:
                pass
            return result

    def unlink_memory(self, memory_id: int, entity_id: int,
                      link_role: str = "related") -> bool:
        with self._lock:
            return self.store.unlink_memory_entity(int(memory_id), int(entity_id),
                                                   link_role=link_role)

    def entities_for_memory(self, memory_id: int,
                            clearance: str = "INTERNAL"):
        with self._lock:
            return [self.store._to_node(e) for e in self.store.entities_for_memory(
                int(memory_id), clearance=clearance)]

    def memories_for_entity(self, entity_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            return self.store.memories_for_entity(int(entity_id))

    def add_relation_evidence(self, relation_id: int, memory_id: int,
                              note: str = "") -> Dict[str, Any]:
        with self._lock:
            return self.store.add_evidence(int(relation_id), int(memory_id),
                                           note=note)

    def relation_evidence(self, relation_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            return self.store.evidences_for_relation(int(relation_id))

    # ── M1.2 stats / integrity ───────────────────────────────────

    def graph_stats(self) -> Dict[str, Any]:
        with self._lock:
            try:
                counts = self.store.graph_counts()
            except Exception:
                counts = {"entities_total": 0, "relations_total": 0}
            return counts

    def validate_graph(self) -> Dict[str, Any]:
        with self._lock:
            report = self.store.validate_graph()
            if not report.get("ok"):
                try:
                    self._audit("GRAPH_VALIDATION_FAILED",
                                {"issues": report.get("issue_count", 0)})
                except Exception:
                    pass
            return report

    # ── read ─────────────────────────────────────────────────────

    def get(self, record_id: int) -> Optional[MemoryRecordV2]:
        with self._lock:
            return self.store.load(record_id)

    def search(self, query: str, limit: int = 20,
               memory_type: Optional[MemoryKind] = None) -> List[MemorySearchResult]:
        """Lexical agora; vetor quando houver embeddings (contrato híbrido)."""
        with self._lock:
            records = self.store.lexical_search(
                query, limit, memory_type.value if memory_type else None)
            results = [MemorySearchResult(
                memory_id=r.id or 0, score=0.0, source=MatchSource.LEXICAL,
                match_type="lexical", snippet=(r.content[:200]),
                metadata={"type": r.memory_type.value}) for r in records]
            vector = self._try_vector(query)
            if vector:
                for memory_id, sim in self.store.vector_search(vector, limit):
                    if all(r.memory_id != memory_id for r in results):
                        record = self.store.load(memory_id)
                        if record:
                            results.append(MemorySearchResult(
                                memory_id=memory_id, score=round(sim, 4),
                                source=MatchSource.VECTOR, match_type="vector",
                                snippet=record.content[:200],
                                metadata={"type": record.memory_type.value}))
            return results[:limit]

    def recall(self, query: str, limit: int = 8) -> List[MemoryRecordV2]:
        with self._lock:
            return self.store.lexical_search(query, limit)

    # ── internos ─────────────────────────────────────────────────

    def _embed_best_effort(self, record: MemoryRecordV2, vector=None) -> None:
        if not self._embed or not record.id:
            return
        try:
            vector = vector if vector is not None else self._embed(record.content)
        except Exception:
            vector = None
        try:
            if vector:
                self.store.save_embedding(record.id, list(vector),
                                          self._embedding_model or "unknown")
                record.embedding_status = "ok"
                record.embedding_model = self._embedding_model or "unknown"
            else:
                self._mark_embedding_pending(record.id)
                record.embedding_status = "pending"
        except Exception:
            record.embedding_status = "degraded"

    def _mark_embedding_pending(self, record_id: int) -> None:
        from .migrations import v2_connect
        try:
            with v2_connect(self.db_path) as conn:
                conn.execute("UPDATE v2_memories SET embedding_status='pending' WHERE id=?",
                             (record_id,))
        except Exception:
            pass

    def _try_vector(self, query: str) -> Optional[List[float]]:
        if not self._embed:
            return None
        try:
            vector = self._embed(str(query or ""))
            return list(vector) if vector else None
        except Exception:
            return None

    # ── status ───────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        with self._lock:
            try:
                schema = v2_schema_version(self.db_path)
                pending = v2_pending_embeddings(self.db_path)
                state = "READY" if schema >= V2_SCHEMA_VERSION else "DEGRADED"
                return {"engine": "V2 %s" % state, "schema_version": schema,
                        "pending_embeddings": pending, "db": str(self.db_path)}
            except Exception as exc:
                return {"engine": "V2 DEGRADED", "error": str(exc)[:160]}

    # ── M1.3 hybrid retrieval (zero LLM; search() legado intacto) ─

    def _fts_sync_best_effort(self, record) -> bool:
        """Índice derivado pós-commit. Falha → degraded, memória válida."""
        try:
            from .hybrid import fts_index_record, fts_remove_record
            if record is None:
                return False
            if record.status == RecordStatus.DELETED_LOGICAL:
                return bool(fts_remove_record(self.db_path, int(record.id or 0)))
            return bool(fts_index_record(
                self.db_path, int(record.id or 0), record.title,
                record.content, record.summary, list(record.tags or []),
                record.project))
        except Exception:
            return False

    def _retriever(self, force_no_fts: bool = False):
        from .hybrid import HybridMemoryRetriever
        return HybridMemoryRetriever(
            self.db_path, self.store, embed=self._embed,
            force_no_fts=force_no_fts)

    def hybrid_search(self, query: str, limit: int = 8, **kwargs):
        """Interface oficial híbrida (nova; search() legado preservado)."""
        with self._lock:
            return self._retriever(
                force_no_fts=bool(kwargs.pop("force_no_fts", False))).search(
                    query, limit=limit, **kwargs)

    def hybrid_context(self, query: str, max_items: int = 8,
                       max_chars: int = 2800, **kwargs) -> str:
        """Blocos [MEMORY_CONTEXT] DATA p/ Brain (budget aplicado)."""
        from .hybrid import build_context
        with self._lock:
            report = self.hybrid_search(query, limit=max_items, **kwargs)
            return build_context(report.results, max_items=max_items,
                                 max_chars=max_chars)

    def rebuild_fts(self, dry_run: bool = False) -> Dict[str, Any]:
        """Reconstrói índice derivado (nunca toca canônico)."""
        from .hybrid import ensure_fts, fts_available, rebuild_fts
        with self._lock:
            if dry_run:
                report = self.validate_retrieval_indexes()
                return {"dry_run": True,
                        "would_index": len(report.get("missing_fts", [])),
                        "would_remove_orphans": len(report.get("orphan_fts", [])),
                        "status": report.get("fts_status", "unknown")}
            if not fts_available():
                ensure_fts(self.db_path)
            result = rebuild_fts(self.db_path, self._all_memories_indexable)
            try:
                self._audit("FTS_REBUILT", {"indexed": result.get("indexed", 0)})
            except Exception:
                pass
            return result

    def _all_memories_indexable(self):
        return [r for r in self._all_memories()
                if r.status != RecordStatus.DELETED_LOGICAL]

    def validate_retrieval_indexes(self) -> Dict[str, Any]:
        """Consistência dos derivados (FTS/embeddings/links)."""
        from .hybrid import ensure_fts, fts_available
        with self._lock:
            report: Dict[str, Any] = {"fts_status": "FTS5_UNAVAILABLE",
                                      "missing_fts": [], "orphan_fts": [],
                                      "content_mismatch": [],
                                      "embeddings_pending": 0,
                                      "embeddings_missing": 0,
                                      "dangling_memory_links": []}
            try:
                report["embeddings_pending"] = v2_pending_embeddings(self.db_path)
            except Exception:
                pass
            if not fts_available(self.db_path):
                ensure_fts(self.db_path)
            if not fts_available(self.db_path):
                try:
                    report["embeddings_missing"] = self._embeddings_missing()
                    report["dangling_memory_links"] = self._dangling_links()
                except Exception:
                    pass
                return report
            report["fts_status"] = "FTS5_AVAILABLE"
            try:
                from .migrations import v2_connect
                canonical = {r.id: r for r in self._all_memories_indexable()}
                with v2_connect(self.db_path) as conn:
                    fts_rows = {row[0]: row[1] for row in conn.execute(
                        "SELECT rowid, content FROM v2_memories_fts").fetchall()}
                report["missing_fts"] = sorted(
                    mid for mid in canonical if mid not in fts_rows)
                report["orphan_fts"] = sorted(
                    rid for rid in fts_rows if rid not in canonical)
                for mid, text in fts_rows.items():
                    record = canonical.get(mid)
                    if record is not None and (text or "") != (record.content or ""):
                        report["content_mismatch"].append(mid)
                report["embeddings_missing"] = self._embeddings_missing()
                report["dangling_memory_links"] = self._dangling_links()
            except Exception as exc:
                report["fts_status"] = "FTS5_DEGRADED"
                report["error"] = str(exc)[:160]
            return report

    def _embeddings_missing(self) -> int:
        try:
            from .migrations import v2_connect
            with v2_connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM v2_memories m LEFT JOIN v2_embeddings e"
                    " ON e.memory_id=m.id WHERE m.status='active'"
                    " AND m.embedding_status='ok' AND e.memory_id IS NULL").fetchone()
                return int(row[0]) if row else 0
        except Exception:
            return 0

    def _dangling_links(self) -> List[Dict[str, Any]]:
        try:
            from .migrations import v2_connect
            with v2_connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT l.memory_id, l.entity_id FROM v2_memory_entities l"
                    " LEFT JOIN v2_memories m ON m.id=l.memory_id"
                    " LEFT JOIN v2_entities e ON e.id=l.entity_id"
                    " WHERE l.status='active' AND (m.id IS NULL OR e.id IS NULL)"
                ).fetchall()
                return [{"memory_id": r[0], "entity_id": r[1]} for r in rows]
        except Exception:
            return []

    def repair_indexes(self) -> Dict[str, Any]:
        """Somente derivados (FTS rebuild + remove órfãos)."""
        from .hybrid import fts_remove_record
        with self._lock:
            report = self.validate_retrieval_indexes()
            removed = 0
            for rid in report.get("orphan_fts", []):
                if fts_remove_record(self.db_path, int(rid)):
                    removed += 1
            rebuilt = self.rebuild_fts()
            return {"orphans_removed": removed, "rebuild": rebuilt,
                    "dangling_memory_links": report.get("dangling_memory_links", [])}

    def retrieval_status(self) -> Dict[str, Any]:
        """Telemetria DEV (sem conteúdo)."""
        from .hybrid import fts_available, hybrid_mode
        with self._lock:
            try:
                counts = self.store.graph_counts()
            except Exception:
                counts = {}
            report = self.validate_retrieval_indexes()
            return {"mode": hybrid_mode(),
                    "fts": report.get("fts_status", "unknown"),
                    "memories_indexable": len(self._all_memories_indexable()),
                    "fts_missing": len(report.get("missing_fts", [])),
                    "fts_orphans": len(report.get("orphan_fts", [])),
                    "embeddings_pending": report.get("embeddings_pending", 0),
                    "graph": {"entities": counts.get("entities_total", 0),
                              "relations": counts.get("relations_total", 0)}}

    # ── M1.1 vault projection (single-writer: só o engine projeta) ──

    def _project_best_effort(self, record: MemoryRecordV2) -> Dict[str, Any]:
        """Pós-commit SQLite → Markdown. Nunca desfaz memória válida."""
        with self._lock:
            if self.vault is None:
                if self._vault_error:
                    self._mark_projection_pending(record, "vault-unavailable")
                return {"sync_status": "pending", "detail": "vault-disabled"}
            try:
                related = self._linked_entity_names(int(record.id or 0))
                return self.vault.project_record(record, related=related,
                                                 degraded=False)
            except MemorySecurityError as exc:
                try:
                    from .migrations import v2_set_projection
                    v2_set_projection(self.db_path, int(record.id or 0),
                                      "memory", "", "",
                                      int(record.version or 0),
                                      "error", "security-block: %s" % str(exc)[:160])
                except Exception:
                    pass
                return {"sync_status": "error", "detail": "security-block"}
            except Exception as exc:
                return self._mark_projection_pending(
                    record, "%s: %s" % (type(exc).__name__, str(exc)[:200]))

    def _mark_projection_pending(self, record: MemoryRecordV2,
                                 detail: str) -> Dict[str, Any]:
        try:
            from .migrations import v2_set_projection
            v2_set_projection(self.db_path, int(record.id or 0), "memory",
                              "", "", int(record.version or 0),
                              "pending", detail)
        except Exception:
            pass
        try:
            self._audit("MEMORY_PROJECTION_PENDING",
                        {"id": record.id, "detail": detail[:160]})
        except Exception:
            pass
        return {"sync_status": "pending", "detail": detail}

    def _archive_projection_best_effort(self, record_id: int) -> bool:
        with self._lock:
            if self.vault is None:
                return False
            try:
                return bool(self.vault.archive_record(int(record_id)))
            except Exception:
                return False

    def _linked_entity_names(self, memory_id: int) -> List[str]:
        """Entidades vinculadas (tabela canônica) p/ Related da nota."""
        try:
            return [e.canonical_name for e in self.store.entities_for_memory(
                int(memory_id)) if str(e.canonical_name or "").strip()]
        except Exception:
            return []

    def _labeled_relations(self, entity_id: int) -> List[tuple]:
        """[(label, nome)] com tipo e inversa derivada; só elos projetáveis
        (PUBLIC/INTERNAL, ativos) p/ não criar wikilink pendente."""
        from .graph import (EdgeDirection, inverse_label, relation_direction)
        labeled: List[tuple] = []
        try:
            for rel, other, side in self.store.neighbors(
                    int(entity_id), clearance="INTERNAL", limit=100):
                if other.privacy.value not in ("PUBLIC", "INTERNAL"):
                    continue
                name = str(other.canonical_name or "").strip()
                if not name:
                    continue
                rtype = rel.relation_type.value
                if relation_direction(rtype) == EdgeDirection.SYMMETRIC:
                    label = rtype
                elif side == "outgoing":
                    label = rtype
                else:
                    label = inverse_label(rtype) or rtype
                labeled.append((label, name))
        except Exception:
            pass
        return labeled

    def _linked_memory_titles(self, entity_id: int) -> List[str]:
        titles: List[str] = []
        try:
            for link in self.store.memories_for_entity(int(entity_id)):
                record = self.store.load(int(link["memory_id"]))
                if record is not None and str(record.status.value) != "deleted_logical":
                    title = str(record.title or "").strip() or (
                        "Memória mem_%d" % int(link["memory_id"]))
                    titles.append(title)
        except Exception:
            pass
        return titles

    def _project_entity_best_effort(self, entity: EntityV2) -> Dict[str, Any]:
        with self._lock:
            if self.vault is None:
                return {"sync_status": "pending", "detail": "vault-disabled"}
            try:
                privacy = str(getattr(getattr(entity, "privacy", ""), "value",
                                      getattr(entity, "privacy", "")) or "").upper()
                if privacy in ("SECRET", "SENSITIVE"):
                    from .migrations import v2_set_projection
                    v2_set_projection(self.db_path, int(entity.id or 0),
                                      "entity", "", "",
                                      int(getattr(entity, "version", 1) or 1),
                                      "ignored",
                                      "%s-no-projection" % privacy.lower())
                    return {"sync_status": "ignored",
                            "detail": "%s-no-projection" % privacy.lower()}
                return self.vault.project_entity(
                    entity,
                    related=self._labeled_relations(int(entity.id or 0)),
                    memories=self._linked_memory_titles(int(entity.id or 0)),
                    degraded=False)
            except Exception as exc:
                try:
                    from .migrations import v2_set_projection
                    v2_set_projection(self.db_path, int(entity.id or 0),
                                      "entity", "", "",
                                      int(getattr(entity, "version", 1) or 1),
                                      "error",
                                      "%s: %s" % (type(exc).__name__,
                                                  str(exc)[:200]))
                except Exception:
                    pass
                return {"sync_status": "error", "detail": str(exc)[:200]}

    def check_drift(self, record_id: int, kind: str = "memory") -> Dict[str, Any]:
        """Auditoria de divergência SQLite vs Markdown (não importa nada)."""
        with self._lock:
            if self.vault is None:
                return {"sync_status": "pending", "detail": "vault-disabled"}
            if kind == "entity":
                entity = self.store.get_entity(int(record_id))
                if entity is None:
                    raise KeyError("entidade %s inexistente" % record_id)
                return self.vault.check_drift(entity, kind="entity")
            record = self.store.load(int(record_id))
            if record is None:
                raise KeyError("memória %s inexistente" % record_id)
            return self.vault.check_drift(record)

    def project_legacy(self, record: MemoryRecordV2) -> Dict[str, Any]:
        """Projeção de leitura legada (adapter) sem tocar registros legados."""
        with self._lock:
            if self.vault is None:
                return {"sync_status": "pending", "detail": "vault-disabled"}
            try:
                return self.vault.project_record(record, degraded=False)
            except Exception as exc:
                return {"sync_status": "error",
                        "detail": "%s: %s" % (type(exc).__name__,
                                              str(exc)[:200])}

    def vault_status(self) -> Dict[str, Any]:
        with self._lock:
            from .migrations import v2_list_projections
            counts: Dict[str, int] = {}
            try:
                for row in v2_list_projections(self.db_path):
                    key = str(row.get("sync_status", "unknown"))
                    counts[key] = counts.get(key, 0) + 1
            except Exception:
                pass
            return {"enabled": self.vault is not None,
                    "vault_root": str(self.vault_root) if self.vault_root else "",
                    "error": self._vault_error,
                    "sync_counts": counts,
                    "managed_notes": (len(self.vault.list_records("memory"))
                                      + len(self.vault.list_records("entity"))
                                      if self.vault is not None else 0)}

    def rebuild_vault(self, dry_run: bool = False) -> Dict[str, Any]:
        """SQLite → Markdown. Seguro: só toca arquivos gerenciados
        (managed_by + ID conhecido); humanas nunca apagadas/movidas.
        Com dry_run=True nada é alterado."""
        from . import vault as _vault
        from .migrations import v2_get_projection, v2_set_projection
        with self._lock:
            report: Dict[str, Any] = {"would_create": [], "would_update": [],
                                      "would_archive": [], "would_conflict": [],
                                      "projected": 0, "skipped": 0, "dry_run": bool(dry_run)}
            if self.vault is None:
                report["error"] = self._vault_error or "vault-disabled"
                return report
            _vault.ensure_vault(self.vault_root)
            memories = self._all_memories()
            for record in memories:
                ok, reason = _vault.export_decision(record)
                if not ok:
                    if not dry_run:
                        v2_set_projection(self.db_path, int(record.id or 0),
                                          "memory", "", "",
                                          int(record.version or 0),
                                          "ignored", reason)
                    else:
                        report["skipped"] += 1
                    continue
                if record.status == RecordStatus.DELETED_LOGICAL:
                    if dry_run:
                        report["would_archive"].append(int(record.id or 0))
                    elif self.vault.delete_projection_if_safe(int(record.id or 0)):
                        report["projected"] += 1
                    continue
                state = v2_get_projection(self.db_path, int(record.id or 0),
                                          "memory")
                drift = (self.vault.check_drift(record)
                         if state is not None else {"sync_status": "pending"})
                bucket = {"pending": "would_create",
                          "drift": "would_conflict",
                          "conflict": "would_conflict",
                          "error": "would_update"}.get(
                              str(drift.get("sync_status", "pending")),
                              "would_update")
                if record.status == RecordStatus.ARCHIVED:
                    bucket = "would_archive"
                if dry_run:
                    report[bucket].append(int(record.id or 0))
                    continue
                if record.status == RecordStatus.ARCHIVED:
                    self.vault.project_record(record)
                    self.vault.archive_record(int(record.id or 0))
                else:
                    self.vault.project_record(record)
                report["projected"] += 1
            for entity in self._all_entities():
                if dry_run:
                    continue
                self._project_entity_best_effort(entity)
                report["projected"] += 1
            if not dry_run:
                self._write_index_note()
            return report

    def _all_memories(self) -> List[MemoryRecordV2]:
        from .migrations import v2_connect
        out: List[MemoryRecordV2] = []
        try:
            with v2_connect(self.db_path) as conn:
                cols = [d[0] for d in conn.execute(
                    "SELECT * FROM v2_memories LIMIT 0").description]
                for row in conn.execute(
                        "SELECT * FROM v2_memories ORDER BY id").fetchall():
                    try:
                        out.append(self.store._row_to_record(dict(zip(cols, row))))
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    def _all_entities(self) -> List[EntityV2]:
        from .migrations import v2_connect
        from .record import EntityV2 as _E
        out: List[EntityV2] = []
        try:
            with v2_connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT id FROM v2_entities WHERE status='active'"
                    " ORDER BY id").fetchall()
                for (eid,) in rows:
                    try:
                        ent = self.store.get_entity(int(eid))
                        if ent is not None:
                            out.append(ent)
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    def _write_index_note(self) -> None:
        from . import vault as _vault
        from .migrations import v2_list_projections
        counts: Dict[str, int] = {}
        try:
            for row in v2_list_projections(self.db_path):
                key = str(row.get("sync_status", "unknown"))
                counts[key] = counts.get(key, 0) + 1
        except Exception:
            pass
        stats = {"last_sync": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "managed_notes": (len(self.vault.list_records("memory"))
                                   + len(self.vault.list_records("entity"))),
                 "drift": counts.get("drift", 0) + counts.get("conflict", 0),
                 "pending": counts.get("pending", 0),
                 "errors": counts.get("error", 0)}
        try:
            _vault.atomic_write(self.vault_root / _vault.INDEX_NOTE_PATH,
                                _vault.render_index_note(stats))
        except Exception:
            pass
        try:
            grouped: Dict[str, List[str]] = {}
            for ent in self.store.list_entities(status="active",
                                                clearance="INTERNAL",
                                                limit=5000):
                if ent.privacy.value not in ("PUBLIC", "INTERNAL"):
                    continue
                grouped.setdefault(ent.entity_type.value, []).append(
                    ent.canonical_name)
            _vault.atomic_write(self.vault_root / _vault.ENTITY_INDEX_PATH,
                                _vault.render_entity_index(grouped))
        except Exception:
            pass
