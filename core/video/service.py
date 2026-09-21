from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.execution import ExecutionService, ExecutionStatus
from core.permissions import PermissionManager

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts"}
VIDEO_MAX_DURATION_SEC = 3600


@dataclass(frozen=True)
class VideoEnvironment:
    available: bool
    error: str = ""
    ffmpeg_path: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoResult:
    status: str
    text: str = ""
    transcript: str = ""
    scene_notes: list[dict[str, Any]] = field(default_factory=list)
    duration_sec: float = 0.0
    frames: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class VideoService:
    """Analisa video: extrai audio (FFmpeg) -> transcreve (Whisper) -> extrai frames e
    descreve cenas (vision). Funde tudo numa timeline de cenas."""

    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.permissions = PermissionManager()
        self.workdir = self.root / "sandbox" / "video"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _audit(self, action: str, status: str, target: str = "", detail: str = "") -> None:
        try:
            self.execution.record_event(
                task_id="video", category="VIDEO", action=action, status=status,
                summary=detail[:600], tool_name="video_service",
                permission_level="READ", risk_level="LOW",
            )
            self.audit.record({
                "action_type": action, "status": status, "agent": "core.video",
                "target": target[:300], "result": detail[:600],
            })
        except Exception:
            pass

    def _ffmpeg(self) -> str:
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def audit_environment(self) -> VideoEnvironment:
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
            return VideoEnvironment(available=True, ffmpeg_path=path, evidence={"ffmpeg": path})
        except Exception as exc:
            return VideoEnvironment(available=False, error=str(exc))

    def status(self) -> dict[str, Any]:
        env = self.audit_environment()
        return {
            "VIDEO_SUPPORTED": env.available,
            "FFMPEG_PATH": env.ffmpeg_path,
            "ERROR": env.error,
            "EXTENSIONS": sorted(VIDEO_EXTENSIONS),
        }

    def _run_ffmpeg(self, args: list[str], timeout: int = 600) -> tuple[int, str, str]:
        import subprocess
        proc = subprocess.run(
            [self._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"] + args,
capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def _duration(self, video: Path) -> float:
        try:
            import subprocess
            proc = subprocess.run(
                [self._ffmpeg(), "-hide_banner", "-i", str(video)],
                capture_output=True, text=True, timeout=30,
            )
            import re
            err = proc.stderr or ""
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
            if m:
                h, mm, s = m.groups()
                return int(h) * 3600 + int(mm) * 60 + float(s)
        except Exception:
            pass
        return 0.0

    def analyze(self, path: str, max_frames: int = 6, fps: float = 0.3) -> VideoResult:
        env = self.audit_environment()
        if not env.available:
            return VideoResult("FFMPEG_NOT_AVAILABLE", error=env.error)
        source = Path(path)
        if not source.exists() or not source.is_file():
            return VideoResult("FILE_NOT_FOUND", error=f"Arquivo nao encontrado: {path}")
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
            return VideoResult("UNSUPPORTED_TYPE", error=f"Extensao nao suportada: {source.suffix}")
        decision = self.permissions.can_read(source)
        if not decision.allowed:
            return VideoResult("PERMISSION_DENIED", error=decision.reason)

        started = time.perf_counter()
        self._audit("VIDEO_ANALYZE_STARTED", "STARTED", str(source), source.name)
        try:
            duration = self._duration(source)
            if duration <= 0:
                duration = 0.0
            if duration > VIDEO_MAX_DURATION_SEC:
                return VideoResult("TOO_LONG", error=f"Video muito longo ({duration:.0f}s). Maximo {VIDEO_MAX_DURATION_SEC}s.")

            task_dir = self.workdir / source.stem
            task_dir.mkdir(parents=True, exist_ok=True)
            audio_path = task_dir / "audio.wav"
            frame_dir = task_dir / "frames"
            frame_dir.mkdir(parents=True, exist_ok=True)

            # 1) Extrai audio
            rc, _, err = self._run_ffmpeg(["-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)])
            if rc != 0:
                return VideoResult("AUDIO_EXTRACT_FAILED", error=f"ffmpeg audio: {err[-400:]}")

            # 2) Transcreve
            transcript = ""
            audio_segments = []
            try:
                from core.audio import AudioService
                audio_res = AudioService(self.root).transcribe(str(audio_path))
                if audio_res.status == "COMPLETED":
                    transcript = audio_res.text
                    audio_segments = audio_res.segments
            except Exception as exc:
                transcript = f"[erro transcricao: {exc}]"

            # 3) Extrai frames (1 frame por segundo ~ fps)
            frame_paths: list[str] = []
            rc, _, err = self._run_ffmpeg(
                ["-i", str(source), "-vf", f"fps={fps}", "-q:v", "5", str(frame_dir / "f_%04d.jpg")]
            )
            if rc == 0:
                for f in sorted(frame_dir.glob("f_*.jpg")):
                    frame_paths.append(str(f))
            if len(frame_paths) > max_frames:
                # amostra uniforme
                step = len(frame_paths) / max_frames
                frame_paths = [frame_paths[int(i * step)] for i in range(max_frames)]

            # 4) Descreve frames com vision
            scene_notes: list[dict[str, Any]] = []
            try:
                from core.vision import VisionService
                vision = VisionService(self.root)
                env_vis = vision.audit_environment()
                if env_vis.vision_available and frame_paths:
                    batch = 3
                    for i in range(0, len(frame_paths), batch):
                        group = frame_paths[i:i + batch]
                        res = vision.analyze_images(
                            group,
                            "Descreva brevemente o que aparece em cada imagem. Se houver tela de computador, texto ou erro, cite o conteudo. Responda em portugues.",
                        )
                        if res.status == "COMPLETED" and res.text:
                            scene_notes.append({
                                "frames": [Path(f).name for f in group],
                                "description": res.text[:1500],
                                "timestamp_sec": round(i / max(1, fps), 1),
                            })
            except Exception as exc:
                scene_notes.append({"error": f"vision: {exc}"})

            # 5) Funde timeline
            text_parts = []
            if transcript:
                text_parts.append(f"TRANSCRICAO:\n{transcript}")
            if scene_notes:
                text_parts.append("CENAS VISUAIS:")
                for note in scene_notes:
                    if "description" in note:
                        text_parts.append(f"[{note.get('timestamp_sec', 0)}s] {note['description']}")
                    else:
                        text_parts.append(str(note))
            text = "\n\n".join(text_parts) if text_parts else "(sem transcricao nem cenas detectadas)"
            if len(text) > 50000:
                text = text[:50000] + "...[truncado]"

            duration_ms = int((time.perf_counter() - started) * 1000)
            self._audit("VIDEO_ANALYZE_COMPLETED", "COMPLETED", str(source), f"seg={len(audio_segments)}; frames={len(frame_paths)}")
            return VideoResult(
                "COMPLETED", text=text, transcript=transcript, scene_notes=scene_notes,
                duration_sec=duration, frames=frame_paths, duration_ms=duration_ms,
                metadata={"source": str(source), "model": "whisper+vision"},
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._audit("VIDEO_ANALYZE_FAILED", "FAILED", str(source), str(exc))
            return VideoResult("FAILED", error=str(exc), duration_ms=duration_ms)
