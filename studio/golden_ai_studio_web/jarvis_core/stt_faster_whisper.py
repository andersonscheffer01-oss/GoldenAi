"""Fail-closed local faster-whisper adapter for the approved Jarvis artifact."""

from __future__ import annotations

import io
import logging
import os
import threading
import uuid
import wave
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .voice_foundation import (
    TranscriptEvent,
    VoiceCancellation,
    VoiceCancelledError,
)

log = logging.getLogger(__name__)

APPROVED_MODEL_PROVIDER = "Systran"
APPROVED_MODEL_ID = "Systran/faster-whisper-small"
APPROVED_MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
APPROVED_MODEL_FORMAT = "CTranslate2"
APPROVED_MODEL_DEVICE = "cpu"
APPROVED_MODEL_COMPUTE_TYPE = "int8"
APPROVED_MODEL_LANGUAGE = "pt"
_REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")


class STTModelError(RuntimeError):
    """Base class for controlled local model failures."""


class STTModelNotAvailable(STTModelError):
    """The exact approved local model is absent or incomplete."""


class STTProviderClosed(STTModelError):
    """The provider lifecycle has been closed."""


def _cache_root() -> Path:
    configured = os.getenv("HUGGINGFACE_HUB_CACHE")
    if configured:
        return Path(configured)
    hf_home = os.getenv("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def resolve_approved_model_path(model_path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve only the pinned snapshot; never invokes Hugging Face download code."""
    configured = model_path or os.getenv("JARVIS_STT_MODEL_PATH")
    if configured:
        path = Path(configured).expanduser()
    else:
        path = (
            _cache_root()
            / "models--Systran--faster-whisper-small"
            / "snapshots"
            / APPROVED_MODEL_REVISION
        )
    return path


def validate_approved_model_path(model_path: str | os.PathLike[str] | None = None) -> Path:
    """Validate revision and required CTranslate2 files without hashing per utterance."""
    path = resolve_approved_model_path(model_path)
    if path.name != APPROVED_MODEL_REVISION:
        raise STTModelNotAvailable(
            f"approved revision required: {APPROVED_MODEL_REVISION}"
        )
    if not path.is_dir():
        raise STTModelNotAvailable(f"approved STT artifact is unavailable: {path}")
    missing = [name for name in _REQUIRED_MODEL_FILES if not (path / name).is_file()]
    if missing:
        raise STTModelNotAvailable(
            f"approved STT artifact is incomplete; missing: {', '.join(missing)}"
        )
    return path


def _default_model_loader(**kwargs: Any) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(**kwargs)


def _pcm16_to_float32(audio: bytes, sample_rate: int) -> np.ndarray:
    """Decode WAV or raw mono PCM16 in memory; never creates a temporary file."""
    if not audio:
        return np.empty(0, dtype=np.float32)
    payload = audio
    if audio[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav_file:
                if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
                    raise ValueError("STT input must be mono PCM16")
                payload = wav_file.readframes(wav_file.getnframes())
                sample_rate = wav_file.getframerate()
        except (wave.Error, EOFError) as exc:
            raise ValueError(f"invalid WAV input: {exc}") from exc
    del sample_rate  # retained in the contract for future resampling validation
    samples = np.frombuffer(payload, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


class FasterWhisperSTTProvider:
    """Utterance-based, local-only faster-whisper provider."""

    provider_name = "faster-whisper"

    def __init__(
        self,
        *,
        model_path: str | os.PathLike[str] | None = None,
        model_loader: Callable[..., Any] | None = None,
        language: str = APPROVED_MODEL_LANGUAGE,
        initial_prompt: str = "",
        beam_size: int = 1,
        best_of: int = 1,
    ) -> None:
        self.model_path = model_path
        self._model_loader = model_loader or _default_model_loader
        self.language = language
        self.initial_prompt = initial_prompt
        self.beam_size = max(1, int(beam_size))
        self.best_of = max(1, int(best_of))
        self._model: Any = None
        self._resolved_path: Path | None = None
        self._lock = threading.RLock()
        self._closed = False
        self._sequence = 0
        self._load_error = ""

    @property
    def model(self) -> Any:
        return self._model

    def resolve_model(self) -> Path:
        path = validate_approved_model_path(self.model_path)
        self._resolved_path = path
        return path

    def _ensure_model(self) -> Any:
        if self._closed:
            raise STTProviderClosed("faster-whisper provider is closed")
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            path = self.resolve_model()
            try:
                self._model = self._model_loader(
                    model_size_or_path=str(path),
                    device=APPROVED_MODEL_DEVICE,
                    compute_type=APPROVED_MODEL_COMPUTE_TYPE,
                    cpu_threads=0,
                    num_workers=1,
                    local_files_only=True,
                )
            except Exception as exc:
                self._load_error = str(exc)[:240]
                self._model = None
                raise STTModelError(f"approved STT model load failed: {exc}") from exc
            return self._model

    def transcribe(
        self,
        audio: bytes,
        *,
        sample_rate: int,
        cancellation: VoiceCancellation,
        session_id: str = "",
        utterance_id: str = "",
        epoch: int = 0,
    ) -> TranscriptEvent:
        cancellation.throw_if_cancelled()
        if self._closed:
            raise STTProviderClosed("faster-whisper provider is closed")
        session_id = session_id or uuid.uuid4().hex
        utterance_id = utterance_id or uuid.uuid4().hex
        samples = _pcm16_to_float32(audio, sample_rate)
        if samples.size == 0:
            return TranscriptEvent(
                text="", is_final=True, sequence=self._sequence,
                session_id=session_id, utterance_id=utterance_id,
                provider=self.provider_name, epoch=epoch,
                metadata={"language": self.language, "empty_audio": True},
            )

        model = self._ensure_model()
        cancellation.throw_if_cancelled()
        try:
            segments, info = model.transcribe(
                samples,
                language=self.language,
                beam_size=self.beam_size,
                best_of=self.best_of,
                condition_on_previous_text=False,
                initial_prompt=self.initial_prompt,
            )
            texts: list[str] = []
            avg_logprobs: list[float] = []
            for segment in segments:
                cancellation.throw_if_cancelled()
                text = str(getattr(segment, "text", "") or "").strip()
                if text:
                    texts.append(text)
                value = getattr(segment, "avg_logprob", None)
                if value is not None:
                    avg_logprobs.append(float(value))
        except VoiceCancelledError:
            raise
        except Exception as exc:
            raise STTModelError(f"local transcription failed: {exc}") from exc
        cancellation.throw_if_cancelled()
        self._sequence += 1
        return TranscriptEvent(
            text=" ".join(texts).strip(),
            is_final=True,
            sequence=self._sequence,
            session_id=session_id,
            utterance_id=utterance_id,
            provider=self.provider_name,
            epoch=epoch,
            metadata={
                "language": getattr(info, "language", self.language),
                "duration": getattr(info, "duration", None),
                "avg_logprob": (
                    sum(avg_logprobs) / len(avg_logprobs) if avg_logprobs else None
                ),
                "model_id": APPROVED_MODEL_ID,
                "revision": APPROVED_MODEL_REVISION,
            },
        )

    def close(self) -> None:
        with self._lock:
            self._closed = True
            model = self._model
            self._model = None
        close = getattr(model, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                log.debug("faster-whisper model close failed", exc_info=True)

    def restart(self) -> None:
        self.close()
        self._closed = False
        self._load_error = ""

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model_id": APPROVED_MODEL_ID,
            "revision": APPROVED_MODEL_REVISION,
            "model_path": str(self._resolved_path or resolve_approved_model_path(self.model_path)),
            "device": APPROVED_MODEL_DEVICE,
            "compute_type": APPROVED_MODEL_COMPUTE_TYPE,
            "language": self.language,
            "loaded": self._model is not None,
            "closed": self._closed,
            "load_error": self._load_error,
            "true_streaming": False,
        }


__all__ = [
    "APPROVED_MODEL_COMPUTE_TYPE",
    "APPROVED_MODEL_DEVICE",
    "APPROVED_MODEL_ID",
    "APPROVED_MODEL_LANGUAGE",
    "APPROVED_MODEL_PROVIDER",
    "APPROVED_MODEL_REVISION",
    "FasterWhisperSTTProvider",
    "STTModelError",
    "STTModelNotAvailable",
    "STTProviderClosed",
    "resolve_approved_model_path",
    "validate_approved_model_path",
]
