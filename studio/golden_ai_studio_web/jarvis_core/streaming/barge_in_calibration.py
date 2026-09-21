"""Barge-in calibration and robust RMS statistics.

Computes median, P90, P95, P99, peak for:
- SILENCE (user quiet, no TTS)
- TTS_ONLY (Jarvis speaking, user quiet)
- USER_ONLY (user speaking, no TTS)
- USER_OVER_TTS (user speaking over TTS)

Also provides adaptive threshold calculation.

Usage:
    cal = BargeInCalibrator()
    stats = cal.measure_silence(5.0)
    threshold = cal.compute_threshold(silence_stats, tts_stats)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# Configurable via env
BARGE_IN_RMS_THRESHOLD = int(os.getenv("JARVIS_BARGE_IN_RMS_THRESHOLD", "300"))
BARGE_IN_MIN_SPEECH_MS = int(os.getenv("JARVIS_BARGE_IN_MIN_SPEECH_MS", "200"))
BARGE_IN_GRACE_SECONDS = float(os.getenv("JARVIS_BARGE_IN_GRACE_SECONDS", "0.2"))
BARGE_IN_PERSISTENCE_BLOCKS = int(os.getenv("JARVIS_BARGE_IN_PERSISTENCE_BLOCKS", "6"))

# Adaptive threshold margin (added above tts_floor)
BARGE_IN_ADAPTIVE_MARGIN = int(os.getenv("JARVIS_BARGE_IN_ADAPTIVE_MARGIN", "150"))

# Minimum absolute threshold (ignores adaptive if noise is very low)
BARGE_IN_MIN_ABSOLUTE = int(os.getenv("JARVIS_BARGE_IN_MIN_ABSOLUTE", "200"))


@dataclass
class RMSStats:
    """Robust statistics for a set of RMS measurements."""
    count: int = 0
    median: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    peak: float = 0.0
    mean: float = 0.0
    min_val: float = 0.0

    @classmethod
    def from_array(cls, arr: list[float]) -> "RMSStats":
        if not arr:
            return cls()
        a = np.array(arr, dtype=np.float64)
        return cls(
            count=len(a),
            median=float(np.median(a)),
            p90=float(np.percentile(a, 90)),
            p95=float(np.percentile(a, 95)),
            p99=float(np.percentile(a, 99)),
            peak=float(np.max(a)),
            mean=float(np.mean(a)),
            min_val=float(np.min(a)),
        )

    def __repr__(self):
        return (
            f"RMSStats(n={self.count}, median={self.median:.0f}, "
            f"P90={self.p90:.0f}, P95={self.p95:.0f}, P99={self.p99:.0f}, "
            f"peak={self.peak:.0f})"
        )


@dataclass
class CalibrationResult:
    """Complete calibration result."""
    silence: RMSStats = field(default_factory=RMSStats)
    tts_only_headset: RMSStats = field(default_factory=RMSStats)
    tts_only_speakers: RMSStats = field(default_factory=RMSStats)
    user_only: RMSStats = field(default_factory=RMSStats)
    user_over_tts_headset: RMSStats = field(default_factory=RMSStats)
    user_over_tts_speakers: RMSStats = field(default_factory=RMSStats)
    selected_threshold: float = 0.0
    noise_floor: float = 0.0
    tts_floor: float = 0.0


class BargeInCalibrator:
    """Measures RMS statistics for barge-in threshold calibration."""

    def __init__(self, samplerate: int = 16000, blocksize: int = 1024):
        self.samplerate = samplerate
        self.blocksize = blocksize

    def _measure_rms(
        self,
        duration_seconds: float,
        label: str = "",
        tts_text: Optional[str] = None,
    ) -> list[float]:
        """Open mic, measure RMS for duration. If tts_text provided, speak during measurement."""
        try:
            import sounddevice as sd
        except ImportError:
            log.warning("sounddevice not installed, skipping measurement")
            return []

        rms_values = []
        tts_thread = None
        tts_done = None

        # Start TTS in background if requested
        if tts_text:
            import threading
            tts_done = threading.Event()
            def _speak():
                try:
                    from jarvis_core.voice_service import VoiceService
                    vs = VoiceService()
                    vs._speak_edge(tts_text)
                except Exception:
                    pass
                tts_done.set()
            tts_thread = threading.Thread(target=_speak, daemon=True)
            tts_thread.start()
            time.sleep(0.3)  # Wait for TTS to start

        try:
            with sd.InputStream(
                samplerate=self.samplerate,
                channels=1,
                dtype="int16",
                blocksize=self.blocksize,
            ) as stream:
                start = time.time()
                while time.time() - start < duration_seconds:
                    data, _ = stream.read(self.blocksize)
                    rms = float(np.abs(data).mean())
                    rms_values.append(rms)
        except Exception as e:
            log.warning("Measurement failed: %s", e)

        if tts_done:
            tts_done.wait(timeout=15)

        return rms_values

    def measure_silence(self, duration: float = 5.0) -> RMSStats:
        """Measure RMS in silence (user quiet, no TTS)."""
        print(f"  [CAL] Measuring SILENCE for {duration}s... ", end="", flush=True)
        values = self._measure_rms(duration, "silence")
        stats = RMSStats.from_array(values)
        print(stats)
        return stats

    def measure_user_only(self, duration: float = 5.0) -> RMSStats:
        """Measure RMS with user speaking (no TTS)."""
        print(f"  [CAL] Measuring USER_ONLY for {duration}s (speak normally)... ", end="", flush=True)
        values = self._measure_rms(duration, "user_only")
        stats = RMSStats.from_array(values)
        print(stats)
        return stats

    def measure_tts_only(self, duration: float = 10.0, device: str = "headset") -> RMSStats:
        """Measure RMS with TTS playing (user quiet)."""
        text = "Esta é uma frase de teste longa para medir o vazamento do TTS. O Jarvis está falando agora e o usuário está em silêncio completo. Esta frase deve durar pelo menos dez segundos para uma medição adequada."
        print(f"  [CAL] Measuring TTS_ONLY ({device}) for {duration}s... ", end="", flush=True)
        values = self._measure_rms(duration, f"tts_only_{device}", tts_text=text)
        stats = RMSStats.from_array(values)
        print(stats)
        return stats

    def measure_user_over_tts(self, duration: float = 5.0, device: str = "headset") -> RMSStats:
        """Measure RMS with user speaking over TTS."""
        text = "Esta é uma frase de teste longa para medir o vazamento do TTS enquanto o usuário fala por cima. O Jarvis está falando e o usuário também está falando ao mesmo tempo."
        print(f"  [CAL] Measuring USER_OVER_TTS ({device}) for {duration}s (speak now)... ", end="", flush=True)
        values = self._measure_rms(duration, f"user_over_tts_{device}", tts_text=text)
        stats = RMSStats.from_array(values)
        print(stats)
        return stats

    def compute_threshold(
        self,
        silence_stats: RMSStats,
        tts_stats: RMSStats,
    ) -> float:
        """Compute adaptive threshold from calibration data.

        threshold = max(
            BARGE_IN_MIN_ABSOLUTE,
            silence_stats.p99 + margin,
            tts_stats.p99 + margin,
        )
        """
        margin = BARGE_IN_ADAPTIVE_MARGIN
        noise_p99 = silence_stats.p99 if silence_stats.count > 0 else 0
        tts_p99 = tts_stats.p99 if tts_stats.count > 0 else 0

        threshold = max(
            BARGE_IN_MIN_ABSOLUTE,
            noise_p99 + margin,
            tts_p99 + margin,
        )

        log.info(
            "[CAL] Threshold: min_abs=%d, noise_p99+margin=%.0f, tts_p99+margin=%.0f → selected=%.0f",
            BARGE_IN_MIN_ABSOLUTE, noise_p99 + margin, tts_p99 + margin, threshold,
        )
        return threshold


def measure_rms_standalone(duration: float = 5.0, tts_text: Optional[str] = None) -> RMSStats:
    """Standalone RMS measurement (for quick tests)."""
    cal = BargeInCalibrator()
    values = cal._measure_rms(duration, tts_text=tts_text)
    return RMSStats.from_array(values)
