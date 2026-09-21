from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.execution import ExecutionService, ExecutionStatus
from core.permissions import PermissionManager


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".md", ".txt"}


@dataclass(frozen=True)
class DocumentEnvironment:
    available: bool
    error: str = ""
    version: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentResult:
    status: str
    text: str = ""
    title: str = ""
    file_type: str = ""
    page_count: int = 0
    char_count: int = 0
    duration_ms: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentService:
    """Extrai conteudo estruturado de PDF/DOCX/PPTX via Docling."""

    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.permissions = PermissionManager()
        self._converter = None

    def _audit(self, action: str, status: str, target: str = "", detail: str = "") -> None:
        try:
            self.execution.record_event(
                task_id="documents", category="DOCUMENT", action=action, status=status,
                summary=detail[:600], tool_name="docling_service",
                permission_level="READ", risk_level="LOW",
            )
            self.audit.record({
                "action_type": action, "status": status, "agent": "core.documents",
                "target": target[:300], "result": detail[:600],
            })
        except Exception:
            pass

    def _converter_instance(self):
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
        return self._converter

    def audit_environment(self) -> DocumentEnvironment:
        try:
            import docling
            env = DocumentEnvironment(
                available=True,
                version=getattr(docling, "__version__", "?"),
                evidence={"import": "docling.document_converter.DocumentConverter"},
            )
            return env
        except Exception as exc:
            return DocumentEnvironment(available=False, error=str(exc))

    def status(self) -> dict[str, Any]:
        env = self.audit_environment()
        return {
            "DOCUMENT_SUPPORTED": env.available,
            "DOCLING_VERSION": env.version,
            "ERROR": env.error,
            "EXTENSIONS": sorted(SUPPORTED_EXTENSIONS),
        }

    def extract(self, path: str, max_chars: int = 120000) -> DocumentResult:
        env = self.audit_environment()
        if not env.available:
            return DocumentResult("DOCLING_NOT_AVAILABLE", error=env.error)
        source = Path(path)
        if not source.exists() or not source.is_file():
            return DocumentResult("FILE_NOT_FOUND", error=f"Arquivo nao encontrado: {path}")
        decision = self.permissions.can_read(source)
        if not decision.allowed:
            self._audit("DOCUMENT_EXTRACT_DENIED", "DENIED", str(source), decision.reason)
            return DocumentResult("PERMISSION_DENIED", error=decision.reason)
        if source.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return DocumentResult("UNSUPPORTED_TYPE", error=f"Extensao nao suportada: {source.suffix}")

        started = time.perf_counter()
        self._audit("DOCUMENT_EXTRACT_STARTED", "STARTED", str(source), source.name)
        try:
            converter = self._converter_instance()
            result = converter.convert(source)
            text = result.document.export_to_markdown()
            title = ""
            try:
                title = result.document.name or source.stem
            except Exception:
                title = source.stem
            page_count = 0
            try:
                from docling_core.types.doc import DocItemLabel
                pages = {item.prov[0].page_no for item in result.document.texts if getattr(item, "prov", None)}
                page_count = len(pages)
            except Exception:
                pass
            if len(text) > max_chars:
                text = text[:max_chars] + "\n...[truncado]"
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("DOCUMENT_EXTRACT_COMPLETED", "COMPLETED", str(source), f"chars={len(text)}; pages={page_count}")
            return DocumentResult(
                "COMPLETED", text=text, title=title, file_type=source.suffix.lower(),
                page_count=page_count, char_count=len(text), duration_ms=duration,
                metadata={"source": str(source), "size_bytes": source.stat().st_size},
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("DOCUMENT_EXTRACT_FAILED", "FAILED", str(source), str(exc))
            return DocumentResult("FAILED", error=str(exc), duration_ms=duration)
