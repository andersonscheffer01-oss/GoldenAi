"""Configuration for the web desktop shell. No Core configuration lives here."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_STUDIO_ROOT = Path(r"C:\GoldenAI\studio\golden_ai_studio_web")


def studio_root() -> Path:
    configured = os.environ.get("GOLDEN_STUDIO_ROOT", "").strip()
    if configured:
        return Path(configured).resolve()
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent.parent
    return DEFAULT_STUDIO_ROOT


def ssl_required() -> bool:
    return os.environ.get("GOLDEN_SSL", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


def candidate_origins() -> tuple[str, ...]:
    configured = os.environ.get("GOLDEN_DESKTOP_ORIGIN", "").strip().rstrip("/")
    if configured:
        parsed = urlparse(configured)
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("GOLDEN_DESKTOP_ORIGIN deve apontar para loopback.")
        if ssl_required() and parsed.scheme != "https":
            raise ValueError("TLS está habilitado; a origem Desktop deve usar HTTPS.")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("A origem Desktop deve usar HTTP ou HTTPS.")
        return (configured,)
    if ssl_required():
        return ("https://127.0.0.1:8765",)
    # Probe HTTPS first so an already-running secure Core is always reused.
    return ("https://127.0.0.1:8765", "http://127.0.0.1:8765")


def ui_url(origin: str) -> str:
    return origin.rstrip("/") + "/jarvis_ui/jarvis.html"

