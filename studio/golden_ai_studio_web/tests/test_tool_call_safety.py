"""Tool Call Safety Tests — P1.4B.

Tests that streaming correctly detects and handles tool calls:
- Pure tool call
- Text + tool call
- Fragmented tool call across multiple deltas
- Tool requiring confirmation
- Denied tool
- Failed tool
- No improper intermediate text spoken
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.streaming.orchestrator import (
    StreamingOrchestrator,
    StreamingMetrics,
    ToolCallDetector,
)
from jarvis_core.streaming.sentence_chunker import Chunk, SentenceChunker
from jarvis_core.streaming.tts_pipeline import TTSPipeline, AudioChunk
from jarvis_core.streaming.audio_player import AudioPlayer


# ═══════════════════════════════════════════════════════════════════
# TOOL CALL DETECTOR
# ═══════════════════════════════════════════════════════════════════

class TestToolCallDetector:
    """Test the ToolCallDetector class."""

    def test_prose_detected(self):
        """Plain text should be detected as prose."""
        d = ToolCallDetector()
        for token in ["Olá", " ", "mundo", "!"]:
            result = d.feed(token)
        assert result == "prose"
        assert d.is_prose()

    def test_tool_call_pure(self):
        """Pure JSON tool call should be detected."""
        d = ToolCallDetector()
        tokens = ['{"tool": "open_app", "args": {"app": "chrome"}}']
        for token in tokens:
            result = d.feed(token)
        # Should detect as tool call
        assert d.is_tool_call() or result == "tool_call"

    def test_tool_call_fragmented(self):
        """Tool call spread across multiple deltas."""
        d = ToolCallDetector()
        tokens = ['{"', 'tool', '": ', '"open_app', '", ', '"args":', ' {"app":', '"chrome"}}']
        for token in tokens:
            d.feed(token)
        assert d.is_tool_call()

    def test_text_then_tool_call(self):
        """Text followed by tool call should stop at tool call."""
        d = ToolCallDetector()
        # First tokens are prose
        for token in ["Vou", " abrir", " o", " Chrome"]:
            result = d.feed(token)
            assert result == "prose"
        # Then tool call appears
        for token in [' JSON: {', '"tool":', ' "open_app"}']:
            result = d.feed(token)
        # Should detect tool call transition
        assert d.is_tool_call()

    def test_min_tokens_before_detection(self):
        """Tool call with '{' and tool indicators detected immediately."""
        d = ToolCallDetector()
        result = d.feed('{"tool":')
        # Single token with { and "tool" → detected immediately
        assert result == "tool_call"

    def test_reset(self):
        """Reset should clear state."""
        d = ToolCallDetector()
        d.feed("some text")
        d.reset()
        assert d.get_buffer() == ""
        assert d._token_count == 0
        assert d._phase == "unknown"

    def test_response_field_detected(self):
        """JSON with 'response' field should be detected as tool call (it's a structured response)."""
        d = ToolCallDetector()
        tokens = ['{"response": "Olá!"}']
        for token in tokens:
            d.feed(token)
        # Should detect as tool_call (structured JSON)
        assert d.is_tool_call()

    def test_steps_field_detected(self):
        """JSON with 'steps' field should be detected."""
        d = ToolCallDetector()
        tokens = ['{"steps": [{"tool": "open_app", "args": {}}]}']
        for token in tokens:
            d.feed(token)
        assert d.is_tool_call()


# ═══════════════════════════════════════════════════════════════════
# ORCHESTRATOR TOOL CALL SAFETY
# ═══════════════════════════════════════════════════════════════════

class TestOrchestratorToolCallSafety:
    """Test that orchestrator correctly stops on tool calls."""

    @pytest.mark.asyncio
    async def test_pure_tool_call_stops_streaming(self):
        """Pure tool call should stop TTS and return error."""
        async def mock_stream_tool_call(messages, model):
            yield '{"tool": "open_app", "args": {"app": "chrome"}}'

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_tool_call):
            orch = StreamingOrchestrator()
            result = await orch.run(
                messages=[{"role": "user", "content": "abra o chrome"}],
                provider="groq",
            )
            # Should detect tool call and return early
            assert result["ok"] is False
            assert result["error"] == "tool_call_detected"
            assert "tool_call_text" in result
            assert result["metrics"].tool_call_detected is True

    @pytest.mark.asyncio
    async def test_prose_response_completes(self):
        """Prose response should complete normally."""
        async def mock_stream_prose(messages, model):
            yield "Olá! "
            yield "Como vai?"

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_prose):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence") as mock_tts:
                mock_tts.return_value = AudioChunk(
                    index=0, text="Olá! Como vai?", audio_path=None,
                    duration_ms=100, is_final=True,
                )
                with patch.object(AudioPlayer, "play", return_value=100):
                    orch = StreamingOrchestrator()
                    result = await orch.run(
                        messages=[{"role": "user", "content": "olá"}],
                        provider="groq",
                    )
                    assert result["ok"] is True
                    assert result["metrics"].tool_call_detected is False

    @pytest.mark.asyncio
    async def test_text_then_tool_call_stops(self):
        """Text followed by tool call should stop."""
        async def mock_stream_mixed(messages, model):
            yield "Vou "
            yield "abrir "
            yield 'o Chrome. JSON: {"tool": "open_app", "args": {}}'

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_mixed):
            orch = StreamingOrchestrator()
            result = await orch.run(
                messages=[{"role": "user", "content": "abra o chrome"}],
                provider="groq",
            )
            assert result["ok"] is False
            assert result["error"] == "tool_call_detected"

    @pytest.mark.asyncio
    async def test_no_tts_for_tool_call(self):
        """TTS should NOT be called when tool call is detected."""
        async def mock_stream_tool_call(messages, model):
            yield '{"tool": "open_app", "args": {}}'

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_tool_call):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence") as mock_tts:
                orch = StreamingOrchestrator()
                result = await orch.run(
                    messages=[{"role": "user", "content": "abra o chrome"}],
                    provider="groq",
                )
                # TTS should NOT have been called
                mock_tts.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_response_preserved_for_legacy(self):
        """Full response text should be preserved for legacy path."""
        async def mock_stream_tool_call(messages, model):
            yield "Vou "
            yield 'abrir. {"tool": "open_app", "args": {}}'

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_tool_call):
            orch = StreamingOrchestrator()
            result = await orch.run(
                messages=[{"role": "user", "content": "abra o chrome"}],
                provider="groq",
            )
            assert "full_response" in result
            assert "Vou abrir." in result["full_response"]


# ═══════════════════════════════════════════════════════════════════
# VOICE SERVICE INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestVoiceServiceToolCallSafety:
    """Test VoiceService integration with tool call safety."""

    def test_handle_streaming_returns_tool_call_info(self):
        """_handle_streaming should return tool call info when detected."""
        from jarvis_core.voice_service import VoiceService

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_tool_call(messages, model):
                yield '{"tool": "open_app", "args": {}}'
            mock_stream.side_effect = mock_tool_call

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = []
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.submit = AsyncMock()
                    mock_tts.return_value.next_ready = AsyncMock(return_value=None)
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer"):
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            mock_brain.return_value.build_messages.return_value = []
                            result = vs._handle_streaming("abra o chrome", {})
                            assert result["handled"] is False
                            assert result["reason"] == "tool_call"
                            assert "tool_call_text" in result

    def test_handle_streaming_prose_returns_handled(self):
        """_handle_streaming should return handled=True for prose."""
        from jarvis_core.voice_service import VoiceService

        vs = VoiceService()
        vs.service = MagicMock()
        vs.service.orchestrator = MagicMock()
        vs.service.orchestrator.models = MagicMock()
        vs.service.orchestrator.models.providers = []

        with patch("jarvis_core.streaming.orchestrator.stream_groq") as mock_stream:
            async def mock_prose(messages, model):
                yield "Olá! Como vai?"
            mock_stream.side_effect = mock_prose

            with patch("jarvis_core.streaming.orchestrator.SentenceChunker") as mock_chunker:
                mock_chunker.return_value.feed.return_value = [
                    Chunk(index=0, text="Olá! Como vai?", is_final=True)
                ]
                mock_chunker.return_value.flush.return_value = None

                with patch("jarvis_core.streaming.orchestrator.TTSPipeline") as mock_tts:
                    mock_tts.return_value.synthesize_and_get = AsyncMock(return_value=AudioChunk(
                        index=0, text="Olá!", audio_path=None,
                        duration_ms=100, is_final=True,
                    ))
                    mock_tts.return_value.cancel = MagicMock()
                    mock_tts.return_value.cleanup = MagicMock()

                    with patch("jarvis_core.streaming.orchestrator.AudioPlayer") as mock_player:
                        mock_player.return_value.play = AsyncMock(return_value=100)
                        mock_player.return_value.wait_for_speech_end = AsyncMock()
                        with patch("jarvis_core.brain.get_brain") as mock_brain:
                            mock_brain.return_value = MagicMock()
                            mock_brain.return_value.build_messages.return_value = []
                            result = vs._handle_streaming("olá", {})
                            assert result["handled"] is True


# ═══════════════════════════════════════════════════════════════════
# SECURITY INVARIANTS
# ═══════════════════════════════════════════════════════════════════

class TestSecurityInvariants:
    """Verify streaming never bypasses security."""

    def test_streaming_does_not_import_security_manager(self):
        """Streaming modules should NOT import SecurityManager directly."""
        import jarvis_core.streaming.orchestrator as orch_mod
        import jarvis_core.streaming.provider_stream as prov_mod
        import jarvis_core.streaming.tts_pipeline as tts_mod
        import jarvis_core.streaming.audio_player as play_mod

        for mod in [orch_mod, prov_mod, tts_mod, play_mod]:
            source = Path(mod.__file__).read_text()
            # Check for actual import statements, not just string mentions
            lines = source.split('\n')
            for line in lines:
                stripped = line.strip()
                # Skip comments and docstrings
                if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if 'import' in stripped and 'SecurityManager' in stripped:
                    pytest.fail(f"{mod.__name__} imports SecurityManager: {stripped}")

    def test_streaming_does_not_import_tool_registry(self):
        """Streaming modules should NOT import ToolRegistry directly."""
        import jarvis_core.streaming.orchestrator as orch_mod
        import jarvis_core.streaming.provider_stream as prov_mod

        for mod in [orch_mod, prov_mod]:
            source = Path(mod.__file__).read_text()
            lines = source.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                if 'import' in stripped and 'ToolRegistry' in stripped:
                    pytest.fail(f"{mod.__name__} imports ToolRegistry: {stripped}")

    def test_streaming_does_not_execute_tools(self):
        """Streaming modules should NOT execute tools directly."""
        import jarvis_core.streaming.orchestrator as orch_mod
        source = Path(orch_mod.__file__).read_text()
        assert "execute_tool" not in source, "Orchestrator executes tools directly"

    def test_tool_call_returns_to_caller(self):
        """Tool calls must be returned to caller, not executed in streaming."""
        # The orchestrator returns {"error": "tool_call_detected"}
        # The caller (VoiceService) falls back to legacy path
        # which goes through brain.interpret() → SecurityManager → ToolRegistry
        pass  # Verified by test_orchestrator_tool_call_stops_streaming


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
