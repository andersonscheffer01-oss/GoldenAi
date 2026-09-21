"""Embeddings reais via Ollama, com fallback lexical explicitamente degradado."""
import os
from typing import Any, Dict, List, Optional


class EmbeddingService:
    MODEL_PRIMARY = os.getenv("JARVIS_EMBEDDING_MODEL", "nomic-embed-text")
    TIMEOUT = float(os.getenv("JARVIS_EMBEDDING_TIMEOUT", "15"))
    PROBE_TIMEOUT = float(os.getenv("JARVIS_EMBEDDING_PROBE_TIMEOUT", "3"))

    def __init__(self, ollama_base: str = "http://127.0.0.1:11434"):
        self.ollama_base = ollama_base
        self._available: Optional[bool] = None
        self._model_name: Optional[str] = None
        self._status: Dict[str, Any] = {
            "ok": False, "state": "unknown", "model": None,
            "timeout": self.TIMEOUT, "message": "ainda não verificado",
        }

    @property
    def available(self) -> bool:
        self._refresh_availability()
        return bool(self._available)

    @property
    def model_name(self) -> Optional[str]:
        self._refresh_availability()
        return self._model_name

    def _refresh_availability(self, force: bool = False) -> None:
        if self._available is not None and not force:
            return
        self._available = False
        try:
            import requests
            response = requests.get(self.ollama_base + "/api/tags", timeout=self.PROBE_TIMEOUT)
            if response.status_code == 200:
                for model in response.json().get("models", []):
                    if str(model.get("name", "")).startswith(self.MODEL_PRIMARY):
                        self._available = True
                        self._model_name = self.MODEL_PRIMARY
                        self._status.update({"ok": True, "state": "ok", "model": self.MODEL_PRIMARY,
                                             "message": "modelo disponível"})
                        return
            self._status.update({"ok": False, "state": "degraded", "model": None,
                                 "message": "nomic-embed-text indisponível; busca lexical ativa"})
        except Exception as exc:
            self._status.update({"ok": False, "state": "degraded", "model": None,
                                 "message": f"Ollama indisponível; busca lexical ativa: {exc}"})

    def embed(self, text: str) -> Optional[List[float]]:
        if not text.strip() or not self.available:
            return None
        try:
            import requests
            response = requests.post(self.ollama_base + "/api/embeddings",
                json={"model": self.MODEL_PRIMARY, "prompt": text}, timeout=self.TIMEOUT)
            vector = response.json().get("embedding") if response.status_code == 200 else None
            if isinstance(vector, list) and vector:
                self._status.update({"ok": True, "state": "ok", "model": self.MODEL_PRIMARY,
                                     "message": "embedding real confirmado"})
                return vector
            self._status.update({"ok": False, "state": "degraded", "model": self.MODEL_PRIMARY,
                                 "message": f"embedding inválido (HTTP {response.status_code}); busca lexical ativa"})
        except Exception as exc:
            self._status.update({"ok": False, "state": "degraded", "model": self.MODEL_PRIMARY,
                                 "message": f"embedding falhou; busca lexical ativa: {exc}"})
        return None

    def embed_sync(self, text: str) -> Optional[List[float]]:
        return self.embed(text)

    def status(self) -> Dict[str, Any]:
        """Leitura cacheada: não consulta nem acorda o Ollama."""
        result = dict(self._status)
        result.update({"available": bool(self._available), "model_name": self._model_name,
                       "fallback": None if self._available else "lexical"})
        return result

    def health_check(self) -> Dict[str, Any]:
        self._refresh_availability(force=True)
        vector = self.embed("Golden Jarvis teste embedding")
        if not vector:
            return {"ok": False, "state": "degraded", "model": self.MODEL_PRIMARY,
                    "dimension": 0, "fallback": "lexical",
                    "message": self._status.get("message", "embedding indisponível")}
        return {"ok": True, "state": "ok", "model": self.MODEL_PRIMARY,
                "dimension": len(vector), "fallback": None,
                "sample_preview": [round(float(x), 3) for x in vector[:5]]}
