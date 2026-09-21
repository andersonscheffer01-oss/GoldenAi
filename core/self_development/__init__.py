"""Self-Development system for GoldenAI.

Allows GoldenAI to work on its own code in a controlled, safe manner
using Codex CLI + Ollama/Qwen local models. No paid API required.

SECURITY CONTRACT
-----------------
- PermissionManager is the sole authority
- Critical files cannot be modified without explicit approval
- AuditLogger records all actions
- Circuit Breaker from Multi-Model Local V1 is reused
- No paid API fallback — local Ollama models only
"""
from .checkpoint import SelfDevCheckpointStore
from .manager import SelfDevelopmentManager
from .models import (
    CRITICAL_PATHS,
    SelfDevCheckpoint,
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_INTERRUPTED,
    TASK_PLANNED,
    TASK_ROLLED_BACK,
    TASK_RUNNING,
    TASK_VALIDATING,
    TASK_WAITING_PERMISSION,
    is_critical_path,
)

__all__ = [
    "SelfDevelopmentManager",
    "SelfDevCheckpointStore",
    "SelfDevCheckpoint",
    "CRITICAL_PATHS",
    "is_critical_path",
    "TASK_PLANNED",
    "TASK_RUNNING",
    "TASK_WAITING_PERMISSION",
    "TASK_VALIDATING",
    "TASK_COMPLETED",
    "TASK_FAILED",
    "TASK_ROLLED_BACK",
    "TASK_INTERRUPTED",
]