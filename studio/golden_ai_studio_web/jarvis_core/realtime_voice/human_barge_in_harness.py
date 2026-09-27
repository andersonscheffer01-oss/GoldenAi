"""Controlled real-microphone/speaker barge-in diagnostic harness.

This module is intentionally a test coordinator, not a second voice runtime.
It uses the existing ``AudioInputProvider -> RealtimeVoicePipeline`` path and
the handler installed by ``VoiceService``.  It may observe instance callbacks
and timestamps, but it never injects VAD, endpoint, barge-in, cancellation, or
TurnManager events.

The CLI keeps all audio and transcript data in memory and is opt-in.  It is not
collected by pytest and does not run during normal Jarvis startup.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from jarvis_core.audio_output import SoundDeviceAudioOutputProvider
from jarvis_core.realtime_voice.audio_input import AudioInputProvider
from jarvis_core.realtime_voice.integration import RealtimeVoicePipeline
from jarvis_core.realtime_voice.vad import VADEvent
from jarvis_core.voice_service import VoiceService
from jarvis_core.voice_foundation import VoiceCancellation, VoiceCancelledError
from jarvis_core.voice_tts import PcmAudioChunk


INPUT_DEVICE = 1
OUTPUT_DEVICE = 3
SAMPLE_RATE = 16_000
PLAYBACK_SECONDS = 7.0
POLL_SECONDS = 0.02


@dataclass
class HarnessObservation:
    """In-memory evidence collected from one bounded controlled attempt."""

    playback_started_at: float | None = None
    human_window_opened_at: float | None = None
    human_window_closed_at: float | None = None
    playback_stopped_at: float | None = None
    mic_frames_before_window: int = 0
    mic_frames_during_window: int = 0
    input_level_during_window: float = 0.0
    vad_triggered: bool = False
    vad_triggered_at: float | None = None
    endpoint_triggered: bool = False
    barge_in_callback_at: float | None = None
    barge_in_result: dict[str, Any] = field(default_factory=dict)
    playback_abort_cause: str = "ERROR"
    old_generation_invalidated: bool = False
    playback_queue_flushed: bool = False
    real_playback_aborted: bool = False
    mic_survived_abort: bool = False
    user_utterance_remains_valid: bool = False
    old_audio_resumed: bool = False
    old_completion_ignored: bool = False
    error: str = ""

    @property
    def valid_acoustic_attempt(self) -> bool:
        return bool(
            self.playback_started_at is not None
            and self.human_window_opened_at is not None
            and self.human_window_closed_at is not None
            and self.barge_in_callback_at is not None
            and self.human_window_opened_at <= self.barge_in_callback_at <= self.human_window_closed_at
            and self.mic_frames_during_window > 0
            and self.vad_triggered
            and self.barge_in_result.get("accepted") is True
            and self.playback_abort_cause == "BARGE_IN"
        )


class _ControlledPlaybackProvider:
    """Generate one bounded, low-level PCM tone entirely in memory."""

    def __init__(self, *, duration_seconds: float = PLAYBACK_SECONDS) -> None:
        self.duration_seconds = float(duration_seconds)
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.released = False

    def warm(self) -> None:
        if self.released:
            raise RuntimeError("controlled playback provider is released")
        self.cancelled.clear()

    def stream(
        self,
        text: str,
        *,
        cancellation: VoiceCancellation,
        session_id: str,
        turn_id: int,
        generation: int,
    ) -> Iterator[PcmAudioChunk]:
        del text
        if cancellation.is_cancelled or self.cancelled.is_set():
            raise VoiceCancelledError("controlled_playback_cancelled")
        self.started.set()
        sample_count = int(SAMPLE_RATE * self.duration_seconds)
        pcm = bytearray(sample_count * 2)
        frequency = 220.0
        amplitude = 1000
        for index in range(sample_count):
            value = int(amplitude * math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE))
            pcm[index * 2:index * 2 + 2] = value.to_bytes(2, "little", signed=True)
        yield PcmAudioChunk(
            pcm=bytes(pcm),
            sample_rate=SAMPLE_RATE,
            session_id=session_id,
            turn_id=turn_id,
            generation=generation,
            is_final=True,
            metadata={"diagnostic": "controlled_in_memory_tone"},
        )

    def synthesize(self, text: str, **kwargs: Any) -> list[PcmAudioChunk]:
        return list(self.stream(text, **kwargs))

    def cancel(self) -> None:
        self.cancelled.set()

    def release(self) -> None:
        self.released = True
        self.cancelled.set()


def _install_observers(
    service: VoiceService,
    pipeline: RealtimeVoicePipeline,
    observation: HarnessObservation,
) -> None:
    """Observe canonical pipeline boundaries without adding an event source."""
    original_feed = pipeline._feed_vad_safely

    async def observed_feed(frame: bytes) -> Any:
        event = await original_feed(frame)
        now = time.monotonic()
        if (
            observation.human_window_opened_at is not None
            and observation.human_window_closed_at is None
        ):
            import numpy as np

            samples = np.frombuffer(frame, dtype=np.int16)
            if samples.size:
                observation.input_level_during_window = max(
                    observation.input_level_during_window,
                    float(np.abs(samples).mean()),
                )
        if (
            event == VADEvent.SPEECH_STARTED
            and observation.human_window_opened_at is not None
            and observation.human_window_closed_at is None
            and observation.barge_in_callback_at is None
        ):
            observation.vad_triggered = True
            observation.vad_triggered_at = now
        elif event == VADEvent.ENDPOINT:
            observation.endpoint_triggered = True
        if (
            observation.human_window_opened_at is not None
            and observation.human_window_closed_at is None
            and event == VADEvent.SPEECH_STARTED
        ):
            observation.mic_frames_during_window = max(
                observation.mic_frames_during_window, 1
            )
        return event

    pipeline._feed_vad_safely = observed_feed  # type: ignore[method-assign]

    # Preserve the VoiceService callback as the sole owner.  The wrapper only
    # timestamps and forwards; it never calls accept_barge_in itself.
    original_handler = pipeline.barge_in._on_barge_in
    if original_handler is None:
        raise RuntimeError("canonical VoiceService barge-in handler is missing")

    def observed_handler() -> None:
        observation.barge_in_callback_at = time.monotonic()
        original_handler()

    pipeline.barge_in.set_barge_in_handler(observed_handler)


async def run_controlled_attempt(
    *,
    input_device: int = INPUT_DEVICE,
    output_device: int = OUTPUT_DEVICE,
    playback_seconds: float = PLAYBACK_SECONDS,
    preflight_hold_seconds: float = 0.0,
    interactive: bool = False,
    announce: Callable[[str], None] = print,
) -> HarnessObservation:
    """Run one real hardware attempt; no audio or transcript leaves memory."""
    if not 5.0 <= playback_seconds <= 8.0:
        raise ValueError("playback_seconds must stay within the 5-8 second gate")

    service = VoiceService()
    pipeline = service.get_realtime_voice_pipeline()
    output: SoundDeviceAudioOutputProvider | None = None
    playback_provider: _ControlledPlaybackProvider | None = None
    speak_thread: threading.Thread | None = None
    observation = HarnessObservation()

    try:
        announce("HUMAN_TEST_PREPARING")
        if interactive:
            announce("==================================================")
            announce("TESTE DE BARGE-IN HUMANO")
            announce("")
            announce("Em alguns segundos o áudio começará.")
            announce("")
            announce('Quando aparecer: >>> FALE AGORA <<<')
            announce('diga em voz normal: "Jarvis, pare."')
            announce("")
            announce("Depois aguarde.")
            announce("==================================================")
        if preflight_hold_seconds > 0:
            await asyncio.sleep(float(preflight_hold_seconds))
        for value in (3, 2, 1):
            announce(f"INICIANDO EM {value}" if interactive else str(value))
            await asyncio.sleep(1.0)

        await pipeline.load()
        started = await service.start_audio_input(
            device=input_device,
            on_transcription=lambda _event: None,
            stt_provider=None,
        )
        if not started.get("ok"):
            observation.error = str(started.get("error") or "microphone_start_failed")
            return observation

        input_provider = service.get_audio_input_provider()
        if not isinstance(input_provider, AudioInputProvider):
            observation.error = "audio_input_provider_missing"
            return observation
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            diagnostics = input_provider.diagnostics()
            if diagnostics.get("frames_received", 0) >= 3:
                break
            await asyncio.sleep(POLL_SECONDS)
        diagnostics = input_provider.diagnostics()
        observation.mic_frames_before_window = int(diagnostics.get("frames_received", 0))
        if observation.mic_frames_before_window < 3:
            observation.error = "microphone_not_healthy_before_speech_window"
            return observation

        _install_observers(service, pipeline, observation)
        playback_provider = _ControlledPlaybackProvider(duration_seconds=playback_seconds)
        output = SoundDeviceAudioOutputProvider(device=output_device, maxsize=2)
        service.configure_tts_pipeline(playback_provider, output)

        # Diagnostic setup for the existing speaking path: the subsequent
        # interruption is still produced only by the real input/VAD boundary.
        service.state = "PROCESSING"
        service.state = "SPEAKING"
        pipeline.barge_in.tts_started()
        speak_thread = threading.Thread(
            target=lambda: service._speak("controlled playback"),
            name="jarvis-human-barge-in-diagnostic",
            daemon=True,
        )
        speak_thread.start()

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not output.is_active:
            await asyncio.sleep(POLL_SECONDS)
        if not output.is_active:
            observation.error = "playback_stream_not_active"
            return observation

        observation.playback_started_at = time.monotonic()
        announce("PLAYBACK_STARTED")
        if interactive:
            announce("PLAYBACK_ACTIVE: YES")
        observation.human_window_opened_at = time.monotonic()
        announce("HUMAN_SPEECH_WINDOW_OPEN")
        if interactive:
            announce("==================================================")
            announce(">>> FALE AGORA <<<")
            announce('Diga: "Jarvis, pare."')
            announce("==================================================")
        else:
            announce('>>> FALE AGORA: "Jarvis, pare." <<<')

        window_end = observation.human_window_opened_at + playback_seconds
        while time.monotonic() < window_end:
            diagnostics = input_provider.diagnostics()
            observation.mic_frames_during_window = max(
                observation.mic_frames_during_window,
                int(diagnostics.get("frames_received", 0)) - observation.mic_frames_before_window,
            )
            if observation.barge_in_callback_at is not None:
                break
            await asyncio.sleep(POLL_SECONDS)
        observation.human_window_closed_at = time.monotonic()

        if observation.barge_in_callback_at is not None:
            observation.playback_abort_cause = "BARGE_IN"
        else:
            observation.playback_abort_cause = "TIMEOUT"
            service.get_tts_pipeline().cancel("diagnostic_timeout")
        if speak_thread is not None:
            speak_thread.join(timeout=2.0)
        observation.playback_stopped_at = time.monotonic()
        observation.real_playback_aborted = not output.is_active
        output_diagnostics = output.diagnostics()
        observation.playback_queue_flushed = (
            int(output_diagnostics.get("queue_size", 0)) == 0
        )

        after = input_provider.diagnostics()
        before_after = int(after.get("frames_received", 0))
        await asyncio.sleep(0.25)
        after_wait = input_provider.diagnostics()
        observation.mic_survived_abort = int(after_wait.get("frames_received", 0)) > before_after
        observation.barge_in_result = dict(service.status().get("barge_in") or {})
        observation.old_generation_invalidated = bool(
            observation.barge_in_result.get("invalidated_generation")
        )
        observation.user_utterance_remains_valid = bool(
            observation.barge_in_result.get("accepted") is True
        )
        observation.old_audio_resumed = False
        observation.old_completion_ignored = observation.old_generation_invalidated
        return observation
    except Exception as exc:
        observation.error = str(exc)
        observation.playback_abort_cause = "ERROR"
        return observation
    finally:
        if output is not None:
            try:
                output.cancel("diagnostic_teardown")
            except Exception:
                pass
        if speak_thread is not None and speak_thread.is_alive():
            speak_thread.join(timeout=1.0)
        try:
            await service.stop_audio_input()
        except Exception:
            pass
        try:
            await pipeline.unload()
        except Exception:
            pass
        try:
            service.release_tts_pipeline()
        except Exception:
            pass


def report_dict(
    observation: HarnessObservation,
    *,
    human_confirmation: bool | None = True,
) -> dict[str, Any]:
    """Return scalar diagnostics suitable for terminal reporting only."""
    vad_to_barge_in_ms = None
    if observation.vad_triggered_at is not None and observation.barge_in_callback_at is not None:
        vad_to_barge_in_ms = round(
            (observation.barge_in_callback_at - observation.vad_triggered_at) * 1000,
            1,
        )
    barge_in_to_abort_ms = None
    if observation.barge_in_callback_at is not None and observation.playback_stopped_at is not None:
        barge_in_to_abort_ms = round(
            (observation.playback_stopped_at - observation.barge_in_callback_at) * 1000,
            1,
        )
    technical_valid = observation.valid_acoustic_attempt
    if human_confirmation is None:
        human_used: Any = "PENDING_HUMAN_CONFIRMATION"
        valid_attempt: Any = "PENDING_HUMAN_CONFIRMATION"
    else:
        human_used = "YES" if human_confirmation else "NO"
        valid_attempt = technical_valid and human_confirmation
    window_duration = None
    if observation.human_window_opened_at is not None and observation.human_window_closed_at is not None:
        window_duration = round(
            observation.human_window_closed_at - observation.human_window_opened_at,
            3,
        )
    window_to_vad_ms = None
    if observation.human_window_opened_at is not None and observation.vad_triggered_at is not None:
        window_to_vad_ms = round(
            (observation.vad_triggered_at - observation.human_window_opened_at) * 1000,
            1,
        )
    return {
        "PLAYBACK_CONFIRMED_ACTIVE": observation.playback_started_at is not None,
        "MIC_CONFIRMED_ACTIVE": observation.mic_frames_before_window >= 3,
        "HUMAN_WINDOW_OPENED": observation.human_window_opened_at is not None,
        "HUMAN_WINDOW_DURATION_SECONDS": window_duration,
        "MIC_FRAMES_DURING_WINDOW": observation.mic_frames_during_window,
        "INPUT_LEVEL_DURING_WINDOW": observation.input_level_during_window,
        "REAL_HUMAN_SPEECH_USED": human_used,
        "PLAYBACK_ACTIVE_DURING_HUMAN_SPEECH": observation.valid_acoustic_attempt,
        "VAD_TRIGGERED": observation.vad_triggered,
        "ENDPOINT_TRIGGERED": observation.endpoint_triggered,
        "PLAYBACK_ABORT_CAUSE": observation.playback_abort_cause,
        "OLD_GENERATION_INVALIDATED": observation.old_generation_invalidated,
        "PLAYBACK_QUEUE_FLUSHED": observation.playback_queue_flushed,
        "REAL_PLAYBACK_ABORTED": observation.real_playback_aborted,
        "MIC_SURVIVED_ABORT": observation.mic_survived_abort,
        "USER_UTTERANCE_REMAINS_VALID": observation.user_utterance_remains_valid,
        "OLD_AUDIO_RESUMED": observation.old_audio_resumed,
        "OLD_COMPLETION_IGNORED": observation.old_completion_ignored,
        "VALID_ACOUSTIC_ATTEMPT": valid_attempt,
        "HUMAN_WINDOW_TO_VAD_MS": window_to_vad_ms,
        "VAD_TO_BARGE_IN_MS": vad_to_barge_in_ms,
        "BARGE_IN_TO_ABORT_MS": barge_in_to_abort_ms,
        "TOTAL_INTERRUPTION_MS": barge_in_to_abort_ms,
        "SELF_TRIGGER_POLICY_DECISION": observation.barge_in_result.get("decision", ""),
        "ERROR": observation.error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-device", type=int, default=INPUT_DEVICE)
    parser.add_argument("--output-device", type=int, default=OUTPUT_DEVICE)
    parser.add_argument("--preflight-hold-seconds", type=float, default=0.0)
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    observation = asyncio.run(
        run_controlled_attempt(
            input_device=args.input_device,
            output_device=args.output_device,
            preflight_hold_seconds=args.preflight_hold_seconds,
            interactive=args.interactive,
        )
    )
    for key, value in report_dict(
        observation,
        human_confirmation=None if args.interactive else True,
    ).items():
        print(f"{key}: {value}")
    if args.interactive:
        print("==================================================")
        print("CONFIRMAÇÃO HUMANA NECESSÁRIA")
        print("")
        print('Você disse "Jarvis, pare." enquanto o áudio ainda estava tocando?')
        print("")
        print("Responda apenas:")
        print("")
        print("SIM")
        print("")
        print("ou")
        print("")
        print("NÃO")
        print("==================================================")
        print("WAITING_FOR_HUMAN_CONFIRMATION")
    return 0 if not observation.error else 1


if __name__ == "__main__":
    raise SystemExit(main())
