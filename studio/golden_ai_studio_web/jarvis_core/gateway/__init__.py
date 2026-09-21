"""Jarvis Gateway V1 — Minimal secure WebSocket transport.

Architecture:
  Client → Gateway → Authentication → Session → JarvisService

Gateway is TRANSPORT ONLY — never executes tools directly.
"""

from .protocol import GatewayMessage, MessageType, PROTOCOL_VERSION
from .auth import AuthManager, AuthState
from .sessions import SessionManager, Session
from .gateway import Gateway, run_gateway

__all__ = [
    "Gateway",
    "GatewayMessage",
    "MessageType",
    "AuthManager",
    "AuthState",
    "SessionManager",
    "Session",
    "PROTOCOL_VERSION",
    "run_gateway",
]
