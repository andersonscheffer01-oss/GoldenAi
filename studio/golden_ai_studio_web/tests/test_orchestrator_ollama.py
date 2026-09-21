"""Test orchestrator with Ollama directly."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def test():
    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    messages = [
        {"role": "system", "content": "Voce e o Jarvis. Responda em portugues."},
        {"role": "user", "content": "Ola, tudo bem?"}
    ]

    print("Testing orchestrator with Ollama...")
    orch = StreamingOrchestrator()

    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
            timeout=30.0
        )
        elapsed = (time.perf_counter() - start) * 1000
        print(f"Result: ok={result.get('ok')}")
        print(f"Response: {result.get('response', '')[:100]}")
        print(f"Elapsed: {elapsed:.0f}ms")
        if result.get("metrics"):
            m = result["metrics"]
            print(f"TTFT: {m.provider_ttft_ms:.0f}ms")
            print(f"First audio: {m.tts_first_audio_ms:.0f}ms")
    except asyncio.TimeoutError:
        print("TIMEOUT after 30s")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
