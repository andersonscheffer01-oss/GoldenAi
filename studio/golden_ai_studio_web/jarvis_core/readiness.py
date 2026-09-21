"""Jarvis readiness — SSOT do estado de startup (P1.3).

Estados: STARTING -> CORE_READY -> WARMING -> READY | DEGRADED | FAILED.

- Backend ONLINE nao significa JARVIS READY: READY exige componentes
  essenciais preparados (providers registrados, STT aquecido, voz pronta).
- O singleton nasce em READY (pass-through): processos que nunca executam
  o boot (ex.: testes unitários) não são bloqueados pelo gate de voz.
- Telemetria nunca contém segredos: só estados, tempos e contagens.
"""
import threading
import time

STARTING = "STARTING"
CORE_READY = "CORE_READY"
WARMING = "WARMING"
READY = "READY"
DEGRADED = "DEGRADED"
FAILED = "FAILED"

_PRE_READY = (STARTING, CORE_READY, WARMING)


class JarvisReadiness:
    """Fonte única do estado de prontidão do Jarvis."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.state = READY
            self.started_at = 0.0
            self.core_ready_ms = None
            self.full_ready_ms = None
            self.provider_registration_ms = None
            self.provider_health_ms = None
            self.stt_load_ms = None
            self.stt_warmup_ms = None
            self.degraded_reason = ""
            self.fail_reason = ""
            self.components = {"providers_registered": [],
                               "ollama": "", "ollama_models": [],
                               "stt_warm": ""}

    def begin(self):
        """Início do boot. Idempotente: segundo begin sem reset é no-op."""
        with self._lock:
            if self.started_at:
                return False
            self.state = STARTING
            self.started_at = time.time()
            self.core_ready_ms = None
            self.full_ready_ms = None
            self.degraded_reason = ""
            self.fail_reason = ""
            return True

    def core_ready(self):
        with self._lock:
            if self.state == STARTING:
                self.state = CORE_READY
                self.core_ready_ms = int((time.time() - self.started_at) * 1000)

    def warming(self):
        with self._lock:
            if self.state in (STARTING, CORE_READY):
                self.state = WARMING

    def record(self, **kwargs):
        with self._lock:
            for key in ("provider_registration_ms", "provider_health_ms",
                        "stt_load_ms", "stt_warmup_ms"):
                if kwargs.get(key) is not None:
                    setattr(self, key, int(kwargs[key]))
            for key in ("providers_registered", "ollama", "ollama_models",
                        "stt_warm"):
                if key in kwargs:
                    self.components[key] = kwargs[key]

    def complete(self, degraded=False, reason=""):
        with self._lock:
            if self.state in (READY, DEGRADED, FAILED):
                return self.state
            self.state = DEGRADED if degraded else READY
            self.degraded_reason = str(reason or "") if degraded else ""
            self.full_ready_ms = int((time.time() - self.started_at) * 1000)
            return self.state

    def fail(self, reason=""):
        with self._lock:
            self.state = FAILED
            self.fail_reason = str(reason or "")
            return self.state

    def is_warming(self):
        with self._lock:
            return self.state in _PRE_READY

    def status(self):
        with self._lock:
            return {"state": self.state, "startup_started_at": self.started_at,
                    "core_ready_ms": self.core_ready_ms,
                    "full_ready_ms": self.full_ready_ms,
                    "provider_registration_ms": self.provider_registration_ms,
                    "provider_health_ms": self.provider_health_ms,
                    "stt_load_ms": self.stt_load_ms,
                    "stt_warmup_ms": self.stt_warmup_ms,
                    "degraded_reason": self.degraded_reason,
                    "fail_reason": self.fail_reason,
                    "components": {k: (list(v) if isinstance(v, list) else v)
                                   for k, v in self.components.items()}}


_readiness = None
_readiness_lock = threading.Lock()


def get_readiness():
    global _readiness
    with _readiness_lock:
        if _readiness is None:
            _readiness = JarvisReadiness()
        return _readiness
