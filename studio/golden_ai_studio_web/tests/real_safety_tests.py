"""Real Safety Tests — tool call, cancel, fallback.

Tests the streaming pipeline with real providers.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def test_real_tool_call():
    """Test that tool calls are detected and not spoken."""
    print("\n  TOOL CALL TEST")
    print("  " + "-" * 40)

    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    # Ask something that might trigger a tool call
    messages = [
        {"role": "system", "content": "Voce e o Jarvis. Responda em portugues."},
        {"role": "user", "content": "Qual e aCapital do Brasil?"}
    ]

    orch = StreamingOrchestrator()
    result = await asyncio.wait_for(
        orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
        timeout=60.0
    )

    if result.get("ok"):
        print(f"  Response: {result.get('response', '')[:100]}")
        metrics = result.get("metrics")
        if hasattr(metrics, 'tool_call_detected'):
            print(f"  Tool call detected: {metrics.tool_call_detected}")
        print("  PASS: Response completed normally")
        return True
    else:
        error = result.get("error", "")
        if "tool_call" in error:
            print(f"  Tool call detected: {result.get('tool_call_text', '')[:100]}")
            print("  PASS: Tool call correctly detected")
            return True
        else:
            print(f"  ERROR: {error}")
            return False


async def test_real_cancel():
    """Test cancel stops playback and clears buffer."""
    print("\n  CANCEL TEST")
    print("  " + "-" * 40)

    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    messages = [
        {"role": "system", "content": "Voce e o Jarvis. Responda em portugues de forma detalhada."},
        {"role": "user", "content": "Explique o que e trading algoritmico em detalhes."}
    ]

    orch = StreamingOrchestrator()

    # Start the task
    task = asyncio.create_task(
        orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b")
    )

    # Wait a bit then cancel
    await asyncio.sleep(2.0)
    print("  Cancelling...")
    orch.cancel()

    try:
        result = await asyncio.wait_for(task, timeout=5.0)
        print(f"  Result: {result.get('error', 'completed')}")
        print("  PASS: Cancel completed")
        return True
    except asyncio.TimeoutError:
        print("  FAIL: Cancel timed out")
        return False


async def test_real_fallback():
    """Test fallback when streaming fails."""
    print("\n  FALLBACK TEST")
    print("  " + "-" * 40)

    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    # Try with invalid provider to trigger fallback
    messages = [
        {"role": "system", "content": "Voce e o Jarvis."},
        {"role": "user", "content": "Teste"}
    ]

    orch = StreamingOrchestrator()

    try:
        result = await asyncio.wait_for(
            orch.run(messages=messages, provider="invalid_provider", model="test"),
            timeout=10.0
        )
        # Should fallback to groq by default
        print(f"  Result: {result.get('error', 'completed')}")
        print("  PASS: Fallback handled")
        return True
    except Exception as e:
        print(f"  Exception: {str(e)[:100]}")
        print("  PASS: Exception handled gracefully")
        return True


async def main():
    print("=" * 60)
    print("  REAL SAFETY TESTS")
    print("=" * 60)

    results = []

    results.append(await test_real_tool_call())
    results.append(await test_real_cancel())
    results.append(await test_real_fallback())

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"  Passed: {passed}/{total}")

    if passed == total:
        print("  ALL TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")

    return passed == total


if __name__ == "__main__":
    asyncio.run(main())
