"""
Jarvis Desktop Voice Service — Fase 8
=====================================
Servico de voz LOCAL: ouve o microfone do PC direto, SEM navegador.

Fluxo:
    Windows liga
        ↓
    Golden inicia (server_agent → start_server)
        ↓
    VoiceService inicia (thread daemon)
        ↓
    Usuario fala: "Jarvis"
        ↓
    Estado OUVINDO → comando ("abra o metatrader")
        ↓
    Whisper (faster-whisper) STT
        ↓
    Brain (Ollama) → Registry → Tool Windows
        ↓
    TTS nas auto-falantes: "MetaTrader aberto."

Reutiliza (nao duplica):
    - jarvis_core.voice.JarvisVoice  (wake word + STT + gravacao)
    - jarvis_core.brain.JarvisBrain  (interpretacao LLM)
    - jarvis_core.service.JarvisService (execucao de tools + seguranca + auditoria)

Controle:
    JARVIS_VOICE_SERVICE=0  → nao inicia automaticamente com o Golden.
    JARVIS_VOICE_TTS=edge|sapi|auto  → modo de TTS (default: auto).
    POST /api/jarvis/voice-service/stop|start  → liga/desliga em runtime.

TTS (ordem no modo auto):
    1. edge-tts (voz neural, online) → mp3 tocado via MediaPlayer nativo.
    2. SAPI do Windows via pywin32 (offline) — sempre disponivel.
"""

import asyncio
import io
import os
import re
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from .voice import get_voice
from .voice_foundation import VoiceCancellation, VoiceSession, TranscriptEvent
from .output_mode import get_output_mode_manager, to_spoken_text
from .realtime_voice.state_machine import (
    ConversationalState,
    IllegalTransition,
    VoiceStateMachine,
)
from .realtime_voice.audio_input import AudioInputProvider
from .realtime_voice.audio_queue import AudioFrameQueue
from .audio_output import SoundDeviceAudioOutputProvider
from .voice_tts import PcmAudioChunk
from .audio_experience import AudioExperienceManager, MicrophoneProfileStore
from .voice_feature_flags import (
    adaptive_microphone_enabled,
    gemini_live_enabled,
    snapshot as voice_feature_snapshot,
)
from .voice_confirmation import classify_confirmation
from .personality_profiles import DEFAULT_PERSONALITY, get_personality, personality_instruction
from .realtime_voice.barge_in import EchoDecision, SelfTriggerPolicy
from .realtime_voice.wake_lifecycle import WakeLifecycle
from .streaming import is_streaming_enabled, is_barge_in_enabled
from .streaming.turn_manager import TurnManager
from .streaming.barge_in_calibration import (
    BARGE_IN_PERSISTENCE_BLOCKS,
    BARGE_IN_ADAPTIVE_MARGIN,
    BARGE_IN_MIN_ABSOLUTE,
    BARGE_IN_RMS_THRESHOLD,
)

log = __import__("logging").getLogger(__name__)


def _safe_voice_detail(value: Any) -> str:
    """Bound diagnostics without exposing credentials or URLs."""
    text = str(value or "")[:240]
    text = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", text)
    return re.sub(
        r"([?&](?:key|token|access_token|authorization)=)[^&\s]+",
        r"\1[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )

# Limiar RMS para ignorar audio puramente silencioso (evita gastar Whisper).
SILENCE_RMS = 150.0
# Janela maxima de escuta por ciclo (segundos).
LISTEN_WINDOW_SECONDS = 6


def _wav_rms(wav_bytes: bytes) -> float:
    """RMS do WAV em memoria (int16 mono). 0.0 se vazio/invalido."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            frames = wf.readframes(wf.getnframes())
        import array
        samples = array.array("h", frames)
        if not samples:
            return 0.0
        total = 0.0
        for s in samples:
            total += float(s) * float(s)
        return (total / len(samples)) ** 0.5
    except Exception:
        return 0.0


class VoiceService:
    """Thread daemon que ouve o microfone e executa comandos do Jarvis."""

    def __init__(self):
        self.enabled = os.getenv("JARVIS_VOICE_SERVICE", "1").lower() not in ("0", "false", "off")
        self.tts_mode = os.getenv("JARVIS_VOICE_TTS", "auto").lower()
        self._state_machine = VoiceStateMachine(ConversationalState.STOPPED)
        self._state_transition_errors = 0
        self._last_state_error = ""
        self._legacy_state = "OFF"
        self._voice_session = VoiceSession(state=ConversationalState.STOPPED,
                                           metadata={"owner": "VoiceService"})
        self._operation_cancellation = VoiceCancellation()
        self._session_id = self._voice_session.session_id
        self._wake_lifecycle = WakeLifecycle(
            self._state_machine, session_id=self._session_id
        )
        self._realtime_pipeline = None
        self._audio_input_provider: Optional[AudioInputProvider] = None
        self._realtime_cancellation: Optional[VoiceCancellation] = None
        self.state = "OFF"
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.service = None  # JarvisService injetado no start()
        self.last_heard = ""
        self.last_response = ""
        self.last_error = ""
        self.last_activity = 0.0
        self.last_level = 0  # RMS real do ultimo bloco de audio captado
        self.last_level_at = 0.0
        self.last_event_id = 0
        self.last_event = {}  # ultimo comando executado (id, heard, route, timings...)
        self.stats = {"heard": 0, "commands": 0, "errors": 0}
        self.last_rejection = {}
        self._ignore_input_until = 0.0
        self._latest_capture_at = 0.0
        self._tts_first_audio_at = 0.0
        self._speaking_event = threading.Event()
        self._tts_epoch = 0
        self._voice = None
        self._sapi = None
        self._self_trigger_policy = SelfTriggerPolicy()
        self._last_barge_in = {}
        # Optional provider-neutral TTS/output seam.  The legacy Edge/SAPI
        # path remains the default until a provider is explicitly configured.
        self._tts_pipeline = None
        self._streaming_tts = None
        # P1.4C: TurnManager + barge-in + conversation context
        self._turn_manager = TurnManager()
        self._current_turn_id = 0
        self._conversation_messages: list[dict] = []  # follow-up context
        self._barge_in_cancel = threading.Event()     # cancel signal for orchestrator
        self._barge_in_monitor_thread: threading.Thread | None = None
        self._barge_in_monitor_stop = threading.Event()
        # P1.4C v2: Audio handoff — separate monitor buffer from utterance buffer
        self._barge_in_pre_roll: list[np.ndarray] = []  # circular pre-roll from monitor
        self._barge_in_preroll_max_blocks = 8  # ~512ms at 64ms/block
        self._barge_in_detected_at: float = 0.0  # timestamp of detection
        self._barge_in_user_audio: list[np.ndarray] = []  # user speech after detection
        self._barge_in_followup_active = False  # True while capturing follow-up
        self._utterance_source: str = ""  # "BARGE_IN" or "NORMAL"
        self._push_to_talk_requested = threading.Event()
        self._desktop_session_id: str = ""
        profile_path = os.getenv(
            "JARVIS_VOICE_PROFILE_PATH",
            str(Path.home() / "AppData" / "Local" / "GoldenAI" / "voice_profiles.json"),
        )
        self._audio_experience = AudioExperienceManager(
            profile_store=MicrophoneProfileStore(profile_path)
        )
        self._selected_microphone_id = os.getenv("JARVIS_VOICE_MICROPHONE_ID", "").strip()
        if not self._selected_microphone_id:
            self._selected_microphone_id = self._audio_experience.profile_store.load_selected_endpoint()
        self._personality_id = os.getenv("JARVIS_VOICE_PERSONALITY", DEFAULT_PERSONALITY).strip().casefold() or DEFAULT_PERSONALITY
        # Presentation preferences are kept at the VoiceService boundary.  The
        # safe default is Gemini Live; local TTS is only available when an
        # explicit legacy/local profile is requested and is never a fallback.
        self._voice_name = os.getenv("JARVIS_VOICE_NAME", "Charon").strip() or "Charon"
        self._voice_mode = "gemini_live"
        self._gemini_live_provider = None
        self._gemini_voice_change_pending = False
        self._gemini_runtime_loop = None
        self._gemini_runtime_thread: threading.Thread | None = None
        self._gemini_runtime_ready = threading.Event()
        self._gemini_audio_queue: asyncio.Queue[bytes] | None = None
        self._gemini_audio_sender: asyncio.Task | None = None
        self._gemini_audio_receiver: asyncio.Task | None = None
        self._gemini_output = None
        self._gemini_audio_generation = 0
        self._gemini_audio_metrics = {
            "frames_captured": 0, "frames_sent": 0, "bytes_sent": 0,
            "audio_chunks_received": 0, "bytes_received": 0,
            "input_drops": 0, "output_drops": 0,
        }
        self._gemini_preview_active = False
        self._gemini_preview_text = ""
        self._gemini_preview_watch_task: asyncio.Task | None = None
        self._gemini_preview_turn_baseline = 0
        self._conversation_id: str = uuid.uuid4().hex  # persists across cancelled turns
        # Adapter 4 lifecycle guard.  This protects only start/stop bookkeeping;
        # it does not replace the canonical VoiceStateMachine or TurnManager.
        self._lifecycle_lock = threading.RLock()
        self._realtime_stop_task = None
        self._recovery_in_progress = False
        self._last_recovery = {}

    _REALTIME_STATE_MAP = {
        "idle": "WAITING_WAKE",
        "listening": "LISTENING",
        "transcribing": "TRANSCRIBING",
        "thinking": "PROCESSING",
        "speaking": "SPEAKING",
        "interrupted": "INTERRUPTED",
        "error": "ERROR",
        "stopped": "OFF",
    }

    _STATE_MAP = {
        "OFF": ConversationalState.STOPPED,
        "OUVINDO": ConversationalState.IDLE,
        "WAITING_WAKE": ConversationalState.IDLE,
        "WAKE_DETECTED": ConversationalState.LISTENING,
        "LISTENING": ConversationalState.LISTENING,
        "CAPTURING_FOLLOWUP": ConversationalState.LISTENING,
        "TRANSCRIBING": ConversationalState.TRANSCRIBING,
        "PROCESSING": ConversationalState.THINKING,
        "SPEAKING": ConversationalState.SPEAKING,
        "INTERRUPTED": ConversationalState.INTERRUPTED,
        "ERROR": ConversationalState.ERROR,
    }

    @property
    def state(self) -> str:
        return self._legacy_state

    @state.setter
    def state(self, value: str) -> None:
        legacy = str(value)
        self._legacy_state = legacy
        machine = getattr(self, "_state_machine", None)
        if machine is None:
            return
        target = self._STATE_MAP.get(legacy)
        if target is None:
            self._last_state_error = f"unknown voice state: {legacy}"
            self._state_transition_errors += 1
            return
        try:
            machine.transition(target)
        except IllegalTransition as exc:
            self._last_state_error = str(exc)
            self._state_transition_errors += 1
            log.warning("Voice state transition rejected: %s", exc)
            if machine.state is not ConversationalState.STOPPED and target is not ConversationalState.ERROR:
                try:
                    machine.transition(ConversationalState.ERROR)
                except IllegalTransition:
                    pass
        self._voice_session.state = machine.state

    # ═══════════════════════════════════════════════════════════════
    # CICLO DE VIDA
    # ═══════════════════════════════════════════════════════════════

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, service) -> dict:
        """Inicia a escuta local. `service` = JarvisService (obrigatorio)."""
        with self._lifecycle_lock:
            if self.is_running():
                return {"ok": True, "message": "VoiceService ja esta rodando."}
            if self._audio_input_provider is not None and self._audio_input_provider.is_running:
                return {
                    "ok": False,
                    "error": "AudioInputProvider ja esta capturando; recuse o loop legado.",
                }
            if service is None:
                return {"ok": False, "error": "JarvisService nao fornecido."}

            # A restart is an explicit new session.  The old operation token,
            # output generation, and turn are never reused by session B.
            if self._streaming_tts is not None:
                self._streaming_tts.cancel("session_restart")
            if self._tts_pipeline is not None:
                self._tts_pipeline.cancel("session_restart")
            self._voice_session = VoiceSession(metadata={"owner": "VoiceService"})
            self._session_id = self._voice_session.session_id
            self._wake_lifecycle.reset_session(self._session_id)
            self._wake_lifecycle.arm()
            self._operation_cancellation = VoiceCancellation()
            self._current_turn_id = self._turn_manager.new_turn()
            self._tts_epoch = 0
            self._recovery_in_progress = False
            self._last_recovery = {}
            self.stop_event.clear()
            self.service = service
            self._voice = get_voice()
            self._voice.warmup_async()
            self.thread = threading.Thread(target=self._loop, name="jarvis-voice", daemon=True)
            self.thread.start()
            self.state = "OUVINDO"
            return {"ok": True, "message": 'VoiceService iniciado. Diga "Jarvis" + comando.'}

    def stop(self) -> dict:
        with self._lifecycle_lock:
            was_running = self.is_running()
            self.stop_event.set()
            if self._streaming_tts is not None:
                self._streaming_tts.cancel("runtime_shutdown")
            if self._tts_pipeline is not None:
                self._tts_pipeline.cancel("runtime_shutdown")
            if self._audio_input_provider is not None:
                self._audio_input_provider.stop()
            if self._realtime_pipeline is not None:
                self._realtime_pipeline.cancel_transcription("runtime_shutdown")
                self._realtime_pipeline.queue.cancel()
                self._schedule_realtime_stop()
            self._wake_lifecycle.shutdown()
            self._voice_session.cancel("runtime_shutdown")
            self._operation_cancellation.cancel("runtime_shutdown")
            self._turn_manager.cancel_current()
            self._stop_barge_in_monitor()
            self._turn_manager.cleanup_all()
            self._barge_in_cancel.clear()
            self._conversation_messages.clear()
            self._barge_in_pre_roll.clear()
            self._barge_in_user_audio.clear()
            self._barge_in_followup_active = False
            self._utterance_source = ""
            self._push_to_talk_requested.clear()
            self._desktop_session_id = ""
            self._conversation_id = uuid.uuid4().hex
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join(timeout=2.0)
            self.state = "OFF"
            return {
                "ok": True,
                "message": "VoiceService parado." if was_running else "VoiceService nao estava rodando.",
                "already_stopped": not was_running,
            }

    def _schedule_realtime_stop(self) -> None:
        """Ask the existing async pipeline to finish without blocking its loop."""
        pipeline = self._realtime_pipeline
        if pipeline is None:
            return
        loop = getattr(pipeline, "_loop", None)
        if loop is None or not loop.is_running():
            return
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is loop:
            self._realtime_stop_task = loop.create_task(pipeline.stop())
            return
        try:
            future = asyncio.run_coroutine_threadsafe(pipeline.stop(), loop)
            future.result(timeout=2.0)
        except Exception as exc:
            # Cancellation and the queue sentinel already make the path safe;
            # keep the failure observable without blocking shutdown forever.
            self.last_error = f"realtime_stop: {_safe_voice_detail(exc)}"

    def _on_realtime_state_change(
        self, value: str, external: Optional[Callable[[str], None]] = None
    ) -> None:
        """Mirror pipeline state into the existing VoiceService state owner."""
        legacy = self._REALTIME_STATE_MAP.get(str(value).casefold())
        if legacy is not None and not (
            legacy == "OFF" and self._voice_session.cancellation.is_cancelled
        ):
            self.state = legacy
        if external is not None:
            try:
                external(value)
            except Exception:
                log.exception("external realtime state callback raised")

    def _recover_after_failure(self, component: str, error: Any) -> bool:
        """Perform one bounded, identity-invalidating recovery transition."""
        with self._lifecycle_lock:
            if self._recovery_in_progress:
                return False
            self._recovery_in_progress = True
            try:
                message = str(error or "unknown failure")[:240]
                self._last_recovery = {
                    "component": str(component),
                    "error": message,
                    "session_id": self._session_id,
                    "previous_turn_id": self._current_turn_id,
                    "at": time.time(),
                }
                self.stats["recovery_attempts"] = self.stats.get("recovery_attempts", 0) + 1
                self.stats["component_failures"] = self.stats.get("component_failures", 0) + 1
                self.last_error = f"{component}: {message}"

                # Invalidate before cancellation so late Core/TTS callbacks can
                # never become current again.
                self._tts_epoch += 1
                self._operation_cancellation.cancel(f"{component}_failure")
                if self._streaming_tts is not None:
                    self._streaming_tts.cancel(f"{component}_failure")
                if self._tts_pipeline is not None:
                    self._tts_pipeline.cancel(f"{component}_failure")
                self._turn_manager.cancel_current()
                self._current_turn_id = self._turn_manager.new_turn()
                if (
                    self._realtime_pipeline is not None
                    and self._realtime_pipeline.session_id == self._session_id
                ):
                    self._realtime_pipeline.replace_turn(self._current_turn_id)
                self._operation_cancellation = VoiceCancellation()
                self._barge_in_cancel.clear()
                self._speaking_event.clear()

                if self.stop_event.is_set() or self._voice_session.cancellation.is_cancelled:
                    self._last_recovery["result"] = "shutdown"
                    return False
                if self._state_machine.state is not ConversationalState.STOPPED:
                    self.state = "WAITING_WAKE"
                self._last_recovery["result"] = "recovered"
                return True
            finally:
                self._recovery_in_progress = False

    def cancel_current_operation(self, reason: str = "operation_cancelled") -> dict:
        """Cooperatively cancel the active turn/TTS boundary without killing a thread."""
        changed = self._operation_cancellation.cancel(reason)
        if self._tts_pipeline is not None:
            self._tts_pipeline.cancel(reason)
        if self._streaming_tts is not None:
            self._streaming_tts.cancel(reason)
        self._barge_in_cancel.set()
        self._turn_manager.cancel_current()
        if self._realtime_pipeline is not None:
            self._realtime_pipeline.cancel_transcription(reason)
        if self.state in {"TRANSCRIBING", "PROCESSING", "SPEAKING"}:
            self.state = "INTERRUPTED"
        return {"ok": True, "cancelled": changed, "reason": reason}

    def accept_barge_in(
        self,
        *,
        source: str = "unknown",
        audio_level: float = 0.0,
        prepare_followup: bool = True,
    ) -> dict[str, Any]:
        """Invalidate the speaking turn before cancelling its work.

        ``source`` is a classification hint from the VAD boundary, not an
        acoustic claim. Unknown input is allowed after the normal speaking
        gate; explicit self-output is ignored by the policy.
        """
        try:
            decision = self._self_trigger_policy.classify(
                source,
                tts_active=self.state == "SPEAKING",
                audio_level=audio_level,
            )
        except Exception as exc:
            log.warning("Self-trigger policy failed safely: %s", exc)
            self._last_barge_in = {
                "accepted": False,
                "decision": EchoDecision.UNCERTAIN.value,
                "reason": "self_trigger_policy_failed",
            }
            return {"ok": False, **self._last_barge_in}
        if decision is EchoDecision.IGNORE_AS_SELF_TRIGGER:
            self._last_barge_in = {
                "accepted": False,
                "decision": decision.value,
                "source": str(source or "unknown"),
            }
            return {"ok": True, **self._last_barge_in}
        if self.state != "SPEAKING":
            self._last_barge_in = {
                "accepted": False,
                "decision": decision.value,
                "reason": "not_speaking",
            }
            return {"ok": False, **self._last_barge_in}

        # Invalidate first. Every subsequent cancellation and late callback
        # observes a generation/turn that is already obsolete.
        self._tts_epoch += 1
        invalidated_generation = self._tts_epoch
        old_operation = self._operation_cancellation
        old_operation.cancel("barge_in")
        self._barge_in_cancel.set()
        self._turn_manager.cancel_current()
        if self._tts_pipeline is not None:
            self._tts_pipeline.cancel("barge_in")
        if self._streaming_tts is not None:
            self._streaming_tts.cancel("barge_in")

        new_turn_id = self._turn_manager.new_turn()
        self._current_turn_id = new_turn_id
        if self._realtime_pipeline is not None:
            self._realtime_pipeline.replace_turn(new_turn_id)
        # A new turn gets a fresh operation token; the old token remains
        # cancelled for any work that still holds it.
        self._operation_cancellation = VoiceCancellation()

        if self._state_machine.state is ConversationalState.SPEAKING:
            self.state = "INTERRUPTED"
            self.state = "LISTENING"
        if prepare_followup:
            self._barge_in_followup_active = True
            self._utterance_source = "BARGE_IN"
        self._last_barge_in = {
            "accepted": True,
            "decision": decision.value,
            "source": str(source or "unknown"),
            "invalidated_generation": invalidated_generation,
            "new_turn_id": new_turn_id,
            "prepare_followup": prepare_followup,
        }
        log.info(
            "[BARGE-IN] accepted: generation=%d new_turn=%d decision=%s",
            invalidated_generation,
            new_turn_id,
            decision.value,
        )
        return {"ok": True, **self._last_barge_in}

    def classify_input_during_output(
        self, *, source: str = "unknown", audio_level: float = 0.0
    ) -> str:
        """Classify synthetic/input evidence while preserving output awareness."""
        try:
            return self._self_trigger_policy.classify(
                source,
                tts_active=self.state == "SPEAKING",
                audio_level=audio_level,
            ).value
        except Exception:
            return EchoDecision.UNCERTAIN.value

    def accept_tts_chunk(self, chunk: Any) -> bool:
        """Apply the current VoiceService owner gate to a provider callback."""
        if self._tts_pipeline is None:
            return False
        return self._tts_pipeline.accept_chunk(chunk)

    def set_enabled(self, value: bool) -> dict:
        self.enabled = bool(value)
        if not self.enabled:
            return {**self.stop(), "enabled": False}
        return {"ok": True, "enabled": True}

    def arm_wake(self) -> dict:
        """Arm the existing wake lifecycle without opening audio hardware."""
        changed = self._wake_lifecycle.arm()
        self._voice_session.state = self._state_machine.state
        self.state = "WAITING_WAKE"
        return {
            "ok": True,
            "armed": self._wake_lifecycle.armed,
            "changed": changed,
            "session_id": self._wake_lifecycle.session_id,
        }

    def activate_wake(self, activation_id: str, session_id: str = "") -> dict:
        """Accept one wake event and move the shared machine to LISTENING."""
        activation = self._wake_lifecycle.activate(
            activation_id, session_id=session_id or None
        )
        if activation is None:
            return {"ok": False, "reason": "stale_or_duplicate_wake"}
        self.state = "WAKE_DETECTED"
        return {
            "ok": True,
            "session_id": activation.session_id,
            "activation_id": activation.activation_id,
            "sequence": activation.sequence,
            "observed_at": activation.observed_at,
        }

    def complete_wake(self, activation_id: str = "") -> dict:
        """Complete the current wake activation without invoking Core."""
        completed = self._wake_lifecycle.complete(activation_id or None)
        if completed and self._wake_lifecycle.armed:
            self.state = "WAITING_WAKE"
        return {"ok": completed, "armed": self._wake_lifecycle.armed}

    def cancel_wake(self) -> dict:
        """Disarm wake cooperatively and discard the active activation."""
        changed = self._wake_lifecycle.cancel()
        self._voice_session.state = self._state_machine.state
        self.state = "OFF"
        return {"ok": True, "changed": changed, "armed": False}

    def get_realtime_voice_pipeline(self):
        """Return the optional realtime pipeline owned by this service."""
        if self._realtime_pipeline is None:
            from .realtime_voice.integration import RealtimeVoicePipeline
            self._realtime_pipeline = RealtimeVoicePipeline(
                state_machine=self._state_machine,
                self_trigger_policy=self._self_trigger_policy,
            )
            self._realtime_pipeline.barge_in.set_barge_in_handler(
                lambda: self.accept_barge_in(
                    source="user_speech", prepare_followup=False
                )
            )
        return self._realtime_pipeline

    def get_audio_input_provider(self) -> Optional[AudioInputProvider]:
        """Return the single provider owned by this VoiceService, if created."""
        return self._audio_input_provider

    def list_microphones(self) -> list[dict[str, Any]]:
        """List deduplicated input endpoints without opening a stream."""
        return [endpoint.public() for endpoint in self._audio_experience.enumerate_microphones()]

    def selected_microphone_id(self) -> str:
        """Return the persisted stable endpoint without opening a stream."""
        return str(self._selected_microphone_id or "")

    def select_microphone(self, endpoint_id: str = "") -> dict[str, Any]:
        """Select a stable endpoint for the opt-in realtime provider."""
        value = str(endpoint_id or "").strip()[:240]
        if not value:
            self._selected_microphone_id = ""
            return {"ok": True, "selected": ""}
        endpoint = next((item for item in self._audio_experience.enumerate_microphones()
                         if item.stable_id == value), None)
        if endpoint is None:
            return {"ok": False, "error": "MICROPHONE_NOT_FOUND"}
        self._selected_microphone_id = endpoint.stable_id
        self._audio_experience.profile_store.save_selected_endpoint(endpoint.stable_id)
        return {"ok": True, "selected": endpoint.public()}

    def configure_conversation_profile(self, *, personality: str | None = None,
                                       voice: str | None = None,
                                       mode: str | None = None) -> dict[str, Any]:
        """Change presentation preferences without changing policy or tools."""
        voice_changed = False
        personality_changed = False
        live_connected_before = self._is_gemini_live_connected()
        requested_voice = None
        if voice is not None:
            # Validate before mutating any other preference so a bad profile
            # update is transactional from the Desktop's perspective.
            from .gemini_live_provider import normalize_gemini_live_voice
            requested_voice = normalize_gemini_live_voice(voice)
        if personality is not None:
            requested_personality = get_personality(personality).id
            personality_changed = requested_personality != self._personality_id
            self._personality_id = requested_personality
        if voice is not None:
            # Gemini applies ``voice_name`` only during session setup.  Reject
            # unknown values locally and never let a stale preference reach
            # the WebSocket as a server-side 1007 invalid argument.
            assert requested_voice is not None
            voice_changed = requested_voice != self._voice_name
            self._voice_name = requested_voice
            live_provider = self._gemini_live_provider
            if live_provider is not None:
                config = getattr(live_provider, "config", None)
                if config is None:
                    config = getattr(getattr(live_provider, "provider", None), "config", None)
                if config is not None:
                    from dataclasses import replace
                    owner = live_provider if hasattr(live_provider, "config") else live_provider.provider
                    owner.config = replace(config, voice=self._voice_name)
            if voice_changed and live_connected_before:
                self._gemini_voice_change_pending = True
        if mode is not None:
            requested_mode = str(mode).casefold()
            if requested_mode not in {"local", "gemini_live"}:
                raise ValueError("unsupported_voice_mode")
            self._voice_mode = requested_mode
        result = self.conversation_profile()
        if voice_changed and live_connected_before:
            result["voice_change_requires_reconnect"] = True
            result["voice_change_scope"] = "current_session_reconnect"
        if personality_changed and live_connected_before:
            result["personality_change_requires_reconnect"] = True
        if live_connected_before and (voice_changed or personality_changed):
            result["profile_change_requires_reconnect"] = True
        return result

    def _is_gemini_live_connected(self) -> bool:
        provider = self._gemini_live_provider
        if provider is None:
            return False
        return bool(getattr(provider, "connected", False)) or bool(
            getattr(getattr(provider, "provider", None), "connected", False)
        )

    def conversation_profile(self) -> dict[str, Any]:
        profile = get_personality(self._personality_id)
        live_provider = self._gemini_live_provider
        live_connected = self._is_gemini_live_connected()
        live_attached = self._gemini_live_provider is not None
        effective_mode = (
            "gemini_live"
            if live_connected
            else "gemini_live_unavailable"
            if self._voice_mode == "gemini_live"
            else "local"
        )
        return {"personality": profile.id, "personality_label": profile.label,
                "personality_instruction": personality_instruction(profile.id),
                "voice": self._voice_name,
                "requested_mode": self._voice_mode,
                "mode": effective_mode,
                "effective_mode": effective_mode,
                "gemini_live_attached": live_attached,
                "gemini_live_connected": live_connected,
                "voice_change_requires_reconnect": bool(self._gemini_voice_change_pending)}

    def _apply_personality_to_brain(self, brain: Any) -> None:
        """Attach presentation-only voice style to the canonical Brain seam."""
        if brain is not None:
            setattr(brain, "_voice_style_instruction", personality_instruction(self._personality_id))

    def attach_gemini_live_provider(self, provider: Any) -> dict[str, Any]:
        """Attach an already-reviewed/injected provider; does not connect it."""
        self._gemini_live_provider = provider
        # The native Live transport exposes completed input/output transcripts
        # through a bounded observer hook.  Persisting them uses the same
        # canonical JarvisService store as text and Gateway turns.
        nested = getattr(provider, "provider", None)
        if nested is not None and hasattr(nested, "_event_sink"):
            previous_sink = getattr(nested, "_event_sink", None)
            def observe(event):
                if callable(previous_sink):
                    try:
                        previous_sink(event)
                    except Exception:
                        pass
                self._on_gemini_provider_event(event)
            nested._event_sink = observe
        return self.conversation_profile()

    def _on_gemini_provider_event(self, event: Any) -> None:
        if not isinstance(event, dict) or event.get("event") != "turn_complete":
            return
        heard = str(event.get("input_transcript") or "").strip()
        response = str(event.get("output_transcript") or "").strip()
        if self.service is None:
            try:
                from desktop_center import DESKTOP_CENTER
                self.service = DESKTOP_CENTER.service
            except Exception:
                self.service = None
        if not heard or self.service is None:
            return
        sequence = str(event.get("sequence") or "")[:32]
        request_id = "gemini-live:%s:%s" % (self._conversation_id[:48], sequence)
        result = {
            "ok": bool(response), "message": response or "Sem resposta.",
            "provider": "gemini_live", "model": str(event.get("model") or "")[:160],
            "response_id": request_id,
        }
        try:
            self.service._record_conversation_turn(
                self._conversation_id, heard, result, source="voice",
                surface="gemini_live", request_id=request_id,
                response_id=request_id)
        except Exception:
            # Transcript persistence is best effort and must not affect audio.
            return

    def get_gemini_live_provider(self) -> Any:
        return self._gemini_live_provider

    def _ensure_gemini_runtime_loop(self) -> asyncio.AbstractEventLoop:
        """Own one persistent asyncio loop for the Gemini duplex session."""
        loop = self._gemini_runtime_loop
        if loop is not None and loop.is_running() and not loop.is_closed():
            return loop
        self._gemini_runtime_ready.clear()

        def runner() -> None:
            runtime_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(runtime_loop)
            self._gemini_runtime_loop = runtime_loop
            self._gemini_runtime_ready.set()
            runtime_loop.run_forever()
            pending = asyncio.all_tasks(runtime_loop)
            for task in pending:
                task.cancel()
            if pending:
                runtime_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            runtime_loop.close()

        self._gemini_runtime_thread = threading.Thread(
            target=runner, name="jarvis-gemini-runtime", daemon=True)
        self._gemini_runtime_thread.start()
        if not self._gemini_runtime_ready.wait(timeout=5):
            raise RuntimeError("gemini_runtime_loop_start_timeout")
        return self._gemini_runtime_loop

    def run_gemini_live(self, coroutine: Any, *, timeout: float = 15.0) -> Any:
        """Run one Gemini operation on the persistent canonical loop."""
        loop = self._ensure_gemini_runtime_loop()
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        return future.result(timeout=max(1.0, float(timeout)))

    def _enqueue_gemini_frame(self, frame: bytes) -> None:
        """Accept one canonical mic frame on the VoiceService event loop."""
        queue = self._gemini_audio_queue
        if queue is None or not self.gemini_live_status().get("connected"):
            return
        self._gemini_audio_metrics["frames_captured"] += 1
        try:
            queue.put_nowait(bytes(frame))
        except asyncio.QueueFull:
            self._gemini_audio_metrics["input_drops"] += 1

    async def _gemini_send_loop(self) -> None:
        queue = self._gemini_audio_queue
        provider = self._gemini_live_provider
        if queue is None or provider is None:
            return
        while True:
            frame = await queue.get()
            try:
                if not self.gemini_live_status().get("connected"):
                    continue
                await provider.send_audio(frame)
                self._gemini_audio_metrics["frames_sent"] += 1
                self._gemini_audio_metrics["bytes_sent"] += len(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A remote 1007/transport failure must be observable and must
                # stop this one sender task.  Letting it escape produces
                # ``Task exception was never retrieved`` and leaves the UI
                # looking connected while the microphone keeps enqueueing
                # frames.  Do not retry here: the session owner decides when
                # a new authorized session may be created.
                detail = ""
                diagnostics = getattr(provider, "diagnostics", None)
                if callable(diagnostics):
                    try:
                        transport = (diagnostics() or {}).get("transport", {})
                        detail = str(transport.get("last_error", ""))[:240]
                    except Exception:
                        detail = ""
                self._last_recovery = {
                    "error": "GEMINI_LIVE_AUDIO_SEND_FAILED",
                    **({"detail": detail} if detail else {}),
                    "at": time.time(),
                }
                self.last_error = "GEMINI_LIVE_AUDIO_SEND_FAILED"
                input_provider = self._audio_input_provider
                if input_provider is not None and getattr(input_provider, "is_running", False):
                    try:
                        input_provider.stop()
                    except Exception:
                        pass
                while True:
                    try:
                        queue.get_nowait()
                        queue.task_done()
                    except asyncio.QueueEmpty:
                        break
                log.warning("Gemini Live audio sender stopped: %s", detail or type(exc).__name__)
                break
            finally:
                queue.task_done()

    async def _gemini_receive_loop(self) -> None:
        provider = self._gemini_live_provider
        if provider is None:
            return
        try:
            while True:
                chunk = await provider.receive_audio()
                if chunk is None:
                    break
                pcm = bytes(chunk)
                if not pcm:
                    continue
                self._gemini_audio_metrics["audio_chunks_received"] += 1
                self._gemini_audio_metrics["bytes_received"] += len(pcm)
                output = self._gemini_output
                if output is None:
                    # Gemini opens the output stream on its first PCM block;
                    # give the USB device a tiny settling window so the
                    # leading syllable is not clipped by PortAudio startup.
                    # Gemini Live delivers PCM in bursty WebSocket chunks.  A
                    # short queue caused the PortAudio callback to alternate
                    # between real audio and silence whenever two bursts
                    # arrived close together, which was heard as stuttering.
                    # Keep this buffering change local to native Gemini Live;
                    # the regular TTS/output providers retain their defaults.
                    output = SoundDeviceAudioOutputProvider(
                        # Live PCM arrives in short websocket bursts.  Keep a
                        # larger bounded reservoir and a short device-settle
                        # prefix so PortAudio does not underflow between two
                        # adjacent model chunks.  This is scoped to Gemini
                        # Live; the regular TTS output contract is unchanged.
                        # Keep roughly 2–3 seconds of short Live PCM blocks
                        # available before the bounded drop policy is reached.
                        # This prevents a bursty WebSocket from dropping the
                        # beginning or middle of a word while preserving a
                        # finite memory bound and cooperative interruption.
                        maxsize=128, startup_silence_ms=120,
                    )
                    output.warm()
                    self._gemini_output = output
                accepted = output.enqueue(PcmAudioChunk(
                    pcm=pcm, sample_rate=24000, channels=1,
                    session_id=self._conversation_id,
                    turn_id=self._current_turn_id,
                    generation=self._gemini_audio_generation,
                ))
                if not accepted:
                    self._gemini_audio_metrics["output_drops"] += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Gemini Live audio receiver stopped: %s", type(exc).__name__)
            # Keep the public failure code stable, but retain the transport's
            # already-sanitized diagnostic so the Desktop can distinguish a
            # normal provider shutdown from a receive/SDK failure.  Do not
            # expose ``str(exc)`` here: arbitrary SDK exceptions can contain
            # URLs, headers, or other sensitive request details.
            detail = ""
            diagnostics = getattr(provider, "diagnostics", None)
            if callable(diagnostics):
                try:
                    detail = str((diagnostics() or {}).get("transport", {}).get("last_error", ""))[:240]
                except Exception:
                    detail = ""
            self._last_recovery = {
                "error": "GEMINI_LIVE_RECEIVE_FAILED",
                **({"detail": detail} if detail else {}),
            }

    async def start_gemini_live_audio(self, *, device: Any = None,
                                      output: Any = None,
                                      provider_factory: Optional[Callable[..., AudioInputProvider]] = None,
                                      capture: bool = True) -> dict[str, Any]:
        """Start the Gemini bridge, optionally without microphone capture."""
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED"}
        if self._gemini_live_provider is None or not self.gemini_live_status().get("connected"):
            return {"ok": False, "error": "GEMINI_LIVE_NOT_CONNECTED"}
        if self._audio_input_provider is not None and self._audio_input_provider.is_running:
            return {"ok": True, "started": False, "already_running": True,
                    "audio": self.gemini_audio_status()}
        if self._gemini_audio_queue is None:
            self._gemini_audio_generation += 1
            self._gemini_audio_queue = asyncio.Queue(maxsize=32)
            self._gemini_output = output
            self._gemini_audio_metrics = {k: 0 for k in self._gemini_audio_metrics}
            self._gemini_audio_sender = asyncio.create_task(self._gemini_send_loop(), name="gemini-live-audio-sender")
            self._gemini_audio_receiver = asyncio.create_task(self._gemini_receive_loop(), name="gemini-live-audio-receiver")
        if not capture:
            return {"ok": True, "started": True, "capture": False,
                    "audio": self.gemini_audio_status()}
        result = await self.start_gemini_live_capture(
            device=device, provider_factory=provider_factory)
        if not result.get("ok"):
            await self.stop_gemini_live_audio()
            return result
        return {"ok": True, "started": True, "capture": True,
                "audio": self.gemini_audio_status()}

    async def start_gemini_live_capture(
        self, *, device: Any = None,
        provider_factory: Optional[Callable[..., AudioInputProvider]] = None,
    ) -> dict[str, Any]:
        """Start only the VoiceService-owned input stream for push-to-talk."""
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED"}
        if self._gemini_live_provider is None or not self.gemini_live_status().get("connected"):
            return {"ok": False, "error": "GEMINI_LIVE_NOT_CONNECTED"}
        if self._gemini_audio_queue is None:
            return {"ok": False, "error": "GEMINI_LIVE_AUDIO_BRIDGE_NOT_STARTED"}
        if self._audio_input_provider is not None and self._audio_input_provider.is_running:
            return {"ok": True, "started": False, "already_running": True,
                    "audio": self.gemini_audio_status()}
        result = await self.start_audio_input(
            device=device, loop=asyncio.get_running_loop(),
            on_frame=self._enqueue_gemini_frame, start_pipeline=False,
            provider_factory=provider_factory,
        )
        return {**result, "capture": bool(result.get("ok")),
                "audio": self.gemini_audio_status()}

    async def stop_gemini_live_capture(self) -> dict[str, Any]:
        """Mute only microphone capture; keep the Gemini output bridge alive."""
        end_error = ""
        input_provider = self._audio_input_provider
        was_running = input_provider is not None and input_provider.is_running
        result = await self.stop_audio_input()
        if was_running:
            # Stop callbacks first, drain frames already accepted by the
            # canonical sender, then mark the Live turn complete.  Sending
            # audio_stream_end before the queue drains can make Gemini see an
            # empty/partial turn and is a common cause of missing replies.
            queue = self._gemini_audio_queue
            if queue is not None:
                try:
                    await asyncio.wait_for(queue.join(), timeout=2.0)
                except asyncio.TimeoutError:
                    end_error = "gemini_live_audio_drain_timeout"
            ender = getattr(self._gemini_live_provider, "end_audio", None)
            if callable(ender):
                try:
                    await ender()
                except Exception as exc:
                    if not end_error:
                        end_error = _safe_voice_detail(exc)
        if end_error:
            return {"ok": False, "error": "GEMINI_LIVE_AUDIO_END_FAILED",
                    "detail": end_error, "stopped": bool(result.get("stopped")),
                    "capture": False, "audio": self.gemini_audio_status()}
        return {"ok": bool(result.get("ok")), "stopped": True,
                "capture": False, "audio": self.gemini_audio_status()}

    async def stop_gemini_live_audio(self) -> dict[str, Any]:
        """Stop capture, sender/receiver tasks and bounded output cooperatively."""
        preview_task = self._gemini_preview_watch_task
        self._gemini_preview_watch_task = None
        if preview_task is not None and not preview_task.done():
            preview_task.cancel()
            try:
                await preview_task
            except asyncio.CancelledError:
                pass
        for task_name in ("_gemini_audio_sender", "_gemini_audio_receiver"):
            task = getattr(self, task_name)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            setattr(self, task_name, None)
        result = await self.stop_audio_input()
        output = self._gemini_output
        if output is not None:
            try:
                output.cancel("gemini_live_stop")
            except Exception:
                pass
        self._gemini_audio_queue = None
        self._gemini_output = None
        # A text preview belongs to this audio bridge. Clear its marker when
        # the bridge stops so a later authorized session cannot inherit a
        # stale GEMINI_PREVIEW_IN_PROGRESS state.
        self._gemini_preview_active = False
        self._gemini_preview_text = ""
        self._gemini_preview_turn_baseline = 0
        return {"ok": bool(result.get("ok")), "stopped": True,
                "audio": self.gemini_audio_status()}

    async def interrupt_gemini_live_audio(self) -> dict[str, Any]:
        output = self._gemini_output
        if output is not None:
            try:
                output.cancel("gemini_live_interrupt")
            except Exception:
                pass
            # ``cancel`` intentionally makes the sink reject future chunks.
            # Drop the cancelled instance so the next Live turn creates a
            # fresh stream instead of silently discarding all of its PCM.
            self._gemini_output = None
        result = await self.interrupt_gemini_live()
        return {**result, "audio": self.gemini_audio_status()}

    async def preview_gemini_live(self, text: str) -> dict[str, Any]:
        """Request a short spoken preview on the already-authorized Live session.

        This method never connects or starts capture.  The Desktop must have
        an active scoped session and audio bridge first; returned PCM is then
        handled by the existing Gemini receive/output loop.
        """
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED"}
        provider = self._gemini_live_provider
        if provider is None or not self.gemini_live_status().get("connected"):
            return {"ok": False, "error": "GEMINI_LIVE_NOT_CONNECTED"}
        if not self.gemini_audio_status().get("bridge_active"):
            return {"ok": False, "error": "GEMINI_LIVE_AUDIO_NOT_STARTED"}
        prompt = str(text or "").strip()[:240]
        if not prompt:
            return {"ok": False, "error": "GEMINI_PREVIEW_TEXT_REQUIRED"}
        if self._gemini_preview_active:
            return {"ok": False, "error": "GEMINI_PREVIEW_IN_PROGRESS"}
        sender = getattr(provider, "send_text", None)
        if sender is None:
            return {"ok": False, "error": "GEMINI_LIVE_TEXT_PREVIEW_UNSUPPORTED"}
        try:
            diagnostics = self.gemini_live_status().get("diagnostics", {})
            provider_diagnostics = diagnostics.get("provider", {}) if isinstance(diagnostics, dict) else {}
            transport_diagnostics = provider_diagnostics.get("transport", {}) if isinstance(provider_diagnostics, dict) else {}
            self._gemini_preview_turn_baseline = int(
                transport_diagnostics.get("turn_complete_events", 0) or 0
            )
            await sender(prompt)
            self._gemini_preview_active = True
            self._gemini_preview_text = prompt
            if self._gemini_preview_watch_task is not None and not self._gemini_preview_watch_task.done():
                self._gemini_preview_watch_task.cancel()
            self._gemini_preview_watch_task = asyncio.create_task(
                self._watch_gemini_preview(), name="gemini-live-preview-watch"
            )
            return {"ok": True, "preview_started": True,
                    "text_length": len(prompt), "voice": self._voice_name,
                    "audio": self.gemini_audio_status()}
        except Exception as exc:
            self._gemini_preview_active = False
            self._gemini_preview_text = ""
            return {"ok": False, "error": "GEMINI_PREVIEW_FAILED",
                    "detail": _safe_voice_detail(exc)}

    async def send_gemini_live_text(self, text: str) -> dict[str, Any]:
        """Send typed text through the already-connected native Live session.

        The existing Gemini audio bridge remains the sole output owner.  This
        path does not create a second session, preview marker, tool call, or
        local TTS fallback.
        """
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED"}
        provider = self._gemini_live_provider
        if provider is None or not self.gemini_live_status().get("connected"):
            return {"ok": False, "error": "GEMINI_LIVE_NOT_CONNECTED"}
        if not self.gemini_audio_status().get("bridge_active"):
            return {"ok": False, "error": "GEMINI_LIVE_AUDIO_NOT_STARTED"}
        prompt = str(text or "").strip()[:2000]
        if not prompt:
            return {"ok": False, "error": "GEMINI_LIVE_TEXT_REQUIRED"}
        sender = getattr(provider, "send_text", None)
        if sender is None:
            return {"ok": False, "error": "GEMINI_LIVE_TEXT_UNSUPPORTED"}
        try:
            await sender(prompt)
            return {"ok": True, "text_sent": True,
                    "text_length": len(prompt), "audio": self.gemini_audio_status()}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_TEXT_FAILED",
                    "detail": _safe_voice_detail(exc)}

    async def _watch_gemini_preview(self) -> None:
        """Release the one-shot preview gate after one completed Live turn."""
        completed_turn = False
        try:
            for _ in range(200):
                await asyncio.sleep(0.1)
                if not self._gemini_preview_active:
                    return
                diagnostics = self.gemini_live_status().get("diagnostics", {})
                provider_diagnostics = diagnostics.get("provider", {}) if isinstance(diagnostics, dict) else {}
                transport = provider_diagnostics.get("transport", {}) if isinstance(provider_diagnostics, dict) else {}
                completed = int(transport.get("turn_complete_events", 0) or 0) if isinstance(transport, dict) else 0
                if completed > self._gemini_preview_turn_baseline:
                    self._gemini_preview_active = False
                    self._gemini_preview_text = ""
                    self._gemini_preview_turn_baseline = completed
                    completed_turn = True
                    return
        except asyncio.CancelledError:
            raise
        finally:
            # A remote turn can finish without a transcript or audio chunk.
            # Never leave the UI permanently locked in GEMINI_PREVIEW_IN_PROGRESS.
            if self._gemini_preview_active and not completed_turn:
                self._gemini_preview_active = False
                self._gemini_preview_text = ""
            if self._gemini_preview_watch_task is asyncio.current_task():
                self._gemini_preview_watch_task = None

    async def stop_gemini_preview(self) -> dict[str, Any]:
        if not self._gemini_preview_active:
            return {"ok": True, "stopped": False, "audio": self.gemini_audio_status()}
        result = await self.interrupt_gemini_live_audio()
        self._gemini_preview_active = False
        self._gemini_preview_text = ""
        return {**result, "stopped": True}

    def gemini_audio_status(self) -> dict[str, Any]:
        provider = self._audio_input_provider
        output = self._gemini_output
        transcription: dict[str, Any] = {}
        live_provider = self._gemini_live_provider
        provider_diagnostics = getattr(live_provider, "diagnostics", None)
        if callable(provider_diagnostics):
            try:
                snapshot = provider_diagnostics() or {}
                transport = snapshot.get("transport", {})
                if not transport and isinstance(snapshot.get("provider"), dict):
                    transport = snapshot["provider"].get("transport", {})
                value = transport.get("transcription", {}) if isinstance(transport, dict) else {}
                if isinstance(value, dict):
                    transcription = dict(value)
            except Exception:
                transcription = {}
        output_diagnostics: dict[str, Any] = {}
        diagnostics = getattr(output, "diagnostics", None)
        if callable(diagnostics):
            try:
                output_diagnostics = dict(diagnostics() or {})
            except Exception:
                output_diagnostics = {"last_error": "output_diagnostics_unavailable"}
        return {
            "active": bool(provider is not None and provider.is_running),
            "capture_active": bool(provider is not None and provider.is_running),
            "bridge_active": bool(
                self._gemini_audio_queue is not None
                and self._gemini_audio_receiver is not None
                and not self._gemini_audio_receiver.done()
            ),
            "generation": self._gemini_audio_generation,
            "queue_size": self._gemini_audio_queue.qsize() if self._gemini_audio_queue else 0,
            "queue_maxsize": self._gemini_audio_queue.maxsize if self._gemini_audio_queue else 32,
            "output_active": bool(self._gemini_output is not None and getattr(self._gemini_output, "is_active", False)),
            "output": output_diagnostics,
            "transcription": transcription,
            "preview_active": bool(self._gemini_preview_active),
            "last_error": dict(self._last_recovery) if self._last_recovery else {},
            "metrics": dict(self._gemini_audio_metrics),
        }

    def gemini_live_system_instruction(self) -> str:
        """Presentation-only instruction; the provider never receives tool authority."""
        profile = get_personality(self._personality_id)
        return (
            "Você é a voz conversacional do Golden Jarvis. Responda em português "
            "brasileiro. A personalidade altera apenas o estilo, nunca permissões, "
            "segurança, confirmações ou análises financeiras. "
            f"Estilo atual: {profile.instruction} "
            "Não execute ferramentas diretamente; pedidos de ação retornam ao "
            "VoiceService e ao SecurityManager canônicos."
        )

    def gemini_live_status(self) -> dict[str, Any]:
        provider = self._gemini_live_provider
        diagnostics = provider.diagnostics() if provider is not None and hasattr(provider, "diagnostics") else {}
        provider_diag = diagnostics.get("provider") if isinstance(diagnostics, dict) else {}
        return {
            "enabled": gemini_live_enabled(),
            "attached": provider is not None,
            "connected": bool(getattr(provider, "connected", False))
            or bool(getattr(getattr(provider, "provider", None), "connected", False))
            or bool(isinstance(diagnostics, dict) and diagnostics.get("started")),
            "requested_mode": self._voice_mode,
            "effective_mode": self.conversation_profile()["effective_mode"],
            "diagnostics": diagnostics,
        }

    async def setup_gemini_live_diagnostic(self, *, timeout_seconds: float = 30.0) -> dict[str, Any]:
        """Run the explicit setup-only handshake; never starts audio tasks."""
        provider = self._gemini_live_provider
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED",
                    "status": self.gemini_live_status()}
        if provider is None:
            return {"ok": False, "error": "GEMINI_LIVE_PROVIDER_NOT_ATTACHED",
                    "status": self.gemini_live_status()}
        runner = getattr(provider, "setup_only", None)
        if not callable(runner):
            return {"ok": False, "error": "GEMINI_LIVE_SETUP_ONLY_UNSUPPORTED",
                    "status": self.gemini_live_status()}
        try:
            result = await runner(timeout_seconds=min(30.0, float(timeout_seconds)))
            return {**dict(result or {}), "status": self.gemini_live_status()}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_SETUP_FAILED",
                    "detail": _safe_voice_detail(exc),
                    "status": self.gemini_live_status()}

    async def connect_gemini_live(self) -> dict[str, Any]:
        """Connect only after explicit flag activation; never called at startup."""
        provider = self._gemini_live_provider
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED", "status": self.gemini_live_status()}
        if provider is None:
            return {"ok": False, "error": "GEMINI_LIVE_PROVIDER_NOT_ATTACHED", "status": self.gemini_live_status()}
        try:
            connector = getattr(provider, "start", None) or getattr(provider, "connect", None)
            if connector is None:
                return {"ok": False, "error": "GEMINI_LIVE_PROVIDER_INVALID", "status": self.gemini_live_status()}
            result = await connector(system_instruction=self.gemini_live_system_instruction())
            self._gemini_voice_change_pending = False
            return {**dict(result or {}), "status": self.gemini_live_status()}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_CONNECT_FAILED", "detail": _safe_voice_detail(exc),
                    "status": self.gemini_live_status()}

    async def disconnect_gemini_live(self) -> dict[str, Any]:
        provider = self._gemini_live_provider
        if provider is None:
            return {"ok": True, "closed": False, "status": self.gemini_live_status()}
        try:
            if self._audio_input_provider is not None and self._audio_input_provider.is_running:
                await self.stop_gemini_live_audio()
            # A Desktop disconnect ends only the current Live session.  Keep
            # the singleton provider reusable so a failed audio start or a
            # subsequent authorized attempt does not become permanently
            # ``gemini_live_provider_closed``.  Final process shutdown still
            # uses the provider's permanent close path.
            reset = getattr(provider, "disconnect", None)
            if callable(reset):
                await reset()
            else:
                await provider.close()
            self._gemini_voice_change_pending = False
            return {"ok": True, "closed": True, "reusable": callable(reset),
                    "status": self.gemini_live_status()}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_CLOSE_FAILED", "detail": _safe_voice_detail(exc),
                    "status": self.gemini_live_status()}

    async def reconnect_gemini_live(self) -> dict[str, Any]:
        """Reconnect an attached Live session only when its flag is explicitly enabled."""
        provider = self._gemini_live_provider
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED", "status": self.gemini_live_status()}
        if provider is None:
            return {"ok": False, "error": "GEMINI_LIVE_PROVIDER_NOT_ATTACHED", "status": self.gemini_live_status()}
        try:
            connector = getattr(provider, "reconnect", None)
            if connector is None:
                return {"ok": False, "error": "GEMINI_LIVE_RECONNECT_UNSUPPORTED",
                        "status": self.gemini_live_status()}
            result = await connector(system_instruction=self.gemini_live_system_instruction())
            self._gemini_voice_change_pending = False
            return {**dict(result or {}), "status": self.gemini_live_status()}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_RECONNECT_FAILED", "detail": _safe_voice_detail(exc),
                    "status": self.gemini_live_status()}

    async def send_gemini_live_audio(self, pcm: bytes) -> dict[str, Any]:
        provider = self._gemini_live_provider
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED"}
        if provider is None or not self.gemini_live_status()["connected"]:
            return {"ok": False, "error": "GEMINI_LIVE_NOT_CONNECTED"}
        try:
            await provider.send_audio(pcm)
            return {"ok": True, "bytes": len(bytes(pcm or b""))}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_SEND_FAILED", "detail": _safe_voice_detail(exc)}

    async def receive_gemini_live_audio(self) -> dict[str, Any]:
        provider = self._gemini_live_provider
        if not gemini_live_enabled():
            return {"ok": False, "error": "GEMINI_LIVE_DISABLED"}
        if provider is None or not self.gemini_live_status()["connected"]:
            return {"ok": False, "error": "GEMINI_LIVE_NOT_CONNECTED"}
        try:
            chunk = await provider.receive_audio()
            if chunk is None:
                return {"ok": True, "audio_complete": True, "pcm": b""}
            return {"ok": True, "audio_complete": False, "pcm": bytes(chunk)}
        except Exception:
            # The canonical attachment is normally a GeminiLiveDuplexSession,
            # so walk its provider diagnostics instead of assuming a direct
            # transport attribute.  Only the transport-owned, redacted error
            # is returned; the SDK exception text may contain request data.
            diagnostics = {}
            provider_diagnostics = getattr(provider, "diagnostics", None)
            if callable(provider_diagnostics):
                try:
                    snapshot = provider_diagnostics() or {}
                    diagnostics = snapshot.get("transport", {})
                    if not diagnostics:
                        nested = snapshot.get("provider", {})
                        diagnostics = nested.get("transport", {}) if isinstance(nested, dict) else {}
                except Exception:
                    diagnostics = {}
            detail = _safe_voice_detail(diagnostics.get("last_error", "")) if isinstance(diagnostics, dict) else ""
            return {"ok": False, "error": "GEMINI_LIVE_RECEIVE_FAILED",
                    **({"detail": detail} if detail else {}), "diagnostics": diagnostics}

    async def interrupt_gemini_live(self) -> dict[str, Any]:
        provider = self._gemini_live_provider
        if provider is None:
            return {"ok": True, "interrupted": False}
        try:
            await provider.interrupt()
            return {"ok": True, "interrupted": True, "status": self.gemini_live_status()}
        except Exception as exc:
            return {"ok": False, "error": "GEMINI_LIVE_INTERRUPT_FAILED", "detail": _safe_voice_detail(exc)}

    def probe_microphone(self, endpoint_id: str = "") -> dict[str, Any]:
        """Probe one selected endpoint with a bounded real capture."""
        endpoints = self._audio_experience.enumerate_microphones()
        endpoint = next((item for item in endpoints if item.stable_id == str(endpoint_id)), None)
        if endpoint is None:
            return {"ok": False, "error": "MICROPHONE_NOT_FOUND",
                    "available": [item.public() for item in endpoints]}
        result = self._audio_experience.probe(endpoint)
        result["endpoint"] = endpoint.public()
        return result

    def observe_microphone(self, endpoint_id: str, kind: str, level: float) -> dict[str, Any]:
        """Record only confirmed numeric speech/noise evidence and thresholds."""
        profile = self._audio_experience.profile_store.load(str(endpoint_id))
        if not profile.observe(kind, level):
            return {"ok": False, "error": "INVALID_CALIBRATION_SAMPLE"}
        self._audio_experience.profile_store.save(profile)
        return {"ok": True, "endpoint_id": profile.endpoint_id,
                "thresholds": profile.thresholds(),
                "sample_counts": {"speech": len(profile.speech), "noise": len(profile.noise)}}

    async def start_audio_input(
        self,
        *,
        device: Any = None,
        loop: Optional[Any] = None,
        provider_factory: Optional[Callable[..., AudioInputProvider]] = None,
        on_frame: Optional[Callable[[bytes], None]] = None,
        start_pipeline: bool = True,
        on_transcription: Optional[Callable[[str], None]] = None,
        on_state_change: Optional[Callable[[str], None]] = None,
        stt_provider: Any = None,
    ) -> dict:
        """Explicitly start one provider and route frames into the VAD pipeline."""
        if self.is_running():
            return {
                "ok": False,
                "error": "VoiceService legacy loop ja esta capturando; pare-o antes do provider.",
            }
        pending_stop = self._realtime_stop_task
        if pending_stop is not None and not pending_stop.done():
            await pending_stop
        self._realtime_stop_task = None
        pipeline = self.get_realtime_voice_pipeline() if start_pipeline else None
        if adaptive_microphone_enabled() and device is None:
            device = self._selected_microphone_id or os.getenv(
                "JARVIS_VOICE_MICROPHONE_ID", "").strip() or None
        active_stt_provider = stt_provider
        active_transcription_callback = on_transcription
        if start_pipeline and active_stt_provider is None and active_transcription_callback is None:
            # The explicit audio path owns the approved local provider lazily;
            # construction validates nothing and does not load or download a model.
            from .stt_faster_whisper import FasterWhisperSTTProvider
            active_stt_provider = FasterWhisperSTTProvider(
                initial_prompt=getattr(self._voice, "initial_prompt", "")
            )
            active_transcription_callback = self._handle_transcript_event
        elif start_pipeline and active_stt_provider is not None and active_transcription_callback is None:
            active_transcription_callback = self._handle_transcript_event
        active_loop = loop
        if active_loop is None:
            try:
                active_loop = asyncio.get_running_loop()
            except RuntimeError:
                active_loop = None

        provider = self._audio_input_provider
        if provider is not None and provider.is_running:
            return {
                "ok": True,
                "started": False,
                "already_running": True,
                "audio_input": provider.diagnostics(),
            }

        if provider is None:
            factory = provider_factory or AudioInputProvider
            provider = factory(
                frame_queue=pipeline.queue if pipeline is not None else AudioFrameQueue(maxsize=32),
                device=device,
                loop=active_loop,
                on_frame=on_frame,
                deliver_to_queue=start_pipeline,
            )
            self._audio_input_provider = provider

        frame_task = getattr(pipeline, "_frame_task", None) if pipeline is not None else None
        if pipeline is not None and (frame_task is None or frame_task.done()):
            self._realtime_cancellation = VoiceCancellation()
            state_callback = lambda value: self._on_realtime_state_change(
                value, on_state_change
            )
            await pipeline.start(
                loop=active_loop,
                on_transcription=active_transcription_callback,
                on_state_change=state_callback,
                stt_provider=active_stt_provider,
                session_id=self._voice_session.session_id,
                cancellation=self._realtime_cancellation,
                turn_id=self._current_turn_id,
            )

        result = provider.start()
        if not result.get("ok"):
            if pipeline is not None:
                await pipeline.stop()
            self._wake_lifecycle.cancel()
            self._voice_session.state = self._state_machine.state
            return {**result, "audio_input": provider.diagnostics()}
        if adaptive_microphone_enabled():
            identity = (provider.diagnostics().get("device_identity") or {}).get("stable_id", "")
            if identity and self._audio_experience.profile_store is not None:
                profile = self._audio_experience.profile_store.load(identity)
                thresholds = profile.thresholds()
                if thresholds.get("confidence", 0) > 0 and thresholds.get("speech_threshold", 0) > 0:
                    if pipeline is not None:
                        pipeline.set_adaptive_rms_threshold(thresholds["speech_threshold"])
        return {**result, "audio_input": provider.diagnostics(),
                "voice_features": voice_feature_snapshot(),
                "realtime": pipeline.diagnostics() if pipeline is not None else {"started": False, "route": "gemini_live"}}

    def recover_audio_input(self) -> dict[str, Any]:
        """Bounded recovery for a disconnected selected endpoint."""
        provider = self._audio_input_provider
        if provider is None:
            return {"ok": False, "error": "AUDIO_INPUT_NOT_STARTED"}
        stopped = provider.stop()
        if not stopped.get("ok"):
            return {"ok": False, "error": stopped.get("error", "AUDIO_INPUT_STOP_FAILED")}
        result = provider.start()
        if not result.get("ok"):
            return {"ok": False, "error": "AUDIO_INPUT_RECOVERY_FAILED",
                    "details": result.get("error", "")}
        return {"ok": True, "recovered": True, "audio_input": provider.diagnostics()}

    async def stop_audio_input(self) -> dict:
        """Stop provider and pipeline cooperatively without touching Core."""
        provider = self._audio_input_provider
        provider_result = (
            provider.stop()
            if provider is not None
            else {"ok": True, "stopped": False, "already_stopped": True}
        )
        pipeline = self._realtime_pipeline
        if pipeline is not None:
            await pipeline.stop()
        self._realtime_cancellation = None
        self._wake_lifecycle.cancel()
        self._voice_session.state = self._state_machine.state
        return {
            "ok": bool(provider_result.get("ok")),
            "provider": provider_result,
            "audio_input": provider.diagnostics() if provider is not None else {},
        }

    async def restart_audio_input(self, **kwargs: Any) -> dict:
        """Restart the same owned provider without creating a second stream."""
        await self.stop_audio_input()
        return await self.start_audio_input(**kwargs)

    async def stop_realtime_voice_pipeline(self) -> None:
        """Stop and release the optional pipeline without touching Core."""
        await self.stop_audio_input()
        pipeline = self._realtime_pipeline
        if pipeline is None:
            return
        await pipeline.unload()
        self._realtime_pipeline = None
        self._wake_lifecycle.cancel()
        self._voice_session.state = self._state_machine.state

    def configure_tts_pipeline(self, provider: Any, output: Any) -> dict[str, Any]:
        """Install one provider-neutral TTS/output pipeline for this service.

        This is an explicit injection seam for local providers and hardware-free
        tests.  It does not create another Core, session, turn manager or
        cancellation owner.
        """
        from .voice_tts import VoiceAudioPipeline

        if self._streaming_tts is not None:
            self._streaming_tts.close()
            self._streaming_tts = None
        if self._tts_pipeline is not None:
            self._tts_pipeline.release()
        pipeline = VoiceAudioPipeline(provider, output)
        try:
            pipeline.warm()
        except Exception:
            pipeline.release()
            raise
        self._tts_pipeline = pipeline
        from .voice_tts import StreamingTTSOrchestrator
        self._streaming_tts = StreamingTTSOrchestrator(pipeline)
        return {
            "ok": True,
            "owner": "VoiceService",
            "provider": type(provider).__name__,
            "output": type(output).__name__,
            "streaming": True,
        }

    def release_tts_pipeline(self) -> dict[str, Any]:
        """Release the optional TTS/output adapters owned by this service."""
        pipeline = self._tts_pipeline
        self._tts_pipeline = None
        streaming = self._streaming_tts
        self._streaming_tts = None
        if streaming is not None:
            streaming.close()
        if pipeline is not None:
            pipeline.release()
            return {"ok": True, "released": True}
        return {"ok": True, "released": False}

    def get_tts_pipeline(self) -> Any:
        """Return the optional provider-neutral pipeline for diagnostics/tests."""
        return self._tts_pipeline

    def get_streaming_tts(self) -> Any:
        """Return the VoiceService-owned bounded streaming TTS coordinator."""
        return self._streaming_tts

    def start_tts_stream(
        self,
        *,
        turn_id: int | None = None,
        generation: int | None = None,
    ) -> dict[str, Any]:
        """Start provider-neutral streaming TTS for the current Core turn."""
        if self._streaming_tts is None:
            return {"ok": False, "error": "tts_pipeline_not_configured"}
        resolved_turn = self._current_turn_id if turn_id is None else int(turn_id)
        if resolved_turn != self._current_turn_id:
            return {"ok": False, "error": "stale_turn"}
        if generation is None:
            self._tts_epoch += 1
            resolved_generation = self._tts_epoch
        else:
            resolved_generation = int(generation)
            if resolved_generation < self._tts_epoch:
                return {"ok": False, "error": "stale_generation"}
            self._tts_epoch = resolved_generation
        self._barge_in_cancel.clear()
        identity = self._streaming_tts.start_stream(
            session_id=self._voice_session.session_id,
            turn_id=resolved_turn,
            generation=resolved_generation,
        )
        return {"ok": True, "identity": identity}

    def feed_tts_stream(
        self,
        text_chunk: str | None,
        *,
        session_id: str | None = None,
        turn_id: int | None = None,
        generation: int | None = None,
        chunk_id: str | None = None,
    ) -> dict[str, Any]:
        """Feed one Core text chunk through the bounded TTS coordinator."""
        if self._streaming_tts is None:
            return {"ok": False, "error": "tts_pipeline_not_configured"}
        submitted = self._streaming_tts.feed_text(
            text_chunk,
            session_id=session_id,
            turn_id=turn_id,
            generation=generation,
            chunk_id=chunk_id,
        )
        return {
            "ok": True,
            "submitted_segments": submitted,
            "diagnostics": self._streaming_tts.diagnostics(),
        }

    def finish_tts_stream(
        self,
        *,
        session_id: str | None = None,
        turn_id: int | None = None,
        generation: int | None = None,
    ) -> dict[str, Any]:
        """Flush and complete the current bounded TTS stream exactly once."""
        if self._streaming_tts is None:
            return {"ok": False, "error": "tts_pipeline_not_configured"}
        result = self._streaming_tts.finish_stream(
            session_id=session_id,
            turn_id=turn_id,
            generation=generation,
        )
        return {"ok": result.ok, **result.__dict__}

    def request_utterance(self, session_id: str = "") -> dict:
        """Arm one capture while preserving wake-word checks otherwise."""
        if not self.is_running():
            return {"ok": False, "error": "VoiceService nao esta rodando."}
        self._desktop_session_id = str(session_id or "").strip()
        self._push_to_talk_requested.set()
        self.state = "LISTENING"
        return {"ok": True, "running": True, "capture_requested": True,
                "session_id": self._desktop_session_id,
                "message": "Microfone pronto para um comando."}

    def _handle_transcript_event(self, event: TranscriptEvent) -> None:
        """Route only accepted final events through the existing Core boundary."""
        if not isinstance(event, TranscriptEvent) or not event.is_final:
            return
        if (
            event.session_id != self._session_id
            or self._voice_session.cancellation.is_cancelled
        ):
            self.last_rejection = {
                "classification": "STALE_EVENT",
                "rejected_reason": "session_invalidated",
                "event_session_id": event.session_id,
                "session_id": self._session_id,
                "at": time.time(),
            }
            self.stats["stale_events"] = self.stats.get("stale_events", 0) + 1
            return
        text = event.text.strip()
        if not text:
            return
        self.last_heard = text
        self.last_activity = time.time()
        if self.service is None:
            return
        if os.getenv("JARVIS_VOICE_SHORT_CONFIRMATIONS", "0").strip().casefold() in {"1", "true", "yes", "on"}:
            decision = classify_confirmation(text)
            pending = getattr(getattr(self.service, "security", None), "pending", {})
            if decision and isinstance(pending, dict) and len(pending) == 1:
                token = next(iter(pending))
                result = (self.service.confirm(token, task_id=self._desktop_session_id or "voice")
                          if decision == "approve" else
                          self.service.deny_confirmation(token, task_id=self._desktop_session_id or "voice"))
                self.last_event = {"id": self.last_event_id + 1,
                                   "kind": "VOICE_CONFIRMATION",
                                   "decision": decision,
                                   "ok": bool(result.get("ok")),
                                   "at": time.time()}
                self.last_event_id += 1
                self.stats["confirmations"] = self.stats.get("confirmations", 0) + 1
                self.last_response = str(result.get("message") or result.get("error") or "")[:240]
                return
            if decision and isinstance(pending, dict) and len(pending) != 1:
                self.last_rejection = {"classification": "AMBIGUOUS_CONFIRMATION",
                                        "rejected_reason": "pending_confirmation_count",
                                        "count": len(pending), "at": time.time()}
                return
        self._handle(
            text,
            timings={
                "utterance_source": "AUDIO_INPUT",
                "session_id": event.session_id,
                "utterance_id": event.utterance_id,
                "stt_provider": event.provider,
            },
            output={"speak": True, "mode": "VOICE"},
        )

    # ═══════════════════════════════════════════════════════════════
    # LOOP PRINCIPAL (thread daemon)
    # ═══════════════════════════════════════════════════════════════

    def _loop(self):
        print('[JARVIS-VOICE] Escuta local ativa. Diga "Jarvis" seguido do comando.')
        while not self.stop_event.is_set():
            try:
                # P1.4C v2: Check if barge-in follow-up needs capture
                if self._barge_in_followup_active:
                    self._stop_barge_in_monitor()
                    self._speaking_event.clear()
                    self.state = "CAPTURING_FOLLOWUP"

                    # Capture follow-up utterance (pre-roll + live mic)
                    record = self._capture_followup_after_barge_in()
                    self._barge_in_followup_active = False

                    if not record.get("ok"):
                        self.state = "WAITING_WAKE"
                        continue

                    audio = record.get("audio") or b""
                    if not record.get("speech_detected") or len(audio) < 2000:
                        self._utterance_source = ""
                        self.state = "WAITING_WAKE"
                        continue

                    # STT the follow-up utterance
                    self.state = "TRANSCRIBING"
                    stt = self._voice.transcribe_audio_bytes(audio, record.get("samplerate", 16000))
                    text = str(stt.get("text") or "").strip() if stt.get("ok") else ""

                    # Clean up: remove Jarvis wake word if present (user may say it during interruption)
                    if text.lower().startswith("jarvis"):
                        text = text[6:].strip().lstrip(",.!?;:").strip()

                    if len(text) < 3:
                        self._utterance_source = ""
                        self.state = "WAITING_WAKE"
                        continue

                    self.last_heard = text
                    self.last_activity = time.time()
                    self.stats["heard"] += 1

                    # Barge-in follow-up: bypass wake word, treat as continue_conversation
                    self._utterance_source = "BARGE_IN"
                    command = text
                    output = get_output_mode_manager().parse(command, source="voice")
                    command = output["content"] or command

                    # Execute as follow-up (preserves conversation context)
                    # The old response was already invalidated; this new
                    # input turn must not inherit its cancellation marker.
                    self._barge_in_cancel.clear()
                    self._handle(command, decision=None, output=output, timings={
                        "utterance_id": record.get("utterance_id", ""),
                        "capture_ms": 0, "stt_ms": 0, "normalize_ms": 0,
                        "barge_in_followup": True,
                        "utterance_source": "BARGE_IN",
                        "preroll_frames": record.get("preroll_frames", 0),
                        "captured_duration_ms": record.get("duration_ms", 0),
                    })
                    self._utterance_source = ""
                    continue

                remaining_guard = self._ignore_input_until - time.time()
                if remaining_guard > 0:
                    self.stop_event.wait(min(remaining_guard, .5))
                    continue
                self.state = ("LISTENING" if self._push_to_talk_requested.is_set()
                              else "WAITING_WAKE")
                if not self._push_to_talk_requested.is_set() and not self._wake_lifecycle.armed:
                    self._wake_lifecycle.arm()
                if self._speaking_event.is_set():
                    self.stop_event.wait(.1)
                    continue
                t0 = time.time()
                capture_epoch = self._tts_epoch
                record = self._voice.record_until_silence(
                    max_seconds=LISTEN_WINDOW_SECONDS,
                    level_callback=self._on_level,
                    state_callback=self._set_capture_state,
                    stop_event=self.stop_event)
                t_capture = int((time.time() - t0) * 1000)
                if self.stop_event.is_set():
                    break
                if capture_epoch != self._tts_epoch:
                    self._reject(record.get("utterance_id"), "IGNORED_NOISE", "tts_self_audio")
                    continue
                if not record.get("ok"):
                    self.last_error = str(record.get("error") or "falha de microfone")
                    self.stats["errors"] += 1
                    self.state = "ERROR"
                    self.stop_event.wait(2.0)
                    continue

                audio = record.get("audio") or b""
                if not record.get("speech_detected") or len(audio) < 2000:
                    continue  # silencio — nao gasta Whisper

                captured_at = float(record.get("captured_at") or time.time())
                max_age = float(os.getenv("JARVIS_AUDIO_MAX_AGE_SECONDS", "1.5"))
                if self._capture_is_stale(captured_at, max_age):
                    self._reject(record.get("utterance_id"), "IGNORED_NOISE", "stale_backlog")
                    continue
                self._latest_capture_at = captured_at

                t_listen = time.time()
                self.state = "TRANSCRIBING"
                stt = self._voice.transcribe_audio_bytes(audio, record.get("samplerate", 16000))
                t_stt = time.time()
                text = str(stt.get("text") or "").strip() if stt.get("ok") else ""
                utterance_id = str(record.get("utterance_id") or uuid.uuid4().hex)
                if not stt.get("accepted"):
                    self._handle_rejected_speech(stt, text, utterance_id)
                    continue
                t_normalize = time.perf_counter()
                text = " ".join(text.split()).strip()
                normalize_ms = int((time.perf_counter() - t_normalize) * 1000)
                if len(text) < 3:
                    self._reject(utterance_id, "LOW_CONFIDENCE", "too_short", stt)
                    continue

                self.last_heard = text
                self.last_activity = time.time()
                self.stats["heard"] += 1

                push_to_talk = self._push_to_talk_requested.is_set()
                desktop_session_id = ""
                if push_to_talk:
                    self._push_to_talk_requested.clear()
                    desktop_session_id = self._desktop_session_id
                    self._desktop_session_id = ""
                    command = text
                    self._utterance_source = "PUSH_TO_TALK"
                else:
                    action = self._voice.process_voice_command(text)
                    wake_activation = None
                    if action.get("wake_word"):
                        wake_result = self.activate_wake(utterance_id)
                        if not wake_result.get("ok"):
                            self._reject(utterance_id, "STALE_WAKE", "wake_lifecycle")
                            continue
                        wake_activation = utterance_id
                    if action.get("action") == "listen_more":
                        # Wake word sozinha: acorda, mas nao gera comando.
                        self.state = "WAKE_DETECTED"
                        self.stop_event.wait(1.2)
                        self.complete_wake(wake_activation or utterance_id)
                        continue
                    if action.get("action") == "ignore":
                        continue
                    command = action.get("command") or text
                output = get_output_mode_manager().parse(command, source="voice")
                command = output["content"] or command
                preview = self.service.orchestrator.decide(
                    command, source="voice", voice_capture=True)
                if not self._voice.accepted_for_risk(stt, preview.requires_confirmation):
                    self._reject(utterance_id, "LOW_CONFIDENCE", "risk_confidence", stt)
                    continue
                self._handle(command, decision=preview, output=output, timings={
                    "utterance_id": utterance_id, "capture_ms": record.get("capture_ms", t_capture),
                    "session_id": desktop_session_id,
                    "utterance_source": self._utterance_source or "NORMAL",
                    "speech_start_ms": record.get("speech_start_ms", 0),
                    "speech_ms": record.get("speech_ms", 0),
                    "silence_wait_ms": record.get("silence_wait_ms", 0),
                    "speech_end_detect_ms": record.get("speech_end_detect_ms", 0),
                    "pre_roll_ms": record.get("pre_roll_ms", 0),
                    "end_silence_target_ms": record.get("end_silence_target_ms", 0),
                    "peak": record.get("peak", 0),
                    "clipped_samples": record.get("clipped_samples", 0),
                    "near_clip_samples": record.get("near_clip_samples", 0),
                    "clipping": record.get("clipping", False),
                    "stt_ms": int((t_stt - t_listen) * 1000), "normalize_ms": normalize_ms,
                    "stt_complete_at": t_stt,
                    "raw_transcript": str(stt.get("text") or text),
                    "stt_confidence": stt.get("stt_confidence", 0),
                    "avg_logprob": stt.get("avg_logprob", 0),
                    "no_speech_prob": stt.get("no_speech_prob", 0),
                    "compression_ratio": stt.get("compression_ratio", 0),
                    "noise_floor": record.get("noise_floor", 0),
                    "speech_threshold": record.get("speech_threshold", 0),
                    "stt_confidence": stt.get("stt_confidence", 0),
                    "model": stt.get("model", ""), "compute_type": stt.get("compute_type", ""),
                    "beam_size": stt.get("beam_size", 0), "rejected_reason": ""})
                if wake_activation:
                    self.complete_wake(wake_activation)
            except Exception as exc:  # nunca derrubar o daemon
                self.last_error = str(exc)
                self.stats["errors"] += 1
                self.state = "ERROR"
                self.stop_event.wait(2.0)
        self.state = "OFF"

    def _on_level(self, rms: float):
        """Telemetria real do microfone (sem audio, só nível)."""
        try:
            self.last_level = int(rms)
            self.last_level_at = time.time()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # P1.4C: BARGE-IN MONITORING (thread separada durante TTS)
    #
    # Methodology (fixed after real test):
    # - NOT pure RMS (was triggering on TTS leakage)
    # - Uses Silero VAD for speech detection
    # - Adaptive threshold from calibration (noise_floor + margin)
    # - Persistence: require N consecutive VAD-positive frames
    # - Grace period after TTS start
    # - Tracks timestamps for proper latency metrics
    # ═══════════════════════════════════════════════════════════════

    def _start_barge_in_monitor(self):
        """Start VAD-based monitoring thread during TTS playback."""
        if self._barge_in_monitor_thread and self._barge_in_monitor_thread.is_alive():
            return  # already running
        self._barge_in_monitor_stop.clear()
        self._barge_in_monitor_thread = threading.Thread(
            target=self._barge_in_monitor_loop,
            name="jarvis-barge-in-monitor",
            daemon=True,
        )
        self._barge_in_monitor_thread.start()

    def _stop_barge_in_monitor(self):
        """Stop monitoring thread."""
        self._barge_in_monitor_stop.set()
        if self._barge_in_monitor_thread:
            self._barge_in_monitor_thread.join(timeout=1.0)
            self._barge_in_monitor_thread = None

    def _barge_in_monitor_loop(self):
        """Monitor mic during TTS playback using Silero VAD + adaptive threshold.

        Feeds pre-roll circular buffer for audio handoff.
        On detection: stores pre-roll + starts user audio capture.

        Detection requires ALL:
        1. Grace period elapsed (0.2s after TTS start)
        2. Silero VAD confirms speech (not just RMS)
        3. RMS exceeds adaptive threshold (noise_floor + margin)
        4. Persistence: N consecutive positive frames
        """
        try:
            import sounddevice as sd

            samplerate = 16000
            blocksize = 1024  # ~64ms per block at 16kHz
            grace_seconds = float(os.getenv("JARVIS_BARGE_IN_GRACE_SECONDS", "0.2"))
            persistence_blocks = BARGE_IN_PERSISTENCE_BLOCKS

            # Adaptive threshold
            noise_floor = float(os.getenv("JARVIS_NOISE_FLOOR", "0"))
            tts_floor = float(os.getenv("JARVIS_TTS_FLOOR", "0"))
            margin = BARGE_IN_ADAPTIVE_MARGIN
            min_absolute = BARGE_IN_MIN_ABSOLUTE

            if tts_floor > 0:
                threshold = max(min_absolute, noise_floor + margin, tts_floor + margin)
            elif noise_floor > 0:
                threshold = max(min_absolute, noise_floor + margin)
            else:
                threshold = float(BARGE_IN_RMS_THRESHOLD)

            log.info(
                "[BARGE-IN] Monitor started: threshold=%.0f, persistence=%d, grace=%.1fs",
                threshold, persistence_blocks, grace_seconds,
            )

            # Try to load Silero VAD
            vad_available = False
            vad_session = None
            try:
                from jarvis_core.realtime_voice.vad import _find_silero_onnx
                onnx_path = _find_silero_onnx()
                if onnx_path:
                    import onnxruntime as ort
                    opts = ort.SessionOptions()
                    opts.intra_op_num_threads = 1
                    opts.inter_op_num_threads = 1
                    opts.enable_cpu_mem_arena = False
                    opts.log_severity_level = 4
                    vad_session = ort.InferenceSession(
                        str(onnx_path), providers=["CPUExecutionProvider"], sess_options=opts,
                    )
                    vad_available = True
                    log.info("[BARGE-IN] Silero VAD loaded")
            except Exception as e:
                log.info("[BARGE-IN] Silero VAD not available, RMS-only: %s", e)

            # VAD state
            vad_h = np.zeros((1, 1, 128), dtype=np.float32)
            vad_c = np.zeros((1, 1, 128), dtype=np.float32)
            vad_context = np.zeros((1, 64), dtype=np.float32)
            VAD_THRESHOLD = 0.5
            VAD_WINDOW_SAMPLES = 512

            speech_count = 0
            tts_start_time = time.monotonic()
            frames_processed = 0

            with sd.InputStream(
                samplerate=samplerate, channels=1, dtype="int16", blocksize=blocksize,
            ) as stream:
                while not self._barge_in_monitor_stop.is_set():
                    try:
                        data, _ = stream.read(blocksize)
                        rms = float(np.abs(data).mean())
                        frames_processed += 1

                        # Feed pre-roll circular buffer (always, even before grace)
                        self._barge_in_pre_roll.append(data.copy())
                        if len(self._barge_in_pre_roll) > self._barge_in_preroll_max_blocks:
                            self._barge_in_pre_roll.pop(0)

                        # Check grace period
                        elapsed = time.monotonic() - tts_start_time
                        if elapsed < grace_seconds:
                            continue

                        # VAD check (if available)
                        vad_speech = True
                        if vad_available and vad_session is not None:
                            try:
                                audio_float = data.astype(np.float32) / 32768.0
                                audio_chunk = audio_float[:VAD_WINDOW_SAMPLES]
                                full_input = np.concatenate([vad_context.flatten(), audio_chunk])[:576]
                                full_input = full_input.reshape(1, -1)
                                ort_inputs = {"input": full_input, "h": vad_h, "c": vad_c}
                                ort_outputs = vad_session.run(None, ort_inputs)
                                prob = float(ort_outputs[0].flatten()[0])
                                vad_h = ort_outputs[1]
                                vad_c = ort_outputs[2]
                                vad_context = audio_chunk[-64:].reshape(1, -1).astype(np.float32)
                                vad_speech = prob >= VAD_THRESHOLD
                            except Exception:
                                vad_speech = True

                        # Combined check: VAD positive AND RMS above threshold
                        if vad_speech and rms >= threshold:
                            speech_count += 1
                            if speech_count >= persistence_blocks:
                                # Barge-in confirmed
                                detection_time = time.monotonic()
                                self._barge_in_detected_at = detection_time
                                self._utterance_source = "BARGE_IN"
                                self._barge_in_followup_active = True

                                # PRESERVE pre-roll (already in self._barge_in_pre_roll)
                                # Start fresh user audio capture after detection point
                                self._barge_in_user_audio = []

                                coordination = self.accept_barge_in(
                                    source="user_speech",
                                    audio_level=rms,
                                    prepare_followup=True,
                                )
                                if not coordination.get("accepted"):
                                    speech_count = 0
                                    continue
                                log.info(
                                    "[BARGE-IN] DETECTED: rms=%.0f threshold=%.0f "
                                    "persistence=%d/%d elapsed=%.1fs preroll=%d",
                                    rms, threshold, speech_count, persistence_blocks,
                                    detection_time - tts_start_time,
                                    len(self._barge_in_pre_roll),
                                )
                                break
                        else:
                            speech_count = max(0, speech_count - 2)

                    except Exception:
                        break

            log.info("[BARGE-IN] Monitor ended: frames=%d", frames_processed)

        except Exception as e:
            log.warning("[BARGE-IN] Monitor failed: %s", e)

    def _capture_followup_after_barge_in(self):
        """Capture user utterance after barge-in, using pre-roll + live mic.

        Called from _loop() when _barge_in_followup_active is True.
        Combines pre-roll frames (from before detection) with live frames
        into a single utterance buffer. Uses endpointing to detect end of speech.
        """
        try:
            import sounddevice as sd

            samplerate = 16000
            blocksize = 1024
            silence_seconds = 1.5
            max_seconds = 10
            speech_threshold = float(os.getenv("JARVIS_SPEECH_THRESHOLD", "300"))

            # Start with pre-roll frames (from before detection)
            utterance_frames = list(self._barge_in_pre_roll)
            self._barge_in_pre_roll.clear()

            # Add any user audio already captured during detection
            utterance_frames.extend(self._barge_in_user_audio)
            self._barge_in_user_audio.clear()

            # Now capture live audio from mic
            speech_started = len(utterance_frames) > 0
            last_speech_at = time.time()
            start = time.time()

            with sd.InputStream(
                samplerate=samplerate, channels=1, dtype="int16", blocksize=blocksize,
            ) as stream:
                while (time.time() - start) < max_seconds:
                    data, _ = stream.read(blocksize)
                    rms = float(np.abs(data).mean())

                    if rms >= speech_threshold:
                        speech_started = True
                        last_speech_at = time.time()
                        utterance_frames.append(data.copy())
                    elif speech_started:
                        utterance_frames.append(data.copy())  # capture silence for endpointing
                        if time.time() - last_speech_at >= silence_seconds:
                            break

            # Build final audio
            if utterance_frames:
                audio = np.concatenate(utterance_frames)
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(samplerate)
                    wf.writeframes(audio.tobytes())
                audio_bytes = buf.getvalue()

                duration_ms = len(audio) / samplerate * 1000
                log.info("[BARGE-IN] Follow-up captured: %d frames, %.0fms", len(utterance_frames), duration_ms)

                return {
                    "ok": True,
                    "audio": audio_bytes,
                    "samplerate": samplerate,
                    "duration_ms": duration_ms,
                    "utterance_id": uuid.uuid4().hex,
                    "speech_detected": speech_started,
                    "preroll_frames": len(self._barge_in_pre_roll),
                }

            return {"ok": False, "error": "no_audio"}

        except Exception as e:
            log.warning("[BARGE-IN] Follow-up capture failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _set_capture_state(self, state):
        self.state = str(state)

    def _capture_is_stale(self, captured_at, max_age=None):
        max_age = (float(os.getenv("JARVIS_AUDIO_MAX_AGE_SECONDS", "1.5"))
                   if max_age is None else float(max_age))
        return captured_at <= self._latest_capture_at or time.time() - captured_at > max_age

    def _reject(self, utterance_id, classification, reason, stt=None):
        self.last_rejection = {"utterance_id": str(utterance_id or ""),
            "classification": str(classification), "rejected_reason": str(reason),
            "stt_confidence": (stt or {}).get("stt_confidence", 0), "at": time.time()}
        self.stats["rejected"] = self.stats.get("rejected", 0) + 1
        self.state = "WAITING_WAKE"

    def _handle_rejected_speech(self, stt, text, utterance_id) -> bool:
        """Rejeição com feedback: fala pouco nítida pede repetição.

        Retorna True quando falou o pedido de repetição. Ruído puro
        (IGNORED_NOISE) continua silencioso por design.
        """
        stt = stt or {}
        classification = stt.get("classification", "LOW_CONFIDENCE")
        reason = stt.get("rejected_reason", "stt_rejected")
        self._reject(utterance_id, classification, reason, stt)
        if classification == "LOW_CONFIDENCE" and str(text or "").strip():
            self._voice.touch_interaction()
            self.state = "SPEAKING"
            self._speak("Não entendi bem. Pode repetir?")
            self.last_rejection["responded"] = True
            return True
        return False

    def accepts_core_output(self, *, turn_id: int, generation: int) -> bool:
        """Return whether a Core completion still belongs to the active turn."""
        try:
            return (
                int(turn_id) == self._current_turn_id
                and int(generation) == self._tts_epoch
                and not self._turn_manager.is_stale(int(turn_id))
                and not self._turn_manager.is_cancelled(int(turn_id))
            )
        except (TypeError, ValueError):
            return False

    # ═══════════════════════════════════════════════════════════════
    # EXECUCAO DO COMANDO (mesmo fluxo de /api/jarvis/chat)
    # ═══════════════════════════════════════════════════════════════

    def _get_brain(self):
        """Import tardio — permite mock em testes e evita ciclo de import."""
        from .brain import get_brain
        return get_brain(self.service.registry)

    def _should_use_streaming(self) -> bool:
        """Check if streaming voice is enabled and available."""
        try:
            from .streaming import is_streaming_enabled
            return is_streaming_enabled()
        except ImportError:
            return False

    def _handle_streaming(self, command: str, timings: dict, decision=None, output=None) -> dict:
        """Streaming path: LLM tokens → sentence chunker → TTS → playback.

        Uses TurnManager for turn lifecycle and cancellation.
        Supports barge-in via threading.Event (cross-thread safe).

        Returns:
            {"handled": True, "metrics": {...}} if streaming handled (prose response)
            {"handled": False, "reason": "tool_call", "tool_call_text": "..."} if tool call detected
            {"handled": False, "reason": "error"} if streaming failed
        """
        try:
            import asyncio
            from .streaming.orchestrator import StreamingOrchestrator
            from .brain import get_brain

            brain = get_brain()
            if not brain:
                return {"handled": False, "reason": "no_brain"}
            self._apply_personality_to_brain(brain)

            # P1.4C: Append user turn to conversation context FIRST
            # (before build_messages, so it appears in context for the LLM)
            self._conversation_messages.append({"role": "user", "content": command})

            # P1.4C: Create new turn (cancels previous)
            self._current_turn_id = self._turn_manager.new_turn()
            turn_id = self._current_turn_id
            self._barge_in_cancel.clear()

            # Get cancel event for this turn
            cancel_event = self._turn_manager.get_cancel_event(turn_id)

            # Determine provider from orchestrator
            provider = "groq"
            model = "qwen/qwen3.8-27b"
            if hasattr(brain, "orchestrator") and brain.orchestrator:
                providers = getattr(brain.orchestrator, "models", None)
                if providers and hasattr(providers, "providers"):
                    provider_list = providers.providers
                    if provider_list:
                        provider = getattr(provider_list[0], "name", "groq")
                        model = getattr(provider_list[0], "default_model", model)

            # Assemble messages using Brain's build_messages — single source of truth.
            # Pass conversation_history so previous turns appear in context.
            from .orchestrator.models import ModelProfile as _MP
            messages = brain.build_messages(
                command, "", source="voice", voice_capture=True,
                conversation_history=self._conversation_messages[:-1],
                profile=_MP.VOICE_FAST,
            )

            # P1.4C: Start barge-in monitoring if enabled
            if is_barge_in_enabled():
                self._start_barge_in_monitor()

            # Run streaming pipeline with TurnManager
            orchestrator = StreamingOrchestrator()
            result = asyncio.run(orchestrator.run(
                messages=messages,
                provider=provider,
                model=model,
                turn_id=turn_id,
                turn_manager=self._turn_manager,
            ))

            # P1.4C: Stop barge-in monitoring
            self._stop_barge_in_monitor()

            # A provider may finish after cancellation.  Do not let that old
            # response fall through to Core/TTS after a newer turn exists.
            if self._turn_manager.is_stale(turn_id):
                return {
                    "handled": True,
                    "cancelled": True,
                    "metrics": result.get("metrics"),
                }

            # TOOL CALL SAFETY: If tool call detected, return to legacy path
            if not result.get("ok") and result.get("error") == "tool_call_detected":
                return {
                    "handled": False,
                    "reason": "tool_call",
                    "tool_call_text": result.get("tool_call_text", ""),
                    "full_response": result.get("full_response", ""),
                }

            if not result.get("ok"):
                # P1.4C: If cancelled, don't clear conversation context
                if result.get("error") == "cancelled":
                    return {"handled": True, "metrics": result.get("metrics")}
                return {"handled": False, "reason": "error"}

            # P1.4C: Store assistant response in conversation context
            response_text = result.get("response", "")
            if response_text:
                self._conversation_messages.append({"role": "assistant", "content": response_text})
                # Keep conversation manageable (last 20 turns)
                if len(self._conversation_messages) > 40:
                    self._conversation_messages = self._conversation_messages[-40:]

            # Update timings with streaming metrics
            metrics = result.get("metrics")
            if metrics:
                timings["streaming_provider_ttft_ms"] = int(metrics.provider_ttft_ms)
                timings["streaming_first_sentence_ms"] = int(metrics.first_sentence_ready_ms)
                timings["streaming_tts_first_audio_ms"] = int(metrics.tts_first_audio_ms)
                timings["streaming_total_ms"] = int(metrics.total_response_ms)
                timings["streaming_chunks_emitted"] = metrics.chunks_emitted
                timings["streaming_chunks_played"] = metrics.chunks_played

            return {"handled": True, "metrics": metrics}

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Streaming failed, falling back: %s", e)
            return {"handled": False, "reason": "error"}

    def _handle_desktop_command(self, command: str, timings: dict, output: dict) -> None:
        """Run a Desktop utterance once through the canonical Gateway service session."""
        session_id = str(timings.get("session_id") or self._session_id)
        utterance_id = str(timings.get("utterance_id") or uuid.uuid4().hex)
        response_id = uuid.uuid4().hex
        started = time.time()
        error = ""
        try:
            result = dict(self.service.execute_command(command, task_id=session_id) or {})
            response = str(result.get("message") or result.get("error") or "Pronto.")
            if not result.get("ok", False):
                error = str(result.get("error") or response)[:300]
                self.stats["errors"] += 1
            else:
                self.stats["commands"] += 1
        except Exception as exc:
            result = {}
            response = "Erro ao executar: %s" % exc
            error = str(exc)[:300]
            self.stats["errors"] += 1

        spoken_response = to_spoken_text(response)
        timings["execution_ms"] = int((time.time() - started) * 1000)
        timings["dispatch_count"] = 1
        timings["jarvis_service_call_count"] = 1
        trace = {
            "PROCESS_ID": os.getpid(),
            "SOURCE_MODULE": "jarvis_core.voice_service",
            "SESSION_ID": session_id,
            "VOICE_UTTERANCE_ID": utterance_id,
            "RESPONSE_ID": response_id,
            "TTS_OWNER": "VoiceService",
            "DISPATCH_COUNT": 1,
            "JARVIS_SERVICE_CALL_COUNT": 1,
            "TOOL_EXECUTION_COUNT": len(result.get("executions") or []) or int(bool(result.get("tool"))),
            "FINAL_RESPONSE_COUNT": 1,
            "TTS_COUNT": int(bool(output.get("speak", True))),
        }
        self.last_response = response
        self.last_error = error
        self.last_event_id += 1
        self.last_event = {
            "id": self.last_event_id, "heard": command,
            "utterance_id": utterance_id, "session_id": session_id,
            "response_id": response_id, "process_id": os.getpid(),
            "source_module": trace["SOURCE_MODULE"], "tts_owner": trace["TTS_OWNER"],
            "route": str(result.get("route") or "canonical_service"),
            "skill": str(result.get("skill") or ""),
            "tool": str(result.get("tool") or ""),
            "tool_provider": str(result.get("provider") or ""),
            "canonical_response": response, "spoken_response": spoken_response,
            "output_mode": output.get("mode", "AUTO"), "response": response,
            "error": error, "timings": timings, "trace": trace, "at": time.time(),
        }
        print("[JARVIS-VOICE-TRACE] " + " ".join(
            "%s=%s" % (key, value) for key, value in trace.items()), flush=True)
        self._voice.touch_interaction()
        self.state = "SPEAKING" if output.get("speak", True) else "WAITING_WAKE"
        if output.get("speak", True):
            self._speak(spoken_response)
        self._ignore_input_until = time.time() + max(.2, float(
            os.getenv("JARVIS_TTS_INPUT_GUARD_SECONDS", ".6")))

    def _handle(self, command: str, timings=None, decision=None, output=None):
        base_timings = {"capture_ms": 0, "stt_ms": 0}
        base_timings.update(dict(timings or {}))
        timings = base_timings
        if "turn_id" in timings and "generation" in timings:
            if not self.accepts_core_output(
                turn_id=timings["turn_id"], generation=timings["generation"]
            ):
                self.last_rejection = {
                    "classification": "STALE_OUTPUT",
                    "rejected_reason": "obsolete_turn_generation",
                    "turn_id": timings["turn_id"],
                    "generation": timings["generation"],
                    "at": time.time(),
                }
                self.stats["stale_outputs"] = self.stats.get("stale_outputs", 0) + 1
                return
        try:
            from .readiness import get_readiness
            warming = get_readiness().is_warming()
        except Exception:
            warming = False
        if warming:
            # Boot ainda em WARMING: não perder silenciosamente nem executar
            # pela metade — avisar e aguardar READY.
            response = "Estou iniciando, tente novamente em alguns segundos."
            output = output or get_output_mode_manager().parse(
                str(command or ""), source="voice")
            self.last_response = response
            self.last_event_id += 1
            self.last_event = {"id": self.last_event_id, "heard": command,
                               "utterance_id": timings.get("utterance_id", ""),
                               "route": "WARMING", "skill": "", "confidence": 0.0,
                               "tool": "", "tool_provider": "",
                               "ack": {"emitted": False, "message": "", "reason": "warming"},
                               "canonical_response": response,
                               "spoken_response": to_spoken_text(response),
                               "output_mode": output.get("mode", "AUTO"),
                               "response": response, "error": "",
                               "timings": {**timings, "warming": True}, "at": time.time()}
            self.stats["warming_deferred"] = self.stats.get("warming_deferred", 0) + 1
            self.state = "SPEAKING" if output.get("speak", True) else "WAITING_WAKE"
            if output.get("speak", True):
                self._speak(self.last_event["spoken_response"])
            else:
                self.state = "WAITING_WAKE"
            return
        self.state = "PROCESSING"

        if (timings.get("utterance_source") == "PUSH_TO_TALK" and
                timings.get("session_id")):
            output = output or get_output_mode_manager().parse(command, source="voice")
            self._handle_desktop_command(command, timings, output)
            return

        # Streaming path: LLM → sentence chunker → TTS → playback
        streaming_result = None
        if self._should_use_streaming() and output and output.get("speak", True):
            streaming_result = self._handle_streaming(command, timings, decision, output)
            if streaming_result.get("handled"):
                # Streaming succeeded for prose — update event and return
                self.last_event_id += 1
                self.last_event = {"id": self.last_event_id, "heard": command,
                                   "utterance_id": timings.get("utterance_id", ""),
                                   "route": "streaming", "skill": "", "confidence": 1.0,
                                   "tool": "", "tool_provider": "",
                                   "ack": {"emitted": False, "message": "", "reason": "streaming"},
                                   "canonical_response": self.last_response,
                                   "spoken_response": to_spoken_text(self.last_response),
                                   "output_mode": "VOICE",
                                   "response": self.last_response, "error": "",
                                   "timings": timings, "at": time.time()}
                self._voice.touch_interaction()
                self._ignore_input_until = time.time() + max(.2, float(
                    os.getenv("JARVIS_TTS_INPUT_GUARD_SECONDS", ".6")))
                return
            # If tool call detected, fall through to legacy path
            # The streaming result contains tool_call_text which we'll use

        t_route = time.time()
        t_exec = t_route
        response = ""
        route = skill = ""
        confidence = 0.0
        tool = tool_provider = ""
        llm_latency = 0
        error = ""
        core_failed = False
        ack = {"emitted": False, "message": "", "reason": "instant"}
        try:
            from .response_policy import ack_for_decision
            preview = decision or self.service.orchestrator.decide(
                command, source="voice", voice_capture=True)
            timings["routing_ms"] = int((time.time() - t_route) * 1000)
            ack_started = time.perf_counter()
            ack = ack_for_decision(preview, self.service.registry)
            if ack["emitted"]:
                self._speak(ack["message"])
                timings["time_to_ack_ms"] = int((time.perf_counter() - ack_started) * 1000)
            brain = self._get_brain()
            self._apply_personality_to_brain(brain)
            response_started = time.time()
            result = brain.interpret(command, source="voice", voice_capture=True)
            timings["response_ready_ms"] = int((time.time() - response_started) * 1000)
            decision = getattr(brain.orchestrator, "last_decision", None)
            if decision is not None:
                route = str(getattr(decision.route, "value", decision.route))
                skill = str(decision.preferred_skill or "")
                try:
                    confidence = float(decision.confidence)
                except (TypeError, ValueError):
                    confidence = 0.0
            llm = dict(getattr(brain, "last_llm", {}) or {})
            tool_provider = str(llm.get("provider") or "")
            try:
                llm_latency = int(llm.get("latency_ms") or 0)
            except (TypeError, ValueError):
                llm_latency = 0
            timings.update({"profile": llm.get("profile", ""),
                "provider_requested": llm.get("provider_requested", ""),
                "provider_actual": llm.get("provider", ""),
                "model_requested": llm.get("model_requested", ""),
                "model_actual": llm.get("model", ""),
                "provider_wait_ms": llm.get("provider_wait_ms", 0),
                "time_to_first_token_ms": llm.get("time_to_first_token_ms", 0),
                "generation_ms": llm.get("generation_ms", 0),
                "fallback": bool(llm.get("fallback", False)),
                "provider_attempts": llm.get("attempts", [])})
            t_exec = time.time()
            if not result.get("ok"):
                response = str(result.get("error") or "Nao consegui processar.")
                core_failed = True
            else:
                plan = result.get("plan", {})
                if set(plan) == {"response"}:
                    # Resposta textual final (sem ferramenta): so falar.
                    response = str(plan["response"])
                    self.stats["commands"] += 1
                else:
                    tool = str(plan.get("tool", ""))
                    exec_result = self.service.execute_tool(
                        plan.get("tool", ""), plan.get("args", {}), command
                    )
                    if not tool_provider:
                        tool_provider = str(exec_result.get("provider") or "")
                    response = str(exec_result.get("message")
                                   or exec_result.get("error")
                                   or "Pronto.")
                    self.stats["commands"] += 1
            exec_ms = int((time.time() - t_exec) * 1000)
            if not result.get("ok"):
                self.stats["errors"] += 1
        except Exception as exc:
            response = f"Erro ao executar: {exc}"
            self.last_response = response
            self.last_error = response
            self.stats["errors"] += 1
            error = str(exc)[:300]
            core_failed = True
            exec_ms = 0
        if core_failed:
            # Keep the existing user-facing, non-sensitive error fallback. It
            # is a valid status response, never an invented Core answer.
            self._recover_after_failure("core", error or response)
            output = output or get_output_mode_manager().parse(
                str(command or ""), source="voice"
            )
            self.last_response = response
            if output.get("speak", True):
                self.state = "SPEAKING"
                self._speak(to_spoken_text(response))
            else:
                self.state = "WAITING_WAKE"
            return
        timings.setdefault("routing_ms", int((t_exec - t_route) * 1000))
        timings["execution_ms"] = exec_ms
        timings["llm_ms"] = llm_latency
        output = output or get_output_mode_manager().parse(command, source="voice")
        spoken_response = to_spoken_text(response)
        self.last_response = response
        self.last_event_id += 1
        self.last_event = {"id": self.last_event_id, "heard": command,
                           "utterance_id": timings.get("utterance_id", ""),
                           "route": route, "skill": skill, "confidence": confidence,
                           "tool": tool, "tool_provider": tool_provider,
                           "ack": ack,
                           "canonical_response": response,
                           "spoken_response": spoken_response,
                           "output_mode": output.get("mode", "AUTO"),
                           "response": response, "error": error, "timings": timings,
                           "at": time.time()}
        try:
            self.service.record_response_metrics(
                route, skill, tool, brain.request_metrics(tool),
                exec_result if tool and "exec_result" in locals() else {"ok": not bool(error)},
                ack=ack, task_id="voice")
        except Exception:
            pass
        self._voice.touch_interaction()
        self.state = "SPEAKING" if output.get("speak", True) else "WAITING_WAKE"
        t_tts = time.time()
        self._tts_first_audio_at = 0.0
        if output.get("speak", True):
            self._speak(spoken_response)
        self._ignore_input_until = time.time() + max(.2, float(
            os.getenv("JARVIS_TTS_INPUT_GUARD_SECONDS", ".6")))
        first_audio = self._tts_first_audio_at or t_tts
        self.last_event["timings"]["tts_first_audio_ms"] = (
            int((first_audio - t_tts) * 1000) if output.get("speak", True) else 0)
        self.last_event["timings"]["tts_start_ms"] = self.last_event["timings"]["tts_first_audio_ms"]
        self.last_event["timings"]["total_turn_ms"] = (
            timings.get("capture_ms", 0) + timings.get("stt_ms", 0)
            + timings["routing_ms"] + timings["execution_ms"]
            + self.last_event["timings"]["tts_first_audio_ms"])
        self.last_event["timings"]["total_ms"] = self.last_event["timings"]["total_turn_ms"]

    # ═══════════════════════════════════════════════════════════════
    # TTS — toca a resposta nas auto-falantes
    # ═══════════════════════════════════════════════════════════════

    def speak_now(self, text: str) -> dict:
        """Fala um texto imediatamente (usado pela API de teste)."""
        text = str(text or "").strip()[:600]
        if not text:
            return {"ok": False, "error": "Texto vazio"}
        if self._voice_mode == "gemini_live":
            return {
                "ok": False,
                "error": "LOCAL_TTS_BLOCKED_BY_GEMINI_MODE",
                "message": "O áudio local está bloqueado enquanto Gemini Live está selecionado.",
            }
        spoke = self._speak(text)
        return {"ok": True, "spoken": spoke, "message": "Falando..." if spoke else "Falhou o TTS."}

    def _speak(self, text: str) -> bool:
        if not text:
            return False
        if self._voice_mode == "gemini_live":
            self.last_error = "LOCAL_TTS_BLOCKED_BY_GEMINI_MODE"
            return False
        operation_cancellation = self._operation_cancellation
        if (self._voice_session.cancellation.is_cancelled
                or operation_cancellation.is_cancelled):
            self.state = "INTERRUPTED"
            return False
        self._tts_epoch += 1
        # A new valid response owns a fresh operation token; the old
        # barge-in marker must not poison later turns.
        self._barge_in_cancel.clear()
        self._speaking_event.set()
        try:
            if self._streaming_tts is not None:
                self._streaming_tts.cancel("single_speak_boundary")
            if self._tts_pipeline is not None:
                try:
                    result = self._tts_pipeline.speak(
                        text,
                        session_id=self._voice_session.session_id,
                        turn_id=self._current_turn_id,
                        generation=self._tts_epoch,
                    )
                    if getattr(result, "accepted_chunks", 0):
                        self._tts_first_audio_at = time.time()
                    if getattr(result, "cancelled", False):
                        self.state = "INTERRUPTED"
                    spoken = bool(getattr(result, "ok", False))
                    if not spoken and not getattr(result, "cancelled", False):
                        self._recover_after_failure(
                            "tts", getattr(result, "error", "provider failure")
                        )
                    return spoken
                except Exception as exc:
                    log.warning("Provider-neutral TTS failed: %s", exc)
                    self.last_error = str(exc)
                    self._recover_after_failure("tts", exc)
                    return False
            if self.tts_mode in ("auto", "edge"):
                if self._speak_edge(text):
                    return True
                if self.tts_mode == "edge":
                    self._recover_after_failure("tts", "edge provider failure")
                    return False
            spoken = self._speak_sapi(text)
            if not spoken:
                self._recover_after_failure("tts", "legacy provider failure")
            return spoken
        finally:
            self._ignore_input_until = time.time() + max(.2, float(
                os.getenv("JARVIS_TTS_INPUT_GUARD_SECONDS", ".6")))
            self._speaking_event.clear()
            if (
                (self._barge_in_cancel.is_set() or operation_cancellation.is_cancelled)
                and self.state in {"SPEAKING", "TRANSCRIBING", "PROCESSING"}
            ):
                self.state = "INTERRUPTED"

    def _speak_edge(self, text: str) -> bool:
        """edge-tts (voz neural) → mp3 → MediaPlayer nativo do Windows."""
        path = None
        try:
            import asyncio
            import edge_tts

            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)

            async def generate():
                communicate = edge_tts.Communicate(
                    text, "pt-BR-FranciscaNeural", rate="+4%", pitch="-2Hz"
                )
                await communicate.save(path)

            asyncio.run(generate())
            return self._play_mp3_windows(Path(path))
        except Exception:
            return False
        finally:
            if path:
                try:
                    os.unlink(path)
                except Exception:
                    pass

    def _play_mp3_windows(self, path: Path) -> bool:
        """Reproduz mp3 com WPF MediaPlayer (nativo, sem pacotes extras)."""
        try:
            import subprocess

            uri = path.resolve().as_uri()
            ps = (
                "Add-Type -AssemblyName PresentationCore;"
                "$p = New-Object System.Windows.Media.MediaPlayer;"
                f"$p.Open([Uri]'{uri}');"
                "for($i=0;$i -lt 50 -and -not $p.NaturalDuration.HasTimeSpan;$i++)"
                "{Start-Sleep -Milliseconds 100};"
                "if($p.NaturalDuration.HasTimeSpan)"
                "{$d=[math]::Ceiling($p.NaturalDuration.TimeSpan.TotalSeconds+0.5)}"
                "else{$d=8};"
                "$p.Play(); Start-Sleep -Seconds $d; $p.Close()"
            )
            self._tts_first_audio_at = time.time()
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, timeout=60, check=False,
            )
            return True
        except Exception:
            return False

    def _speak_sapi(self, text: str) -> bool:
        """Fallback offline: SAPI do Windows via pywin32 (sem arquivos)."""
        try:
            import win32com.client  # pywin32 (ja em requirements.txt)

            if self._sapi is None:
                self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            self._tts_first_audio_at = time.time()
            self._sapi.Speak(text)
            return True
        except Exception:
            print(f"[JARVIS-VOICE] (sem TTS) {text}")
            return False

    # ═══════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════

    def status(self) -> dict:
        try:
            level_age_ms = int((time.time() - self.last_level_at) * 1000)
        except Exception:
            level_age_ms = -1
        return {
            "ok": True,
            "running": self.is_running(),
            "enabled": self.enabled,
            "state": self.state,
            "voice_state": self._state_machine.state.value,
            "session_id": self._voice_session.session_id,
            "voice_session": {
                "session_id": self._voice_session.session_id,
                "created_at": self._voice_session.created_at,
                "cancellation_requested": self._voice_session.cancellation.is_cancelled,
                "cancellation_reason": self._voice_session.cancellation.reason,
            },
            "state_machine": {
                "transitions": len(self._state_machine.history),
                "transition_errors": self._state_transition_errors,
                "last_error": self._last_state_error,
            },
            "wake_word": self._voice.WAKE_WORD if self._voice else "jarvis",
            "tts_mode": self.tts_mode,
            "voice_features": voice_feature_snapshot(),
            "conversation_profile": self.conversation_profile(),
            "gemini_live": self.gemini_live_status(),
            "microphone": {
                "selected_id": self._selected_microphone_id,
                "configured": bool(self._selected_microphone_id),
                "adaptive_enabled": adaptive_microphone_enabled(),
            },
            "whisper_model": os.getenv("JARVIS_WHISPER_MODEL", "small"),
            "stt": self._voice.status() if self._voice else {},
            "last_heard": self.last_heard,
            "last_response": self.last_response,
            "last_error": self.last_error,
            "level": {"rms": self.last_level, "age_ms": level_age_ms},
            "last_event": dict(self.last_event),
            "last_rejection": dict(self.last_rejection),
            "capture_requested": self._push_to_talk_requested.is_set(),
            "audio_input": (
                self._audio_input_provider.diagnostics()
                if self._audio_input_provider is not None
                else {"running": False}
            ),
            "realtime_pipeline": (
                self._realtime_pipeline.diagnostics()
                if self._realtime_pipeline is not None else {"active": False}
            ),
            "tts_pipeline": {
                "configured": self._tts_pipeline is not None,
                "owner": "VoiceService" if self._tts_pipeline is not None else "",
                "identity": (
                    self._tts_pipeline.identity
                    if self._tts_pipeline is not None else None
                ),
                "streaming": (
                    self._streaming_tts.diagnostics()
                    if self._streaming_tts is not None else None
                ),
            },
            "barge_in": dict(self._last_barge_in),
            "stats": dict(self.stats),
            # P1.4C: Turn manager + barge-in status
            "turn_manager": {
                "current_turn_id": self._turn_manager.current_turn_id,
                "barge_in_enabled": is_barge_in_enabled(),
                "barge_in_cancel_set": self._barge_in_cancel.is_set(),
            },
            "lifecycle": {
                "owner": "VoiceService",
                "recovery_in_progress": self._recovery_in_progress,
                "last_recovery": dict(self._last_recovery),
                "realtime_stop_pending": bool(
                    self._realtime_stop_task is not None
                    and not self._realtime_stop_task.done()
                ),
            },
            "conversation_turns": len(self._conversation_messages),
        }


# Singleton
_voice_service: VoiceService | None = None
_voice_service_lock = threading.Lock()


def get_voice_service() -> VoiceService:
    global _voice_service
    with _voice_service_lock:
        if _voice_service is None:
            _voice_service = VoiceService()
        return _voice_service
