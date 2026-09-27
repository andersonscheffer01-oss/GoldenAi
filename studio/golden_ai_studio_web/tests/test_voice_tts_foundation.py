"""Hardware/network-free tests for the provider-neutral TTS foundation."""

from __future__ import annotations

import threading
import time

import pytest

from jarvis_core.voice_foundation import VoiceCancellation
from jarvis_core.voice_service import VoiceService
from jarvis_core.voice_tts import (
    AudioOutputProvider,
    FakeAudioOutputProvider,
    FakeTextToSpeechProvider,
    PcmAudioChunk,
    TextToSpeechProvider,
    VoiceAudioPipeline,
)


def _chunk(*, session="s1", turn=1, generation=1, sequence=0, final=True):
    return PcmAudioChunk(
        pcm=b"\x00\x00" * 8,
        sample_rate=22050,
        sequence=sequence,
        session_id=session,
        turn_id=turn,
        generation=generation,
        is_final=final,
    )


def _pipeline(*, delay=0.0, failure=None, maxsize=8):
    provider = FakeTextToSpeechProvider(chunk_delay=delay, failure=failure)
    output = FakeAudioOutputProvider(maxsize=maxsize)
    pipeline = VoiceAudioPipeline(provider, output)
    return pipeline, provider, output


def test_fake_tts_is_provider_neutral_and_emits_ordered_pcm_events():
    pipeline, provider, output = _pipeline()

    result = pipeline.speak(
        "primeira frase. segunda frase! terceira frase?",
        session_id="session-1",
        turn_id=7,
        generation=3,
    )

    assert result.ok is True
    assert result.accepted_chunks == 3
    assert result.final_emitted is True
    assert [chunk.sequence for chunk in output.accepted] == [0, 1, 2]
    assert all(chunk.identity == ("session-1", 7, 3) for chunk in output.accepted)
    assert all(chunk.sample_format == "s16le" and chunk.pcm for chunk in output.accepted)
    assert provider.warm_count >= 1


def test_synthesize_and_stream_share_the_same_deterministic_contract():
    provider = FakeTextToSpeechProvider()
    provider.warm()
    cancellation = VoiceCancellation()

    synthesized = provider.synthesize(
        "uma frase.",
        cancellation=cancellation,
        session_id="s",
        turn_id=1,
        generation=1,
    )
    streamed = list(provider.stream(
        "uma frase.",
        cancellation=VoiceCancellation(),
        session_id="s",
        turn_id=1,
        generation=1,
    ))

    assert synthesized == streamed
    assert isinstance(provider, TextToSpeechProvider)
    assert isinstance(FakeAudioOutputProvider(), AudioOutputProvider)


def test_cancel_before_synthesis_prevents_audio_output():
    pipeline, _, output = _pipeline()
    pipeline.begin_turn(session_id="s", turn_id=1, generation=1)
    pipeline.cancel("before_synthesis")

    result = pipeline.synthesize_current("nao deve sair")

    assert result.ok is False
    assert result.cancelled is True
    assert output.accepted == []
    assert output.qsize == 0


def test_cancel_during_synthesis_stops_provider_and_drops_late_audio():
    pipeline, provider, output = _pipeline(delay=0.15)
    pipeline.begin_turn(session_id="s", turn_id=1, generation=1)
    result_holder = []

    worker = threading.Thread(
        target=lambda: result_holder.append(
            pipeline.synthesize_current("primeira. segunda.")
        ),
        daemon=True,
    )
    worker.start()
    assert provider.started.wait(0.5)
    time.sleep(0.02)
    pipeline.cancel("barge_in")
    worker.join(1.0)

    assert not worker.is_alive()
    assert result_holder and result_holder[0].cancelled is True
    accepted_at_cancel = len(output.accepted)
    assert pipeline.accept_chunk(_chunk(session="s", turn=1, generation=1)) is False
    assert len(output.accepted) == accepted_at_cancel


def test_cancel_after_synthesis_is_idempotent_and_blocks_late_chunk():
    pipeline, provider, output = _pipeline()
    result = pipeline.speak("pronto", session_id="s", turn_id=1, generation=1)

    assert result.ok is True
    assert pipeline.cancel("done") is None
    assert pipeline.cancel("done_again") is None
    assert provider.cancel_count >= 3
    assert pipeline.accept_chunk(_chunk(session="s", turn=1, generation=1)) is False
    assert output.qsize == 0


def test_old_session_turn_and_generation_cannot_reach_new_output():
    pipeline, _, output = _pipeline()
    pipeline.begin_turn(session_id="old", turn_id=1, generation=1)
    pipeline.begin_turn(session_id="new", turn_id=2, generation=2)

    assert pipeline.accept_chunk(_chunk(session="old", turn=1, generation=1)) is False
    assert pipeline.accept_chunk(_chunk(session="new", turn=2, generation=2)) is True
    assert [chunk.identity for chunk in output.accepted] == [("new", 2, 2)]


def test_bounded_output_queue_has_explicit_drop_oldest_policy():
    output = FakeAudioOutputProvider(maxsize=2, overflow_policy="drop_oldest")
    output.warm()
    assert output.enqueue(_chunk(sequence=0)) is True
    assert output.enqueue(_chunk(sequence=1)) is True
    assert output.enqueue(_chunk(sequence=2)) is True

    assert output.qsize == 2
    assert [chunk.sequence for chunk in output.queued] == [1, 2]
    assert output.dropped == 1
    assert output.flush() == 2
    assert output.qsize == 0


def test_shutdown_during_synthesis_releases_without_zombie_worker():
    pipeline, provider, output = _pipeline(delay=0.15)
    pipeline.begin_turn(session_id="s", turn_id=1, generation=1)
    result_holder = []
    worker = threading.Thread(
        target=lambda: result_holder.append(pipeline.synthesize_current("longo.")),
        daemon=True,
    )
    worker.start()
    assert provider.started.wait(0.5)
    pipeline.release()
    worker.join(1.0)

    assert not worker.is_alive()
    assert result_holder and result_holder[0].cancelled is True
    assert provider.released is True
    assert output.qsize == 0
    pipeline.release()  # release is idempotent


def test_provider_exception_is_reported_without_reaching_output():
    pipeline, _, output = _pipeline(failure=RuntimeError("provider boom"))

    result = pipeline.speak("falha", session_id="s", turn_id=1, generation=1)

    assert result.ok is False
    assert result.cancelled is False
    assert "provider boom" in result.error
    assert output.accepted == []


def test_voice_service_owns_the_single_injected_tts_output_pipeline():
    service = VoiceService()
    provider = FakeTextToSpeechProvider()
    output = FakeAudioOutputProvider()

    configured = service.configure_tts_pipeline(provider, output)
    result = service.speak_now("resposta do Core")

    assert configured["ok"] is True
    assert configured["owner"] == "VoiceService"
    assert result["ok"] is True
    assert len(output.accepted) == 1
    assert output.accepted[0].session_id == service.status()["session_id"]
    assert service.status()["tts_pipeline"]["configured"] is True

    cancelled = service.cancel_current_operation("test_shutdown")
    assert cancelled["ok"] is True
    released = service.release_tts_pipeline()
    assert released == {"ok": True, "released": True}
    assert service.get_tts_pipeline() is None


@pytest.mark.parametrize("method", ["warm", "cancel", "release"])
def test_fake_provider_lifecycle_methods_are_safe(method):
    provider = FakeTextToSpeechProvider()
    if method == "warm":
        provider.warm()
        assert provider.warm_count == 1
    elif method == "cancel":
        provider.cancel()
        provider.cancel()
        assert provider.cancel_count == 2
    else:
        provider.release()
        provider.release()
        assert provider.release_count == 2
