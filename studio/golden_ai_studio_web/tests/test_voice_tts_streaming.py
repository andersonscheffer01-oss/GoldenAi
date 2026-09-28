"""Offline regression tests for bounded provider-neutral streaming TTS."""

from __future__ import annotations

import time

from jarvis_core.voice_service import VoiceService
from jarvis_core.voice_tts import (
    FakeAudioOutputProvider,
    FakeTextToSpeechProvider,
    StreamingTTSOrchestrator,
    StreamingTextSegmenter,
    VoiceAudioPipeline,
)


def _segments(text: str, split_points: list[int]) -> list[str]:
    segmenter = StreamingTextSegmenter()
    result = []
    start = 0
    for end in split_points:
        result.extend(segment.text for segment in segmenter.feed(text[start:end]))
        start = end
    result.extend(segment.text for segment in segmenter.feed(text[start:]))
    trailing = segmenter.flush()
    if trailing is not None:
        result.append(trailing.text)
    return result


def _orchestrator(*, provider=None, output=None, max_pending_segments=4):
    provider = provider or FakeTextToSpeechProvider()
    output = output or FakeAudioOutputProvider(maxsize=64)
    pipeline = VoiceAudioPipeline(provider, output)
    return StreamingTTSOrchestrator(
        pipeline,
        max_pending_segments=max_pending_segments,
    ), provider, output


def test_arbitrary_chunk_boundaries_reconstruct_equivalent_pt_br_segments():
    text = (
        "Claro. Encontrei as informações que você pediu. "
        "Posso abrir o último arquivo amanhã."
    )
    expected = _segments(text, [])
    for split in range(1, len(text)):
        assert _segments(text, [split]) == expected


def test_segmenter_preserves_abbreviations_numbers_urls_and_markdown():
    segmenter = StreamingTextSegmenter()
    text = (
        "Dr. Silva confirmou o valor 3.14 e R$ 1.250,50. "
        "Acesse https://example.com/docs. **Próximo passo.**"
    )
    segments = [segment.text for segment in segmenter.feed(text)]
    trailing = segmenter.flush()
    if trailing is not None:
        segments.append(trailing.text)
    joined = " ".join(segments)
    assert "Dr. Silva" in joined
    assert "3.14" in joined
    assert "R$ 1.250,50" in joined
    assert "https://example.com/docs" in joined
    assert "**" not in joined
    assert "Próximo passo." in joined


def test_final_flush_is_idempotent_and_empty_chunks_create_no_jobs():
    segmenter = StreamingTextSegmenter()
    assert segmenter.feed("") == []
    assert segmenter.feed("   \n\t") == []
    assert segmenter.flush() is None
    assert segmenter.flush() is None


def test_forced_flush_bounds_pending_text_and_preserves_content():
    segmenter = StreamingTextSegmenter(max_pending_chars=48)
    text = "palavra " * 30
    emitted = segmenter.feed(text)
    trailing = segmenter.flush()
    if trailing is not None:
        emitted.append(trailing)
    assert emitted
    assert all(len(segment.text) <= 48 for segment in emitted[:-1])
    assert " ".join(segment.text for segment in emitted).split() == text.split()


def test_streaming_tts_starts_before_final_flush_and_preserves_order():
    orchestrator, provider, output = _orchestrator(max_pending_segments=2)
    identity = orchestrator.start_stream(
        session_id="session-a", turn_id=3, generation=10
    )
    assert identity == ("session-a", 3, 10)
    submitted = orchestrator.feed_text("Claro. Encontrei os arquivos que você pediu. ")
    assert submitted == 2
    assert provider.started.wait(0.5)
    result = orchestrator.finish_stream()
    assert result.ok is True
    assert result.final_flushed is True
    assert result.completed_segments == 2
    assert [chunk.metadata["text"] for chunk in output.queued] == [
        "Claro.",
        "Encontrei os arquivos que você pediu.",
    ]
    assert orchestrator.finish_stream() == result
    orchestrator.close()


def test_fast_producer_is_backpressured_by_bounded_work_queue():
    provider = FakeTextToSpeechProvider(chunk_delay=0.01)
    orchestrator, _, output = _orchestrator(
        provider=provider, max_pending_segments=2
    )
    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=1)
    orchestrator.feed_text(" ".join(f"Frase {index}." for index in range(12)))
    result = orchestrator.finish_stream()
    diagnostics = orchestrator.diagnostics()
    assert result.ok is True
    assert diagnostics["queue_maxsize"] == 2
    assert diagnostics["max_queue_depth"] <= 2
    assert len(output.queued) == 12
    orchestrator.close()


def test_duplicate_chunk_callback_is_deduplicated_by_source_id():
    orchestrator, provider, output = _orchestrator()
    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=1)
    assert orchestrator.feed_text("Resposta final.", chunk_id="chunk-1") == 1
    assert orchestrator.feed_text("Resposta final.", chunk_id="chunk-1") == 0
    result = orchestrator.finish_stream()
    assert result.ok is True
    assert len(provider.calls) == 1
    assert len(output.queued) == 1
    orchestrator.close()


def test_stale_generation_text_and_late_audio_cannot_enter_new_output_queue():
    provider = FakeTextToSpeechProvider(chunk_delay=0.1)
    orchestrator, _, output = _orchestrator(provider=provider)
    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=10)
    orchestrator.feed_text("Resposta antiga.")
    assert provider.started.wait(0.5)

    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=11)
    assert orchestrator.feed_text(
        "Texto antigo.", session_id="session-a", turn_id=1, generation=10
    ) == 0
    assert orchestrator.feed_text(
        "Resposta nova.", session_id="session-a", turn_id=1, generation=11
    ) == 1
    result = orchestrator.finish_stream(
        session_id="session-a", turn_id=1, generation=11
    )
    assert result.ok is True
    assert result.stale_rejections == 1
    assert all(chunk.generation == 11 for chunk in output.queued)
    orchestrator.close()


def test_session_restart_rejects_old_identity_and_keeps_new_session():
    orchestrator, _, output = _orchestrator()
    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=1)
    orchestrator.feed_text("Sessão antiga.")
    orchestrator.start_stream(session_id="session-b", turn_id=2, generation=1)
    assert orchestrator.feed_text(
        "Texto antigo.", session_id="session-a", turn_id=1, generation=1
    ) == 0
    orchestrator.feed_text(
        "Sessão nova.", session_id="session-b", turn_id=2, generation=1
    )
    result = orchestrator.finish_stream(
        session_id="session-b", turn_id=2, generation=1
    )
    assert result.ok is True
    assert output.queued
    assert all(chunk.session_id == "session-b" for chunk in output.queued)
    orchestrator.close()


def test_provider_error_is_bounded_and_does_not_deadlock():
    provider = FakeTextToSpeechProvider(failure=RuntimeError("tts failure"))
    orchestrator, _, output = _orchestrator(provider=provider)
    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=1)
    orchestrator.feed_text("Falha controlada.")
    started = time.monotonic()
    result = orchestrator.finish_stream()
    assert time.monotonic() - started < 1.0
    assert result.ok is False
    assert "tts failure" in result.error
    assert output.queued == ()
    assert orchestrator.diagnostics()["worker_alive"] is False


def test_cancel_and_session_stop_flush_pending_work_without_zombie_worker():
    provider = FakeTextToSpeechProvider(chunk_delay=0.1)
    orchestrator, _, output = _orchestrator(provider=provider)
    orchestrator.start_stream(session_id="session-a", turn_id=1, generation=1)
    orchestrator.feed_text("Primeira. Segunda. Terceira.")
    assert provider.started.wait(0.5)
    result = orchestrator.cancel("session_stop")
    diagnostics = orchestrator.diagnostics()
    assert result.cancelled is True
    assert diagnostics["worker_alive"] is False
    assert diagnostics["queue_depth"] == 0
    assert output.queued == ()


def test_voice_service_remains_owner_of_streaming_tts_pipeline():
    service = VoiceService()
    provider = FakeTextToSpeechProvider()
    output = FakeAudioOutputProvider(maxsize=64)
    configured = service.configure_tts_pipeline(provider, output)
    assert configured["owner"] == "VoiceService"
    started = service.start_tts_stream()
    assert started["ok"] is True
    identity = started["identity"]
    service.feed_tts_stream(
        "Resposta progressiva.",
        session_id=identity[0],
        turn_id=identity[1],
        generation=identity[2],
    )
    finished = service.finish_tts_stream(
        session_id=identity[0],
        turn_id=identity[1],
        generation=identity[2],
    )
    assert finished["ok"] is True
    assert service.status()["tts_pipeline"]["streaming"]["worker_alive"] is False
    service.release_tts_pipeline()
