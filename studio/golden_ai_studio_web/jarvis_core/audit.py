import json
import sqlite3
import threading
import time
import re
from contextlib import contextmanager
from pathlib import Path

class AuditLog:
    SENSITIVE = {"password", "passwd", "senha", "token", "access_token", "refresh_token",
                 "secret", "client_secret", "api_key", "apikey", "authorization", "cookie",
                 "session", "credential", "credentials"}
    PAYLOAD_KEYS = {"base64", "audio_base64", "image_base64", "screenshot_base64", "image", "audio"}
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jarvis_audit (
                id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, task_id TEXT NOT NULL,
                command TEXT, tool TEXT, arguments TEXT, risk TEXT, status TEXT,
                result TEXT, elapsed_ms INTEGER)""")

    @contextmanager
    def _connect(self):
        database = sqlite3.connect(self.path, timeout=10)
        try:
            yield database
            database.commit()
        finally:
            database.close()

    def add(self, **row):
        arguments = self._sanitize(row.get("arguments", {}))
        result = self._sanitize(row.get("result", ""))
        with self.lock, self._connect() as db:
            db.execute("""INSERT INTO jarvis_audit
                (timestamp,task_id,command,tool,arguments,risk,status,result,elapsed_ms)
                VALUES (?,?,?,?,?,?,?,?,?)""", (
                time.time(), self._sanitize(row.get("task_id", "desktop"), "task_id"),
                self._sanitize(row.get("command", "")),
                row.get("tool", ""), json.dumps(arguments, ensure_ascii=False),
                row.get("risk", ""), row.get("status", ""),
                json.dumps(result, ensure_ascii=False)[:4000] if not isinstance(result, str) else result[:4000],
                row.get("elapsed_ms", 0)))

    @classmethod
    def _sanitize(cls, value, key=""):
        normalized = str(key).lower().replace("-", "_")
        if normalized in cls.SENSITIVE or any(part in cls.SENSITIVE for part in normalized.split(".")):
            return "[REDACTED]"
        if normalized in cls.PAYLOAD_KEYS:
            size = len(value) if hasattr(value, "__len__") else 0
            return {"redacted_payload": True, "size": size}
        if isinstance(value, dict):
            return {k: cls._sanitize(v, k) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._sanitize(v, key) for v in value]
        if isinstance(value, (bytes, bytearray)):
            return {"binary_payload": True, "size": len(value)}
        if isinstance(value, str) and len(value) > 2000:
            return {"large_text": True, "size": len(value), "preview": value[:160]}
        if isinstance(value, str):
            return re.sub(
                r"(?i)\b(password|passwd|senha|token|secret|api[_-]?key|authorization|cookie)"
                r"\s*[:=]\s*([^\s,;]+)",
                lambda match: f"{match.group(1)}=[REDACTED]", value)
        return value

    def recent(self, limit=20):
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM jarvis_audit ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]
