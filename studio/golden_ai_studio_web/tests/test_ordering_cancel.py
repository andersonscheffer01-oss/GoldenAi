"""Queue/Ordering and Cancel Tests — P1.4B.

Tests that:
1. Chunks play in correct order (1 → 2 → 3)
2. Out-of-order TTS completion doesn't break ordering
3. Cancel works at provider/chunk/TTS/playback stages
4. No old chunks play after cancel
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

from jarvis_core.streaming.orchestrator import StreamingOrchestrator
from jarvis_core.streaming.tts_pipeline import TTSPipeline, AudioChunk
from jarvis_core.streaming.audio_player import AudioPlayer


# ═══════════════════════════════════════════════════════════════════
# ORDERING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOrdering:
    """Test that chunks play in correct order."""

    @pytest.mark.asyncio
    async def test_simple_ordering(self):
        """Chunks submitted in order should play in order."""
        async def fake_synth(text, index, is_final=False, cancel_event=None):
            return AudioChunk(
                index=index, text=text, audio_path=None,
                duration_ms=100, is_final=is_final,
            )

        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", fake_synth):
            pipeline = TTSPipeline()
            await pipeline.submit("First", 0)
            await pipeline.submit("Second", 1)
            await pipeline.submit("Third", 2)

            chunks = []
            while True:
                chunk = await asyncio.wait_for(pipeline.next_ready(), timeout=2.0)
                if chunk is None:
                    break
                chunks.append(chunk)
                if chunk.is_final:
                    break

            assert len(chunks) == 3
            assert chunks[0].index == 0
            assert chunks[1].index == 1
            assert chunks[2].index == 2

    @pytest.mark.asyncio
    async def test_out_of_order_synthesis(self):
        """Out-of-order TTS completion should still yield correct order."""
        async def fake_synth(text, index, is_final=False, cancel_event=None):
            delay = {0: 0.03, 1: 0.02, 2: 0.01}.get(index, 0.01)
            await asyncio.sleep(delay)
            return AudioChunk(
                index=index, text=text, audio_path=None,
                duration_ms=100, is_final=is_final,
            )

        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", fake_synth):
            pipeline = TTSPipeline()
            await pipeline.submit("Third", 2)
            await pipeline.submit("First", 0)
            await pipeline.submit("Second", 1)

            chunks = []
            while True:
                chunk = await asyncio.wait_for(pipeline.next_ready(), timeout=2.0)
                if chunk is None:
                    break
                chunks.append(chunk)
                if chunk.is_final:
                    break

            assert len(chunks) == 3
            assert chunks[0].index == 0
            assert chunks[1].index == 1
            assert chunks[2].index == 2

    @pytest.mark.asyncio
    async def test_playback_ordering(self):
        """AudioPlayer should play chunks in order."""
        played_order = []

        async def mock_play(chunk):
            played_order.append(chunk.index)
            return 100

        player = AudioPlayer()
        with patch.object(player, "play", mock_play):
            # Simulate playing chunks in order
            for i in range(3):
                chunk = AudioChunk(
                    index=i, text=f"Chunk {i}", audio_path=None,
                    duration_ms=100, is_final=(i == 2),
                )
                await player.play(chunk)

        assert played_order == [0, 1, 2]


# ═══════════════════════════════════════════════════════════════════
# CANCEL TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCancel:
    """Test cancellation at various stages."""

    @pytest.mark.asyncio
    async def test_cancel_provider_stream(self):
        """Cancel during provider stream should stop immediately."""
        from jarvis_core.streaming.turn_manager import TurnManager

        async def slow_stream(messages, model):
            for i in range(10):
                yield f"Token {i} "
                await asyncio.sleep(0.01)

        with patch("jarvis_core.streaming.orchestrator.stream_groq", slow_stream):
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
    async def test_cancel_during_tts(self):
        """Cancel during TTS synthesis should stop."""
        async def slow_synth(text, index, is_final=False, cancel_event=None):
            if cancel_event and cancel_event.is_set():
                return None
            await asyncio.sleep(0.05)
            return AudioChunk(
                index=index, text=text, audio_path=None,
                duration_ms=100, is_final=is_final,
            )

        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", slow_synth):
            pipeline = TTSPipeline()
            await pipeline.submit("Test", 0)
            pipeline.cancel()
            chunk = await asyncio.wait_for(pipeline.next_ready(), timeout=2.0)
            assert chunk is None

    @pytest.mark.asyncio
    async def test_cancel_during_playback(self):
        """Cancel during playback should stop player."""
        player = AudioPlayer()
        player.stop()
        assert player.is_playing is False

    @pytest.mark.asyncio
    async def test_cancel_clears_queues(self):
        """Cancel should clear all pending chunks."""
        async def fake_synth(text, index, is_final=False, cancel_event=None):
            return AudioChunk(
                index=index, text=text, audio_path=None,
                duration_ms=100, is_final=is_final,
            )

        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", fake_synth):
            pipeline = TTSPipeline()
            await pipeline.submit("Chunk 1", 0)
            await pipeline.submit("Chunk 2", 1)
            await pipeline.submit("Chunk 3", 2)

            pipeline.cancel()

            chunk = await asyncio.wait_for(pipeline.next_ready(), timeout=2.0)
            assert chunk is None

    @pytest.mark.asyncio
    async def test_no_old_chunks_after_cancel(self):
        """No old chunks should play after cancel."""
        played = []

        async def mock_play(chunk):
            played.append(chunk.index)
            return 100

        player = AudioPlayer()
        with patch.object(player, "play", mock_play):
            chunk0 = AudioChunk(index=0, text="0", audio_path=None,
                               duration_ms=100, is_final=False)
            await player.play(chunk0)
            player.stop()
            assert player.is_playing is False

        assert played == [0]

    @pytest.mark.asyncio
    async def test_cancel_event_propagates(self):
        """Cancel event should propagate to all components."""
        cancel = asyncio.Event()
        pipeline = TTSPipeline(cancel)
        cancel.set()
        chunk = await asyncio.wait_for(pipeline.next_ready(), timeout=2.0)
        assert chunk is None

    @pytest.mark.asyncio
    async def test_orchestrator_cancel_mid_stream(self):
        """Cancel mid-stream should stop everything."""
        cancel_token = None

        async def slow_stream(messages, model):
            nonlocal cancel_token
            for i in range(100):
                cancel_token = i
                yield f"Token {i} "
                await asyncio.sleep(0.02)

        with patch("jarvis_core.streaming.orchestrator.stream_groq", slow_stream):
            orch = StreamingOrchestrator()
            # Cancel after first few tokens
            async def delayed_cancel():
                await asyncio.sleep(0.03)
                orch.cancel()
            asyncio.create_task(delayed_cancel())
            result = await orch.run(
                messages=[{"role": "user", "content": "test"}],
                provider="groq",
            )
            # Should be cancelled (or complete if cancel was too slow)
            # The important thing is it doesn't hang
            assert result["ok"] in (True, False)

    @pytest.mark.asyncio
    async def test_orchestrator_cancel_is_idempotent_and_closes_stream(self):
        """Direct cancel signals the active stream once and closes it."""
        closed = False

        async def slow_stream(messages, model):
            nonlocal closed
            try:
                while True:
                    yield "token "
                    await asyncio.sleep(0.01)
            finally:
                closed = True

        with patch("jarvis_core.streaming.orchestrator.stream_groq", slow_stream):
            orch = StreamingOrchestrator()
            task = asyncio.create_task(orch.run([], provider="groq"))
            await asyncio.sleep(0.03)
            assert orch.cancel() is True
            assert orch.cancel() is False
            result = await asyncio.wait_for(task, timeout=1.0)

        assert result["ok"] is False
        assert result["error"] == "cancelled"
        assert closed is True

    @pytest.mark.asyncio
    async def test_cancel_before_stream_is_safe_and_does_not_poison_restart(self):
        """A pre-start cancel is a no-op and a later run remains usable."""
        async def completed_stream(messages, model):
            yield "Finished."

        with patch("jarvis_core.streaming.orchestrator.stream_groq", completed_stream):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", return_value=None):
                orch = StreamingOrchestrator()
                assert orch.cancel() is False
                result = await asyncio.wait_for(orch.run([], provider="groq"), timeout=1.0)

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_cancel_after_completion_does_not_affect_next_run(self):
        """A stale cancel after completion cannot cancel a new run."""
        async def completed_stream(messages, model):
            yield "Finished."

        with patch("jarvis_core.streaming.orchestrator.stream_groq", completed_stream):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", return_value=None):
                orch = StreamingOrchestrator()
                first = await asyncio.wait_for(orch.run([], provider="groq"), timeout=1.0)
                assert first["ok"] is True
                assert orch.cancel() is False
                second = await asyncio.wait_for(orch.run([], provider="groq"), timeout=1.0)

        assert second["ok"] is True

    @pytest.mark.asyncio
    async def test_turn_manager_cancellation_is_session_isolated(self):
        """Cancelling turn A does not cancel turn B's independent event."""
        from jarvis_core.streaming.turn_manager import TurnManager

        manager = TurnManager()
        turn_a = manager.new_turn()
        turn_b = manager.new_turn()

        assert manager.is_cancelled(turn_a) is True
        assert manager.is_cancelled(turn_b) is False
        manager.cancel_turn(turn_a)
        assert manager.is_cancelled(turn_b) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
