import json
import ipaddress
import secrets
import time
from urllib.parse import urlparse

from .models import BROWSER_READ, Risk


READ_ONLY_PUBLIC_BROWSER_OBSERVATION = "READ_ONLY_PUBLIC_BROWSER_OBSERVATION"


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
        if (configured == "confirm" or tool.confirmation or requires_confirmation
                or risk in (Risk.HIGH, Risk.CRITICAL)):
            return "confirm"
        return "allow"

    def create_confirmation(self, tool, arguments, command, risk=None):
        token = secrets.token_urlsafe(24)
        self.pending[token] = {"tool": tool.name, "arguments": arguments, "command": command,
                               "created_at": time.time(), "risk": (risk or tool.risk).value,
                               "signature": json.dumps([tool.name, arguments], sort_keys=True),
                               "expires": time.time() + self.confirmation_ttl}
        return token

    def consume(self, token):
        item = self.pending.pop(str(token or ""), None)
        return item if item and item["expires"] >= time.time() else None

    def prune(self):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v["expires"] >= now}
