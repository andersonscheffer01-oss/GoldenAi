"""Safe microphone discovery, probing, selection, and adaptive profiles.

This module never opens hardware at import time.  It is a provider-neutral
boundary used by the existing VoiceService; it does not own a second voice
runtime, VAD, STT, or TTS pipeline.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


_HOST_PRIORITY = {"WASAPI": 0, "DirectSound": 1, "MME": 2, "WDM-KS": 3}


def _host_family(value: Any) -> str:
    text = str(value or "").strip()
    upper = text.upper()
    for family in ("WASAPI", "DIRECTSOUND", "MME", "WDM-KS"):
        if family in upper:
            return family
    return text or "Unknown"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


@dataclass(frozen=True)
class MicrophoneEndpoint:
    index: int
    name: str
    host_api: str
    channels: int
    native_sample_rate: float
    stable_id: str
    is_default: bool = False

    def public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdaptiveMicrophoneProfile:
    endpoint_id: str
    speech: list[float] = field(default_factory=list)
    noise: list[float] = field(default_factory=list)
    updated_at: float = 0.0

    def observe(self, kind: str, level: float) -> bool:
        kind = str(kind).strip().casefold()
        level = float(level)
        if kind not in {"speech", "noise"} or not math.isfinite(level) or level <= 0:
            return False
        target = self.speech if kind == "speech" else self.noise
        target.append(level)
        del target[:-120]
        self.updated_at = time.time()
        return True

    def thresholds(self) -> dict[str, float]:
        noise_floor = _percentile(self.noise, 0.5)
        noise_high = _percentile(self.noise, 0.9)
        speech_low = _percentile(self.speech, 0.2)
        if noise_floor <= 0 and speech_low <= 0:
            return {"noise_floor": 0.0, "speech_threshold": 0.0,
                    "rescue_threshold": 0.0, "confidence": 0.0}
        threshold = max(noise_high * 1.15, noise_floor * 1.5)
        if speech_low > 0:
            threshold = min(threshold or speech_low * 0.55, speech_low * 0.75)
        rescue = max(noise_floor * 1.1, min(threshold, speech_low * 0.45 if speech_low else threshold))
        confidence = min(1.0, (len(self.speech) + len(self.noise)) / 24.0)
        return {"noise_floor": round(noise_floor, 3),
                "speech_threshold": round(threshold, 3),
                "rescue_threshold": round(rescue, 3),
                "confidence": round(confidence, 3)}


class MicrophoneProfileStore:
    """Atomic, local persistence containing numeric calibration only."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def load(self, endpoint_id: str) -> AdaptiveMicrophoneProfile:
        with self._lock:
            row = (self._read().get("profiles") or {}).get(str(endpoint_id), {})
        return AdaptiveMicrophoneProfile(
            endpoint_id=str(endpoint_id),
            speech=[float(v) for v in row.get("speech", [])[-120:] if float(v) > 0],
            noise=[float(v) for v in row.get("noise", [])[-120:] if float(v) > 0],
            updated_at=float(row.get("updated_at") or 0),
        )

    def save(self, profile: AdaptiveMicrophoneProfile) -> None:
        with self._lock:
            data = self._read()
            profiles = data.setdefault("profiles", {})
            profiles[profile.endpoint_id] = {
                "speech": profile.speech[-120:], "noise": profile.noise[-120:],
                "updated_at": profile.updated_at,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp",
                                             dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def load_selected_endpoint(self) -> str:
        with self._lock:
            value = self._read().get("selected_endpoint_id", "")
        return str(value or "")[:240]

    def save_selected_endpoint(self, endpoint_id: str) -> None:
        with self._lock:
            data = self._read()
            data["selected_endpoint_id"] = str(endpoint_id or "")[:240]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp",
                                             dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)


class AudioExperienceManager:
    """Enumerate and probe microphones without owning the live audio stream."""

    def __init__(self, *, backend: Any = None,
                 profile_store: Optional[MicrophoneProfileStore] = None):
        self._backend = backend
        self.profile_store = profile_store

    def _sounddevice(self) -> Any:
        if self._backend is not None:
            return self._backend
        import sounddevice as sounddevice
        return sounddevice

    @staticmethod
    def _wasapi_settings(sounddevice: Any, endpoint: MicrophoneEndpoint) -> Any:
        """Request Windows shared-mode conversion only for WASAPI endpoints."""
        if _host_family(endpoint.host_api) != "WASAPI":
            return None
        factory = getattr(sounddevice, "WasapiSettings", None)
        if not callable(factory):
            return None
        try:
            return factory(auto_convert=True)
        except Exception:
            return None

    def enumerate_microphones(self) -> list[MicrophoneEndpoint]:
        sd = self._sounddevice()
        devices = list(sd.query_devices())
        hostapis = list(sd.query_hostapis())
        default = getattr(getattr(sd, "default", None), "device", (None, None))
        default_input = default[0] if isinstance(default, (tuple, list)) else default
        candidates: dict[str, MicrophoneEndpoint] = {}
        for index, row in enumerate(devices):
            channels = int(row.get("max_input_channels") or 0)
            if channels <= 0:
                continue
            api_index = int(row.get("hostapi") or 0)
            api = hostapis[api_index] if 0 <= api_index < len(hostapis) else {}
            host_name = _host_family(api.get("name") or "Unknown")
            name = str(row.get("name") or f"Microphone {index}").strip()
            stable_id = f"{_norm(name)}|{_norm(host_name)}|{channels}"
            endpoint = MicrophoneEndpoint(
                index=index, name=name, host_api=host_name, channels=channels,
                native_sample_rate=float(row.get("default_samplerate") or 16000),
                stable_id=stable_id, is_default=index == default_input,
            )
            physical_key = _norm(name)
            current = candidates.get(physical_key)
            if current is None or _HOST_PRIORITY.get(host_name, 99) < _HOST_PRIORITY.get(current.host_api, 99):
                candidates[physical_key] = endpoint
        return sorted(candidates.values(), key=lambda item: (
            not item.is_default, _HOST_PRIORITY.get(item.host_api, 99), item.name.casefold()))

    def probe(self, endpoint: MicrophoneEndpoint, *, seconds: float = 0.35,
              timeout: float = 2.0, stream_factory: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
        result: dict[str, Any] = {"ok": False, "endpoint_id": endpoint.stable_id,
                                  "blocks": 0, "rms": 0.0, "clipping": 0}
        finished = threading.Event()

        def worker() -> None:
            try:
                sd = self._sounddevice()
                samples: list[int] = []

                def callback(indata, frames, _time_info, _status):
                    raw = bytes(indata)
                    for offset in range(0, len(raw) - 1, 2 * endpoint.channels):
                        samples.append(int.from_bytes(raw[offset:offset + 2], "little", signed=True))
                    result["blocks"] += 1

                factory = stream_factory or sd.RawInputStream
                extra_settings = self._wasapi_settings(sd, endpoint)
                if extra_settings is not None:
                    factory = stream_factory or getattr(sd, "InputStream", factory)
                    probe_rate = 16_000
                    probe_blocksize = 640
                else:
                    probe_rate = endpoint.native_sample_rate
                    probe_blocksize = 0
                stream_kwargs = {
                    "device": endpoint.index,
                    "samplerate": probe_rate,
                    "channels": endpoint.channels,
                    "dtype": "int16",
                    "callback": callback,
                }
                if probe_blocksize:
                    stream_kwargs["blocksize"] = probe_blocksize
                if extra_settings is not None:
                    stream_kwargs["extra_settings"] = extra_settings
                stream = factory(**stream_kwargs)
                with stream:
                    time.sleep(max(0.05, min(float(seconds), 2.0)))
                if samples:
                    result["rms"] = round(math.sqrt(sum(v * v for v in samples) / len(samples)), 2)
                    result["clipping"] = sum(abs(v) >= 32700 for v in samples)
                result["ok"] = bool(result["blocks"] and samples)
                if not result["ok"]:
                    result["error"] = "NO_AUDIO_BLOCKS"
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            finally:
                finished.set()

        threading.Thread(target=worker, name="jarvis-microphone-probe", daemon=True).start()
        if not finished.wait(max(0.1, min(float(timeout), 8.0))):
            return {**result, "ok": False, "error": "PROBE_TIMEOUT"}
        return result

