"""Focused tests for the real Windows PCM output adapter.

All tests use a fake RawOutputStream.  No microphone, speaker, file, or
network is touched by this suite.
"""

from __future__ import annotations

import pytest

from jarvis_core.audio_output import SoundDeviceAudioOutputProvider
from jarvis_core.voice_service import VoiceService
from jarvis_core.voice_tts import FakeTextToSpeechProvider, PcmAudioChunk, VoiceAudioPipeline


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = 0
        self.aborted = 0
        self.stopped = 0
        self.closed = 0

    def start(self):
        self.started += 1

    def abort(self):
        self.aborted += 1

    def stop(self):
        self.stopped += 1

    def close(self):
        self.closed += 1


class FakeSoundDevice:
    class _Default:
        device = (3, 7)

    default = _Default()

    def __init__(self):
        self.streams = []

    def RawOutputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream

    def query_devices(self):
        return [
            {"name": "Mic only", "max_output_channels": 0, "default_samplerate": 16000},
            {"name": "Golden Speakers", "max_output_channels": 2, "default_samplerate": 48000},
        ]


def _chunk(*, value=1, sample_rate=22050, channels=1, sequence=0, session="s", turn=1, generation=1):
    frame = value.to_bytes(2, "little", signed=True)
    return PcmAudioChunk(
        pcm=frame * 8 * channels,
        sample_rate=sample_rate,
        channels=channels,
        sequence=sequence,
        session_id=session,
        turn_id=turn,
        generation=generation,
    )


def test_provider_reuses_sounddevice_and_enumerates_output_only():
    sd = FakeSoundDevice()

    devices = SoundDeviceAudioOutputProvider.enumerate_devices(sd)

    assert devices == [{
        "index": 1,
        "name": "Golden Speakers",
        "max_output_channels": 2,
        "default_samplerate": 48000.0,
    }]
    assert SoundDeviceAudioOutputProvider.default_output_device(sd) == 7


def test_output_lifecycle_ordering_and_callback_frame_alignment():
    created = []

    def factory(**kwargs):
        stream = FakeStream(**kwargs)
        created.append(stream)
        return stream

    output = SoundDeviceAudioOutputProvider(stream_factory=factory)
    output.warm()
    first = _chunk(value=1, sequence=0)
    second = _chunk(value=2, sequence=1)

    assert output.enqueue(first) is True
    assert output.enqueue(second) is True
    assert len(created) == 1
    assert created[0].started == 1
    assert created[0].kwargs["dtype"] == "int16"

    first_out = bytearray(len(first.pcm))
    second_out = bytearray(len(second.pcm))
    output._callback(first_out, frames=8)
    output._callback(second_out, frames=8)
    assert bytes(first_out) == first.pcm
    assert bytes(second_out) == second.pcm

    output.stop()
    assert output.is_active is False
    assert created[0].aborted == 1
    assert created[0].stopped == 1
    assert created[0].closed == 1
    output.stop()
    output.release()
    output.release()


def test_pcm_validation_rejects_unaligned_and_unsupported_chunks():
    output = SoundDeviceAudioOutputProvider()
    output.warm()

    with pytest.raises(ValueError, match="frame aligned"):
        output.enqueue(PcmAudioChunk(pcm=b"\x00", sample_rate=22050))
    with pytest.raises(ValueError, match="range"):
        output.enqueue(PcmAudioChunk(pcm=b"\x00\x00", sample_rate=1))
    with pytest.raises(ValueError, match="mono or stereo"):
        output.enqueue(PcmAudioChunk(pcm=b"\x00\x00" * 3, sample_rate=22050, channels=3))


def test_bounded_queue_has_explicit_drop_oldest_policy():
    output = SoundDeviceAudioOutputProvider(maxsize=2, stream_factory=lambda **kwargs: FakeStream(**kwargs))
    output.warm()

    assert output.enqueue(_chunk(sequence=0)) is True
    assert output.enqueue(_chunk(sequence=1)) is True
    assert output.enqueue(_chunk(sequence=2)) is True

    assert output.qsize == 2
    assert output.dropped == 1
    assert output.diagnostics()["queue_maxsize"] == 2
    assert output.diagnostics()["queue_policy"] == "drop_oldest"


def test_cancel_before_open_and_during_playback_flushes_and_blocks_late_audio():
    created = []

    def factory(**kwargs):
        stream = FakeStream(**kwargs)
        created.append(stream)
        return stream

    output = SoundDeviceAudioOutputProvider(stream_factory=factory)
    output.warm()
    output.cancel("before_open")
    assert output.enqueue(_chunk()) is False
    assert created == []

    output.warm()
    assert output.enqueue(_chunk()) is True
    stream = created[0]
    output.cancel("barge_in")
    assert output.qsize == 0
    assert output.is_active is False
    assert stream.aborted == 1
    assert output.enqueue(_chunk()) is False
    callback_out = bytearray(16)
    output._callback(callback_out, frames=8)
    assert callback_out == bytearray(16)
    output.cancel("double_cancel")


def test_format_changes_require_a_turn_boundary():
    output = SoundDeviceAudioOutputProvider(stream_factory=lambda **kwargs: FakeStream(**kwargs))
    output.warm()
    assert output.enqueue(_chunk(sample_rate=22050)) is True
    assert output.enqueue(_chunk(sample_rate=44100)) is False

    output.cancel("new_turn")
    output.warm()
    assert output.enqueue(_chunk(sample_rate=44100)) is True


def test_open_failure_has_bounded_recovery_and_no_zombie_stream():
    attempts = []

    def factory(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RuntimeError("speaker unavailable")
        return FakeStream(**kwargs)

    output = SoundDeviceAudioOutputProvider(stream_factory=factory, recovery_attempts=1)
    output.warm()
    assert output.enqueue(_chunk()) is False
    assert output.stream is None
    assert output.enqueue(_chunk(sequence=1)) is True
    assert len(attempts) == 2
    assert output.diagnostics()["open_attempts"] == 2


def test_device_loss_can_recover_without_switching_device():
    created = []

    def factory(**kwargs):
        stream = FakeStream(**kwargs)
        created.append(stream)
        return stream

    output = SoundDeviceAudioOutputProvider(device=11, stream_factory=factory)
    output.warm()
    assert output.enqueue(_chunk()) is True
    assert output.enqueue(_chunk(sequence=1)) is True
    output._callback(bytearray(8), frames=4, status="device unavailable")
    assert output.diagnostics()["device_lost"] is True
    assert output.recover() is True
    assert created[0].closed == 1
    assert len(created) == 2
    assert created[1].kwargs["device"] == 11


def test_pipeline_and_voice_service_use_the_single_output_boundary():
    output = SoundDeviceAudioOutputProvider(stream_factory=lambda **kwargs: FakeStream(**kwargs))
    pipeline = VoiceAudioPipeline(FakeTextToSpeechProvider(), output)
    result = pipeline.speak("resposta.", session_id="s", turn_id=2, generation=4)
    assert result.ok is True
    assert output.accepted == 1
    assert pipeline.identity == ("s", 2, 4)
    pipeline.release()

    service = VoiceService()
    service_output = SoundDeviceAudioOutputProvider(stream_factory=lambda **kwargs: FakeStream(**kwargs))
    configured = service.configure_tts_pipeline(FakeTextToSpeechProvider(), service_output)
    spoken = service.speak_now("uma resposta")
    assert configured["owner"] == "VoiceService"
    assert spoken["ok"] is True
    assert service.status()["tts_pipeline"]["configured"] is True
    service.release_tts_pipeline()
