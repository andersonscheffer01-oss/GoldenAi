"""Hardware-free tests for the Batch 02A audio input boundary."""

from __future__ import annotations

import asyncio
import time

import numpy as np

from jarvis_core.realtime_voice.audio_input import (
    AudioInputProvider,
    FakeAudioInputProvider,
)
from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue
from jarvis_core.realtime_voice.constants import FRAME_BYTES, FRAME_SAMPLES


def _frame(value: int = 1) -> bytes:
    return bytes([value]) * FRAME_BYTES


def test_provider_module_import_is_hardware_independent():
    assert AudioInputProvider is not None
    assert FakeAudioInputProvider is not None


def test_fake_provider_delivers_canonical_frames_without_hardware():
    queue = AudioFrameQueue(maxsize=4)
    provider = FakeAudioInputProvider(frame_queue=queue)

    assert provider.start()["ok"] is True
    provider.emit_frame(_frame(7))
    assert queue.qsize == 1
    assert queue._queue.get_nowait() == _frame(7)
    assert provider.stop()["ok"] is True


def test_fake_provider_rejects_invalid_frame_without_persistence():
    provider = FakeAudioInputProvider()
    provider.start()
    provider.emit_frame(b"bad")
    assert provider.diagnostics()["invalid_frames"] == 1
    assert provider.queue.empty
    provider.stop()


def test_provider_start_is_nonduplicating_and_stop_is_idempotent():
    created = []

    class Stream:
        def __init__(self):
            self.starts = 0
            self.stops = 0
            self.closes = 0

        def start(self):
            self.starts += 1

        def stop(self):
            self.stops += 1

        def close(self):
            self.closes += 1

    def factory(**kwargs):
        stream = Stream()
        created.append((stream, kwargs))
        return stream

    provider = AudioInputProvider(stream_factory=factory)
    assert provider.start()["started"] is True
    assert provider.start()["already_running"] is True
    assert len(created) == 1
    assert created[0][1]["samplerate"] == 16000
    assert created[0][1]["blocksize"] == 480
    assert provider.stop()["stopped"] is True
    assert provider.stop()["already_stopped"] is True
    assert created[0][0].starts == 1
    assert created[0][0].stops == 1
    assert created[0][0].closes == 1


def test_provider_backpressure_reports_drop_oldest():
    queue = AudioFrameQueue(maxsize=2)
    provider = FakeAudioInputProvider(frame_queue=queue)
    provider.start()
    for value in (1, 2, 3):
        provider.emit_frame(_frame(value))

    diagnostics = provider.diagnostics()
    assert diagnostics["overflow_count"] == 1
    assert diagnostics["dropped_oldest"] == 1
    assert queue.qsize == 2
    provider.stop()


def test_provider_device_failure_is_controlled_and_does_not_persist_audio():
    def failing_factory(**kwargs):
        raise RuntimeError("device unavailable")

    provider = AudioInputProvider(stream_factory=failing_factory)
    result = provider.start()

    assert result["ok"] is False
    assert provider.is_running is False
    assert provider.diagnostics()["device_errors"] == 1
    assert provider.queue.empty


def test_provider_closes_stream_when_stream_start_fails():
    class BrokenStream:
        def __init__(self):
            self.closed = False

        def start(self):
            raise RuntimeError("PortAudio start failed")

        def close(self):
            self.closed = True

    stream = BrokenStream()
    provider = AudioInputProvider(stream_factory=lambda **_: stream)

    assert provider.start()["ok"] is False
    assert stream.closed is True
    assert provider.is_running is False


def test_provider_callback_failure_is_isolated():
    provider = AudioInputProvider()
    provider.start = lambda: {"ok": True, "started": True}  # no hardware path
    provider._running = True

    class BrokenBuffer:
        def __bytes__(self):
            raise RuntimeError("callback conversion failed")

    provider._on_callback(BrokenBuffer(), FRAME_BYTES // 2)
    assert provider.diagnostics()["callback_errors"] == 1
    provider._running = False


def test_fake_provider_restart_and_queue_cancellation_are_safe():
    async def exercise():
        provider = FakeAudioInputProvider()
        assert provider.start()["ok"] is True
        assert provider.stop()["ok"] is True
        assert provider.start()["ok"] is True
        provider.queue.cancel()
        provider.emit_frame(_frame())
        assert provider.queue.empty
        assert provider.stop()["ok"] is True

    asyncio.run(exercise())


def _device_snapshot(devices, default_device=1):
    return {
        "devices": devices,
        "hostapis": [{"name": "MME"}, {"name": "WASAPI"}],
        "default_device": default_device,
    }


def _mic(name="Microfone USB", hostapi=0, rate=48000, channels=2):
    return {
        "name": name,
        "hostapi": hostapi,
        "max_input_channels": channels,
        "default_samplerate": rate,
    }


class _CapturedStream:
    def __init__(self, kwargs, streams):
        self.kwargs = kwargs
        self.streams = streams
        self.closed = False
        streams.append(self)

    def start(self):
        return None

    def stop(self):
        return None

    def close(self):
        self.closed = True


def test_native_rate_and_stereo_are_converted_to_canonical_frames():
    streams = []
    queue = AudioFrameQueue(maxsize=4)
    snapshot = lambda: _device_snapshot([{"name": "Speakers", "hostapi": 0, "max_input_channels": 0}, _mic()])
    provider = AudioInputProvider(
        frame_queue=queue,
        device=1,
        stream_factory=lambda **kwargs: _CapturedStream(kwargs, streams),
        device_query=snapshot,
    )

    result = provider.start()
    assert result["ok"] is True
    assert streams[0].kwargs["samplerate"] == 48000
    assert streams[0].kwargs["channels"] == 2
    assert streams[0].kwargs["blocksize"] == 1440

    stereo = np.zeros((1440, 2), dtype=np.int16)
    stereo[:, 0] = 1000
    stereo[:, 1] = 3000
    streams[0].kwargs["callback"](stereo.tobytes(), 1440, None, None)

    deadline = time.monotonic() + 3.0
    while queue.qsize == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert queue.qsize == 1
    assert len(queue._queue.get_nowait()) == FRAME_BYTES
    assert provider.diagnostics()["native_samplerate"] == 48000
    assert provider.diagnostics()["canonical_frames_delivered"] == 1
    provider.stop()
    assert provider._conversion_thread is None


def test_numeric_index_is_reresolved_by_logical_identity_after_reordering():
    snapshots = [
        _device_snapshot([{"name": "Speakers", "hostapi": 0, "max_input_channels": 0}, _mic(rate=44100, channels=1)]),
        _device_snapshot([{"name": "Speakers", "hostapi": 0, "max_input_channels": 0}, {"name": "Other mic", "hostapi": 0, "max_input_channels": 1, "default_samplerate": 16000}, _mic(rate=44100, channels=1)], default_device=2),
    ]
    streams = []
    provider = AudioInputProvider(
        device=1,
        stream_factory=lambda **kwargs: _CapturedStream(kwargs, streams),
        device_query=lambda: snapshots.pop(0),
    )

    assert provider.start()["resolved_device"] == 1
    provider.stop()
    assert provider.start()["resolved_device"] == 2
    assert streams[-1].kwargs["device"] == 2
    provider.stop()


def test_missing_intended_device_is_rejected_without_unrelated_fallback():
    created = []
    provider = AudioInputProvider(
        device="Microfone USB",
        stream_factory=lambda **kwargs: created.append(kwargs),
        device_query=lambda: _device_snapshot([{"name": "Other mic", "hostapi": 0, "max_input_channels": 1, "default_samplerate": 16000}], default_device=0),
    )

    result = provider.start()
    assert result["ok"] is False
    assert "not found" in result["error"]
    assert created == []


def test_old_callback_is_rejected_after_stop_and_restart():
    streams = []
    provider = AudioInputProvider(
        stream_factory=lambda **kwargs: _CapturedStream(kwargs, streams),
    )
    assert provider.start()["ok"] is True
    old_callback = streams[0].kwargs["callback"]
    provider.stop()
    provider.queue.flush()
    assert provider.start()["ok"] is True
    before = provider.diagnostics()["frames_received"]
    old_callback(_frame(4), FRAME_SAMPLES, None, None)
    assert provider.diagnostics()["frames_received"] == before
    assert provider.queue.empty
    provider.stop()


def test_callback_status_tracks_input_overflow_without_leaking_exception():
    class Status:
        input_overflow = True

        def __str__(self):
            return "input overflow"

    provider = AudioInputProvider(stream_factory=lambda **_: _CapturedStream({}, []))
    assert provider.start()["ok"] is True
    provider._on_callback(_frame(2), FRAME_SAMPLES, None, Status())
    assert provider.diagnostics()["input_overflow"] == 1
    assert provider.diagnostics()["frames_received"] == 1
    provider.stop()
