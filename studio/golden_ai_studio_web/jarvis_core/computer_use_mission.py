"""Perception-driven missions built on the existing Jarvis tools.

This module is intentionally small.  It does not own input, vision, UIA,
security, or audit infrastructure; it coordinates those existing boundaries
one step at a time and stops when a confirmation or fresh observation is
required.
"""
from __future__ import annotations

import re
import base64
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .browser import (MAX_SEARCH_PROVIDERS, SEARCH_PROVIDER_ORDER,
                      SEARCH_PROVIDER_URLS, classify_page_barrier)
from .security import (COMPUTER_USE_MISSION_PRE_SAVE,
                       READ_ONLY_PUBLIC_BROWSER_OBSERVATION)
from .windows_known_folders import documents_dir as known_documents_dir


DEFAULT_SEARCH_HOME = SEARCH_PROVIDER_URLS[SEARCH_PROVIDER_ORDER[0]]


class MissionStatus(str, Enum):
    PENDING = "PENDING"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    PAUSED = "PAUSED"
    WAITING_FOR_USER_IDLE = "WAITING_FOR_USER_IDLE"
    RESUMING = "RESUMING"
    RECOVERING = "RECOVERING"
    CANCELLED = "CANCELLED"


class MissionStepStatus(str, Enum):
    PENDING = "PENDING"
    OBSERVING = "OBSERVING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    CANCELLED = "CANCELLED"


class CheckpointState(str, Enum):
    PENDING = "CHECKPOINT_PENDING"
    WRITING = "CHECKPOINT_WRITING"
    VALID = "CHECKPOINT_VALID"
    FAILED = "CHECKPOINT_FAILED"


class ActionState(str, Enum):
    NOT_STARTED = "ACTION_NOT_STARTED"
    IN_FLIGHT_UNKNOWN = "ACTION_IN_FLIGHT_UNKNOWN"
    VERIFIED = "ACTION_VERIFIED"
    FAILED = "ACTION_FAILED"


class WorldStateChangeType(str, Enum):
    VALID = "WORLD_STATE_VALID"
    APP_CLOSED = "APP_CLOSED"
    WINDOW_MISSING = "WINDOW_MISSING"
    WINDOW_EXISTS_BACKGROUND = "WINDOW_EXISTS_BACKGROUND"
    WINDOW_EXISTS_BACKGROUND_RECOVERABLE = "WINDOW_EXISTS_BACKGROUND_RECOVERABLE"
    WINDOW_EXISTS_BACKGROUND_USER_ACTIVE = "WINDOW_EXISTS_BACKGROUND_USER_ACTIVE"
    WINDOW_EXISTS_BACKGROUND_UNKNOWN = "WINDOW_EXISTS_BACKGROUND_UNKNOWN"
    WINDOW_MINIMIZED = "WINDOW_MINIMIZED"
    WINDOW_OCCLUDED = "WINDOW_OCCLUDED"
    FOREGROUND_CONTENTION = "FOREGROUND_CONTENTION"
    DOCUMENT_MISSING = "DOCUMENT_MISSING"
    PAGE_CHANGED = "PAGE_CHANGED"
    FILE_STATE_CHANGED = "FILE_STATE_CHANGED"
    TARGET_CHANGED = "TARGET_CHANGED"
    UNKNOWN = "UNKNOWN_STATE_CHANGE"


CHECKPOINT_SCHEMA_VERSION = 1
MISSION_STORE_SCHEMA_VERSION = 1
DEFAULT_RESUME_QUIET_WINDOW_MS = max(
    500, int(os.getenv("JARVIS_RESUME_QUIET_WINDOW_MS", "1500")))
DEFAULT_RESUME_MAX_WAIT_MS = max(
    DEFAULT_RESUME_QUIET_WINDOW_MS,
    int(os.getenv("JARVIS_RESUME_MAX_WAIT_MS", "30000")))
_CHECKPOINT_RUNTIME_KEYS = {
    "bounds", "center", "handle", "window_id", "pid", "process_id",
    "identity", "runtime_id", "coordinate_mapping_verified", "screenshot",
    "image", "audio", "token", "pending_confirmation_token", "cookies",
    "browser_profile", "clipboard",
}


def _checkpoint_safe(value: Any, key: str = "") -> Any:
    """Keep checkpoint data logical and exclude UI/runtime credentials."""
    if str(key).casefold() in _CHECKPOINT_RUNTIME_KEYS:
        return None
    if isinstance(value, dict):
        return {str(k): safe for k, raw in value.items()
                if (safe := _checkpoint_safe(raw, str(k))) is not None}
    if isinstance(value, (list, tuple)):
        return [_checkpoint_safe(item, key) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _resolved_result_url(raw_url: str) -> str:
    """Resolve common search-provider redirects without trusting page text."""
    value = str(raw_url or "").strip()
    parsed = urlparse(value)
    encoded = parse_qs(parsed.query).get("u", [""])[0]
    if encoded.startswith("a1"):
        try:
            decoded = base64.urlsafe_b64decode(encoded[2:] + "===").decode("utf-8")
            if urlparse(decoded).scheme in {"http", "https"}:
                return decoded
        except (ValueError, UnicodeError):
            pass
    return value


@dataclass
class MissionValue:
    """A short-lived observed/user/derived value owned by one mission."""

    value: str
    mission_id: str
    kind: str
    source_app: str = ""
    source_type: str = ""
    source_title: str = ""
    source_url: str = ""
    observed_at: float = field(default_factory=time.time)
    confidence: str = "verified"
    context_version: int = 0
    source_state_id: str = ""
    valid_until_step: Optional[int] = None
    invalidated: bool = False

    def public(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "kind": self.kind,
            "source_app": self.source_app,
            "source_type": self.source_type,
            "source_title": self.source_title,
            "source_url": self.source_url,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "context_version": self.context_version,
            "source_state_id": self.source_state_id,
            "valid_until_step": self.valid_until_step,
            "invalidated": self.invalidated,
        }


@dataclass
class MissionContext:
    """Transient cross-application state; never the Jarvis long-term memory."""

    mission_id: str
    user_request: str
    current_app: str = ""
    previous_app: str = ""
    variables: dict[str, MissionValue] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    context_version: int = 0
    app_switches: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def store_variable(self, name: str, value: str, *, kind: str,
                       source_app: str = "", source_type: str = "",
                       source_title: str = "", source_url: str = "",
                       confidence: str = "verified", source_state_id: str = "",
                       valid_until_step: Optional[int] = None) -> MissionValue:
        self.context_version += 1
        stored = MissionValue(
            value=str(value), mission_id=self.mission_id, kind=kind,
            source_app=source_app, source_type=source_type,
            source_title=source_title, source_url=source_url,
            confidence=confidence, context_version=self.context_version,
            source_state_id=source_state_id, valid_until_step=valid_until_step,
        )
        self.variables[str(name)] = stored
        self.source_provenance[str(name)] = stored.public()
        self.updated_at = time.time()
        return stored

    def resolve(self, name: str, *, mission_id: str,
                current_step: int) -> tuple[Optional[MissionValue], str]:
        stored = self.variables.get(str(name))
        if stored is None:
            return None, "MISSING_MISSION_VARIABLE"
        if stored.mission_id != mission_id or stored.invalidated:
            return None, "STALE_CONTEXT_DETECTED"
        if (stored.valid_until_step is not None and
                current_step > stored.valid_until_step):
            return None, "STALE_CONTEXT_DETECTED"
        return stored, ""

    def invalidate(self, name: str, reason: str = "") -> bool:
        stored = self.variables.get(str(name))
        if stored is None:
            return False
        stored.invalidated = True
        self.context_version += 1
        self.updated_at = time.time()
        self.artifacts.setdefault("invalidations", {})[str(name)] = {
            "reason": reason, "context_version": self.context_version,
        }
        return True

    def public(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "user_request": self.user_request,
            "current_app": self.current_app,
            "previous_app": self.previous_app,
            "variables": {key: value.public() for key, value in self.variables.items()},
            "artifacts": dict(self.artifacts),
            "step_outputs": dict(self.step_outputs),
            "source_provenance": dict(self.source_provenance),
            "context_version": self.context_version,
            "app_switches": self.app_switches,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def checkpoint_snapshot(self) -> dict[str, Any]:
        """Serialize only logical mission context for durable checkpoints."""
        return _checkpoint_safe(self.public())

    @classmethod
    def from_checkpoint(cls, snapshot: dict[str, Any], mission_id: str,
                        user_request: str) -> "MissionContext":
        context = cls(mission_id, user_request)
        context.current_app = str(snapshot.get("current_app") or "")
        context.previous_app = str(snapshot.get("previous_app") or "")
        context.artifacts = dict(snapshot.get("artifacts") or {})
        context.step_outputs = dict(snapshot.get("step_outputs") or {})
        context.source_provenance = dict(snapshot.get("source_provenance") or {})
        context.context_version = int(snapshot.get("context_version") or 0)
        context.app_switches = int(snapshot.get("app_switches") or 0)
        context.created_at = float(snapshot.get("created_at") or time.time())
        context.updated_at = float(snapshot.get("updated_at") or time.time())
        for name, raw in dict(snapshot.get("variables") or {}).items():
            value = str(raw.get("value") or "")
            context.variables[str(name)] = MissionValue(
                value=value, mission_id=mission_id,
                kind=str(raw.get("kind") or "OBSERVED_VALUE"),
                source_app=str(raw.get("source_app") or ""),
                source_type=str(raw.get("source_type") or ""),
                source_title=str(raw.get("source_title") or ""),
                source_url=str(raw.get("source_url") or ""),
                observed_at=float(raw.get("observed_at") or time.time()),
                confidence=str(raw.get("confidence") or "verified"),
                context_version=int(raw.get("context_version") or 0),
                source_state_id=str(raw.get("source_state_id") or ""),
                valid_until_step=raw.get("valid_until_step"),
                invalidated=bool(raw.get("invalidated", False)),
            )
        if context.context_version != int(snapshot.get("context_version") or 0):
            raise ValueError("CHECKPOINT_CONTEXT_MISMATCH")
        return context


@dataclass
class ComputerMissionStep:
    step_id: str
    description: str
    action_type: str
    target: str = ""
    expected_state: dict[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    app: str = ""
    status: MissionStepStatus = MissionStepStatus.PENDING
    attempts: int = 0
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    requires: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    max_attempts: int = 3


@dataclass
class ComputerMission:
    mission_id: str
    user_request: str
    status: MissionStatus
    created_at: float
    steps: list[ComputerMissionStep]
    current_step: int = 0
    max_steps: int = 30
    timeout_seconds: float = 300.0
    requires_confirmation: bool = True
    risk_level: str = "WRITE"
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    pending_confirmation_token: str = ""
    context: Optional[MissionContext] = None

    def __post_init__(self):
        if self.context is None:
            self.context = MissionContext(self.mission_id, self.user_request)

    def public(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "user_request": self.user_request,
            "status": self.status.value,
            "created_at": self.created_at,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "timeout_seconds": self.timeout_seconds,
            "requires_confirmation": self.requires_confirmation,
            "risk_level": self.risk_level,
            "result": dict(self.result),
            "error": self.error,
            "pending_confirmation": bool(self.pending_confirmation_token),
            "resume_token": str(self.result.get("resume_token") or ""),
            "progress": self.progress(),
            "context": self.context.public() if self.context else {},
            "steps": [
                {
                    "step_id": step.step_id,
                    "description": step.description,
                    "action_type": step.action_type,
                    "target": step.target,
                    "expected_state": dict(step.expected_state),
                    "app": step.app,
                    "status": step.status.value,
                    "attempts": step.attempts,
                    "result": dict(step.result),
                    "error": step.error,
                    "requires": list(step.requires),
                    "produces": list(step.produces),
                    "max_attempts": step.max_attempts,
                }
                for step in self.steps
            ],
        }

    def progress(self) -> dict[str, Any]:
        total = len(self.steps)
        completed = sum(step.status is MissionStepStatus.COMPLETED
                        for step in self.steps)
        current = self.steps[self.current_step] if self.current_step < total else None
        return {
            "completed_steps": completed,
            "total_steps": total,
            "ratio": round(completed / total, 3) if total else 1.0,
            "current_phase": (current.description if current else "Complete"),
        }


class MissionCheckpointStore:
    """Small checkpoint/receipt adapter over the existing TaskDatabase."""

    def __init__(self, task_database=None):
        self.database = task_database
        self._memory_checkpoints: dict[str, dict[str, Any]] = {}
        self._memory_missions: dict[str, dict[str, Any]] = {}
        self._memory_receipts: dict[tuple[str, str], dict[str, Any]] = {}
        if self.database is not None:
            self._ensure_schema()

    def _ensure_schema(self):
        with getattr(self.database, "_lock", threading.RLock()):
            with self.database.connect() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS mission_checkpoint_schema("
                    "version INTEGER NOT NULL)"
                )
                row = db.execute(
                    "SELECT version FROM mission_checkpoint_schema "
                    "ORDER BY version DESC LIMIT 1"
                ).fetchone()
                db.execute(
                    "CREATE TABLE IF NOT EXISTS mission_checkpoints("
                    "checkpoint_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,"
                    "mission_version INTEGER NOT NULL, created_at REAL NOT NULL,"
                    "name TEXT NOT NULL, state TEXT NOT NULL, pause_reason TEXT NOT NULL,"
                    "current_step INTEGER NOT NULL, next_step INTEGER NOT NULL,"
                    "context_revision INTEGER NOT NULL, schema_version INTEGER NOT NULL,"
                    "snapshot TEXT NOT NULL, integrity_hash TEXT NOT NULL)"
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mission_checkpoints_mission "
                    "ON mission_checkpoints(mission_id, created_at)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS mission_action_receipts("
                    "action_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,"
                    "step_id TEXT NOT NULL, action_type TEXT NOT NULL, target TEXT NOT NULL,"
                    "started_at REAL NOT NULL, verified_at REAL, result_state TEXT NOT NULL,"
                    "result TEXT NOT NULL, UNIQUE(mission_id, step_id))"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS mission_records("
                    "mission_id TEXT PRIMARY KEY, mission_type TEXT NOT NULL,"
                    "user_request TEXT NOT NULL, status TEXT NOT NULL,"
                    "created_at REAL NOT NULL, updated_at REAL NOT NULL,"
                    "current_step INTEGER NOT NULL, next_step INTEGER NOT NULL,"
                    "checkpoint_id TEXT, context_revision INTEGER NOT NULL,"
                    "pause_reason TEXT NOT NULL, schema_version INTEGER NOT NULL,"
                    "snapshot TEXT NOT NULL, integrity_hash TEXT NOT NULL)"
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mission_records_status "
                    "ON mission_records(status, updated_at)"
                )
                if not row or int(row[0]) < CHECKPOINT_SCHEMA_VERSION:
                    db.execute("DELETE FROM mission_checkpoint_schema")
                    db.execute(
                        "INSERT INTO mission_checkpoint_schema(version) VALUES(?)",
                        (CHECKPOINT_SCHEMA_VERSION,))

    @staticmethod
    def _canonical(snapshot: dict[str, Any]) -> str:
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    @classmethod
    def _integrity_hash(cls, checkpoint_id: str, mission_id: str,
                        snapshot: dict[str, Any]) -> str:
        payload = f"{CHECKPOINT_SCHEMA_VERSION}:{checkpoint_id}:{mission_id}:" \
                  f"{cls._canonical(snapshot)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _mission_integrity_hash(cls, mission_id: str,
                                snapshot: dict[str, Any]) -> str:
        payload = f"{MISSION_STORE_SCHEMA_VERSION}:{mission_id}:" \
                  f"{cls._canonical(snapshot)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save_mission(self, *, mission_id: str, mission_type: str,
                     user_request: str, status: str, created_at: float,
                     updated_at: float, current_step: int, next_step: int,
                     checkpoint_id: str, context_revision: int,
                     pause_reason: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Upsert one logical mission record in the existing task database."""
        safe_snapshot = _checkpoint_safe(snapshot)
        record = {
            "mission_id": str(mission_id),
            "mission_type": str(mission_type or "computer_use"),
            "user_request": str(user_request or ""),
            "status": str(status),
            "created_at": float(created_at),
            "updated_at": float(updated_at),
            "current_step": int(current_step),
            "next_step": int(next_step),
            "checkpoint_id": str(checkpoint_id or ""),
            "context_revision": int(context_revision),
            "pause_reason": str(pause_reason or ""),
            "schema_version": MISSION_STORE_SCHEMA_VERSION,
            "snapshot": safe_snapshot,
        }
        record["integrity_hash"] = self._mission_integrity_hash(
            record["mission_id"], safe_snapshot)
        if self.database is None:
            self._memory_missions[record["mission_id"]] = record
            return dict(record)
        self._ensure_schema()
        values = (
            record["mission_id"], record["mission_type"], record["user_request"],
            record["status"], record["created_at"], record["updated_at"],
            record["current_step"], record["next_step"], record["checkpoint_id"],
            record["context_revision"], record["pause_reason"],
            record["schema_version"], self._canonical(safe_snapshot),
            record["integrity_hash"],
        )
        with getattr(self.database, "_lock", threading.RLock()):
            with self.database.connect() as db:
                existing = db.execute(
                    "SELECT mission_id FROM mission_records WHERE mission_id=?",
                    (record["mission_id"],)).fetchone()
                if existing:
                    db.execute(
                        "UPDATE mission_records SET mission_type=?,user_request=?,"
                        "status=?,created_at=?,updated_at=?,current_step=?,next_step=?,"
                        "checkpoint_id=?,context_revision=?,pause_reason=?,"
                        "schema_version=?,snapshot=?,integrity_hash=? WHERE mission_id=?",
                        values[1:] + (record["mission_id"],))
                else:
                    db.execute(
                        "INSERT INTO mission_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        values)
        return dict(record)

    def load_mission(self, mission_id: str) -> tuple[Optional[dict[str, Any]], str]:
        if self.database is None:
            record = self._memory_missions.get(str(mission_id))
        else:
            self._ensure_schema()
            with self.database.connect(rows=True) as db:
                record = db.execute(
                    "SELECT * FROM mission_records WHERE mission_id=?",
                    (str(mission_id),)).fetchone()
            record = dict(record) if record else None
        if record is None:
            return None, "MISSION_NOT_FOUND"
        record = dict(record)
        try:
            record["snapshot"] = (record["snapshot"] if
                                   isinstance(record.get("snapshot"), dict) else
                                   json.loads(record.get("snapshot") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, "MISSION_RECORD_INVALID"
        if int(record.get("schema_version") or 0) != MISSION_STORE_SCHEMA_VERSION:
            return None, "MISSION_RECORD_INVALID"
        if self._mission_integrity_hash(str(record["mission_id"]),
                                        record["snapshot"]) != record.get("integrity_hash"):
            return None, "MISSION_RECORD_INVALID"
        return record, ""

    def save_checkpoint(self, *, mission_id: str, mission_version: int,
                        name: str, current_step: int, next_step: int,
                        context_revision: int, snapshot: dict[str, Any],
                        pause_reason: str = "",
                        state: CheckpointState = CheckpointState.VALID,
                        mission_record: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        checkpoint_id = str(uuid.uuid4())
        safe_snapshot = _checkpoint_safe(snapshot)
        created_at = time.time()
        if mission_record is None:
            mission_record = {
                "mission_id": str(mission_id),
                "mission_type": "computer_use",
                "user_request": str(safe_snapshot.get("user_request") or ""),
                "status": str(safe_snapshot.get("status") or MissionStatus.PENDING.value),
                "created_at": created_at,
                "updated_at": created_at,
                "current_step": int(current_step),
                "next_step": int(next_step),
                "context_revision": int(context_revision),
                "pause_reason": str(pause_reason or ""),
                "snapshot": safe_snapshot,
            }
        digest = self._integrity_hash(checkpoint_id, mission_id, safe_snapshot)
        record = {
            "checkpoint_id": checkpoint_id,
            "mission_id": mission_id,
            "mission_version": int(mission_version),
            "created_at": created_at,
            "name": str(name),
            "state": CheckpointState.WRITING.value,
            "pause_reason": str(pause_reason or ""),
            "current_step": int(current_step),
            "next_step": int(next_step),
            "context_revision": int(context_revision),
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "snapshot": safe_snapshot,
            "integrity_hash": digest,
        }
        if self.database is None:
            record["state"] = state.value
            self._memory_checkpoints[checkpoint_id] = record
            if mission_record:
                stored = dict(mission_record)
                stored["checkpoint_id"] = checkpoint_id
                self.save_mission(**stored)
        else:
            self._ensure_schema()
            with getattr(self.database, "_lock", threading.RLock()):
                with self.database.connect() as db:
                    db.execute(
                        "INSERT INTO mission_checkpoints VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (checkpoint_id, mission_id, int(mission_version), created_at,
                         str(name), CheckpointState.WRITING.value,
                         str(pause_reason or ""), int(current_step), int(next_step),
                         int(context_revision), CHECKPOINT_SCHEMA_VERSION,
                         self._canonical(safe_snapshot), digest),
                    )
                    db.execute(
                        "UPDATE mission_checkpoints SET state=? WHERE checkpoint_id=?",
                        (state.value, checkpoint_id),
                    )
                    if mission_record:
                        stored = dict(mission_record)
                        stored["checkpoint_id"] = checkpoint_id
                        safe_mission = _checkpoint_safe(stored.get("snapshot") or {})
                        mission_digest = self._mission_integrity_hash(
                            str(stored["mission_id"]), safe_mission)
                        mission_values = (
                            str(stored["mission_id"]),
                            str(stored.get("mission_type") or "computer_use"),
                            str(stored.get("user_request") or ""),
                            str(stored.get("status") or MissionStatus.PENDING.value),
                            float(stored.get("created_at") or created_at),
                            float(stored.get("updated_at") or created_at),
                            int(stored.get("current_step") or 0),
                            int(stored.get("next_step") or 0),
                            checkpoint_id,
                            int(stored.get("context_revision") or 0),
                            str(stored.get("pause_reason") or ""),
                            MISSION_STORE_SCHEMA_VERSION,
                            self._canonical(safe_mission), mission_digest,
                        )
                        existing = db.execute(
                            "SELECT mission_id FROM mission_records WHERE mission_id=?",
                            (mission_values[0],)).fetchone()
                        if existing:
                            db.execute(
                                "UPDATE mission_records SET mission_type=?,user_request=?,"
                                "status=?,created_at=?,updated_at=?,current_step=?,next_step=?,"
                                "checkpoint_id=?,context_revision=?,pause_reason=?,"
                                "schema_version=?,snapshot=?,integrity_hash=? WHERE mission_id=?",
                                mission_values[1:] + (mission_values[0],))
                        else:
                            db.execute(
                                "INSERT INTO mission_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                mission_values)
            record["state"] = state.value
        record["resume_token"] = f"{mission_id}:{checkpoint_id}"
        return record

    def _row_record(self, row) -> Optional[dict[str, Any]]:
        if row is None:
            return None
        if isinstance(row, dict):
            record = dict(row)
        else:
            record = dict(row)
        if not isinstance(record.get("snapshot"), dict):
            try:
                record["snapshot"] = json.loads(record.get("snapshot") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
        required = {"checkpoint_id", "mission_id", "snapshot", "integrity_hash",
                    "schema_version", "context_revision", "state"}
        if not required.issubset(record) or int(record["schema_version"]) != CHECKPOINT_SCHEMA_VERSION:
            return None
        if record["state"] != CheckpointState.VALID.value:
            return None
        if self._integrity_hash(record["checkpoint_id"], record["mission_id"],
                                record["snapshot"]) != record["integrity_hash"]:
            return None
        context = record["snapshot"].get("context") or {}
        if int(record["context_revision"]) != int(context.get("context_version") or 0):
            return None
        record["resume_token"] = f"{record['mission_id']}:{record['checkpoint_id']}"
        return record

    def load(self, checkpoint_id: str, mission_id: str = "") -> tuple[Optional[dict[str, Any]], str]:
        if self.database is None:
            record = self._memory_checkpoints.get(str(checkpoint_id))
            if record is None:
                return None, "CHECKPOINT_NOT_FOUND"
            validated = self._row_record(record)
        else:
            self._ensure_schema()
            with self.database.connect(rows=True) as db:
                row = db.execute(
                    "SELECT * FROM mission_checkpoints WHERE checkpoint_id=?",
                    (str(checkpoint_id),)).fetchone()
            validated = self._row_record(row)
        if validated is None:
            return None, "CHECKPOINT_INVALID"
        if mission_id and validated["mission_id"] != str(mission_id):
            return None, "RESUME_MISSION_MISMATCH"
        return validated, ""

    def load_resume_token(self, token: str) -> tuple[Optional[dict[str, Any]], str]:
        parts = str(token or "").split(":", 1)
        if len(parts) != 2 or not all(parts):
            return None, "RESUME_TOKEN_INVALID"
        mission_id, checkpoint_id = parts
        checkpoint, error = self.load(checkpoint_id, mission_id)
        if error:
            return None, "RESUME_TOKEN_NOT_FOUND" if error in {
                "CHECKPOINT_NOT_FOUND", "CHECKPOINT_INVALID",
                "RESUME_MISSION_MISMATCH"} else error
        mission, mission_error = self.load_mission(mission_id)
        if mission_error:
            return None, "RESUME_TOKEN_NOT_FOUND"
        checkpoint["mission_record"] = mission
        return checkpoint, ""

    def latest(self, mission_id: str) -> tuple[Optional[dict[str, Any]], str]:
        if self.database is None:
            records = [item for item in self._memory_checkpoints.values()
                       if item.get("mission_id") == str(mission_id)]
            row = max(records, key=lambda item: item.get("created_at", 0), default=None)
            return (self._row_record(row), "" if row else "CHECKPOINT_NOT_FOUND")
        self._ensure_schema()
        with self.database.connect(rows=True) as db:
            row = db.execute(
                "SELECT * FROM mission_checkpoints WHERE mission_id=? "
                "AND state=? ORDER BY created_at DESC LIMIT 1",
                (str(mission_id), CheckpointState.VALID.value)).fetchone()
        validated = self._row_record(row)
        return validated, "" if validated else "CHECKPOINT_NOT_FOUND"

    def save_receipt(self, *, mission_id: str, step_id: str,
                     action_type: str, target: str, result_state: ActionState,
                     result: Optional[dict[str, Any]] = None,
                     started_at: Optional[float] = None,
                     verified_at: Optional[float] = None) -> dict[str, Any]:
        started = float(started_at or time.time())
        receipt = {
            "action_id": str(uuid.uuid4()), "mission_id": str(mission_id),
            "step_id": str(step_id), "action_type": str(action_type),
            "target": str(target or ""), "started_at": started,
            "verified_at": verified_at, "result_state": result_state.value,
            "result": _checkpoint_safe(result or {}),
        }
        if self.database is None:
            old = self._memory_receipts.get((str(mission_id), str(step_id)))
            if old:
                receipt["action_id"] = old["action_id"]
            self._memory_receipts[(str(mission_id), str(step_id))] = receipt
            return receipt
        self._ensure_schema()
        with getattr(self.database, "_lock", threading.RLock()):
            with self.database.connect() as db:
                old = db.execute(
                    "SELECT action_id FROM mission_action_receipts "
                    "WHERE mission_id=? AND step_id=?",
                    (str(mission_id), str(step_id))).fetchone()
                if old:
                    receipt["action_id"] = old[0]
                    db.execute(
                        "UPDATE mission_action_receipts SET action_type=?,target=?,"
                        "started_at=?,verified_at=?,result_state=?,result=? "
                        "WHERE action_id=?",
                        (receipt["action_type"], receipt["target"], receipt["started_at"],
                         receipt["verified_at"], receipt["result_state"],
                         json.dumps(receipt["result"], ensure_ascii=False), receipt["action_id"]))
                else:
                    db.execute(
                        "INSERT INTO mission_action_receipts VALUES(?,?,?,?,?,?,?,?,?)",
                        (receipt["action_id"], receipt["mission_id"], receipt["step_id"],
                         receipt["action_type"], receipt["target"], receipt["started_at"],
                         receipt["verified_at"], receipt["result_state"],
                         json.dumps(receipt["result"], ensure_ascii=False)))
        return receipt

    def receipt(self, mission_id: str, step_id: str) -> Optional[dict[str, Any]]:
        if self.database is None:
            return self._memory_receipts.get((str(mission_id), str(step_id)))
        self._ensure_schema()
        with self.database.connect(rows=True) as db:
            row = db.execute(
                "SELECT * FROM mission_action_receipts WHERE mission_id=? AND step_id=?",
                (str(mission_id), str(step_id))).fetchone()
        if not row:
            return None
        record = dict(row)
        try:
            record["result"] = json.loads(record.get("result") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            record["result"] = {}
        return record

    def receipts_for_mission(self, mission_id: str) -> list[dict[str, Any]]:
        if self.database is None:
            return [dict(item) for (stored_mission, _), item in
                    self._memory_receipts.items()
                    if stored_mission == str(mission_id)]
        self._ensure_schema()
        with self.database.connect(rows=True) as db:
            rows = db.execute(
                "SELECT * FROM mission_action_receipts WHERE mission_id=?",
                (str(mission_id),)).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            try:
                record["result"] = json.loads(record.get("result") or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                record["result"] = {}
            records.append(record)
        return records


class ComputerMissionPlanner:
    """Create bounded plans using only tools present in the shared registry."""

    MAX_STEPS = 30
    _NOTEPAD_RE = re.compile(r"\b(bloco\s+de\s+notas|notepad)\b", re.I)
    _BROWSER_RE = re.compile(r"\b(navegador|browser|chrome|edge)\b", re.I)
    _DIRECT_TITLE_RE = re.compile(r"\bt[ií]tulo\b.*\bpython\.org\b|\bpython\.org\b.*\bt[ií]tulo\b", re.I | re.S)
    _SAVE_RE = re.compile(r"\bsalv(?:e|ar|a)\s+(?:como\s+)?([\w.-]+)", re.I)
    _MULTI_APP_RE = re.compile(
        r"(?:chrome|navegador|ollama|página\s+oficial).*(?:bloco\s+de\s+notas|notepad).*"
        r"(?:salv|escrev|digit)", re.I | re.S)

    def __init__(self, registry, documents_dir: Optional[Path] = None):
        self.registry = registry
        self._documents_dir_override = Path(documents_dir) if documents_dir else None

    def resolve_documents_dir(self) -> Path:
        return (self._documents_dir_override if self._documents_dir_override is not None
                else known_documents_dir())

    def resolve_target_path(self, filename: str) -> Path:
        """Resolve a mission filename against the current Known Folder."""
        return self.resolve_documents_dir() / Path(filename).name

    def can_plan(self, request: str) -> bool:
        text = str(request or "")
        low = text.casefold()
        if self._is_multi_app_request(text):
            return True
        if self._DIRECT_TITLE_RE.search(text) and self._BROWSER_RE.search(text):
            return True
        if self._BROWSER_RE.search(text):
            return bool(re.search(r"\b(pesquis|buscar|busque|procure)\w*\b", low))
        return bool(self._NOTEPAD_RE.search(text) and
                    re.search(r"\b(escrev|digit|salv|confirme|funcionando)\w*\b", low))

    def plan(self, request: str) -> ComputerMission:
        if not self.can_plan(request):
            raise ValueError("Missão Computer Use não reconhecida.")
        text = str(request).strip()
        if self._is_multi_app_request(text):
            if "ollama" in text.casefold() and "python" in text.casefold():
                return self._plan_long_research(text)
            return self._plan_multi_app(text)
        if self._DIRECT_TITLE_RE.search(text):
            return self._plan_direct_title(text)
        if self._BROWSER_RE.search(text):
            return self._plan_browser_search(text)
        match = self._SAVE_RE.search(text)
        filename = match.group(1) if match else "teste.txt"
        filename = Path(filename).name
        if not filename or filename in {".", ".."}:
            raise ValueError("Nome de arquivo inválido para a missão.")
        target_path = self.resolve_target_path(filename)
        content_match = re.search(
            r"\b(?:escrev|digite|digitar)\s+(.+?)(?=\s*,?\s*(?:salv|confirme|e\s+salv)|$)",
            text, re.I)
        content = (content_match.group(1).strip(" \t,\"'")
                   if content_match else "Golden Jarvis funcionando")

        tool_names = {
            "open_program", "ui_active_window", "ui_focus_window", "ui_focus_element",
            "ui_dismiss_path_not_found", "keyboard_type", "keyboard_hotkey", "keyboard_press",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None,
                 app="", requires=(), produces=(), max_attempts=3):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {}, app=app,
                                       requires=tuple(requires), produces=tuple(produces),
                                       max_attempts=max_attempts)

        steps = [
            step("open-notepad", "Abrir o Bloco de Notas", "open_program",
                  target="Bloco de Notas", args={"name": "bloco de notas"}),
            step("focus-notepad", "Focar a janela do Bloco de Notas", "ui_focus_window",
                  target="notepad", expected={"process": "notepad"},
                  args={"window": "notepad"}),
            step("new-notepad-document", "Abrir uma nova aba em branco", "keyboard_hotkey",
                  target="notepad", expected={"process": "notepad"},
                  args={"keys": ["ctrl", "n"]}),
            step("observe-notepad", "Confirmar a janela correta", "observe_window",
                  target="notepad", expected={"process": "notepad"}),
            step("type-content", "Escrever o conteúdo solicitado", "keyboard_type",
                  target="notepad-editor", expected={"process": "notepad"},
                  args={"text": content, "interval": 0.03}),
            step("open-save-dialog", "Abrir o diálogo Salvar como", "keyboard_hotkey",
                  target="save-dialog", expected={"process": "notepad"},
                  args={"keys": ["ctrl", "shift", "s"]}),
            step("observe-save-dialog", "Confirmar o diálogo de salvamento", "observe_window",
                  target="save-dialog", expected={"title": ("save as", "salvar como"),
                                                   "process": "notepad"}),
            step("focus-file-name", "Focar o campo de nome do arquivo", "ui_focus_element",
                  target="file-name", expected={"control_type": "Edit"},
                  args={"target": "", "control_type": "Edit", "window": ""}),
            step("type-file-name", "Informar o nome do arquivo", "keyboard_type",
                  target="file-name", expected={"title": ("save as", "salvar como")},
                  args={"text": str(target_path), "interval": 0.03}),
            step("confirm-save", "Confirmar o salvamento", "keyboard_press",
                  target="save-dialog", expected={"title": ("save as", "salvar como")},
                  args={"key": "enter"}),
            step("observe-saved-window", "Confirmar o retorno ao Bloco de Notas",
                  "observe_window", target="notepad",
                  expected={"process": "notepad"}),
            step("verify-file", "Verificar existência e conteúdo no filesystem",
                  "verify_file", target=str(target_path),
                  expected={"path": str(target_path), "content": content}),
        ]
        return ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                               time.time(), steps, max_steps=self.MAX_STEPS)

    def _plan_direct_title(self, text: str) -> ComputerMission:
        """Plan a read-only direct official-page title observation."""
        tool_names = {
            "browser_open", "browser_navigate", "browser_health", "browser_get_page_info",
            "ui_active_window", "ui_focus_window", "browser_record_window",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None,
                 app="chrome"):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {}, app=app)

        steps = [
            step("open-browser", "Abrir Google Chrome visível", "browser_open", "browser",
                 args={"visible": True, "provider": "chrome"}),
            step("navigate-official-python", "Acessar a página oficial do Python",
                 "browser_navigate", "https://www.python.org/",
                 args={"url": "https://www.python.org/"}),
            step("focus-browser", "Confirmar foco no Google Chrome", "focus_browser", "browser",
                 expected={"browser_process": True}),
            step("observe-browser", "Validar sessão e página oficial", "observe_browser", "browser",
                 expected={"browser_process": True}),
            step("extract-python-title", "Observar o título da página oficial",
                 "extract_mission_value", "browser-page",
                 args={"source_variable": "python_page_title", "value_kind": "title"}),
        ]
        mission = ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                                  time.time(), steps, max_steps=self.MAX_STEPS,
                                  requires_confirmation=False, risk_level="LOW")
        mission.result.update({
            "browser_mission": True,
            "direct_official_navigation": True,
            "authorization_scope": READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
            "official_host": "www.python.org",
            "source_url": "https://www.python.org/",
            "value_key": "python_page_title",
            "search_provider": "chrome",
        })
        return mission

    def _is_multi_app_request(self, text: str) -> bool:
        low = str(text or "").casefold()
        return bool(self._MULTI_APP_RE.search(text) and "document" in low)

    def _plan_multi_app(self, text: str) -> ComputerMission:
        low = text.casefold()
        title_mode = bool(re.search(r"t[ií]tulo", low))
        ollama_mode = "ollama" in low
        value_key = ("ollama_page_title" if ollama_mode and title_mode else
                     "python_page_title" if title_mode else "python_version")
        query = ("Ollama official homepage" if ollama_mode else
                 "Python official homepage Python.org" if title_mode else
                 "current stable Python version official Python")
        template = ("{{ollama_page_title}}" if ollama_mode and title_mode else
                    "{{python_page_title}}" if title_mode else
                    "Versão atual do Python: {{python_version}}")
        match = re.search(r"\bsalv(?:e|ar|a)\s+(?:como\s+)?([\w.-]+)", text, re.I)
        filename = Path(match.group(1)).name if match else (
            "tarefa_7d.txt" if ollama_mode else
            "titulo_python.txt" if title_mode else "pesquisa_python.txt")
        if not filename or filename in {".", ".."}:
            raise ValueError("Nome de arquivo inválido para a missão multiaplicativo.")
        target_path = self.resolve_target_path(filename)
        tool_names = {
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "browser_click",
            "browser_record_window", "browser_wait_for_results", "ui_active_window",
            "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
            "ui_invoke_element", "ui_classify_dialog", "ui_list_elements",
            "open_program", "keyboard_type",
            "keyboard_hotkey", "keyboard_press",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None,
                 app="", requires=(), produces=(), max_attempts=3):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {}, app=app,
                                       requires=tuple(requires), produces=tuple(produces),
                                       max_attempts=max_attempts)

        steps = [
            step("open-browser", "Abrir Google Chrome", "browser_open", "browser",
                  args={"visible": True, "provider": "chrome"}, app="chrome"),
            step("navigate-search-home", "Abrir a página de pesquisa", "browser_navigate",
                  DEFAULT_SEARCH_HOME, args={"url": DEFAULT_SEARCH_HOME}, app="chrome"),
            step("focus-browser", "Validar foco do Chrome", "focus_browser", "browser",
                  expected={"browser_process": True}, app="chrome"),
            step("observe-browser", "Validar identidade do Chrome", "observe_browser", "browser",
                  expected={"browser_process": True}, app="chrome"),
            step("ground-search-field", "Localizar campo de pesquisa", "ground_search_field",
                  "search-field", app="chrome"),
            step("execute-search", "Pesquisar o dado solicitado", "browser_search",
                  "search-field", args={"query": query, "ref": ""}, app="chrome"),
            step("observe-results", "Confirmar página de resultados", "observe_browser", "results",
                  expected={"page_changed": True}, app="chrome"),
            step("extract-mission-value", "Extrair e validar o valor observado",
                  "extract_mission_value", "browser-result",
                  args={"source_variable": value_key}, app="chrome",
                  produces=(value_key,)),
            step("handoff-to-notepad", "Transferir a missão para o Bloco de Notas",
                  "handoff_to_notepad", "notepad", args={"name": "bloco de notas"},
                  app="notepad"),
            step("focus-notepad", "Validar foco do Bloco de Notas", "ui_focus_window",
                  "notepad", expected={"process": "notepad"},
                  args={"window": "notepad"}, app="notepad"),
            step("observe-notepad", "Validar identidade do Bloco de Notas", "observe_window",
                  "notepad", expected={"process": "notepad"}, app="notepad"),
            step("capture-preexisting-document", "Registrar documento pré-existente",
                  "capture_document_state", "notepad", app="notepad"),
            step("new-notepad-document", "Abrir uma nova aba em branco",
                  "keyboard_hotkey", "notepad", expected={"process": "notepad"},
                  args={"keys": ["ctrl", "n"]}, app="notepad"),
            step("capture-mission-document", "Registrar documento criado pela missão",
                  "capture_document_state", "notepad", app="notepad"),
            step("check-overwrite", "Verificar política de sobrescrita", "check_overwrite_policy",
                  str(target_path), app="notepad"),
            step("type-mission-template", "Resolver o valor e escrever o texto",
                  "type_mission_template", "notepad-editor",
                  expected={"process": "notepad"},
                  args={"template": template, "source_variable": value_key}, app="notepad"),
            step("verify-editor-pre-save", "Validar editor antes do salvamento",
                  "verify_editor_pre_save", "notepad-editor",
                  expected={"process": "notepad"}, app="notepad"),
            step("open-save-dialog", "Abrir Salvar como", "keyboard_hotkey", "save-dialog",
                  expected={"process": "notepad"},
                  args={"keys": ["ctrl", "shift", "s"]}, app="notepad"),
            step("observe-save-dialog", "Validar Salvar como", "observe_window", "save-dialog",
                  expected={"title": ("save as", "salvar como"), "process": "notepad"},
                  app="notepad"),
            step("focus-file-name", "Focar nome do arquivo", "ui_focus_element", "file-name",
                  expected={"control_type": "Edit"},
                  args={"target": "", "control_type": "Edit", "window": ""}, app="notepad"),
            step("type-file-name", "Informar o caminho autorizado", "keyboard_type", "file-name",
                  expected={"title": ("save as", "salvar como")},
                  args={"text": str(target_path), "interval": 0.03}, app="notepad"),
            step("focus-save-button", "Groundar o botão Salvar", "ui_focus_element", "save-button",
                  expected={"control_type": "Button"},
                  args={"target": "Salvar", "control_type": "Button", "window": ""},
                  app="notepad"),
            step("confirm-save", "Confirmar salvamento", "ui_invoke_element", "save-button",
                  expected={"control_type": "Button"},
                  args={"target": "Salvar", "control_type": "Button", "window": ""},
                  app="notepad"),
            step("handle-overwrite-confirmation", "Confirmar sobrescrita somente do alvo autorizado",
                  "handle_overwrite_confirmation", "overwrite-dialog", app="notepad"),
            step("observe-saved-window", "Confirmar retorno ao Notepad", "observe_window",
                  "notepad", expected={"process": "notepad"}, app="notepad"),
            step("verify-cross-app-file", "Validar arquivo e valor transferido",
                  "verify_cross_app_file", str(target_path), app="notepad"),
        ]
        if ollama_mode:
            steps = [
                step("open-browser", "Abrir Google Chrome", "browser_open", "browser",
                     args={"visible": True, "provider": "chrome"}, app="chrome"),
                step("navigate-ollama-official", "Abrir a página oficial do Ollama",
                     "browser_navigate", "https://ollama.com/",
                     args={"url": "https://ollama.com/"}, app="chrome"),
                step("focus-browser", "Validar foco do Chrome", "focus_browser", "browser",
                     expected={"browser_process": True}, app="chrome"),
                step("observe-browser", "Validar identidade da página oficial",
                     "observe_browser", "browser", expected={"browser_process": True},
                     app="chrome"),
                step("extract-mission-value", "Observar o título oficial do Ollama",
                     "extract_mission_value", "browser-page",
                     args={"source_variable": "ollama_page_title", "value_kind": "title"},
                     app="chrome", produces=("ollama_page_title",)),
            ] + steps[8:]
        mission = ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                                  time.time(), steps, max_steps=self.MAX_STEPS)
        mission.result.update({
            "multi_app_mission": True,
            "search_query": query,
            "value_key": value_key,
            "filename": filename,
            "target_path": str(target_path),
            "original_user_request": text,
            "browser_mission": True,
            "search_provider": SEARCH_PROVIDER_ORDER[0],
            "provider_index": 0,
            "provider_health": [],
            "document_ownership": "PENDING",
        })
        if ollama_mode:
            mission.result.update({
                "direct_official_navigation": True,
                "authorization_scope": READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
                "official_host": "ollama.com",
                "source_url": "https://ollama.com/",
            })
        mission.context.artifacts["search_query"] = {
            "value": query, "kind": "USER_VALUE",
        }
        return mission

    def _plan_long_research(self, text: str) -> ComputerMission:
        """Plan the bounded Python -> Ollama -> Notepad workflow on one stack."""
        match = self._SAVE_RE.search(text)
        filename = Path(match.group(1)).name if match else "resumo_pesquisa.txt"
        target_path = self.resolve_target_path(filename)
        tool_names = {
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "browser_click",
            "browser_record_window", "browser_wait_for_results", "ui_active_window",
            "ui_focus_window", "ui_focus_element", "ui_focus_editor", "ui_read_editor",
            "ui_invoke_element", "ui_classify_dialog", "ui_list_elements",
            "open_program", "keyboard_type", "keyboard_hotkey", "keyboard_press",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None,
                 app="", requires=(), produces=()):
            return ComputerMissionStep(
                step_id, description, action_type, target, expected or {}, args or {},
                app=app, requires=tuple(requires), produces=tuple(produces))

        steps = [
            step("open-browser", "Abrir Google Chrome", "browser_open", "browser",
                  args={"visible": True, "provider": "chrome"}, app="chrome"),
            step("navigate-python-search", "Abrir pesquisa do Python", "browser_navigate",
                  DEFAULT_SEARCH_HOME, args={"url": DEFAULT_SEARCH_HOME}, app="chrome",
                  requires=("open-browser",)),
            step("focus-browser-python", "Validar foco do Chrome", "focus_browser", "browser",
                  expected={"browser_process": True}, app="chrome",
                  requires=("navigate-python-search",)),
            step("observe-browser-python", "Validar identidade do Chrome", "observe_browser",
                  "browser", expected={"browser_process": True}, app="chrome",
                  requires=("focus-browser-python",)),
            step("ground-python-search", "Localizar campo de pesquisa do Python",
                  "ground_search_field", "search-field", app="chrome",
                  requires=("observe-browser-python",)),
            step("search-python", "Pesquisar versão estável atual do Python",
                  "browser_search", "search-field",
                  args={"query": "current stable Python version official Python", "ref": ""},
                  app="chrome", requires=("ground-python-search",)),
            step("observe-python-results", "Confirmar resultados do Python", "observe_browser",
                  "results", expected={"page_changed": True}, app="chrome",
                  requires=("search-python",)),
            step("extract-python-value", "Extrair versão oficial do Python",
                  "extract_mission_value", "browser-result",
                  args={"source_variable": "python_version", "value_kind": "version"},
                  app="chrome", requires=("observe-python-results",),
                  produces=("python_version",)),
            step("checkpoint-python", "Criar CHECKPOINT_PYTHON_DONE", "checkpoint",
                  args={"name": "CHECKPOINT_PYTHON_DONE"}, app="chrome",
                  requires=("extract-python-value",)),
            step("navigate-ollama-search", "Abrir pesquisa do Ollama", "browser_navigate",
                  DEFAULT_SEARCH_HOME, args={"url": DEFAULT_SEARCH_HOME}, app="chrome",
                  requires=("checkpoint-python",)),
            step("focus-browser-ollama", "Revalidar foco do Chrome", "focus_browser", "browser",
                  expected={"browser_process": True}, app="chrome",
                  requires=("navigate-ollama-search",)),
            step("observe-browser-ollama", "Revalidar identidade do Chrome", "observe_browser",
                  "browser", expected={"browser_process": True}, app="chrome",
                  requires=("focus-browser-ollama",)),
            step("ground-ollama-search", "Localizar campo de pesquisa do Ollama",
                  "ground_search_field", "search-field", app="chrome",
                  requires=("observe-browser-ollama",)),
            step("search-ollama", "Pesquisar página oficial do Ollama", "browser_search",
                  "search-field", args={"query": "Ollama official homepage", "ref": ""},
                  app="chrome", requires=("ground-ollama-search",)),
            step("observe-ollama-results", "Confirmar resultados do Ollama", "observe_browser",
                  "results", expected={"page_changed": True}, app="chrome",
                  requires=("search-ollama",)),
            step("extract-ollama-value", "Extrair título oficial do Ollama",
                  "extract_mission_value", "browser-result",
                  args={"source_variable": "ollama_page_title", "value_kind": "title"},
                  app="chrome", requires=("observe-ollama-results",),
                  produces=("ollama_page_title",)),
            step("checkpoint-ollama", "Criar CHECKPOINT_OLLAMA_DONE", "checkpoint",
                  args={"name": "CHECKPOINT_OLLAMA_DONE"}, app="chrome",
                  requires=("extract-ollama-value",)),
            step("checkpoint-research", "Criar CHECKPOINT_RESEARCH_COMPLETE", "checkpoint",
                  args={"name": "CHECKPOINT_RESEARCH_COMPLETE"}, app="chrome",
                  requires=("checkpoint-ollama",)),
            step("handoff-to-notepad", "Transferir a pesquisa para o Bloco de Notas",
                  "handoff_to_notepad", "notepad", args={"name": "bloco de notas"},
                  app="notepad", requires=("checkpoint-research",)),
            step("focus-notepad", "Validar foco do Bloco de Notas", "ui_focus_window",
                  "notepad", expected={"process": "notepad"},
                  args={"window": "notepad"}, app="notepad",
                  requires=("handoff-to-notepad",)),
            step("observe-notepad", "Validar identidade do Bloco de Notas", "observe_window",
                  "notepad", expected={"process": "notepad"}, app="notepad",
                  requires=("focus-notepad",)),
            step("capture-preexisting-document", "Registrar documento pré-existente",
                  "capture_document_state", "notepad", app="notepad",
                  requires=("observe-notepad",)),
            step("checkpoint-notepad-ready", "Criar CHECKPOINT_NOTEPAD_READY", "checkpoint",
                  args={"name": "CHECKPOINT_NOTEPAD_READY"}, app="notepad",
                  requires=("capture-preexisting-document",)),
            step("new-notepad-document", "Abrir uma nova aba em branco", "keyboard_hotkey",
                  "notepad", expected={"process": "notepad"}, args={"keys": ["ctrl", "n"]},
                  app="notepad", requires=("checkpoint-notepad-ready",)),
            step("capture-mission-document", "Registrar documento da missão",
                  "capture_document_state", "notepad", app="notepad",
                  requires=("new-notepad-document",)),
            step("check-overwrite", "Verificar política de sobrescrita",
                  "check_overwrite_policy", str(target_path), app="notepad",
                  requires=("capture-mission-document",)),
            step("type-summary", "Escrever resumo com os valores observados",
                  "type_mission_template", "notepad-editor",
                  expected={"process": "notepad"},
                  args={"template": "Versão estável do Python: {{python_version}}\n"
                                "Título principal do Ollama: {{ollama_page_title}}",
                        "source_variables": ["python_version", "ollama_page_title"]},
                  app="notepad", requires=("check-overwrite",),
                  produces=("summary_text",)),
            step("verify-editor-pre-save", "Validar resumo no editor", "verify_editor_pre_save",
                  "notepad-editor", expected={"process": "notepad"}, app="notepad",
                  requires=("type-summary",), produces=("summary_text_verified",)),
            step("checkpoint-text-verified", "Criar CHECKPOINT_TEXT_VERIFIED", "checkpoint",
                  args={"name": "CHECKPOINT_TEXT_VERIFIED"}, app="notepad",
                  requires=("verify-editor-pre-save",)),
            step("open-save-dialog", "Abrir Salvar como", "keyboard_hotkey", "save-dialog",
                  expected={"process": "notepad"}, args={"keys": ["ctrl", "shift", "s"]},
                  app="notepad", requires=("checkpoint-text-verified",)),
            step("observe-save-dialog", "Validar Salvar como", "observe_window", "save-dialog",
                  expected={"title": ("save as", "salvar como"), "process": "notepad"},
                  app="notepad", requires=("open-save-dialog",)),
            step("focus-file-name", "Focar nome do arquivo", "ui_focus_element", "file-name",
                  expected={"control_type": "Edit"},
                  args={"target": "", "control_type": "Edit", "window": ""},
                  app="notepad", requires=("observe-save-dialog",)),
            step("type-file-name", "Informar o caminho autorizado", "keyboard_type", "file-name",
                  expected={"title": ("save as", "salvar como")},
                  args={"text": str(target_path), "interval": 0.03}, app="notepad",
                  requires=("focus-file-name",)),
            step("focus-save-button", "Groundar o botão Salvar", "ui_focus_element", "save-button",
                  expected={"control_type": "Button"},
                  args={"target": "Salvar", "control_type": "Button", "window": ""},
                  app="notepad", requires=("type-file-name",)),
            step("confirm-save", "Confirmar salvamento", "ui_invoke_element", "save-button",
                  expected={"control_type": "Button"},
                  args={"target": "Salvar", "control_type": "Button", "window": ""},
                  app="notepad", requires=("focus-save-button",)),
            step("handle-overwrite-confirmation", "Confirmar sobrescrita autorizada",
                  "handle_overwrite_confirmation", "overwrite-dialog", app="notepad",
                  requires=("confirm-save",)),
            step("observe-saved-window", "Confirmar retorno ao Notepad", "observe_window",
                  "notepad", expected={"process": "notepad"}, app="notepad",
                  requires=("handle-overwrite-confirmation",)),
            step("verify-cross-app-file", "Validar arquivo e contexto cruzado",
                  "verify_cross_app_file", str(target_path), app="notepad",
                  requires=("observe-saved-window",)),
            step("checkpoint-file-saved", "Criar CHECKPOINT_FILE_SAVED", "checkpoint",
                  args={"name": "CHECKPOINT_FILE_SAVED"}, app="notepad",
                  requires=("verify-cross-app-file",)),
        ]
        mission = ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                                  time.time(), steps, max_steps=60)
        mission.result.update({
            "multi_app_mission": True, "long_workflow": True,
            "search_query": "current stable Python version official Python",
            "target_path": str(target_path), "filename": filename,
            "browser_mission": True, "search_provider": SEARCH_PROVIDER_ORDER[0],
            "provider_index": 0, "provider_health": [],
            "document_ownership": "PENDING", "replans": 0,
            "max_replans": 2, "app_switch_budget": self.MAX_STEPS,
        })
        mission.context.artifacts["search_query"] = {
            "value": mission.result["search_query"], "kind": "USER_VALUE"}
        return mission

    def _plan_browser_search(self, text: str) -> ComputerMission:
        match = re.search(
            r"\b(?:pesquis(?:e|ar)?|busque|buscar|procure)\s+(.+?)(?=\s+e\s+me\s+diga|\s+e\s+abra|$)",
            text, re.I)
        query = (match.group(1).strip(" \t,\"'") if match else "")
        if not query:
            raise ValueError("Consulta de navegador vazia.")
        tool_names = {
            "browser_open", "browser_navigate", "browser_health", "browser_get_elements",
            "browser_search", "browser_get_page_info", "ui_active_window", "ui_focus_window",
            "browser_click", "browser_record_window", "browser_wait_for_results",
        }
        missing = sorted(name for name in tool_names if self.registry.get(name) is None)
        if missing:
            raise ValueError("Capacidades não registradas: " + ", ".join(missing))

        def step(step_id, description, action_type, target="", expected=None, args=None):
            return ComputerMissionStep(step_id, description, action_type, target,
                                       expected or {}, args or {})

        steps = [
            step("open-browser", "Abrir navegador visível controlado", "browser_open",
                 target="browser", args={"visible": True, "provider": "chrome"}),
            step("navigate-search-home", "Abrir página inicial de pesquisa", "browser_navigate",
                 target=DEFAULT_SEARCH_HOME, args={"url": DEFAULT_SEARCH_HOME}),
            step("focus-browser", "Confirmar foco no navegador", "focus_browser",
                 target="browser", expected={"browser_process": True}),
            step("observe-browser", "Confirmar sessão e janela do navegador", "observe_browser",
                 target="browser", expected={"browser_process": True}),
            step("ground-search-field", "Localizar campo de busca por elementos estruturados",
                 "ground_search_field", target="search-field"),
            step("execute-search", "Executar busca textual", "browser_search",
                 target="search-field", args={"query": query, "ref": ""}),
            step("observe-results", "Detectar mudança real de página", "observe_browser",
                 target="results", expected={"page_changed": True}),
            step("read-visible-results", "Ler conteúdo visível estruturado", "browser_get_page_info",
                 target="page"),
            step("verify-three-results", "Validar três títulos de resultados", "verify_browser_results",
                 target="results", expected={"minimum": 3}),
        ]
        mission = ComputerMission(str(uuid.uuid4()), text, MissionStatus.PENDING,
                                  time.time(), steps, max_steps=self.MAX_STEPS)
        mission.result["browser_mission"] = True
        mission.result["search_query"] = query
        mission.result["search_provider"] = SEARCH_PROVIDER_ORDER[0]
        mission.result["provider_index"] = 0
        mission.result["provider_health"] = []
        return mission


class ComputerMissionExecutor:
    """Run one mission step at a time through JarvisService.execute_tool."""

    _WINDOW_TOOLS = {"ui_active_window", "ui_focus_window", "ui_focus_element"}
    _ACTION_TOOLS = {"keyboard_type", "keyboard_hotkey", "keyboard_press"}
    MAX_APP_SWITCHES = 4
    MAX_FOCUS_RECOVERY_ATTEMPTS = 2

    def __init__(self, service, planner: Optional[ComputerMissionPlanner] = None):
        self.service = service
        self.planner = planner or ComputerMissionPlanner(service.registry)
        task_manager = getattr(service, "task_manager", None)
        task_database = getattr(task_manager, "database", None)
        self.persistence = MissionCheckpointStore(task_database)
        self._active: Optional[ComputerMission] = None
        self._missions: dict[str, ComputerMission] = {}
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._pause_requested = threading.Event()
        self._pause_reason = ""

    def run(self, request: str, task_id: str = "desktop",
            authorized_overwrite_paths: Optional[list[str]] = None,
            pause_after_checkpoint: str = "") -> dict[str, Any]:
        mission = self.planner.plan(request)
        if authorized_overwrite_paths:
            mission.result["authorized_overwrite_paths"] = [
                str(Path(path).resolve()) for path in authorized_overwrite_paths
            ]
        if pause_after_checkpoint:
            mission.result["pause_after_checkpoint"] = str(pause_after_checkpoint)
        with self._lock:
            self._active = mission
            self._missions[mission.mission_id] = mission
            self._cancel.clear()
            self._pause_requested.clear()
            self._pause_reason = ""
        persisted = self._persist_mission(mission)
        if not persisted.get("ok"):
            mission.status = MissionStatus.BLOCKED
            mission.error = persisted.get("error", "MISSION_PERSIST_FAILED")
            return self._finish(mission, False)
        started_checkpoint = self._create_checkpoint(
            mission, "CHECKPOINT_MISSION_STARTED", "")
        if not started_checkpoint.get("ok"):
            mission.status = MissionStatus.BLOCKED
            mission.error = started_checkpoint.get("error", "CHECKPOINT_FAILED")
            return self._finish(mission, False)
        self._audit_mission(mission, "MISSION_STARTED", {
            "checkpoint_id": started_checkpoint.get("checkpoint_id")})
        return self._run_from_current(mission, task_id)

    def _wait_for_resume_quiet(self, mission, task_id: str) -> dict[str, Any]:
        """Wait for observed quiet after an explicit resume request."""
        registry = getattr(self.service, "registry", None)
        if not registry or not registry.get("ui_user_activity"):
            return {"ok": True, "verification": "resume_quiet_window_unavailable"}
        quiet_ms = DEFAULT_RESUME_QUIET_WINDOW_MS
        max_wait_ms = DEFAULT_RESUME_MAX_WAIT_MS
        mission.status = MissionStatus.WAITING_FOR_USER_IDLE
        mission.error = "WAITING_FOR_USER_IDLE"
        mission.result.update({
            "explicit_resume_requested": True,
            "resume_requested_at": time.time(),
            "required_quiet_window_ms": quiet_ms,
            "quiet_window_max_wait_ms": max_wait_ms,
        })
        self._persist_mission(mission, pause_reason="USER_ACTIVITY")
        self._audit_mission(mission, "WAITING_FOR_USER_IDLE", {
            "required_quiet_window_ms": quiet_ms,
            "max_wait_ms": max_wait_ms,
        })
        started = time.monotonic()
        previous_age = None
        while True:
            if self._cancel.is_set() or self.service.cancellation.is_cancelled():
                mission.status = MissionStatus.CANCELLED
                mission.error = "Cancelamento solicitado pelo operador."
                self._persist_mission(mission, pause_reason="USER_ACTIVITY")
                self._audit_mission(mission, "MISSION_CANCELLED", {
                    "during": "WAITING_FOR_USER_IDLE"})
                return self._cancelled_result()
            activity = self.service.execute_tool(
                "ui_user_activity", {"threshold_ms": quiet_ms},
                command=f"computer_mission:{mission.mission_id}:resume_quiet_window",
                task_id=task_id)
            age = activity.get("last_user_input_age_ms")
            mission.result["last_user_input_age_ms"] = age
            if (previous_age is not None and age is not None and
                    int(age) < int(previous_age)):
                self._audit_mission(mission, "QUIET_WINDOW_RESET", {
                    "last_user_input_age_ms": age})
            previous_age = age
            if (activity.get("ok") and age is not None and
                    int(age) >= quiet_ms):
                mission.result["quiet_window_satisfied"] = True
                self._audit_mission(mission, "QUIET_WINDOW_SATISFIED", {
                    "last_user_input_age_ms": age,
                    "required_quiet_window_ms": quiet_ms,
                })
                return {"ok": True, "verification": "quiet_window_satisfied",
                        "last_user_input_age_ms": age}
            if (time.monotonic() - started) * 1000 >= max_wait_ms:
                mission.status = MissionStatus.PAUSED
                mission.error = "MISSION_PAUSED_FOR_USER_ACTIVITY"
                mission.result["pause_reason"] = "USER_ACTIVITY"
                self._persist_mission(mission, pause_reason="USER_ACTIVITY")
                self._audit_mission(mission, "MISSION_PAUSED_FOR_USER_ACTIVITY", {
                    "reason": "quiet_window_not_satisfied",
                    "last_user_input_age_ms": age,
                })
                return {"ok": False, "error": "USER_ACTIVITY_DETECTED",
                        "pause_reason": "USER_ACTIVITY",
                        "last_user_input_age_ms": age}
            self._cancel.wait(0.05)

    def resume(self, mission_id: str, token: str, task_id: str = "desktop") -> dict[str, Any]:
        with self._lock:
            mission = self._missions.get(str(mission_id))
        if mission is None:
            checkpoint, error = self.persistence.load_resume_token(token)
            if error or not checkpoint or checkpoint.get("mission_id") != str(mission_id):
                return {"ok": False, "error": error or "RESUME_MISSION_MISMATCH"}
            try:
                mission = self._restore_from_checkpoint(checkpoint)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            with self._lock:
                self._missions[mission.mission_id] = mission
                self._active = mission
        if mission.pending_confirmation_token == str(token):
            mission.pending_confirmation_token = ""
            current = mission.steps[mission.current_step]
            revalidated = self._resume_revalidate(mission, current, task_id)
            if not revalidated.get("ok"):
                if revalidated.get("error") in {
                        "USER_ACTIVITY_DETECTED", "FOREGROUND_CONTENTION",
                        "FOREGROUND_CHANGED_DURING_ATOMIC_ACTION",
                        "FOCUS_ACQUIRE_FAILED"}:
                    return self._pause_for_foreground_state(
                        mission, current, revalidated)
                mission.status = MissionStatus.BLOCKED
                mission.error = str(revalidated.get("error") or "RESUME_REVALIDATION_FAILED")
                current.status = MissionStepStatus.BLOCKED
                current.error = mission.error
                self._audit_step(mission, current, revalidated, "resume_revalidation_failed")
                return self._finish(mission, False)
            self._audit_mission(mission, "MISSION_RESUME_REQUESTED", {
                "mode": "security_confirmation"})
            result = self.service.confirm(token, task_id=mission.mission_id)
            if not result.get("ok") or result.get("confirmation_required"):
                mission.status = MissionStatus.FAILED
                mission.error = result.get("error", "Confirmação falhou")
                return self._finish(mission, False)
            mission.status = MissionStatus.RESUMING
            self._audit_mission(mission, "MISSION_RESUMED", {"mode": "confirmation"})
            return self._run_from_current(mission, task_id, preconfirmed=(current, result))

        checkpoint, error = self.persistence.load_resume_token(token)
        if error or not checkpoint or checkpoint.get("mission_id") != str(mission_id):
            return {"ok": False, "error": error or "RESUME_TOKEN_NOT_FOUND"}
        if checkpoint.get("checkpoint_id") != mission.result.get("checkpoint_id"):
            try:
                mission = self._restore_from_checkpoint(checkpoint)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            with self._lock:
                self._missions[mission.mission_id] = mission
                self._active = mission
        quiet = self._wait_for_resume_quiet(mission, task_id)
        if not quiet.get("ok"):
            return self._finish(mission, False)
        mission.status = MissionStatus.RESUMING
        mission.error = ""
        self._persist_mission(mission, pause_reason="")
        self._audit_mission(mission, "MISSION_RESUME_REQUESTED", {
            "checkpoint_id": checkpoint.get("checkpoint_id")})
        revalidated = self._revalidate_world(mission, task_id)
        if not revalidated.get("ok"):
            if revalidated.get("error") in {
                    "USER_ACTIVITY_DETECTED", "FOREGROUND_CONTENTION",
                    "FOREGROUND_CHANGED_DURING_ATOMIC_ACTION"}:
                return self._pause_for_foreground_state(
                    mission, mission.steps[mission.current_step], revalidated)
            mission.status = MissionStatus.BLOCKED
            mission.error = str(revalidated.get("error") or "WORLD_STATE_CHANGED")
            self._audit_mission(mission, "WORLD_STATE_REVALIDATED", revalidated)
            return self._finish(mission, False)
        self._audit_mission(mission, "WORLD_STATE_REVALIDATED", revalidated)
        self._audit_mission(mission, "MISSION_RESUMED", {
            "checkpoint_id": checkpoint.get("checkpoint_id")})
        return self._run_from_current(mission, task_id)

    def resume_current_mission(self, mission_id: str, resume_token: str,
                               task_id: str = "desktop") -> dict[str, Any]:
        return self.resume(mission_id, resume_token, task_id=task_id)

    def pause_current_mission(self, reason: str = "operator_requested") -> dict[str, Any]:
        with self._lock:
            mission = self._active
            if mission is None or mission.status in {MissionStatus.COMPLETED,
                                                       MissionStatus.FAILED,
                                                       MissionStatus.BLOCKED,
                                                       MissionStatus.CANCELLED}:
                return {"ok": False, "error": "NO_ACTIVE_MISSION"}
            self._pause_reason = str(reason)
            self._pause_requested.set()
            self._persist_mission(mission, pause_reason=reason)
            return {"ok": True, "pause_requested": True,
                    "mission_id": mission.mission_id}

    def cancel_current_mission(self) -> bool:
        with self._lock:
            mission = self._active
            if mission is None or mission.status in {MissionStatus.COMPLETED,
                                                       MissionStatus.FAILED,
                                                       MissionStatus.CANCELLED}:
                return False
            self._cancel.set()
            self._pause_requested.clear()
            mission.status = MissionStatus.CANCELLED
            mission.error = "Cancelamento solicitado pelo operador."
            if mission.current_step < len(mission.steps):
                mission.steps[mission.current_step].status = MissionStepStatus.CANCELLED
            self._persist_mission(mission, pause_reason="OPERATOR_CANCELLED")
            self._audit_mission(mission, "MISSION_CANCELLED", {
                "reason": "operator_requested"})
            return True

    def current(self) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._active.public() if self._active else None

    def _audit_mission(self, mission, event: str, details=None):
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool="computer_mission",
            arguments={"mission_id": mission.mission_id, "event": event},
            risk=mission.risk_level, status=event,
            result=_checkpoint_safe(details or {}),
        )

    @staticmethod
    def _mission_type(mission) -> str:
        if mission.result.get("long_workflow"):
            return "computer_use_6d"
        if mission.result.get("multi_app_mission"):
            return "computer_use_multi_app"
        if mission.result.get("browser_mission"):
            return "computer_use_browser"
        return "computer_use"

    def _checkpoint_snapshot(self, mission) -> dict[str, Any]:
        context = mission.context.checkpoint_snapshot() if mission.context else {}
        steps = []
        for step in mission.steps:
            steps.append({
                "step_id": step.step_id,
                "status": step.status.value,
                "attempts": step.attempts,
                "result": _checkpoint_safe(step.result),
                "error": step.error,
            })
        return {
            "mission_id": mission.mission_id,
            "user_request": mission.user_request,
            "status": mission.status.value,
            "current_step": mission.current_step,
            "next_step": mission.current_step,
            "max_steps": mission.max_steps,
            "timeout_seconds": mission.timeout_seconds,
            "risk_level": mission.risk_level,
            "result": _checkpoint_safe(mission.result),
            "steps": steps,
            "context": context,
            "context_revision": int(context.get("context_version") or 0),
        }

    def _mission_record_payload(self, mission, checkpoint_id: str = "",
                                pause_reason: str = "") -> dict[str, Any]:
        snapshot = self._checkpoint_snapshot(mission)
        return {
            "mission_id": mission.mission_id,
            "mission_type": self._mission_type(mission),
            "user_request": mission.user_request,
            "status": mission.status.value,
            "created_at": mission.created_at,
            "updated_at": time.time(),
            "current_step": mission.current_step,
            "next_step": mission.current_step,
            "checkpoint_id": checkpoint_id or str(
                mission.result.get("checkpoint_id") or ""),
            "context_revision": int(snapshot.get("context_revision") or 0),
            "pause_reason": pause_reason or str(
                mission.result.get("pause_reason") or ""),
            "snapshot": snapshot,
        }

    def _persist_mission(self, mission, *, checkpoint_id: str = "",
                         pause_reason: str = "", audit: bool = True) -> dict[str, Any]:
        try:
            payload = self._mission_record_payload(
                mission, checkpoint_id=checkpoint_id, pause_reason=pause_reason)
            record = self.persistence.save_mission(**payload)
            if audit:
                self._audit_mission(mission, "MISSION_PERSISTED", {
                    "status": mission.status.value,
                    "checkpoint_id": record.get("checkpoint_id") or None,
                    "context_revision": record.get("context_revision"),
                })
            return {"ok": True, **record}
        except Exception as exc:
            if audit:
                self._audit_mission(mission, "MISSION_PERSIST_FAILED", {
                    "error": str(exc)[:200]})
            return {"ok": False, "error": "MISSION_PERSIST_FAILED"}

    def _create_checkpoint(self, mission, name: str, pause_reason: str,
                           state: CheckpointState = CheckpointState.VALID) -> dict[str, Any]:
        try:
            snapshot = self._checkpoint_snapshot(mission)
            record = self.persistence.save_checkpoint(
                mission_id=mission.mission_id,
                mission_version=int(snapshot["context_revision"]),
                name=name,
                current_step=mission.current_step,
                next_step=mission.current_step,
                context_revision=int(snapshot["context_revision"]),
                snapshot=snapshot,
                pause_reason=pause_reason,
                state=state,
                mission_record=self._mission_record_payload(
                    mission, pause_reason=pause_reason),
            )
            mission.result.setdefault("completed_checkpoints", []).append(name)
            mission.result["checkpoint_id"] = record["checkpoint_id"]
            mission.result["resume_token"] = record["resume_token"]
            durable = self._persist_mission(
                mission, checkpoint_id=record["checkpoint_id"],
                pause_reason=pause_reason, audit=False)
            if not durable.get("ok"):
                return durable
            self._audit_mission(mission, "CHECKPOINT_DURABLY_COMMITTED", {
                "checkpoint_id": record["checkpoint_id"],
                "name": name,
            })
            self._audit_mission(mission, "CHECKPOINT_CREATED", {
                "checkpoint_id": record["checkpoint_id"], "name": name,
                "state": record["state"], "pause_reason": pause_reason,
            })
            return {"ok": True, **record}
        except Exception as exc:
            self._audit_mission(mission, "CHECKPOINT_FAILED", {
                "name": name, "error": str(exc)[:200]})
            return {"ok": False, "error": "CHECKPOINT_FAILED"}

    def _restore_from_checkpoint(self, checkpoint: dict[str, Any]) -> ComputerMission:
        snapshot = checkpoint.get("snapshot") or {}
        if snapshot.get("mission_id") != checkpoint.get("mission_id"):
            raise ValueError("CHECKPOINT_INVALID")
        context_snapshot = snapshot.get("context") or {}
        if int(checkpoint.get("context_revision") or 0) != int(
                context_snapshot.get("context_version") or 0):
            raise ValueError("CHECKPOINT_CONTEXT_MISMATCH")
        mission = self.planner.plan(str(snapshot.get("user_request") or ""))
        stored_result = dict(snapshot.get("result") or {})
        stored_step_ids = {str(item.get("step_id") or "")
                           for item in snapshot.get("steps") or []}
        planned_step_ids = {step.step_id for step in mission.steps}
        legacy_plan_repaired = bool(
            mission.result.get("multi_app_mission") and
            (not stored_result.get("multi_app_mission") or
             bool(stored_step_ids - planned_step_ids)))
        if mission.mission_id != checkpoint.get("mission_id"):
            mission.mission_id = str(checkpoint["mission_id"])
            context_snapshot = dict(context_snapshot)
        if legacy_plan_repaired:
            # The persisted mission was created before the planner recognized
            # the official Ollama -> Notepad workflow. Restart the same mission
            # from step zero with the corrected plan; do not create new IDs.
            mission.context = MissionContext(
                mission.mission_id,
                str(snapshot.get("user_request") or mission.user_request))
            mission.current_step = 0
            mission.result.update({
                "replanned_from_checkpoint": True,
                "replan_reason": "PLANNER_SCOPE_MISMATCH",
            })
            self._audit_mission(mission, "MISSION_PLAN_REPAIRED", {
                "reason": "PLANNER_SCOPE_MISMATCH",
                "mission_id": mission.mission_id,
            })
        else:
            mission.context = MissionContext.from_checkpoint(
                context_snapshot, mission.mission_id,
                str(snapshot.get("user_request") or mission.user_request))
            mission.current_step = int(snapshot.get("next_step", snapshot.get("current_step", 0)))
        mission.max_steps = int(snapshot.get("max_steps") or mission.max_steps)
        mission.timeout_seconds = float(snapshot.get("timeout_seconds") or mission.timeout_seconds)
        mission.risk_level = str(snapshot.get("risk_level") or mission.risk_level)
        if not legacy_plan_repaired:
            mission.result.update(stored_result)
        if mission.result.get("direct_official_navigation"):
            # Older checkpoints created this read-only mission as WRITE.
            # Normalize them without widening permissions or creating a new mission.
            mission.requires_confirmation = False
            mission.risk_level = "LOW"
            mission.result["authorization_scope"] = READ_ONLY_PUBLIC_BROWSER_OBSERVATION
        mission.result["checkpoint_id"] = checkpoint["checkpoint_id"]
        mission.result["resume_token"] = checkpoint["resume_token"]
        mission.result["recovered_from_checkpoint"] = True
        if not legacy_plan_repaired:
            by_id = {step.step_id: step for step in mission.steps}
            for raw in snapshot.get("steps") or []:
                step = by_id.get(str(raw.get("step_id") or ""))
                if step is None:
                    continue
                try:
                    step.status = MissionStepStatus(str(raw.get("status") or "PENDING"))
                except ValueError:
                    raise ValueError("CHECKPOINT_INVALID")
                step.attempts = int(raw.get("attempts") or 0)
                step.result = dict(raw.get("result") or {})
                step.error = str(raw.get("error") or "")
        if mission.current_step < 0 or mission.current_step > len(mission.steps):
            raise ValueError("CHECKPOINT_INVALID")
        mission.status = MissionStatus.RESUMING
        mission.pending_confirmation_token = ""
        self._audit_mission(mission, "CHECKPOINT_LOADED", {
            "checkpoint_id": checkpoint["checkpoint_id"]})
        return mission

    def _foreground_guard(self, mission, task_id, app: str) -> dict[str, Any]:
        """Protect mission actions from competing with a human-owned foreground."""
        if not getattr(self.service, "registry", None) or not self.service.registry.get(
                "ui_foreground_state"):
            return {"ok": True, "verification": "foreground_guard_unavailable"}
        expected = "notepad" if str(app).casefold() == "notepad" else "chrome"
        state = self.service.execute_tool(
            "ui_foreground_state", {"window": expected,
                                     "expected_process": expected},
            command=f"computer_mission:{mission.mission_id}:foreground_guard",
            task_id=task_id)
        if not state.get("ok"):
            return {"ok": False, "error": "FOREGROUND_STATE_UNAVAILABLE",
                    "detail": state}
        mission.result.update({
            "foreground_owner": state.get("foreground_owner", "UNKNOWN"),
            "foreground_window_state": state.get("window_state", "UNKNOWN_WINDOW_STATE"),
            "foreground_epoch": state.get("foreground_epoch"),
            "last_user_input_age_ms": state.get("last_user_input_age_ms"),
            "user_active": bool(state.get("user_active")),
        })
        if (state.get("user_active") and
                state.get("foreground_owner") == "USER_EXTERNAL_APP" and
                not state.get("window_focused")):
            return {"ok": False, "error": "USER_ACTIVITY_DETECTED",
                    "pause_reason": "USER_ACTIVITY",
                    "foreground_owner": state.get("foreground_owner"),
                    "last_user_input_age_ms": state.get("last_user_input_age_ms"),
                    "foreground_state": state}
        if (state.get("foreground_owner") == "SYSTEM_DIALOG" and
                not state.get("window_focused")):
            return {"ok": False, "error": "FOREGROUND_CONTENTION",
                    "pause_reason": "SYSTEM_DIALOG",
                    "foreground_owner": state.get("foreground_owner"),
                    "foreground_state": state}
        return state

    def _pause_for_foreground_state(self, mission, step, result):
        """Persist a safe pause; explicit resume is required to continue."""
        error = str(result.get("error") or "FOREGROUND_CONTENTION")
        reason = str(result.get("pause_reason") or (
            "USER_ACTIVITY" if error == "USER_ACTIVITY_DETECTED"
            else "FOREGROUND_CONTENTION"))
        mission.status = MissionStatus.PAUSED
        mission.error = ("MISSION_PAUSED_FOR_USER_ACTIVITY" if
                         reason == "USER_ACTIVITY" else
                         "MISSION_PAUSED_FOR_FOREGROUND_CONTENTION")
        step.status = MissionStepStatus.PENDING
        step.error = ""
        mission.result.update({
            "pause_reason": reason,
            "mission_paused_for_user_activity": reason == "USER_ACTIVITY",
            "foreground_owner": result.get("foreground_owner",
                                             mission.result.get("foreground_owner", "UNKNOWN")),
            "last_user_input_age_ms": result.get(
                "last_user_input_age_ms", mission.result.get("last_user_input_age_ms")),
        })
        checkpoint_name = ("CHECKPOINT_PAUSED_USER_ACTIVITY" if
                           reason == "USER_ACTIVITY" else
                           "CHECKPOINT_PAUSED_FOREGROUND_CONTENTION")
        checkpoint = self._create_checkpoint(mission, checkpoint_name, reason)
        if not checkpoint.get("ok"):
            mission.status = MissionStatus.BLOCKED
            mission.error = checkpoint.get("error", "CHECKPOINT_FAILED")
            return self._finish(mission, False)
        self._audit_mission(mission, "USER_ACTIVITY_DETECTED" if
                            reason == "USER_ACTIVITY" else "FOREGROUND_CONTENTION", {
                                "pause_reason": reason,
                                "foreground_owner": mission.result.get("foreground_owner"),
                                "last_user_input_age_ms": mission.result.get(
                                    "last_user_input_age_ms"),
                            })
        self._audit_mission(mission, "MISSION_PAUSED_FOR_USER_ACTIVITY" if
                            reason == "USER_ACTIVITY" else
                            "MISSION_PAUSED_FOR_FOREGROUND_CONTENTION", {
                                "checkpoint_id": checkpoint.get("checkpoint_id"),
                                "next_step": mission.current_step,
                            })
        return self._finish(mission, False)

    def _revalidate_world(self, mission, task_id):
        current_app = str((mission.context.current_app if mission.context else "") or "")
        if current_app.casefold() in {"chrome", "notepad"}:
            guard = self._foreground_guard(mission, task_id, current_app)
            if not guard.get("ok"):
                return guard
        if current_app.casefold() == "chrome":
            previous_state = str(mission.result.get("browser_page_state_id") or "")
            health = self.service.execute_tool(
                "browser_health", {}, command="computer_mission:resume_browser_health",
                task_id=mission.mission_id)
            if not health.get("ok") or not health.get("started"):
                return {"ok": False, "error": "WORLD_STATE_CHANGED", "detail": health}
            provider = str(health.get("browser_provider") or health.get("provider") or "").casefold()
            if provider != "chrome":
                return {"ok": False, "error": "WORLD_STATE_CHANGED", "detail": health}
            current_state = str(health.get("page_state_id") or "")
            if previous_state and current_state and previous_state != current_state:
                return {"ok": False, "error": "STALE_BROWSER_STATE",
                        "expected_state": previous_state, "actual_state": current_state}
            mission.result["browser_page_state_id"] = health.get("page_state_id")
            mission.result["browser_url"] = health.get("current_url", "")
            mission.result["browser_title"] = health.get("page_title", "")
        elif current_app.casefold() == "notepad":
            observed = self._observe_window(
                ComputerMissionStep("resume-notepad-observe", "Revalidar Notepad",
                                    "observe_window", expected_state={"process": "notepad"}))
            if not observed.get("ok"):
                change = self._classify_world_state_change(mission, observed, task_id)
                if change in {WorldStateChangeType.APP_CLOSED,
                              WorldStateChangeType.WINDOW_MISSING,
                              WorldStateChangeType.DOCUMENT_MISSING}:
                    recovered = self._prepare_notepad_recovery(
                        mission, change, observed)
                    if recovered.get("ok"):
                        return recovered
                    return recovered
                if change == WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_RECOVERABLE:
                    return self._recover_background_notepad(
                        mission, task_id, observed)
                if change == WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_USER_ACTIVE:
                    return {"ok": False, "error": "USER_ACTIVITY_DETECTED",
                            "pause_reason": "USER_ACTIVITY",
                            "world_state_change_type": change.value,
                            "detail": observed}
                if change == WorldStateChangeType.FOREGROUND_CONTENTION:
                    return {"ok": False, "error": "FOREGROUND_CONTENTION",
                            "pause_reason": "FOREGROUND_CONTENTION",
                            "world_state_change_type": change.value,
                            "detail": observed}
                return {"ok": False, "error": "WORLD_STATE_CHANGED",
                        "world_state_change_type": change.value,
                        "detail": observed}
            if mission.context and mission.context.artifacts.get("mission_document_id"):
                guard = self._assert_mission_document(mission, task_id)
                if not guard.get("ok"):
                    change = self._classify_world_state_change(mission, guard, task_id)
                    if change in {WorldStateChangeType.DOCUMENT_MISSING,
                                  WorldStateChangeType.WINDOW_MISSING}:
                        return self._prepare_notepad_recovery(
                            mission, change, guard)
                    if change == WorldStateChangeType.FOREGROUND_CONTENTION:
                        return {"ok": False, "error": "FOREGROUND_CONTENTION",
                                "pause_reason": "FOREGROUND_CONTENTION",
                                "world_state_change_type": change.value,
                                "detail": guard}
                    return {"ok": False, "error": "WORLD_STATE_CHANGED",
                            "world_state_change_type": change.value,
                            "detail": guard}
        return {"ok": True, "verification": WorldStateChangeType.VALID.value,
                "world_state_change_type": WorldStateChangeType.VALID.value,
                "current_app": current_app}

    def _classify_world_state_change(self, mission, observed, task_id):
        """Classify a missing Notepad target before deciding whether to recover."""
        detail = dict(observed or {})
        if detail.get("error") in {"DOCUMENT_NOT_FOUND", "DOCUMENT_IDENTITY_MISMATCH",
                                    "DOCUMENT_WINDOW_MISMATCH"}:
            return WorldStateChangeType.DOCUMENT_MISSING
        if getattr(self.service, "registry", None) and self.service.registry.get(
                "ui_foreground_state"):
            foreground = self.service.execute_tool(
                "ui_foreground_state",
                {"window": "notepad", "expected_process": "notepad"},
                command=f"computer_mission:{mission.mission_id}:world_foreground_probe",
                task_id=task_id)
            if foreground.get("ok"):
                state = str(foreground.get("window_state") or "")
                if state == "WINDOW_EXISTS_BACKGROUND":
                    if foreground.get("user_active"):
                        return WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_USER_ACTIVE
                    if self._background_recovery_allowed(mission):
                        return WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_RECOVERABLE
                    return WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_UNKNOWN
                if state == "WINDOW_MINIMIZED":
                    return WorldStateChangeType.WINDOW_MINIMIZED
                if state == "WINDOW_OCCLUDED":
                    return WorldStateChangeType.WINDOW_OCCLUDED
                if state == "PROCESS_NOT_RUNNING":
                    return WorldStateChangeType.APP_CLOSED
                if state == "WINDOW_NOT_FOUND":
                    return WorldStateChangeType.WINDOW_MISSING
        probe = self.service.execute_tool(
            "ui_read_editor", {"window": "notepad", "expected_process": "notepad"},
            command=f"computer_mission:{mission.mission_id}:world_probe",
            task_id=task_id)
        if probe.get("path_error_dialog"):
            return WorldStateChangeType.UNKNOWN
        if probe.get("found") and probe.get("verified"):
            return WorldStateChangeType.WINDOW_MISSING
        reason = str(probe.get("reason") or detail.get("reason") or "").casefold()
        if reason in {"window_not_found", "process_mismatch", "editor_not_found"}:
            return WorldStateChangeType.APP_CLOSED
        return WorldStateChangeType.UNKNOWN

    def _background_recovery_allowed(self, mission) -> bool:
        """Return whether a background target is provably mission-owned and safe."""
        artifacts = mission.context.artifacts if mission.context else {}
        if (mission.result.get("document_ownership") != "OWNED_BY_CURRENT_MISSION" or
                not artifacts.get("mission_document_id") or
                not artifacts.get("mission_document_created_by_mission")):
            return False
        unknown = [receipt for receipt in self.persistence.receipts_for_mission(
            mission.mission_id)
                   if receipt.get("result_state") == ActionState.IN_FLIGHT_UNKNOWN.value]
        if unknown:
            return False
        tool = self.service.registry.get("ui_focus_window") if getattr(
            self.service, "registry", None) else None
        security = getattr(self.service, "security", None)
        if tool is None:
            return False
        if security is not None and security.decision(tool) == "deny":
            return False
        return True

    def _recover_background_notepad(self, mission, task_id, observed):
        """Recover one owned idle background window without bypassing guards."""
        if not self._background_recovery_allowed(mission):
            return {"ok": False, "error": "WINDOW_EXISTS_BACKGROUND_UNKNOWN",
                    "world_state_change_type":
                    WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_UNKNOWN.value}
        artifacts = mission.context.artifacts
        expected_handle = int(artifacts.get("mission_window_id") or 0)
        attempts = 0
        self._audit_mission(mission, "BACKGROUND_WINDOW_RECOVERY_STARTED", {
            "expected_window_id": expected_handle,
            "max_attempts": self.MAX_FOCUS_RECOVERY_ATTEMPTS,
        })
        for attempt in range(1, self.MAX_FOCUS_RECOVERY_ATTEMPTS + 1):
            attempts = attempt
            activity = self.service.execute_tool(
                "ui_user_activity", {"threshold_ms": DEFAULT_RESUME_QUIET_WINDOW_MS},
                command=f"computer_mission:{mission.mission_id}:focus_recovery_activity",
                task_id=task_id)
            if not activity.get("ok"):
                return {"ok": False, "error": "FOREGROUND_STATE_UNAVAILABLE",
                        "focus_recovery_attempts": attempts}
            if activity.get("user_active"):
                self._audit_mission(mission, "USER_ACTIVITY_DETECTED", {
                    "phase": "before_focus_recovery",
                    "focus_recovery_attempts": attempts,
                })
                return {"ok": False, "error": "USER_ACTIVITY_DETECTED",
                        "pause_reason": "USER_ACTIVITY",
                        "focus_recovery_attempts": attempts}
            foreground = self._foreground_guard(mission, task_id, "notepad")
            if not foreground.get("ok"):
                return {**foreground, "focus_recovery_attempts": attempts}
            target = foreground.get("target_window") or {}
            target_handle = int(target.get("handle") or 0)
            if expected_handle and target_handle and target_handle != expected_handle:
                return {"ok": False, "error": "STALE_DOCUMENT",
                        "focus_recovery_attempts": attempts,
                        "expected_window_id": expected_handle,
                        "current_window_id": target_handle}
            self._audit_mission(mission, "FOCUS_RECOVERY_ATTEMPT", {
                "attempt": attempts, "window_id": target_handle or expected_handle,
            })
            focused = self.service.execute_tool(
                "ui_focus_window", {"window": "notepad",
                                     "process_id": int(target.get("pid") or 0)},
                command=f"computer_mission:{mission.mission_id}:focus_recovery",
                task_id=task_id)
            if focused.get("confirmation_required"):
                return focused
            after_activity = self.service.execute_tool(
                "ui_user_activity", {"threshold_ms": DEFAULT_RESUME_QUIET_WINDOW_MS},
                command=f"computer_mission:{mission.mission_id}:focus_recovery_post_activity",
                task_id=task_id)
            if not after_activity.get("ok"):
                return {"ok": False, "error": "FOREGROUND_STATE_UNAVAILABLE",
                        "focus_recovery_attempts": attempts}
            if after_activity.get("user_active"):
                return {"ok": False, "error": "USER_ACTIVITY_DETECTED",
                        "pause_reason": "USER_ACTIVITY",
                        "focus_recovery_attempts": attempts}
            verified = self._foreground_guard(mission, task_id, "notepad")
            active = self.service.execute_tool(
                "ui_active_window", {},
                command=f"computer_mission:{mission.mission_id}:focus_recovery_verify",
                task_id=task_id)
            active_data = active.get("result") if isinstance(
                active.get("result"), dict) else active
            active_process = str(active_data.get("process_name") or "").casefold()
            if (focused.get("ok") and verified.get("window_focused") and
                    verified.get("window_state") == "WINDOW_EXISTS_FOREGROUND" and
                    active_process == "notepad.exe"):
                ownership = self._assert_mission_document(mission, task_id)
                if not ownership.get("ok"):
                    return {"ok": False, "error": "STALE_DOCUMENT",
                            "focus_recovery_attempts": attempts,
                            "detail": ownership}
                verify_step = next((step for step in mission.steps
                                    if step.step_id == "verify-editor-pre-save"), None)
                if verify_step is None:
                    return {"ok": False, "error": "EDITOR_REVALIDATION_UNAVAILABLE",
                            "focus_recovery_attempts": attempts}
                editor = self._verify_editor_content(
                    mission, verify_step, task_id, pre_save=True)
                if not editor.get("ok"):
                    return {**editor, "focus_recovery_attempts": attempts}
                self._audit_mission(mission, "BACKGROUND_WINDOW_RECOVERED", {
                    "focus_recovery_attempts": attempts,
                    "mission_document_id": artifacts.get("mission_document_id"),
                })
                return {"ok": True, "verified": True,
                        "verification": "background_window_recovered_and_editor_reverified",
                        "world_state_change_type":
                        WorldStateChangeType.WINDOW_EXISTS_BACKGROUND_RECOVERABLE.value,
                        "focus_recovery_attempts": attempts,
                        "editor_content_verified": True,
                        "mission_to_editor_match": True}
        self._audit_mission(mission, "FOCUS_RECOVERY_FAILED", {
            "focus_recovery_attempts": attempts})
        return {"ok": False, "error": "FOCUS_RECOVERY_FAILED",
                "pause_reason": "FOREGROUND_CONTENTION",
                "focus_recovery_attempts": attempts}

    def _recovery_context_validation(self, mission):
        context = mission.context
        if context is None:
            return {"ok": False, "error": "MISSING_MISSION_CONTEXT"}
        known_hosts = {
            "python_version": ("python.org", ".python.org"),
            "python_page_title": ("python.org", ".python.org"),
            "ollama_page_title": ("ollama.com", ".ollama.com"),
        }
        required_keys = set()
        value_key = str(mission.result.get("value_key") or "").strip()
        if value_key:
            required_keys.add(value_key)
        for step in mission.steps:
            source_variable = str(step.args.get("source_variable") or "").strip()
            if source_variable:
                required_keys.add(source_variable)
            required_keys.update(
                str(key) for key in step.args.get("source_variables", ()) if key)
            template = str(step.args.get("template") or "")
            required_keys.update(re.findall(
                r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}", template))
        if not required_keys:
            required_keys.update(str(key) for key in context.variables)
        for key in sorted(required_keys):
            hosts = known_hosts.get(key)
            if not hosts:
                return {"ok": False, "error": "SOURCE_PROVENANCE_INVALID",
                        "variable": key}
            value, error = context.resolve(
                key, mission_id=mission.mission_id,
                current_step=mission.current_step)
            if error or not value:
                return {"ok": False, "error": "MISSING_MISSION_VARIABLE",
                        "variable": key}
            provenance = context.source_provenance.get(key) or {}
            source_url = str(provenance.get("source_url") or "")
            parsed = urlparse(source_url)
            host = (parsed.hostname or "").casefold()
            valid_hosts = {item.casefold().lstrip(".") for item in hosts}
            if (provenance.get("confidence") != "verified" or
                    provenance.get("invalidated") or
                    not any(host == item or host.endswith("." + item)
                            for item in valid_hosts)):
                return {"ok": False, "error": "SOURCE_PROVENANCE_INVALID",
                        "variable": key}
        return {"ok": True, "verification": "MISSION_CONTEXT_AND_PROVENANCE_VALID"}

    def _recovery_target_validation(self, mission):
        filename = str(mission.result.get("filename") or "")
        stored_path = Path(str(mission.result.get("target_path") or ""))
        if not filename or not stored_path:
            return {"ok": False, "error": "TARGET_CHANGED"}
        resolved_path = self.planner.resolve_target_path(filename).resolve()
        if resolved_path != stored_path.resolve():
            return {"ok": False, "error": "TARGET_CHANGED",
                    "expected_path": str(stored_path),
                    "resolved_path": str(resolved_path)}
        if resolved_path.exists():
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "reason": "AUTHORIZED_TARGET_ALREADY_EXISTS",
                    "path": str(resolved_path)}
        return {"ok": True, "path": str(resolved_path)}

    def _prepare_notepad_recovery(self, mission, change, detail):
        context_check = self._recovery_context_validation(mission)
        if not context_check.get("ok"):
            return {"ok": False, "error": context_check["error"],
                    "world_state_change_type": change.value,
                    "world_state_change_classification": "BLOCKED",
                    "detail": context_check}
        target_check = self._recovery_target_validation(mission)
        if not target_check.get("ok"):
            classification = ("BLOCKED" if target_check.get("error") != "TARGET_CHANGED"
                              else "REPLAN_REQUIRED")
            return {"ok": False, "error": target_check["error"],
                    "world_state_change_type": WorldStateChangeType.TARGET_CHANGED.value,
                    "world_state_change_classification": classification,
                    "detail": target_check}
        dangerous = {
            ActionState.IN_FLIGHT_UNKNOWN.value,
        }
        unknown = [receipt for receipt in self.persistence.receipts_for_mission(
            mission.mission_id)
                   if receipt.get("result_state") in dangerous and
                   receipt.get("action_type") in {
                       "keyboard_type", "keyboard_hotkey", "keyboard_press",
                       "ui_invoke_element", "open_program"}]
        if unknown:
            return {"ok": False, "error": "ACTION_IN_FLIGHT_UNKNOWN",
                    "world_state_change_type": change.value,
                    "world_state_change_classification": "BLOCKED"}

        context = mission.context
        artifacts = context.artifacts
        old_document_id = str(artifacts.get("mission_document_id") or "")
        old_window_id = int(artifacts.get("mission_window_id") or 0)
        artifacts["old_targets_invalidated"] = True
        artifacts["old_document_target_invalidated"] = bool(old_document_id)
        artifacts["old_window_target_invalidated"] = bool(old_window_id)
        for key in (
                "mission_document_id", "mission_window_id",
                "mission_document_content_state_id", "mission_document_tabs",
                "mission_document_created_by_mission", "pre_existing_document_ids",
                "pre_existing_documents", "pre_existing_tabs", "editor_content_verified",
                "editor_content_state_id", "rendered_text", "text_input_sent"):
            artifacts.pop(key, None)
        for key in ("mission_document_id", "mission_window_id", "document_ownership"):
            mission.result.pop(key, None)
        mission.result.update({
            "old_window_target_invalidated": True,
            "old_document_target_invalidated": True,
            "world_state_change_type": change.value,
            "world_state_change_classification": "RECOVERABLE",
            "recovery_active": True,
            "recovery_count": int(mission.result.get("recovery_count") or 0) + 1,
        })
        start = next((index for index, step in enumerate(mission.steps)
                      if step.step_id == "handoff-to-notepad"), None)
        if start is None:
            return {"ok": False, "error": "RECOVERY_PLAN_UNAVAILABLE",
                    "world_state_change_type": change.value,
                    "world_state_change_classification": "BLOCKED"}
        for step in mission.steps[start:]:
            step.status = MissionStepStatus.PENDING
            step.attempts = 0
            step.error = ""
            step.result = {}
            if step.action_type in {"keyboard_type", "keyboard_hotkey", "keyboard_press",
                                    "ui_invoke_element", "open_program"}:
                self.persistence.save_receipt(
                    mission_id=mission.mission_id, step_id=step.step_id,
                    action_type=step.action_type, target=step.target,
                    result_state=ActionState.NOT_STARTED,
                    result={"recovery_reset": True})
        new_document = next((step for step in mission.steps
                             if step.step_id == "new-notepad-document"), None)
        if new_document is not None:
            # Recovery must create a fresh mission surface through a newly
            # grounded UIA control; a global Ctrl+N can land in another app
            # when the foreground changes between observation and action.
            new_document.action_type = "ui_invoke_element"
            new_document.target = "Adicionar Nova Guia"
            new_document.args = {
                "target": "Adicionar Nova Guia",
                "control_type": "Button",
                "window": "notepad",
            }
        mission.current_step = start
        context.current_app = "chrome"
        context.previous_app = "chrome"
        context.updated_at = time.time()
        self._audit_context_event(
            mission, "APP_RECOVERY_STARTED", "recovering", {"ok": True},
            app="notepad", previous_app="chrome", destination="notepad")
        self._audit_mission(mission, "OLD_TARGETS_INVALIDATED", {
            "old_window_target_invalidated": True,
            "old_document_target_invalidated": True,
            "world_state_change_type": change.value})
        return {"ok": True, "verified": True,
                "verification": "WORLD_STATE_CHANGED_RECOVERABLE",
                "world_state_change_type": change.value,
                "world_state_change_classification": "RECOVERABLE",
                "recovery_required": True,
                "detail": detail}

    def _dependencies_satisfied(self, mission, step):
        completed = {item.step_id for item in mission.steps
                     if item.status is MissionStepStatus.COMPLETED}
        checkpoints = set(mission.result.get("completed_checkpoints") or [])
        for requirement in step.requires:
            requirement = str(requirement)
            if requirement.startswith("checkpoint:"):
                ok = requirement.split(":", 1)[1] in checkpoints
            elif requirement.startswith("var:"):
                _, name = requirement.split(":", 1)
                ok = bool(mission.context and mission.context.resolve(
                    name, mission_id=mission.mission_id,
                    current_step=mission.current_step)[0])
            else:
                ok = requirement in completed
            if not ok:
                return {"ok": False, "error": "DEPENDENCY_NOT_SATISFIED",
                        "dependency": requirement}
        return {"ok": True}

    def _receipt_before_action(self, mission, step):
        if step.action_type not in {"keyboard_type", "keyboard_hotkey", "keyboard_press",
                                    "ui_invoke_element", "open_program"}:
            return None
        receipt = self.persistence.receipt(mission.mission_id, step.step_id)
        if receipt and receipt.get("result_state") == ActionState.VERIFIED.value:
            return {"ok": True, "verified": True, "skipped": True,
                    "verification": "STEP_SKIPPED_ALREADY_VERIFIED",
                    "receipt": receipt}
        if receipt and receipt.get("result_state") == ActionState.IN_FLIGHT_UNKNOWN.value:
            if step.step_id in {"confirm-save", "verify-cross-app-file"}:
                recovered = self._verify_cross_app_file(mission, step)
                if recovered.get("ok"):
                    self.persistence.save_receipt(
                        mission_id=mission.mission_id, step_id=step.step_id,
                        action_type=step.action_type, target=step.target,
                        result_state=ActionState.VERIFIED, result=recovered,
                        verified_at=time.time())
                    return {"ok": True, "verified": True, "skipped": True,
                            "verification": "ACTION_IN_FLIGHT_RECOVERED"}
            return {"ok": False, "error": "ACTION_IN_FLIGHT_UNKNOWN"}
        self.persistence.save_receipt(
            mission_id=mission.mission_id, step_id=step.step_id,
            action_type=step.action_type, target=step.target,
            result_state=ActionState.IN_FLIGHT_UNKNOWN,
            result={"state": ActionState.IN_FLIGHT_UNKNOWN.value})
        return None

    def _receipt_confirmation_reset(self, mission, step):
        if step.action_type in {"keyboard_type", "keyboard_hotkey", "keyboard_press",
                                "ui_invoke_element", "open_program"}:
            self.persistence.save_receipt(
                mission_id=mission.mission_id, step_id=step.step_id,
                action_type=step.action_type, target=step.target,
                result_state=ActionState.NOT_STARTED,
                result={"confirmation_required": True})

    def _receipt_verified(self, mission, step, result):
        if step.action_type in {"keyboard_type", "keyboard_hotkey", "keyboard_press",
                                "ui_invoke_element", "open_program"}:
            self.persistence.save_receipt(
                mission_id=mission.mission_id, step_id=step.step_id,
                action_type=step.action_type, target=step.target,
                result_state=ActionState.VERIFIED, result=result,
                verified_at=time.time())

    @staticmethod
    def _classify_error(result: dict[str, Any]) -> str:
        error = str(result.get("error") or "").casefold()
        if any(value in error for value in
               ("timeout", "tempor", "navigation", "network")):
            return "TRANSIENT"
        if any(value in error for value in
               ("focus", "window", "stale", "state_changed", "document")):
            return "STATE_CHANGED"
        if any(value in error for value in
               ("confirmation", "permission", "authorized")):
            return "PERMISSION_REQUIRED"
        if any(value in error for value in
               ("captcha", "anti_bot", "source_verification")):
            return "NON_RETRYABLE"
        return "UNKNOWN"

    def _run_from_current(self, mission, task_id, preconfirmed=None):
        started = time.monotonic()
        action_count = 0
        fingerprints: dict[str, int] = {}
        while mission.current_step < len(mission.steps):
            if self._cancel.is_set() or self.service.cancellation.is_cancelled():
                mission.status = MissionStatus.CANCELLED
                mission.error = "Cancelamento solicitado pelo operador."
                return self._finish(mission, False)
            if time.monotonic() - started > mission.timeout_seconds:
                mission.status = MissionStatus.FAILED
                mission.error = "Timeout da missão excedido."
                return self._finish(mission, False)
            action_count += 1
            if action_count > mission.max_steps:
                mission.status = MissionStatus.BLOCKED
                mission.error = "MAX_STEPS_EXCEEDED"
                return self._finish(mission, False)

            step = mission.steps[mission.current_step]
            dependency = self._dependencies_satisfied(mission, step)
            if not dependency.get("ok"):
                mission.status = MissionStatus.BLOCKED
                mission.error = dependency["error"]
                step.status = MissionStepStatus.BLOCKED
                step.error = dependency["dependency"]
                self._audit_step(mission, step, dependency, "blocked")
                return self._finish(mission, False)
            step.attempts += 1
            step.status = MissionStepStatus.OBSERVING
            if step.action_type == "verify_file":
                step.status = MissionStepStatus.VERIFYING
                result = self._verify_file(step)
            elif step.action_type == "extract_mission_value":
                step.status = MissionStepStatus.VERIFYING
                result = self._extract_mission_value(mission, step, task_id)
            elif step.action_type == "handoff_to_notepad":
                result = self._handoff_to_notepad(mission, step)
            elif step.action_type == "capture_document_state":
                result = self._capture_document_state(mission, step, task_id)
            elif step.action_type == "check_overwrite_policy":
                result = self._check_overwrite_policy(mission, step)
            elif step.action_type == "type_mission_template":
                result = self._type_mission_template(mission, step, task_id,
                                                     preconfirmed=preconfirmed)
                preconfirmed = None
            elif step.action_type == "verify_editor_pre_save":
                result = self._verify_editor_content(mission, step, task_id,
                                                     pre_save=True)
            elif step.action_type == "handle_overwrite_confirmation":
                result = self._handle_overwrite_confirmation(
                    mission, step, task_id, preconfirmed=preconfirmed)
                preconfirmed = None
            elif step.action_type == "verify_cross_app_file":
                step.status = MissionStepStatus.VERIFYING
                result = self._verify_cross_app_file(mission, step)
            elif step.action_type == "observe_window":
                result = self._observe_window(step)
            elif step.action_type == "focus_browser":
                result = self._focus_browser(mission)
            elif step.action_type == "observe_browser":
                result = self._observe_browser(mission, step)
            elif step.action_type == "ground_search_field":
                result = self._ground_search_field(mission)
            elif step.action_type == "verify_browser_results":
                step.status = MissionStepStatus.VERIFYING
                result = self._verify_browser_results(mission, step)
            elif step.action_type == "checkpoint":
                result = {"ok": True, "verified": True,
                          "verification": "checkpoint_boundary",
                          "checkpoint_name": step.args.get("name", "")}
            else:
                result = self._execute_tool_step(mission, step, task_id, preconfirmed)
                preconfirmed = None
            if result.get("confirmation_required"):
                self._receipt_confirmation_reset(mission, step)
                mission.status = MissionStatus.WAITING_CONFIRMATION
                mission.pending_confirmation_token = str(result.get("token") or "")
                step.status = MissionStepStatus.WAITING_CONFIRMATION
                step.result = {"confirmation_required": True}
                self._create_checkpoint(mission, "CHECKPOINT_WAITING_CONFIRMATION",
                                        "USER_CONFIRMATION_REQUIRED")
                self._audit_mission(mission, "WAITING_CONFIRMATION", {
                    "step_id": step.step_id})
                self._audit_step(mission, step, result, "waiting_confirmation")
                return self._finish(mission, False)
            if not result.get("ok"):
                if result.get("error") == "USER_CONFIRMATION_REQUIRED":
                    mission.status = MissionStatus.WAITING_CONFIRMATION
                    mission.error = "USER_CONFIRMATION_REQUIRED"
                    step.status = MissionStepStatus.WAITING_CONFIRMATION
                    self._create_checkpoint(mission, "CHECKPOINT_WAITING_CONFIRMATION",
                                            "USER_CONFIRMATION_REQUIRED")
                    self._audit_mission(mission, "WAITING_CONFIRMATION", {
                        "step_id": step.step_id})
                    self._audit_step(mission, step, result, "user_confirmation_required")
                    return self._finish(mission, False)
                if result.get("error") in {
                        "USER_ACTIVITY_DETECTED", "FOREGROUND_CONTENTION",
                        "FOREGROUND_CHANGED_DURING_ATOMIC_ACTION",
                        "FOCUS_ACQUIRE_FAILED"}:
                    return self._pause_for_foreground_state(mission, step, result)
                if result.get("error") in {
                    "NAVIGATION_TIMEOUT", "SEARCH_EXECUTION_FAILED",
                    "SEARCH_PROVIDERS_EXHAUSTED", "NON_CHROME_BROWSER_DETECTED",
                    "CHROME_FOCUS_GUARD_FAILED", "CHROME_WINDOW_PROCESS_MISMATCH",
                    "CHROME_WINDOW_IDENTITY_UNAVAILABLE", "CHROME_NOT_FOUND",
                    "NON_CHROME_BROWSER_DISABLED",
                    "MISSING_MISSION_VARIABLE", "UNRESOLVED_TEMPLATE_VARIABLE",
                    "STALE_CONTEXT_DETECTED", "SOURCE_VERIFICATION_FAILED",
                    "APP_IDENTITY_MISMATCH", "CROSS_APP_DATA_MISMATCH",
                    "APP_SWITCH_LOOP_DETECTED", "EDITOR_CONTENT_EMPTY",
                    "EDITOR_CONTENT_MISMATCH", "STALE_EDITOR_TARGET",
                    "EDITOR_NOT_FOUND", "EDITOR_PROCESS_MISMATCH",
                    "OVERWRITE_CONFIRMATION_NOT_DISMISSED", "DOCUMENT_NOT_FOUND",
                    "DOCUMENT_IDENTITY_UNAVAILABLE", "DOCUMENT_IDENTITY_MISMATCH",
                    "DOCUMENT_WINDOW_MISMATCH", "MISSION_DOCUMENT_NOT_REGISTERED",
                    "DIALOG_OWNERSHIP_MISMATCH", "DEPENDENCY_NOT_SATISFIED",
                    "ACTION_IN_FLIGHT_UNKNOWN", "WORLD_STATE_CHANGED",
                    "STALE_BROWSER_STATE", "CHECKPOINT_CONTEXT_MISMATCH",
                    "CHECKPOINT_INVALID",
                }:
                    mission.status = MissionStatus.BLOCKED
                    mission.error = str(result.get("error"))
                    step.status = MissionStepStatus.BLOCKED
                    self._audit_step(mission, step, result, "blocked")
                    return self._finish(mission, False)
                if self._is_path_not_found(result):
                    self._audit_step(mission, step, result, "path_not_found")
                    if self._recover_path_not_found(mission, step, result):
                        step.status = MissionStepStatus.PENDING
                        mission.status = MissionStatus.OBSERVING
                        continue
                fingerprint = f"{step.step_id}:{result.get('error', '')}:{self._window_fingerprint()}"
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
                step.error = str(result.get("error") or "Etapa falhou")[:500]
                step.result = {"ok": False, "error": step.error}
                self._audit_step(mission, step, result, "failed")
                if fingerprints[fingerprint] >= 2 or step.attempts >= step.max_attempts:
                    mission.status = MissionStatus.BLOCKED
                    mission.error = "ACTION_LOOP_DETECTED"
                    step.status = MissionStepStatus.BLOCKED
                    return self._finish(mission, False)
                mission.result["last_error"] = step.error
                mission.result["last_error_classification"] = self._classify_error(result)
                self._audit_mission(mission, "RETRY_STARTED", {
                    "step_id": step.step_id,
                    "attempt": step.attempts,
                    "classification": mission.result["last_error_classification"],
                })
                time.sleep(min(0.25, 0.05 * step.attempts))
                step.status = MissionStepStatus.PENDING
                mission.status = MissionStatus.OBSERVING
                continue
            step.status = MissionStepStatus.VERIFYING
            if not self._validate_step_result(step, result):
                step.status = MissionStepStatus.FAILED
                step.error = "Pós-condição da etapa não confirmada."
                self._audit_step(mission, step, result, "verification_failed")
                mission.status = MissionStatus.FAILED
                mission.error = step.error
                return self._finish(mission, False)
            self._receipt_verified(mission, step, result)
            step.status = MissionStepStatus.COMPLETED
            step.result = self._safe_step_result(result)
            self._record_step_output(mission, step)
            self._audit_step(mission, step, result, "completed")
            if mission.result.get("recovery_active"):
                if step.step_id == "capture-mission-document":
                    self._audit_context_event(
                        mission, "MISSION_DOCUMENT_RECREATED", "recreated",
                        result, app="notepad", destination="mission_document")
                elif step.step_id == "verify-editor-pre-save":
                    self._audit_context_event(
                        mission, "EDITOR_REVERIFIED", "verified", result,
                        app="notepad", destination="mission_document")
                elif step.step_id == "checkpoint-text-verified":
                    self._audit_context_event(
                        mission, "APP_RECOVERY_COMPLETED", "completed",
                        {"ok": True}, app="notepad", destination="save_stage")
            mission.current_step += 1
            mission.status = MissionStatus.OBSERVING
            checkpoint_name = str(step.args.get("name") or "") \
                if step.action_type == "checkpoint" else ""
            if checkpoint_name:
                checkpoint = self._create_checkpoint(mission, checkpoint_name, "")
                if not checkpoint.get("ok"):
                    mission.status = MissionStatus.BLOCKED
                    mission.error = checkpoint.get("error", "CHECKPOINT_FAILED")
                    return self._finish(mission, False)
                pause_name = str(mission.result.get("pause_after_checkpoint") or "")
                if pause_name == checkpoint_name or self._pause_requested.is_set():
                    mission.status = MissionStatus.PAUSED
                    mission.error = ""
                    self._audit_mission(mission, "MISSION_PAUSED", {
                        "checkpoint_id": checkpoint.get("checkpoint_id"),
                        "reason": self._pause_reason or "checkpoint_boundary",
                    })
                    return self._finish(mission, False)

        mission.status = MissionStatus.COMPLETED
        if mission.result.get("multi_app_mission"):
            final = mission.steps[-1].result
            mission.result.update({
                "mission_completed": True,
                "file_exists": bool(final.get("file_exists")),
                "content_valid": bool(final.get("content_valid")),
                "cross_app_data_match": bool(final.get("cross_app_data_match")),
                "variable_stored": bool(mission.context and mission.context.variables),
                "provenance_stored": bool(mission.context and mission.context.source_provenance),
                "context_version": mission.context.context_version if mission.context else 0,
                "current_app": mission.context.current_app if mission.context else "",
                "document_ownership": mission.result.get("document_ownership", ""),
                "mission_document_id": mission.result.get("mission_document_id", ""),
            })
        elif mission.result.get("browser_mission"):
            mission.result.update({"mission_completed": True,
                                   "result_count": len(mission.result.get("titles", []))})
        else:
            recovered_metadata = ({
                key: mission.result[key]
                for key in ("recovered_from_checkpoint", "checkpoint_id",
                            "resume_token", "completed_checkpoints")
                if key in mission.result
            } if mission.result.get("recovered_from_checkpoint") else {})
            mission.result = {
                **recovered_metadata,
                "mission_completed": True,
                "file_exists": bool(mission.steps[-1].result.get("file_exists"))
                if mission.steps else False,
                "content_valid": bool(mission.steps[-1].result.get("content_valid"))
                if mission.steps else False,
            }
        return self._finish(mission, True)

    def _execute_tool_step(self, mission, step, task_id, preconfirmed):
        if preconfirmed and preconfirmed[0] is step:
            return preconfirmed[1]
        if step.action_type == "browser_search":
            mission.result["search_query"] = str(step.args.get("query") or "")
        if step.action_type == "browser_search":
            ref = str(mission.result.get("search_ref") or "")
            if not ref:
                return {"ok": False, "error": "SEARCH_FIELD_NOT_GROUNDED"}
            step.args["ref"] = ref
            guard = self._observe_browser(mission, step)
            if not guard.get("ok"):
                return guard
        if step.action_type in self._ACTION_TOOLS:
            guard = self._observe_window(step)
            if (not guard.get("ok") and step.app == "notepad" and
                    guard.get("error") == "CORRECT_WINDOW_NOT_FOCUSED"):
                foreground = self._foreground_guard(mission, task_id, step.app)
                if not foreground.get("ok"):
                    return foreground
                refocused = self.service.execute_tool(
                    "ui_focus_window", {"window": "notepad"},
                    command=f"computer_mission:{mission.mission_id}:refocus_notepad",
                    task_id=task_id)
                if refocused.get("ok"):
                    guard = self._observe_window(step)
            if not guard.get("ok"):
                return guard
        if (step.app in {"notepad", "chrome"} and step.action_type in {
                "ui_focus_window", "ui_focus_element", "ui_invoke_element",
                "keyboard_type", "keyboard_hotkey", "keyboard_press"}):
            foreground = self._foreground_guard(mission, task_id, step.app)
            if not foreground.get("ok"):
                return foreground
        if (mission.result.get("multi_app_mission") and step.app == "notepad" and
                step.step_id not in {"focus-notepad", "observe-notepad",
                                     "capture-preexisting-document",
                                     "new-notepad-document", "capture-mission-document"}):
            ownership = self._assert_mission_document(mission, task_id)
            if not ownership.get("ok"):
                return ownership
        receipt_result = self._receipt_before_action(mission, step)
        if receipt_result is not None:
            if receipt_result.get("skipped"):
                self._audit_mission(mission, "STEP_SKIPPED_ALREADY_VERIFIED", {
                    "step_id": step.step_id})
            return receipt_result
        step.status = MissionStepStatus.EXECUTING
        scoped = step.action_type in {
            "keyboard_type", "keyboard_hotkey", "keyboard_press",
            "ui_type_editor",
        } and step.step_id not in {"confirm-save", "handle-overwrite-confirmation"}
        try:
            result = self.service.execute_tool(
                step.action_type, step.args,
                command=f"computer_mission:{mission.mission_id}",
                task_id=task_id,
                authorization_scope=(COMPUTER_USE_MISSION_PRE_SAVE if scoped else ""))
        except TypeError as exc:
            if "unexpected keyword argument 'authorization_scope'" not in str(exc):
                raise
            result = self.service.execute_tool(
                step.action_type, step.args,
                command=f"computer_mission:{mission.mission_id}",
                task_id=task_id)
        if (step.action_type == "ui_focus_window" and not result.get("ok") and
                result.get("error") in {"FOCUS_ACQUIRE_FAILED",
                                         "CHROME_FOCUS_GUARD_FAILED",
                                         "WINDOW_NOT_FOUND", "window_not_found"}):
            return {**result, "error": "FOREGROUND_CONTENTION",
                    "pause_reason": "FOREGROUND_CONTENTION"}
        if result.get("confirmation_required"):
            self._receipt_confirmation_reset(mission, step)
        return result

    def _resume_revalidate(self, mission, step, task_id):
        """Re-observe mission-owned state before consuming a confirmation."""
        if step.app in {"notepad", "chrome"}:
            foreground = self._foreground_guard(mission, task_id, step.app)
            if not foreground.get("ok"):
                return foreground
        if not mission.result.get("multi_app_mission") or step.app != "notepad":
            return {"ok": True, "verification": "resume_revalidation_not_required"}
        if step.step_id == "new-notepad-document":
            return self._assert_preexisting_document(mission, task_id)
        if step.action_type == "handle_overwrite_confirmation":
            dialog = self.service.execute_tool(
                "ui_classify_dialog", {},
                command=f"computer_mission:{mission.mission_id}:resume_dialog",
                task_id=task_id)
            if dialog.get("dialog_type") != "FILE_OVERWRITE_DIALOG":
                return {"ok": False, "error": "DIALOG_OWNERSHIP_MISMATCH"}
        return self._assert_mission_document(mission, task_id)

    def _assert_preexisting_document(self, mission, task_id):
        """Ensure a confirmed tab action still targets the protected document."""
        artifacts = mission.context.artifacts if mission.context else {}
        pre_existing = set(artifacts.get("pre_existing_document_ids") or [])
        if not pre_existing:
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        observed = self._read_notepad_editor(
            mission, task_id, "preexisting_guard")
        if observed.get("path_error_dialog"):
            return {"ok": False, "error": "PATH_NOT_FOUND", "path_error_dialog": True}
        if not observed.get("found") or not observed.get("verified"):
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        editor = observed.get("editor") or {}
        current_id = str(editor.get("document_identity") or "")
        if current_id not in pre_existing:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "current_document_id": current_id,
                    "pre_existing_document_ids": sorted(pre_existing)}
        expected_window = int((artifacts.get("pre_existing_documents") or [{}])[0].get("window_id") or 0)
        current_window = int((observed.get("window") or {}).get("handle") or 0)
        if expected_window and current_window != expected_window:
            return {"ok": False, "error": "DOCUMENT_WINDOW_MISMATCH",
                    "pre_existing_window_id": expected_window,
                    "current_window_id": current_window}
        return {"ok": True, "verified": True,
                "verification": "pre_existing_document_revalidated",
                "document_identity": current_id}

    def _cancelled_result(self):
        return {"ok": False, "error": "MISSION_CANCELLED"}

    def _record_step_output(self, mission, step):
        if not mission.context:
            return
        mission.context.step_outputs[step.step_id] = dict(step.result)
        if step.app and not mission.context.current_app:
            mission.context.current_app = step.app
        mission.context.updated_at = time.time()

    def _audit_context_event(self, mission, tool, status, result, *, app="",
                             previous_app="", source_variable="", destination=""):
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool=tool,
            arguments={
                "mission_id": mission.mission_id,
                "app": app,
                "previous_app": previous_app,
                "source_variable": source_variable,
                "destination": destination,
            },
            risk=mission.risk_level,
            status=status,
            result={"ok": bool(result.get("ok")), "error": result.get("error", "")},
        )

    @staticmethod
    def _browser_read_scope(mission, target_url):
        official_host = str(mission.result.get("official_host") or "").strip()
        allowed_hosts = [official_host] if official_host else []
        if official_host.casefold().startswith("www."):
            allowed_hosts.append(official_host[4:])
        return {
            "authorization_scope": READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
            "target_url": str(target_url or ""),
            "allowed_hosts": tuple(allowed_hosts),
        }

    def _execute_browser_read(self, name, arguments, **kwargs):
        """Call scoped browser reads while keeping legacy test doubles compatible."""
        try:
            return self.service.execute_tool(name, arguments, **kwargs)
        except TypeError as exc:
            if "unexpected keyword argument 'authorization_scope'" not in str(exc):
                raise
            legacy_kwargs = {
                key: value for key, value in kwargs.items()
                if key not in {"authorization_scope", "target_url", "allowed_hosts",
                               "page_barrier"}
            }
            return self.service.execute_tool(name, arguments, **legacy_kwargs)

    def _mission_run_id(self, mission, task_id):
        task_manager = getattr(self.service, "task_manager", None)
        database = getattr(task_manager, "database", None)
        if database is None or not task_id:
            return ""
        try:
            runs = database.list_task_runs(str(task_id))
        except (AttributeError, OSError, TypeError):
            return ""
        for run in runs or []:
            if str(run.get("mission_id") or "") == mission.mission_id:
                return str(run.get("run_id") or "")
        return ""

    def _extract_mission_value(self, mission, step, task_id=""):
        key = str(step.args.get("source_variable") or
                  mission.result.get("value_key") or "python_version")
        mode = str(step.args.get("value_kind") or
                   ("title" if key in {"python_page_title", "ollama_page_title"}
                    else "version"))
        hosts = (("python.org", ".python.org") if key != "ollama_page_title"
                 else ("ollama.com", ".ollama.com"))
        version_re = re.compile(
            r"\bPython\s+([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b", re.I)
        execution_task_id = str(task_id or "")
        execution_run_id = self._mission_run_id(mission, execution_task_id)

        for attempt in range(MAX_SEARCH_PROVIDERS):
            if self._cancel.is_set() or self.service.cancellation.is_cancelled():
                return self._cancelled_result()
            target_url = _resolved_result_url(str(
                mission.result.get("browser_url") or mission.result.get("source_url") or ""))
            read_scope = self._browser_read_scope(mission, target_url)
            observation_method = "browser_get_page_info"
            self._execute_browser_read(
                "browser_wait_for_results", {"timeout_ms": 10000},
                command="computer_mission:extract_value_wait",
                task_id=mission.mission_id, **read_scope)
            page_result = self._execute_browser_read(
                "browser_get_page_info", {}, command="computer_mission:extract_value",
                task_id=mission.mission_id, **read_scope)
            if page_result.get("confirmation_required"):
                self._audit_mission(mission, "BROWSER_READ_SCOPE_DENIED", {
                    "scope": READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
                    "target_url": target_url,
                    "allowed_hosts": read_scope.get("allowed_hosts"),
                })
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": "BROWSER_READ_SCOPE"}
            page = page_result.get("page") or {}
            if not page_result.get("ok") or not page:
                # A transient DOM extraction failure is not an authorization request.
                # Re-observe the already-authorized public page through browser health
                # before failing the mission, without clicking or navigating.
                health_result = self._execute_browser_read(
                    "browser_health", {}, command="computer_mission:extract_value_health",
                    task_id=mission.mission_id, **read_scope)
                health_url = _resolved_result_url(str(
                    health_result.get("current_url") or ""))
                health_title = " ".join(str(
                    health_result.get("page_title") or "").split())
                if (health_result.get("ok") and health_url and health_title and
                        health_url == target_url and
                        classify_page_barrier({"url": health_url,
                                               "title": health_title}) == "NONE"):
                    page = {"url": health_url, "title": health_title,
                            "text": "", "links": [], "interactive": [],
                            "forms": [], "barrier_type": "NONE"}
                    observation_method = "browser_health"
                    self._audit_mission(mission, "BROWSER_READ_HEALTH_FALLBACK", {
                        "scope": READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
                        "source": "browser_health",
                        "target_url": health_url,
                        "original_error": page_result.get("error", ""),
                    })
                else:
                    self._audit_mission(mission, "BROWSER_READ_FAILED", {
                        "scope": READ_ONLY_PUBLIC_BROWSER_OBSERVATION,
                        "target_url": target_url,
                        "error": page_result.get("error", ""),
                        "health_error": health_result.get("error", ""),
                    })
                    return {"ok": False, "error": "BROWSER_READ_FAILURE",
                            "detail": {"page": page_result.get("error", ""),
                                       "health": health_result.get("error", "")}}
            barrier = classify_page_barrier(page, page.get("interactive"))
            if barrier == "COOKIE_CONSENT":
                elements_result = self.service.execute_tool(
                    "browser_get_elements", {},
                    command="computer_mission:extract_value_consent",
                    task_id=mission.mission_id)
                consent = self._handle_cookie_consent(
                    mission, page, elements_result.get("elements") or [])
                if not consent.get("ok"):
                    return consent
                continue
            if barrier in {"UNKNOWN_BLOCKER", "LOGIN_REQUIRED", "AUTH_REQUIRED",
                           "PRIVACY_CONSENT", "BENIGN_INTERSTITIAL"}:
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": barrier}
            current_url = _resolved_result_url(str(page.get("url") or ""))
            current_host = urlparse(current_url).netloc.casefold()
            if (mode == "title" and barrier == "NONE" and
                    (current_host == hosts[0] or current_host.endswith(hosts[1]))):
                page_title = " ".join(str(page.get("title") or "").split())
                if page_title and not re.fullmatch(r"(?:https?://|www\.)\S+", page_title, re.I):
                    stored = mission.context.store_variable(
                        key, page_title, kind="OBSERVED_VALUE", source_app="chrome",
                        source_type="browser_page", source_title=page_title,
                        source_url=current_url, confidence="verified",
                        source_state_id=str(mission.result.get("browser_page_state_id") or current_url),
                        valid_until_step=mission.current_step + mission.max_steps)
                    provenance = stored.public()
                    provenance.update({
                        "observed_value": page_title,
                        "observation_method": observation_method,
                        "task_id": execution_task_id,
                        "run_id": execution_run_id,
                        "mission_id": mission.mission_id,
                    })
                    mission.context.source_provenance[key] = provenance
                    mission.result.update({
                        key: page_title, "value_extracted": True, "source_found": True,
                        "source_verified": True, "source_provenance": provenance,
                        "final_url": current_url,
                    })
                    self._audit_context_event(
                        mission, "CONTEXT_VALUE_CREATED", "stored", {"ok": True},
                        app="chrome", source_variable=key, destination="mission_context")
                    return {"ok": True, "verified": True,
                            "verification": "observed_official_page_title", "value": page_title,
                            "source_variable": key, "source_url": current_url,
                            "source_title": page_title}
            candidates = [item for item in list(page.get("links") or [])
                          if item.get("visible", True) and item.get("result_candidate")]
            official = [item for item in candidates if (
                urlparse(_resolved_result_url(str(item.get("href") or ""))).netloc.casefold() == hosts[0] or
                urlparse(_resolved_result_url(str(item.get("href") or ""))).netloc.casefold().endswith(hosts[1]))]
            selected = None
            version_match = None
            if official and barrier == "NONE":
                if mode == "version":
                    for item in official:
                        haystack = " ".join(
                            str(item.get(field) or "")
                            for field in ("text", "aria_label", "title"))
                        version_match = version_re.search(haystack)
                        if version_match:
                            selected = item
                            break
                else:
                    selected = official[0]
            if selected is not None:
                source_title = " ".join(
                    " ".join(str(selected.get(field) or "").split())
                    for field in ("text", "title") if selected.get(field)
                ).strip()
                source_url = _resolved_result_url(str(selected.get("href") or ""))
                if mode == "title" and re.fullmatch(
                        r"(?:https?://|www\.)\S+", source_title, re.I):
                    navigated = self.service.execute_tool(
                        "browser_navigate", {"url": source_url},
                        command="computer_mission:official_source_title",
                        task_id=mission.mission_id)
                    if not navigated.get("ok"):
                        selected = None
                    else:
                        observed = self._observe_browser(
                            mission,
                            ComputerMissionStep(
                                "official-source-observe",
                                "Observar título da fonte oficial",
                                "observe_browser", expected_state={}, app="chrome"))
                        if not observed.get("ok"):
                            return observed
                        official_page = self.service.execute_tool(
                            "browser_get_page_info", {},
                            command="computer_mission:official_source_title",
                            task_id=mission.mission_id)
                        page_title = " ".join(str(
                            (official_page.get("page") or {}).get("title") or ""
                        ).split())
                        if page_title and not re.fullmatch(
                                r"(?:https?://|www\.)\S+", page_title, re.I):
                            source_title = page_title
                        else:
                            selected = None
                value = (f"Python {version_match.group(1)}"
                         if mode == "version" and version_match else source_title)
                if selected is not None and value:
                    state_id = str(mission.result.get("browser_page_state_id") or
                                   page.get("url") or "")
                    stored = mission.context.store_variable(
                        key, value, kind="OBSERVED_VALUE", source_app="chrome",
                        source_type="browser_result", source_title=source_title,
                        source_url=source_url, confidence="verified",
                        source_state_id=state_id,
                        valid_until_step=mission.current_step + mission.max_steps)
                    mission.result.update({
                        key: value, "value_extracted": True, "source_found": True,
                        "source_verified": True, "source_provenance": stored.public(),
                    })
                    self._audit_context_event(
                        mission, "CONTEXT_VALUE_CREATED", "stored", {"ok": True},
                        app="chrome", source_variable=key, destination="mission_context")
                    return {"ok": True, "verified": True,
                            "verification": "observed_official_value", "value": value,
                            "source_variable": key, "source_url": source_url,
                            "source_title": source_title}
            if attempt >= MAX_SEARCH_PROVIDERS - 1:
                break
            fallback = self._advance_provider(mission, "SOURCE_VERIFICATION_FAILED")
            if not fallback.get("ok"):
                break
            prepared = self._prepare_search_provider(mission)
            if not prepared.get("ok"):
                if prepared.get("error") == "USER_CONFIRMATION_REQUIRED":
                    return prepared
                continue
            search = self.service.execute_tool(
                "browser_search", {"query": mission.result.get("search_query", ""),
                                    "ref": mission.result.get("search_ref", "")},
                command="computer_mission:value_provider_search",
                task_id=mission.mission_id)
            if not search.get("ok"):
                continue
            observed = self._observe_browser(
                mission, ComputerMissionStep("value-provider-observe",
                                             "Observar provider de valor", "observe_browser",
                                             expected_state={"page_changed": True}, app="chrome"))
            if not observed.get("ok"):
                continue
        return {"ok": False, "error": "SOURCE_VERIFICATION_FAILED"}

    def _handoff_to_notepad(self, mission, step):
        context = mission.context
        if not context:
            return {"ok": False, "error": "MISSING_MISSION_CONTEXT"}
        if self._cancel.is_set() or self.service.cancellation.is_cancelled():
            return self._cancelled_result()
        if context.app_switches >= self.MAX_APP_SWITCHES:
            return {"ok": False, "error": "APP_SWITCH_LOOP_DETECTED"}
        guard = self._foreground_guard(mission, mission.mission_id, "notepad")
        if not guard.get("ok"):
            return guard
        previous = context.current_app
        self._audit_context_event(
            mission, "APP_HANDOFF_STARTED", "switching", {"ok": True},
            app="notepad", previous_app=previous, destination="notepad")
        opened = self.service.execute_tool(
            "open_program", {"name": step.args.get("name", "bloco de notas")},
            command=f"computer_mission:{mission.mission_id}", task_id=mission.mission_id)
        if opened.get("confirmation_required"):
            return opened
        if not opened.get("ok"):
            return {"ok": False, "error": "APP_HANDOFF_FAILED"}
        if self._cancel.is_set() or self.service.cancellation.is_cancelled():
            return self._cancelled_result()
        focused = {}
        data = {}
        for _ in range(self.MAX_FOCUS_RECOVERY_ATTEMPTS):
            guard = self._foreground_guard(mission, mission.mission_id, "notepad")
            if not guard.get("ok"):
                return guard
            focused = self.service.execute_tool(
                "ui_focus_window", {"window": "notepad"},
                command=f"computer_mission:{mission.mission_id}",
                task_id=mission.mission_id)
            if focused.get("confirmation_required"):
                return focused
            active = self.service.execute_tool(
                "ui_active_window", {},
                command=f"computer_mission:{mission.mission_id}",
                task_id=mission.mission_id)
            data = active.get("result") if isinstance(active.get("result"), dict) else active
            process = str(data.get("process_name") or "").casefold()
            if focused.get("ok") and process == "notepad.exe":
                break
            time.sleep(0.2)
        else:
            return {"ok": False, "error": "FOREGROUND_CONTENTION",
                    "pause_reason": "FOREGROUND_CONTENTION", "window": data}
        context.previous_app = previous
        context.current_app = "notepad"
        context.app_switches += 1
        context.context_version += 1
        context.updated_at = time.time()
        result = {"ok": True, "verified": True, "verification": "app_handoff_completed",
                  "window": data, "previous_app": previous, "app": "notepad"}
        self._audit_context_event(
            mission, "APP_HANDOFF_COMPLETED", "completed", result,
            app="notepad", previous_app=previous, destination="notepad")
        return result

    def _read_notepad_editor(self, mission, task_id, purpose):
        """Re-ground the live editor across short foreground/UIA races."""
        observed = {}
        for attempt in range(4):
            observed = self.service.execute_tool(
                "ui_read_editor", {"window": "notepad", "expected_process": "notepad"},
                command=f"computer_mission:{mission.mission_id}:{purpose}",
                task_id=task_id)
            if observed.get("found") and observed.get("verified"):
                return observed
            if observed.get("path_error_dialog"):
                return observed
            if attempt < 3:
                foreground = self._foreground_guard(mission, task_id, "notepad")
                if not foreground.get("ok"):
                    return foreground
                self.service.execute_tool(
                    "ui_focus_window", {"window": "notepad"},
                    command=f"computer_mission:{mission.mission_id}:refocus_editor",
                    task_id=task_id)
                time.sleep(0.2)
        return observed

    def _capture_document_state(self, mission, step, task_id):
        observed = self._read_notepad_editor(mission, task_id, "document_state")
        if observed.get("error") in {"USER_ACTIVITY_DETECTED",
                                      "FOREGROUND_CONTENTION"}:
            return observed
        if observed.get("path_error_dialog"):
            return {"ok": False, "error": "PATH_NOT_FOUND", "path_error_dialog": True}
        if not observed.get("found") or not observed.get("verified"):
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        editor = observed.get("editor") or {}
        document_id = str(editor.get("document_identity") or "")
        window = observed.get("window") or {}
        if not document_id or not window.get("handle"):
            return {"ok": False, "error": "DOCUMENT_IDENTITY_UNAVAILABLE"}
        tabs = self.service.execute_tool(
            "ui_list_elements", {"window": "notepad", "limit": 100},
            command=f"computer_mission:{mission.mission_id}:document_tabs",
            task_id=task_id)
        tab_records = [item for item in (tabs.get("elements") or [])
                       if str(item.get("control_type") or "").casefold() == "tabitem"]
        owned = step.step_id == "capture-mission-document"
        artifacts = mission.context.artifacts
        if not owned:
            existing = set(artifacts.get("pre_existing_document_ids") or [])
            existing.add(document_id)
            artifacts["pre_existing_document_ids"] = sorted(existing)
            artifacts["pre_existing_documents"] = [{
                "document_id": document_id, "window_id": window.get("handle"),
                "process_id": window.get("pid"), "content_state_id": editor.get("content_state_id"),
            }]
            artifacts["pre_existing_tabs"] = tab_records
            mission.result["document_ownership"] = "PRE_EXISTING_DOCUMENT_PROTECTED"
            return {"ok": True, "verified": True,
                    "verification": "pre_existing_document_recorded",
                    "document_identity": document_id,
                    "pre_existing_document": True}
        if document_id in set(artifacts.get("pre_existing_document_ids") or []):
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "document_identity": document_id}
        artifacts.update({
            "mission_document_id": document_id,
            "mission_window_id": int(window.get("handle") or 0),
            "mission_document_content_state_id": editor.get("content_state_id", ""),
            "mission_document_created_by_mission": True,
            "mission_document_app": "notepad",
            "mission_document_tabs": tab_records,
        })
        mission.result.update({
            "mission_document_id": document_id,
            "mission_window_id": int(window.get("handle") or 0),
            "document_ownership": "OWNED_BY_CURRENT_MISSION",
        })
        return {"ok": True, "verified": True,
                "verification": "mission_document_registered",
                "document_identity": document_id,
                "mission_document_id": document_id,
                "created_by_mission": True}

    def _assert_mission_document(self, mission, task_id, *, expected_text=None):
        artifacts = mission.context.artifacts if mission.context else {}
        mission_document_id = str(artifacts.get("mission_document_id") or "")
        if not mission_document_id:
            return {"ok": False, "error": "MISSION_DOCUMENT_NOT_REGISTERED"}
        observed = self._read_notepad_editor(mission, task_id, "document_guard")
        if observed.get("error") in {"USER_ACTIVITY_DETECTED",
                                      "FOREGROUND_CONTENTION"}:
            return observed
        if observed.get("path_error_dialog"):
            return {"ok": False, "error": "PATH_NOT_FOUND", "path_error_dialog": True}
        if not observed.get("found") or not observed.get("verified"):
            return {"ok": False, "error": "DOCUMENT_NOT_FOUND"}
        editor = observed.get("editor") or {}
        current_id = str(editor.get("document_identity") or "")
        if current_id != mission_document_id:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "mission_document_id": mission_document_id,
                    "current_document_id": current_id}
        expected_window = int(artifacts.get("mission_window_id") or 0)
        current_window = int((observed.get("window") or {}).get("handle") or 0)
        if expected_window and current_window != expected_window:
            return {"ok": False, "error": "DOCUMENT_WINDOW_MISMATCH",
                    "mission_window_id": expected_window,
                    "current_window_id": current_window}
        actual = str(observed.get("text") or "")
        if expected_text is not None and actual == "":
            return {"ok": False, "error": "EDITOR_CONTENT_EMPTY",
                    "editor_text": actual}
        if expected_text is not None and actual != str(expected_text):
            return {"ok": False, "error": "EDITOR_CONTENT_MISMATCH",
                    "editor_text": actual}
        return {"ok": True, "verified": True,
                "verification": "mission_document_identity_match",
                "mission_document_id": mission_document_id,
                "editor_text": actual,
                "content_state_id": editor.get("content_state_id", "")}

    def _check_overwrite_policy(self, mission, step):
        path = Path(step.target)
        authorized = {
            str(Path(item).resolve())
            for item in mission.result.get("authorized_overwrite_paths", [])
        }
        created = {
            str(Path(item).resolve())
            for item in (mission.context.artifacts.get("created_paths", [])
                         if mission.context else [])
        }
        if path.exists() and str(path.resolve()) not in authorized | created:
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": "overwrite_existing_file", "path": str(path)}
        verification = ("authorized_overwrite_target" if path.exists()
                        else "overwrite_policy_clear")
        return {"ok": True, "verified": True, "verification": verification,
                "path": str(path)}

    def _render_template(self, mission, template):
        context = mission.context
        if not context:
            return None, "MISSING_MISSION_CONTEXT", []
        names = re.findall(r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}", template)
        rendered = str(template)
        consumed = []
        for name in names:
            stored, error = context.resolve(
                name, mission_id=mission.mission_id, current_step=mission.current_step)
            if error:
                return None, error, consumed
            rendered = re.sub(r"\{\{\s*" + re.escape(name) + r"\s*\}\}",
                              stored.value, rendered, count=1)
            consumed.append(name)
            self._audit_context_event(
                mission, "CONTEXT_VALUE_CONSUMED", "consumed", {"ok": True},
                app="notepad", source_variable=name, destination="keyboard_type")
        if "{{" in rendered or "}}" in rendered:
            return None, "UNRESOLVED_TEMPLATE_VARIABLE", consumed
        return rendered, "", consumed

    def _type_mission_template(self, mission, step, task_id, preconfirmed=None):
        rendered, error, consumed = self._render_template(
            mission, str(step.args.get("template") or ""))
        if error:
            return {"ok": False, "error": error}
        foreground = self._foreground_guard(mission, task_id, "notepad")
        if not foreground.get("ok"):
            return foreground
        guard = self._observe_window(step)
        if (not guard.get("ok") and
                guard.get("error") == "CORRECT_WINDOW_NOT_FOCUSED"):
            refocused = self.service.execute_tool(
                "ui_focus_window", {"window": "notepad"},
                command=f"computer_mission:{mission.mission_id}:refocus_notepad_editor",
                task_id=task_id)
            if refocused.get("ok"):
                guard = self._observe_window(step)
        if not guard.get("ok"):
            return guard
        ownership = self._assert_mission_document(mission, task_id)
        if not ownership.get("ok"):
            return ownership
        if self._cancel.is_set() or self.service.cancellation.is_cancelled():
            return self._cancelled_result()
        mission_id = str(mission.context.artifacts.get("mission_document_id") or "")
        typed = (preconfirmed[1]
                 if preconfirmed and preconfirmed[0] is step else None)
        if typed is not None and not typed.get("ok"):
            return typed
        if typed is None:
            editor_args = {
                "window": "notepad", "expected_process": "notepad",
                "text": rendered,
                "interval": step.args.get("interval", 0.03),
            }
            try:
                typed = self.service.execute_tool(
                    "ui_type_editor", editor_args,
                    command=f"computer_mission:{mission.mission_id}", task_id=task_id,
                    authorization_scope=COMPUTER_USE_MISSION_PRE_SAVE)
            except TypeError as exc:
                if "unexpected keyword argument 'authorization_scope'" not in str(exc):
                    raise
                typed = self.service.execute_tool(
                    "ui_type_editor", editor_args,
                    command=f"computer_mission:{mission.mission_id}", task_id=task_id)
        if typed.get("confirmation_required"):
            return typed
        if not typed.get("ok"):
            reason = str(typed.get("reason") or typed.get("error") or "")
            if typed.get("path_error_dialog"):
                return {"ok": False, "error": "PATH_NOT_FOUND",
                        "path_error_dialog": True}
            error = ("EDITOR_PROCESS_MISMATCH" if reason == "process_mismatch"
                     else "EDITOR_NOT_FOUND" if reason in {
                         "window_not_found", "editor_not_found", "focus_unavailable",
                         "editor_reread_failed"}
                     else "EDITOR_CONTENT_MISMATCH" if reason == "editor_content_mismatch"
                     else typed.get("error") or reason or "EDITOR_NOT_FOUND")
            return {**typed, "ok": False, "error": error}
        typed_id = str((typed.get("editor") or {}).get("document_identity") or
                       typed.get("editor_identity") or "")
        if typed_id != mission_id:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "mission_document_id": mission_id,
                    "current_document_id": typed_id}
        mission.context.artifacts["text_input_sent"] = True
        verified = self._verify_editor_content(mission, step, task_id)
        if not verified.get("ok"):
            return verified
        mission.context.artifacts["rendered_text"] = {
            "value": rendered, "kind": "DERIVED_VALUE",
            "source_variables": consumed, "context_version": mission.context.context_version,
        }
        return {"ok": True, "verified": True,
                "verification": "template_resolved_typed_and_editor_verified",
                "text": rendered, "source_variable": consumed,
                "text_input_sent": True, "editor_content_verified": True,
                "mission_to_editor_match": True,
                "editor_identity": verified.get("editor_identity"),
                "content_state_id": verified.get("content_state_id")}

    def _verify_editor_content(self, mission, step, task_id, pre_save=False):
        rendered = str((mission.context.artifacts.get("rendered_text") or {}).get("value") or "")
        if not rendered:
            # During the first verification the rendered text is still carried
            # by the current template step.
            rendered, error, _ = self._render_template(
                mission, str(step.args.get("template") or ""))
            if error:
                return {"ok": False, "error": error}
        foreground = self._foreground_guard(mission, task_id, "notepad")
        if not foreground.get("ok"):
            return foreground
        guard = self._observe_window(step)
        if not guard.get("ok"):
            return guard
        ownership = self._assert_mission_document(
            mission, task_id, expected_text=rendered)
        if not ownership.get("ok"):
            return ownership
        observed = self._read_notepad_editor(mission, task_id, "read_editor")
        if not observed.get("found") or not observed.get("verified"):
            if observed.get("path_error_dialog"):
                return {"ok": False, "error": "PATH_NOT_FOUND",
                        "path_error_dialog": True}
            reason = str(observed.get("reason") or "")
            return {"ok": False,
                    "error": ("EDITOR_PROCESS_MISMATCH" if reason == "process_mismatch"
                               else "EDITOR_NOT_FOUND"),
                    "editor_content_verified": False}
        editor = observed.get("editor") or {}
        actual = str(observed.get("text") or "")
        mission_document_id = str(mission.context.artifacts.get("mission_document_id") or "")
        if str(editor.get("document_identity") or "") != mission_document_id:
            return {"ok": False, "error": "DOCUMENT_IDENTITY_MISMATCH",
                    "editor_content_verified": False}
        if actual == "":
            return {"ok": False, "error": "EDITOR_CONTENT_EMPTY",
                    "editor_content_verified": False, "editor_identity": editor.get("document_identity")}
        if actual != rendered:
            return {"ok": False, "error": "EDITOR_CONTENT_MISMATCH",
                    "editor_content_verified": False, "editor_text": actual,
                    "editor_identity": editor.get("document_identity")}
        identity = str(editor.get("document_identity") or "")
        previous_identity = str(mission.context.artifacts.get("editor_identity") or "")
        if pre_save and previous_identity and identity != previous_identity:
            return {"ok": False, "error": "STALE_EDITOR_TARGET",
                    "editor_content_verified": False,
                    "editor_identity": identity, "previous_editor_identity": previous_identity}
        mission.context.artifacts["editor_identity"] = identity
        mission.context.artifacts["editor_content_state_id"] = editor.get("content_state_id", "")
        mission.context.artifacts["editor_text"] = {
            "value": actual, "kind": "OBSERVED_VALUE",
            "document_identity": identity,
            "content_state_id": editor.get("content_state_id", ""),
        }
        mission.context.artifacts["editor_content_verified"] = True
        mission.context.artifacts["mission_to_editor_match"] = actual == rendered
        return {"ok": True, "verified": True,
                "verification": "editor_content_exact_match",
                "editor_content_verified": True,
                "mission_to_editor_match": actual == rendered,
                "editor_identity": identity,
                "content_state_id": editor.get("content_state_id", ""),
                "editor_text": actual}

    def _verify_cross_app_file(self, mission, step):
        rendered = str((mission.context.artifacts.get("rendered_text") or {}).get("value") or "")
        path = Path(mission.result.get("target_path") or step.target)
        try:
            exists = path.is_file()
            content = path.read_text(encoding="utf-8") if exists else ""
        except OSError as exc:
            return {"ok": False, "error": type(exc).__name__,
                    "file_exists": False, "content_valid": False,
                    "path_error": "PATH_NOT_FOUND" if getattr(exc, "errno", None) == 2 else ""}
        stored, error = mission.context.resolve(
            str(mission.result.get("value_key") or "python_version"),
            mission_id=mission.mission_id, current_step=mission.current_step)
        value_match = bool(stored and stored.value in content)
        content_valid = bool(exists and content == rendered)
        cross_match = bool(content_valid and value_match and rendered)
        if exists and cross_match:
            mission.context.artifacts.setdefault("created_paths", []).append(str(path))
        return {"ok": cross_match and not error, "verified": cross_match and not error,
                "verification": "filesystem_and_context_match",
                "file_exists": exists, "content_valid": content_valid,
                "cross_app_data_match": cross_match, "path": str(path),
                "context_error": error}

    def _handle_overwrite_confirmation(self, mission, step, task_id,
                                        preconfirmed=None):
        target = str(mission.result.get("target_path") or "")
        if preconfirmed and preconfirmed[0] is step:
            result = preconfirmed[1]
            if not result.get("ok"):
                return result
        else:
            dialog = self.service.execute_tool(
                "ui_classify_dialog", {},
                command=f"computer_mission:{mission.mission_id}:overwrite_guard",
                task_id=task_id)
            dialog_type = str(dialog.get("dialog_type") or "UNKNOWN")
            if dialog_type == "UNSAVED_DOCUMENT_DIALOG":
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": dialog_type, "dialog_ownership": "unknown"}
            if dialog_type == "NONE":
                return {"ok": True, "verified": True,
                        "verification": "overwrite_confirmation_not_required"}
            if dialog_type != "FILE_OVERWRITE_DIALOG":
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": dialog_type}
            authorized = {str(Path(item).resolve()) for item in
                          mission.result.get("authorized_overwrite_paths", [])}
            if not target or str(Path(target).resolve()) not in authorized:
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": "overwrite_target_not_authorized"}
            visible = " ".join(str(item.get("text") or "")
                               for item in dialog.get("visible_controls", []))
            if Path(target).name.casefold() not in visible.casefold():
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": "overwrite_target_mismatch",
                        "target": target}
            affirmative_order = ("substituir", "replace", "sim", "yes",
                                 "confirmar", "confirm")
            buttons = {str(item.get("text") or "").casefold(): str(item.get("text") or "")
                       for item in dialog.get("visible_controls", [])
                       if str(item.get("control_type") or "").casefold() == "button"}
            button = next((buttons[label] for label in affirmative_order if label in buttons), "")
            if not button:
                return {"ok": False, "error": "OVERWRITE_CONFIRMATION_BUTTON_NOT_FOUND"}
            confirmed = self.service.execute_tool(
                "ui_invoke_element", {"target": button, "control_type": "Button", "window": ""},
                command=f"computer_mission:{mission.mission_id}:overwrite_confirm",
                task_id=task_id)
            if confirmed.get("confirmation_required"):
                return confirmed
            if not confirmed.get("ok"):
                return confirmed
        time.sleep(0.1)
        dialog = self.service.execute_tool(
            "ui_classify_dialog", {},
            command=f"computer_mission:{mission.mission_id}:overwrite_verify",
            task_id=task_id)
        if dialog.get("dialog_type") != "NONE":
            return {"ok": False, "error": "OVERWRITE_CONFIRMATION_NOT_DISMISSED"}
        mission.context.artifacts["overwrite_confirmed"] = True
        return {"ok": True, "verified": True,
                "verification": "authorized_overwrite_confirmed",
                "overwrite_confirmed": True}

    def _focus_browser(self, mission=None):
        if mission is not None:
            foreground = self._foreground_guard(mission, mission.mission_id, "chrome")
            if not foreground.get("ok"):
                return foreground
        health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:focus_browser",
            task_id="computer-mission")
        if not health.get("ok") or not health.get("started"):
            return {"ok": False, "error": "BROWSER_SESSION_NOT_STARTED"}
        if str(health.get("browser_provider") or health.get("provider") or "").casefold() != "chrome":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED"}
        session_pid = int(health.get("process_id") or
                          ((mission.result.get("chrome_process_id") or 0)
                           if mission is not None else 0))
        if not session_pid:
            return {"ok": False, "error": "CHROME_SESSION_PROCESS_UNAVAILABLE"}
        result = self.service.execute_tool(
            "ui_focus_window", {"window": "chrome", "process_id": session_pid},
            command="computer_mission:focus_browser", task_id="computer-mission")
        if not result.get("ok"):
            result = self.service.execute_tool(
                "ui_focus_window", {"window": "chrome", "process_id": 0},
                command="computer_mission:focus_browser",
                task_id="computer-mission")
        if not result.get("ok"):
            return {"ok": False, "error": "CHROME_FOCUS_GUARD_FAILED"}
        active = self.service.execute_tool(
            "ui_active_window", {}, command="computer_mission:focus_browser",
            task_id="computer-mission")
        data = active.get("result") if isinstance(active.get("result"), dict) else active
        process = str(data.get("process_name") or "").casefold()
        if process != "chrome.exe":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED",
                    "window": data}
        active_pid = int(data.get("pid") or 0)
        return {"ok": True, "focused": True, "browser_process": "chrome.exe",
                "window": data, "session_process_id": active_pid or session_pid,
                "launch_process_id": session_pid,
                "process_identity_reconciled": bool(active_pid and active_pid != session_pid),
                "verification": "chrome_window_focus_guard"}

    def _observe_browser(self, mission, step):
        health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:observe_browser",
            task_id=mission.mission_id)
        if not health.get("ok") or not health.get("started"):
            return {"ok": False, "error": "BROWSER_SESSION_NOT_STARTED"}
        if str(health.get("browser_provider") or health.get("provider") or "").casefold() != "chrome":
            return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED"}
        active = self.service.execute_tool(
            "ui_active_window", {}, command="computer_mission:observe_browser",
            task_id=mission.mission_id)
        data = active.get("result") if isinstance(active.get("result"), dict) else active
        process = str(data.get("process_name") or "").casefold()
        if process != "chrome.exe":
            refocused = self._focus_browser(mission)
            if not refocused.get("ok"):
                return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED",
                        "window": data}
            active = self.service.execute_tool(
                "ui_active_window", {}, command="computer_mission:observe_browser",
                task_id=mission.mission_id)
            data = active.get("result") if isinstance(active.get("result"), dict) else active
            process = str(data.get("process_name") or "").casefold()
            if process != "chrome.exe":
                return {"ok": False, "error": "NON_CHROME_BROWSER_DETECTED",
                        "window": data}
        pid = int(data.get("pid") or 0)
        window_id = int(data.get("handle") or 0)
        session_pid = int(health.get("process_id") or
                          (mission.result.get("chrome_process_id") or 0))
        if session_pid and pid and session_pid != pid:
            refocused = self._focus_browser(mission)
            if not refocused.get("ok"):
                return {"ok": False, "error": "CHROME_WINDOW_PROCESS_MISMATCH",
                        "window": data, "session_process_id": session_pid}
            active = self.service.execute_tool(
                "ui_active_window", {}, command="computer_mission:observe_browser",
                task_id=mission.mission_id)
            data = active.get("result") if isinstance(active.get("result"), dict) else active
            pid = int(data.get("pid") or 0)
            window_id = int(data.get("handle") or 0)
            session_pid = int(refocused.get("session_process_id") or session_pid)
            if str(data.get("process_name") or "").casefold() != "chrome.exe" or (
                    session_pid and pid and session_pid != pid):
                return {"ok": False, "error": "CHROME_WINDOW_PROCESS_MISMATCH",
                        "window": data, "session_process_id": session_pid}
        if self.service.registry.get("browser_record_window") is not None:
            recorded = self.service.execute_tool(
                "browser_record_window", {"pid": pid, "window_id": window_id},
                command="computer_mission:observe_browser", task_id=mission.mission_id)
            if not recorded.get("ok"):
                return {"ok": False, "error": "CHROME_WINDOW_IDENTITY_UNAVAILABLE"}
            health = self.service.execute_tool(
                "browser_health", {}, command="computer_mission:observe_browser",
                task_id=mission.mission_id)
        state_id = health.get("page_state_id")
        previous = mission.result.get("browser_page_state_id")
        if step.expected_state.get("page_changed") and previous is not None and state_id == previous:
            return {"ok": False, "error": "NAVIGATION_STATE_NOT_CHANGED"}
        mission.result["browser_page_state_id"] = state_id
        mission.result["browser_url"] = health.get("current_url", "")
        mission.result["browser_title"] = health.get("page_title", "")
        mission.result["browser_provider"] = "chrome"
        mission.result["chrome_process_id"] = pid
        mission.result["chrome_window_id"] = window_id
        return {"ok": True, "verified": True,
                "verification": "browser_window_and_session_state",
                "window": data, "health": health}

    @staticmethod
    def _search_field(elements):
        candidates = [item for item in elements
                      if item.get("visible", True) and
                      str(item.get("tag")) in {"input", "textarea"}]
        search_terms = ("search", "busca", "query", "pesquisar")
        preferred = [item for item in candidates if any(
            term in " ".join(str(item.get(key) or "").casefold()
                              for key in ("aria_label", "placeholder", "text"))
            for term in search_terms)]
        return (preferred or [item for item in candidates
                              if str(item.get("input_type") or "text").casefold() in
                              {"", "text", "search"} or
                              str(item.get("tag")) == "textarea"])

    @staticmethod
    def _consent_target(elements):
        safe_first = (
            "reject all", "rejeitar tudo", "only necessary", "somente necessários",
            "somente necessarios", "necessary only", "rejeitar", "reject",
        )
        benign_fallback = ("accept", "aceitar", "continue", "continuar", "ok")
        candidates = [item for item in elements if item.get("visible", True) and
                      str(item.get("tag")) in {"a", "button", "input"}]
        for labels in (safe_first, benign_fallback):
            for item in candidates:
                label = " ".join(str(item.get(key) or "") for key in
                                 ("text", "aria_label", "placeholder")).strip().casefold()
                if label and any(label == target or target in label for target in labels):
                    return str(item.get("ref") or ""), label
        return "", ""

    def _provider_health(self, mission, provider, status, block_reason=""):
        entries = list(mission.result.get("provider_health") or [])
        entries.append({"provider": provider, "attempt": len(entries) + 1,
                        "status": status, "block_reason": block_reason})
        mission.result["provider_health"] = entries[-MAX_SEARCH_PROVIDERS:]

    def _advance_provider(self, mission, reason):
        replans = int(mission.result.get("replans", 0)) + 1
        mission.result["replans"] = replans
        if replans > int(mission.result.get("max_replans", 2)):
            return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                    "barrier_type": "REPLAN_BUDGET_EXCEEDED"}
        current_index = int(mission.result.get("provider_index", 0))
        current = SEARCH_PROVIDER_ORDER[current_index]
        self._provider_health(mission, current, "BLOCKED", reason)
        next_index = current_index + 1
        if next_index >= MAX_SEARCH_PROVIDERS:
            return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                    "barrier_type": reason}
        provider = SEARCH_PROVIDER_ORDER[next_index]
        mission.result["provider_index"] = next_index
        mission.result["search_provider"] = provider
        navigation = self.service.execute_tool(
            "browser_navigate", {"url": SEARCH_PROVIDER_URLS[provider]},
            command="computer_mission:provider_fallback", task_id=mission.mission_id)
        if not navigation.get("ok"):
            self._provider_health(mission, provider, "ERROR", navigation.get("error", ""))
            return {"ok": False, "error": "SEARCH_PROVIDER_FALLBACK_FAILED"}
        health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:provider_fallback",
            task_id=mission.mission_id)
        if (not health.get("ok") or not health.get("started") or
                str(health.get("browser_provider") or health.get("provider") or "").casefold()
                != "chrome"):
            self._provider_health(mission, provider, "ERROR", "CHROME_SESSION_UNAVAILABLE")
            return {"ok": False, "error": "SEARCH_PROVIDER_FALLBACK_FAILED"}
        mission.result["browser_page_state_id"] = health.get("page_state_id")
        self._provider_health(mission, provider, "AVAILABLE", "")
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool="browser_provider_fallback",
            arguments={"from": current, "to": provider},
            risk=mission.risk_level,
            status="fallback",
            result={"reason": reason, "browser": "chrome"},
        )
        return {"ok": True, "provider": provider, "verification": "chrome_provider_fallback"}

    def _handle_cookie_consent(self, mission, page, elements):
        ref, label = self._consent_target(elements)
        if not ref:
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": "unknown_cookie_consent"}
        health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:cookie_consent",
            task_id=mission.mission_id)
        if not health.get("ok") or not health.get("started"):
            return {"ok": False, "error": "BROWSER_SESSION_NOT_STARTED"}
        clicked = self.service.execute_tool(
            "browser_click", {"ref": ref, "selector": "", "text": ""},
            command="computer_mission:cookie_consent", task_id=mission.mission_id)
        if not clicked.get("ok"):
            return {"ok": False, "error": "COOKIE_CONSENT_ACTION_FAILED"}
        page_result = self.service.execute_tool(
            "browser_get_page_info", {}, command="computer_mission:cookie_consent",
            task_id=mission.mission_id)
        elements_result = self.service.execute_tool(
            "browser_get_elements", {}, command="computer_mission:cookie_consent",
            task_id=mission.mission_id)
        refreshed_health = self.service.execute_tool(
            "browser_health", {}, command="computer_mission:cookie_consent",
            task_id=mission.mission_id)
        if refreshed_health.get("ok"):
            mission.result["browser_page_state_id"] = refreshed_health.get("page_state_id")
        barrier = classify_page_barrier(page_result.get("page") or {},
                                        elements_result.get("elements") or [])
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool="browser_cookie_consent",
            arguments={"target": ref, "label": label},
            risk=mission.risk_level,
            status="dismissed" if barrier == "NONE" else "blocked",
            result={"browser": "chrome", "barrier_type": barrier,
                    "decision": "safe_consent_target"},
        )
        if barrier != "NONE":
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": barrier}
        return {"ok": True, "verified": True,
                "verification": "cookie_consent_dismissed"}

    def _prepare_search_provider(self, mission):
        while True:
            page_result = self.service.execute_tool(
                "browser_get_page_info", {}, command="computer_mission:classify_barrier",
                task_id=mission.mission_id)
            elements_result = self.service.execute_tool(
                "browser_get_elements", {}, command="computer_mission:ground_search_field",
                task_id=mission.mission_id)
            page = page_result.get("page") or {}
            elements = list(elements_result.get("elements") or [])
            barrier = classify_page_barrier(page, elements)
            mission.result["barrier_type"] = barrier
            if barrier == "COOKIE_CONSENT":
                consent = self._handle_cookie_consent(mission, page, elements)
                if not consent.get("ok"):
                    return consent
                continue
            if barrier in {"UNKNOWN_BLOCKER", "LOGIN_REQUIRED", "AUTH_REQUIRED",
                           "PRIVACY_CONSENT", "BENIGN_INTERSTITIAL"}:
                return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                        "dialog": barrier}
            if barrier in {"CAPTCHA", "ANTI_BOT", "BOT_VERIFICATION", "ACCESS_DENIED",
                           "RATE_LIMITED", "NETWORK_ERROR", "PAGE_ERROR"}:
                fallback = self._advance_provider(mission, barrier)
                if not fallback.get("ok"):
                    return fallback
                continue
            selected = self._search_field(elements)
            if selected:
                ref = str(selected[0].get("ref") or "")
                if ref:
                    mission.result["search_ref"] = ref
                    return {"ok": True, "verified": True, "ref": ref,
                            "verification": "structured_search_field_grounding"}
            fallback = self._advance_provider(mission, "SEARCH_FIELD_NOT_FOUND")
            if not fallback.get("ok"):
                return {"ok": False, "error": "SEARCH_FIELD_NOT_FOUND"}

    def _ground_search_field(self, mission):
        return self._prepare_search_provider(mission)

    def _extract_browser_results(self, mission, page, minimum=3):
        page = page or {}
        barrier = classify_page_barrier(page, page.get("interactive"))
        if barrier != "NONE":
            return {"ok": False, "barrier_type": barrier, "titles": [], "source_urls": []}
        links = [link for link in list(page.get("links") or [])
                 if link.get("visible", True) and link.get("result_candidate")]
        page_url = str(page.get("url") or "")
        try:
            page_host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(page_url).netloc
        except Exception:
            page_host = ""
        query = str(mission.result.get("search_query") or "").casefold()
        excluded = {"images", "videos", "maps", "news", "shopping", "sign in", "more",
                    "aceitar", "rejeitar", "privacy policy", "política de privacidade"}
        selected: dict[str, tuple[str, str]] = {}

        def title_score(value):
            lowered = value.casefold()
            return (0 if "›" in value or value.startswith("http") else 100) + min(len(value), 120)

        for link in links:
            title = " ".join(str(link.get("text") or "").split())
            href = str(link.get("href") or "")
            try:
                host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(href).netloc
            except Exception:
                host = ""
            lowered = title.casefold()
            if (len(title) < 3 or lowered in excluded or
                    re.fullmatch(r"(?:https?://|www\.)\S+", title, re.I) or
                    any(marker in lowered for marker in ("sponsored", "patrocinado", "anúncio", "anuncio")) or
                    not href.startswith(("http://", "https://")) or host == page_host):
                continue
            normalized_href = href.rstrip("/")
            previous = selected.get(normalized_href)
            if previous is None or title_score(title) > title_score(previous[0]):
                selected[normalized_href] = (title, href)
            if len(selected) >= int(minimum):
                break
        titles = [item[0] for item in selected.values()]
        sources = [item[1] for item in selected.values()]
        page_text = " ".join(str(page.get(key) or "") for key in
                             ("url", "title", "text", "headings")).casefold()
        query_present = not query or query in page_text or query.replace(" ", "+") in page_url.casefold()
        ok = query_present and len(titles) >= int(minimum)
        return {"ok": ok, "barrier_type": "NONE", "titles": titles[:minimum],
                "source_urls": sources[:minimum],
                "result_page_confirmed": ok, "visible_results_read": bool(links)}

    def _fallback_search_and_extract(self, mission, step):
        for _ in range(MAX_SEARCH_PROVIDERS):
            prepared = self._prepare_search_provider(mission)
            if not prepared.get("ok"):
                return prepared
            search = self.service.execute_tool(
                "browser_search", {"query": mission.result["search_query"],
                                    "ref": mission.result.get("search_ref", "")},
                command="computer_mission:provider_fallback_search",
                task_id=mission.mission_id)
            if not search.get("ok"):
                fallback = self._advance_provider(mission, search.get("error", "SEARCH_FAILED"))
                if fallback.get("ok"):
                    continue
                return fallback
            observed = self._observe_browser(
                mission, ComputerMissionStep("fallback-observe", "Observar resultados do provider",
                                             "observe_browser", expected_state={"page_changed": True}))
            if not observed.get("ok"):
                return observed
            self.service.execute_tool(
                "browser_wait_for_results", {"timeout_ms": 10000},
                command="computer_mission:wait_fallback_results",
                task_id=mission.mission_id)
            page_result = self.service.execute_tool(
                "browser_get_page_info", {}, command="computer_mission:fallback_results",
                task_id=mission.mission_id)
            extracted = self._extract_browser_results(
                mission, page_result.get("page") or {}, minimum=3)
            if extracted.get("ok"):
                mission.result.update({
                    "titles": extracted["titles"],
                    "source_urls": extracted["source_urls"],
                    "result_page_confirmed": True,
                    "visible_results_read": True,
                    "page_title": (page_result.get("page") or {}).get("title", ""),
                    "page_url": (page_result.get("page") or {}).get("url", ""),
                })
                return {"ok": True, "verified": True,
                        "verification": "fallback_result_page_confirmed"}
            barrier = extracted.get("barrier_type") or "SEARCH_RESULTS_NOT_CONFIRMED"
            fallback = self._advance_provider(mission, barrier)
            if not fallback.get("ok"):
                return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                        "barrier_type": barrier}
        return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED"}

    def _verify_browser_results(self, mission, step):
        self.service.execute_tool(
            "browser_wait_for_results", {"timeout_ms": 10000},
            command="computer_mission:wait_results",
            task_id=mission.mission_id)
        result = self.service.execute_tool(
            "browser_get_page_info", {}, command="computer_mission:verify_results",
            task_id=mission.mission_id)
        page = result.get("page") or {}
        extracted = self._extract_browser_results(
            mission, page, minimum=int(step.expected_state.get("minimum", 3)))
        if extracted.get("ok"):
            titles = extracted["titles"]
            sources = extracted["source_urls"]
            mission.result.update({"titles": titles, "source_urls": sources,
                                   "page_title": page.get("title", ""),
                                   "page_url": page.get("url", ""),
                                   "result_page_confirmed": True,
                                   "visible_results_read": True})
            return {"ok": True, "verified": True, "titles": titles,
                    "source_urls": sources, "verification": "result_page_confirmed"}
        barrier = extracted.get("barrier_type") or "SEARCH_RESULTS_NOT_CONFIRMED"
        if barrier in {"UNKNOWN_BLOCKER", "LOGIN_REQUIRED", "AUTH_REQUIRED",
                       "PRIVACY_CONSENT", "BENIGN_INTERSTITIAL"}:
            return {"ok": False, "error": "USER_CONFIRMATION_REQUIRED",
                    "dialog": barrier}
        current_provider = SEARCH_PROVIDER_ORDER[int(mission.result.get("provider_index", 0))]
        self._provider_health(mission, current_provider, "BLOCKED", barrier)
        fallback = self._advance_provider(mission, barrier)
        if fallback.get("ok"):
            return self._fallback_search_and_extract(mission, step)
        return {"ok": False, "error": "SEARCH_PROVIDERS_EXHAUSTED",
                "barrier_type": barrier}

    def _observe_window(self, step):
        result = self.service.execute_tool("ui_active_window", {},
                                           command="computer_mission:observe",
                                           task_id="computer-mission")
        if result.get("confirmation_required") or not (result.get("ok") or result.get("found")):
            return result
        data = result.get("result") if isinstance(result.get("result"), dict) else result
        expected = step.expected_state
        title = str(data.get("title") or data.get("message") or "").casefold()
        process = str(data.get("process_name") or "").casefold()
        if expected.get("process") and expected["process"].casefold() not in process:
            return {"ok": False, "error": "CORRECT_WINDOW_NOT_FOCUSED"}
        expected_title = expected.get("title")
        titles = expected_title if isinstance(expected_title, (tuple, list)) else (expected_title,)
        if expected_title and not any(str(item).casefold() in title for item in titles if item):
            if self._is_path_not_found({"error": title}):
                return {"ok": False, "error": "PATH_NOT_FOUND",
                        "path_error_dialog": True, "window": data}
            return {"ok": False, "error": "EXPECTED_WINDOW_NOT_FOUND"}
        return {"ok": True, "window": data, "verified": True,
                "verification": "active_window_match"}

    def _verify_file(self, step):
        path = Path(step.expected_state.get("path") or step.target)
        expected = str(step.expected_state.get("content") or "")
        try:
            exists = path.is_file()
            content_valid = exists and path.read_text(encoding="utf-8") == expected
            return {"ok": exists and content_valid, "verified": exists and content_valid,
                    "verification": "filesystem_exists_and_content",
                    "file_exists": exists, "content_valid": content_valid,
                    "path": str(path)}
        except OSError as exc:
            return {"ok": False, "verified": False, "error": type(exc).__name__,
                    "path_error": "PATH_NOT_FOUND" if getattr(exc, "errno", None) == 2 else "",
                    "file_exists": False, "content_valid": False}

    @staticmethod
    def _is_path_not_found(result: dict[str, Any]) -> bool:
        text = " ".join(str(result.get(key, "")) for key in
                        ("error", "message", "reason", "path_error")).casefold()
        return any(marker in text for marker in
                   ("path_not_found", "path not found", "cannot find the path",
                    "caminho especificado", "sistema não pode encontrar"))

    def _recover_path_not_found(self, mission, step, result) -> bool:
        attempts = int(mission.result.get("path_recovery_attempts", 0)) + 1
        mission.result["path_recovery_attempts"] = attempts
        if attempts > 2:
            mission.status = MissionStatus.BLOCKED
            mission.error = "PATH_NOT_FOUND_UNRECOVERED"
            step.status = MissionStepStatus.BLOCKED
            return False
        if result.get("path_error_dialog"):
            dismissed = self.service.execute_tool(
                "ui_dismiss_path_not_found", {"window": "notepad"},
                command=f"computer_mission:{mission.mission_id}",
                task_id=mission.mission_id)
            self._audit_step(mission, step, dismissed, "path_not_found_dialog_dismissed")
            if not dismissed.get("ok"):
                return False
            if step.action_type in {"type_mission_template", "verify_editor_pre_save"}:
                # The dialog may be a stale child of the target app.  Retry
                # the current perception step after the exact dialog is gone;
                # do not jump into Save As or rewrite a file path blindly.
                mission.result["path_reresolved"] = {"dialog": "dismissed",
                                                       "step": step.step_id}
                if step.action_type == "type_mission_template":
                    restart_index = next((index for index, item in enumerate(mission.steps)
                                          if item.step_id == "new-notepad-document"),
                                         mission.current_step)
                    for item in mission.steps[restart_index:]:
                        item.status = MissionStepStatus.PENDING
                        item.error = ""
                    mission.current_step = restart_index
                return True
        if not self._reresolve_path(mission):
            return False
        entry_index = next((index for index, item in enumerate(mission.steps)
                            if item.target == "file-name" and item.action_type == "keyboard_type"),
                           mission.current_step)
        for item in mission.steps[entry_index:]:
            item.status = MissionStepStatus.PENDING
            item.error = ""
        mission.current_step = entry_index
        return True

    def _reresolve_path(self, mission: ComputerMission) -> bool:
        """Refresh a mission's file target after a recoverable path failure."""
        verify = next((item for item in mission.steps
                       if item.action_type in {"verify_file", "verify_cross_app_file"}), None)
        type_name = next((item for item in mission.steps if item.step_id == "type-file-name"), None)
        if verify is None:
            return False
        old_path = str(verify.expected_state.get("path") or verify.target)
        new_path = self.planner.resolve_target_path(Path(old_path).name)
        verify.expected_state["path"] = str(new_path)
        verify.target = str(new_path)
        if type_name is not None:
            type_name.args["text"] = str(new_path)
        mission.result["path_reresolved"] = {"from": old_path, "to": str(new_path)}
        return True

    def _validate_step_result(self, step, result):
        valid = None
        if step.action_type == "verify_file":
            valid = bool(result.get("verified") and result.get("file_exists")
                         and result.get("content_valid"))
        elif step.action_type == "observe_window":
            valid = bool(result.get("verified"))
        elif step.action_type in {"focus_browser", "observe_browser", "ground_search_field",
                                  "verify_browser_results"}:
            valid = bool(result.get("verified") or result.get("focused"))
        else:
            valid = bool(result.get("ok"))
        if not valid:
            return False
        for produced in step.produces:
            if produced in {"python_version", "python_page_title", "ollama_page_title"}:
                stored = self._active.context.resolve(
                    produced, mission_id=self._active.mission_id,
                    current_step=self._active.current_step) if self._active and self._active.context else (None, "")
                if not stored[0]:
                    return False
            elif produced == "summary_text" and not result.get("text"):
                return False
            elif produced == "summary_text_verified" and not result.get("editor_content_verified", True):
                return False
        return True

    def _window_fingerprint(self):
        try:
            result = self.service.execute_tool("ui_active_window", {},
                                               command="computer_mission:fingerprint",
                                               task_id="computer-mission")
            return str((result.get("result") or result).get("title", ""))
        except Exception:
            return "unknown"

    def _audit_step(self, mission, step, result, status):
        self.service.audit.add(
            task_id=mission.mission_id,
            command=f"computer_mission:{mission.mission_id}",
            tool=step.action_type,
            arguments={"mission_id": mission.mission_id, "step_id": step.step_id,
                       "target": step.target},
            risk=mission.risk_level,
            status=status,
            result={"ok": bool(result.get("ok")), "verification": result.get("verification"),
                    "error": result.get("error", "")},
        )

    @staticmethod
    def _safe_step_result(result):
        allowed = {"ok", "verified", "verification", "message", "file_exists",
                   "content_valid", "cross_app_data_match", "window", "path", "tool",
                   "text", "value", "source_variable", "source_url", "source_title",
                   "previous_app", "app", "text_input_sent",
                   "editor_content_verified", "mission_to_editor_match",
                   "editor_identity", "content_state_id", "overwrite_confirmed",
                   "document_identity", "mission_document_id", "created_by_mission",
                   "pre_existing_document", "checkpoint_name", "skipped",
                   "receipt", "source_variables", "cross_app_data_match"}
        return {key: value for key, value in result.items() if key in allowed}

    def _finish(self, mission, ok):
        self._persist_mission(
            mission,
            checkpoint_id=str(mission.result.get("checkpoint_id") or ""),
            pause_reason=str(mission.result.get("pause_reason") or ""),
            audit=False,
        )
        with self._lock:
            if self._active is mission and mission.status in {MissionStatus.COMPLETED,
                                                               MissionStatus.FAILED,
                                                               MissionStatus.BLOCKED,
                                                               MissionStatus.CANCELLED}:
                self._active = None
        return {"ok": bool(ok), "mission": mission.public(),
                "message": ("Missão concluída." if ok else
                            mission.error or mission.status.value)}


__all__ = [
    "ComputerMission", "ComputerMissionExecutor", "ComputerMissionPlanner",
    "ComputerMissionStep", "MissionStatus", "MissionStepStatus",
    "MissionContext", "MissionCheckpointStore", "CheckpointState", "ActionState",
    "WorldStateChangeType",
]
