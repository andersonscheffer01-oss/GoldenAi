"""Controlled local faster-whisper benchmark.

This tool measures the approved local provider without opening a microphone or
calling Core. Synthetic PCM is used only for mechanical performance samples;
human-speech quality is measured only from explicitly licensed manifest items.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import string
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import psutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis_core.stt_faster_whisper import (
    APPROVED_MODEL_COMPUTE_TYPE,
    APPROVED_MODEL_DEVICE,
    APPROVED_MODEL_ID,
    APPROVED_MODEL_LANGUAGE,
    APPROVED_MODEL_REVISION,
    FasterWhisperSTTProvider,
)
from jarvis_core.voice_foundation import VoiceCancellation


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = value.translate(str.maketrans("", "", string.punctuation))
    return " ".join(value.split())


def edit_counts(reference: str, hypothesis: str) -> tuple[int, int, int, int]:
    """Return substitutions, deletions, insertions and reference length."""
    ref = normalize(reference).split()
    hyp = normalize(hypothesis).split()
    rows = [[(0, 0, 0) for _ in range(len(hyp) + 1)] for _ in range(len(ref) + 1)]
    for j in range(1, len(hyp) + 1):
        rows[0][j] = (0, 0, j)
    for i in range(1, len(ref) + 1):
        rows[i][0] = (0, i, 0)
    for i, ref_word in enumerate(ref, 1):
        for j, hyp_word in enumerate(hyp, 1):
            if ref_word == hyp_word:
                rows[i][j] = rows[i - 1][j - 1]
                continue
            substitution = rows[i - 1][j - 1]
            deletion = rows[i - 1][j]
            insertion = rows[i][j - 1]
            candidates = [
                (substitution[0] + 1, substitution[1], substitution[2]),
                (deletion[0], deletion[1] + 1, deletion[2]),
                (insertion[0], insertion[1], insertion[2] + 1),
            ]
            rows[i][j] = min(candidates, key=lambda item: sum(item))
    substitutions, deletions, insertions = rows[-1][-1]
    return substitutions, deletions, insertions, len(ref)


def rss_bytes(process: psutil.Process) -> int:
    return int(process.memory_info().rss)


def load_manifest(path: Path | None) -> tuple[str, str, list[dict[str, Any]]]:
    if path is None:
        return "none", "none", []
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = []
    for item in payload.get("fixtures", []):
        if item.get("provenance_class") != "LICENSED_TEST_FIXTURE":
            continue
        if not item.get("license"):
            continue
        fixtures.append(item)
    return str(payload.get("source", path)), str(payload.get("license", "")), fixtures


def transcribe_sample(provider, audio: bytes, duration: float, fixture_id: str, category: str):
    started = time.perf_counter()
    event = provider.transcribe(
        audio,
        sample_rate=16000,
        cancellation=VoiceCancellation(),
        session_id="benchmark",
        utterance_id=fixture_id,
    )
    wall = time.perf_counter() - started
    return {
        "fixture_id": fixture_id,
        "category": category,
        "audio_duration": duration,
        "reference": None,
        "hypothesis": event.text,
        "normalized_reference": None,
        "normalized_hypothesis": normalize(event.text),
        "transcription_time": wall,
        "rtf": wall / duration if duration else None,
        "quality_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    process = psutil.Process(os.getpid())
    provider = FasterWhisperSTTProvider()
    path = provider.resolve_model()
    base_rss = rss_bytes(process)
    load_started = time.perf_counter()
    provider._ensure_model()
    load_time = time.perf_counter() - load_started
    post_load_rss = rss_bytes(process)

    results: list[dict[str, Any]] = []
    peak_rss = post_load_rss
    # These are non-speech signals used only to measure decode cost and RTF.
    for seconds in (1.0, 2.0, 4.0):
        samples = np.zeros(int(16000 * seconds), dtype=np.int16)
        result = transcribe_sample(
            provider,
            samples.tobytes(),
            seconds,
            f"synthetic-performance-{seconds:g}s",
            "synthetic_performance_non_speech",
        )
        results.append(result)
        peak_rss = max(peak_rss, rss_bytes(process))

    source, corpus_license, fixtures = load_manifest(args.manifest)
    quality_results = []
    for fixture in fixtures:
        fixture_path = Path(fixture["path"])
        if not fixture_path.is_absolute() and args.manifest:
            fixture_path = args.manifest.parent / fixture_path
        audio = fixture_path.read_bytes()
        duration = float(fixture.get("audio_duration") or 0)
        result = transcribe_sample(
            provider, audio, duration, str(fixture["fixture_id"]), str(fixture["category"])
        )
        reference = str(fixture.get("reference") or "")
        substitutions, deletions, insertions, reference_words = edit_counts(
            reference, result["hypothesis"]
        )
        result.update({
            "reference": reference,
            "normalized_reference": normalize(reference),
            "quality_eligible": True,
            "substitutions": substitutions,
            "deletions": deletions,
            "insertions": insertions,
            "reference_word_count": reference_words,
            "wer": (
                (substitutions + deletions + insertions) / reference_words
                if reference_words else None
            ),
        })
        quality_results.append(result)
        peak_rss = max(peak_rss, rss_bytes(process))

    warm_times = [item["transcription_time"] for item in results]
    warm_rtfs = [item["rtf"] for item in results]
    all_counts = [edit_counts(item["reference"], item["hypothesis"]) for item in quality_results]
    substitutions = sum(item[0] for item in all_counts)
    deletions = sum(item[1] for item in all_counts)
    insertions = sum(item[2] for item in all_counts)
    reference_words = sum(item[3] for item in all_counts)

    payload = {
        "benchmark": "JARVIS_STT_PTBR_BENCHMARK",
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": {
            "provider": "Systran",
            "id": APPROVED_MODEL_ID,
            "revision": APPROVED_MODEL_REVISION,
            "path": str(path),
            "device": APPROVED_MODEL_DEVICE,
            "compute_type": APPROVED_MODEL_COMPUTE_TYPE,
            "language": APPROVED_MODEL_LANGUAGE,
            "local_files_only": True,
        },
        "environment": {
            "python": platform.python_version(),
            "cpu": platform.processor(),
            "logical_threads": os.cpu_count(),
            "ram_bytes": psutil.virtual_memory().total,
            "gpu_stt_acceleration": False,
            "cuda": False,
        },
        "corpus": {
            "source": source,
            "license": corpus_license,
            "licensed_fixture_count": len(quality_results),
            "human_speech_samples": 0,
            "synthetic_speech_samples": 0,
            "synthetic_performance_samples": len(results),
            "sufficient_for_quality": bool(quality_results),
        },
        "quality": {
            "reference_word_count": reference_words,
            "substitutions": substitutions,
            "deletions": deletions,
            "insertions": insertions,
            "aggregate_wer": (
                (substitutions + deletions + insertions) / reference_words
                if reference_words else None
            ),
            "results": quality_results,
        },
        "performance": {
            "model_load_time_cold": load_time,
            "warm_transcription_runs": len(results),
            "transcription_time_min": min(warm_times),
            "transcription_time_median": statistics.median(warm_times),
            "transcription_time_mean": statistics.mean(warm_times),
            "transcription_time_max": max(warm_times),
            "rtf_min": min(warm_rtfs),
            "rtf_median": statistics.median(warm_rtfs),
            "rtf_mean": statistics.mean(warm_rtfs),
            "rtf_max": max(warm_rtfs),
            "rtf_below_1": all(value < 1 for value in warm_rtfs),
        },
        "memory": {
            "base_process_rss": base_rss,
            "post_model_load_rss": post_load_rss,
            "peak_transcription_rss": peak_rss,
            "post_transcription_rss": rss_bytes(process),
            "method": "psutil.Process(os.getpid()).memory_info().rss",
        },
        "safety": {
            "model_downloads": False,
            "network_stt_used": False,
            "remote_stt_used": False,
            "raw_audio_persisted": False,
            "microphone_recorded": False,
            "transcript_executes_core": False,
        },
        "samples": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    provider.close()
    print(json.dumps({
        "model_load_time_cold": load_time,
        "warm_runs": len(results),
        "rtf_median": payload["performance"]["rtf_median"],
        "rtf_below_1": payload["performance"]["rtf_below_1"],
        "quality_fixture_count": len(quality_results),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
