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

import io
import os
import tempfile
import threading
import time
import uuid
import wave
from pathlib import Path

import numpy as np

from .voice import get_voice
from .output_mode import get_output_mode_manager, to_spoken_text
from .streaming import is_streaming_enabled, is_barge_in_enabled
from .streaming.turn_manager import TurnManager
from .streaming.barge_in_calibration import (
    BARGE_IN_PERSISTENCE_BLOCKS,
    BARGE_IN_ADAPTIVE_MARGIN,
    BARGE_IN_MIN_ABSOLUTE,
    BARGE_IN_RMS_THRESHOLD,
)

log = __import__("logging").getLogger(__name__)

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
        self._conversation_id: str = uuid.uuid4().hex  # persists across cancelled turns
        self._session_id: str = uuid.uuid4().hex

    # ═══════════════════════════════════════════════════════════════
    # CICLO DE VIDA
    # ═══════════════════════════════════════════════════════════════

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, service) -> dict:
        """Inicia a escuta local. `service` = JarvisService (obrigatorio)."""
        if self.is_running():
            return {"ok": True, "message": "VoiceService ja esta rodando."}
        if service is None:
            return {"ok": False, "error": "JarvisService nao fornecido."}
        self.service = service
        self.stop_event.clear()
        self._voice = get_voice()
        self._voice.warmup_async()
        self.thread = threading.Thread(target=self._loop, name="jarvis-voice", daemon=True)
        self.thread.start()
        self.state = "OUVINDO"
        return {"ok": True, "message": 'VoiceService iniciado. Diga "Jarvis" + comando.'}

    def stop(self) -> dict:
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
        self._session_id = uuid.uuid4().hex
        if not self.is_running():
            self.state = "OFF"
            return {"ok": True, "message": "VoiceService nao estava rodando."}
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2.0)
        self.state = "OFF"
        return {"ok": True, "message": "VoiceService parado."}

    def set_enabled(self, value: bool) -> dict:
        self.enabled = bool(value)
        if not self.enabled:
            return {**self.stop(), "enabled": False}
        return {"ok": True, "enabled": True}

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
                    if action.get("action") == "listen_more":
                        # Wake word sozinha: acorda, mas nao gera comando.
                        self.state = "WAKE_DETECTED"
                        self.stop_event.wait(1.2)
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

                                self._barge_in_cancel.set()
                                self._turn_manager.cancel_current()
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

            # P1.4C: Append user turn to conversation context FIRST
            # (before build_messages, so it appears in context for the LLM)
            self._conversation_messages.append({"role": "user", "content": command})

            # P1.4C: Create new turn (cancels previous)
            self._current_turn_id = self._turn_manager.new_turn()
            self._barge_in_cancel.clear()

            # Get cancel event for this turn
            cancel_event = self._turn_manager.get_cancel_event(self._current_turn_id)

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
                turn_id=self._current_turn_id,
                turn_manager=self._turn_manager,
            ))

            # P1.4C: Stop barge-in monitoring
            self._stop_barge_in_monitor()

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
            exec_ms = 0
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
        spoke = self._speak(text)
        return {"ok": True, "spoken": spoke, "message": "Falando..." if spoke else "Falhou o TTS."}

    def _speak(self, text: str) -> bool:
        if not text:
            return False
        self._tts_epoch += 1
        self._speaking_event.set()
        try:
            if self.tts_mode in ("auto", "edge"):
                if self._speak_edge(text):
                    return True
                if self.tts_mode == "edge":
                    return False
            return self._speak_sapi(text)
        finally:
            self._ignore_input_until = time.time() + max(.2, float(
                os.getenv("JARVIS_TTS_INPUT_GUARD_SECONDS", ".6")))
            self._speaking_event.clear()

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
            "wake_word": self._voice.WAKE_WORD if self._voice else "jarvis",
            "tts_mode": self.tts_mode,
            "whisper_model": os.getenv("JARVIS_WHISPER_MODEL", "small"),
            "stt": self._voice.status() if self._voice else {},
            "last_heard": self.last_heard,
            "last_response": self.last_response,
            "last_error": self.last_error,
            "level": {"rms": self.last_level, "age_ms": level_age_ms},
            "last_event": dict(self.last_event),
            "last_rejection": dict(self.last_rejection),
            "capture_requested": self._push_to_talk_requested.is_set(),
            "stats": dict(self.stats),
            # P1.4C: Turn manager + barge-in status
            "turn_manager": {
                "current_turn_id": self._turn_manager.current_turn_id,
                "barge_in_enabled": is_barge_in_enabled(),
                "barge_in_cancel_set": self._barge_in_cancel.is_set(),
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
