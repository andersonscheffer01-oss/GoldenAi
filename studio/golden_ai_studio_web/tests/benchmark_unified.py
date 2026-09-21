"""Unified Benchmark — fair comparison using TurnClock.

All metrics measured from TURN_START for both Legacy and Streaming pipelines.
Ensures apples-to-apples comparison.
"""

import asyncio
import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.streaming.turn_clock import TurnClock

TEST_QUESTIONS = [
    ("resposta curta", "Que horas são?"),
    ("resposta média", "Explique rapidamente o que é latência."),
    ("3 itens", "Me dê três ideias para melhorar o Golden."),
    ("3-5 frases", "O que é trading algoritmico?"),
]


@dataclass
class UnifiedResult:
    question: str
    question_type: str
    run: int
    mode: str  # "legacy", "sentence_stream", "true_stream"
    clock_metrics: dict = field(default_factory=dict)
    response: str = ""
    error: str = ""


async def test_legacy(question: str, run: int) -> UnifiedResult:
    """Test legacy pipeline with unified clock."""
    import edge_tts, tempfile, subprocess
    from ollama import chat

    clock = TurnClock()
    result = UnifiedResult(
        question=question,
        question_type="",
        run=run,
        mode="legacy",
    )

    try:
        messages = [
            {"role": "system", "content": "Voce e o Jarvis. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]

        # TURN_START
        clock.mark_turn_start()

        # LLM
        resp = chat(model="qwen2.5-coder:14b", messages=messages, stream=False)
        text = resp.get("message", {}).get("content", "")
        clock.mark_provider_first_token()
        clock.mark_provider_complete()
        clock.mark_first_text_chunk()

        result.response = text[:100]

        # TTS
        clock.mark_tts_request_start()
        comm = edge_tts.Communicate(text, "pt-BR-AntonioNeural")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()
        await comm.save(tmp_path)
        clock.mark_first_audio_bytes()

        # Playback
        clock.mark_playback_start()
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
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60)

        clock.mark_response_complete()

        result.clock_metrics = clock.to_dict()

        try:
            os.unlink(tmp_path)
        except:
            pass

    except Exception as e:
        result.error = str(e)[:100]

    return result


async def test_sentence_streaming(question: str, run: int) -> UnifiedResult:
    """Test sentence-level streaming with unified clock."""
    from jarvis_core.streaming.orchestrator import StreamingOrchestrator

    result = UnifiedResult(
        question=question,
        question_type="",
        run=run,
        mode="sentence_stream",
    )

    try:
        messages = [
            {"role": "system", "content": "Voce e o Jarvis. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]

        orch = StreamingOrchestrator()
        res = await asyncio.wait_for(
            orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
            timeout=60.0
        )

        if res.get("ok"):
            # The orchestrator already uses TurnClock internally
            # We need to extract the clock metrics
            metrics = res["metrics"]
            result.clock_metrics = {
                "provider_first_token_from_turn_ms": metrics.provider_ttft_ms,
                "first_text_chunk_from_turn_ms": metrics.first_sentence_ready_ms,
                "tts_request_start_from_turn_ms": metrics.tts_start_ms,
                "first_audio_bytes_from_turn_ms": metrics.tts_first_audio_ms,
                "playback_start_from_turn_ms": metrics.playback_start_ms,
                "response_complete_from_turn_ms": metrics.total_response_ms,
            }
            result.response = res.get("response", "")[:100]
        else:
            result.error = res.get("error", "unknown")

    except Exception as e:
        result.error = str(e)[:100]

    return result


async def test_true_streaming(question: str, run: int) -> UnifiedResult:
    """Test true audio streaming with unified clock."""
    from jarvis_core.streaming.orchestrator_true_streaming import TrueStreamingOrchestrator

    result = UnifiedResult(
        question=question,
        question_type="",
        run=run,
        mode="true_stream",
    )

    try:
        messages = [
            {"role": "system", "content": "Voce e o Jarvis. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]

        orch = TrueStreamingOrchestrator()
        res = await asyncio.wait_for(
            orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
            timeout=60.0
        )

        if res.get("ok"):
            metrics = res["metrics"]
            result.clock_metrics = metrics.clock.to_dict()
            result.response = res.get("response", "")[:100]
        else:
            result.error = res.get("error", "unknown")

    except Exception as e:
        result.error = str(e)[:100]

    return result


def p50(arr):
    s = sorted(arr)
    n = len(s)
    if n == 0:
        return 0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def p95(arr):
    s = sorted(arr)
    n = len(s)
    return s[min(int(n * 0.95), n - 1)] if n else 0


def extract_metric(results, metric_name):
    return [r.clock_metrics.get(metric_name, 0) for r in results if not r.error]


async def main():
    print("=" * 70)
    print("  UNIFIED BENCHMARK — Fair Comparison (TurnClock)")
    print("=" * 70)

    RUNS = 3
    legacy_results = []
    sentence_results = []
    true_results = []

    # Run benchmarks
    for q_type, question in TEST_QUESTIONS:
        for run in range(1, RUNS + 1):
            print(f"\n  [{q_type}] {question[:40]}... (run {run})")

            # Legacy
            r = await test_legacy(question, run)
            r.question_type = q_type
            legacy_results.append(r)
            if r.error:
                print(f"    LEGACY ERROR: {r.error}")
            else:
                kpi = r.clock_metrics.get("playback_start_from_turn_ms", 0)
                print(f"    LEGACY:   KPI={kpi:.0f}ms")

            # Sentence streaming
            r = await test_sentence_streaming(question, run)
            r.question_type = q_type
            sentence_results.append(r)
            if r.error:
                print(f"    SENTENCE ERROR: {r.error}")
            else:
                kpi = r.clock_metrics.get("playback_start_from_turn_ms", 0)
                print(f"    SENTENCE: KPI={kpi:.0f}ms")

            # True streaming
            r = await test_true_streaming(question, run)
            r.question_type = q_type
            true_results.append(r)
            if r.error:
                print(f"    TRUE ERROR: {r.error}")
            else:
                kpi = r.clock_metrics.get("playback_start_from_turn_ms", 0)
                print(f"    TRUE:     KPI={kpi:.0f}ms")

    # Statistics
    print("\n" + "=" * 70)
    print("  RESULTS (P50/P95 from TURN_START)")
    print("=" * 70)

    metrics_to_show = [
        "provider_first_token_from_turn_ms",
        "first_text_chunk_from_turn_ms",
        "first_audio_bytes_from_turn_ms",
        "playback_start_from_turn_ms",
        "response_complete_from_turn_ms",
    ]

    print(f"\n  {'Metric':<35} {'Legacy':>12} {'Sentence':>12} {'True':>12}")
    print(f"  {'-'*35} {'-'*12} {'-'*12} {'-'*12}")

    for metric in metrics_to_show:
        leg = extract_metric(legacy_results, metric)
        sen = extract_metric(sentence_results, metric)
        tru = extract_metric(true_results, metric)

        leg_p50 = p50(leg)
        sen_p50 = p50(sen)
        tru_p50 = p50(tru)

        name = metric.replace("_from_turn_ms", "").replace("_", " ").title()
        print(f"  {name + ' P50':<35} {leg_p50:>10.0f}ms {sen_p50:>10.0f}ms {tru_p50:>10.0f}ms")

    # KPI comparison
    leg_kpi = extract_metric(legacy_results, "playback_start_from_turn_ms")
    sen_kpi = extract_metric(sentence_results, "playback_start_from_turn_ms")
    tru_kpi = extract_metric(true_results, "playback_start_from_turn_ms")

    leg_p50 = p50(leg_kpi)
    sen_p50 = p50(sen_kpi)
    tru_p50 = p50(tru_kpi)

    print(f"\n  KEY KPI: TURN_START_TO_PLAYBACK_START_MS (P50)")
    print(f"    Legacy:          {leg_p50:.0f}ms")
    print(f"    Sentence Stream: {sen_p50:.0f}ms (delta: {sen_p50 - leg_p50:+.0f}ms)")
    print(f"    True Stream:     {tru_p50:.0f}ms (delta: {tru_p50 - leg_p50:+.0f}ms)")

    # Save results
    out = {
        "legacy": [{"question": r.question, "type": r.question_type, "run": r.run, "metrics": r.clock_metrics} for r in legacy_results],
        "sentence_stream": [{"question": r.question, "type": r.question_type, "run": r.run, "metrics": r.clock_metrics} for r in sentence_results],
        "true_stream": [{"question": r.question, "type": r.question_type, "run": r.run, "metrics": r.clock_metrics} for r in true_results],
        "stats": {
            "legacy_kpi_p50": leg_p50,
            "sentence_kpi_p50": sen_p50,
            "true_kpi_p50": tru_p50,
        }
    }

    with open(Path(__file__).parent / "unified_benchmark_results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)


import os
asyncio.run(main())
