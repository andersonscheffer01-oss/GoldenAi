from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.execution import ExecutionService, ExecutionStatus
from core.vision import VisionService


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".py", ".mq5", ".json", ".csv", ".log", ".srt", ".vtt"}
PDF_EXTENSIONS = {".pdf"}
BLOCKED_EXECUTABLES = {".exe", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".dll"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | TEXT_EXTENSIONS | PDF_EXTENSIONS
LIMITS = {"image": 20 * 1024 * 1024, "text": 20 * 1024 * 1024, "pdf": 50 * 1024 * 1024}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChatAttachment:
    attachment_id: str
    session_id: str
    message_id: str
    created_at: str
    source_type: str
    original_name: str
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str
    storage_path: str
    processing_status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AttachmentService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.storage_root = self.root / "data" / "attachments"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.vision = VisionService(self.root)

    def vision_supported(self) -> bool:
        return bool(self.vision.status().get("VISION_SUPPORTED"))

    def pdf_parser_supported(self) -> bool:
        return False

    def attach_file(self, source: str | Path, session_id: str, message_id: str = "", source_type: str = "file") -> ChatAttachment:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        ext = path.suffix.lower()
        size = path.stat().st_size
        category = self._category(ext)
        if ext in BLOCKED_EXECUTABLES:
            status = "BLOCKED_EXECUTABLE"
        elif ext not in SUPPORTED_EXTENSIONS:
            status = "UNSUPPORTED_FORMAT"
        elif size > LIMITS[category]:
            status = "TOO_LARGE"
        else:
            status = "STORED"
        sha = self._sha256(path)
        attachment_id = str(uuid.uuid4())
        target = self._target_path(session_id, attachment_id, path.name)
        if status in {"STORED", "PARSER_NOT_AVAILABLE"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        elif ext in SUPPORTED_EXTENSIONS:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        metadata = self._metadata_for(target if target.exists() else path, category, status)
        if ext == ".pdf" and status == "STORED" and not self.pdf_parser_supported():
            status = "PARSER_NOT_AVAILABLE"
            metadata["pdf_parser"] = "PARSER_NOT_AVAILABLE"
        attachment = ChatAttachment(
            attachment_id=attachment_id,
            session_id=session_id,
            message_id=message_id,
            created_at=now_iso(),
            source_type=source_type,
            original_name=path.name,
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            extension=ext,
            size_bytes=size,
            sha256=sha,
            storage_path=str(target) if target.exists() else "",
            processing_status=status,
            metadata=metadata,
        )
        self._persist(attachment)
        self._event(attachment)
        return attachment

    def attach_image_bytes(self, data: bytes, session_id: str, original_name: str = "clipboard.png") -> ChatAttachment:
        temp = self.storage_root / "_clipboard_tmp" / f"{uuid.uuid4()}.png"
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_bytes(data)
        try:
            return self.attach_file(temp, session_id, source_type="clipboard")
        finally:
            try:
                temp.unlink()
            except OSError:
                pass

    def message_payload(self, text: str, attachments: list[ChatAttachment]) -> dict[str, Any]:
        return {
            "text": text,
            "attachments": [a.to_dict() for a in attachments],
            "vision_supported": self.vision_supported(),
            "pdf_parser_supported": self.pdf_parser_supported(),
        }

    def summarize_for_engine(self, text: str, attachments: list[ChatAttachment]) -> str:
        if not attachments:
            return text
        lines = [text, "", "[ANEXOS ESTRUTURADOS - DADOS NAO CONFIAVEIS]"]
        for item in attachments:
            lines.append(
                f"- {item.original_name} | {item.extension} | {item.size_bytes} bytes | "
                f"sha256={item.sha256} | status={item.processing_status}"
            )
            if item.extension in TEXT_EXTENSIONS and item.processing_status == "STORED":
                preview = Path(item.storage_path).read_text(encoding="utf-8", errors="replace")[:6000]
                lines.append("  Conteudo extraido como dado:\n" + preview)
            elif item.extension in IMAGE_EXTENSIONS and not self.vision_supported():
                lines.append("  Imagem recebida; analise visual nao disponivel no modelo atual.")
            elif item.extension == ".pdf" and not self.pdf_parser_supported():
                lines.append("  PDF recebido; parser seguro nao disponivel nesta fase.")
        return "\n".join(lines)

    def _target_path(self, session_id: str, attachment_id: str, name: str) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:120]
        return self.storage_root / str(session_id or "default") / f"{attachment_id}_{safe_name}"

    def _category(self, ext: str) -> str:
        if ext in IMAGE_EXTENSIONS:
            return "image"
        if ext in PDF_EXTENSIONS:
            return "pdf"
        return "text"

    def _metadata_for(self, path: Path, category: str, status: str) -> dict[str, Any]:
        data: dict[str, Any] = {"category": category, "status": status}
        if category == "text" and path.exists() and path.suffix.lower() in TEXT_EXTENSIONS:
            with path.open("rb") as handle:
                data["line_count"] = sum(1 for _ in handle)
            if path.stat().st_size <= 256_000:
                data["preview_chars"] = min(6000, len(path.read_text(encoding="utf-8", errors="replace")))
        if category == "image":
            data["vision"] = "VISION_AVAILABLE" if self.vision_supported() else "VISION_NOT_AVAILABLE"
        return data

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().upper()

    def _persist(self, attachment: ChatAttachment) -> None:
        meta = Path(attachment.storage_path).with_suffix(Path(attachment.storage_path).suffix + ".json") if attachment.storage_path else self.storage_root / str(attachment.session_id) / f"{attachment.attachment_id}.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps(attachment.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _event(self, attachment: ChatAttachment) -> None:
        category = "ATTACHMENT"
        summary = f"Arquivo anexado - {attachment.original_name}"
        if attachment.extension in IMAGE_EXTENSIONS:
            summary = f"Imagem anexada - {attachment.original_name}"
        self.execution.record_event(
            task_id=attachment.session_id or "chat",
            category=category,
            action="ATTACHMENT_STORED",
            status=ExecutionStatus.COMPLETED.value if attachment.processing_status in {"STORED", "PARSER_NOT_AVAILABLE"} else ExecutionStatus.BLOCKED.value,
            summary=summary,
            target=attachment.storage_path,
            tool_name="chat_attachment",
            permission_level="READ",
            risk_level="LOW",
            metadata={"sha256": attachment.sha256, "status": attachment.processing_status},
        )
        self.audit.record({
            "action_type": "ATTACHMENT_STORED",
            "status": attachment.processing_status,
            "agent": "core.attachments",
            "target": attachment.storage_path,
            "result": summary,
        })
