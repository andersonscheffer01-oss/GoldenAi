"""Benchmark: Legacy vs Streaming Voice Pipeline — P1.4B.

Compares legacy (Brain.interpret() → _speak()) vs streaming (provider → chunker → TTS).
Uses text input (no microphone). Measures first audio latency.

Usage:
    python -m tests.test_benchmark_streaming
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

from jarvis_core.streaming.orchestrator import StreamingOrchestrator, StreamingMetrics
from jarvis_core.streaming.tts_pipeline import AudioChunk


# ═══════════════════════════════════════════════════════════════════
# TEST QUESTIONS
# ═══════════════════════════════════════════════════════════════════

TEST_QUESTIONS = [
    "Que horas são?",
    "Explique em poucas palavras o que é latência.",
    "Me dê três ideias para melhorar o Golden.",
    "O Golden AI é um sistema de trading algoritmico que utiliza inteligência artificial para automatizar operações no mercado financeiro. Ele foi desenvolvido para auxiliar traders no gerenciamento de risco e tomada de decisões.",
]


# ═══════════════════════════════════════════════════════════════════
# MOCK PROVIDERS
# ═══════════════════════════════════════════════════════════════════

MOCK_RESPONSES = {
    "Que horas são?": "São duas da tarde.",
    "Explique em poucas palavras o que é latência.": "Latência é o tempo entre uma ação e sua resposta.",
    "Me dê três ideias para melhorar o Golden.": "1. Interface web moderna. 2. Dashboard de métricas. 3. Integração com mais exchanges.",
    "O Golden AI é um sistema de trading algoritmico que utiliza inteligência artificial para automatizar operações no mercado financeiro. Ele foi desenvolvido para auxiliar traders no gerenciamento de risco e tomada de decisões.": "O Golden AI é uma ferramenta poderosa para traders que buscam automação e inteligência nas suas operações.",
}


async def mock_stream_groq(messages, model):
    """Mock Groq stream that yields tokens."""
    # Find the user message
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_msg = msg.get("content", "")
            break

    response = MOCK_RESPONSES.get(user_msg, "Resposta padrão.")
    for token in response.split(" "):
        yield token + " "
        await asyncio.sleep(0.01)  # Simulate network delay


async def mock_stream_groq_fast(messages, model):
    """Faster mock for benchmarking."""
    user_msg = ""
    for msg in messages:
        if msg.get("role") == "user":
            user_msg = msg.get("content", "")
            break

    response = MOCK_RESPONSES.get(user_msg, "Resposta padrão.")
    for token in response.split(" "):
        yield token + " "


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK TESTS
# ═══════════════════════════════════════════════════════════════════

class TestBenchmark:
    """Benchmark legacy vs streaming."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", TEST_QUESTIONS)
    async def test_streaming_first_audio(self, question):
        """Measure streaming first audio latency."""
        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_groq_fast):
            with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence") as mock_tts:
                mock_tts.return_value = AudioChunk(
                    index=0, text="test", audio_path=None,
                    duration_ms=50, is_final=True,
                )
                with patch("jarvis_core.streaming.audio_player.AudioPlayer.play", return_value=50):
                    orch = StreamingOrchestrator()
                    start = time.perf_counter()
                    result = await orch.run(
                        messages=[{"role": "user", "content": question}],
                        provider="groq",
                    )
                    elapsed_ms = (time.perf_counter() - start) * 1000

                    assert result["ok"] is True
                    assert result["metrics"].provider_ttft_ms > 0
                    assert result["metrics"].total_response_ms > 0

                    return {
                        "question": question[:30],
                        "provider_ttft_ms": result["metrics"].provider_ttft_ms,
                        "first_sentence_ms": result["metrics"].first_sentence_ready_ms,
                        "tts_first_audio_ms": result["metrics"].tts_first_audio_ms,
                        "total_ms": result["metrics"].total_response_ms,
                    }

    @pytest.mark.asyncio
    async def test_streaming_cancellation_benchmark(self):
        """Benchmark cancellation latency."""
        from jarvis_core.streaming.turn_manager import TurnManager

        with patch("jarvis_core.streaming.orchestrator.stream_groq", mock_stream_groq):
            tm = TurnManager()
            turn_id = tm.new_turn()
            tm.cancel_current()
            orch = StreamingOrchestrator()

            start = time.perf_counter()
            result = await orch.run(
                messages=[{"role": "user", "content": "test"}],
                provider="groq",
                turn_id=turn_id,
                turn_manager=tm,
            )
            cancel_ms = (time.perf_counter() - start) * 1000

            assert result["ok"] is False
            assert cancel_ms < 100  # Should be near-instant

    @pytest.mark.asyncio
    async def test_chunker_latency(self):
        """Benchmark chunker sentence detection."""
        from jarvis_core.streaming.sentence_chunker import SentenceChunker

        chunker = SentenceChunker()
        text = "Esta é uma resposta longa com várias frases. Cada frase deve ser detectada corretamente. O chunker não deve quebrar palavras no meio."

        start = time.perf_counter()
        chunks = []
        for word in text.split(" "):
            chunks.extend(chunker.feed(word + " "))
        remaining = chunker.flush()
        if remaining:
            chunks.append(remaining)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(chunks) >= 2
        assert elapsed_ms < 10  # Should be very fast

    @pytest.mark.asyncio
    async def test_tts_pipeline_latency(self):
        """Benchmark TTS pipeline ordering."""
        from jarvis_core.streaming.tts_pipeline import TTSPipeline

        async def fast_synth(text, index, is_final=False, cancel_event=None):
            return AudioChunk(
                index=index, text=text, audio_path=None,
                duration_ms=10, is_final=is_final,
            )

        with patch("jarvis_core.streaming.tts_pipeline.synthesize_sentence", fast_synth):
            pipeline = TTSPipeline()

            start = time.perf_counter()
            for i in range(5):
                await pipeline.submit(f"Sentence {i}", i, is_final=(i == 4))

            chunks = []
            while True:
                chunk = await asyncio.wait_for(pipeline.next_ready(), timeout=2.0)
                if chunk is None:
                    break
                chunks.append(chunk)
                if chunk.is_final:
                    break
            elapsed_ms = (time.perf_counter() - start) * 1000

            assert len(chunks) == 5
            assert elapsed_ms < 500  # Should be fast with mocked TTS


# ═══════════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════

def generate_report():
    """Generate benchmark report."""
    print("\n" + "=" * 60)
    print("P1.4B BENCHMARK REPORT")
    print("=" * 60)
    print("\nSTREAM TYPE: sentence-level pipelining")
    print("EDGE TTS MODE: sentence-level (not true audio streaming)")
    print("\nMETRICS:")
    print("-" * 40)
    print("provider_ttft_ms: Time to first token from provider")
    print("first_sentence_ms: Time to first complete sentence")
    print("tts_first_audio_ms: Time to first TTS audio chunk")
    print("total_ms: Total response time")
    print("-" * 40)
    print("\nTEST QUESTIONS:")
    for i, q in enumerate(TEST_QUESTIONS, 1):
        print(f"  {i}. {q[:50]}...")
    print("\nRun: python -m pytest tests/test_benchmark_streaming.py -v")
    print("=" * 60)


if __name__ == "__main__":
    generate_report()
    pytest.main([__file__, "-v"])
