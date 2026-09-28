"""Offline tests for the deterministic semantic turn adapter."""

from jarvis_core.realtime_voice.semantic_turn import (
    DeterministicSemanticTurnDetector,
    SemanticTurnConfig,
    SemanticTurnInput,
    SemanticTurnReason,
    SemanticTurnState,
)


def _evidence(**overrides):
    values = {
        "session_id": "session-1",
        "turn_id": 7,
        "utterance_id": "utterance-1",
        "epoch": 3,
        "transcript": "Jarvis, abra o navegador.",
        "is_final": True,
        "acoustic_endpoint": True,
        "speech_active": False,
    }
    values.update(overrides)
    return SemanticTurnInput(**values)


def test_incomplete_portuguese_thought_does_not_complete():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(
        _evidence(
            transcript="Jarvis, procure os arquivos que eu...",
            acoustic_endpoint=True,
        )
    )

    assert decision.state is SemanticTurnState.CONTINUE_LISTENING
    assert decision.reason_code is SemanticTurnReason.ELLIPSIS
    assert decision.should_finalize is False


def test_continuation_can_complete_as_one_final_phrase():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(
        _evidence(
            transcript="Jarvis, procure os arquivos que eu salvei ontem.",
            acoustic_endpoint=True,
        )
    )

    assert decision.state is SemanticTurnState.COMPLETE
    assert decision.reason_code is SemanticTurnReason.TERMINAL_PUNCTUATION


def test_clear_complete_portuguese_phrase_is_completion_compatible():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(_evidence(transcript="Jarvis, abra o navegador."))

    assert decision.state is SemanticTurnState.COMPLETE
    assert decision.should_finalize is True


def test_natural_pause_keeps_acoustic_endpoint_from_forcing_completion():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(
        _evidence(
            transcript="Jarvis, procure os arquivos que eu",
            acoustic_endpoint=True,
        )
    )

    assert decision.state is SemanticTurnState.CONTINUE_LISTENING
    assert decision.reason_code is SemanticTurnReason.INCOMPLETE_TRAILING_CONNECTIVE


def test_ambiguous_short_phrase_is_uncertain():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(_evidence(transcript="sim"))

    assert decision.state is SemanticTurnState.UNCERTAIN
    assert decision.reason_code is SemanticTurnReason.INSUFFICIENT_EVIDENCE


def test_timeout_uses_bounded_acoustic_fallback():
    detector = DeterministicSemanticTurnDetector(
        SemanticTurnConfig(max_continuation_window_ms=100.0)
    )

    decision = detector.decide(
        _evidence(
            transcript="Jarvis, procure os arquivos que eu",
            continuation_elapsed_ms=100.0,
            acoustic_endpoint=True,
        )
    )

    assert decision.state is SemanticTurnState.COMPLETE
    assert decision.reason_code is SemanticTurnReason.CONTINUATION_TIMEOUT


def test_timeout_without_acoustic_endpoint_does_not_invent_completion():
    detector = DeterministicSemanticTurnDetector(
        SemanticTurnConfig(max_continuation_window_ms=10.0)
    )

    decision = detector.decide(
        _evidence(
            continuation_elapsed_ms=20.0,
            acoustic_endpoint=False,
        )
    )

    assert decision.state is SemanticTurnState.UNCERTAIN
    assert decision.reason_code is SemanticTurnReason.CONTINUATION_TIMEOUT


def test_malformed_timing_fails_closed_without_crashing():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(_evidence(decision_elapsed_ms=-1.0))

    assert decision.state is SemanticTurnState.UNCERTAIN
    assert decision.reason_code is SemanticTurnReason.INVALID_INPUT


def test_empty_and_missing_optional_timing_are_deterministic():
    detector = DeterministicSemanticTurnDetector()

    first = detector.decide(
        _evidence(transcript=None, decision_elapsed_ms=None, continuation_elapsed_ms=None)
    )
    second = detector.decide(
        _evidence(transcript="   ", decision_elapsed_ms=None, continuation_elapsed_ms=None)
    )

    assert first == second
    assert first.state is SemanticTurnState.CONTINUE_LISTENING
    assert first.reason_code is SemanticTurnReason.EMPTY_TRANSCRIPT


def test_unicode_portuguese_text_is_preserved_for_reasoning():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(
        _evidence(transcript="Verifique as informações de amanhã, por favor."),
    )

    assert decision.state is SemanticTurnState.COMPLETE
    assert decision.reason_code is SemanticTurnReason.TERMINAL_PUNCTUATION


def test_identity_is_preserved_without_new_identity_semantics():
    detector = DeterministicSemanticTurnDetector()
    evidence = _evidence(
        session_id="s-9",
        turn_id=42,
        utterance_id="u-8",
        epoch=11,
    )

    decision = detector.decide(evidence)

    assert (decision.session_id, decision.turn_id, decision.utterance_id, decision.epoch) == (
        "s-9",
        42,
        "u-8",
        11,
    )


def test_partial_transcript_never_returns_complete():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(
        _evidence(
            transcript="Jarvis, abra o navegador.",
            is_final=False,
            acoustic_endpoint=True,
        )
    )

    assert decision.state is not SemanticTurnState.COMPLETE
    assert decision.reason_code is SemanticTurnReason.PARTIAL_TRANSCRIPT


def test_speech_active_always_continues_listening():
    detector = DeterministicSemanticTurnDetector()

    decision = detector.decide(
        _evidence(
            transcript="Jarvis, abra o navegador.",
            speech_active=True,
            acoustic_endpoint=True,
        )
    )

    assert decision.state is SemanticTurnState.CONTINUE_LISTENING
    assert decision.reason_code is SemanticTurnReason.SPEECH_ACTIVE


def test_decision_is_repeatable_and_has_no_runtime_side_effects():
    detector = DeterministicSemanticTurnDetector()
    evidence = _evidence(transcript="Não altere o arquivo de amanhã.")

    first = detector.decide(evidence)
    second = detector.decide(evidence)

    assert first == second
    assert first.session_id == evidence.session_id
