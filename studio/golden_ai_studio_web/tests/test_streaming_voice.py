"""Tests for Streaming Voice Pipeline — P1.4B.

Tests sentence chunker, TTS pipeline, and orchestrator.
No real microphone required — uses mock providers.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.streaming import is_streaming_enabled
from jarvis_core.streaming.sentence_chunker import Chunk, SentenceChunker
from jarvis_core.streaming.tts_pipeline import AudioChunk, TTSPipeline, synthesize_sentence
from jarvis_core.streaming.audio_player import AudioPlayer
from jarvis_core.streaming.orchestrator import StreamingOrchestrator, StreamingMetrics


# ═══════════════════════════════════════════════════════════════════
# FEATURE FLAG
# ═══════════════════════════════════════════════════════════════════

class TestFeatureFlag:
    def test_default_off(self):
        os.environ.pop("JARVIS_STREAMING_VOICE", None)
        assert is_streaming_enabled() is False

    def test_enabled(self):
        os.environ["JARVIS_STREAMING_VOICE"] = "1"
        assert is_streaming_enabled() is True
        os.environ.pop("JARVIS_STREAMING_VOICE", None)

    def test_disabled_explicit(self):
        os.environ["JARVIS_STREAMING_VOICE"] = "0"
        assert is_streaming_enabled() is False
        os.environ.pop("JARVIS_STREAMING_VOICE", None)


# ═══════════════════════════════════════════════════════════════════
# SENTENCE CHUNKER
# ═══════════════════════════════════════════════════════════════════

class TestSentenceChunker:
    def test_no_chunk_below_min(self):
        c = SentenceChunker(min_chars=5)
        chunks = c.feed("Hello")
        assert len(chunks) == 0

    def test_chunk_at_sentence_terminator(self):
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Hello world.")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world."

    def test_chunk_at_question_mark(self):
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Como vai?")
        assert len(chunks) == 1
        assert chunks[0].text == "Como vai?"

    def test_chunk_at_exclamation(self):
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Otimo!")
        assert len(chunks) == 1
        assert chunks[0].text == "Otimo!"

    def test_multi_token_assembly(self):
        c = SentenceChunker(min_chars=2)
        c.feed("Hello ")
        c.feed("world")
        chunks = c.feed(".")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world."

    def test_multiple_sentences(self):
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("First sentence. Second sentence.")
        # Should emit at least one chunk
        assert len(chunks) >= 1

    def test_flush_remaining(self):
        c = SentenceChunker(min_chars=2)
        c.feed("No terminator here")
        chunk = c.flush()
        assert chunk is not None
        assert chunk.text == "No terminator here"
        assert chunk.is_final is True

    def test_flush_empty(self):
        c = SentenceChunker(min_chars=2)
        chunk = c.flush()
        assert chunk is None

    def test_chunk_index_increments(self):
        c = SentenceChunker(min_chars=2)
        c.feed("First. ")
        c.feed("Second.")
        c.feed(" ")
        c.feed("Third.")
        all_chunks = []
        # Feed trailing space to trigger second chunk
        for text in ["First. ", "Second.", " ", "Third."]:
            all_chunks.extend(c.feed(text))
        remaining = c.flush()
        if remaining:
            all_chunks.append(remaining)
        indices = [ch.index for ch in all_chunks]
        assert indices == sorted(indices)

    def test_max_chars_force_emit(self):
        c = SentenceChunker(min_chars=2, max_chars=20)
        chunks = c.feed("This is a long text without punctuation")
        assert len(chunks) == 1
        assert "long text" in chunks[0].text

    def test_url_not_broken(self):
        c = SentenceChunker(min_chars=2)
        c.feed("Visit https://example.com for info")
        chunks = c.flush()
        assert chunks is not None
        assert "https://example.com" in chunks.text

    def test_abbreviation_not_terminated(self):
        c = SentenceChunker(min_chars=2)
        chunks = c.feed("Dr. Smith")
        assert len(chunks) == 0  # Should not emit on "Dr."

    def test_pending_property(self):
        c = SentenceChunker(min_chars=10)
        c.feed("Some text")
        assert c.pending == "Some text"

    def test_chunk_count(self):
        c = SentenceChunker(min_chars=2)
        c.feed("One. ")
        c.feed("Two.")
        c.feed(" ")
        chunks = []
        for t in ["One. ", "Two.", " "]:
            chunks.extend(c.feed(t))
        remaining = c.flush()
        if remaining:
            chunks.append(remaining)
        assert c.chunk_count >= 2


# ═══════════════════════════════════════════════════════════════════
# TTS PIPELINE
# ═══════════════════════════════════════════════════════════════════

class TestTTSPipeline:
    @pytest.mark.asyncio
    async def test_synthesize_creates_file(self):
        """Test that synthesize_sentence creates an audio file."""
        with patch("jarvis_core.streaming.tts_pipeline.edge_tts.Communicate") as MockComm:
            instance = MockComm.return_value

            async def mock_stream():
                yield {"type": "audio", "data": b"fake_audio_data"}

            instance.stream = mock_stream

            result = await synthesize_sentence("Teste", 0)
            assert result is not None
            assert result.text == "Teste"
            assert result.index == 0
            # Cleanup
            if result.audio_path:
                os.unlink(result.audio_path)

    @pytest.mark.asyncio
    async def test_synthesize_cancel_returns_none(self):
        """Test that cancellation returns None."""
        cancel = asyncio.Event()
        cancel.set()

        result = await synthesize_sentence("Teste", 0, cancel_event=cancel)
        assert result is None

    @pytest.mark.asyncio
    async def test_pipeline_submit_and_next(self):
        """Test TTS pipeline submit and next_ready."""
        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence") as mock_synth:
            mock_synth.return_value = AudioChunk(
                index=0, text="Test", audio_path=None,
                duration_ms=100, is_final=False,
            )

            pipeline = TTSPipeline()
            await pipeline.submit("Test", 0)
            chunk = await pipeline.next_ready()
            assert chunk is not None
            assert chunk.index == 0

    @pytest.mark.asyncio
    async def test_pipeline_ordering(self):
        """Test that chunks come out in order."""
        results = {}
        call_order = []

        async def fake_synth(text, index, is_final=False, cancel_event=None):
            call_order.append(index)
            # Simulate different synthesis times
            await asyncio.sleep(0.01 * (3 - index))
            return AudioChunk(
                index=index, text=text, audio_path=None,
                duration_ms=100, is_final=is_final,
            )

        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", fake_synth):
            pipeline = TTSPipeline()
            # Submit out of order
            await pipeline.submit("Third", 2)
            await pipeline.submit("First", 0)
            await pipeline.submit("Second", 1)

            # Should come out in order 0, 1, 2
            for expected_index in range(3):
                chunk = await pipeline.next_ready()
                assert chunk is not None
                assert chunk.index == expected_index

    @pytest.mark.asyncio
    async def test_pipeline_cancel(self):
        """Test pipeline cancellation."""
        pipeline = TTSPipeline()
        pipeline.cancel()
        chunk = await pipeline.next_ready()
        assert chunk is None


# ═══════════════════════════════════════════════════════════════════
# AUDIO PLAYER
# ═══════════════════════════════════════════════════════════════════

class TestAudioPlayer:
    def test_play_missing_file(self):
        """Test playing non-existent file returns 0."""
        player = AudioPlayer()
        chunk = AudioChunk(
            index=0, text="test", audio_path="/nonexistent.mp3",
            duration_ms=100, is_final=False,
        )
        duration = asyncio.run(player.play(chunk))
        assert duration == 0

    def test_stop(self):
        """Test stop clears state."""
        player = AudioPlayer()
        player.stop()
        assert player.is_playing is False


# ═══════════════════════════════════════════════════════════════════
# STREAMING ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════

class TestStreamingOrchestrator:
    @pytest.mark.asyncio
    async def test_orchestrator_cancellation(self):
        """Test orchestrator can be cancelled via TurnManager."""
        from jarvis_core.streaming.turn_manager import TurnManager
        tm = TurnManager()
        turn_id = tm.new_turn()
        tm.cancel_current()
        orch = StreamingOrchestrator()
        result = await orch.run(
            messages=[{"role": "user", "content": "test"}],
            provider="groq",
            turn_id=turn_id,
            turn_manager=tm,
        )
        assert result["ok"] is False
        assert result["error"] == "cancelled"

    @pytest.mark.asyncio
    async def test_orchestrator_with_mock_stream(self):
        """Test orchestrator with mocked provider stream."""
        async def mock_stream(messages, model):
            yield "Hello "
            yield "world."

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence") as mock_tts:
                mock_tts.return_value = AudioChunk(
                    index=0, text="Hello world.", audio_path=None,
                    duration_ms=100, is_final=True,
                )
                with patch.object(AudioPlayer, "play", return_value=100):
                    orch = StreamingOrchestrator()
                    result = await orch.run(
                        messages=[{"role": "user", "content": "test"}],
                        provider="groq",
                    )
                    assert result["ok"] is True
                    assert "Hello world." in result["response"]

    @pytest.mark.asyncio
    async def test_metrics_collected(self):
        """Test that metrics are properly collected."""
        async def mock_stream(messages, model):
            yield "Test response."

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence") as mock_tts:
                mock_tts.return_value = AudioChunk(
                    index=0, text="Test response.", audio_path=None,
                    duration_ms=100, is_final=True,
                )
                with patch.object(AudioPlayer, "play", return_value=100):
                    orch = StreamingOrchestrator()
                    result = await orch.run(
                        messages=[{"role": "user", "content": "test"}],
                        provider="groq",
                    )
                    metrics = result["metrics"]
                    assert metrics.provider_ttft_ms > 0
                    assert metrics.total_response_ms > 0
                    assert metrics.chunks_emitted >= 1


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_feature_flag_blocks_streaming(self):
        """Test that streaming is blocked when flag is off."""
        os.environ.pop("JARVIS_STREAMING_VOICE", None)
        from jarvis_core.streaming.integration import should_use_streaming
        assert should_use_streaming(None, "test") is False

    def test_metrics_collector(self):
        """Test metrics collector."""
        from jarvis_core.streaming.integration import StreamingMetricsCollector
        collector = StreamingMetricsCollector()
        collector.record_legacy(1000)
        collector.record_streaming(StreamingMetrics(end_speech_to_first_audio_ms=500))
        report = collector.report()
        assert report["latency_reduction_ms"] == 500
        assert report["latency_reduction_pct"] == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
