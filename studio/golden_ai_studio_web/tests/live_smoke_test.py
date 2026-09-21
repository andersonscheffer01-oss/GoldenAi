"""P1.4B.1 — Live Streaming Voice Smoke Test.

Uses Ollama (local) + Edge TTS + WPF playback.
Compares legacy vs streaming with real providers.
No microphone — text input only.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["JARVIS_STREAMING_VOICE"] = "1"

TEST_QUESTIONS = [
    "Que horas são?",
    "Explique rapidamente o que é latência.",
    "Me dê três ideias para melhorar o Golden.",
    "O que é um sistema de trading algoritmico e quais são suas principais vantagens?",
]


@dataclass
class LatencyResult:
    question: str
    run: int
    mode: str
    provider_ttft_ms: float = 0
    first_chunk_ready_ms: float = 0
    tts_first_audio_ms: float = 0
    total_response_ms: float = 0
    response_text: str = ""
    error: str = ""


async def test_streaming(question: str, run: int) -> LatencyResult:
    """Test streaming pipeline with real Ollama."""
    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    result = LatencyResult(question=question, run=run, mode="streaming")

    try:
        messages = [
            {"role": "system", "content": "Voce e o Jarvis, um assistente IA. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]

        orch = StreamingOrchestrator()
        start = time.perf_counter()

        pipeline_result = await asyncio.wait_for(
            orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
            timeout=60.0
        )

        elapsed = (time.perf_counter() - start) * 1000

        if pipeline_result.get("ok"):
            metrics = pipeline_result.get("metrics")
            result.provider_ttft_ms = metrics.provider_ttft_ms
            result.first_chunk_ready_ms = metrics.first_sentence_ready_ms
            result.tts_first_audio_ms = metrics.tts_first_audio_ms
            result.total_response_ms = metrics.total_response_ms
            result.response_text = pipeline_result.get("response", "")[:200]
        else:
            result.error = pipeline_result.get("error", "unknown")

    except asyncio.TimeoutError:
        result.error = "timeout"
    except Exception as e:
        result.error = str(e)[:200]

    return result


async def test_legacy(question: str, run: int) -> LatencyResult:
    """Test legacy pipeline with real Ollama + Edge TTS."""
    result = LatencyResult(question=question, run=run, mode="legacy")

    try:
        import edge_tts
        import tempfile
        import subprocess

        messages = [
            {"role": "system", "content": "Voce e o Jarvis, um assistente IA. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]

        from ollama import chat

        llm_start = time.perf_counter()
        response = chat(model="qwen2.5-coder:14b", messages=messages, stream=False)
        response_text = response.get("message", {}).get("content", "")
        llm_end = time.perf_counter()
        result.provider_ttft_ms = (llm_end - llm_start) * 1000
        result.response_text = response_text[:200]

        tts_start = time.perf_counter()
        communicate = edge_tts.Communicate(response_text, "pt-BR-AntonioNeural")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()
        await communicate.save(tmp_path)
        tts_end = time.perf_counter()
        result.tts_first_audio_ms = (tts_end - tts_start) * 1000

        play_start = time.perf_counter()
        uri = Path(tmp_path).resolve().as_uri()
        ps = (
            "Add-Type -AssemblyName PresentationCore;"
            "$p = New-Object System.Windows.Media.MediaPlayer;"
            f"$p.Open([Uri]'{uri}');"
            "for($i=0;$i -lt 50 -and -not $p.NaturalDuration.HasTimeSpan;$i++)"
            "{Start-Sleep -Milliseconds 100};"
            "if($p.NaturalDuration.HasTimeSpan)"
            "{$d=[math]::Ceiling($p.NaturalDuration.TimeSpan.TotalSeconds+0.5)}"
            "else{$d=8};"
            "$p.Play(); Start-Sleep -Seconds $d; $p.Close()"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=60, check=False,
        )
        play_end = time.perf_counter()

        result.total_response_ms = (play_end - llm_start) * 1000

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    except Exception as e:
        result.error = str(e)[:200]

    return result


def print_results(results: list[LatencyResult], mode: str):
    print(f"\n{'='*60}")
    print(f"  {mode.upper()} RESULTS")
    print(f"{'='*60}")

    for r in results:
        print(f"\n  Q: {r.question[:40]}...")
        print(f"     Run {r.run}:")
        print(f"       Provider TTFT:   {r.provider_ttft_ms:>8.1f} ms")
        print(f"       TTS First Audio: {r.tts_first_audio_ms:>8.1f} ms")
        print(f"       Total Response:  {r.total_response_ms:>8.1f} ms")
        if r.error:
            print(f"       ERROR: {r.error}")
        else:
            print(f"       Response: {r.response_text[:60]}...")


def calculate_stats(results: list[LatencyResult]) -> dict:
    valid = [r for r in results if not r.error]
    if not valid:
        return {}

    ttft = sorted([r.provider_ttft_ms for r in valid])
    tts = sorted([r.tts_first_audio_ms for r in valid])
    total = sorted([r.total_response_ms for r in valid])

    def p50(arr):
        n = len(arr)
        if n == 0:
            return 0
        if n % 2 == 1:
            return arr[n // 2]
        return (arr[n // 2 - 1] + arr[n // 2]) / 2

    def p95(arr):
        n = len(arr)
        if n == 0:
            return 0
        idx = int(n * 0.95)
        return arr[min(idx, n - 1)]

    return {
        "provider_ttft_p50": p50(ttft),
        "provider_ttft_p95": p95(ttft),
        "tts_first_audio_p50": p50(tts),
        "tts_first_audio_p95": p95(tts),
        "total_p50": p50(total),
        "total_p95": p95(total),
        "n": len(valid),
    }


async def main():
    print("=" * 60)
    print("  P1.4B.1 — LIVE STREAMING VOICE SMOKE TEST")
    print("=" * 60)
    print()
    print("Provider: Ollama (qwen2.5-coder:14b)")
    print("TTS: Edge TTS (pt-BR-AntonioNeural)")
    print("Playback: WPF MediaPlayer")
    print("Questions:", len(TEST_QUESTIONS))
    print("Runs per question: 3")

    RUNS = 3
    streaming_results = []
    legacy_results = []

    print("\n" + "=" * 60)
    print("  PHASE 1: STREAMING PIPELINE")
    print("=" * 60)

    for q_idx, question in enumerate(TEST_QUESTIONS):
        for run in range(1, RUNS + 1):
            print(f"\n  [{q_idx+1}/{len(TEST_QUESTIONS)}] Run {run}/{RUNS}: {question[:30]}...")
            result = await test_streaming(question, run)
            streaming_results.append(result)
            if result.error:
                print(f"    ERROR: {result.error}")
            else:
                print(f"    TTFT: {result.provider_ttft_ms:.0f}ms, TTS: {result.tts_first_audio_ms:.0f}ms, Total: {result.total_response_ms:.0f}ms")

    print("\n" + "=" * 60)
    print("  PHASE 2: LEGACY PIPELINE")
    print("=" * 60)

    for q_idx, question in enumerate(TEST_QUESTIONS):
        for run in range(1, RUNS + 1):
            print(f"\n  [{q_idx+1}/{len(TEST_QUESTIONS)}] Run {run}/{RUNS}: {question[:30]}...")
            result = await test_legacy(question, run)
            legacy_results.append(result)
            if result.error:
                print(f"    ERROR: {result.error}")
            else:
                print(f"    TTFT: {result.provider_ttft_ms:.0f}ms, TTS: {result.tts_first_audio_ms:.0f}ms, Total: {result.total_response_ms:.0f}ms")

    print_results(streaming_results, "streaming")
    print_results(legacy_results, "legacy")

    stream_stats = calculate_stats(streaming_results)
    legacy_stats = calculate_stats(legacy_results)

    print("\n" + "=" * 60)
    print("  COMPARISON")
    print("=" * 60)

    if stream_stats and legacy_stats:
        print(f"\n  {'Metric':<25} {'Legacy':>12} {'Streaming':>12} {'Delta':>12}")
        print(f"  {'-'*25} {'-'*12} {'-'*12} {'-'*12}")

        for metric, label in [
            ("provider_ttft", "Provider TTFT"),
            ("tts_first_audio", "TTS First Audio"),
            ("total", "Total Response"),
        ]:
            leg_p50 = legacy_stats[f"{metric}_p50"]
            str_p50 = stream_stats[f"{metric}_p50"]
            delta = str_p50 - leg_p50
            pct = (delta / leg_p50 * 100) if leg_p50 > 0 else 0
            print(f"  {label + ' P50':<25} {leg_p50:>10.0f}ms {str_p50:>10.0f}ms {delta:>+10.0f}ms ({pct:>+.0f}%)")

        leg_first = legacy_stats["tts_first_audio_p50"]
        str_first = stream_stats["tts_first_audio_p50"]
        delta_first = str_first - leg_first
        print(f"\n  KEY KPI (First Audio P50):")
        print(f"    Legacy:    {leg_first:.0f}ms")
        print(f"    Streaming: {str_first:.0f}ms")
        print(f"    Delta:     {delta_first:+.0f}ms")

        promote = delta_first < -200
        print(f"\n  PROMOTE STREAMING: {'YES' if promote else 'NO'}")
        if promote:
            print(f"  (Streaming is {abs(delta_first):.0f}ms faster to first audio)")
        else:
            print(f"  (Streaming is not significantly faster)")
    else:
        print("\n  Insufficient data for comparison")

    output = {
        "streaming": [vars(r) for r in streaming_results],
        "legacy": [vars(r) for r in legacy_results],
        "stream_stats": stream_stats,
        "legacy_stats": legacy_stats,
    }
    output_path = Path(__file__).parent / "p1.4b_smoke_results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to: {output_path}")

    print("\n" + "=" * 60)
    print("  SMOKE TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
