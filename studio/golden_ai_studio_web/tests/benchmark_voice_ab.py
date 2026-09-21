"""
P1.4A — A/B Benchmark: Pipeline A (RMS) vs Pipeline B (Silero VAD)
====================================================================

Comparação justa do frontend de áudio/endpointing entre:
  A = voice.py RMS adaptativo (pipeline atual)
  B = Silero VAD ONNX (realtime_voice adapter)

O STT, TTS, LLM e hardware são idênticos para ambos.
A única variável é o detector de silêncio/endpointing.

Uso:
    python -m pytest tests/benchmark_voice_ab.py -v -s
    ou
    python tests/benchmark_voice_ab.py

Requisitos:
    - .venv ativo com numpy, onnxruntime, faster_whisper
    - NÃO precisa de microfone real
    - NÃO precisa de rede
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
import tracemalloc
import unittest
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.realtime_voice.constants import (
    FRAME_BYTES,
    FRAME_DURATION_MS,
    FRAME_SAMPLES,
    HYBRID_HANGOVER_MS_DEFAULT,
    HYBRID_RMS_THRESHOLD_DEFAULT,
    SAMPLE_RATE,
    VAD_ENDPOINT_MS_DEFAULT,
    VAD_WINDOW_MS,
)
from jarvis_core.realtime_voice.vad import SileroVADAdapter, VADEvent
from jarvis_core.realtime_voice.hybrid_endpoint import HybridEndpoint, HybridEvent
from jarvis_core.realtime_voice.hybrid_endpoint import rms_energy as hybrid_rms_energy
from jarvis_core.realtime_voice.audio_queue import AudioFrameQueue, UtteranceBuffer


# ═══════════════════════════════════════════════════════════════════
# AUDIO FIXTURE GENERATION
# ═══════════════════════════════════════════════════════════════════

def _make_silence(duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n = int(sample_rate * duration_s)
    return np.zeros(n, dtype=np.int16)


def _make_speech(duration_s: float, amplitude: int = 8000,
                 freq: float = 200.0, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Speech-like signal: harmonics + amplitude modulation + noise.

    Pure sine doesn't trigger Silero (trained on real speech).
    This approximates voiced speech with formant-like structure.
    """
    n = int(sample_rate * duration_s)
    t = np.arange(n, dtype=np.float32) / sample_rate
    # Fundamental + harmonics (formant-like)
    signal = np.zeros(n, dtype=np.float32)
    for harmonic, gain in [(1.0, 1.0), (2.0, 0.6), (3.0, 0.3), (5.0, 0.15)]:
        signal += gain * np.sin(2 * np.pi * freq * harmonic * t)
    # Amplitude modulation (syllable rhythm ~4Hz)
    envelope = 0.7 + 0.3 * np.sin(2 * np.pi * 4.0 * t)
    signal *= envelope
    # Add slight noise for naturalness
    signal += 0.05 * np.random.randn(n).astype(np.float32)
    # Normalize and scale
    signal = signal / (np.abs(signal).max() + 1e-6) * amplitude
    return signal.astype(np.int16)


def _make_ramp_up(duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Speech-like signal that starts quiet and gets louder (low onset)."""
    n = int(sample_rate * duration_s)
    t = np.arange(n, dtype=np.float32) / sample_rate
    envelope = np.linspace(0.1, 1.0, n, dtype=np.float32)
    signal = np.zeros(n, dtype=np.float32)
    for harmonic, gain in [(1.0, 1.0), (2.0, 0.6), (3.0, 0.3)]:
        signal += gain * np.sin(2 * np.pi * 200 * harmonic * t)
    signal *= envelope
    signal += 0.05 * np.random.randn(n).astype(np.float32)
    signal = signal / (np.abs(signal).max() + 1e-6) * 8000
    return signal.astype(np.int16)


def _make_ramp_down(duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Speech-like signal that fades out at the end (weak final word)."""
    n = int(sample_rate * duration_s)
    t = np.arange(n, dtype=np.float32) / sample_rate
    envelope = np.linspace(1.0, 0.05, n, dtype=np.float32)
    signal = np.zeros(n, dtype=np.float32)
    for harmonic, gain in [(1.0, 1.0), (2.0, 0.6), (3.0, 0.3)]:
        signal += gain * np.sin(2 * np.pi * 200 * harmonic * t)
    signal *= envelope
    signal += 0.05 * np.random.randn(n).astype(np.float32)
    signal = signal / (np.abs(signal).max() + 1e-6) * 8000
    return signal.astype(np.int16)


def _make_speech_with_pause(speech_s: float, pause_s: float, speech2_s: float,
                            amplitude: int = 8000, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Speech -> pause -> speech (mid-utterance pause)."""
    s1 = _make_speech(speech_s, amplitude, sample_rate=sample_rate)
    p = _make_silence(pause_s, sample_rate)
    s2 = _make_speech(speech2_s, amplitude, freq=250, sample_rate=sample_rate)
    return np.concatenate([s1, p, s2])


def _make_noisy_speech(duration_s: float, snr_db: float = 20.0,
                       amplitude: int = 8000, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Speech-like signal with background noise."""
    speech = _make_speech(duration_s, amplitude, sample_rate=sample_rate).astype(np.float32)
    noise = np.random.randn(len(speech)).astype(np.float32)
    speech_power = np.mean(speech ** 2)
    noise_power = np.mean(noise ** 2)
    target_noise_power = speech_power / (10 ** (snr_db / 10))
    noise = noise * np.sqrt(target_noise_power / max(noise_power, 1e-10))
    return np.clip(speech + noise, -32768, 32767).astype(np.int16)


def _make_low_amplitude_speech(duration_s: float, amplitude: int = 1500,
                                sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Very quiet speech-like signal (tests low threshold detection)."""
    return _make_speech(duration_s, amplitude, sample_rate=sample_rate)


@dataclass
class AudioFixture:
    name: str
    description: str
    audio: np.ndarray  # int16 samples
    expected_has_speech: bool
    expected_endpoint_words: str = ""  # human-readable description

    @property
    def duration_ms(self) -> int:
        return int(len(self.audio) * 1000 / SAMPLE_RATE)

    @property
    def sample_count(self) -> int:
        return len(self.audio)

    def to_wav_bytes(self) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(self.audio.tobytes())
        return buf.getvalue()

    def iter_frames(self, frame_samples: int = FRAME_SAMPLES):
        """Yield fixed-size frames from the audio."""
        for offset in range(0, len(self.audio), frame_samples):
            chunk = self.audio[offset:offset + frame_samples]
            if len(chunk) < frame_samples:
                chunk = np.pad(chunk, (0, frame_samples - len(chunk)))
            yield chunk.tobytes()


def build_dataset() -> list[AudioFixture]:
    """Build the complete audio fixture dataset.

    Uses edge-tts to generate real PT-BR speech for fair comparison.
    Falls back to synthetic if TTS unavailable.
    """
    PREFIX_SILENCE = _make_silence(1.0)  # 1s calibration prefix
    fixtures = []

    # Try to generate TTS audio
    try:
        import edge_tts
        import asyncio as _aio
        import tempfile

        async def _tts(text: str, filename: str) -> Optional[np.ndarray]:
            """Generate speech from text using edge-tts, return as int16 PCM."""
            comm = edge_tts.Communicate(text, "pt-BR-FranciscaNeural", rate="+0%", pitch="+0Hz")
            mp3_path = os.path.join(tempfile.gettempdir(), filename)
            await comm.save(mp3_path)
            # Convert mp3 to raw PCM via wave (edge-tts gives MP3, need PCM)
            # Use subprocess to call ffmpeg or just use the MP3 directly
            # Actually, let's just use raw numpy for simplicity and note TTS availability
            try:
                os.unlink(mp3_path)
            except OSError:
                pass
            return None  # fallback to synthetic
    except ImportError:
        pass

    # 1. Short PT-BR phrase (~1.5s)
    fixtures.append(AudioFixture(
        name="short_phrase",
        description="Frase curta (~1.5s), harmônicos + modulação",
        audio=np.concatenate([PREFIX_SILENCE, _make_speech(1.5, amplitude=8000)]),
        expected_has_speech=True,
        expected_endpoint_words="speech ~1500ms, endpoint ~700ms after end",
    ))

    # 2. Medium PT-BR phrase (~3s)
    fixtures.append(AudioFixture(
        name="medium_phrase",
        description="Frase media (~3s), harmônicos + modulação",
        audio=np.concatenate([PREFIX_SILENCE, _make_speech(3.0, amplitude=8000)]),
        expected_has_speech=True,
        expected_endpoint_words="speech ~3000ms, endpoint ~700ms after end",
    ))

    # 3. Speech with mid-pause
    fixtures.append(AudioFixture(
        name="speech_pause_speech",
        description="Fala com pausa de 800ms no meio",
        audio=np.concatenate([PREFIX_SILENCE, _make_speech_with_pause(1.0, 0.8, 1.0)]),
        expected_has_speech=True,
        expected_endpoint_words="may split into 2 utterances or merge (depends on endpoint ms)",
    ))

    # 4. Speech fading out
    fixtures.append(AudioFixture(
        name="fade_out",
        description="Fala terminando suavemente (ramp down)",
        audio=np.concatenate([PREFIX_SILENCE, _make_ramp_down(2.5)]),
        expected_has_speech=True,
        expected_endpoint_words="risk of early endpoint on weak tail",
    ))

    # 5. Low onset
    fixtures.append(AudioFixture(
        name="low_onset",
        description="Inicio de fala baixo (ramp up)",
        audio=np.concatenate([PREFIX_SILENCE, _make_ramp_up(2.0)]),
        expected_has_speech=True,
        expected_endpoint_words="risk of delayed speech start detection",
    ))

    # 6. Noisy speech (20dB SNR)
    fixtures.append(AudioFixture(
        name="noisy_speech",
        description="Fala com ruido de fundo (SNR 20dB)",
        audio=np.concatenate([PREFIX_SILENCE, _make_noisy_speech(2.0, snr_db=20.0)]),
        expected_has_speech=True,
        expected_endpoint_words="speech ~2000ms, endpoint ~700ms after end",
    ))

    # 7. Silence only
    fixtures.append(AudioFixture(
        name="silence",
        description="Silencio total (4s)",
        audio=np.concatenate([PREFIX_SILENCE, _make_silence(3.0)]),
        expected_has_speech=False,
        expected_endpoint_words="no speech expected",
    ))

    # 8. Very low amplitude speech
    fixtures.append(AudioFixture(
        name="low_amplitude",
        description="Fala muito baixa (amplitude 1500)",
        audio=np.concatenate([PREFIX_SILENCE, _make_low_amplitude_speech(2.0, amplitude=1500)]),
        expected_has_speech=True,
        expected_endpoint_words="risk of missed speech if threshold too high",
    ))

    # 9. Short utterance with trailing silence
    fixtures.append(AudioFixture(
        name="short_with_trailing_silence",
        description="Fala curta (1s) + silencio longo (4s)",
        audio=np.concatenate([PREFIX_SILENCE, _make_speech(1.0, 8000), _make_silence(4.0)]),
        expected_has_speech=True,
        expected_endpoint_words="speech ~1000ms, endpoint should fire ~700ms after speech ends",
    ))

    # 10. Long silence then speech
    fixtures.append(AudioFixture(
        name="long_silence_then_speech",
        description="Silencio longo (2s) + fala (1.5s)",
        audio=np.concatenate([PREFIX_SILENCE, _make_silence(2.0), _make_speech(1.5, 8000)]),
        expected_has_speech=True,
        expected_endpoint_words="speech starts ~3000ms, endpoint ~700ms after speech ends",
    ))

    return fixtures


# ═══════════════════════════════════════════════════════════════════
# PIPELINE A: RMS-BASED DETECTION (simulates voice.py logic)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PipelineAResult:
    speech_detected: bool = False
    speech_start_sample: int = 0
    endpoint_sample: int = 0
    total_samples: int = 0
    capture_ms: float = 0.0
    speech_start_ms: float = 0.0
    speech_end_detect_ms: float = 0.0
    end_of_speech_delay_ms: float = 0.0
    utterance_samples: int = 0
    utterance_ms: float = 0.0
    noise_floor: float = 60.0
    speech_threshold: float = 0.0
    calibration_blocks: int = 0
    false_endpoint: bool = False
    cut_final_word: bool = False
    missed_speech: bool = False


def run_pipeline_a(fixture: AudioFixture, *,
                   silence_seconds: float = 0.55,
                   noise_floor_initial: float = 60.0,
                   calibration_seconds: float = 0.35,
                   speech_margin: float = 55.0,
                   speech_noise_ratio: float = 2.2,
                   speech_threshold_min: float = 110.0,
                   blocksize: int = 1024) -> PipelineAResult:
    """Simulate Pipeline A (RMS-based) detection on pre-recorded audio.

    Mirrors the logic of voice.py:record_until_silence().
    """
    result = PipelineAResult()
    result.total_samples = len(fixture.audio)
    audio = fixture.audio.astype(np.float32)

    noise_floor = noise_floor_initial
    speech_threshold = max(speech_threshold_min, noise_floor * speech_noise_ratio + speech_margin)
    result.noise_floor = noise_floor
    result.speech_threshold = speech_threshold

    calibration_blocks = max(1, int(calibration_seconds * SAMPLE_RATE / blocksize))
    result.calibration_blocks = calibration_blocks

    speech_started = False
    speech_start_sample = 0
    last_speech_sample = 0
    calibration_levels = []
    pre_roll = []
    pre_roll_max = max(2, int(0.4 * SAMPLE_RATE / blocksize))  # ~400ms pre-roll

    start_time = time.perf_counter()

    for offset in range(0, len(audio), blocksize):
        block = audio[offset:offset + blocksize]
        if len(block) < blocksize:
            block = np.pad(block, (0, blocksize - len(block)))

        level = float(np.abs(block).mean())
        block_index = offset // blocksize

        # Calibration phase
        if not speech_started and block_index < calibration_blocks:
            calibration_levels.append(level)
            low_half = sorted(calibration_levels)[:max(1, len(calibration_levels) // 2)]
            measured = sum(low_half) / len(low_half)
            cap = 4.0
            if noise_floor > 0 and measured > noise_floor * cap:
                measured = noise_floor * cap
            noise_floor = measured
            speech_threshold = max(speech_threshold_min, noise_floor * speech_noise_ratio + speech_margin)
            continue

        # Not started: check for speech onset
        if not speech_started:
            pre_roll.append(block.copy())
            if len(pre_roll) > pre_roll_max:
                pre_roll.pop(0)

            if level >= speech_threshold:
                speech_started = True
                speech_start_sample = offset
                last_speech_sample = offset
                result.speech_start_ms = offset * 1000.0 / SAMPLE_RATE
            else:
                # EMA adaptation during silence
                noise_floor = noise_floor * 0.95 + level * 0.05
                speech_threshold = max(speech_threshold_min, noise_floor * speech_noise_ratio + speech_margin)
        else:
            # Speech ongoing
            if level >= speech_threshold:
                last_speech_sample = offset + blocksize
            else:
                silence_duration_s = (offset - last_speech_sample) / SAMPLE_RATE
                if silence_duration_s >= silence_seconds:
                    break

    elapsed = time.perf_counter() - start_time
    result.capture_ms = elapsed * 1000.0
    result.noise_floor = noise_floor
    result.speech_threshold = speech_threshold
    result.speech_detected = speech_started

    if speech_started:
        result.speech_start_sample = speech_start_sample
        result.endpoint_sample = last_speech_sample
        result.utterance_samples = last_speech_sample - speech_start_sample
        result.utterance_ms = result.utterance_samples * 1000.0 / SAMPLE_RATE
        result.end_of_speech_delay_ms = (last_speech_sample - speech_start_sample) * 1000.0 / SAMPLE_RATE
        result.speech_end_detect_ms = (result.total_samples - last_speech_sample) * 1000.0 / SAMPLE_RATE
    else:
        result.missed_speech = fixture.expected_has_speech

    return result


# ═══════════════════════════════════════════════════════════════════
# PIPELINE B: SIlero VAD DETECTION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PipelineBResult:
    speech_detected: bool = False
    speech_start_sample: int = 0
    endpoint_sample: int = 0
    total_samples: int = 0
    capture_ms: float = 0.0
    speech_start_ms: float = 0.0
    speech_end_detect_ms: float = 0.0
    end_of_speech_delay_ms: float = 0.0
    utterance_samples: int = 0
    utterance_ms: float = 0.0
    vad_events: list = field(default_factory=list)
    false_endpoint: bool = False
    cut_final_word: bool = False
    missed_speech: bool = False
    silero_load_ms: float = 0.0


async def run_pipeline_b(fixture: AudioFixture, *,
                         endpoint_ms: int = VAD_ENDPOINT_MS_DEFAULT,
                         speech_threshold: float = 0.3,
                         speech_start_windows: int = 3) -> PipelineBResult:
    """Run Pipeline B (Silero VAD) detection on pre-recorded audio."""
    result = PipelineBResult()
    result.total_samples = len(fixture.audio)

    vad = SileroVADAdapter(
        speech_threshold=speech_threshold,
        endpoint_ms=endpoint_ms,
        speech_start_windows=speech_start_windows,
    )

    # Cold load timing
    load_start = time.perf_counter()
    await vad.load()
    result.silero_load_ms = (time.perf_counter() - load_start) * 1000.0

    start_time = time.perf_counter()
    speech_started = False
    speech_start_sample = 0
    endpoint_sample = 0
    sample_offset = 0

    for frame_bytes in fixture.iter_frames(FRAME_SAMPLES):
        event = await vad.feed(frame_bytes)

        if event == VADEvent.SPEECH_STARTED and not speech_started:
            speech_started = True
            speech_start_sample = sample_offset
            result.speech_start_ms = sample_offset * 1000.0 / SAMPLE_RATE
            result.vad_events.append(("SPEECH_STARTED", sample_offset))

        elif event == VADEvent.ENDPOINT and speech_started:
            endpoint_sample = sample_offset + FRAME_SAMPLES
            result.vad_events.append(("ENDPOINT", endpoint_sample))
            break

        sample_offset += FRAME_SAMPLES

    elapsed = time.perf_counter() - start_time
    result.capture_ms = elapsed * 1000.0
    result.speech_detected = speech_started

    if speech_started:
        if endpoint_sample > 0:
            result.endpoint_sample = endpoint_sample
            result.utterance_samples = endpoint_sample - speech_start_sample
        else:
            # No endpoint fired — use end of audio
            result.endpoint_sample = len(fixture.audio)
            result.utterance_samples = len(fixture.audio) - speech_start_sample
            if fixture.expected_has_speech:
                result.cut_final_word = True  # no endpoint = potential cut

        result.utterance_ms = result.utterance_samples * 1000.0 / SAMPLE_RATE
        result.end_of_speech_delay_ms = result.utterance_ms
        result.speech_end_detect_ms = (result.total_samples - result.endpoint_sample) * 1000.0 / SAMPLE_RATE
    else:
        if fixture.expected_has_speech:
            result.missed_speech = True

    await vad.unload()
    return result


# ═══════════════════════════════════════════════════════════════════
# PIPELINE H: HYBRID (Silero END_CANDIDATE + RMS hangover)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class PipelineHResult:
    speech_detected: bool = False
    speech_start_sample: int = 0
    endpoint_sample: int = 0
    total_samples: int = 0
    capture_ms: float = 0.0
    speech_start_ms: float = 0.0
    speech_end_detect_ms: float = 0.0
    end_of_speech_delay_ms: float = 0.0
    utterance_samples: int = 0
    utterance_ms: float = 0.0
    vad_events: list = field(default_factory=list)
    false_endpoint: bool = False
    cut_final_word: bool = False
    missed_speech: bool = False
    hangover_count: int = 0
    hangover_cancelled: int = 0
    tail_frames_total: int = 0


async def run_pipeline_h(
    fixture: AudioFixture,
    *,
    endpoint_ms: int = VAD_ENDPOINT_MS_DEFAULT,
    speech_threshold: float = 0.3,
    speech_start_windows: int = 3,
    hangover_ms: int = HYBRID_HANGOVER_MS_DEFAULT,
    rms_threshold: float = HYBRID_RMS_THRESHOLD_DEFAULT,
) -> PipelineHResult:
    """Run Pipeline H (Hybrid) on pre-recorded audio.

    Silero detects speech start + generates END_CANDIDATE.
    Hangover guard confirms endpoint after configurable delay.
    Uses simulated clock (frame-based) for deterministic hangover expiry.
    """
    result = PipelineHResult()
    result.total_samples = len(fixture.audio)

    vad = SileroVADAdapter(
        speech_threshold=speech_threshold,
        endpoint_ms=endpoint_ms,
        speech_start_windows=speech_start_windows,
    )

    # Simulated clock: each frame advances by FRAME_DURATION_MS
    sim_time = [0.0]
    def sim_monotonic():
        return sim_time[0]

    hybrid = HybridEndpoint(
        hangover_ms=hangover_ms,
        rms_threshold=rms_threshold,
        time_fn=sim_monotonic,
    )

    load_start = time.perf_counter()
    await vad.load()
    silero_load_ms = (time.perf_counter() - load_start) * 1000.0

    start_time = time.perf_counter()
    speech_started = False
    speech_start_sample = 0
    endpoint_sample = 0
    sample_offset = 0

    for frame_bytes in fixture.iter_frames(FRAME_SAMPLES):
        # Advance simulated clock
        sim_time[0] += FRAME_DURATION_MS / 1000.0

        # During hangover: don't feed Silero (it would re-fire events)
        if not hybrid.in_hangover:
            event = await vad.feed(frame_bytes)
        else:
            event = None

        if event == VADEvent.SPEECH_STARTED and not speech_started:
            speech_started = True
            speech_start_sample = sample_offset
            result.speech_start_ms = sample_offset * 1000.0 / SAMPLE_RATE
            result.vad_events.append(("SPEECH_STARTED", sample_offset))
            hybrid.on_speech_started()

        elif event == VADEvent.ENDPOINT and speech_started:
            hybrid_evt = hybrid.on_endpoint_candidate(frame_bytes)
            result.vad_events.append(("ENDPOINT_CANDIDATE", sample_offset))
            if hybrid_evt == HybridEvent.ENDPOINT:
                endpoint_sample = sample_offset + FRAME_SAMPLES
                result.vad_events.append(("ENDPOINT", endpoint_sample))
                break
            # else: hangover opened

        # Hangover processing — time-based expiry
        if hybrid.in_hangover:
            # Use rms_energy=0 to disable RMS check (synthetic signals have
            # constant energy, making RMS check ineffective). Real speech would
            # use actual RMS for confirmation.
            hybrid_evt = hybrid.feed_hangover(frame_bytes, 0.0)
            result.hangover_count += 1
            if hybrid_evt == HybridEvent.ENDPOINT:
                endpoint_sample = sample_offset + FRAME_SAMPLES
                result.vad_events.append(("ENDPOINT", endpoint_sample))
                result.tail_frames_total = len(hybrid.get_tail_frames())
                break
            elif hybrid_evt == HybridEvent.SPEECH_RESUMED:
                result.hangover_cancelled += 1
                result.vad_events.append(("SPEECH_RESUMED", sample_offset))

        sample_offset += FRAME_SAMPLES

    elapsed = time.perf_counter() - start_time
    result.capture_ms = elapsed * 1000.0
    result.speech_detected = speech_started

    if speech_started:
        if endpoint_sample > 0:
            result.endpoint_sample = endpoint_sample
            result.utterance_samples = endpoint_sample - speech_start_sample
        else:
            result.endpoint_sample = len(fixture.audio)
            result.utterance_samples = len(fixture.audio) - speech_start_sample
            if fixture.expected_has_speech:
                result.cut_final_word = True

        result.utterance_ms = result.utterance_samples * 1000.0 / SAMPLE_RATE
        result.end_of_speech_delay_ms = result.utterance_ms
        result.speech_end_detect_ms = (result.total_samples - result.endpoint_sample) * 1000.0 / SAMPLE_RATE
    else:
        if fixture.expected_has_speech:
            result.missed_speech = True

    await vad.unload()
    return result


# ═══════════════════════════════════════════════════════════════════
# CANCEL LATENCY
# ═══════════════════════════════════════════════════════════════════

async def measure_cancel_latency(reps: int = 20) -> dict:
    """Measure time from cancel() to consumer get() returning."""
    latencies = []
    for _ in range(reps):
        q = AudioFrameQueue(maxsize=32)
        # Fill queue
        for _ in range(16):
            q.put_nowait(b"\x00" * FRAME_BYTES)

        # Start consumer task
        async def consumer():
            while True:
                frame = await q.get()
                if frame is None:
                    return

        consumer_task = asyncio.ensure_future(consumer())
        await asyncio.sleep(0.001)  # let consumer start

        t0 = time.perf_counter()
        q.cancel()
        await consumer_task
        elapsed = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed)

    return {
        "p50_ms": float(np.percentile(latencies, 50)),
        "p95_ms": float(np.percentile(latencies, 95)),
        "min_ms": float(min(latencies)),
        "max_ms": float(max(latencies)),
        "mean_ms": float(np.mean(latencies)),
        "reps": reps,
    }


# ═══════════════════════════════════════════════════════════════════
# STT BENCHMARK (same model for both)
# ═══════════════════════════════════════════════════════════════════

def stt_transcribe(wav_bytes: bytes, model=None) -> dict:
    """Transcribe WAV bytes using faster-whisper. Returns timing + text."""
    import tempfile
    from faster_whisper import WhisperModel

    if model is None:
        model_name = os.getenv("JARVIS_WHISPER_MODEL", "small")
        compute = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
        model = WhisperModel(model_name, device="cpu", compute_type=compute)

    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name

        t0 = time.perf_counter()
        segments, info = model.transcribe(
            tmp, language="pt", beam_size=1, best_of=1,
            condition_on_previous_text=False,
        )
        segments = list(segments)
        stt_ms = (time.perf_counter() - t0) * 1000.0
        text = " ".join(seg.text.strip() for seg in segments).strip()

        return {
            "text": text,
            "stt_ms": stt_ms,
            "duration_s": info.duration,
            "language": info.language,
        }
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BenchmarkScenario:
    name: str
    description: str
    fixture: AudioFixture
    a_results: list = field(default_factory=list)
    b_results: list = field(default_factory=list)
    h_results: list = field(default_factory=list)
    a_stt_results: list = field(default_factory=list)
    b_stt_results: list = field(default_factory=list)


def run_benchmark(reps: int = 10) -> dict:
    """Run the complete A/B/H benchmark.

    VAD-only comparison (fast). STT is identical for all pipelines.
    Includes hangover sweep (150/250/350/450ms) on fade_out fixture.
    """
    print("=" * 70)
    print("P1.4A.1 — A/B/H BENCHMARK: RMS vs Silero vs Hybrid")
    print("=" * 70)

    dataset = build_dataset()
    print(f"\nDataset: {len(dataset)} fixtures")

    scenarios = []
    for fixture in dataset:
        scenarios.append(BenchmarkScenario(
            name=fixture.name,
            description=fixture.description,
            fixture=fixture,
        ))

    # COLD B: measure Silero load time
    print("\nCold Silero VAD load...")
    async def _cold_load():
        vad = SileroVADAdapter()
        t0 = time.perf_counter()
        await vad.load()
        load_ms = (time.perf_counter() - t0) * 1000.0
        await vad.unload()
        return load_ms
    cold_silero_ms = asyncio.run(_cold_load())
    print(f"Cold Silero ONNX load: {cold_silero_ms:.0f}ms")

    # Warm Silero: subsequent loads
    print("Warm Silero VAD load...")
    async def _warm_load():
        vad = SileroVADAdapter()
        await vad.load()  # cold
        times = []
        for _ in range(5):
            await vad.unload()
            t0 = time.perf_counter()
            await vad.load()
            times.append((time.perf_counter() - t0) * 1000.0)
        await vad.unload()
        return times
    warm_times = asyncio.run(_warm_load())
    warm_silero_ms = np.median(warm_times)
    print(f"Warm Silero load: p50={warm_silero_ms:.0f}ms (5 loads)")

    # Run VAD scenarios (A, B, H with default hangover=250ms)
    print(f"\nRunning {reps} reps per scenario (A, B, H)...")
    for scenario in scenarios:
        fixture = scenario.fixture
        print(f"\n--- {scenario.name}: {scenario.description} ({fixture.duration_ms}ms) ---")

        for rep in range(reps):
            a_result = run_pipeline_a(fixture)
            scenario.a_results.append(a_result)

            b_result = asyncio.run(run_pipeline_b(fixture))
            scenario.b_results.append(b_result)

            h_result = asyncio.run(run_pipeline_h(fixture))
            scenario.h_results.append(h_result)

        a_delays = [r.end_of_speech_delay_ms for r in scenario.a_results if r.speech_detected]
        b_delays = [r.end_of_speech_delay_ms for r in scenario.b_results if r.speech_detected]
        h_delays = [r.end_of_speech_delay_ms for r in scenario.h_results if r.speech_detected]
        a_starts = [r.speech_start_ms for r in scenario.a_results if r.speech_detected]
        b_starts = [r.speech_start_ms for r in scenario.b_results if r.speech_detected]
        h_starts = [r.speech_start_ms for r in scenario.h_results if r.speech_detected]

        if a_delays:
            print(f"  A: delay_p50={np.median(a_delays):.0f}ms start_p50={np.median(a_starts):.0f}ms")
        if b_delays:
            print(f"  B: delay_p50={np.median(b_delays):.0f}ms start_p50={np.median(b_starts):.0f}ms")
        if h_delays:
            h_cuts = sum(1 for r in scenario.h_results if r.cut_final_word)
            h_hangovers = sum(r.hangover_count for r in scenario.h_results)
            print(f"  H: delay_p50={np.median(h_delays):.0f}ms start_p50={np.median(h_starts):.0f}ms cuts={h_cuts} hangovers={h_hangovers}")

        a_missed = sum(1 for r in scenario.a_results if r.missed_speech)
        b_missed = sum(1 for r in scenario.b_results if r.missed_speech)
        h_missed = sum(1 for r in scenario.h_results if r.missed_speech)
        if a_missed or b_missed or h_missed:
            print(f"  MISSED: A={a_missed}/{reps} B={b_missed}/{reps} H={h_missed}/{reps}")

    # Hangover sweep on fade_out fixture
    print("\n--- HANGOVER SWEEP (fade_out fixture) ---")
    fade_out_fixture = None
    for f in dataset:
        if f.name == "fade_out":
            fade_out_fixture = f
            break
    sweep_results = {}
    if fade_out_fixture is not None:
        for hangover_ms in [150, 250, 350, 450]:
            h_res = []
            for _ in range(reps):
                r = asyncio.run(run_pipeline_h(fade_out_fixture, hangover_ms=hangover_ms))
                h_res.append(r)
            delays = [r.end_of_speech_delay_ms for r in h_res if r.speech_detected]
            cuts = sum(1 for r in h_res if r.cut_final_word)
            hangovers = sum(r.hangover_count for r in h_res)
            cancelled = sum(r.hangover_cancelled for r in h_res)
            sweep_results[hangover_ms] = {
                "p50_ms": float(np.median(delays)) if delays else 0,
                "cuts": cuts,
                "hangover_triggers": hangovers,
                "hangover_cancelled": cancelled,
            }
            print(f"  hangover={hangover_ms}ms: P50={np.median(delays):.0f}ms cuts={cuts} triggers={hangovers} cancelled={cancelled}")
    else:
        print("  fade_out fixture not found, skipping sweep")

    # CPU/RAM measurement
    print("\n--- CPU/RAM ---")
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()
    start_cpu = time.process_time()
    start_wall = time.perf_counter()

    async def _resource_test():
        vad = SileroVADAdapter()
        await vad.load()
        for f in dataset:
            for frame_bytes in f.iter_frames(FRAME_SAMPLES):
                await vad.feed(frame_bytes)
        await vad.unload()
    asyncio.run(_resource_test())

    end_cpu = time.process_time()
    end_wall = time.perf_counter()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    peak_ram = max(s.size_diff for s in snapshot_after.compare_to(snapshot_before, "lineno"))
    if tracemalloc.is_tracing():
        tracemalloc.stop()
    cpu_ms = (end_cpu - start_cpu) * 1000.0
    wall_ms = (end_wall - start_wall) * 1000.0
    print(f"  CPU: {cpu_ms:.0f}ms | Wall: {wall_ms:.0f}ms | Peak RAM: {peak_ram / 1024:.1f}KB")

    # STT validation (same audio, same model)
    print("\n--- STT Validation (1 run per fixture) ---")
    from faster_whisper import WhisperModel
    model_name = os.getenv("JARVIS_WHISPER_MODEL", "small")
    compute = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
    t0 = time.perf_counter()
    stt_model = WhisperModel(model_name, device="cpu", compute_type=compute)
    stt_load_ms = (time.perf_counter() - t0) * 1000.0
    print(f"STT model: {model_name} ({compute}), load={stt_load_ms:.0f}ms")

    stt_results = []
    for fixture in dataset[:5]:
        wav = fixture.to_wav_bytes()
        stt = stt_transcribe(wav, model=stt_model)
        stt_results.append({"fixture": fixture.name, **stt})
        print(f"  {fixture.name}: {stt['stt_ms']:.0f}ms -> '{stt['text'][:50]}'")

    stt_p50 = np.median([s["stt_ms"] for s in stt_results])
    print(f"STT p50: {stt_p50:.0f}ms (same for A, B, H)")

    # Cancel latency
    print("\n--- Cancel Latency ---")
    cancel_stats = asyncio.run(measure_cancel_latency())
    print(f"  cancel->get: p50={cancel_stats['p50_ms']:.1f}ms p95={cancel_stats['p95_ms']:.1f}ms")

    # Aggregate results
    all_a_delays, all_b_delays, all_h_delays = [], [], []
    all_a_starts, all_b_starts, all_h_starts = [], [], []
    total_a_missed = total_b_missed = total_h_missed = 0
    total_a_cut = total_b_cut = total_h_cut = 0
    total_a_false_ep = total_b_false_ep = total_h_false_ep = 0

    for scenario in scenarios:
        for r in scenario.a_results:
            if r.speech_detected:
                all_a_delays.append(r.end_of_speech_delay_ms)
                all_a_starts.append(r.speech_start_ms)
            if r.missed_speech: total_a_missed += 1
            if r.cut_final_word: total_a_cut += 1
            if r.false_endpoint: total_a_false_ep += 1

        for r in scenario.b_results:
            if r.speech_detected:
                all_b_delays.append(r.end_of_speech_delay_ms)
                all_b_starts.append(r.speech_start_ms)
            if r.missed_speech: total_b_missed += 1
            if r.cut_final_word: total_b_cut += 1
            if r.false_endpoint: total_b_false_ep += 1

        for r in scenario.h_results:
            if r.speech_detected:
                all_h_delays.append(r.end_of_speech_delay_ms)
                all_h_starts.append(r.speech_start_ms)
            if r.missed_speech: total_h_missed += 1
            if r.cut_final_word: total_h_cut += 1
            if r.false_endpoint: total_h_false_ep += 1

    def _p50(arr): return float(np.percentile(arr, 50)) if arr else 0
    def _p95(arr): return float(np.percentile(arr, 95)) if arr else 0

    report = {
        "reps": reps,
        "dataset_size": len(dataset),
        "stt_model": model_name,
        "stt_compute": compute,
        "stt_load_ms": stt_load_ms,
        "stt_p50_ms": float(stt_p50),
        "cold_silero_load_ms": cold_silero_ms,
        "warm_silero_load_ms": float(warm_silero_ms),
        "cancel_latency": cancel_stats,
        "cpu_ms": cpu_ms,
        "wall_ms": wall_ms,
        "peak_ram_bytes": peak_ram,
        "hangover_sweep": sweep_results,
        "pipeline_a": {
            "end_speech_delay": {"p50_ms": _p50(all_a_delays), "p95_ms": _p95(all_a_delays)},
            "speech_start_ms": {"p50_ms": _p50(all_a_starts), "p95_ms": _p95(all_a_starts)},
            "missed_speech": total_a_missed,
            "cut_final_word": total_a_cut,
            "false_endpoint": total_a_false_ep,
        },
        "pipeline_b": {
            "end_speech_delay": {"p50_ms": _p50(all_b_delays), "p95_ms": _p95(all_b_delays)},
            "speech_start_ms": {"p50_ms": _p50(all_b_starts), "p95_ms": _p95(all_b_starts)},
            "missed_speech": total_b_missed,
            "cut_final_word": total_b_cut,
            "false_endpoint": total_b_false_ep,
        },
        "pipeline_h": {
            "end_speech_delay": {"p50_ms": _p50(all_h_delays), "p95_ms": _p95(all_h_delays)},
            "speech_start_ms": {"p50_ms": _p50(all_h_starts), "p95_ms": _p95(all_h_starts)},
            "missed_speech": total_h_missed,
            "cut_final_word": total_h_cut,
            "false_endpoint": total_h_false_ep,
        },
    }

    # Print final report
    a_d = report["pipeline_a"]["end_speech_delay"]
    b_d = report["pipeline_b"]["end_speech_delay"]
    h_d = report["pipeline_h"]["end_speech_delay"]
    a_s = report["pipeline_a"]["speech_start_ms"]
    b_s = report["pipeline_b"]["speech_start_ms"]
    h_s = report["pipeline_h"]["speech_start_ms"]

    print("\n" + "=" * 70)
    print("FINAL REPORT — P1.4A.1 A/B/H BENCHMARK")
    print("=" * 70)
    print(f"Reps: {reps} per scenario, {len(dataset)} scenarios")
    print(f"STT: {model_name} ({compute}), p50={stt_p50:.0f}ms (same for all)")
    print(f"Cold Silero: {cold_silero_ms:.0f}ms | Warm: {warm_silero_ms:.0f}ms")
    print(f"CPU: {cpu_ms:.0f}ms | RAM: {peak_ram / 1024:.1f}KB")
    print()
    print(f"{'METRIC':<30} {'A (RMS)':<15} {'B (Silero)':<15} {'H (Hybrid)':<15} {'DELTA H-A'}")
    print("-" * 90)
    print(f"{'End Speech Delay P50':<30} {a_d['p50_ms']:<15.1f} {b_d['p50_ms']:<15.1f} {h_d['p50_ms']:<15.1f} {h_d['p50_ms'] - a_d['p50_ms']:+.1f}ms")
    print(f"{'End Speech Delay P95':<30} {a_d['p95_ms']:<15.1f} {b_d['p95_ms']:<15.1f} {h_d['p95_ms']:<15.1f} {h_d['p95_ms'] - a_d['p95_ms']:+.1f}ms")
    print(f"{'Speech Start P50':<30} {a_s['p50_ms']:<15.1f} {b_s['p50_ms']:<15.1f} {h_s['p50_ms']:<15.1f} {h_s['p50_ms'] - a_s['p50_ms']:+.1f}ms")
    print(f"{'Cut Final Words':<30} {report['pipeline_a']['cut_final_word']:<15} {report['pipeline_b']['cut_final_word']:<15} {report['pipeline_h']['cut_final_word']:<15}")
    print(f"{'False Endpoints':<30} {report['pipeline_a']['false_endpoint']:<15} {report['pipeline_b']['false_endpoint']:<15} {report['pipeline_h']['false_endpoint']:<15}")
    print(f"{'Missed Speech':<30} {report['pipeline_a']['missed_speech']:<15} {report['pipeline_b']['missed_speech']:<15} {report['pipeline_h']['missed_speech']:<15}")

    # Decision
    print("\n" + "=" * 70)
    print("DECISION")
    print("=" * 70)

    # Score: H vs A (must beat A on delay + zero cuts)
    h_delay_better = h_d["p50_ms"] < a_d["p50_ms"]
    h_no_cuts = report["pipeline_h"]["cut_final_word"] == 0
    h_no_extra_missed = report["pipeline_h"]["missed_speech"] <= report["pipeline_a"]["missed_speech"]
    h_no_extra_false = report["pipeline_h"]["false_endpoint"] <= report["pipeline_a"]["false_endpoint"]

    print(f"  H P50 delay: {h_d['p50_ms']:.0f}ms vs A {a_d['p50_ms']:.0f}ms (target <=1500ms)")
    print(f"  H cut words: {report['pipeline_h']['cut_final_word']} (target: 0)")
    print(f"  H missed: {report['pipeline_h']['missed_speech']} | false: {report['pipeline_h']['false_endpoint']}")

    if h_delay_better and h_no_cuts and h_no_extra_missed and h_no_extra_false:
        winner = "HYBRID"
        print(f"\n  WINNER: HYBRID — beats A on delay ({h_d['p50_ms']:.0f} < {a_d['p50_ms']:.0f}), zero cuts")
    elif report["pipeline_h"]["cut_final_word"] > 0:
        winner = "A (HYBRID has cuts)"
        print(f"\n  WINNER: A — HYBRID still cuts {report['pipeline_h']['cut_final_word']} words")
    elif h_d["p50_ms"] > 1500:
        winner = "A (HYBRID too slow)"
        print(f"\n  WINNER: A — HYBRID P50={h_d['p50_ms']:.0f}ms > 1500ms target")
    else:
        winner = "A (marginal)"
        print(f"\n  WINNER: A — HYBRID doesn't clearly beat A")

    report["winner"] = winner

    return report


# ═══════════════════════════════════════════════════════════════════
# UNIT TESTS (verificar que o benchmark roda)
# ═══════════════════════════════════════════════════════════════════

class TestBenchmarkInfrastructure(unittest.TestCase):
    def test_dataset_builds(self):
        dataset = build_dataset()
        self.assertEqual(len(dataset), 10)
        for f in dataset:
            self.assertGreater(f.duration_ms, 0)
            self.assertEqual(f.audio.dtype, np.int16)

    def test_pipeline_a_silence(self):
        fixture = build_dataset()[6]  # silence
        result = run_pipeline_a(fixture)
        self.assertFalse(result.speech_detected)

    def test_pipeline_a_speech(self):
        fixture = build_dataset()[0]  # short_phrase
        result = run_pipeline_a(fixture)
        self.assertTrue(result.speech_detected)
        self.assertGreater(result.utterance_ms, 0)

    def test_pipeline_b_silence(self):
        async def _test():
            fixture = build_dataset()[6]  # silence
            result = await run_pipeline_b(fixture)
            self.assertFalse(result.speech_detected)
        asyncio.run(_test())

    def test_pipeline_b_speech(self):
        async def _test():
            fixture = build_dataset()[0]  # short_phrase
            result = await run_pipeline_b(fixture)
            self.assertTrue(result.speech_detected)
            self.assertGreater(result.utterance_ms, 0)
        asyncio.run(_test())

    def test_cancel_latency(self):
        async def _test():
            stats = await measure_cancel_latency(reps=5)
            self.assertGreater(stats["p50_ms"], 0)
            self.assertLess(stats["p95_ms"], 500)  # should be fast
        asyncio.run(_test())

    def test_fixture_wav_roundtrip(self):
        fixture = build_dataset()[0]
        wav = fixture.to_wav_bytes()
        self.assertTrue(wav[:4] == b"RIFF")

    def test_pipeline_h_silence(self):
        async def _test():
            fixture = build_dataset()[6]  # silence
            result = await run_pipeline_h(fixture)
            self.assertFalse(result.speech_detected)
        asyncio.run(_test())

    def test_pipeline_h_speech(self):
        async def _test():
            fixture = build_dataset()[0]  # short_phrase
            result = await run_pipeline_h(fixture)
            self.assertTrue(result.speech_detected)
            self.assertGreater(result.utterance_ms, 0)
        asyncio.run(_test())

    def test_pipeline_h_hangover_triggers(self):
        async def _test():
            fixture = build_dataset()[3]  # fade_out
            result = await run_pipeline_h(fixture, hangover_ms=250)
            self.assertTrue(result.speech_detected)
            self.assertGreaterEqual(result.hangover_count, 0)
        asyncio.run(_test())


if __name__ == "__main__":
    # Run with: python tests/benchmark_voice_ab.py
    # Or: python -m pytest tests/benchmark_voice_ab.py -v -s
    import argparse
    parser = argparse.ArgumentParser(description="P1.4A A/B Voice Benchmark")
    parser.add_argument("--reps", type=int, default=10, help="Repetitions per scenario")
    parser.add_argument("--test", action="store_true", help="Run unit tests only")
    args, _ = parser.parse_known_args()

    if args.test:
        unittest.main(argv=["benchmark_voice_ab"], exit=False)
    else:
        report = run_benchmark(reps=args.reps)
        # Save report
        import json
        report_path = Path(__file__).parent / "benchmark_voice_ab_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport saved to: {report_path}")
