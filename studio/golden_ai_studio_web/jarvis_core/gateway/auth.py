"""Gateway Auth V1 — Token-based authentication for WebSocket connections.

Reuses the concept from SecurityManager: simple shared token.
For V1 localhost, token is a pre-shared secret loaded from environment or config.

No OAuth, no cloud auth, no multi-user. Just one token for the local gateway.

Device tokens are also accepted (complementary to shared token).
Device pairing COMPLEMENTS this auth — does NOT replace it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from ..config import resolve_api_key

if TYPE_CHECKING:
    from ..device_pairing import DevicePairingService


# Rate limiting for auth failures
_MAX_AUTH_FAILURES = 10
_AUTH_FAILURE_WINDOW = 300  # 5 minutes


@dataclass
class AuthState:
    """Tracks authentication state for a single connection."""
    authenticated: bool = False
    token_hash: Optional[str] = None
    authenticated_at: Optional[float] = None
    client_info: Optional[dict] = None


@dataclass
class AuthManager:
    """Manages gateway authentication.

    Token resolution order:
    1. Environment variable GOLDEN_GATEWAY_TOKEN
    2. config/api_keys.json["gateway_token"]
    3. Auto-generated token (never logged)

    Security: Token is NEVER logged in full.
    Only the last 4 characters are exposed in debug output.
    """
    _token: Optional[str] = field(default=None, repr=False)
    _failure_counts: dict = field(default_factory=dict)
    _failure_windows: dict = field(default_factory=dict)
    _device_pairing: Optional["DevicePairingService"] = field(default=None, repr=False)

    def _resolve_token(self) -> str:
        if self._token:
            return self._token

        # 1. Environment variable
        token = os.environ.get("GOLDEN_GATEWAY_TOKEN", "")
        if token:
            self._token = token
            return self._token

        # 2. Config file
        try:
            config_token = resolve_api_key("GOLDEN_GATEWAY_TOKEN", "gateway_token")
            if config_token:
                self._token = config_token
                return self._token
        except Exception:
            pass

        # 3. Auto-generate (V1 localhost only)
        self._token = secrets.token_urlsafe(32)
        return self._token

    def get_token(self) -> str:
        """Returns the gateway token (generates if needed)."""
        return self._resolve_token()

    def _hash_token(self, token: str) -> str:
        """Hash token for safe storage in AuthState."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def verify_token(self, token: str) -> bool:
        """Verify a token using constant-time comparison.

        Also enforces rate limiting on failures per source IP.
        """
        if not token:
            return False

        expected = self._resolve_token()
        # Constant-time comparison
        return hmac.compare_digest(token, expected)

    def _is_rate_limited(self, source_ip: str) -> bool:
        now = time.time()
        window_start = self._failure_windows.get(source_ip, 0)
        count = self._failure_counts.get(source_ip, 0)

        if now - window_start > _AUTH_FAILURE_WINDOW:
            # Window expired, reset
            self._failure_counts[source_ip] = 0
            self._failure_windows[source_ip] = now
            return False

        return count >= _MAX_AUTH_FAILURES

    def _record_failure(self, source_ip: str) -> None:
        now = time.time()
        window_start = self._failure_windows.get(source_ip, 0)

        if now - window_start > _AUTH_FAILURE_WINDOW:
            self._failure_counts[source_ip] = 1
            self._failure_windows[source_ip] = now
        else:
            self._failure_counts[source_ip] = self._failure_counts.get(source_ip, 0) + 1

    def get_failure_count(self, source_ip: str) -> int:
        return self._failure_counts.get(source_ip, 0)

    def set_device_pairing_service(self, service: "DevicePairingService") -> None:
        """Set the device pairing service for device token authentication."""
        self._device_pairing = service

    def authenticate(self, token: str, source_ip: str = "unknown") -> AuthState:
        """Attempt authentication. Returns AuthState.

        Tries shared token first, then device token.
        Rate-limits failures per source_ip.
        """
        now = time.time()

        # Check rate limit
        if self._is_rate_limited(source_ip):
            return AuthState(authenticated=False)

        # 1. Try shared token
        if self.verify_token(token):
            self._failure_counts.pop(source_ip, None)
            self._failure_windows.pop(source_ip, None)
            return AuthState(
                authenticated=True,
                token_hash=self._hash_token(token),
                authenticated_at=now,
            )

        # 2. Try device token
        if self._device_pairing and token:
            device = self._device_pairing.verify_device_token(token)
            if device:
                self._failure_counts.pop(source_ip, None)
                self._failure_windows.pop(source_ip, None)
                return AuthState(
                    authenticated=True,
                    token_hash=self._hash_token(token),
                    authenticated_at=now,
                    client_info={
                        "type": "device",
                        "device_id": device.device_id,
                        "device_name": device.device_name,
                    },
                )

        # Record failure
        self._record_failure(source_ip)
        return AuthState(authenticated=False)
