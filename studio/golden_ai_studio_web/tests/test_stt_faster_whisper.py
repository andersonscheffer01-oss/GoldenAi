"""Structural tests for the approved local faster-whisper adapter."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from jarvis_core.stt_faster_whisper import (
    APPROVED_MODEL_COMPUTE_TYPE,
    APPROVED_MODEL_DEVICE,
    APPROVED_MODEL_REVISION,
    FasterWhisperSTTProvider,
    STTModelNotAvailable,
    validate_approved_model_path,
)
from jarvis_core.voice_foundation import VoiceCancellation, VoiceCancelledError


def _artifact(root: Path, revision: str = APPROVED_MODEL_REVISION) -> Path:
    path = root / revision
    path.mkdir()
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        (path / name).write_bytes(b"test")
    return path


class _Segment:
    text = " ola mundo "
    avg_logprob = -0.2


class _Info:
    language = "pt"
    duration = 0.12


class _Model:
    def __init__(self):
        self.calls = []
        self.closed = False

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return iter([_Segment()]), _Info()

    def close(self):
        self.closed = True


def test_approved_artifact_requires_exact_revision_and_files(tmp_path):
    path = _artifact(tmp_path)
    assert validate_approved_model_path(path) == path
    with pytest.raises(STTModelNotAvailable):
        validate_approved_model_path(_artifact(tmp_path, "wrong-revision"))


def test_adapter_loads_only_approved_local_artifact_with_cpu_int8(tmp_path):
    path = _artifact(tmp_path)
    model = _Model()
    loader_calls = []

    def loader(**kwargs):
        loader_calls.append(kwargs)
        return model

    provider = FasterWhisperSTTProvider(model_path=path, model_loader=loader)
    event = provider.transcribe(
        (np.ones(1600, dtype=np.int16) * 100).tobytes(),
        sample_rate=16000,
        cancellation=VoiceCancellation(),
        session_id="s1",
        utterance_id="u1",
        epoch=1,
    )

    assert event.text == "ola mundo"
    assert event.is_final is True
    assert event.session_id == "s1"
    assert event.utterance_id == "u1"
    assert event.provider == "faster-whisper"
    assert loader_calls == [{
        "model_size_or_path": str(path),
        "device": APPROVED_MODEL_DEVICE,
        "compute_type": APPROVED_MODEL_COMPUTE_TYPE,
        "cpu_threads": 0,
        "num_workers": 1,
        "local_files_only": True,
    }]
    assert model.calls[0][1]["language"] == "pt"


def test_adapter_accepts_wav_in_memory_without_creating_audio_files(tmp_path):
    path = _artifact(tmp_path)
    model = _Model()
    provider = FasterWhisperSTTProvider(model_path=path, model_loader=lambda **_: model)
    wav_buffer = __import__("io").BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes((np.zeros(1600, dtype=np.int16)).tobytes())
    before = set(tmp_path.rglob("*.wav"))
    provider.transcribe(wav_buffer.getvalue(), sample_rate=16000,
                        cancellation=VoiceCancellation(), session_id="s", utterance_id="u")
    assert set(tmp_path.rglob("*.wav")) == before


def test_missing_artifact_fails_closed_without_invoking_loader(tmp_path):
    called = []
    provider = FasterWhisperSTTProvider(
        model_path=tmp_path / APPROVED_MODEL_REVISION,
        model_loader=lambda **kwargs: called.append(kwargs),
    )
    with pytest.raises(STTModelNotAvailable):
        provider.transcribe(b"\x00\x00", sample_rate=16000, cancellation=VoiceCancellation())
    assert called == []
    assert provider.status()["loaded"] is False


def test_cancelled_transcription_cannot_load_or_emit_a_result(tmp_path):
    path = _artifact(tmp_path)
    called = []
    provider = FasterWhisperSTTProvider(
        model_path=path,
        model_loader=lambda **kwargs: called.append(kwargs),
    )
    cancellation = VoiceCancellation()
    cancellation.cancel("stale session")
    with pytest.raises(VoiceCancelledError):
        provider.transcribe(b"pcm", sample_rate=16000, cancellation=cancellation)
    assert called == []


def test_shutdown_and_restart_are_cooperative(tmp_path):
    path = _artifact(tmp_path)
    model = _Model()
    provider = FasterWhisperSTTProvider(model_path=path, model_loader=lambda **_: model)
    provider.transcribe(b"\x00\x00", sample_rate=16000, cancellation=VoiceCancellation())
    provider.close()
    assert provider.status()["closed"] is True
    assert model.closed is True
    provider.restart()
    assert provider.status()["closed"] is False
