"""Hardware/model/network-free STT contract tests."""

from __future__ import annotations

import threading

import pytest

from jarvis_core.voice_foundation import (
    DeterministicFakeSTTProvider,
    SpeechToTextProvider,
    TranscriptAcceptanceGate,
    TranscriptEvent,
    VoiceCancellation,
    VoiceCancelledError,
)


def _event(*, text="ola", session="s1", utterance="u1", epoch=0, final=True):
    return TranscriptEvent(
        text=text,
        is_final=final,
        sequence=1,
        session_id=session,
        utterance_id=utterance,
        provider="test",
        epoch=epoch,
    )


def test_transcript_event_is_immutable_and_identity_is_explicit():
    event = _event()
    assert event.identity == ("s1", "u1")
    with pytest.raises(AttributeError):
        event.text = "changed"
    with pytest.raises(TypeError):
        event.metadata["raw"] = "audio"


def test_provider_protocol_and_final_event_contract():
    provider = DeterministicFakeSTTProvider(["Jarvis status"])
    assert isinstance(provider, SpeechToTextProvider)
    event = provider.transcribe(
        b"pcm", sample_rate=16000, cancellation=VoiceCancellation(),
        session_id="s1", utterance_id="u1", epoch=1,
    )
    assert event == TranscriptEvent(
        text="Jarvis status", is_final=True, sequence=1,
        session_id="s1", utterance_id="u1", provider="fake-stt", epoch=1,
    )


def test_partial_event_never_enters_acceptance_gate():
    gate = TranscriptAcceptanceGate("s1")
    epoch = gate.begin("s1")
    assert gate.accept(_event(final=False, epoch=epoch)) is False


def test_empty_transcript_is_blocked():
    gate = TranscriptAcceptanceGate("s1")
    gate.begin("s1")
    assert gate.accept(_event(text="   ")) is False


def test_duplicate_final_is_blocked():
    gate = TranscriptAcceptanceGate("s1")
    epoch = gate.begin("s1")
    event = _event(epoch=epoch)
    assert gate.accept(event) is True
    assert gate.accept(event) is False


def test_stale_session_is_blocked_after_new_session():
    gate = TranscriptAcceptanceGate("s1")
    old_epoch = gate.begin("s1")
    old = _event(session="s1", epoch=old_epoch)
    gate.begin("s2")
    assert gate.accept(old) is False
    assert gate.accept(_event(session="s2", utterance="u2", epoch=gate.epoch)) is True


def test_cancelled_final_is_blocked_and_epoch_changes():
    gate = TranscriptAcceptanceGate("s1")
    epoch = gate.begin("s1")
    gate.cancel()
    assert gate.accept(_event(epoch=epoch)) is False
    assert gate.epoch != epoch


def test_provider_failure_isolated_as_controlled_exception():
    provider = DeterministicFakeSTTProvider([RuntimeError("decoder failed")])
    with pytest.raises(RuntimeError, match="decoder failed"):
        provider.transcribe(b"pcm", sample_rate=16000, cancellation=VoiceCancellation())


def test_cancellation_prevents_late_fake_result():
    cancellation = VoiceCancellation()
    started = threading.Event()

    def delayed(signal):
        started.set()
        signal.wait(1.0)
        signal.throw_if_cancelled()
        return "too late"

    provider = DeterministicFakeSTTProvider([delayed])
    errors = []

    def run():
        try:
            provider.transcribe(
                b"pcm", sample_rate=16000, cancellation=cancellation,
                session_id="s1", utterance_id="u1",
            )
        except VoiceCancelledError as exc:
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert started.wait(0.5)
    cancellation.cancel("session restarted")
    worker.join(0.5)
    assert not worker.is_alive()
    assert len(errors) == 1


def test_fake_provider_is_deterministic_and_does_not_persist_audio():
    provider = DeterministicFakeSTTProvider(["one", "two"])
    cancellation = VoiceCancellation()
    first = provider.transcribe(b"a", sample_rate=16000, cancellation=cancellation,
                                session_id="s", utterance_id="u1")
    second = provider.transcribe(b"b", sample_rate=16000, cancellation=cancellation,
                                 session_id="s", utterance_id="u2")
    assert [first.text, second.text] == ["one", "two"]
    assert provider.calls[0]["audio_bytes"] == 1
    assert not hasattr(provider, "audio_path")


def test_provider_restart_reopens_fake_without_new_stream_or_database():
    provider = DeterministicFakeSTTProvider(["ok"])
    provider.close()
    provider.restart()
    event = provider.transcribe(b"pcm", sample_rate=16000, cancellation=VoiceCancellation())
    assert event.text == "ok"
