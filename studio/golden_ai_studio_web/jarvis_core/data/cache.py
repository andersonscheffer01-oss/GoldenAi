"""
Cache TTL simples e thread-safe para dados online — Fase 8.1.
"""

import threading
import time


class TTLCache:
    """Cache em memória com expiração por entrada. Thread-safe."""

    def __init__(self, ttl_seconds: float = 30.0, max_entries: int = 128):
        self.ttl = float(ttl_seconds)
        self.max_entries = max(int(max_entries), 1)
        self._store: dict = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str, allow_stale: bool = False):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                if not allow_stale:
                    self.misses += 1
                return None
            value, expires_at = entry
            if time.time() >= expires_at:
                # Entrada expirada permanece no store (para fallback stale);
                # a limpeza acontece no set() via evicao.
                if not allow_stale:
                    self.misses += 1
                return value if allow_stale else None
            self.hits += 1
            return value

    def set(self, key: str, value):
        with self._lock:
            if len(self._store) >= self.max_entries:
                # Evicta o mais antigo (por expiração).
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
            self._store[key] = (value, time.time() + self.ttl)

    def clear(self):
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            return {"entries": len(self._store), "hits": self.hits, "misses": self.misses,
                    "ttl_seconds": self.ttl}
