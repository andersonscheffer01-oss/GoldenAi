from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.audit import AuditLogger
from core.config.settings import ROOT

from .models import (
    ApprovalRequest,
    AuthorizationResult,
    ExecutionEvent,
    ExecutionStatus,
    PermissionMode,
    RiskLevel,
)
from .repository import ExecutionRepository


class ExecutionService:
    def __init__(self, root: str | Path = ROOT):
        self.root = Path(root)
        self.repo = ExecutionRepository(self.root / "data" / "golden_ai.db")
        self.audit = AuditLogger(self.root / "logs")

    def get_mode(self) -> PermissionMode:
        raw = self.repo.get_mode()
        try:
            return PermissionMode(raw)
        except ValueError:
            return PermissionMode.READ_ONLY

    def set_mode(self, mode: str | PermissionMode) -> PermissionMode:
        selected = PermissionMode(str(mode.value if isinstance(mode, PermissionMode) else mode))
        previous = self.get_mode().value
        self.repo.set_mode(selected.value)
        self._audit("PERMISSION_MODE_CHANGED", "COMPLETED", selected.value, f"{previous}->{selected.value}")
        self.record_event(
            category="PERMISSION",
            action="PERMISSION_MODE_CHANGED",
            status=ExecutionStatus.COMPLETED.value,
            summary=f"Modo de permissao alterado para {selected.value}",
            permission_level=selected.value,
        )
        return selected

    def classify_risk(
        self,
        permission_level: str = "READ",
        target: str | Path = "",
        action: str = "",
        category: str = "",
    ) -> RiskLevel:
        level = str(permission_level or "").upper()
        text = f"{target} {action} {category}".lower()
        if level == "CRITICAL" or any(term in text for term in ("trade", "ordem", "order_send", "mt5 real")):
            return RiskLevel.CRITICAL
        if any(term in text for term in ("installer", "instalador", "credential", "credencial", "powershell", "cmd")):
            return RiskLevel.HIGH
        if level in {"WRITE", "EXECUTE"}:
            path = Path(str(target)) if target else None
            if path and str(path).lower().startswith(str(self.root).lower()):
                return RiskLevel.MEDIUM
            return RiskLevel.HIGH
        return RiskLevel.LOW

    def operation_key(self, permission_level: str, action: str, target: str = "", tool_name: str = "") -> str:
        return "|".join(
            part.strip().lower()
            for part in (permission_level or "", tool_name or "", action or "", str(target or ""))
        )

    def authorize_action(
        self,
        task_id: str,
        permission_level: str,
        action: str,
        target: str = "",
        reason: str = "",
        risk_level: str | RiskLevel | None = None,
        tool_name: str = "",
        capability_exists: bool = True,
    ) -> AuthorizationResult:
        mode = self.get_mode()
        permission_level = str(permission_level or "READ").upper()
        risk = RiskLevel(str(risk_level.value if isinstance(risk_level, RiskLevel) else risk_level)) if risk_level else self.classify_risk(permission_level, target, action)
        task_id = task_id or "global"
        key = self.operation_key(permission_level, action, target, tool_name)

        if risk == RiskLevel.CRITICAL:
            self._blocked(task_id, permission_level, action, target, risk.value, "CRITICAL continua bloqueado nesta fase")
            return AuthorizationResult(False, "CRITICAL continua bloqueado nesta fase", mode.value, ExecutionStatus.BLOCKED.value, risk_level=risk.value)

        if permission_level == "READ":
            self._allowed(task_id, permission_level, action, target, risk.value, "Leitura permitida")
            return AuthorizationResult(True, "Leitura permitida", mode.value, ExecutionStatus.COMPLETED.value, risk_level=risk.value)

        if not capability_exists:
            self._blocked(task_id, permission_level, action, target, risk.value, "Capability nao implementada")
            return AuthorizationResult(False, "Capability nao implementada", mode.value, ExecutionStatus.BLOCKED.value, risk_level=risk.value)

        if mode == PermissionMode.READ_ONLY:
            self._blocked(task_id, permission_level, action, target, risk.value, "ACAO BLOQUEADA: SOMENTE LEITURA")
            return AuthorizationResult(False, "ACAO BLOQUEADA: SOMENTE LEITURA", mode.value, ExecutionStatus.BLOCKED.value, risk_level=risk.value)

        if self.repo.granted_once(task_id, key):
            request = self.repo.granted_once(task_id, key)
            self.repo.update_request(request["request_id"], "GRANTED_ONCE", consumed=True)
            self._allowed(task_id, permission_level, action, target, risk.value, "Aprovacao unica consumida")
            return AuthorizationResult(True, "Aprovacao unica consumida", mode.value, ExecutionStatus.COMPLETED.value, request["request_id"], risk.value)

        if self.repo.granted_for_task(task_id, key):
            self._allowed(task_id, permission_level, action, target, risk.value, "Aprovado para esta tarefa")
            return AuthorizationResult(True, "Aprovado para esta tarefa", mode.value, ExecutionStatus.COMPLETED.value, risk_level=risk.value)

        if mode == PermissionMode.AUTO_SAFE and risk == RiskLevel.LOW:
            self._allowed(task_id, permission_level, action, target, risk.value, "AUTO_SAFE permitiu acao LOW")
            return AuthorizationResult(True, "AUTO_SAFE permitiu acao LOW", mode.value, ExecutionStatus.COMPLETED.value, risk_level=risk.value)

        if mode == PermissionMode.FULL and risk in {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}:
            self._allowed(task_id, permission_level, action, target, risk.value, "FULL permitiu capability habilitada")
            return AuthorizationResult(True, "FULL permitiu capability habilitada", mode.value, ExecutionStatus.COMPLETED.value, risk_level=risk.value)

        request = self._request_approval(task_id, key, permission_level, action, target, reason, risk.value, tool_name)
        return AuthorizationResult(False, "Aguardando aprovacao", mode.value, ExecutionStatus.WAITING_APPROVAL.value, request.request_id, risk.value)

    def grant_once(self, request_id: str) -> None:
        self.repo.update_request(request_id, "GRANTED_ONCE", scope="ONCE", consumed=False)
        self._audit("APPROVAL_GRANTED_ONCE", "GRANTED", request_id)

    def grant_for_task(self, request_id: str) -> None:
        self.repo.update_request(request_id, "GRANTED_TASK", scope="TASK", consumed=False)
        self._audit("APPROVAL_GRANTED_TASK", "GRANTED", request_id)

    def deny(self, request_id: str) -> None:
        self.repo.update_request(request_id, "DENIED", scope="DENIED", consumed=True)
        self._audit("APPROVAL_DENIED", "DENIED", request_id)

    def record_event(self, **kwargs: Any) -> ExecutionEvent:
        event = ExecutionEvent(**kwargs)
        self.repo.add_event(event)
        self._audit("EXECUTION_EVENT_CREATED", event.status, event.target, event.summary)
        return event

    def latest_events(self, task_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        rows = self.repo.latest_events(task_id, limit)
        return [self._event_row(row) for row in rows]

    def latest_requests(self, limit: int = 20) -> list[dict[str, Any]]:
        return [dict(row) for row in self.repo.latest_requests(limit)]

    def _request_approval(self, task_id: str, key: str, permission_level: str, action: str, target: str, reason: str, risk: str, tool_name: str) -> ApprovalRequest:
        pending = self.repo.pending_equivalent(task_id, key)
        if pending:
            return ApprovalRequest(
                request_id=pending["request_id"],
                task_id=pending["task_id"],
                operation_key=pending["operation_key"],
                action=pending["action"],
                target=pending["target"],
                reason=pending["reason"],
                risk_level=pending["risk_level"],
                permission_level=pending["permission_level"],
                status=pending["status"],
                created_at=pending["created_at"],
            )
        request = ApprovalRequest(
            task_id=task_id,
            operation_key=key,
            action=action,
            target=target,
            reason=reason or "A acao exige autorizacao.",
            risk_level=risk,
            permission_level=permission_level,
            metadata={"tool_name": tool_name},
        )
        self.repo.add_request(request)
        self._audit("APPROVAL_REQUESTED", "PENDING", request.request_id, f"{permission_level}:{target}")
        self.record_event(
            task_id=task_id,
            category="APPROVAL",
            action="APPROVAL_REQUESTED",
            status=ExecutionStatus.WAITING_APPROVAL.value,
            summary=f"Aguardando aprovacao para {action}",
            details=request.reason,
            target=target,
            tool_name=tool_name,
            permission_level=permission_level,
            risk_level=risk,
        )
        return request

    def _allowed(self, task_id: str, permission_level: str, action: str, target: str, risk: str, reason: str) -> None:
        self._audit("ACTION_ALLOWED", "ALLOWED", target, reason)
        self.record_event(
            task_id=task_id,
            category="PERMISSION",
            action="ACTION_ALLOWED",
            status=ExecutionStatus.COMPLETED.value,
            summary=reason,
            target=target,
            permission_level=permission_level,
            risk_level=risk,
        )

    def _blocked(self, task_id: str, permission_level: str, action: str, target: str, risk: str, reason: str) -> None:
        self._audit("ACTION_BLOCKED", "BLOCKED", target, reason)
        self.record_event(
            task_id=task_id,
            category="PERMISSION",
            action="ACTION_BLOCKED",
            status=ExecutionStatus.BLOCKED.value,
            summary=reason,
            target=target,
            permission_level=permission_level,
            risk_level=risk,
        )

    def _event_row(self, row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    def _audit(self, action_type: str, status: str, target: str = "", detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "core.execution",
            "target": str(target),
            "result": str(detail)[:800],
            "files_changed": [],
            "commands_executed": [],
        })
