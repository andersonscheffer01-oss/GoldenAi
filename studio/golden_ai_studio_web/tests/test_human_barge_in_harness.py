from jarvis_core.realtime_voice.human_barge_in_harness import (
    HarnessObservation,
    VADDiagnosticObservation,
    report_dict,
)


def test_harness_does_not_call_an_attempt_valid_without_real_barge_in_evidence():
    observation = HarnessObservation(
        playback_started_at=1.0,
        human_window_opened_at=1.1,
        human_window_closed_at=2.0,
        barge_in_callback_at=1.5,
        mic_frames_during_window=4,
        vad_triggered=True,
        barge_in_result={"accepted": True, "invalidated_generation": 1},
        playback_abort_cause="TIMEOUT",
    )
    assert observation.valid_acoustic_attempt is False


def test_harness_report_requires_canonical_barge_in_abort():
    observation = HarnessObservation(
        playback_started_at=1.0,
        human_window_opened_at=1.1,
        human_window_closed_at=2.0,
        barge_in_callback_at=1.5,
        mic_frames_during_window=4,
        vad_triggered=True,
        barge_in_result={"accepted": True, "invalidated_generation": 2},
        playback_abort_cause="BARGE_IN",
    )
    report = report_dict(observation)
    assert report["VALID_ACOUSTIC_ATTEMPT"] is True
    assert report["PLAYBACK_ABORT_CAUSE"] == "BARGE_IN"


def test_harness_report_keeps_endpoint_separate_from_speech_start():
    observation = HarnessObservation(
        vad_triggered=True,
        endpoint_triggered=False,
        human_window_opened_at=1.0,
        human_window_closed_at=2.0,
        barge_in_callback_at=1.5,
        mic_frames_during_window=1,
        playback_abort_cause="BARGE_IN",
        barge_in_result={"accepted": True, "invalidated_generation": 3},
    )
    report = report_dict(observation)
    assert report["VAD_TRIGGERED"] is True
    assert report["ENDPOINT_TRIGGERED"] is False


def test_interactive_report_waits_for_human_confirmation():
    observation = HarnessObservation(
        playback_started_at=1.0,
        human_window_opened_at=1.1,
        human_window_closed_at=2.0,
        mic_frames_during_window=10,
        playback_abort_cause="TIMEOUT",
    )
    report = report_dict(observation, human_confirmation=None)
    assert report["REAL_HUMAN_SPEECH_USED"] == "PENDING_HUMAN_CONFIRMATION"
    assert report["VALID_ACOUSTIC_ATTEMPT"] == "PENDING_HUMAN_CONFIRMATION"


def test_vad_diagnostic_reports_pcm_contract_without_retaining_pcm():
    observation = VADDiagnosticObservation(mode="silence", duration_seconds=0.03)
    observation.record_frame((1000).to_bytes(2, "little", signed=True) * 480, 1.0, "silence")
    observation.record_probability(0.2, 1.0, "silence")
    report = observation.report()
    assert report["FRAME_BYTES"] == 960
    assert report["FRAME_SAMPLES"] == 480
    assert report["NORMALIZATION_FUNCTION"] == "int16.astype(float32) / 32768.0"
    assert report["RAW_PCM16_PEAK_MAX"] == 1000
    assert report["RAW_PCM16_MIN"] == 1000
    assert report["RAW_PCM16_MAX"] == 1000
    assert report["RAW_PCM16_NONZERO_PERCENT"] == 100.0
    assert report["RAW_PCM16_UNIQUE_VALUES_PER_FRAME_MAX"] == 1
    assert report["RAW_PCM16_CLIPPED_PERCENT"] == 0.0
    assert report["FRAME_HASH_UNIQUE_COUNT"] == 1
    assert report["FRAME_BYTE_CHANGE_DETECTED"] is False
    assert report["FRAME_HASH_CHAIN_SHA256"]
    assert not hasattr(observation, "raw_pcm")


def test_vad_diagnostic_detects_transient_pcm_changes_without_retaining_audio():
    observation = VADDiagnosticObservation(mode="silence", duration_seconds=0.06)
    observation.record_frame((0).to_bytes(2, "little", signed=True) * 480, 1.0, "silence")
    observation.record_frame((1).to_bytes(2, "little", signed=True) * 480, 1.1, "silence")
    report = observation.report()
    assert report["RAW_PCM16_NONZERO_PERCENT"] == 50.0
    assert report["RAW_PCM16_UNIQUE_VALUES_PER_FRAME_MEAN"] == 1.0
    assert report["FRAME_HASH_UNIQUE_COUNT"] == 2
    assert report["FRAME_BYTE_CHANGE_DETECTED"] is True
    assert not hasattr(observation, "raw_pcm")


def test_vad_diagnostic_probability_aggregates_are_numeric():
    observation = VADDiagnosticObservation(mode="speech-only", duration_seconds=0.1)
    observation.record_probability(0.05, 1.0, "silence")
    observation.record_probability(0.55, 1.1, "silence")
    observation.record_probability(0.80, 1.2, "speech")
    report = observation.report()
    assert report["VAD_PROB_MIN"] == 0.05
    assert report["VAD_PROB_MAX"] == 0.8
    assert report["FRAMES_ABOVE_CURRENT_THRESHOLD"] == 2
