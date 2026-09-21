"""M1.6 — External edit import pipeline.

Importa edições externas do Vault Markdown de volta ao SQLite
via GoldenMemoryEngine. Conteúdo Markdown é UNTRUSTED DATA.

Fluxo:
    Markdown externo
    → parse seguro (frontmatter + body)
    → validar YAML/ID/version
    → comparar com SQLite canônico
    → classificar alteração (SYNCED/DRIFT/CONFLICT/PENDING/ERROR/IGNORED)
    → se aceito: GoldenMemoryEngine.update()
    → re-projetar vault
"""
import hashlib
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .vault import (
    MANAGED_BY, NOTE_SCHEMA_VERSION, SyncStatus,
    parse_frontmatter, projection_hash, split_note,
    _yaml_quote,
)


class ImportDecision(str, Enum):
    ACCEPTED = "accepted"
    DRIFT = "drift"
    CONFLICT = "conflict"
    REJECTED = "rejected"
    ERROR = "error"
    IGNORED = "ignored"


PROTECTED_FIELDS = frozenset({
    "id", "managed_by", "schema_version", "created_at",
})


@dataclass
class ImportResult:
    decision: ImportDecision
    memory_id: Optional[int] = None
    note_id: Optional[str] = None
    detail: str = ""
    sqlite_version: int = 0
    markdown_version: int = 0
    conflicts: Optional[Dict[str, Any]] = None


class VaultImporter:
    """Importa edições externas do Vault Markdown.

    Uso:
        importer = VaultImporter(engine, vault_root)
        result = importer.import_file(path)
    """

    def __init__(self, engine: Any, vault_root: Path):
        self.engine = engine
        self.vault_root = Path(vault_root)

    def import_file(self, path: Path) -> ImportResult:
        """Importa uma alteração externa de um arquivo Markdown."""
        path = Path(path)
        if not path.exists():
            return ImportResult(
                decision=ImportDecision.ERROR,
                detail="file-not-found")

        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            return ImportResult(
                decision=ImportDecision.ERROR,
                detail="read-error: %s" % type(exc).__name__)

        return self.import_text(text, path=path)

    def import_text(self, text: str,
                    path: Optional[Path] = None) -> ImportResult:
        """Importa texto Markdown com frontmatter YAML."""
        try:
            front, body = split_note(text)
        except ValueError as exc:
            return ImportResult(
                decision=ImportDecision.ERROR,
                detail="invalid-frontmatter: %s" % str(exc)[:100])

        managed = front.get("managed_by", "")
        if managed != MANAGED_BY:
            return ImportResult(
                decision=ImportDecision.IGNORED,
                detail="not-managed-by-jarvis")

        note_id = str(front.get("id", "")).strip()
        if not note_id:
            return ImportResult(
                decision=ImportDecision.ERROR,
                detail="missing-id")

        id_match = re.match(r"^(mem|ent)_(\d+)$", note_id)
        if not id_match:
            return ImportResult(
                decision=ImportDecision.ERROR,
                detail="invalid-id-format: %s" % note_id)

        kind = "memory" if id_match.group(1) == "mem" else "entity"
        record_id = int(id_match.group(2))

        schema_ver = int(front.get("schema_version", 0) or 0)
        if schema_ver > NOTE_SCHEMA_VERSION:
            return ImportResult(
                decision=ImportDecision.REJECTED,
                detail="schema-version-unsupported: %d" % schema_ver)

        privacy = str(front.get("privacy", "INTERNAL")).strip().upper()
        if privacy == "SECRET":
            return ImportResult(
                decision=ImportDecision.REJECTED,
                detail="secret-not-allowed")
        if privacy not in ("PUBLIC", "INTERNAL", "SENSITIVE", "SECRET"):
            return ImportResult(
                decision=ImportDecision.ERROR,
                detail="invalid-privacy: %s" % privacy)

        protected_violations = self._check_protected_fields(front)
        if protected_violations:
            return ImportResult(
                decision=ImportDecision.CONFLICT,
                memory_id=record_id,
                note_id=note_id,
                detail="protected-fields-edited",
                conflicts={"violations": protected_violations})

        if kind == "memory":
            return self._import_memory(
                front, body, record_id, note_id, path)
        else:
            return self._import_entity(
                front, body, record_id, note_id, path)

    def _check_protected_fields(self, front: Dict[str, Any]) -> List[str]:
        """Detecta campos protegidos que foram falsificados."""
        violations = []
        for field in PROTECTED_FIELDS:
            val = front.get(field)
            if val is None:
                continue
            if field == "id":
                if not re.match(r"^(mem|ent)_\d+$", str(val)):
                    violations.append(field)
            elif field == "managed_by":
                if val != MANAGED_BY:
                    violations.append(field)
            elif field == "schema_version":
                if not isinstance(val, (int, float)):
                    violations.append(field)
            elif field == "created_at":
                if not isinstance(val, (int, float)):
                    violations.append(field)
        return violations

    def _import_memory(self, front: Dict[str, Any], body: str,
                       record_id: int, note_id: str,
                       path: Optional[Path]) -> ImportResult:
        """Importa uma memória (memory) do Markdown externo."""
        try:
            current = self.engine.store.load(record_id)
        except Exception:
            current = None

        if current is None:
            return ImportResult(
                decision=ImportDecision.ERROR,
                memory_id=record_id,
                note_id=note_id,
                detail="record-not-found-in-sqlite")

        md_version = int(front.get("version", 1) or 1)
        sqlite_version = int(current.version or 1)

        content_changed = body.strip() != (current.content or "").strip()
        version_changed = md_version != sqlite_version

        if not content_changed and not version_changed:
            return ImportResult(
                decision=ImportDecision.ACCEPTED,
                memory_id=record_id,
                note_id=note_id,
                detail="no-change",
                sqlite_version=sqlite_version,
                markdown_version=md_version)

        if content_changed and version_changed:
            if md_version < sqlite_version:
                return ImportResult(
                    decision=ImportDecision.CONFLICT,
                    memory_id=record_id,
                    note_id=note_id,
                    detail="version-regression",
                    sqlite_version=sqlite_version,
                    markdown_version=md_version,
                    conflicts={
                        "sqlite_version": sqlite_version,
                        "markdown_version": md_version,
                        "content_diff": True,
                    })
            return ImportResult(
                decision=ImportDecision.CONFLICT,
                memory_id=record_id,
                note_id=note_id,
                detail="both-changed",
                sqlite_version=sqlite_version,
                markdown_version=md_version,
                conflicts={
                    "sqlite_version": sqlite_version,
                    "markdown_version": md_version,
                    "content_diff": True,
                })

        if content_changed and not version_changed:
            new_title = front.get("title", current.title) or current.title
            new_summary = front.get("summary", current.summary) or current.summary
            new_tags = list(front.get("tags", current.tags) or current.tags)
            new_confidence = front.get("confidence", current.confidence)
            if isinstance(new_confidence, str):
                try:
                    new_confidence = float(new_confidence)
                except ValueError:
                    new_confidence = current.confidence

            try:
                self.engine.update(
                    record_id,
                    content=body.strip(),
                    title=str(new_title),
                    summary=str(new_summary),
                    confidence=float(new_confidence) if new_confidence is not None else None,
                    metadata=current.metadata,
                )
            except Exception as exc:
                return ImportResult(
                    decision=ImportDecision.ERROR,
                    memory_id=record_id,
                    note_id=note_id,
                    detail="engine-update-failed: %s" % type(exc).__name__)

            self._update_projection_hash(record_id, "memory", path, text=None)
            return ImportResult(
                decision=ImportDecision.ACCEPTED,
                memory_id=record_id,
                note_id=note_id,
                detail="content-imported",
                sqlite_version=sqlite_version,
                markdown_version=md_version)

        if not content_changed and version_changed:
            return ImportResult(
                decision=ImportDecision.DRIFT,
                memory_id=record_id,
                note_id=note_id,
                detail="version-changed-content-unchanged",
                sqlite_version=sqlite_version,
                markdown_version=md_version)

        return ImportResult(
            decision=ImportDecision.ACCEPTED,
            memory_id=record_id,
            note_id=note_id,
            detail="applied",
            sqlite_version=sqlite_version,
            markdown_version=md_version)

    def _import_entity(self, front: Dict[str, Any], body: str,
                       record_id: int, note_id: str,
                       path: Optional[Path]) -> ImportResult:
        """Importa uma entidade do Markdown externo."""
        try:
            current = self.engine.store.get_entity(record_id)
        except Exception:
            current = None

        if current is None:
            return ImportResult(
                decision=ImportDecision.ERROR,
                memory_id=record_id,
                note_id=note_id,
                detail="entity-not-found-in-sqlite")

        md_version = int(front.get("version", 1) or 1)
        sqlite_version = int(current.version or 1)

        new_name = str(front.get("canonical_name", current.canonical_name) or "").strip()
        name_changed = new_name and new_name != current.canonical_name
        version_changed = md_version != sqlite_version

        if not name_changed and not version_changed:
            return ImportResult(
                decision=ImportDecision.ACCEPTED,
                memory_id=record_id,
                note_id=note_id,
                detail="no-change",
                sqlite_version=sqlite_version,
                markdown_version=md_version)

        if name_changed and version_changed:
            return ImportResult(
                decision=ImportDecision.CONFLICT,
                memory_id=record_id,
                note_id=note_id,
                detail="entity-both-changed",
                sqlite_version=sqlite_version,
                markdown_version=md_version,
                conflicts={
                    "sqlite_version": sqlite_version,
                    "markdown_version": md_version,
                    "name_diff": True,
                })

        if name_changed and not version_changed:
            new_aliases = list(front.get("aliases", current.aliases) or current.aliases)
            new_privacy = front.get("privacy", current.privacy.value)
            if hasattr(new_privacy, "value"):
                new_privacy = new_privacy.value

            try:
                self.engine.update_entity(
                    record_id,
                    canonical_name=new_name,
                    aliases=new_aliases,
                )
            except Exception as exc:
                return ImportResult(
                    decision=ImportDecision.ERROR,
                    memory_id=record_id,
                    note_id=note_id,
                    detail="entity-update-failed: %s" % type(exc).__name__)

            self._update_projection_hash(record_id, "entity", path, text=None)
            return ImportResult(
                decision=ImportDecision.ACCEPTED,
                memory_id=record_id,
                note_id=note_id,
                detail="entity-imported",
                sqlite_version=sqlite_version,
                markdown_version=md_version)

        return ImportResult(
            decision=ImportDecision.DRIFT,
            memory_id=record_id,
            note_id=note_id,
            detail="entity-version-changed",
            sqlite_version=sqlite_version,
            markdown_version=md_version)

    def _update_projection_hash(self, record_id: int, kind: str,
                                path: Optional[Path], text: Optional[str]) -> None:
        """Atualiza o hash da projeção após import bem-sucedido."""
        from .migrations import v2_set_projection, v2_get_projection
        try:
            state = v2_get_projection(self.engine.db_path, record_id, kind)
            if path and path.exists():
                actual_text = text or path.read_text(encoding="utf-8")
                actual_hash = projection_hash(actual_text)
                current_version = int(
                    getattr(
                        self.engine.store.load(record_id) if kind == "memory"
                        else self.engine.store.get_entity(record_id),
                        "version", 1) or 1)
                v2_set_projection(
                    self.engine.db_path, record_id, kind,
                    str(path), actual_hash, current_version,
                    SyncStatus.SYNCED.value, "imported")
        except Exception:
            pass

    def _find_path_for_note(self, note_id: str) -> Optional[Path]:
        """Encontra o caminho de um arquivo no Vault pelo note_id."""
        if not self.vault_root.exists():
            return None
        for path in self.vault_root.rglob("*.md"):
            try:
                text = path.read_text(encoding="utf-8")
                front, _ = split_note(text)
                if (front.get("managed_by") == MANAGED_BY
                        and str(front.get("id", "")) == note_id):
                    return path
            except Exception:
                continue
        return None

    def classify_all(self) -> List[Dict[str, Any]]:
        """Classifica o sync status de todas as projeções."""
        from .migrations import v2_list_projections
        results = []
        for proj in v2_list_projections(self.engine.db_path):
            memory_id = proj.get("memory_id", 0)
            kind = proj.get("kind", "memory")
            path_str = proj.get("path", "")
            if not path_str:
                results.append({
                    "memory_id": memory_id,
                    "kind": kind,
                    "sync_status": "pending",
                    "detail": "no-path"})
                continue
            path = Path(path_str)
            if not path.exists():
                results.append({
                    "memory_id": memory_id,
                    "kind": kind,
                    "sync_status": "pending",
                    "detail": "file-missing"})
                continue
            try:
                text = path.read_text(encoding="utf-8")
                front, _ = split_note(text)
                file_hash = projection_hash(text)
                stored_hash = proj.get("projection_hash", "")
                file_changed = file_hash != stored_hash
                stored_version = int(proj.get("projection_version", 0))
                current = None
                if kind == "memory":
                    current = self.engine.store.load(memory_id)
                else:
                    current = self.engine.store.get_entity(memory_id)
                current_version = int(getattr(current, "version", 0) or 0) if current else 0
                record_changed = current_version != stored_version
                if file_changed and record_changed:
                    status = "conflict"
                elif file_changed:
                    status = "drift"
                elif record_changed:
                    status = "pending"
                else:
                    status = "synced"
                results.append({
                    "memory_id": memory_id,
                    "kind": kind,
                    "sync_status": status,
                    "file_changed": file_changed,
                    "record_changed": record_changed,
                    "detail": "ok"})
            except Exception as exc:
                results.append({
                    "memory_id": memory_id,
                    "kind": kind,
                    "sync_status": "error",
                    "detail": str(exc)[:100]})
        return results
