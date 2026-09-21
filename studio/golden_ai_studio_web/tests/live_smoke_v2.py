"""P1.4B.1 — Live Smoke Test (reduced runs)."""
import asyncio
import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_QUESTIONS = [
    "Que horas são?",
    "Explique rapidamente o que é latência.",
    "Me dê três ideias para melhorar o Golden.",
    "O que é trading algoritmico?",
]

@dataclass
class Result:
    question: str
    run: int
    mode: str
    provider_ttft_ms: float = 0
    tts_first_audio_ms: float = 0
    total_response_ms: float = 0
    response: str = ""
    error: str = ""

async def test_streaming(question: str, run: int) -> Result:
    from jarvis_core.streaming.orchestrator import StreamingOrchestrator
    r = Result(question=question, run=run, mode="streaming")
    try:
        messages = [
            {"role": "system", "content": "Voce e o Jarvis. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]
        orch = StreamingOrchestrator()
        start = time.perf_counter()
        res = await asyncio.wait_for(
            orch.run(messages=messages, provider="ollama", model="qwen2.5-coder:14b"),
            timeout=60.0
        )
        r.total_response_ms = (time.perf_counter() - start) * 1000
        if res.get("ok"):
            m = res["metrics"]
            r.provider_ttft_ms = m.provider_ttft_ms
            r.tts_first_audio_ms = m.tts_first_audio_ms
            r.response = res.get("response", "")[:100]
        else:
            r.error = res.get("error", "unknown")
    except Exception as e:
        r.error = str(e)[:100]
    return r

async def test_legacy(question: str, run: int) -> Result:
    import edge_tts, tempfile, subprocess
    from ollama import chat
    r = Result(question=question, run=run, mode="legacy")
    try:
        messages = [
            {"role": "system", "content": "Voce e o Jarvis. Responda em portugues de forma concisa."},
            {"role": "user", "content": question}
        ]
        t0 = time.perf_counter()
        resp = chat(model="qwen2.5-coder:14b", messages=messages, stream=False)
        text = resp.get("message", {}).get("content", "")
        r.provider_ttft_ms = (time.perf_counter() - t0) * 1000
        r.response = text[:100]

        t1 = time.perf_counter()
        comm = edge_tts.Communicate(text, "pt-BR-AntonioNeural")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()
        await comm.save(tmp_path)
        r.tts_first_audio_ms = (time.perf_counter() - t1) * 1000

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
        r.total_response_ms = (time.perf_counter() - t0) * 1000
        try: os.unlink(tmp_path)
        except: pass
    except Exception as e:
        r.error = str(e)[:100]
    return r

def p50(arr):
    s = sorted(arr)
    n = len(s)
    if n == 0: return 0
    return s[n//2] if n % 2 else (s[n//2-1] + s[n//2]) / 2

def p95(arr):
    s = sorted(arr)
    n = len(s)
    return s[min(int(n*0.95), n-1)] if n else 0

async def main():
    print("=" * 60)
    print("  P1.4B.1 — LIVE SMOKE TEST (2 runs × 4 questions)")
    print("=" * 60)

    RUNS = 2
    streaming = []
    legacy = []

    for q in TEST_QUESTIONS:
        for run in range(1, RUNS + 1):
            print(f"\n  STREAMING: {q[:30]}... (run {run})")
            r = await test_streaming(q, run)
            streaming.append(r)
            if r.error:
                print(f"    ERROR: {r.error}")
            else:
                print(f"    TTFT={r.provider_ttft_ms:.0f}ms TTS={r.tts_first_audio_ms:.0f}ms Total={r.total_response_ms:.0f}ms")

    for q in TEST_QUESTIONS:
        for run in range(1, RUNS + 1):
            print(f"\n  LEGACY: {q[:30]}... (run {run})")
            r = await test_legacy(q, run)
            legacy.append(r)
            if r.error:
                print(f"    ERROR: {r.error}")
            else:
                print(f"    TTFT={r.provider_ttft_ms:.0f}ms TTS={r.tts_first_audio_ms:.0f}ms Total={r.total_response_ms:.0f}ms")

    # Stats
    s_ttft = [r.provider_ttft_ms for r in streaming if not r.error]
    s_tts = [r.tts_first_audio_ms for r in streaming if not r.error]
    l_ttft = [r.provider_ttft_ms for r in legacy if not r.error]
    l_tts = [r.tts_first_audio_ms for r in legacy if not r.error]

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"\n  {'Metric':<25} {'Legacy':>10} {'Streaming':>10} {'Delta':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*10}")

    leg_ttft = p50(l_ttft)
    str_ttft = p50(s_ttft)
    print(f"  {'TTFT P50':<25} {leg_ttft:>8.0f}ms {str_ttft:>8.0f}ms {str_ttft-leg_ttft:>+8.0f}ms")

    leg_tts = p50(l_tts)
    str_tts = p50(s_tts)
    print(f"  {'First Audio P50':<25} {leg_tts:>8.0f}ms {str_tts:>8.0f}ms {str_tts-leg_tts:>+8.0f}ms")

    delta = str_tts - leg_tts
    print(f"\n  KEY KPI (First Audio P50):")
    print(f"    Legacy:    {leg_tts:.0f}ms")
    print(f"    Streaming: {str_tts:.0f}ms")
    print(f"    Delta:     {delta:+.0f}ms")
    print(f"\n  PROMOTE: {'YES' if delta < -200 else 'NO'}")

    # Save
    out = {
        "streaming": [vars(r) for r in streaming],
        "legacy": [vars(r) for r in legacy],
        "stats": {"legacy_ttft_p50": leg_ttft, "streaming_ttft_p50": str_ttft,
                  "legacy_tts_p50": leg_tts, "streaming_tts_p50": str_tts, "delta": delta}
    }
    with open(Path(__file__).parent / "p1.4b_smoke_results.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)

import os
asyncio.run(main())
