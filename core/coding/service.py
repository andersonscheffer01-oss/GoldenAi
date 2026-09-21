from __future__ import annotations

import os
import re
from pathlib import Path

from core.audit import AuditLogger
from core.config import GoldenAISettings
from core.execution import ExecutionService
from core.permissions import PermissionManager
from core.tools.checkpoint import CheckpointService
from core.tools.hashing import sha256_file

from .approval import approval_matches, create_approval
from .diff_service import diff_hash, unified_diff
from .models import CodingTask, now_iso
from .repository import CodingRepository
from .rollback import restore_checkpoint_file
from .validation import CodingValidator
from .workspace import CodingWorkspace


class CodingService:
    def __init__(self, root: str | Path = r"C:\GoldenAI"):
        self.root = Path(root)
        self.db_path = self.root / "data" / "golden_ai.db"
        self.repo = CodingRepository(self.db_path)
        self.workspace = CodingWorkspace(self.root)
        self.validator = CodingValidator(self.root / ".venv" / "Scripts" / "python.exe")
        settings = GoldenAISettings(
            root=self.root,
            projects_dir=self.root / "projetos",
            backups_dir=self.root / "backups",
            logs_dir=self.root / "logs",
            sandbox_dir=self.root / "sandbox",
            data_dir=self.root / "data",
            allowed_paths=(self.root / "projetos", self.root / "workspace", self.root / "data", self.root / "logs"),
            protected_paths=(self.root / "app", self.root / "core", self.root / "studio", self.root / "backups"),
        )
        self.permission_manager = PermissionManager(settings)
        self.audit = AuditLogger(self.root / "logs")
        self.execution = ExecutionService(self.root)
        self.checkpoints = CheckpointService(root=self.root / "backups" / "checkpoints")

    def _audit(self, action_type: str, status: str, task: CodingTask | None = None, detail: str = "") -> None:
        self.audit.record({
            "action_type": action_type,
            "status": status,
            "agent": "core.coding",
            "target": task.source_path if task else "",
            "input_summary": task.task_id if task else "",
            "result": detail[:800],
            "files_changed": [],
            "commands_executed": [],
        })
        if task:
            self.repo.add_event(task.task_id, action_type, status, detail)
            category = self._execution_category(action_type)
            self.execution.record_event(
                task_id=task.task_id,
                category=category,
                action=action_type,
                status=self._execution_status(status),
                summary=self._execution_summary(action_type, status, detail),
                details=detail[:2000],
                target=task.source_path,
                agent="core.coding",
                permission_level="WRITE" if action_type.startswith("SOURCE_WRITE") else "READ",
                risk_level="MEDIUM" if action_type.startswith(("SOURCE_WRITE", "CHECKPOINT", "ROLLBACK")) else "LOW",
            )

    def _execution_category(self, action_type: str) -> str:
        if "VALIDATION" in action_type:
            return "VALIDATION"
        if "DIFF" in action_type:
            return "DIFF"
        if "APPROVAL" in action_type:
            return "APPROVAL"
        if "CHECKPOINT" in action_type:
            return "CHECKPOINT"
        if "ROLLBACK" in action_type:
            return "ROLLBACK"
        if "WRITE" in action_type:
            return "CODE"
        if "WORKSPACE" in action_type:
            return "CODE"
        return "TASK"

    def _execution_status(self, status: str) -> str:
        value = str(status or "").upper()
        if value in {"PASSED", "GRANTED", "CREATED"}:
            return "COMPLETED"
        if value == "PENDING":
            return "WAITING_APPROVAL"
        if value in {"REJECTED", "CANCELLED"}:
            return "CANCELLED"
        return value

    def _execution_summary(self, action_type: str, status: str, detail: str = "") -> str:
        labels = {
            "CODING_TASK_CREATED": "Tarefa de programacao criada",
            "WORKSPACE_CREATED": "Sandbox criado",
            "CODING_ANALYSIS_COMPLETED": "Analise concluida",
            "CODING_PLAN_CREATED": "Plano criado",
            "WORKING_COPY_MODIFIED": "Working copy preparada",
            "DIFF_CREATED": "Diff criado",
            "VALIDATION_STARTED": "Validacao iniciada",
            "VALIDATION_PASSED": "Validacao concluida",
            "VALIDATION_FAILED": "Validacao falhou",
            "APPROVAL_REQUESTED": "Aguardando aprovacao",
            "APPROVAL_GRANTED": "Aprovacao concedida",
            "APPROVAL_REJECTED": "Aprovacao rejeitada",
            "CHECKPOINT_CREATED": "Checkpoint criado",
            "SOURCE_WRITE_STARTED": "Aplicacao iniciada",
            "SOURCE_WRITE_COMPLETED": "Alteracao aplicada",
            "SOURCE_WRITE_FAILED": "Aplicacao falhou",
            "ROLLBACK_STARTED": "Rollback iniciado",
            "ROLLBACK_COMPLETED": "Rollback concluido",
        }
        return labels.get(action_type, action_type.replace("_", " ").title())

    def _analysis_for(self, request: str, source: Path, language: str) -> str:
        text = source.read_text(encoding="utf-8", errors="replace")
        functions = re.findall(r"^\s*(?:def\s+([A-Za-z_]\w*)|(?:void|int|double|bool|string)\s+([A-Za-z_]\w*)\s*\()", text, flags=re.MULTILINE)
        names = [a or b for a, b in functions][:8]
        return (
            f"Arquivo alvo: {source}\n"
            f"Linguagem: {language}\n"
            f"Pedido: {request}\n"
            f"Funcoes relacionadas detectadas: {', '.join(names) if names else 'Ainda sem dados'}\n"
            "Escopo permitido: somente working copy no workspace ate aprovacao explicita.\n"
            "Riscos: alteracao bloqueada se hash original ou diff mudarem."
        )

    def _plan_for(self, request: str, source: Path, language: str) -> str:
        return (
            f"Objetivo: preparar alteracao solicitada sem tocar no original.\n"
            f"Arquivo afetado: {source.name}\n"
            f"Linguagem: {language}\n"
            "Arquivos previstos: 1\n"
            "Risco: medio\n"
            "Validacao: pre-aplicacao na working copy e pos-aplicacao no original aprovado."
        )

    def create_task(self, user_request: str, source_path: str | Path) -> CodingTask:
        source = Path(source_path).resolve()
        if not self.workspace.is_authorized_source(source):
            raise PermissionError("CodingTask bloqueada: fonte fora de C:\\GoldenAI\\projetos ou protegida")
        task_id = self.workspace.new_task_id()
        workspace_info = self.workspace.create(task_id, source)
        language = self.workspace.language_for(source)
        task = CodingTask(
            task_id=task_id,
            created_at=now_iso(),
            updated_at=now_iso(),
            status="CREATED",
            user_request=user_request,
            source_path=str(source),
            source_hash=workspace_info["source_hash"],
            workspace_path=workspace_info["task_root"],
            language=language,
        )
        self.repo.save_task(task)
        self.repo.add_file(task_id, "original", workspace_info["original"], workspace_info["original_hash"])
        self.repo.add_file(task_id, "working", workspace_info["working"], workspace_info["working_hash"])
        self._audit("CODING_TASK_CREATED", "CREATED", task)
        self._audit("WORKSPACE_CREATED", "COMPLETED", task, task.workspace_path)
        return task

    def analyze_and_plan(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        source = Path(task.source_path)
        task.status = "PLANNED"
        task.analysis = self._analysis_for(task.user_request, source, task.language)
        task.plan = self._plan_for(task.user_request, source, task.language)
        task.updated_at = now_iso()
        self.repo.save_task(task)
        self._audit("CODING_ANALYSIS_COMPLETED", "COMPLETED", task)
        self._audit("CODING_PLAN_CREATED", "COMPLETED", task)
        return task

    def apply_controlled_python_change(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        working = self.workspace.working_path(task.task_id, task.source_path)
        text = working.read_text(encoding="utf-8", errors="replace")
        lowered = task.user_request.lower()
        changed = text
        if "soma" in lowered and ("tres" in lowered or "três" in lowered or "3" in lowered):
            changed = re.sub(r"def\s+soma\s*\(\s*a\s*,\s*b\s*\)\s*:", "def soma(a, b, c):", changed)
            changed = re.sub(r"return\s+a\s*\+\s*b\b", "return a + b + c", changed)
        if changed == text:
            raise ValueError("Nenhuma alteracao controlada disponivel para este pedido na V1")
        working.write_text(changed, encoding="utf-8")
        return self.finalize_working_copy(task_id)

    def replace_working_text(self, task_id: str, new_text: str) -> CodingTask:
        task = self.require_task(task_id)
        working = self.workspace.working_path(task.task_id, task.source_path)
        working.write_text(new_text, encoding="utf-8")
        return self.finalize_working_copy(task_id)

    def finalize_working_copy(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        source = Path(task.source_path)
        if sha256_file(source) != task.source_hash:
            task.status = "FAILED"
            task.result = "O arquivo original mudou desde o inicio desta tarefa."
            self.repo.save_task(task)
            self._audit("WORKING_COPY_MODIFIED", "FAILED", task, task.result)
            return task

        original = self.workspace.original_copy_path(task.task_id, task.source_path)
        working = self.workspace.working_path(task.task_id, task.source_path)
        diff_text = unified_diff(original, working)
        task.diff = diff_text
        task.diff_hash = diff_hash(diff_text)
        task.status = "VALIDATING"
        task.updated_at = now_iso()
        self.workspace.diff_path(task.task_id).write_text(diff_text, encoding="utf-8")
        self.repo.save_task(task)
        self._audit("WORKING_COPY_MODIFIED", "COMPLETED", task)
        self._audit("DIFF_CREATED", "COMPLETED", task, task.diff_hash)

        self._audit("VALIDATION_STARTED", "STARTED", task, "pre_apply")
        validation = self.validator.validate(working, phase="pre_apply")
        self.repo.add_validation(task.task_id, validation.phase, validation.ok, validation.status, validation.output)
        task.validation_status = validation.status
        task.status = "AWAITING_APPROVAL" if validation.ok and diff_text else "FAILED"
        task.result = validation.output
        task.updated_at = now_iso()
        self.repo.save_task(task)
        self._audit("VALIDATION_PASSED" if validation.ok else "VALIDATION_FAILED", validation.status, task, validation.output)
        if task.status == "AWAITING_APPROVAL":
            self._audit("APPROVAL_REQUESTED", "PENDING", task)
        return task

    def approve(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        if task.status != "AWAITING_APPROVAL":
            raise ValueError("Tarefa nao esta aguardando aprovacao")
        token = create_approval(task)
        task.approval_status = "GRANTED"
        task.approval_token = token.as_token()
        task.status = "APPROVED"
        task.updated_at = now_iso()
        self.repo.add_approval(task.task_id, task.source_path, task.source_hash, task.diff_hash, task.approval_token, "GRANTED")
        self.repo.save_task(task)
        self._audit("APPROVAL_GRANTED", "GRANTED", task)
        return task

    def reject(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        task.approval_status = "REJECTED"
        task.status = "CANCELLED"
        task.updated_at = now_iso()
        self.repo.add_approval(task.task_id, task.source_path, task.source_hash, task.diff_hash, "", "REJECTED")
        self.repo.save_task(task)
        self._audit("APPROVAL_REJECTED", "REJECTED", task)
        return task

    def cancel(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        task.approval_status = "CANCELLED"
        task.status = "CANCELLED"
        task.updated_at = now_iso()
        self.repo.save_task(task)
        self._audit("APPROVAL_REJECTED", "CANCELLED", task, "cancelada pelo usuario")
        return task

    def apply_approved(self, task_id: str) -> CodingTask:
        task = self.require_task(task_id)
        current_diff = unified_diff(
            self.workspace.original_copy_path(task.task_id, task.source_path),
            self.workspace.working_path(task.task_id, task.source_path),
        )
        approval = self.repo.latest_approval(task.task_id)
        valid_approval, reason = approval_matches(task, approval, current_diff)
        source_hash_valid = sha256_file(task.source_path) == task.source_hash
        checkpoint = None
        if source_hash_valid:
            checkpoint = self.checkpoints.create_checkpoint(task.source_path, reason="CodingTask approved apply", origin="core.coding")
            self._audit("CHECKPOINT_CREATED", "COMPLETED", task, checkpoint.checkpoint_id)

        decision = self.permission_manager.can_write_approved_coding_task({
            "task_valid": task.status == "APPROVED",
            "approval_valid": valid_approval,
            "path_authorized": self.workspace.is_authorized_source(task.source_path),
            "source_hash_valid": source_hash_valid,
            "diff_hash_valid": task.diff_hash == diff_hash(current_diff),
            "checkpoint_created": checkpoint is not None,
            "source_path": task.source_path,
        })
        if not decision.allowed:
            task.status = "FAILED"
            task.result = decision.reason if valid_approval else reason
            task.updated_at = now_iso()
            self.repo.save_task(task)
            self._audit("SOURCE_WRITE_FAILED", "FAILED", task, task.result)
            return task

        task.status = "APPLYING"
        task.checkpoint_id = checkpoint.checkpoint_id
        task.updated_at = now_iso()
        self.repo.save_task(task)
        self._audit("SOURCE_WRITE_STARTED", "STARTED", task)

        source = Path(task.source_path)
        working = self.workspace.working_path(task.task_id, task.source_path)
        temp = source.with_name(source.name + ".coding_tmp")
        try:
            data = working.read_bytes()
            with temp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, source)
            self._audit("SOURCE_WRITE_COMPLETED", "COMPLETED", task)
        except Exception as exc:
            if temp.exists():
                temp.unlink()
            task.status = "FAILED"
            task.result = str(exc)
            self.repo.save_task(task)
            self._audit("SOURCE_WRITE_FAILED", "FAILED", task, str(exc))
            return task

        validation = self.validator.validate(source, phase="post_apply")
        self.repo.add_validation(task.task_id, validation.phase, validation.ok, validation.status, validation.output)
        if validation.ok:
            task.status = "COMPLETED"
            task.validation_status = validation.status
            task.result = validation.output
            task.updated_at = now_iso()
            self.repo.save_task(task)
            self._audit("VALIDATION_PASSED", "PASSED", task, "post_apply")
            return task

        self._audit("VALIDATION_FAILED", "FAILED", task, validation.output)
        self._audit("ROLLBACK_STARTED", "STARTED", task, checkpoint.checkpoint_path)
        restore_checkpoint_file(checkpoint.checkpoint_path, source)
        restored = sha256_file(source) == checkpoint.sha256
        task.status = "ROLLED_BACK" if restored else "FAILED"
        task.rollback_status = "COMPLETED" if restored else "FAILED"
        task.result = "A alteracao falhou na validacao e a versao anterior foi restaurada." if restored else "Rollback falhou."
        task.updated_at = now_iso()
        self.repo.save_task(task)
        self._audit("ROLLBACK_COMPLETED", task.rollback_status, task, task.result)
        return task

    def recover_open_tasks(self) -> list[CodingTask]:
        rows = self.repo.fetchall(
            "SELECT * FROM coding_tasks WHERE status IN ('AWAITING_APPROVAL', 'APPLYING', 'APPROVED') ORDER BY updated_at DESC"
        )
        recovered = []
        for row in rows:
            task = CodingTask(**dict(row))
            if task.status == "APPLYING":
                task.status = "FAILED"
                task.result = "Studio reiniciado durante APPLYING; estado seguro exige nova analise."
                task.updated_at = now_iso()
                self.repo.save_task(task)
            recovered.append(task)
        return recovered

    def latest_awaiting_approval(self) -> CodingTask | None:
        return self.repo.latest_awaiting_approval()

    def require_task(self, task_id: str) -> CodingTask:
        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(task_id)
        return task
