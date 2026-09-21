"""
Golden AI - Permission Manager V2
Resource-based permissions with persistent grants.
Evolves the existing ExternalAccessService, does not replace it.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from core.audit import AuditLogger
from core.config import load_settings
from core.execution import ExecutionService


class ResourceType(str, Enum):
    FILE = "file"
    FOLDER = "folder"
    TREE = "tree"
    MT5 = "mt5"
    METAEDITOR = "metaeditor"
    INTERNET = "internet"
    DOMAIN = "domain"
    PROCESS = "process"


class Operation(str, Enum):
    READ_FILE = "READ_FILE"
    READ_FOLDER = "READ_FOLDER"
    LIST_FOLDER = "LIST_FOLDER"
    SEARCH_FOLDER = "SEARCH_FOLDER"
    WRITE_FILE = "WRITE_FILE"
    CREATE_FILE = "CREATE_FILE"
    DELETE_FILE = "DELETE_FILE"
    MOVE_FILE = "MOVE_FILE"
    EXECUTE = "EXECUTE"
    COMPILE = "COMPILE"
    DEPLOY = "DEPLOY"
    INTERNET_SEARCH = "INTERNET_SEARCH"
    INTERNET_FETCH = "INTERNET_FETCH"
    DOWNLOAD = "DOWNLOAD"
    UPLOAD = "UPLOAD"


class GrantType(str, Enum):
    ONCE = "once"
    TASK = "task"
    PERMANENT = "permanent"
    DENIED = "denied"


READ_OPERATIONS = {
    Operation.READ_FILE,
    Operation.READ_FOLDER,
    Operation.LIST_FOLDER,
    Operation.SEARCH_FOLDER,
}

WRITE_OPERATIONS = {
    Operation.WRITE_FILE,
    Operation.CREATE_FILE,
    Operation.DELETE_FILE,
    Operation.MOVE_FILE,
}

EXECUTE_OPERATIONS = {
    Operation.EXECUTE,
    Operation.COMPILE,
    Operation.DEPLOY,
}


@dataclass
class PermissionGrant:
    grant_id: str
    canonical_path: str
    resource_type: str
    operations: list[str]
    grant_type: str
    task_id: str = ""
    created_at: str = ""
    origin: str = "user_approval"
    description: str = ""
    consumed: bool = False
    status: str = "active"

    def matches(self, canonical_path: str, operation: str, task_id: str = "") -> bool:
        if self.status != "active":
            return False
        if self.consumed and self.grant_type == GrantType.ONCE.value:
            return False
        if operation not in self.operations:
            return False
        if self.grant_type == GrantType.TASK.value and task_id and self.task_id != task_id:
            return False
        if self.grant_type == GrantType.PERMANENT.value:
            return True
        if self.grant_type == GrantType.ONCE.value:
            return not self.consumed
        if self.grant_type == GrantType.TASK.value and (not task_id or self.task_id == task_id):
            return True
        return False

    def is_expired(self) -> bool:
        if self.grant_type == GrantType.ONCE.value and self.consumed:
            return True
        if self.status == "revoked":
            return True
        return False


class PermissionManagerV2:
    """
    Resource-based permission manager with persistent grants.
    Evolves ExternalAccessService, does not replace it.
    """

    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.settings = load_settings()
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")
        self.grants_file = self.root / "data" / "permission_grants.json"
        self._grants: list[PermissionGrant] = []
        self._load_grants()

    def _load_grants(self):
        if self.grants_file.exists():
            try:
                data = json.loads(self.grants_file.read_text(encoding="utf-8"))
                self._grants = [PermissionGrant(**g) for g in data if isinstance(g, dict)]
            except Exception:
                self._grants = []
        self._grants = [g for g in self._grants if not g.is_expired()]

    def _save_grants(self):
        try:
            self.grants_file.parent.mkdir(parents=True, exist_ok=True)
            active = [g for g in self._grants if not g.is_expired()]
            data = [asdict(g) for g in active]
            self.grants_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._grants = active
        except Exception as e:
            print(f"[PermissionManagerV2] Error saving grants: {e}")

    def canonical_path(self, path: str | Path) -> Path:
        return Path(str(path).strip().strip('"')).resolve()

    def is_external(self, path: str | Path) -> bool:
        resolved = self.canonical_path(path)
        allowed_roots = []
        for root in self.settings.allowed_paths + self.settings.protected_paths:
            if root.exists():
                allowed_roots.append(root.resolve())
        for root in allowed_roots:
            try:
                resolved.relative_to(root)
                return False
            except ValueError:
                continue
        return True

    def check_permission(self, path: str | Path, operation: str, task_id: str = "", resource_type: str = "file") -> dict:
        resolved = self.canonical_path(path)
        canonical = str(resolved)

        if not self.is_external(resolved):
            if operation in [op.value for op in READ_OPERATIONS]:
                return {"allowed": True, "reason": "Internal path read allowed", "scope": "internal"}
            if operation in [op.value for op in WRITE_OPERATIONS]:
                return {"allowed": False, "reason": "WRITE requires approval", "scope": "needs_approval"}
            if operation in [op.value for op in EXECUTE_OPERATIONS]:
                return {"allowed": False, "reason": "EXECUTE requires approval", "scope": "needs_approval"}

        for grant in self._grants:
            if grant.matches(canonical, operation, task_id):
                if grant.grant_type == GrantType.ONCE.value:
                    grant.consumed = True
                    self._save_grants()
                self._record("PERMISSION_V2_GRANTED", "COMPLETED", canonical, f"Access {operation} granted via {grant.grant_type}", task_id)
                return {"allowed": True, "reason": f"Granted via {grant.grant_type}", "grant_id": grant.grant_id, "scope": grant.grant_type}

        for grant in self._grants:
            if (grant.canonical_path == canonical and grant.grant_type == GrantType.DENIED.value and grant.status == "active" and operation in grant.operations):
                return {"allowed": False, "reason": "Access denied by user", "scope": "denied"}

        request_id = str(uuid.uuid4())
        self._record("PERMISSION_V2_APPROVAL_NEEDED", "WAITING_APPROVAL", canonical, f"Need approval for {operation} on {canonical}", task_id)
        return {"allowed": False, "reason": "Approval needed", "request_id": request_id, "scope": "needs_approval", "canonical_path": canonical, "operation": operation, "resource_type": resource_type}

    def grant_once(self, request_id: str, canonical_path: str, operation: str, task_id: str = ""):
        grant = PermissionGrant(
            grant_id=request_id, canonical_path=canonical_path, resource_type="file",
            operations=[operation], grant_type=GrantType.ONCE.value, task_id=task_id,
            created_at=datetime.now().isoformat(timespec="seconds"), origin="user_approval",
        )
        self._grants.append(grant)
        self._save_grants()
        self._record("PERMISSION_V2_GRANTED_ONCE", "COMPLETED", canonical_path, "One-time access granted", task_id)

    def grant_for_task(self, request_id: str, canonical_path: str, operation: str, task_id: str):
        grant = PermissionGrant(
            grant_id=request_id, canonical_path=canonical_path, resource_type="file",
            operations=[operation], grant_type=GrantType.TASK.value, task_id=task_id,
            created_at=datetime.now().isoformat(timespec="seconds"), origin="user_approval",
        )
        self._grants.append(grant)
        self._save_grants()
        self._record("PERMISSION_V2_GRANTED_TASK", "COMPLETED", canonical_path, "Task-scoped access granted", task_id)

    def grant_permanent(self, request_id: str, canonical_path: str, operations: list[str], resource_type: str = "file"):
        grant = PermissionGrant(
            grant_id=request_id, canonical_path=canonical_path, resource_type=resource_type,
            operations=operations, grant_type=GrantType.PERMANENT.value,
            created_at=datetime.now().isoformat(timespec="seconds"), origin="user_approval",
            description=f"Permanent {', '.join(operations)} access",
        )
        self._grants.append(grant)
        self._save_grants()
        self._record("PERMISSION_V2_GRANTED_PERMANENT", "COMPLETED", canonical_path, "Permanent access granted", "")

    def deny(self, request_id: str, canonical_path: str, operation: str):
        grant = PermissionGrant(
            grant_id=request_id, canonical_path=canonical_path, resource_type="file",
            operations=[operation], grant_type=GrantType.DENIED.value,
            created_at=datetime.now().isoformat(timespec="seconds"), origin="user_denial",
        )
        self._grants.append(grant)
        self._save_grants()
        self._record("PERMISSION_V2_DENIED", "BLOCKED", canonical_path, "Access denied by user", "")

    def revoke(self, grant_id: str):
        for grant in self._grants:
            if grant.grant_id == grant_id:
                grant.status = "revoked"
                self._save_grants()
                self._record("PERMISSION_V2_REVOKED", "COMPLETED", grant.canonical_path, "Permission revoked", "")
                return True
        return False

    def revoke_all_permanent(self):
        count = 0
        for grant in self._grants:
            if grant.grant_type == GrantType.PERMANENT.value and grant.status == "active":
                grant.status = "revoked"
                count += 1
        self._save_grants()
        self._record("PERMISSION_V2_ALL_REVOKED", "COMPLETED", "", f"Revoked {count} permanent grants", "")
        return count

    def list_active_grants(self) -> list[dict]:
        result = []
        for grant in self._grants:
            if grant.is_expired():
                continue
            result.append({
                "grant_id": grant.grant_id, "path": grant.canonical_path,
                "resource_type": grant.resource_type, "operations": grant.operations,
                "grant_type": grant.grant_type, "task_id": grant.task_id,
                "created_at": grant.created_at, "origin": grant.origin,
                "status": grant.status, "description": grant.description,
            })
        return result

    def list_permanent_grants(self) -> list[dict]:
        return [g for g in self.list_active_grants() if g["grant_type"] == GrantType.PERMANENT.value]

    def read_file_after_approval(self, task_id: str, path: str | Path, max_bytes: int = 200_000) -> str:
        resolved = self.canonical_path(path)
        decision = self.check_permission(resolved, Operation.READ_FILE.value, task_id)
        if not decision.get("allowed"):
            raise PermissionError(decision.get("reason", "Access denied"))
        self._record("PERMISSION_V2_READ", "COMPLETED", str(resolved), "Reading authorized file", task_id)
        if resolved.stat().st_size > max_bytes:
            return resolved.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        return resolved.read_text(encoding="utf-8", errors="replace")

    def list_folder_after_approval(self, task_id: str, path: str | Path) -> list[str]:
        resolved = self.canonical_path(path)
        decision = self.check_permission(resolved, Operation.LIST_FOLDER.value, task_id, "folder")
        if not decision.get("allowed"):
            raise PermissionError(decision.get("reason", "Access denied"))
        self._record("PERMISSION_V2_LIST", "COMPLETED", str(resolved), "Listing authorized folder", task_id)
        if not resolved.is_dir():
            raise NotADirectoryError(str(resolved))
        return [str(f.name) for f in resolved.iterdir() if f.is_file()]

    def _record(self, action: str, status: str, target: str, summary: str, task_id: str):
        try:
            self.execution.record_event(
                task_id=task_id, category="PERMISSION", action=action, status=status,
                summary=summary, target=target, tool_name="permission_v2",
                permission_level="READ_EXTERNAL", risk_level="LOW",
            )
            self.audit.record({
                "action_type": action, "status": status,
                "agent": "core.permissions.v2", "target": target, "result": summary,
            })
        except Exception:
            pass