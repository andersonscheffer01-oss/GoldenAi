from __future__ import annotations

import logging
from pathlib import Path


SENSITIVE_WORDS = ("token", "senha", "password", "codigo", "code", "secret")


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for word in SENSITIVE_WORDS:
            if word.lower() in message.lower():
                record.msg = "[mensagem tecnica omitida por seguranca]"
                record.args = ()
                break
        return True


def get_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("golden_jarvis_pc_agent")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    return logger
