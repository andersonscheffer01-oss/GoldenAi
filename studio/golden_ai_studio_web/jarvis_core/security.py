import json
import secrets
import time

from .models import Risk

class SecurityManager:
    def __init__(self, rules=None, confirmation_ttl=60):
        self.rules = rules or {}
        self.confirmation_ttl = confirmation_ttl
        self.pending = {}

    def decision(self, tool, risk=None, requires_confirmation=None):
        risk = risk or tool.risk
        configured = self.rules.get(tool.name, "")
        if configured == "deny":
            return "deny"
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
