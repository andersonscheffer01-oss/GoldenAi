import json
import sqlite3
import threading
import time
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

class AuditLog:
    SENSITIVE = {"password", "passwd", "senha", "token", "access_token", "refresh_token",
                 "secret", "client_secret", "api_key", "apikey", "authorization", "cookie",
                 "session", "credential", "credentials"}
    PAYLOAD_KEYS = {"base64", "audio_base64", "image_base64", "screenshot_base64", "image", "audio"}
    ENVELOPE_KEY = "_audit_envelope"
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
        envelope_input = row.get("envelope")
        if envelope_input is not None:
            envelope = self._build_envelope(row, envelope_input, result)
            result = self._attach_envelope(result, envelope)
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
    def _build_envelope(cls, row, supplied, sanitized_result):
        supplied = dict(supplied or {})
        legacy_metadata = {
            field: row[field] for field in
            ("agent", "files_changed", "commands_executed") if field in row
        }
        metadata = dict(supplied.get("metadata") or {})
        metadata.update(legacy_metadata)
        return cls._sanitize({
            "event_id": supplied.get("event_id") or str(uuid.uuid4()),
            "timestamp": supplied.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "request_id": supplied.get("request_id", row.get("request_id", "")),
            "correlation_id": supplied.get("correlation_id", row.get("correlation_id", "")),
            "session_id": supplied.get("session_id", row.get("session_id", "")),
            "conversation_id": supplied.get("conversation_id", row.get("conversation_id", "")),
            "task_id": supplied.get("task_id", row.get("task_id", "")),
            "mission_id": supplied.get("mission_id", row.get("mission_id", "")),
            "run_id": supplied.get("run_id", row.get("run_id", "")),
            "approval_id": supplied.get("approval_id", row.get("approval_id", "")),
            "surface": supplied.get("surface", row.get("surface", "")),
            "operation": supplied.get("operation", row.get("operation", row.get("command", ""))),
            "action": supplied.get("action", row.get("action", row.get("command", ""))),
            "target": supplied.get("target", row.get("target", "")),
            "tool": supplied.get("tool", row.get("tool", "")),
            "provider": supplied.get("provider", row.get("provider", "")),
            "model": supplied.get("model", row.get("model", "")),
            "risk": supplied.get("risk", row.get("risk", "")),
            "security_decision": supplied.get("security_decision", row.get("security_decision", "")),
            "status": supplied.get("status", row.get("status", "")),
            "result": sanitized_result,
            "error": supplied.get("error", row.get("error", "")),
            "elapsed_ms": supplied.get("elapsed_ms", row.get("elapsed_ms", 0)),
            "runtime_profile": supplied.get("runtime_profile", row.get("runtime_profile", "")),
            "metadata": metadata,
        })

    @classmethod
    def _attach_envelope(cls, result, envelope):
        if isinstance(result, dict):
            wrapped = dict(result)
        else:
            wrapped = {"value": result}
        wrapped[cls.ENVELOPE_KEY] = envelope
        return wrapped

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
        result = []
        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(item.get("result", ""))
                if isinstance(payload, dict) and self.ENVELOPE_KEY in payload:
                    item["audit_envelope"] = payload[self.ENVELOPE_KEY]
            except (TypeError, json.JSONDecodeError):
                pass
            result.append(item)
        return result
