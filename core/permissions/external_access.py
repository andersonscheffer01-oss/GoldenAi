from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.audit import AuditLogger
from core.config import load_settings
from core.execution import ApprovalRequest, ExecutionService, ExecutionStatus


@dataclass(frozen=True)
class ExternalAccessDecision:
    allowed: bool
    request_id: str = ""
    reason: str = ""
    consumed: bool = False
    scope: str = ""


class ExternalAccessService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.settings = load_settings()
        self.execution = ExecutionService(self.root)
        self.audit = AuditLogger(self.root / "logs")

    def is_external(self, path: str | Path) -> bool:
        resolved = Path(path).resolve()
        allowed = tuple(root.resolve() for root in self.settings.allowed_paths + self.settings.protected_paths if root.exists())
        for root in allowed:
            try:
                resolved.relative_to(root)
                return False
            except ValueError:
                continue
        return True

    def request_read(self, task_id: str, path: str | Path, reason: str) -> ExternalAccessDecision:
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        key = self.operation_key("READ", resolved)
        existing = self.execution.repo.pending_equivalent(task_id, key)
        if existing:
            return ExternalAccessDecision(False, existing["request_id"], "Aguardando autorizacao")
        request = ApprovalRequest(
            task_id=task_id,
            operation_key=key,
            action="read_external_file",
            target=str(resolved),
            reason=reason,
            risk_level="LOW",
            permission_level="READ_EXTERNAL",
            metadata={"path": str(resolved), "operation": "READ"},
        )
        self.execution.repo.add_request(request)
        self._record("EXTERNAL_ACCESS_APPROVAL_CREATED", "WAITING_APPROVAL", resolved, "Aguardando autorizacao READ externa", task_id)
        return ExternalAccessDecision(False, request.request_id, "Aguardando autorizacao")

    def check_read(self, task_id: str, path: str | Path) -> ExternalAccessDecision:
        resolved = self.canonical_path(path)
        if not self.is_external(resolved):
            return ExternalAccessDecision(True, reason="Path interno permitido")
        key = self.operation_key("READ", resolved)
        once = self.execution.repo.granted_once(task_id, key)
        if once:
            return ExternalAccessDecision(True, once["request_id"], "Permitido uma vez", scope="ONCE")
        task = self.execution.repo.granted_for_task(task_id, key)
        if task:
            self._record("EXTERNAL_ACCESS_USED", "COMPLETED", resolved, "Acesso READ externo usado nesta tarefa", task_id)
            return ExternalAccessDecision(True, task["request_id"], "Permitido nesta tarefa", scope="TASK")
        return self.request_read(task_id, resolved, "Analisar o arquivo solicitado em modo somente leitura.")

    def deny(self, request_id: str) -> None:
        self.execution.deny(request_id)
        self._record("EXTERNAL_ACCESS_DENIED", "BLOCKED", "", request_id, "external-access")

    def grant_once(self, request_id: str) -> None:
        self.execution.grant_once(request_id)
        self._record("EXTERNAL_ACCESS_APPROVED_ONCE", "COMPLETED", "", request_id, "external-access")

    def grant_for_task(self, request_id: str) -> None:
        self.execution.grant_for_task(request_id)
        self._record("EXTERNAL_ACCESS_APPROVED_TASK", "COMPLETED", "", request_id, "external-access")

    def read_text_after_approval(self, task_id: str, path: str | Path, max_bytes: int = 80_000) -> str:
        resolved = self.canonical_path(path)
        decision = self.check_read(task_id, resolved)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        self._record("EXTERNAL_ACCESS_USED", "COMPLETED", resolved, "Reading authorized external file", task_id)
        if resolved.stat().st_size > max_bytes:
            text = resolved.read_text(encoding="utf-8", errors="replace")[:max_bytes]
        else:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        self._record("EXTERNAL_READ_COMPLETED", "COMPLETED", resolved, "Read completed", task_id)
        if decision.scope == "ONCE" and decision.request_id:
            self.execution.repo.update_request(decision.request_id, "GRANTED_ONCE", consumed=True)
            self._record("EXTERNAL_ACCESS_EXPIRED", "COMPLETED", resolved, "Temporary authorization expired", task_id)
        return text

    def operation_key(self, operation: str, path: str | Path) -> str:
        return f"{operation.upper()}_EXTERNAL|{self.canonical_path(path)}"

    def canonical_path(self, path: str | Path) -> Path:
        return Path(str(path).strip().strip('"')).resolve()

    def _record(self, action: str, status: str, target: str | Path, summary: str, task_id: str) -> None:
        self.execution.record_event(
            task_id=task_id,
            category="PERMISSION",
            action=action,
            status=status if status in {s.value for s in ExecutionStatus} else ExecutionStatus.COMPLETED.value,
            summary=summary,
            target=str(target),
            tool_name="external_access",
            permission_level="READ_EXTERNAL",
            risk_level="LOW",
        )
        self.audit.record({
            "action_type": action,
            "status": status,
            "agent": "core.permissions.external_access",
            "target": str(target),
            "result": summary,
        })
