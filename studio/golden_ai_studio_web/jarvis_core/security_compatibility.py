"""Bounded compatibility bridge from legacy tool calls to Jarvis security.

Only tools with an exact canonical handler/argument contract are migrated.
Unknown or unsupported legacy tools return ``None`` so their existing path can
be classified separately; a selected migrated tool fails closed if the
canonical service is unavailable.
"""

from __future__ import annotations

from typing import Any, Callable

from .models import Risk, Tool


class ExecutionSecurityFacade:
    """Small read-only compatibility facade owned by canonical SecurityManager.

    This adapter makes no execution decision of its own and never dispatches a
    handler. It is intentionally limited to deterministic low-risk reads.
    """

    READ_TOOL_NAMES = {
        "read": "legacy_read",
        "read_file": "legacy_read",
        "internet_search": "legacy_internet_search",
        "internet_fetch": "legacy_internet_fetch",
    }

    def __init__(self, security_manager):
        self.security = security_manager

    def authorize(self, *, action, target="", task_id="", reason=""):
        tool_name = self.READ_TOOL_NAMES.get(str(action or "").casefold())
        if not tool_name:
            return {
                "allowed": False,
                "status": "BLOCKED",
                "reason": "Ação fora do escopo seguro do adaptador canônico.",
            }
        tool = Tool(
            tool_name,
            f"Legacy read compatibility: {action}",
            lambda **_: {"ok": True},
            risk=Risk.LOW,
            confirmation=False,
            parameters={"target": str},
            side_effect_class="READ_ONLY",
            provenance="legacy_compatibility",
            capability_name=tool_name,
        )
        try:
            decision = self.security.decision(tool, risk=Risk.LOW,
                                              requires_confirmation=False)
        except Exception:
            return {
                "allowed": False,
                "status": "BLOCKED",
                "reason": "Canonical SecurityManager indisponível; leitura bloqueada.",
            }
        if decision == "allow":
            return {
                "allowed": True,
                "status": "COMPLETED",
                "reason": "Leitura autorizada pelo SecurityManager canônico.",
            }
        if decision == "confirm":
            return {
                "allowed": False,
                "status": "WAITING_APPROVAL",
                "reason": "SecurityManager canônico exige aprovação para esta leitura.",
            }
        return {
            "allowed": False,
            "status": "BLOCKED",
            "reason": "Leitura bloqueada pelo SecurityManager canônico.",
        }


class LegacySecurityBridge:
    """Route a small, proven legacy subset through JarvisService."""

    MIGRATED_TOOLS = frozenset({"open_file", "delete_file"})

    def __init__(self, service_provider: Callable[[], Any]):
        self._service_provider = service_provider

    def execute(self, tool_call: dict[str, Any], session_id: str = "default"):
        name = str((tool_call or {}).get("tool") or "")
        if name not in self.MIGRATED_TOOLS:
            return None

        try:
            service = self._service_provider()
        except Exception:
            service = None
        if service is None or not hasattr(service, "execute_tool"):
            return {
                "ok": False,
                "error": "Canonical SecurityManager indisponível; ação bloqueada.",
                "security_owner": "jarvis_core.security.SecurityManager",
                "security_fail_closed": True,
            }

        arguments = {key: value for key, value in (tool_call or {}).items()
                     if key != "tool"}
        allowed_arguments = {"path"}
        if set(arguments) - allowed_arguments or "path" not in arguments:
            return {
                "ok": False,
                "error": "Argumentos incompatíveis com o contrato canônico.",
                "security_owner": "jarvis_core.security.SecurityManager",
                "security_fail_closed": True,
            }

        result = service.execute_tool(
            name,
            arguments,
            command=f"legacy:{name}",
            task_id=str(session_id or "default"),
        )
        result = dict(result or {})
        result["security_owner"] = "jarvis_core.security.SecurityManager"
        result["audit_owner"] = "jarvis_core.audit.AuditLog"
        result["compatibility_bridge"] = True
        if result.get("confirmation_required") and result.get("token"):
            result["approval_backend"] = "jarvis_core"
            result["request_id"] = f"jarvis:{result['token']}"
            result["approval_scope"] = "ONCE"
        return result


__all__ = ["ExecutionSecurityFacade", "LegacySecurityBridge"]
