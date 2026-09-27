"""
Jarvis Voice Module
===================
Gerencia voz do Jarvis: microfone, wake word, STT, TTS.

Estados:
    DORMINDO    → aguardando wake word
    OUVINDO     → gravando audio do usuario
    PROCESSANDO → transcrevendo audio
    FALANDO     → Jarvis esta respondendo por voz

Uso do servidor (browser envia audio):
    1. Browser grava audio via Web Speech API ou MediaRecorder
    2. Envia base64 para /api/jarvis/voice/transcribe
    3. Servidor transcreve com faster-whisper
    4. Retorna texto

Uso local (microfone direto):
    1. Jarvis grava do microfone
    2. Detecta wake word "Jarvis"
    3. Transcreve com faster-whisper
    4. Envia para JarvisService
    5. Responde por voz com Edge TTS
"""

import base64
import io
import os
import re
import tempfile
import threading
import time
import unicodedata
import uuid
import wave
from collections import deque
from enum import Enum
from pathlib import Path
from typing import Optional


def _strip_accents(text: str) -> str:
    """Remove acentos preservando comprimento (para fatiar o original)."""
    out = []
    for ch in str(text or ""):
        decomposed = unicodedata.normalize("NFD", ch)
        base = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
        out.append(base[:1] if base else ch)
    return "".join(out)


def get_input_device_info():
    """Dispositivo de entrada REAL usado pelo VoiceService (sem mudar nada).

    Retorna dict com nome, índice, host API, canais e sample rate nativo.
    Nunca altera a configuração global do Windows.
    """
    info = {"name": "", "index": -1, "host_api": "", "channels": 0,
            "native_samplerate": 0, "capture_samplerate": 16000,
            "capture_channels": 1, "available": False}
    try:
        import sounddevice as sd
        default_in, _ = sd.default.device
        devices = sd.query_devices()
        if default_in is not None and 0 <= default_in < len(devices):
            dev = devices[default_in]
            try:
                host = sd.query_hostapis(dev["hostapi"])["name"]
            except Exception:
                host = ""
            info.update({"name": str(dev.get("name", "")), "index": int(default_in),
                         "host_api": str(host),
                         "channels": int(dev.get("max_input_channels", 0)),
                         "native_samplerate": float(dev.get("default_samplerate", 0) or 0),
                         "available": True})
    except Exception:
        pass
    return info


def _calibration_seconds():
    return max(.15, float(os.getenv("JARVIS_NOISE_CALIBRATION_SECONDS", ".35")))


def effective_pre_roll_seconds(voice=None):
    """Pre-roll efetivo em segundos (0 = automático pela calibração)."""
    override = float(getattr(voice, "pre_roll_seconds", 0) or 0)
    if override > 0:
        return override
    return max(.25, _calibration_seconds() + .15)


class VoiceState(str, Enum):
    DORMINDO = "DORMINDO"
    OUVINDO = "OUVINDO"
    PROCESSANDO = "PROCESSANDO"
    FALANDO = "FALANDO"


class JarvisVoice:
    """Motor de voz do Jarvis."""

    WAKE_WORD = "jarvis"
    SILENCE_THRESHOLD = 500
    MAX_RECORD_SECONDS = 30
    SILENCE_TIMEOUT = 2

    def __init__(self):
        self.state = VoiceState.DORMINDO
        self.whisper_model = None
        self.model_name = os.getenv("JARVIS_WHISPER_MODEL", "small")
        self.compute_type = os.getenv("JARVIS_WHISPER_COMPUTE", "int8")
        self.language = os.getenv("JARVIS_STT_LANGUAGE", "pt")
        self._whisper_error = ""
        self.beam_size = max(1, int(os.getenv("JARVIS_STT_BEAM", "1")))
        self.best_of = max(1, int(os.getenv("JARVIS_STT_BEST_OF", "1")))
        self.initial_prompt = os.getenv("JARVIS_STT_INITIAL_PROMPT",
            "Jarvis, Golden, Golden Jarvis, Radar, MetaTrader, MT5, XAUUSD, Forex, "
            "dólar, cotação, calculadora, gerenciador de tarefas, Bloco de Notas, OpenCode, Codex")
        self.silence_seconds = max(.3, float(os.getenv("JARVIS_SILENCE_SECONDS", ".55")))
        self.pre_roll_seconds = float(os.getenv("JARVIS_PRE_ROLL_SECONDS", "0") or 0)
        self.noise_floor = float(os.getenv("JARVIS_NOISE_FLOOR_INITIAL", "60"))
        self.speech_threshold = self._threshold_for(self.noise_floor)
        self._model_lock = threading.Lock()
        self._warmup_thread = None
        self.warmup = {"state": "NOT_STARTED", "latency_ms": 0, "error": ""}
        self.last_transcription = ""
        self.wake_word_enabled = True
        self.conversation_timeout = 30
        self.last_interaction = 0.0
        self.mic_info = get_input_device_info()
        self.last_capture = {}

    # ═══════════════════════════════════════════════════════════════
    # WHISPER MODEL (lazy loading)
    # ═══════════════════════════════════════════════════════════════

    def _ensure_whisper(self):
        if self.whisper_model is not None:
            return
        with self._model_lock:
            if self.whisper_model is not None:
                return
            try:
                from faster_whisper import WhisperModel
                from .stt_faster_whisper import (
                    validate_approved_model_path,
                    APPROVED_MODEL_COMPUTE_TYPE,
                )
                approved_path = validate_approved_model_path(
                    os.getenv("JARVIS_STT_MODEL_PATH")
                )
                self.whisper_model = WhisperModel(
                    str(approved_path), device="cpu",
                    compute_type=self.compute_type or APPROVED_MODEL_COMPUTE_TYPE,
                    local_files_only=True,
                )
            except ImportError:
                self.whisper_model = None
                self._whisper_error = "faster-whisper nao disponivel"
            except Exception as exc:
                self.whisper_model = None
                self._whisper_error = str(exc)[:240]

    def warmup_async(self):
        if self._warmup_thread and self._warmup_thread.is_alive():
            return self._warmup_thread
        def run():
            started = time.perf_counter()
            self.warmup = {"state": "RUNNING", "latency_ms": 0, "error": ""}
            try:
                self._ensure_whisper()
                if self.whisper_model is None:
                    raise RuntimeError("faster-whisper nao disponivel")
                self.warmup = {"state": "READY",
                    "latency_ms": int((time.perf_counter() - started) * 1000), "error": ""}
            except Exception as exc:
                self.warmup = {"state": "ERROR", "latency_ms": 0, "error": str(exc)[:160]}
        self._warmup_thread = threading.Thread(target=run, name="jarvis-stt-warmup", daemon=True)
        self._warmup_thread.start()
        return self._warmup_thread

    # ═══════════════════════════════════════════════════════════════
    # STT — Speech to Text
    # ═══════════════════════════════════════════════════════════════

    def transcribe_audio_bytes(self, audio_data: bytes, sample_rate: int = 16000) -> dict:
        """Transcreve audio (bytes WAV) para texto."""
        self._ensure_whisper()
        if not self.whisper_model:
            return {"ok": False, "error": self._whisper_error or "STT model unavailable"}

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                # Se ja for WAV, escrever direto
                if audio_data[:4] == b"RIFF":
                    f.write(audio_data)
                else:
                    # Assumir raw PCM 16-bit
                    with wave.open(f.name, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(sample_rate)
                        wf.writeframes(audio_data)
                tmp_path = f.name

            started = time.perf_counter()
            segments, info = self.whisper_model.transcribe(
                tmp_path, language=self.language, beam_size=self.beam_size,
                best_of=self.best_of, condition_on_previous_text=False,
                initial_prompt=self.initial_prompt
            )
            segments = list(segments)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            stt_ms = int((time.perf_counter() - started) * 1000)
            avg_logprob = (sum(float(seg.avg_logprob) for seg in segments) / len(segments)
                           if segments else -10.0)
            no_speech_prob = max((float(seg.no_speech_prob) for seg in segments), default=1.0)
            compression_ratio = max((float(seg.compression_ratio) for seg in segments), default=0.0)
            confidence = max(0.0, min(1.0, (1.0 - no_speech_prob) * (2.71828 ** avg_logprob)))
            classification, rejected_reason = self.classify_transcript(
                text, avg_logprob, no_speech_prob, compression_ratio)

            self.last_transcription = text
            return {
                "ok": True,
                "text": text,
                "language": info.language,
                "duration": info.duration,
                "accepted": classification == "VALID_COMMAND",
                "classification": classification,
                "rejected_reason": rejected_reason,
                "stt_ms": stt_ms,
                "stt_confidence": round(confidence, 4),
                "avg_logprob": round(avg_logprob, 4),
                "no_speech_prob": round(no_speech_prob, 4),
                "compression_ratio": round(compression_ratio, 4),
                "model": self.model_name, "compute_type": self.compute_type,
                "beam_size": self.beam_size,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def classify_transcript(text, avg_logprob, no_speech_prob, compression_ratio):
        normalized = re.sub(r"\s+", " ", str(text or "").strip().casefold())
        if not normalized:
            return "IGNORED_NOISE", "empty"
        hallucinations = {
            "obrigado por assistir", "inscreva-se no canal",
            "legendas pela comunidade amara.org", "até o próximo vídeo",
        }
        if normalized.strip(" .!?,") in hallucinations:
            return "IGNORED_NOISE", "known_silence_hallucination"
        words = re.findall(r"\w+", normalized)
        if len(words) >= 6 and len(set(words)) <= max(1, len(words) // 4):
            return "IGNORED_NOISE", "repetition"
        if no_speech_prob >= float(os.getenv("JARVIS_STT_NO_SPEECH_MAX", ".65")):
            return "IGNORED_NOISE", "no_speech_probability"
        if (avg_logprob < float(os.getenv("JARVIS_STT_MIN_LOGPROB", "-1.35"))
                or compression_ratio > float(os.getenv("JARVIS_STT_MAX_COMPRESSION", "2.8"))):
            return "LOW_CONFIDENCE", "decoder_confidence"
        return "VALID_COMMAND", ""

    def accepted_for_risk(self, result, high_risk=False):
        if not result.get("accepted"):
            return False
        if not high_risk:
            return True
        return (float(result.get("avg_logprob", -10)) >=
                float(os.getenv("JARVIS_STT_RISK_MIN_LOGPROB", "-.8"))
                and float(result.get("no_speech_prob", 1)) <=
                float(os.getenv("JARVIS_STT_RISK_NO_SPEECH_MAX", ".4")))

    def transcribe_base64(self, audio_b64: str, format: str = "wav") -> dict:
        """Transcreve audio base64 para texto."""
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception as e:
            return {"ok": False, "error": f"Base64 invalido: {e}"}

        if format == "wav":
            return self.transcribe_audio_bytes(audio_bytes)
        elif format == "raw":
            return self.transcribe_audio_bytes(audio_bytes, sample_rate=16000)
        else:
            return {"ok": False, "error": f"Formato nao suportado: {format}"}

    # ═══════════════════════════════════════════════════════════════
    # WAKE WORD DETECTION
    # ═══════════════════════════════════════════════════════════════

    def detect_wake_word(self, text: str) -> bool:
        """Verifica se o texto contem a wake word 'Jarvis' (acentos ok)."""
        if not self.wake_word_enabled:
            return True
        norm = _strip_accents(text).lower().strip()
        if norm.startswith(self.WAKE_WORD):
            return True
        if self.WAKE_WORD in norm:
            return True
        return False

    def strip_wake_word(self, text: str) -> str:
        """Remove wake word SOMENTE do inicio: Jarvis/Jarvis + pontuacao.

        Nunca remove ocorrencias no meio da frase.
        """
        original = str(text or "")
        lowered = _strip_accents(original).lower()
        match = re.match(r"\s*(jarvis)\s*[,.:;…!?\u2026\-]*\s*", lowered)
        if not match:
            return original.strip()
        # Fatiar o ORIGINAL pelo mesmo comprimento do prefixo casado.
        prefix_len = match.end()
        # Ajuste: o match foi no texto normalizado (mesmo comprimento,
        # ja que _strip_accents preserva caracteres 1:1 para estes casos).
        return original[prefix_len:].strip() if prefix_len <= len(original) else ""

    def is_conversation_active(self) -> bool:
        """Verifica se a conversa ainda esta ativa (dentro do timeout)."""
        if self.last_interaction == 0:
            return False
        return (time.time() - self.last_interaction) < self.conversation_timeout

    def touch_interaction(self):
        """Registra interacao (reseta timeout)."""
        self.last_interaction = time.time()

    # ═══════════════════════════════════════════════════════════════
    # TTS — Text to Speech (Edge TTS)
    # ═══════════════════════════════════════════════════════════════

    async def text_to_speech(self, text: str, voice: str = "pt-BR-FranciscaNeural") -> dict:
        """Converte texto para audio usando Edge TTS."""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice, rate="+4%", pitch="-2Hz")

            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            audio_bytes = b"".join(audio_chunks)
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

            return {
                "ok": True,
                "audio": audio_b64,
                "voice": voice,
                "size_bytes": len(audio_bytes),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def text_to_speech_sync(self, text: str, voice: str = "pt-BR-FranciscaNeural") -> dict:
        """Versao sincrona do TTS (bloqueia)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.text_to_speech(text, voice))
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(self.text_to_speech(text, voice))
        except Exception:
            return asyncio.run(self.text_to_speech(text, voice))

    # ═══════════════════════════════════════════════════════════════
    # MICROPHONE RECORDING (local)
    # ═══════════════════════════════════════════════════════════════

    def record_from_microphone(self, max_seconds: int = None) -> dict:
        """Grava audio do microfone local. Retorna bytes WAV."""
        max_seconds = max_seconds or self.MAX_RECORD_SECONDS
        try:
            import sounddevice as sd
            import numpy as np

            samplerate = 16000
            channels = 1
            dtype = "int16"

            audio = sd.rec(
                int(samplerate * max_seconds),
                samplerate=samplerate,
                channels=channels,
                dtype=dtype,
            )
            sd.wait()

            # Converter para WAV bytes
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(samplerate)
                wf.writeframes(audio.tobytes())

            return {"ok": True, "audio": buf.getvalue(), "samplerate": samplerate}
        except ImportError:
            return {"ok": False, "error": "sounddevice nao instalado"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def record_until_silence(self, max_seconds: int = None, level_callback=None,
                             state_callback=None, stop_event=None) -> dict:
        """Grava audio ate detectar silencio.

        level_callback(rms): telemetria real do microfone por bloco
        (sem audio, so nivel). Opcional.
        """
        max_seconds = max_seconds or self.MAX_RECORD_SECONDS
        try:
            import sounddevice as sd
            import numpy as np

            samplerate = 16000
            channels = 1
            blocksize = 1024
            frames = []
            calibration_seconds = _calibration_seconds()
            if self.pre_roll_seconds > 0:
                pre_roll_seconds = self.pre_roll_seconds
            else:
                pre_roll_seconds = max(.25, calibration_seconds + .15)
            pre_roll = deque(maxlen=max(2, int(pre_roll_seconds * samplerate / blocksize)))
            calibration = []
            prev_floor = float(self.noise_floor or 0)
            speech_started = False
            speech_started_at = 0.0
            last_speech_at = 0.0
            utterance_id = uuid.uuid4().hex
            peak = 0
            clipped_samples = 0
            near_clip_samples = 0

            with sd.InputStream(
                samplerate=samplerate,
                channels=channels,
                dtype="int16",
                blocksize=blocksize,
            ) as stream:
                start = time.time()
                while (time.time() - start) < max_seconds:
                    if stop_event is not None and stop_event.is_set():
                        break
                    data, overflowed = stream.read(blocksize)
                    level = int(np.abs(data).mean())
                    block_peak = int(np.abs(data).max()) if data.size else 0
                    peak = max(peak, block_peak)
                    clipped_samples += int((np.abs(data) >= 32767).sum())
                    near_clip_samples += int((np.abs(data) >= 30000).sum())
                    if level_callback is not None:
                        try:
                            level_callback(level)
                        except Exception:
                            pass
                    elapsed = time.time() - start
                    if not speech_started:
                        pre_roll.append(data.copy())
                        if elapsed <= calibration_seconds:
                            calibration.append(level)
                            low_half = sorted(calibration)[:max(1, len(calibration) // 2)]
                            measured = sum(low_half) / len(low_half)
                            # Anti-contaminação: se o usuário começou a falar
                            # durante a calibração, o floor medido explode e o
                            # gate dispara tarde (começo da frase é cortado).
                            # Trava a subida brusca; a adaptação fina (EMA)
                            # continua após a calibração.
                            cap = float(os.getenv("JARVIS_CALIBRATION_MAX_JUMP", "4"))
                            if prev_floor > 0 and measured > prev_floor * cap:
                                measured = prev_floor * cap
                            self.noise_floor = measured
                            self.speech_threshold = self._threshold_for(self.noise_floor)
                            continue
                        if level >= self.speech_threshold:
                            speech_started = True
                            speech_started_at = time.time()
                            last_speech_at = speech_started_at
                            frames.extend(pre_roll)
                            if state_callback:
                                state_callback("LISTENING")
                        else:
                            self.noise_floor = self.noise_floor * .95 + level * .05
                            self.speech_threshold = self._threshold_for(self.noise_floor)
                            continue
                    else:
                        frames.append(data.copy())
                        if level >= self.speech_threshold:
                            last_speech_at = time.time()
                        elif time.time() - last_speech_at >= self.silence_seconds:
                            break

            audio = np.concatenate(frames) if frames else np.array([], dtype="int16")
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(samplerate)
                wf.writeframes(audio.tobytes())

            ended = time.time()
            capture = {"ok": True, "audio": buf.getvalue(), "samplerate": samplerate,
                    "utterance_id": utterance_id if speech_started else "",
                    "speech_detected": speech_started, "captured_at": ended,
                    "capture_ms": int((ended - start) * 1000),
                    "speech_start_ms": int((speech_started_at - start) * 1000) if speech_started else 0,
                    "speech_ms": int((last_speech_at - speech_started_at) * 1000) if speech_started else 0,
                    "silence_wait_ms": int((ended - last_speech_at) * 1000) if speech_started else 0,
                    "speech_end_detect_ms": int((ended - last_speech_at) * 1000) if speech_started else 0,
                    "pre_roll_ms": int(len(pre_roll) * blocksize / samplerate * 1000),
                    "end_silence_target_ms": int(self.silence_seconds * 1000),
                    "peak": peak, "clipped_samples": clipped_samples,
                    "near_clip_samples": near_clip_samples,
                    "clipping": bool(clipped_samples),
                    "noise_floor": round(self.noise_floor, 1),
                    "speech_threshold": round(self.speech_threshold, 1),
                    "overflowed": bool(overflowed) if 'overflowed' in locals() else False}
            self.last_capture = {k: v for k, v in capture.items() if k != "audio"}
            return capture
        except ImportError:
            return {"ok": False, "error": "sounddevice nao instalado"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    def _threshold_for(noise_floor):
        margin = float(os.getenv("JARVIS_SPEECH_MARGIN", "55"))
        ratio = float(os.getenv("JARVIS_SPEECH_NOISE_RATIO", "2.2"))
        minimum = float(os.getenv("JARVIS_SPEECH_THRESHOLD_MIN", "110"))
        return max(minimum, float(noise_floor) * ratio + margin)

    # ═══════════════════════════════════════════════════════════════
    # FULL VOICE PIPELINE (local)
    # ═══════════════════════════════════════════════════════════════

    def listen_and_transcribe(self) -> dict:
        """Grava do microfone e transcreve. Pipeline completo."""
        self.state = VoiceState.OUVINDO
        record = self.record_until_silence()
        if not record.get("ok"):
            self.state = VoiceState.DORMINDO
            return record

        self.state = VoiceState.PROCESSANDO
        result = self.transcribe_audio_bytes(record["audio"], record["samplerate"])
        self.state = VoiceState.DORMINDO
        return result

    def process_voice_command(self, text: str) -> dict:
        """Processa comando de voz: detecta wake word, extrai comando."""
        if self.detect_wake_word(text):
            self.touch_interaction()
            command = self.strip_wake_word(text)
            if not command:
                return {"ok": True, "wake_word": True, "command": "", "action": "listen_more"}
            return {"ok": True, "wake_word": True, "command": command, "action": "execute"}

        if self.is_conversation_active():
            self.touch_interaction()
            return {"ok": True, "wake_word": False, "command": text, "action": "continue_conversation"}

        return {"ok": True, "wake_word": False, "command": "", "action": "ignore"}

    # ═══════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════

    def status(self) -> dict:
        return {
            "state": self.state.value,
            "language": self.language,
            "wake_word_enabled": self.wake_word_enabled,
            "wake_word": self.WAKE_WORD,
            "whisper_available": self.whisper_model is not None,
            "model": self.model_name, "compute_type": self.compute_type,
            "beam_size": self.beam_size, "best_of": self.best_of,
            "initial_prompt": self.initial_prompt,
            "noise_floor": round(self.noise_floor, 1),
            "speech_threshold": round(self.speech_threshold, 1),
            "silence_seconds": self.silence_seconds,
            "pre_roll_seconds": round(effective_pre_roll_seconds(self), 3),
            "mic": dict(self.mic_info),
            "last_capture": dict(self.last_capture),
            "warmup": dict(self.warmup),
            "stt_error": self._whisper_error,
            "conversation_active": self.is_conversation_active(),
            "last_transcription": self.last_transcription,
        }


# Singleton
_voice = None

def get_voice() -> JarvisVoice:
    global _voice
    if _voice is None:
        _voice = JarvisVoice()
    return _voice
