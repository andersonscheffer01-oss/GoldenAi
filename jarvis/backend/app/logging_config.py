from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import ROOT_DIR, get_settings


SENSITIVE_MARKERS = ("authorization", "bearer ", "device_token", "secret_key", "senha")


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return not any(marker in message for marker in SENSITIVE_MARKERS)


def configure_logging() -> None:
    settings = get_settings()
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "jarvis.log",
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handler.addFilter(SecretFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if not any(isinstance(item, RotatingFileHandler) for item in root.handlers):
        root.addHandler(handler)
