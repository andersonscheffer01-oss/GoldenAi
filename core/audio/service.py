from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.execution import ExecutionService, ExecutionStatus
from core.permissions import PermissionManager

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".opus"}
WHISPER_SIZES = ("tiny", "base", "small", "medium", "large-v3")


@dataclass(frozen=True)
class AudioEnvironment:
    available: bool
    error: str = ""
    whisper_size: str = "base"
    compute_type: str = "int8"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioResult:
    status: str
    text: str = ""
    language: str = ""
    language_probability: float = 0.0
    duration_sec: float = 0.0
    segments: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class AudioService:
    """Transcricao de audio/voz via faster-whisper (CT2, local)."""

    def __init__(self, root: str | Path = r"C:\GoldenAI", whisper_size: str = "base"):
        self.root = Path(root)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.permissions = PermissionManager()
        self.whisper_size = whisper_size if whisper_size in WHISPER_SIZES else "base"
        self._model = None

    def _audit(self, action: str, status: str, target: str = "", detail: str = "") -> None:
        try:
            self.execution.record_event(
                task_id="audio", category="AUDIO", action=action, status=status,
                summary=detail[:600], tool_name="whisper_service",
                permission_level="READ", risk_level="LOW",
            )
            self.audit.record({
                "action_type": action, "status": status, "agent": "core.audio",
                "target": target[:300], "result": detail[:600],
            })
        except Exception:
            pass

    def _model_instance(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.whisper_size, device="cpu", compute_type="int8"
            )
        return self._model

    def audit_environment(self) -> AudioEnvironment:
        try:
            import faster_whisper
            return AudioEnvironment(
                available=True,
                whisper_size=self.whisper_size,
                compute_type="int8",
                evidence={"import": "faster_whisper.WhisperModel", "version": getattr(faster_whisper, "__version__", "?")},
            )
        except Exception as exc:
            return AudioEnvironment(available=False, error=str(exc))

    def status(self) -> dict[str, Any]:
        env = self.audit_environment()
        return {
            "AUDIO_SUPPORTED": env.available,
            "WHISPER_MODEL": env.whisper_size,
            "COMPUTE_TYPE": env.compute_type,
            "ERROR": env.error,
        }

    def transcribe(self, path: str, language: str | None = None, max_chars: int = 40000) -> AudioResult:
        env = self.audit_environment()
        if not env.available:
            return AudioResult("WHISPER_NOT_AVAILABLE", error=env.error)
        source = Path(path)
        if not source.exists() or not source.is_file():
            return AudioResult("FILE_NOT_FOUND", error=f"Arquivo nao encontrado: {path}")
        if source.suffix.lower() not in AUDIO_EXTENSIONS:
            return AudioResult("UNSUPPORTED_TYPE", error=f"Extensao nao suportada: {source.suffix}")
        decision = self.permissions.can_read(source)
        if not decision.allowed:
            return AudioResult("PERMISSION_DENIED", error=decision.reason)

        started = time.perf_counter()
        self._audit("AUDIO_TRANSCRIBE_STARTED", "STARTED", str(source), source.name)
        try:
            model = self._model_instance()
            segments_iter, info = model.transcribe(
                str(source), language=language, vad_filter=True,
            )
            segments = []
            text_parts = []
            for seg in segments_iter:
                entry = {
                    "start": round(seg.start, 2),
                    "end": round(seg.end, 2),
                    "text": seg.text.strip(),
                }
                segments.append(entry)
                text_parts.append(seg.text.strip())
            text = " ".join(text_parts).strip()
            if len(text) > max_chars:
                text = text[:max_chars] + "...[truncado]"
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("AUDIO_TRANSCRIBE_COMPLETED", "COMPLETED", str(source), f"segments={len(segments)}; chars={len(text)}")
            return AudioResult(
                "COMPLETED", text=text, language=getattr(info, "language", "") or "",
                language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
                duration_sec=float(getattr(info, "duration", 0.0) or 0.0),
                segments=segments, duration_ms=duration,
                metadata={"source": str(source), "model": self.whisper_size},
            )
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self._audit("AUDIO_TRANSCRIBE_FAILED", "FAILED", str(source), str(exc))
            return AudioResult("FAILED", error=str(exc), duration_ms=duration)
