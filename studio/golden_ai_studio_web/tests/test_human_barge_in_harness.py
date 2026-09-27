from jarvis_core.realtime_voice.human_barge_in_harness import (
    HarnessObservation,
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
