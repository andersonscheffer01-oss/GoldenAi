from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config import GoldenAISettings, load_settings
from core.execution import ExecutionService, PermissionMode, RiskLevel


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str


class PermissionManager:
    def __init__(self, settings: GoldenAISettings | None = None):
        self.settings = settings or load_settings()
        self.execution = ExecutionService(self.settings.root)

    def is_read_only(self) -> bool:
        return self.settings.read_only or not self.settings.write_enabled

    def _resolve(self, path: str | Path) -> Path:
        return Path(path).resolve()

    def _is_under(self, path: Path, roots: tuple[Path, ...]) -> bool:
        for root in roots:
            try:
                path.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False

    def is_protected_dir(self, path: str | Path) -> bool:
        return self._is_under(self._resolve(path), self.settings.protected_paths)

    def can_read(self, path: str | Path) -> PermissionDecision:
        resolved = self._resolve(path)
        if self._is_under(resolved, self.settings.allowed_paths) or self.is_protected_dir(resolved):
            return PermissionDecision(True, "read allowed by configured path policy")
        return PermissionDecision(False, "path is outside allowed/protected project areas")

    def can_write(self, path: str | Path, explicit_authorization: bool = False) -> PermissionDecision:
        resolved = self._resolve(path)
        mode = self.execution.get_mode()
        if self.settings.read_only:
            return PermissionDecision(False, "read-only mode blocks writes")
        if self.is_read_only() and mode == PermissionMode.READ_ONLY:
            return PermissionDecision(False, "read-only mode blocks writes")
        if self.is_protected_dir(resolved):
            return PermissionDecision(False, "protected directory blocks writes")
        if self._is_under(resolved, self.settings.allowed_paths):
            if explicit_authorization:
                return PermissionDecision(True, "write allowed with explicit authorization")
            decision = self.execution.authorize_action(
                task_id="permission-manager",
                permission_level="WRITE",
                action="write_file",
                target=str(resolved),
                reason="write requires approval policy",
                risk_level=RiskLevel.MEDIUM,
                capability_exists=True,
            )
            return PermissionDecision(decision.allowed, decision.reason)
        return PermissionDecision(False, "path is outside allowed write areas")

    def can_execute_command(self, command: str, explicit_authorization: bool = False) -> PermissionDecision:
        if not self.settings.command_execution_enabled:
            return PermissionDecision(False, "command execution is disabled")
        if not explicit_authorization:
            decision = self.execution.authorize_action(
                task_id="permission-manager",
                permission_level="EXECUTE",
                action=str(command),
                target=str(command),
                reason="command requires approval policy",
                risk_level=RiskLevel.MEDIUM,
                capability_exists=True,
            )
            return PermissionDecision(decision.allowed, decision.reason)
        return PermissionDecision(True, "command execution allowed by policy")

    def can_read_external_safe(self, purpose: str, path: str | Path | None = None) -> PermissionDecision:
        allowed_purposes = {
            "datetime",
            "system_info",
            "disk_usage",
            "process_list",
            "find_installed_app",
            "mt5_status",
            "mt5_read",
        }
        if purpose not in allowed_purposes:
            return PermissionDecision(False, "READ_EXTERNAL_SAFE purpose is not allowed")

        if path is None:
            return PermissionDecision(True, "READ_EXTERNAL_SAFE allowed for system API query")

        resolved = self._resolve(path)
        safe_roots = (
            self.settings.root,
            Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal",
            Path(r"C:\Program Files"),
            Path(r"C:\Program Files (x86)"),
        )
        if self._is_under(resolved, tuple(root for root in safe_roots if root.exists())):
            return PermissionDecision(True, "READ_EXTERNAL_SAFE allowed for explicit safe root")
        if str(resolved).upper() == "C:\\":
            return PermissionDecision(True, "READ_EXTERNAL_SAFE allowed for disk usage root")
        return PermissionDecision(False, "READ_EXTERNAL_SAFE blocks this path")

    def can_launch_allowed_app(self, app_name: str) -> PermissionDecision:
        allowed = {
            "metatrader 5",
            "metaeditor",
            "notepad",
            "explorer",
            "browser",
            "golden ai studio",
        }
        if str(app_name).lower() in allowed:
            return PermissionDecision(True, "EXECUTE allowed for allowlisted application")
        return PermissionDecision(False, "EXECUTE blocked: app is not allowlisted")

    def can_open_folder(self, path: str | Path) -> PermissionDecision:
        resolved = self._resolve(path)
        allowed = (
            self.settings.root,
            self.settings.projects_dir,
            self.settings.logs_dir,
            self.settings.backups_dir,
            Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal",
        )
        if self._is_under(resolved, tuple(root for root in allowed if root.exists())):
            return PermissionDecision(True, "EXECUTE allowed for allowlisted folder")
        return PermissionDecision(False, "EXECUTE blocked: folder is not allowlisted")

    def can_write_approved_coding_task(self, task: dict) -> PermissionDecision:
        required = (
            "task_valid",
            "approval_valid",
            "path_authorized",
            "source_hash_valid",
            "diff_hash_valid",
            "checkpoint_created",
        )
        missing = [key for key in required if not bool(task.get(key))]
        if missing:
            return PermissionDecision(False, "WRITE_APPROVED_CODING_TASK blocked: missing " + ", ".join(missing))

        resolved = self._resolve(task.get("source_path", ""))
        if self.is_protected_dir(resolved):
            return PermissionDecision(False, "WRITE_APPROVED_CODING_TASK blocked: protected Golden AI path")
        if not self._is_under(resolved, (self.settings.projects_dir,)):
            return PermissionDecision(False, "WRITE_APPROVED_CODING_TASK blocked: source is outside projects")
        mt5_terminal = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
        if mt5_terminal.exists() and self._is_under(resolved, (mt5_terminal,)):
            return PermissionDecision(False, "WRITE_APPROVED_CODING_TASK blocked: real MT5 terminal path")
        return PermissionDecision(True, "WRITE_APPROVED_CODING_TASK allowed for this approved task only")


    def can_internet_search(self, query=None):
        if not getattr(self.settings, 'internet_enabled', False):
            return PermissionDecision(False, 'Internet desativado')
        decision = self.execution.authorize_action(task_id='permission-manager', permission_level='READ', action='internet_search', target=str(query or '')[:200], reason='Pesquisa requer autorizacao', risk_level=RiskLevel.LOW, capability_exists=True)
        return PermissionDecision(decision.allowed, decision.reason)

    def can_internet_fetch(self, url=None):
        if not getattr(self.settings, 'internet_enabled', False):
            return PermissionDecision(False, 'Internet desativado')
        decision = self.execution.authorize_action(task_id='permission-manager', permission_level='READ', action='internet_fetch', target=str(url or '')[:300], reason='Consulta de pagina requer autorizacao', risk_level=RiskLevel.LOW, capability_exists=True)
        return PermissionDecision(decision.allowed, decision.reason)

    def can_internet_download(self, url=None, dest=None):
        if not getattr(self.settings, 'internet_enabled', False):
            return PermissionDecision(False, 'Internet desativado')
        if self.settings.read_only:
            return PermissionDecision(False, 'read-only mode blocks downloads')
        decision = self.execution.authorize_action(task_id='permission-manager', permission_level='WRITE', action='internet_download', target=str(url or '')[:300], reason='Download requer autorizacao explicita', risk_level=RiskLevel.HIGH, capability_exists=True)
        return PermissionDecision(decision.allowed, decision.reason)

    def can_execute_downloaded_file(self, path):
        resolved = self._resolve(path)
        if self.is_protected_dir(resolved):
            return PermissionDecision(False, 'protected directory blocks execution')
        if not self._is_under(resolved, self.settings.allowed_paths):
            return PermissionDecision(False, 'file is outside allowed areas')
        decision = self.execution.authorize_action(task_id='permission-manager', permission_level='EXECUTE', action='execute_downloaded_file', target=str(resolved), reason='Execucao requer autorizacao SEPARADA do download', risk_level=RiskLevel.HIGH, capability_exists=True)
        return PermissionDecision(decision.allowed, decision.reason)
