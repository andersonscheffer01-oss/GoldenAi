"""Authenticated inbound HTTP perimeter for the canonical Jarvis server.

Identity is deliberately shared with the Gateway AuthManager.  This module
only authenticates the caller; SecurityManager remains responsible for
authorization and approvals for side effects.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

from .gateway.auth import AuthManager


_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


@dataclass(frozen=True)
class HttpAuthDecision:
    allowed: bool
    status_code: int
    code: str
    reason: str
    context: dict[str, Any] = field(default_factory=dict)


class HttpPerimeter:
    """Classify and authenticate HTTP requests before route dispatch."""

    PUBLIC_LOCAL = frozenset({("GET", "/health")})
    READ_ONLY_DESKTOP_ROUTES = frozenset({
        ("POST", "/api/jarvis/golden/symbol-discovery"),
        ("POST", "/api/jarvis/golden/market-data"),
        ("POST", "/api/jarvis/golden/market-live"),
        ("POST", "/api/jarvis/golden/market-intelligence"),
        ("POST", "/api/jarvis/golden/panel-analysis"),
        # Authenticated Desktop-only scan snapshots, including a bounded local DB save.
        # The ToolRegistry separately classifies SAVE as LOCAL_MUTATION.
        ("POST", "/api/jarvis/golden/trend-scan"),
        ("GET", "/api/status"),
        ("GET", "/api/capabilities"),
        ("GET", "/api/security/status"),
        ("GET", "/api/desktop/status"),
        ("GET", "/api/mt5/status"),
        ("GET", "/api/jarvis/providers/status"),
        ("GET", "/api/jarvis/brain/status"),
        ("GET", "/api/jarvis/memory/status"),
        ("GET", "/api/jarvis/readiness"),
        ("GET", "/api/jarvis/orchestrator/status"),
        ("GET", "/api/jarvis/skills/status"),
        ("GET", "/api/jarvis/voice/status"),
        ("GET", "/api/jarvis/voice-service/status"),
    })
    HIGH_RISK_EXACT = frozenset({
        "/api/chat", "/api/jarvis/chat", "/api/agent", "/api/audio",
        "/api/video", "/api/document",
        "/api/models/key", "/api/plugins/toggle", "/api/clear_history",
        "/api/security/mode", "/api/security/approve", "/api/security/deny",
        "/api/security/lockdown", "/api/desktop/action", "/api/desktop/confirm",
        "/api/desktop/speech", "/api/jarvis/brain/execute",
        "/api/jarvis/memory/remember", "/api/jarvis/tasks/cancel",
        "/api/jarvis/voice/command", "/api/jarvis/voice-service/start",
        "/api/jarvis/voice-service/stop", "/api/jarvis/voice-service/speak",
        "/api/mt5/compile", "/api/mt5/backtest", "/api/mt5/real_backtest",
        "/api/mt5/import_history", "/api/mt5/auto_trade",
        "/api/mt5/close_position", "/api/position/start", "/api/position/stop",
        "/api/position/config", "/api/strategy_manager/toggle",
        "/api/strategy_manager/toggle_mode", "/api/strategy_manager/preset",
        "/api/strategy_manager/auto_rank", "/api/monitor/toggle",
        "/api/risk/config", "/api/validation/real", "/api/validation/all_real",
        "/api/rag/index", "/api/filesystem", "/api/system",
    })
    HIGH_RISK_PREFIXES = (
        "/stream/", "/api/stream", "/api/strategy_", "/api/portfolio_",
        "/api/chart_strategy_test", "/api/mt5/", "/api/position/",
        "/api/strategy_manager/", "/api/validation/", "/api/scanner/",
        "/api/risk/", "/api/jarvis/voice-service/",
    )

    MARKET_READ_ROUTES = frozenset({
        ("POST", "/api/jarvis/golden/symbol-discovery"),
        ("POST", "/api/jarvis/golden/market-data"),
        ("POST", "/api/jarvis/golden/market-live"),
        ("POST", "/api/jarvis/golden/market-intelligence"),
        ("POST", "/api/jarvis/golden/panel-analysis"),
    })

    def __init__(self, auth_manager: Optional[AuthManager] = None,
                 audit_log: Any = None, lan_config: Any = None,
                 runtime_profile_provider=None) -> None:
        self.auth_manager = auth_manager or AuthManager()
        self.audit_log = audit_log
        self.lan_config = lan_config
        self.runtime_profile_provider = runtime_profile_provider

    @staticmethod
    def path_only(path: str) -> str:
        return urlsplit(str(path or "")).path or "/"

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return str(value or "")
        return ""

    @staticmethod
    def _safe_id(value: str, fallback: str) -> str:
        value = str(value or "").strip()
        return value if _ID_RE.fullmatch(value) else fallback

    @staticmethod
    def _is_loopback(source_ip: str) -> bool:
        return str(source_ip or "").strip() in {"127.0.0.1", "::1", "[::1]", "unknown"}

    @staticmethod
    def _is_read_only_desktop_route(method: str, path: str) -> bool:
        return (str(method or "GET").upper(), HttpPerimeter.path_only(path)) in (
            HttpPerimeter.READ_ONLY_DESKTOP_ROUTES
        )

    def _read_only_route_enabled(self, method: str, path: str) -> bool:
        if self.runtime_profile_provider is None:
            return False
        try:
            profile = self.runtime_profile_provider()
        except Exception:
            return False
        if profile is None or not getattr(profile, "web_enabled", False):
            return False
        if (method, path) in self.MARKET_READ_ROUTES:
            market_enabled = bool(
                getattr(profile, "market_data_read_enabled", False)
                and getattr(profile, "mt5_market_data_read_enabled", False))
            if path == "/api/jarvis/golden/panel-analysis":
                return bool(market_enabled and getattr(profile, "ai_enabled", False)
                            and getattr(profile, "audit_enabled", False))
            return market_enabled
        return bool(getattr(profile, "security_enabled", False))

    def set_lan_config(self, lan_config: Any) -> None:
        self.lan_config = lan_config

    def route_class(self, method: str, path: str) -> str:
        method = str(method or "GET").upper()
        path = self.path_only(path)
        if method == "OPTIONS":
            return "PUBLIC_LOCAL"
        if (method, path) in self.PUBLIC_LOCAL:
            return "PUBLIC_LOCAL"
        if path.startswith("/api/") or path.startswith("/stream/"):
            if path in self.HIGH_RISK_EXACT or any(
                    path.startswith(prefix) for prefix in self.HIGH_RISK_PREFIXES):
                return "AUTHENTICATED_AND_AUTHORIZED"
            return "AUTHENTICATED"
        return "PUBLIC_LOCAL"

    def _audit(self, context: dict[str, Any], status: str,
               status_code: int, reason: str) -> None:
        if self.audit_log is None:
            return
        try:
            self.audit_log.add(
                task_id=context.get("request_id", "http"),
                command="http_perimeter",
                tool="http_auth",
                risk="HIGH" if context.get("route_class") == "AUTHENTICATED_AND_AUTHORIZED" else "LOW",
                status=status,
                result={"status_code": status_code, "reason": reason,
                        "route": context.get("route", "")},
                envelope={**context, "action": "HTTP_%s" % status,
                          "status": status, "error": reason if status != "AUTH_SUCCESS" else ""},
            )
        except Exception:
            # Authentication must remain fail-closed if audit storage is unavailable.
            return

    def authorize(self, method: str, path: str,
                  headers: Mapping[str, str], source_ip: str = "unknown") -> HttpAuthDecision:
        method = str(method or "GET").upper()
        path = self.path_only(path)
        route_class = self.route_class(method, path)
        request_id = self._safe_id(self._header(headers, "X-Request-ID"), uuid.uuid4().hex)
        correlation_id = self._safe_id(
            self._header(headers, "X-Correlation-ID"), request_id)
        context = {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "session_id": "",
            "surface": "http",
            "operation": "%s %s" % (method, path),
            "route": path,
            "route_class": route_class,
            "actor_id": "anonymous",
            "runtime_profile": "",
            "metadata": {"source_ip": str(source_ip or "unknown")[:80]},
        }

        if method == "OPTIONS":
            return HttpAuthDecision(True, 204, "OPTIONS_ALLOWED", "preflight", context)
        if route_class == "PUBLIC_LOCAL" and (method, path) in self.PUBLIC_LOCAL:
            if not self._is_loopback(source_ip):
                self._audit(context, "PUBLIC_LOCAL_DENIED", 403, "local route from non-loopback")
                return HttpAuthDecision(False, 403, "LOCAL_ONLY", "Local route required", context)
            context["actor_id"] = "local_public"
            self._audit(context, "AUTH_PUBLIC_LOCAL", 200, "allowlisted local route")
            return HttpAuthDecision(True, 200, "PUBLIC_LOCAL", "allowlisted", context)
        if route_class == "PUBLIC_LOCAL":
            return HttpAuthDecision(True, 200, "STATIC_ALLOWED", "static asset", context)

        raw = self._header(headers, "Authorization")
        if not raw:
            self._audit(context, "AUTH_MISSING", 401, "authorization required")
            return HttpAuthDecision(False, 401, "AUTH_MISSING", "Authentication required", context)
        if not raw.startswith("Bearer ") or raw[7:].strip() != raw[7:] or not raw[7:]:
            self._audit(context, "AUTH_MALFORMED", 401, "malformed bearer authorization")
            return HttpAuthDecision(False, 401, "AUTH_MALFORMED", "Malformed authorization", context)

        token = raw[7:]
        read_only_desktop = self._is_read_only_desktop_route(method, path)
        if read_only_desktop and not self._read_only_route_enabled(method, path):
            self._audit(context, "READ_ONLY_DESKTOP_DENIED", 403,
                        "read-only route disabled by runtime profile")
            return HttpAuthDecision(False, 403, "READ_ONLY_DISABLED_BY_PROFILE",
                                    "Read-only route disabled by runtime profile", context)
        if read_only_desktop and not self._is_loopback(source_ip):
            self._audit(context, "READ_ONLY_DESKTOP_DENIED", 403,
                        "loopback Desktop identity required")
            return HttpAuthDecision(False, 403, "LOCAL_DESKTOP_REQUIRED",
                                    "Loopback Desktop identity required", context)

        state = self.auth_manager.authenticate(
            token,
            source_ip=str(source_ip or "unknown"),
            update_device_last_seen=not read_only_desktop,
        )
        if not state.authenticated:
            self._audit(context, "AUTH_FAILURE", 401, "invalid or expired authorization")
            return HttpAuthDecision(False, 401, "AUTH_INVALID", "Authentication failed", context)

        if read_only_desktop and (
                not state.client_info or
                str(state.client_info.get("device_type", "")).casefold() != "desktop"):
            self._audit(context, "READ_ONLY_DESKTOP_DENIED", 403,
                        "existing Desktop device identity required")
            return HttpAuthDecision(False, 403, "DESKTOP_IDENTITY_REQUIRED",
                                    "Existing Desktop identity required", context)

        context["actor_id"] = "authenticated_client"
        if state.client_info and state.client_info.get("device_id"):
            context["actor_id"] = "device:%s" % self._safe_id(
                state.client_info.get("device_id"), "authenticated")
        self._audit(context, "AUTH_SUCCESS", 200, "authenticated")
        return HttpAuthDecision(True, 200, "AUTH_SUCCESS", "authenticated", context)

    def cors_headers(self, origin: str) -> dict[str, str]:
        if not origin:
            return {}
        try:
            from .gateway.cors import build_cors_headers
            return build_cors_headers(
                origin, self.lan_config,
                allowed_methods=["GET", "POST", "OPTIONS"],
                allowed_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Correlation-ID"],
            )
        except Exception:
            return {}

    def preflight(self, headers: Mapping[str, str]) -> HttpAuthDecision:
        origin = self._header(headers, "Origin")
        if origin and not self.cors_headers(origin):
            return HttpAuthDecision(False, 403, "CORS_ORIGIN_DENIED", "Origin not allowed", {})
        return HttpAuthDecision(True, 204, "OPTIONS_ALLOWED", "preflight", {})
