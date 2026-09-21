from __future__ import annotations

from .diff_service import diff_hash
from .models import ApprovalToken, CodingTask


def create_approval(task: CodingTask) -> ApprovalToken:
    return ApprovalToken(
        task_id=task.task_id,
        source_path=task.source_path,
        source_hash=task.source_hash,
        diff_hash=task.diff_hash,
    )


def approval_matches(task: CodingTask, approval_row, current_diff: str) -> tuple[bool, str]:
    if not approval_row:
        return False, "aprovacao ausente"
    if approval_row["task_id"] != task.task_id:
        return False, "aprovacao pertence a outra tarefa"
    if approval_row["source_path"] != task.source_path:
        return False, "arquivo da aprovacao nao confere"
    if approval_row["source_hash"] != task.source_hash:
        return False, "hash original da aprovacao nao confere"
    current_hash = diff_hash(current_diff)
    if approval_row["diff_hash"] != current_hash:
        return False, "diff mudou depois da aprovacao"
    if approval_row["status"] != "GRANTED":
        return False, "aprovacao nao concedida"
    return True, "aprovacao valida"
