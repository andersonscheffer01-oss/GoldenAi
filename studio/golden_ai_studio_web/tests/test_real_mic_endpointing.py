"""
P1.4A.2 — Real Microphone Endpointing Validation
==================================================

Validates RMS vs Silero vs Hybrid with real human speech in PT-BR.

Recording is NEUTRAL: fixed time window, no VAD decides when to stop.
Same raw buffer is delivered to all three pipelines.

Usage:
    python tests/test_real_mic_endpointing.py              # interactive menu
    python tests/test_real_mic_endpointing.py --scenario 1 # direct
    python tests/test_real_mic_endpointing.py --reps 3     # custom reps
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import wave
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.realtime_voice.constants import (
    FRAME_BYTES,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    VAD_ENDPOINT_MS_DEFAULT,
    HYBRID_HANGOVER_MS_DEFAULT,
)
from jarvis_core.realtime_voice.vad import SileroVADAdapter, VADEvent
from jarvis_core.realtime_voice.hybrid_endpoint import (
    HybridEndpoint,
    HybridEvent,
    rms_energy as hybrid_rms_energy,
)


# ═══════════════════════════════════════════════════════════════════
# SCENARIOS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Scenario:
    id: int
    name: str
    phrase: str
    last_word: str
    window_s: float
    description: str


SCENARIOS = [
    Scenario(1, "short_phrase", "Jarvis, que horas são?", "são", 4.0,
             "Frase curta, palavra final fraca"),
    Scenario(2, "medium_phrase", "Jarvis, me diga como está o projeto Golden.", "Golden", 6.0,
             "Frase média"),
    Scenario(3, "soft_ending", "Jarvis, abra o navegador por favor.", "favor", 5.0,
             "Final suave"),
    Scenario(4, "final_short", "Jarvis, pare.", "pare", 4.0,
             "Palavra final curta"),
    Scenario(5, "pause_continue", "Jarvis, eu quero... abrir o Golden.", "Golden", 6.0,
             "Pausa natural no meio"),
    Scenario(6, "long_phrase",
             "Jarvis, preciso que você verifique o status do projeto Golden e me diga quais são os próximos passos.",
             "passos", 14.0,
             "Frase longa 8-12s"),
    Scenario(7, "low_volume", "Jarvis, que horas são?", "são", 4.0,
             "Mesma frase 1, sussurrada"),
    Scenario(8, "noisy", "Jarvis, que horas são?", "são", 4.0,
             "Mesma frase 1, com ruído ambiente"),
]


# ═══════════════════════════════════════════════════════════════════
# NEUTRAL RECORDING
# ═══════════════════════════════════════════════════════════════════

def record_from_mic(scenario: Scenario) -> Optional[np.ndarray]:
    """Record audio from microphone with FIXED time window.

    Uses sd.rec() (blocking) which matches the golden sample that works.
    No VAD, no silence detection. Pure neutral capture.
    Returns numpy int16 array.
    """
    import sounddevice as sd

    samplerate = 16000
    channels = 1
    duration = scenario.window_s
    n_samples = int(samplerate * duration)

    print(f"\n  Frase: \"{scenario.phrase}\"")
    print(f"  Gravando {duration:.0f}s de audio apos o sinal...")

    for i in range(3, 0, -1):
        print(f"  {i}...", end="", flush=True)
        time.sleep(1)
    print(" FALE!\n")

    audio = sd.rec(
        n_samples,
        samplerate=samplerate,
        channels=channels,
        dtype="int16",
        device=1,
    )
    sd.wait()

    return audio.flatten()


def record_all_reps(scenario: Scenario, reps: int) -> list[tuple[int, Optional[np.ndarray]]]:
    """Record all reps using sd.rec() per rep. First call is warmup."""
    import sounddevice as sd

    recordings = []

    # Warmup: first sd.rec() call primes the device
    print("  Warmup (1s)...")
    warmup = sd.rec(16000, samplerate=16000, channels=1, dtype="int16", device=1)
    sd.wait()
    del warmup
    print("  Warmup OK.\n")

    for rep in range(reps):
        print(f"  -- Repeticao {rep+1} --")
        audio = record_from_mic(scenario)
        if audio is not None:
            peak = int(np.abs(audio).max())
            rms_level = float(np.abs(audio.astype(np.float32)).mean())
            clip = int((np.abs(audio) >= 32767).sum())
            print(f"  Audio: {len(audio)/SAMPLE_RATE:.1f}s, peak={peak}, rms={rms_level:.0f}, clip={clip}")
        recordings.append((rep, audio))
        time.sleep(0.5)

    return recordings
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PipelineResult:
    pipeline: str = ""
    speech_detected: bool = False
    speech_start_sample: int = 0
    endpoint_sample: int = 0
    total_samples: int = 0
    speech_start_ms: float = 0.0
    endpoint_ms: float = 0.0
    utterance_ms: float = 0.0
    transcript: str = ""
    last_word_present: bool = False
    cut_final_word: bool = False
    missed_speech: bool = False
    false_endpoint: bool = False
    hangover_count: int = 0
    raw_rms_levels: list = field(default_factory=list)


def run_pipeline_a(audio: np.ndarray, scenario: Scenario) -> PipelineResult:
    """Run RMS detection on captured audio. Replicates voice.py logic."""
    result = PipelineResult(pipeline="A (RMS)")
    result.total_samples = len(audio)

    blocksize = 1024
    calibration_seconds = 0.35
    silence_seconds = 0.55
    noise_floor = 60.0
    speech_margin = 55.0
    speech_noise_ratio = 2.2
    speech_threshold_min = 110.0
    speech_threshold = max(speech_threshold_min, noise_floor * speech_noise_ratio + speech_margin)

    calibration_blocks = max(1, int(calibration_seconds * SAMPLE_RATE / blocksize))
    calibration = []
    prev_floor = noise_floor

    speech_started = False
    speech_start_sample = 0
    last_speech_sample = 0
    frames = []

    for offset in range(0, len(audio), blocksize):
        block = audio[offset:offset + blocksize].astype(np.float32)
        if len(block) < blocksize:
            block = np.pad(block, (0, blocksize - len(block)))

        level = float(np.abs(block).mean())
        block_index = offset // blocksize

        if not speech_started:
            if block_index < calibration_blocks:
                calibration.append(level)
                low_half = sorted(calibration)[:max(1, len(calibration) // 2)]
                measured = sum(low_half) / len(low_half)
                cap = 4.0
                if prev_floor > 0 and measured > prev_floor * cap:
                    measured = prev_floor * cap
                noise_floor = measured
                speech_threshold = max(speech_threshold_min, noise_floor * speech_noise_ratio + speech_margin)
                continue

            if level >= speech_threshold:
                speech_started = True
                speech_start_sample = offset
                last_speech_sample = offset
                result.speech_start_ms = offset * 1000.0 / SAMPLE_RATE
            else:
                noise_floor = noise_floor * 0.95 + level * 0.05
                speech_threshold = max(speech_threshold_min, noise_floor * speech_noise_ratio + speech_margin)
        else:
            if level >= speech_threshold:
                last_speech_sample = offset + blocksize
            else:
                silence_duration_s = (offset - last_speech_sample) / SAMPLE_RATE
                if silence_duration_s >= silence_seconds:
                    break

    result.speech_detected = speech_started

    if speech_started:
        result.endpoint_sample = last_speech_sample
        result.endpoint_ms = last_speech_sample * 1000.0 / SAMPLE_RATE
        result.utterance_ms = result.endpoint_ms - result.speech_start_ms
        result.cut_final_word = False
    else:
        result.missed_speech = True

    return result


# ═══════════════════════════════════════════════════════════════════
# PIPELINE B: Silero VAD
# ═══════════════════════════════════════════════════════════════════

async def run_pipeline_b(audio: np.ndarray, scenario: Scenario) -> PipelineResult:
    """Run Silero VAD on captured audio."""
    result = PipelineResult(pipeline="B (Silero)")
    result.total_samples = len(audio)

    vad = SileroVADAdapter(
        speech_threshold=0.3,
        endpoint_ms=VAD_ENDPOINT_MS_DEFAULT,
        speech_start_windows=3,
    )
    await vad.load()

    speech_started = False
    speech_start_sample = 0
    endpoint_sample = 0
    sample_offset = 0

    for frame_bytes in _iter_frames(audio, FRAME_SAMPLES):
        event = await vad.feed(frame_bytes)

        if event == VADEvent.SPEECH_STARTED and not speech_started:
            speech_started = True
            speech_start_sample = sample_offset
            result.speech_start_ms = sample_offset * 1000.0 / SAMPLE_RATE

        elif event == VADEvent.ENDPOINT and speech_started:
            endpoint_sample = sample_offset + FRAME_SAMPLES
            break

        sample_offset += FRAME_SAMPLES

    result.speech_detected = speech_started

    if speech_started:
        if endpoint_sample > 0:
            result.endpoint_sample = endpoint_sample
            result.endpoint_ms = endpoint_sample * 1000.0 / SAMPLE_RATE
        else:
            result.endpoint_sample = len(audio)
            result.endpoint_ms = len(audio) * 1000.0 / SAMPLE_RATE
            result.cut_final_word = True
        result.utterance_ms = result.endpoint_ms - result.speech_start_ms
    else:
        result.missed_speech = True

    await vad.unload()
    return result


# ═══════════════════════════════════════════════════════════════════
# PIPELINE H: Hybrid (Silero + hangover)
# ═══════════════════════════════════════════════════════════════════

async def run_pipeline_h(audio: np.ndarray, scenario: Scenario,
                         hangover_ms: int = HYBRID_HANGOVER_MS_DEFAULT) -> PipelineResult:
    """Run Hybrid endpoint on captured audio."""
    result = PipelineResult(pipeline=f"H (Hybrid {hangover_ms}ms)")
    result.total_samples = len(audio)

    vad = SileroVADAdapter(
        speech_threshold=0.3,
        endpoint_ms=VAD_ENDPOINT_MS_DEFAULT,
        speech_start_windows=3,
    )

    sim_time = [0.0]
    def sim_monotonic():
        return sim_time[0]

    hybrid = HybridEndpoint(
        hangover_ms=hangover_ms,
        rms_threshold=300.0,
        time_fn=sim_monotonic,
    )

    await vad.load()

    speech_started = False
    speech_start_sample = 0
    endpoint_sample = 0
    sample_offset = 0

    for frame_bytes in _iter_frames(audio, FRAME_SAMPLES):
        sim_time[0] += FRAME_DURATION_MS / 1000.0

        if not hybrid.in_hangover:
            event = await vad.feed(frame_bytes)
        else:
            event = None

        if event == VADEvent.SPEECH_STARTED and not speech_started:
            speech_started = True
            speech_start_sample = sample_offset
            result.speech_start_ms = sample_offset * 1000.0 / SAMPLE_RATE
            hybrid.on_speech_started()

        elif event == VADEvent.ENDPOINT and speech_started:
            hybrid_evt = hybrid.on_endpoint_candidate(frame_bytes)
            if hybrid_evt == HybridEvent.ENDPOINT:
                endpoint_sample = sample_offset + FRAME_SAMPLES
                break

        if hybrid.in_hangover:
            energy = hybrid_rms_energy(frame_bytes)
            hybrid_evt = hybrid.feed_hangover(frame_bytes, energy)
            result.hangover_count += 1
            if hybrid_evt == HybridEvent.ENDPOINT:
                endpoint_sample = sample_offset + FRAME_SAMPLES
                break

        sample_offset += FRAME_SAMPLES

    result.speech_detected = speech_started

    if speech_started:
        if endpoint_sample > 0:
            result.endpoint_sample = endpoint_sample
            result.endpoint_ms = endpoint_sample * 1000.0 / SAMPLE_RATE
        else:
            result.endpoint_sample = len(audio)
            result.endpoint_ms = len(audio) * 1000.0 / SAMPLE_RATE
            result.cut_final_word = True
        result.utterance_ms = result.endpoint_ms - result.speech_start_ms
    else:
        result.missed_speech = True

    await vad.unload()
    return result


# ═══════════════════════════════════════════════════════════════════
# STT
# ═══════════════════════════════════════════════════════════════════

_stt_model = None

def get_stt_model():
    global _stt_model
    if _stt_model is None:
        from faster_whisper import WhisperModel
        model_name = os.getenv("JARVIS_WHISPER_MODEL", "small")
        compute = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
        _stt_model = WhisperModel(model_name, device="cpu", compute_type=compute)
    return _stt_model


def transcribe(audio: np.ndarray) -> str:
    """Transcribe audio to text using Whisper."""
    model = get_stt_model()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    tmp = Path(__file__).parent / "_tmp_mic_audio.wav"
    tmp.write_bytes(buf.getvalue())

    try:
        segments, info = model.transcribe(
            str(tmp),
            language="pt",
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments)
        return text.strip()
    finally:
        tmp.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

FRAME_DURATION_MS = FRAME_SAMPLES * 1000 // SAMPLE_RATE


def _iter_frames(audio: np.ndarray, frame_samples: int):
    """Yield fixed-size frames from audio array."""
    for offset in range(0, len(audio), frame_samples):
        chunk = audio[offset:offset + frame_samples]
        if len(chunk) < frame_samples:
            chunk = np.pad(chunk, (0, frame_samples - len(chunk)))
        yield chunk.tobytes()


def check_last_word(transcript: str, last_word: str) -> bool:
    """Check if last word of phrase appears in transcript."""
    return last_word.lower() in transcript.lower()


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def process_single_rep(audio: np.ndarray, scenario: Scenario, rep: int) -> dict:
    """Process one recorded audio through A/B/H + STT."""
    peak = int(np.abs(audio).max())
    rms_level = float(np.abs(audio.astype(np.float32)).mean())

    # Run all three pipelines on same audio
    print(f"  Rep {rep+1} - Rodando RMS...", end="", flush=True)
    t0 = time.perf_counter()
    ra = run_pipeline_a(audio, scenario)
    ra_ms = (time.perf_counter() - t0) * 1000
    print(f" {ra_ms:.0f}ms")

    print(f"  Rep {rep+1} - Rodando Silero...", end="", flush=True)
    t0 = time.perf_counter()
    rb = await run_pipeline_b(audio, scenario)
    rb_ms = (time.perf_counter() - t0) * 1000
    print(f" {rb_ms:.0f}ms")

    print(f"  Rep {rep+1} - Rodando Hybrid...", end="", flush=True)
    t0 = time.perf_counter()
    rh = await run_pipeline_h(audio, scenario)
    rh_ms = (time.perf_counter() - t0) * 1000
    print(f" {rh_ms:.0f}ms")

    # STT
    print(f"  Rep {rep+1} - Transcrevendo...", end="", flush=True)
    t0 = time.perf_counter()
    transcript = transcribe(audio)
    stt_ms = (time.perf_counter() - t0) * 1000
    print(f" {stt_ms:.0f}ms")

    # Check last word
    last_word_ok = check_last_word(transcript, scenario.last_word)
    ra.last_word_present = last_word_ok
    rb.last_word_present = last_word_ok
    rh.last_word_present = last_word_ok
    ra.transcript = transcript
    rb.transcript = transcript
    rh.transcript = transcript

    # Print results
    print(f"\n  Transcricao: \"{transcript}\"")
    print(f"  Ultima palavra '{scenario.last_word}': {'OK' if last_word_ok else 'FALTANDO'}")
    print()
    print(f"  {'Pipeline':<20} {'Speech Start':>12} {'Endpoint':>12} {'Utterance':>12} {'Cuts':>6} {'Hangover':>8}")
    print(f"  {'-'*72}")
    for r in [ra, rb, rh]:
        if r.speech_detected:
            cut = "SIM" if r.cut_final_word else "nao"
            hang = str(r.hangover_count) if r.pipeline.startswith("H") else "-"
            print(f"  {r.pipeline:<20} {r.speech_start_ms:>10.0f}ms {r.endpoint_ms:>10.0f}ms {r.utterance_ms:>10.0f}ms {cut:>6} {hang:>8}")
        else:
            print(f"  {r.pipeline:<20} {'MISSED':>12}")

    return {
        "scenario": scenario.name,
        "rep": rep,
        "transcript": transcript,
        "last_word_ok": last_word_ok,
        "a": ra, "b": rb, "h": rh,
    }


async def process_scenario(recordings: list[tuple[int, Optional[np.ndarray]]], scenario: Scenario) -> list[dict]:
    """Process all recorded audio for a scenario through async pipelines."""
    results = []
    for rep, audio in recordings:
        if audio is None:
            continue
        r = await process_single_rep(audio, scenario, rep)
        results.append(r)
    return results


def run_scenario_full(scenario: Scenario, reps: int) -> list[dict]:
    """Record all reps synchronously, then process async."""
    import asyncio

    print(f"\n{'='*60}")
    print(f"Cenario {scenario.id}: {scenario.name}")
    print(f"Frase: \"{scenario.phrase}\"")
    print(f"Descricao: {scenario.description}")
    print(f"Repeticoes: {reps}")
    print(f"{'='*60}")

    # Phase 1: Record all audio synchronously
    print("\n--- FASE 1: Gravacao (sincrono) ---")
    recordings = record_all_reps(scenario, reps)

    # Phase 2: Process all audio async (single event loop)
    print("\n--- FASE 2: Processamento (async) ---")
    results = asyncio.run(process_scenario(recordings, scenario))

    return results


def print_summary(all_results: dict):
    """Print aggregated summary across all scenarios and reps."""
    import numpy as np

    print(f"\n{'='*70}")
    print("RESUMO GERAL — P1.4A.2 REAL MIC VALIDATION")
    print(f"{'='*70}")

    for scenario in SCENARIOS:
        results = all_results.get(scenario.id, [])
        if not results:
            continue

        print(f"\n-- Cenario {scenario.id}: {scenario.name} ({len(results)} reps) --")

        for pipeline_key, pipeline_name in [("a", "A (RMS)"), ("b", "B (Silero)"), ("h", "H (Hybrid)")]:
            starts = [r[pipeline_key].speech_start_ms for r in results if r[pipeline_key].speech_detected]
            endpoints = [r[pipeline_key].endpoint_ms for r in results if r[pipeline_key].speech_detected]
            utterances = [r[pipeline_key].utterance_ms for r in results if r[pipeline_key].speech_detected]
            cuts = sum(1 for r in results if r[pipeline_key].cut_final_word)
            missed = sum(1 for r in results if r[pipeline_key].missed_speech)
            last_word = sum(1 for r in results if r[pipeline_key].last_word_present)

            if starts:
                p50_start = np.percentile(starts, 50)
                p50_end = np.percentile(endpoints, 50)
                p50_utt = np.percentile(utterances, 50)
                print(f"  {pipeline_name}: start_p50={p50_start:.0f}ms endpoint_p50={p50_end:.0f}ms "
                      f"utt_p50={p50_utt:.0f}ms cuts={cuts} missed={missed} last_word={last_word}/{len(results)}")
            else:
                print(f"  {pipeline_name}: MISSED all reps")

    # Overall
    print(f"\n-- GERAL --")
    for pipeline_key, pipeline_name in [("a", "A (RMS)"), ("b", "B (Silero)"), ("h", "H (Hybrid)")]:
        all_starts = []
        all_endpoints = []
        all_utt = []
        total_cuts = 0
        total_missed = 0
        total_last_word = 0
        total_reps = 0

        for results in all_results.values():
            for r in results:
                total_reps += 1
                p = r[pipeline_key]
                if p.speech_detected:
                    all_starts.append(p.speech_start_ms)
                    all_endpoints.append(p.endpoint_ms)
                    all_utt.append(p.utterance_ms)
                if p.cut_final_word:
                    total_cuts += 1
                if p.missed_speech:
                    total_missed += 1
                if p.last_word_present:
                    total_last_word += 1

        if all_starts:
            print(f"  {pipeline_name}: start_p50={np.percentile(all_starts,50):.0f}ms "
                  f"endpoint_p50={np.percentile(all_endpoints,50):.0f}ms "
                  f"utt_p50={np.percentile(all_utt,50):.0f}ms "
                  f"cuts={total_cuts}/{total_reps} missed={total_missed}/{total_reps} "
                  f"last_word={total_last_word}/{total_reps}")
        else:
            print(f"  {pipeline_name}: no speech detected")


def main():
    parser = argparse.ArgumentParser(description="P1.4A.2 Real Mic Endpointing Validation")
    parser.add_argument("--scenario", type=int, help="Run specific scenario (1-8)")
    parser.add_argument("--reps", type=int, default=5, help="Repetitions per scenario (default: 5)")
    args = parser.parse_args()

    print("=" * 60)
    print("P1.4A.2 — REAL MICROPHONE ENDPOINTING VALIDATION")
    print("=" * 60)
    print("Gravação neutra: janela fixa, sem VAD.")
    print("Mesmo buffer para A/B/H.")
    print()

    # Show device info
    try:
        import sounddevice as sd
        dev = sd.query_devices(sd.default.device[0])
        print(f"Dispositivo: {dev['name']}")
        print(f"Sample rate: 16000 Hz")
    except Exception as e:
        print(f"Aviso: {e}")

    if args.scenario:
        scenarios_to_run = [s for s in SCENARIOS if s.id == args.scenario]
        if not scenarios_to_run:
            print(f"Cenário {args.scenario} não encontrado.")
            return
    else:
        print("\nCenários disponíveis:")
        for s in SCENARIOS:
            print(f"  {s.id}. {s.name}: \"{s.phrase}\"")
        print(f"  0. TODOS")
        choice = input("\nSelecione cenário (0-8): ").strip()
        if choice == "0":
            scenarios_to_run = SCENARIOS
        else:
            try:
                cid = int(choice)
                scenarios_to_run = [s for s in SCENARIOS if s.id == cid]
            except ValueError:
                print("Entrada inválida.")
                return

    all_results = {}
    for scenario in scenarios_to_run:
        results = run_scenario_full(scenario, args.reps)
        all_results[scenario.id] = results

    print_summary(all_results)

    print("\n" + "=" * 60)
    print("VALIDAÇÃO CONCLUÍDA")
    print("Feature flags JARVIS_REALTIME_VOICE_V2 e JARVIS_HYBRID_ENDPOINT continuam OFF.")
    print("Nenhuma alteração em produção.")
    print("=" * 60)


if __name__ == "__main__":
    main()
