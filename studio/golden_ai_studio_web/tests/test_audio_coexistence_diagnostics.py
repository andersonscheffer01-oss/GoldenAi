"""Hardware-free tests for coexistence level measurements and classification."""

from __future__ import annotations

import math
import struct

from jarvis_core.realtime_voice.coexistence_diagnostics import (
    classify_echo,
    measure_pcm16,
    relative_db,
)


def _pcm(value: int, count: int = 8) -> bytes:
    return b"".join(struct.pack("<h", value) for _ in range(count))


def test_pcm_measurement_is_in_memory_and_uses_true_rms():
    level = measure_pcm16([_pcm(3, 4), _pcm(-4, 4)])

    assert level.frame_count == 2
    assert level.sample_count == 8
    assert round(level.rms, 5) == round(math.sqrt(12.5), 5)
    assert level.peak == 4
    assert measure_pcm16([]).rms == 0.0


def test_relative_db_handles_silent_baseline_and_level_change():
    assert relative_db(0.0, 10.0) is None
    assert round(relative_db(10.0, 20.0), 5) == round(20.0 * math.log10(2), 5)


def test_echo_classification_does_not_promote_unmeasured_audio():
    assert classify_echo(
        playback_to_mic_db=-10.7,
        vad_activations=0,
        stt_observed=None,
        false_barge_in=None,
    ) == "CLASS_0"
    assert classify_echo(
        playback_to_mic_db=8.0,
        vad_activations=0,
        stt_observed=None,
        false_barge_in=None,
    ) == "CLASS_1"
    assert classify_echo(
        playback_to_mic_db=8.0,
        vad_activations=1,
        stt_observed=None,
        false_barge_in=None,
    ) == "CLASS_2"
    assert classify_echo(
        playback_to_mic_db=None,
        vad_activations=0,
        stt_observed=None,
        false_barge_in=None,
    ) == "INCONCLUSIVE"
