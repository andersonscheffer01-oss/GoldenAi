import copy
import hmac
import json
import ipaddress
import secrets
import time
import uuid
from urllib.parse import urlparse

from .models import BROWSER_READ, Risk


READ_ONLY_PUBLIC_BROWSER_OBSERVATION = "READ_ONLY_PUBLIC_BROWSER_OBSERVATION"
COMPUTER_USE_MISSION_PRE_SAVE = "COMPUTER_USE_MISSION_PRE_SAVE"


def is_public_browser_url(url):
    """Return whether a URL is suitable for a public read-only observation."""
    try:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme.casefold() not in {"http", "https"} or not host:
            return False
        if parsed.username or parsed.password or host in {"localhost", "localhost.localdomain"}:
            return False
        if host.endswith((".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host)
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except (TypeError, ValueError):
        return False


def browser_host_matches(url, allowed_hosts=()):
    try:
        host = (urlparse(str(url or "")).hostname or "").casefold().rstrip(".")
    except (TypeError, ValueError):
        return False
    for allowed in allowed_hosts or ():
        expected = str(allowed or "").casefold().lstrip(".").rstrip(".")
        if expected and (host == expected or host.endswith("." + expected)):
            return True
    return False

class SecurityManager:
    def __init__(self, rules=None, confirmation_ttl=60, audit_log=None):
        self.rules = rules or {}
        self.confirmation_ttl = confirmation_ttl
        self.pending = {}
        self.audit = audit_log

    def set_audit_log(self, audit_log):
        self.audit = audit_log

    @staticmethod
    def _audit_target(arguments):
        if not isinstance(arguments, dict):
            return ""
        for key in ("target", "path", "url", "symbol", "ticket"):
            if key in arguments:
                return arguments[key]
        return ""

    def _audit_event(self, *, action, status, tool="", arguments=None,
                     command="", risk="", security_decision="", context=None,
                     result=None, error="", approval_id=""):
        if self.audit is None or context is None:
            return
        context = dict(context or {})
        envelope = {
            "request_id": context.get("request_id", ""),
            "correlation_id": context.get("correlation_id", ""),
            "session_id": context.get("session_id", ""),
            "conversation_id": context.get("conversation_id", ""),
            "task_id": context.get("task_id", ""),
            "mission_id": context.get("mission_id", ""),
            "run_id": context.get("run_id", ""),
            "approval_id": approval_id or context.get("approval_id", ""),
            "surface": context.get("surface", "jarvis_core"),
            "operation": context.get("operation", tool or command),
            "action": action,
            "target": context.get("target") or self._audit_target(arguments),
            "tool": tool,
            "provider": context.get("provider", ""),
            "model": context.get("model", ""),
            "risk": risk,
            "security_decision": security_decision,
            "status": status,
            "error": error,
            "runtime_profile": context.get("runtime_profile", ""),
            "metadata": context.get("metadata", {}),
        }
        self.audit.add(
            task_id=envelope["task_id"], command=command or action, tool=tool,
            arguments=arguments or {}, risk=risk, status=status,
            result=result if result is not None else {},
            elapsed_ms=context.get("elapsed_ms", 0), envelope=envelope)

    def decision(self, tool, risk=None, requires_confirmation=None,
                 authorization_scope="", target_url="", allowed_hosts=(),
                 page_barrier="", audit_context=None):
        risk = risk or tool.risk
        configured = self.rules.get(tool.name, "")
        if configured == "deny":
            result = "deny"
        elif (getattr(tool, "action_class", "") == BROWSER_READ and
                authorization_scope == READ_ONLY_PUBLIC_BROWSER_OBSERVATION):
            if (not is_public_browser_url(target_url) or
                    not browser_host_matches(target_url, allowed_hosts) or
                    str(page_barrier or "NONE") != "NONE"):
                result = "confirm"
            else:
                result = "allow"
        elif authorization_scope == COMPUTER_USE_MISSION_PRE_SAVE and tool.name in {
                "keyboard_hotkey", "keyboard_type", "keyboard_press",
                "ui_type_editor"}:
            result = "allow"
        elif (configured == "confirm" or tool.confirmation or requires_confirmation
                or risk in (Risk.HIGH, Risk.CRITICAL)):
            result = "confirm"
        else:
            result = "allow"
        if audit_context is not None:
            status = {"allow": "ALLOW", "deny": "DENY",
                      "confirm": "APPROVAL_REQUIRED"}[result]
            self._audit_event(
                action="SECURITY_DECISION", status=status, tool=tool.name,
                arguments={}, risk=risk.value, security_decision=status,
                context={**audit_context,
                         "target": audit_context.get("target") or target_url},
                result={"decision": result})
        return result

    def create_confirmation(self, tool, arguments, command, risk=None,
                            audit_context=None):
        token = secrets.token_urlsafe(24)
        stored_arguments = copy.deepcopy(arguments)
        approval_id = "approval:" + str(uuid.uuid4())
        self.pending[token] = {"tool": tool.name, "arguments": stored_arguments, "command": command,
                               "created_at": time.time(), "risk": (risk or tool.risk).value,
                               "approval_id": approval_id,
                               "signature": self._confirmation_signature(
                                   tool.name, stored_arguments, command),
                               "expires": time.time() + self.confirmation_ttl}
        self._audit_event(
            action="APPROVAL_CREATED", status="APPROVAL_CREATED", tool=tool.name,
            arguments=stored_arguments, command=command,
            risk=(risk or tool.risk).value, security_decision="APPROVAL_REQUIRED",
            context=audit_context, approval_id=approval_id,
            result={"approval_scope": "ONCE", "expires_in_seconds": self.confirmation_ttl})
        return token

    @staticmethod
    def _is_sensitive_key(key):
        lowered = str(key or "").casefold().replace("-", "_")
        return any(marker in lowered for marker in (
            "password", "passwd", "secret", "token", "api_key", "apikey",
            "authorization", "cookie", "credential", "private_key",
        ))

    @classmethod
    def _canonicalize(cls, value, key=""):
        if cls._is_sensitive_key(key):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(name): cls._canonicalize(item, name)
                    for name, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
        if isinstance(value, (list, tuple)):
            return [cls._canonicalize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @classmethod
    def _confirmation_signature(cls, tool_name, arguments, command):
        return json.dumps(
            [str(tool_name), cls._canonicalize(arguments), str(command or "")],
            ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        )

    def consume(self, token, *, expected_tool=None, expected_arguments=None,
                expected_command=None, audit_context=None):
        """Consume a valid, bound confirmation exactly once.

        A caller-supplied action/target mismatch is rejected without consuming
        the original approval. Expired, invalid, or tampered tokens are
        removed so they cannot be retried.
        """
        token_key = str(token or "")
        item = self.pending.get(token_key)
        if item is None:
            self._audit_event(action="INVALID_APPROVAL", status="INVALID_APPROVAL",
                              security_decision="DENY", context=audit_context,
                              error="unknown_or_consumed_token")
            return None
        if item.get("expires", 0) < time.time():
            self.pending.pop(token_key, None)
            self._audit_event(
                action="EXPIRED_APPROVAL", status="EXPIRED_APPROVAL",
                tool=item.get("tool", ""), arguments=item.get("arguments", {}),
                command=item.get("command", ""), risk=item.get("risk", ""),
                security_decision="DENY", context=audit_context,
                approval_id=item.get("approval_id", ""), error="approval_expired")
            return None

        expected_signature = self._confirmation_signature(
            item.get("tool", ""), item.get("arguments", {}), item.get("command", ""))
        if not hmac.compare_digest(str(item.get("signature", "")), expected_signature):
            self.pending.pop(token_key, None)
            self._audit_event(
                action="STALE_TARGET", status="STALE_TARGET", tool=item.get("tool", ""),
                arguments=item.get("arguments", {}), command=item.get("command", ""),
                risk=item.get("risk", ""), security_decision="DENY", context=audit_context,
                approval_id=item.get("approval_id", ""), error="approval_signature_mismatch")
            return None
        if expected_tool is not None and str(expected_tool) != str(item.get("tool", "")):
            self._audit_event(
                action="ACTION_MISMATCH", status="MISMATCH", tool=item.get("tool", ""),
                arguments=item.get("arguments", {}), command=item.get("command", ""),
                risk=item.get("risk", ""), security_decision="DENY", context=audit_context,
                approval_id=item.get("approval_id", ""), error="approved_action_mismatch")
            return None
        if (expected_arguments is not None and
                self._canonicalize(expected_arguments) !=
                self._canonicalize(item.get("arguments", {}))):
            self._audit_event(
                action="TARGET_MISMATCH", status="MISMATCH", tool=item.get("tool", ""),
                arguments=item.get("arguments", {}), command=item.get("command", ""),
                risk=item.get("risk", ""), security_decision="DENY", context=audit_context,
                approval_id=item.get("approval_id", ""), error="approved_target_mismatch")
            return None
        if (expected_command is not None and
                str(expected_command) != str(item.get("command", ""))):
            self._audit_event(
                action="ACTION_MISMATCH", status="MISMATCH", tool=item.get("tool", ""),
                arguments=item.get("arguments", {}), command=item.get("command", ""),
                risk=item.get("risk", ""), security_decision="DENY", context=audit_context,
                approval_id=item.get("approval_id", ""), error="approved_command_mismatch")
            return None
        self.pending.pop(token_key, None)
        self._audit_event(
            action="APPROVAL_CONSUMED", status="APPROVAL_CONSUMED", tool=item.get("tool", ""),
            arguments=item.get("arguments", {}), command=item.get("command", ""),
            risk=item.get("risk", ""), security_decision="ALLOW", context=audit_context,
            approval_id=item.get("approval_id", ""), result={"consumed": True})
        return item

    def prune(self):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v["expires"] >= now}
