import copy
import hmac
import json
import ipaddress
import secrets
import time
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
    def __init__(self, rules=None, confirmation_ttl=60):
        self.rules = rules or {}
        self.confirmation_ttl = confirmation_ttl
        self.pending = {}

    def decision(self, tool, risk=None, requires_confirmation=None,
                 authorization_scope="", target_url="", allowed_hosts=(),
                 page_barrier=""):
        risk = risk or tool.risk
        configured = self.rules.get(tool.name, "")
        if configured == "deny":
            return "deny"
        if (getattr(tool, "action_class", "") == BROWSER_READ and
                authorization_scope == READ_ONLY_PUBLIC_BROWSER_OBSERVATION):
            if (not is_public_browser_url(target_url) or
                    not browser_host_matches(target_url, allowed_hosts) or
                    str(page_barrier or "NONE") != "NONE"):
                return "confirm"
            return "allow"
        if authorization_scope == COMPUTER_USE_MISSION_PRE_SAVE and tool.name in {
                "keyboard_hotkey", "keyboard_type", "keyboard_press",
                "ui_type_editor"}:
            return "allow"
        if (configured == "confirm" or tool.confirmation or requires_confirmation
                or risk in (Risk.HIGH, Risk.CRITICAL)):
            return "confirm"
        return "allow"

    def create_confirmation(self, tool, arguments, command, risk=None):
        token = secrets.token_urlsafe(24)
        stored_arguments = copy.deepcopy(arguments)
        self.pending[token] = {"tool": tool.name, "arguments": stored_arguments, "command": command,
                               "created_at": time.time(), "risk": (risk or tool.risk).value,
                               "signature": self._confirmation_signature(
                                   tool.name, stored_arguments, command),
                               "expires": time.time() + self.confirmation_ttl}
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
                expected_command=None):
        """Consume a valid, bound confirmation exactly once.

        A caller-supplied action/target mismatch is rejected without consuming
        the original approval. Expired, invalid, or tampered tokens are
        removed so they cannot be retried.
        """
        token_key = str(token or "")
        item = self.pending.get(token_key)
        if item is None:
            return None
        if item.get("expires", 0) < time.time():
            self.pending.pop(token_key, None)
            return None

        expected_signature = self._confirmation_signature(
            item.get("tool", ""), item.get("arguments", {}), item.get("command", ""))
        if not hmac.compare_digest(str(item.get("signature", "")), expected_signature):
            self.pending.pop(token_key, None)
            return None
        if expected_tool is not None and str(expected_tool) != str(item.get("tool", "")):
            return None
        if (expected_arguments is not None and
                self._canonicalize(expected_arguments) !=
                self._canonicalize(item.get("arguments", {}))):
            return None
        if (expected_command is not None and
                str(expected_command) != str(item.get("command", ""))):
            return None
        self.pending.pop(token_key, None)
        return item

    def prune(self):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v["expires"] >= now}
