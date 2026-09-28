"""M1.7 — Project Memory / Long-Term Memory.

Wraps GoldenMemoryEngine to provide project-scoped memory management.
Reuses: EntityType.PROJECT, project field, entity graph, hybrid retrieval.

Does NOT create parallel DB. Does NOT make Markdown canonical.
Does NOT save everything indiscriminately.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    ConfidenceBasis,
    EntityType,
    MemoryKind,
    RecordStatus,
    RelationType,
    SourceType,
)
from ...orchestrator.models import DataClassification


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Freshness(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class CandidateVerdict(str, Enum):
    PROMOTE = "promote"
    REJECT = "reject"
    DEFER = "defer"


class Provenance(str, Enum):
    KNOWN = "known"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class Scope(str, Enum):
    PROJECT = "project"
    GLOBAL = "global"


# ── Token budget constants ──

PROJECT_STATE_MAX_CHARS = 1200
MEMORY_RETRIEVAL_MAX_ITEMS = 8
HANDOFF_MAX_CHARS = 800
DECISIONS_MAX_ITEMS = 5
IMPORTANT_FILES_MAX = 10


# ── Data classes ──


@dataclass
class ProjectRecord:
    entity_id: int = 0
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    root_path: str = ""
    status: str = "active"
    current_phase: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectState:
    project: str = ""
    status: str = "unknown"
    current_phase: str = ""
    last_completed: str = ""
    current_work: str = ""
    next_step: str = ""
    blockers: List[str] = field(default_factory=list)
    important_files: List[str] = field(default_factory=list)
    known_issues: List[str] = field(default_factory=list)
    last_handoff: str = ""
    freshness: str = "UNKNOWN"
    updated_at: float = 0.0
    source: str = "unknown"

    def to_compact(self) -> str:
        lines = [
            f"PROJECT: {self.project}",
            f"STATUS: {self.status}",
            f"CURRENT_PHASE: {self.current_phase}",
            f"LAST_COMPLETED: {self.last_completed}",
            f"CURRENT_WORK: {self.current_work}",
            f"NEXT_STEP: {self.next_step}",
        ]
        if self.blockers:
            lines.append(f"BLOCKERS: {'; '.join(self.blockers[:3])}")
        if self.important_files:
            lines.append(f"FILES: {', '.join(self.important_files[:5])}")
        if self.known_issues:
            lines.append(f"ISSUES: {'; '.join(self.known_issues[:3])}")
        if self.last_handoff:
            lines.append(f"HANDOFF: {self.last_handoff[:200]}")
        lines.append(f"FRESHNESS: {self.freshness}")
        text = "\n".join(lines)
        return text[:PROJECT_STATE_MAX_CHARS]


@dataclass
class MemoryCandidate:
    content: str = ""
    title: str = ""
    summary: str = ""
    memory_type: str = "semantic"
    confidence: float = 0.5
    confidence_basis: str = "inferred"
    source_type: str = "system"
    source_ref: str = ""
    project: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    verdict: str = "defer"
    reason: str = ""


@dataclass
class ProjectContext:
    project: str = ""
    state: Optional[ProjectState] = None
    relevant_memories: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    known_issues: List[str] = field(default_factory=list)
    next_step: str = ""
    important_files: List[str] = field(default_factory=list)
    handoff: str = ""
    token_estimate: int = 0


@dataclass
class HandoffData:
    project: str = ""
    status: str = ""
    done: str = ""
    current: str = ""
    next_step: str = ""
    blockers: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    known_issues: List[str] = field(default_factory=list)
    generated_at: float = 0.0

    def to_compact(self) -> str:
        lines = [
            f"PROJECT: {self.project}",
            f"STATUS: {self.status}",
            f"DONE: {self.done}",
            f"CURRENT: {self.current}",
            f"NEXT: {self.next_step}",
        ]
        if self.blockers:
            lines.append(f"BLOCKERS: {'; '.join(self.blockers[:3])}")
        if self.files:
            lines.append(f"FILES: {', '.join(self.files[:5])}")
        if self.decisions:
            lines.append(f"DECISIONS: {'; '.join(self.decisions[:3])}")
        if self.known_issues:
            lines.append(f"ISSUES: {'; '.join(self.known_issues[:3])}")
        text = "\n".join(lines)
        return text[:HANDOFF_MAX_CHARS]


# ── Canonical key helpers ──

def _project_canonical_key(project: str, kind: str, detail: str = "") -> str:
    base = f"project:{project.lower().strip()}:{kind}"
    if detail:
        base += f":{detail.lower().strip()}"
    return base


def _decision_key(project: str, decision: str) -> str:
    return _project_canonical_key(project, "decision", decision)


def _issue_key(project: str, issue: str) -> str:
    return _project_canonical_key(project, "issue", issue)


def _lesson_key(project: str, lesson: str) -> str:
    return _project_canonical_key(project, "lesson", lesson)


def _handoff_key(project: str) -> str:
    return _project_canonical_key(project, "handoff", "latest")


def _state_key(project: str) -> str:
    return _project_canonical_key(project, "state", "current")


# ── Project Resolver ──


class ProjectResolver:
    """Resolve project name/alias to entity via GoldenMemoryEngine graph."""

    def __init__(self, engine):
        self._engine = engine

    def resolve(self, name: str) -> Optional[ProjectRecord]:
        if not name or not name.strip():
            return None
        res = self._engine.resolve_entity(
            name.strip(), EntityType.PROJECT, clearance="INTERNAL"
        )
        if res.status.value == "found" and res.entity:
            entity_id = res.entity.entity_id
            full_entity = self._engine.store.get_entity(entity_id)
            if full_entity:
                return self._entity_to_record(full_entity)
            return self._entity_to_record(res.entity)
        return None

    def resolve_or_create(self, name: str, aliases: Optional[List[str]] = None,
                          root_path: str = "") -> ProjectRecord:
        existing = self.resolve(name)
        if existing:
            if aliases:
                new_aliases = list(set(existing.aliases + aliases))
                if new_aliases != existing.aliases:
                    self._engine.update_entity(
                        existing.entity_id, canonical_name=existing.name,
                        aliases=new_aliases
                    )
                    existing.aliases = new_aliases
            return existing
        all_aliases = list(set(aliases or []))
        entity = self._engine.upsert_entity(
            canonical_name=name,
            entity_type=EntityType.PROJECT,
            aliases=all_aliases,
            privacy=DataClassification.INTERNAL,
            confidence=1.0,
            confidence_basis=ConfidenceBasis.USER_CONFIRMED,
            source_type=SourceType.USER_EXPLICIT,
            metadata={"root_path": root_path, "status": "active"},
        )
        return ProjectRecord(
            entity_id=entity.id or 0,
            name=name,
            aliases=all_aliases,
            root_path=root_path,
            status="active",
            created_at=entity.created_at or time.time(),
            updated_at=time.time(),
        )

    def list_projects(self) -> List[ProjectRecord]:
        entities = self._engine.list_entities(
            entity_type=EntityType.PROJECT, clearance="INTERNAL", limit=50
        )
        return [self._entity_to_record(e) for e in entities]

    def _entity_to_record(self, entity: Any) -> ProjectRecord:
        meta = {}
        if hasattr(entity, "metadata") and entity.metadata:
            if isinstance(entity.metadata, str):
                try:
                    meta = json.loads(entity.metadata)
                except Exception:
                    meta = {}
            elif isinstance(entity.metadata, dict):
                meta = entity.metadata
        eid = getattr(entity, "id", None) or getattr(entity, "entity_id", 0) or 0
        return ProjectRecord(
            entity_id=int(eid),
            name=getattr(entity, "canonical_name", ""),
            aliases=getattr(entity, "aliases", []) or [],
            root_path=meta.get("root_path", ""),
            status=meta.get("status", "active"),
            current_phase=meta.get("current_phase", ""),
            created_at=getattr(entity, "created_at", 0) or 0,
            updated_at=getattr(entity, "updated_at", 0) or 0,
            metadata=meta,
        )


# ── Memory Candidate Detector ──

_DECISION_SIGNALS = [
    "decidimos", "decidiu", "decisão", "decisao", "vamos usar",
    "optamos", "escolhemos", "a opção", "a alternativa", "definimos",
    "decided", "we decided", "we will use", "the decision",
]

_LESSON_SIGNALS = [
    "não faça", "nunca", "cuidado", "erro", "bug", "problema",
    "solução", "resolveu", "funcionou", "lição", "aprendizado",
    "dont", "never", "careful", "error", "bug", "lesson",
    "learned", "solution", "fixed",
]

_PROCEDURE_SIGNALS = [
    "sempre", "procedimento", "fluxo", "passo a passo", "workflow",
    "always", "procedure", "workflow", "step by step",
]

_STATUS_SIGNALS = [
    "concluído", "completo", "pronto", "feito", "iniciando",
    "em andamento", "parado", "bloqueado", "pendente",
    "done", "complete", "finished", "starting", "blocked",
]

_IMPORTANT_FILE_SIGNALS = [
    ".py", ".mq5", ".mqh", ".html", ".js", "importante",
    "principal", "core", "engine", "config",
]


class MemoryCandidateDetector:
    """Detect if conversation content should be promoted to long-term memory."""

    def __init__(self):
        self._signals = {
            "decision": _DECISION_SIGNALS,
            "lesson": _LESSON_SIGNALS,
            "procedure": _PROCEDURE_SIGNALS,
            "status": _STATUS_SIGNALS,
        }

    def detect(self, content: str, project: str = "",
               title: str = "", tags: Optional[List[str]] = None) -> List[MemoryCandidate]:
        if not content or len(content.strip()) < 20:
            return []

        content_lower = content.lower()
        candidates = []

        for kind, signals in self._signals.items():
            score = sum(1 for s in signals if s in content_lower)
            if score >= 1:
                verdict = self._classify(kind, score, content_lower)
                candidates.append(MemoryCandidate(
                    content=content[:2000],
                    title=title or self._auto_title(content, kind),
                    summary=content[:500],
                    memory_type=self._kind_to_memory_type(kind),
                    confidence=min(0.3 + score * 0.15, 0.9),
                    confidence_basis="inferred",
                    source_type="conversation",
                    project=project,
                    tags=tags or [],
                    verdict=verdict,
                    reason=f"detected {kind} signals (score={score})",
                ))

        if not candidates:
            candidates.append(MemoryCandidate(
                content=content[:2000],
                title=title or self._auto_title(content, "general"),
                summary=content[:500],
                memory_type="semantic",
                confidence=0.3,
                confidence_basis="tentative",
                source_type="conversation",
                project=project,
                tags=tags or [],
                verdict="reject",
                reason="no persistent signals detected",
            ))
        return candidates

    def _classify(self, kind: str, score: int, content_lower: str) -> str:
        if kind == "decision" and score >= 2:
            return "promote"
        if kind == "lesson" and score >= 1:
            negative = any(w in content_lower for w in ["não", "nunca", "dont", "never", "error", "bug"])
            return "promote" if negative else "defer"
        if kind == "status" and score >= 2:
            return "defer"
        if kind == "procedure" and score >= 2:
            return "defer"
        return "reject"

    def _kind_to_memory_type(self, kind: str) -> str:
        mapping = {
            "decision": "decision",
            "lesson": "lesson",
            "procedure": "procedural",
            "status": "semantic",
        }
        return mapping.get(kind, "semantic")

    def _auto_title(self, content: str, kind: str) -> str:
        first_line = content.split("\n")[0][:100].strip()
        prefix = {"decision": "Decision", "lesson": "Lesson", "procedure": "Procedure", "status": "Status"}.get(kind, "Note")
        return f"{prefix}: {first_line}"


# ── Session → Long-Term Extractor ──


class SessionLongTermExtractor:
    """Extract persistent facts from session work for Project Memory."""

    def __init__(self, engine, resolver: ProjectResolver):
        self._engine = engine
        self._resolver = resolver

    def extract_task_completed(self, project: str, task: str,
                                details: str = "") -> Optional[Any]:
        rec = self._resolver.resolve(project)
        if not rec:
            return None
        return self._engine.remember(
            content=f"Task completed: {task}. {details}".strip(),
            memory_type=MemoryKind.SEMANTIC,
            title=f"Task completed: {task[:80]}",
            summary=f"Completed task in {project}: {task[:200]}",
            confidence=0.9,
            confidence_basis=ConfidenceBasis.USER_CONFIRMED,
            source_type=SourceType.CONVERSATION,
            project=project,
            tags=["task-completed", "status-update"],
            canonical_key=_project_canonical_key(project, "task", task[:100]),
        )

    def extract_decision(self, project: str, decision: str,
                          rationale: str = "") -> Optional[Any]:
        rec = self._resolver.resolve(project)
        if not rec:
            return None
        content = f"Decision: {decision}"
        if rationale:
            content += f". Rationale: {rationale}"
        return self._engine.remember(
            content=content,
            memory_type=MemoryKind.DECISION,
            title=f"Decision: {decision[:80]}",
            summary=f"Decision in {project}: {decision[:200]}",
            confidence=0.85,
            confidence_basis=ConfidenceBasis.USER_CONFIRMED,
            source_type=SourceType.CONVERSATION,
            project=project,
            tags=["decision"],
            canonical_key=_decision_key(project, decision[:100]),
        )

    def extract_bug(self, project: str, bug: str,
                     resolution: str = "") -> Optional[Any]:
        rec = self._resolver.resolve(project)
        if not rec:
            return None
        content = f"Known issue: {bug}"
        if resolution:
            content += f". Resolution: {resolution}"
        return self._engine.remember(
            content=content,
            memory_type=MemoryKind.LESSON,
            title=f"Issue: {bug[:80]}",
            summary=f"Known issue in {project}: {bug[:200]}",
            confidence=0.8,
            confidence_basis=ConfidenceBasis.DOCUMENTED,
            source_type=SourceType.CONVERSATION,
            project=project,
            tags=["known-issue"],
            canonical_key=_issue_key(project, bug[:100]),
        )

    def extract_lesson(self, project: str, lesson: str) -> Optional[Any]:
        rec = self._resolver.resolve(project)
        if not rec:
            return None
        return self._engine.remember(
            content=f"Lesson learned: {lesson}",
            memory_type=MemoryKind.LESSON,
            title=f"Lesson: {lesson[:80]}",
            summary=f"Lesson in {project}: {lesson[:200]}",
            confidence=0.75,
            confidence_basis=ConfidenceBasis.INFERRED,
            source_type=SourceType.CONVERSATION,
            project=project,
            tags=["lesson"],
            canonical_key=_lesson_key(project, lesson[:100]),
        )

    def extract_status_change(self, project: str, new_status: str,
                               detail: str = "") -> Optional[Any]:
        rec = self._resolver.resolve(project)
        if not rec:
            return None
        return self._engine.remember(
            content=f"Status changed to: {new_status}. {detail}".strip(),
            memory_type=MemoryKind.SEMANTIC,
            title=f"Status: {new_status[:60]}",
            summary=f"Project {project} status → {new_status}",
            confidence=0.9,
            confidence_basis=ConfidenceBasis.USER_CONFIRMED,
            source_type=SourceType.CONVERSATION,
            project=project,
            tags=["status-update"],
        )


# ── Handoff Generator ──


class HandoffGenerator:
    """Generate compact handoff for a project from memories."""

    def __init__(self, engine, resolver: ProjectResolver):
        self._engine = engine
        self._resolver = resolver

    def generate(self, project: str) -> HandoffData:
        rec = self._resolver.resolve(project)
        if not rec:
            return HandoffData(project=project, status="unknown")

        decisions = self._get_memories(project, "decision", limit=3)
        issues = self._get_memories(project, "lesson", tags=["known-issue"], limit=3)
        lessons = self._get_memories(project, "lesson", tags=["lesson"], limit=3)
        status = self._get_latest_status(project)

        return HandoffData(
            project=project,
            status=rec.metadata.get("status", "active"),
            done=self._format_list(decisions, "decision"),
            current=rec.metadata.get("current_work", ""),
            next_step=rec.metadata.get("next_step", ""),
            blockers=rec.metadata.get("blockers", []),
            files=rec.metadata.get("important_files", []),
            decisions=[d.get("content", "")[:100] for d in decisions],
            known_issues=[i.get("content", "")[:100] for i in issues],
            generated_at=time.time(),
        )

    def save_handoff(self, project: str) -> Optional[Any]:
        hd = self.generate(project)
        return self._engine.remember(
            content=hd.to_compact(),
            memory_type=MemoryKind.SEMANTIC,
            title=f"Handoff: {project}",
            summary=f"Auto-generated handoff for {project}",
            confidence=1.0,
            confidence_basis=ConfidenceBasis.DOCUMENTED,
            source_type=SourceType.SYSTEM,
            project=project,
            tags=["handoff", "auto-generated"],
            canonical_key=_handoff_key(project),
        )

    def _get_memories(self, project: str, memory_type: str,
                       tags: Optional[List[str]] = None,
                       limit: int = 5) -> List[Dict[str, Any]]:
        report = self._engine.hybrid_search(
            query=f"{project} {memory_type}",
            limit=limit,
            memory_type=memory_type,
            project=project,
        )
        results = []
        for item in (report.results if hasattr(report, "results") else []):
            if hasattr(item, "metadata"):
                results.append(item.metadata if isinstance(item.metadata, dict) else {"title": getattr(item, "title", "")})
            else:
                results.append({"title": str(item)})
        return results

    def _get_latest_status(self, project: str) -> str:
        report = self._engine.hybrid_search(
            query=f"{project} status update",
            limit=1,
            memory_type="semantic",
            project=project,
            tags=["status-update"],
        )
        for item in (report.results if hasattr(report, "results") else []):
            return getattr(item, "content", "")[:200]
        return ""

    def _format_list(self, items: List[Dict], kind: str) -> str:
        if not items:
            return ""
        return "; ".join(i.get("content", "")[:60] for i in items[:3])


# ── Project Memory Manager ──


class ProjectMemoryManager:
    """Main orchestrator for M1.7 Project Memory.

    Wraps GoldenMemoryEngine. Does NOT create parallel DB.
    """

    def __init__(self, engine):
        self._engine = engine
        self._resolver = ProjectResolver(engine)
        self._extractor = SessionLongTermExtractor(engine, self._resolver)
        self._handoff_gen = HandoffGenerator(engine, self._resolver)
        self._detector = MemoryCandidateDetector()
        self._dirty_projects: set = set()
        self._sync_content_hashes: Dict[str, str] = {}

    @property
    def engine(self):
        return self._engine

    @property
    def resolver(self) -> ProjectResolver:
        return self._resolver

    # ── Dirty flag / auto-sync ──

    def _mark_dirty(self, project: str) -> None:
        if project:
            self._dirty_projects.add(project)

    def _sync_if_dirty(self) -> Dict[str, Any]:
        results = {}
        for project in list(self._dirty_projects):
            self._dirty_projects.discard(project)
            try:
                result = self.sync_to_second_brain(project)
                results[project] = result
            except Exception as e:
                results[project] = {"error": str(e)}
        return results

    def _content_hash(self, text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _write_if_changed(self, path: Path, content: str) -> bool:
        key = str(path)
        new_hash = self._content_hash(content)
        if self._sync_content_hashes.get(key) == new_hash:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._sync_content_hashes[key] = new_hash
        return True

    # ── Project management ──

    def create_project(self, name: str, aliases: Optional[List[str]] = None,
                        root_path: str = "", metadata: Optional[Dict] = None) -> ProjectRecord:
        meta = metadata or {}
        rec = self._resolver.resolve_or_create(name, aliases, root_path)
        if meta:
            merged = {**rec.metadata, **meta}
            self._engine.update_entity(rec.entity_id, metadata=merged)
            rec.metadata = merged
        return rec

    def get_project(self, name: str) -> Optional[ProjectRecord]:
        return self._resolver.resolve(name)

    def list_projects(self) -> List[ProjectRecord]:
        return self._resolver.list_projects()

    def update_project(self, name: str, **kwargs) -> Optional[ProjectRecord]:
        rec = self._resolver.resolve(name)
        if not rec:
            return None
        meta = {**rec.metadata}
        for k, v in kwargs.items():
            meta[k] = v
        self._engine.update_entity(rec.entity_id, metadata=meta)
        rec.metadata = meta
        return rec

    # ── Resolution ──

    def resolve_project(self, name: str) -> Optional[ProjectRecord]:
        return self._resolver.resolve(name)

    # ── Current State ──

    def get_current_state(self, project: str) -> ProjectState:
        rec = self._resolver.resolve(project)
        if not rec:
            return ProjectState(project=project, freshness="UNKNOWN")

        meta = rec.metadata
        freshness = self._compute_freshness(rec)
        return ProjectState(
            project=project,
            status=meta.get("status", "active"),
            current_phase=meta.get("current_phase", ""),
            last_completed=meta.get("last_completed", ""),
            current_work=meta.get("current_work", ""),
            next_step=meta.get("next_step", ""),
            blockers=meta.get("blockers", []),
            important_files=meta.get("important_files", []),
            known_issues=meta.get("known_issues", []),
            last_handoff=self._get_latest_handoff_text(project),
            freshness=freshness,
            updated_at=rec.updated_at,
            source="entity-metadata",
        )

    def update_project_state(self, project: str, **state_kwargs) -> ProjectState:
        rec = self._resolver.resolve(project)
        if not rec:
            rec = self.create_project(project)
        meta = {**rec.metadata}
        for k, v in state_kwargs.items():
            if k in ("status", "current_phase", "last_completed", "current_work",
                      "next_step", "blockers", "important_files", "known_issues"):
                meta[k] = v
        meta["updated_at"] = time.time()
        self._engine.update_entity(rec.entity_id, metadata=meta)
        self._mark_dirty(project)
        return self.get_current_state(project)

    # ── Memory Operations ──

    def remember(self, content: str, project: str, memory_type: str = "semantic",
                  title: str = "", summary: str = "", confidence: float = 0.7,
                  tags: Optional[List[str]] = None, **kwargs) -> Any:
        mt = memory_type
        if isinstance(mt, str):
            try:
                mt = MemoryKind(mt)
            except (ValueError, KeyError):
                mt = MemoryKind.SEMANTIC
        cb = kwargs.get("confidence_basis", "inferred")
        if isinstance(cb, str):
            try:
                cb = ConfidenceBasis(cb)
            except (ValueError, KeyError):
                cb = ConfidenceBasis.INFERRED
        st = kwargs.get("source_type", "conversation")
        if isinstance(st, str):
            try:
                st = SourceType(st)
            except (ValueError, KeyError):
                st = SourceType.CONVERSATION
        result = self._engine.remember(
            content=content,
            memory_type=mt,
            title=title,
            summary=summary,
            confidence=confidence,
            confidence_basis=cb,
            source_type=st,
            source_ref=kwargs.get("source_ref", ""),
            project=project,
            tags=tags or [],
            canonical_key=kwargs.get("canonical_key", ""),
        )
        if project and mt in (MemoryKind.DECISION, MemoryKind.LESSON):
            self._mark_dirty(project)
        return result

    def get_memories(self, project: str, query: str = "",
                      memory_type: Optional[str] = None,
                      limit: int = MEMORY_RETRIEVAL_MAX_ITEMS) -> List[Dict[str, Any]]:
        q = query or f"{project} context"
        report = self._engine.hybrid_search(
            query=q, limit=limit,
            memory_type=memory_type, project=project,
        )
        results = []
        for item in (report.results if hasattr(report, "results") else []):
            d = {
                "title": getattr(item, "title", ""),
                "content": getattr(item, "snippet", ""),
                "memory_type": getattr(item, "memory_type", ""),
                "project": getattr(item, "project", ""),
                "score": getattr(item, "final_score", 0),
                "privacy": getattr(item, "privacy", "INTERNAL"),
            }
            results.append(d)
        return results

    # ── Decisions ──

    def record_decision(self, project: str, decision: str,
                         rationale: str = "") -> Any:
        self._mark_dirty(project)
        return self._extractor.extract_decision(project, decision, rationale)

    def get_decisions(self, project: str, limit: int = DECISIONS_MAX_ITEMS) -> List[Dict[str, Any]]:
        return self.get_memories(project, "decision", "decision", limit)

    # ── Known Issues ──

    def record_issue(self, project: str, issue: str,
                      resolution: str = "") -> Any:
        self._mark_dirty(project)
        return self._extractor.extract_bug(project, issue, resolution)

    def get_known_issues(self, project: str, limit: int = 5) -> List[str]:
        mems = self.get_memories(project, "known issue", "lesson", limit)
        return [m.get("content", "")[:200] for m in mems]

    # ── Lessons ──

    def record_lesson(self, project: str, lesson: str) -> Any:
        self._mark_dirty(project)
        return self._extractor.extract_lesson(project, lesson)

    # ── Task tracking ──

    def record_task_completed(self, project: str, task: str,
                               details: str = "") -> Any:
        return self._extractor.extract_task_completed(project, task, details)

    def record_status_change(self, project: str, new_status: str,
                              detail: str = "") -> Any:
        result = self._extractor.extract_status_change(project, new_status, detail)
        self.update_project_state(project, status=new_status)
        return result

    # ── Handoff ──

    def generate_handoff(self, project: str) -> HandoffData:
        return self._handoff_gen.generate(project)

    def save_handoff(self, project: str) -> Any:
        return self._handoff_gen.save_handoff(project)

    def get_handoff(self, project: str) -> str:
        hd = self.generate_handoff(project)
        return hd.to_compact()

    # ── Memory Candidates ──

    def detect_candidates(self, content: str, project: str = "",
                           title: str = "", tags: Optional[List[str]] = None) -> List[MemoryCandidate]:
        return self._detector.detect(content, project, title, tags)

    def promote_candidate(self, candidate: MemoryCandidate) -> Optional[Any]:
        if candidate.verdict != "promote":
            return None
        return self.remember(
            content=candidate.content,
            project=candidate.project,
            memory_type=candidate.memory_type,
            title=candidate.title,
            summary=candidate.summary,
            confidence=candidate.confidence,
            tags=candidate.tags,
            confidence_basis=candidate.confidence_basis,
            source_type=candidate.source_type,
        )

    # ── Project Context (main API) ──

    def get_project_context(self, project: str) -> ProjectContext:
        state = self.get_current_state(project)
        memories = self.get_memories(project)
        decisions = self.get_decisions(project)
        issues = self.get_known_issues(project)
        handoff = self.get_handoff(project)

        important_files = []
        rec = self._resolver.resolve(project)
        if rec:
            important_files = rec.metadata.get("important_files", [])

        next_step = ""
        if rec:
            next_step = rec.metadata.get("next_step", "")

        token_est = self._estimate_tokens(state, memories, decisions)

        return ProjectContext(
            project=project,
            state=state,
            relevant_memories=memories,
            decisions=decisions,
            known_issues=issues,
            next_step=next_step,
            important_files=important_files[:IMPORTANT_FILES_MAX],
            handoff=handoff,
            token_estimate=token_est,
        )

    # ── Cross-project ──

    def get_global_memories(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        report = self._engine.hybrid_search(query=query, limit=limit)
        results = []
        for item in (report.results if hasattr(report, "results") else []):
            proj = getattr(item, "project", "")
            if not proj:
                d = {
                    "title": getattr(item, "title", ""),
                    "content": getattr(item, "snippet", ""),
                    "memory_type": getattr(item, "memory_type", ""),
                    "project": "",
                    "score": getattr(item, "final_score", 0),
                }
                results.append(d)
        return results

    # ── Session integration ──

    def on_session_end(self, project: str, summary: str,
                        decisions: Optional[List[str]] = None,
                        tasks_completed: Optional[List[str]] = None,
                        issues_found: Optional[List[str]] = None) -> None:
        if decisions:
            for d in decisions:
                self.record_decision(project, d)
        if tasks_completed:
            for t in tasks_completed:
                self.record_task_completed(project, t)
        if issues_found:
            for i in issues_found:
                self.record_issue(project, i)
        if summary:
            self.remember(
                content=summary, project=project,
                memory_type="semantic",
                title=f"Session summary: {summary[:80]}",
                tags=["session-summary"],
            )
        self.save_handoff(project)
        self._mark_dirty(project)
        self._sync_if_dirty()

    # ── Second Brain sync ──

    def sync_to_second_brain(self, project: str) -> Dict[str, Any]:
        from ...context_index import ContextIndexBuilder
        from datetime import datetime
        builder = ContextIndexBuilder()
        result = {"project": project, "files_updated": [], "skipped": []}

        # CURRENT_STATE.md
        state = self.get_current_state(project)
        state_path = builder.vault / "Projetos" / project / "CURRENT_STATE.md"
        content = state.to_compact()
        if self._write_if_changed(state_path, content):
            result["files_updated"].append("CURRENT_STATE.md")
        else:
            result["skipped"].append("CURRENT_STATE.md")

        # DECISIONS.md
        decisions = self.get_decisions(project, limit=5)
        now = datetime.now().strftime("%Y-%m-%d")
        if decisions:
            lines = ["---", f"last_updated: {now}", "source: auto-generated",
                     f"scope: {project} — Decisões", "status: CURRENT", "---", "",
                     f"# {project} — Decisões", ""]
            for d in decisions:
                lines.append(f"- {d.get('content', '')[:200]}")
            dec_content = "\n".join(lines)
        else:
            dec_content = ""
        dec_path = builder.vault / "Projetos" / project / "DECISIONS.md"
        if dec_content:
            if self._write_if_changed(dec_path, dec_content):
                result["files_updated"].append("DECISIONS.md")
            else:
                result["skipped"].append("DECISIONS.md")
        elif dec_path.exists():
            dec_path.unlink()

        # KNOWN_ISSUES.md
        issues = self.get_known_issues(project, limit=5)
        if issues:
            lines = ["---", f"last_updated: {now}", "source: auto-generated",
                     f"scope: {project} — Issues conhecidas", "status: CURRENT", "---", "",
                     f"# {project} — Known Issues", ""]
            for i in issues:
                lines.append(f"- {i[:200]}")
            iss_content = "\n".join(lines)
        else:
            iss_content = ""
        iss_path = builder.vault / "Projetos" / project / "KNOWN_ISSUES.md"
        if iss_content:
            if self._write_if_changed(iss_path, iss_content):
                result["files_updated"].append("KNOWN_ISSUES.md")
            else:
                result["skipped"].append("KNOWN_ISSUES.md")
        elif iss_path.exists():
            iss_path.unlink()

        # HANDOFF.md
        hd = self.generate_handoff(project)
        if hd.done or hd.current:
            ho_lines = ["---", f"last_updated: {now}", "source: auto-generated",
                        f"scope: {project} — Handoff", "status: CURRENT", "---", "",
                        hd.to_compact()]
            ho_content = "\n".join(ho_lines)
        else:
            ho_content = ""
        ho_path = builder.vault / "Projetos" / project / "HANDOFF.md"
        if ho_content:
            if self._write_if_changed(ho_path, ho_content):
                result["files_updated"].append("HANDOFF.md")
            else:
                result["skipped"].append("HANDOFF.md")
        elif ho_path.exists():
            ho_path.unlink()

        return result

    # ── Internal helpers ──

    def _compute_freshness(self, rec: ProjectRecord) -> str:
        if rec.updated_at == 0:
            return "UNKNOWN"
        age_hours = (time.time() - rec.updated_at) / 3600
        if age_hours < 24:
            return "CURRENT"
        if age_hours < 168:
            return "STALE"
        return "UNKNOWN"

    def _get_latest_handoff_text(self, project: str) -> str:
        report = self._engine.hybrid_search(
            query=f"{project} handoff",
            limit=1,
            memory_type="semantic",
            project=project,
            tags=["handoff"],
        )
        for item in (report.results if hasattr(report, "results") else []):
            return getattr(item, "content", "")[:500]
        return ""

    def _estimate_tokens(self, state: ProjectState, memories: List,
                          decisions: List) -> int:
        text = state.to_compact()
        for m in memories:
            text += " " + str(m.get("content", ""))
        for d in decisions:
            text += " " + str(d.get("content", ""))
        return len(text) // 4
