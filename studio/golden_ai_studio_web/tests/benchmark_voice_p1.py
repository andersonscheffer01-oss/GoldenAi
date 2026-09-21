"""Benchmark controlado P1. Gera fala SAPI temporária; não preserva áudio."""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PHRASES = (
    ("Jarvis, que horas são?", "SYSTEM"),
    ("Jarvis, abra a calculadora.", "WINDOWS"),
    ("Jarvis, abra o gerenciador de tarefas.", "WINDOWS"),
    ("Jarvis, qual é a cotação do dólar?", "MARKET_DATA"),
    ("Jarvis, feche a calculadora.", "CONVERSATION"),
    ("Jarvis, explique o que é inflação.", "CONVERSATION"),
    ("Jarvis, abra ele.", "CLARIFY"),
    ("Jarvis.", "WAKE_ONLY"),
    ("Qual é a cotação do ouro?", "IGNORED"),
    ("Pare.", "IGNORED"),
)


def synthesize(text, path):
    import win32com.client
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Open(str(path), 3, False)
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.AudioOutputStream = stream
    voice.Speak(text)
    stream.Close()


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--beam", type=int, required=True)
    parser.add_argument("--best-of", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    import psutil
    from faster_whisper import WhisperModel
    from jarvis_core.service import JarvisService
    from jarvis_core.voice import JarvisVoice

    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    cpu_before = sum(proc.cpu_times()[:2])
    load_started = time.perf_counter()
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    load_ms = int((time.perf_counter() - load_started) * 1000)
    voice = JarvisVoice()
    service = JarvisService(tempfile.mkdtemp(prefix="golden-voice-bench-"))
    samples, latencies = [], []
    prompt = getattr(voice, "initial_prompt", "Jarvis, Golden, MetaTrader, MT5, XAUUSD, Forex")
    with tempfile.TemporaryDirectory(prefix="golden-p1-audio-") as temp:
        for index, (phrase, expected_route) in enumerate(PHRASES):
            wav = Path(temp) / f"sample-{index}.wav"
            synthesize(phrase, wav)
            started = time.perf_counter()
            segments, info = model.transcribe(str(wav), language="pt", beam_size=args.beam,
                best_of=args.best_of, condition_on_previous_text=False, initial_prompt=prompt)
            segments = list(segments)
            stt_ms = int((time.perf_counter() - started) * 1000)
            text = " ".join(s.text.strip() for s in segments).strip()
            action = voice.process_voice_command(text)
            if action.get("action") == "listen_more":
                route = "WAKE_ONLY"
            elif action.get("action") == "ignore":
                route = "IGNORED"
            else:
                route = service.orchestrator.decide(action.get("command") or text).route.value
            similarity = SequenceMatcher(None, phrase.casefold(), text.casefold()).ratio()
            latencies.append(stt_ms)
            samples.append({"expected": phrase, "transcript": text, "stt_ms": stt_ms,
                "similarity": round(similarity, 3), "expected_route": expected_route,
                "route": route, "route_ok": route == expected_route,
                "avg_logprob": round(statistics.mean([s.avg_logprob for s in segments]), 3)
                    if segments else None,
                "no_speech_prob": round(max([s.no_speech_prob for s in segments]), 3)
                    if segments else None})
    result = {"model": args.model, "compute_type": "int8", "beam_size": args.beam,
        "best_of": args.best_of, "load_ms": load_ms,
        "avg_stt_ms": round(statistics.mean(latencies), 1),
        "p50_ms": percentile(latencies, .5), "p95_ms": percentile(latencies, .95),
        "errors": sum(s["similarity"] < .8 for s in samples),
        "routing_success": sum(s["route_ok"] for s in samples),
        "sample_count": len(samples),
        "cpu_seconds": round(sum(proc.cpu_times()[:2]) - cpu_before, 2),
        "rss_delta_mb": round((proc.memory_info().rss - rss_before) / 1048576, 1),
        "samples": samples}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
