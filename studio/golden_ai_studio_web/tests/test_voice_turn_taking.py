"""Deterministic turn-taking and logical barge-in tests.

No microphone, speaker, model download, network, or real TTS is used here.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from jarvis_core.realtime_voice.barge_in import (
    BargeInController,
    EchoDecision,
    SelfTriggerPolicy,
)
from jarvis_core.realtime_voice.integration import RealtimeVoicePipeline
from jarvis_core.realtime_voice.state_machine import (
    ConversationalState,
    VoiceStateMachine,
)
from jarvis_core.voice_service import VoiceService
from jarvis_core.voice_tts import (
    FakeAudioOutputProvider,
    FakeTextToSpeechProvider,
    PcmAudioChunk,
    VoiceAudioPipeline,
)


def _speaking_service() -> VoiceService:
    service = VoiceService()
    service.state = "OUVINDO"
    service.state = "LISTENING"
    service.state = "PROCESSING"
    service.state = "SPEAKING"
    service._voice = MagicMock()
    return service


def _chunk(identity: tuple[str, int, int], sequence: int = 0) -> PcmAudioChunk:
    return PcmAudioChunk(
        pcm=b"\x00\x00" * 8,
        sample_rate=22050,
        sequence=sequence,
        session_id=identity[0],
        turn_id=identity[1],
        generation=identity[2],
        is_final=True,
    )


def test_self_trigger_policy_is_explicit_without_claiming_aec():
    policy = SelfTriggerPolicy(self_output_threshold=500)

    assert policy.classify("user_speech", tts_active=True, audio_level=900) is EchoDecision.ALLOW_BARGE_IN
    assert policy.classify("self_output", tts_active=True, audio_level=900) is EchoDecision.IGNORE_AS_SELF_TRIGGER
    assert policy.classify("unknown", tts_active=False, audio_level=10) is EchoDecision.UNCERTAIN
    assert policy.classify("unknown", tts_active=True, audio_level=900) is EchoDecision.IGNORE_AS_SELF_TRIGGER


def test_barge_in_invalidates_before_cancel_and_flushes_old_tts_output():
    service = _speaking_service()
    provider = FakeTextToSpeechProvider()
    output = FakeAudioOutputProvider()
    service.configure_tts_pipeline(provider, output)
    old_turn = service._turn_manager.new_turn()

    assert service._speak("resposta antiga") is True
    old_identity = service.get_tts_pipeline().identity
    old_epoch = service._tts_epoch
    assert output.qsize == 1

    result = service.accept_barge_in(source="user_speech", prepare_followup=False)

    assert result["accepted"] is True
    assert result["invalidated_generation"] == old_epoch + 1
    assert service._tts_epoch == old_epoch + 1
    assert service._turn_manager.is_cancelled(old_turn) is True
    assert output.qsize == 0
    assert service.accept_tts_chunk(_chunk(old_identity)) is False
    assert service.state == "LISTENING"


def test_hardware_free_e2e_only_second_response_survives():
    service = VoiceService()
    service.state = "OUVINDO"
    service.state = "LISTENING"
    service._voice = MagicMock()
    service.service = MagicMock()
    service.service.orchestrator.decide.return_value = MagicMock()
    service.service.registry = MagicMock()
    provider = FakeTextToSpeechProvider()
    output = FakeAudioOutputProvider()
    service.configure_tts_pipeline(provider, output)

    brain = MagicMock()
    brain.interpret.side_effect = [
        {"ok": True, "plan": {"response": "primeira resposta"}},
        {"ok": True, "plan": {"response": "segunda resposta"}},
    ]
    brain.orchestrator.last_decision = None
    brain.last_llm = {}

    with patch("jarvis_core.response_policy.ack_for_decision", return_value={
        "emitted": False, "message": "", "reason": "test"
    }):
        with patch.object(service, "_should_use_streaming", return_value=False):
            with patch.object(service, "_get_brain", return_value=brain):
                service._handle("primeiro pedido", output={"speak": True, "mode": "VOICE"})
                first_identity = service.get_tts_pipeline().identity
                assert output.qsize == 1

                accepted = service.accept_barge_in(source="user_speech", prepare_followup=False)
                assert accepted["accepted"] is True
                assert output.qsize == 0

                service._handle("segundo pedido", output={"speak": True, "mode": "VOICE"})

    assert brain.interpret.call_count == 2
    assert len(provider.calls) == 2
    assert output.qsize == 1
    assert output.queued[0].metadata["text"] == "segunda resposta"
    assert service.accept_tts_chunk(_chunk(first_identity)) is False


def test_double_barge_in_and_rapid_new_turns_do_not_poison_future_output():
    service = _speaking_service()
    provider = FakeTextToSpeechProvider()
    output = FakeAudioOutputProvider()
    service.configure_tts_pipeline(provider, output)

    assert service._speak("resposta um") is True
    first = service.accept_barge_in(source="user_speech", prepare_followup=False)
    assert first["accepted"] is True

    service.state = "PROCESSING"
    service.state = "SPEAKING"
    assert service._speak("resposta dois") is True
    second = service.accept_barge_in(source="user_speech", prepare_followup=False)
    assert second["accepted"] is True

    service.state = "PROCESSING"
    service.state = "SPEAKING"
    assert service._speak("resposta tres") is True
    assert output.qsize == 1
    assert output.queued[0].metadata["text"] == "resposta tres"


def test_self_output_is_ignored_but_uncertain_input_is_documented():
    service = _speaking_service()
    assert service.classify_input_during_output(source="self_output", audio_level=800) == "ignore_as_self_trigger"
    assert service.accept_barge_in(source="self_output", audio_level=800)["accepted"] is False
    assert service.classify_input_during_output(source="unknown", audio_level=10) == "uncertain"
    assert service.accept_barge_in(source="unknown", audio_level=10)["accepted"] is True


def test_sessions_are_isolated():
    first = _speaking_service()
    second = _speaking_service()
    first_provider, first_output = FakeTextToSpeechProvider(), FakeAudioOutputProvider()
    second_provider, second_output = FakeTextToSpeechProvider(), FakeAudioOutputProvider()
    first.configure_tts_pipeline(first_provider, first_output)
    second.configure_tts_pipeline(second_provider, second_output)
    assert first._speak("sessao um") is True
    assert second._speak("sessao dois") is True

    first.accept_barge_in(source="user_speech", prepare_followup=False)

    assert first_output.qsize == 0
    assert second_output.qsize == 1
    assert first.status()["session_id"] != second.status()["session_id"]


def test_realtime_pipeline_routes_synthetic_barge_in_to_voice_service():
    service = _speaking_service()
    pipeline = service.get_realtime_voice_pipeline()
    pipeline.barge_in._grace_seconds = 0.0
    pipeline.barge_in.tts_started()

    assert pipeline.barge_in.trigger_barge_in() is True
    assert service.status()["barge_in"]["accepted"] is True
    assert service.state == "LISTENING"


def test_stale_core_completion_is_blocked_before_tts():
    service = _speaking_service()
    old_turn = service._turn_manager.new_turn()
    service._current_turn_id = old_turn
    service._tts_epoch = 4
    service.accept_barge_in(source="user_speech", prepare_followup=False)

    assert service.accepts_core_output(turn_id=old_turn, generation=4) is False
    brain = MagicMock()
    with patch.object(service, "_get_brain", return_value=brain):
        service._handle(
            "late core text",
            timings={"turn_id": old_turn, "generation": 4},
            output={"speak": True, "mode": "VOICE"},
        )
    brain.interpret.assert_not_called()
    assert service.last_rejection["classification"] == "STALE_OUTPUT"


def test_failure_boundaries_do_not_corrupt_voice_state():
    class FailingOutput(FakeAudioOutputProvider):
        def enqueue(self, chunk):
            raise RuntimeError("output failed")

    pipeline = VoiceAudioPipeline(FakeTextToSpeechProvider(), FailingOutput())
    result = pipeline.speak("falha de output", session_id="s", turn_id=1, generation=1)
    assert result.ok is False
    assert "output failed" in result.error

    service = _speaking_service()
    service._self_trigger_policy = MagicMock()
    service._self_trigger_policy.classify.side_effect = RuntimeError("policy failed")
    result = service.accept_barge_in(source="unknown")
    assert result["ok"] is False
    assert result["reason"] == "self_trigger_policy_failed"
    assert service.state == "SPEAKING"


def test_vad_failure_is_counted_and_does_not_kill_the_pipeline_boundary():
    pipeline = RealtimeVoicePipeline()

    async def failing_feed(_frame):
        raise RuntimeError("vad failed")

    pipeline._vad.feed = failing_feed
    assert asyncio.run(pipeline._feed_vad_safely(b"frame")) is None
    assert pipeline.stats["vad_errors"] == 1
    assert pipeline.stats["last_vad_error"] == "vad failed"


def test_barge_in_controller_handler_is_single_owner_callback():
    machine = VoiceStateMachine(ConversationalState.IDLE)
    machine.transition(ConversationalState.LISTENING)
    machine.transition(ConversationalState.THINKING)
    machine.transition(ConversationalState.SPEAKING)
    called = []
    controller = BargeInController(machine, grace_seconds=0)
    controller.set_barge_in_handler(lambda: called.append("owner"))
    controller.tts_started()

    assert controller.trigger_barge_in() is True
    assert called == ["owner"]
    assert controller.handler_installed is True
