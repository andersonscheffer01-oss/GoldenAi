"""P1.4B.1 — Minimal Live Smoke Test."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def test_streaming_minimal():
    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    messages = [
        {"role": "system", "content": "Voce e o Jarvis. Responda em portugues."},
        {"role": "user", "content": "Ola"}
    ]

    print("Testing streaming with Ollama...")
    orch = StreamingOrchestrator()

    start = time.perf_counter()
    result = await asyncio.wait_for(
        orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
        timeout=60.0
    )
    elapsed = (time.perf_counter() - start) * 1000

    print(f"Result: ok={result.get('ok')}")
    print(f"Response: {result.get('response', '')[:100]}")
    print(f"Elapsed: {elapsed:.0f}ms")
    if result.get("metrics"):
        m = result["metrics"]
        print(f"TTFT: {m.provider_ttft_ms:.0f}ms")
        print(f"First audio: {m.tts_first_audio_ms:.0f}ms")
        print(f"Chunks emitted: {m.chunks_emitted}")
        print(f"Chunks played: {m.chunks_played}")

asyncio.run(test_streaming_minimal())
