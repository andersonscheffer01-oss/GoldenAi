"""Offline regression tests for the identity-aware voice coordinator."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from jarvis_core.realtime_voice.conversation_coordinator import (
    ConversationResultStatus,
    ConversationStreamCoordinator,
)
from jarvis_core.realtime_voice.constants import FRAME_BYTES
from jarvis_core.realtime_voice.integration import RealtimeVoicePipeline
from jarvis_core.realtime_voice.state_machine import ConversationalState
from jarvis_core.realtime_voice.vad import VADEvent
from jarvis_core.voice_foundation import DeterministicFakeSTTProvider, TranscriptEvent


def _event(
    text: str,
    *,
    session_id: str = "session-a",
    utterance_id: str = "utterance-a",
    sequence: int = 1,
    epoch: int = 1,
    is_final: bool = True,
) -> TranscriptEvent:
    return TranscriptEvent(
        text=text,
        is_final=is_final,
        sequence=sequence,
        session_id=session_id,
        utterance_id=utterance_id,
        provider="test-stt",
        epoch=epoch,
    )


def _coordinator(**kwargs) -> ConversationStreamCoordinator:
    coordinator = ConversationStreamCoordinator(**kwargs)
    coordinator.begin_session(session_id="session-a", turn_id=7, epoch=1)
    return coordinator


def test_incomplete_final_waits_and_continuation_is_one_logical_utterance():
    coordinator = _coordinator()
    first = coordinator.observe_transcript(
        _event("preciso de", utterance_id="segment-a"),
        turn_id=7,
        acoustic_endpoint=True,
    )
    assert first.status is ConversationResultStatus.WAITING_CONTINUATION
    assert first.eligible_for_dispatch is False

    second = coordinator.observe_transcript(
        _event("ajuda com isso", utterance_id="segment-b", sequence=2),
        turn_id=7,
        acoustic_endpoint=True,
    )
    assert second.status is ConversationResultStatus.COMPLETED
    assert second.eligible_for_dispatch is True
    assert second.event is not None
    assert second.event.text == "preciso de ajuda com isso"
    assert second.event.utterance_id == "segment-a"
    assert second.event.metadata["coordinator_segment_count"] == 2


def test_duplicate_final_is_not_dispatchable_twice():
    coordinator = _coordinator()
    event = _event("abra o painel agora")
    first = coordinator.observe_transcript(
        event, turn_id=7, acoustic_endpoint=True
    )
    duplicate = coordinator.observe_transcript(
        replace(event, sequence=2), turn_id=7, acoustic_endpoint=True
    )
    assert first.status is ConversationResultStatus.COMPLETED
    assert first.eligible_for_dispatch is True
    assert duplicate.status is ConversationResultStatus.REJECTED_DUPLICATE
    assert duplicate.eligible_for_dispatch is False


def test_new_utterance_after_completion_remains_eligible():
    coordinator = _coordinator()
    first = coordinator.observe_transcript(
        _event("abra o painel agora", utterance_id="utterance-a"),
        turn_id=7,
        acoustic_endpoint=True,
    )
    second = coordinator.observe_transcript(
        _event("feche o painel agora", utterance_id="utterance-b", sequence=2),
        turn_id=7,
        acoustic_endpoint=True,
    )
    assert first.eligible_for_dispatch is True
    assert second.eligible_for_dispatch is True
    assert second.event is not None
    assert second.event.text == "feche o painel agora"


def test_partial_is_observable_but_never_eligible_for_dispatch():
    coordinator = _coordinator()
    result = coordinator.observe_transcript(
        _event("parcial", is_final=False),
        turn_id=7,
        acoustic_endpoint=False,
    )
    assert result.status is ConversationResultStatus.PARTIAL_OBSERVED
    assert result.eligible_for_dispatch is False


def test_stale_session_turn_epoch_and_cancelled_events_are_rejected():
    coordinator = _coordinator()
    assert coordinator.observe_transcript(
        _event("sessao antiga", session_id="session-old"),
        turn_id=7,
        acoustic_endpoint=True,
    ).reason_code == "STALE_SESSION"
    assert coordinator.observe_transcript(
        _event("turno antigo"), turn_id=6, acoustic_endpoint=True
    ).reason_code == "STALE_TURN"
    assert coordinator.observe_transcript(
        _event("epoch antigo", epoch=2), turn_id=7, acoustic_endpoint=True
    ).reason_code == "STALE_EPOCH"

    coordinator.cancel("test cancellation")
    cancelled = coordinator.observe_transcript(
        _event("depois do cancelamento"), turn_id=7, acoustic_endpoint=True
    )
    assert cancelled.status is ConversationResultStatus.REJECTED_STALE
    assert cancelled.reason_code == "CANCELLED_OR_INACTIVE"


def test_timeout_completes_bounded_continuation_once():
    coordinator = _coordinator()
    waiting = coordinator.observe_transcript(
        _event("preciso de"), turn_id=7, acoustic_endpoint=True
    )
    completed = coordinator.timeout()
    repeated = coordinator.timeout()
    assert waiting.status is ConversationResultStatus.WAITING_CONTINUATION
    assert completed.status is ConversationResultStatus.COMPLETED
    assert completed.reason_code == "CONTINUATION_TIMEOUT"
    assert repeated.status is ConversationResultStatus.NOOP


def test_uncertain_without_endpoint_does_not_finalize_but_endpoint_is_fallback():
    no_endpoint = _coordinator()
    uncertain = no_endpoint.observe_transcript(
        _event("sim"), turn_id=7, acoustic_endpoint=False
    )
    assert uncertain.status is ConversationResultStatus.WAITING_CONTINUATION
    assert uncertain.eligible_for_dispatch is False

    acoustic = _coordinator()
    fallback = acoustic.observe_transcript(
        _event("sim"), turn_id=7, acoustic_endpoint=True
    )
    assert fallback.status is ConversationResultStatus.COMPLETED
    assert fallback.reason_code == "ACOUSTIC_FALLBACK"


def test_semantic_detector_failure_uses_only_acoustic_fallback():
    class FailingDetector:
        def decide(self, _evidence):
            raise RuntimeError("detector unavailable")

    coordinator = _coordinator(semantic_detector=FailingDetector())
    fallback = coordinator.observe_transcript(
        _event("texto seguro"), turn_id=7, acoustic_endpoint=True
    )
    assert fallback.status is ConversationResultStatus.COMPLETED
    assert fallback.reason_code == "ACOUSTIC_FALLBACK"

    coordinator = _coordinator(semantic_detector=FailingDetector())
    rejected = coordinator.observe_transcript(
        _event("texto seguro"), turn_id=7, acoustic_endpoint=False
    )
    assert rejected.status is ConversationResultStatus.REJECTED_UNCERTAIN


def test_memory_limits_reject_oversized_logical_utterance():
    coordinator = _coordinator(max_segments=2, max_transcript_chars=20)
    first = coordinator.observe_transcript(
        _event("preciso de"), turn_id=7, acoustic_endpoint=True
    )
    oversized = coordinator.observe_transcript(
        _event("uma frase muito longa", utterance_id="segment-b", sequence=2),
        turn_id=7,
        acoustic_endpoint=True,
    )
    assert first.status is ConversationResultStatus.WAITING_CONTINUATION
    assert oversized.status is ConversationResultStatus.REJECTED_INVALID
    assert coordinator.diagnostics()["segment_count"] == 0


class _SyntheticVAD:
    def __init__(self, events):
        self._events = iter(events)

    def reset(self):
        return None

    async def unload(self):
        return None

    async def feed(self, frame):
        assert len(frame) == FRAME_BYTES
        return next(self._events, None)


def test_realtime_pipeline_dispatches_one_combined_final_after_continuation():
    async def exercise():
        callbacks = []
        provider = DeterministicFakeSTTProvider(["preciso de", "ajuda com isso"])
        events = (
            [VADEvent.SPEECH_STARTED]
            + [None] * 17
            + [VADEvent.ENDPOINT]
            + [VADEvent.SPEECH_STARTED]
            + [None] * 17
            + [VADEvent.ENDPOINT]
        )
        pipeline = RealtimeVoicePipeline()
        pipeline._vad = _SyntheticVAD(events)
        await pipeline.start(
            on_transcription=callbacks.append,
            stt_provider=provider,
            session_id="pipeline-session",
            turn_id=11,
        )
        pipeline.state_machine.transition(ConversationalState.LISTENING)
        try:
            for _ in range(38):
                pipeline.feed_frame(b"\x01" * FRAME_BYTES)
                await asyncio.sleep(0)
            await asyncio.sleep(0.12)
            assert len(provider.calls) == 2
            assert len(callbacks) == 1
            assert callbacks[0].text == "preciso de ajuda com isso"
            assert pipeline.stats["accepted_finals"] == 1
            assert pipeline.stats["coordinator_nonfinals"] == 1
        finally:
            await pipeline.stop()

    asyncio.run(exercise())


def test_pipeline_turn_replacement_reuses_owner_and_updates_identity():
    async def exercise():
        pipeline = RealtimeVoicePipeline()
        await pipeline.start(session_id="pipeline-session", turn_id=11)
        try:
            assert pipeline.turn_id == 11
            assert pipeline.conversation_coordinator.diagnostics()["turn_id"] == 11
            pipeline.replace_turn(12)
            diagnostics = pipeline.conversation_coordinator.diagnostics()
            assert pipeline.turn_id == 12
            assert diagnostics["turn_id"] == 12
            assert diagnostics["session_id"] == "pipeline-session"
        finally:
            await pipeline.stop()

    asyncio.run(exercise())
