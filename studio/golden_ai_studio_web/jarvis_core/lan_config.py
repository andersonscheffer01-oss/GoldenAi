"""LAN Configuration V2 — Secure local network access for Jarvis.

ARCHITECTURE:
  LAN mode is OPT-IN. Default remains 127.0.0.1.
  When explicitly enabled, binds to a private network interface.
  SSL mode is OPT-IN via GOLDEN_SSL=1.

SECURITY:
  - Only accepts private/local IP ranges
  - Validates WebSocket origins
  - When SSL enabled, rejects HTTP origins (fail closed)
  - Detects firewall requirements
  - Never exposes to public internet
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.lan_config")

# ─── Private Network Ranges ──────────────────────────────────

_PRIVATE_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # Class A private
    ipaddress.ip_network("172.16.0.0/12"),     # Class B private
    ipaddress.ip_network("192.168.0.0/16"),    # Class C private
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

# ─── Allowed Origins ─────────────────────────────────────────

_ALLOWED_ORIGINS = {
    "http://127.0.0.1",
    "http://localhost",
    "http://[::1]",
    "https://127.0.0.1",
    "https://localhost",
    "https://[::1]",
    # LAN origins added dynamically
}


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/local."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in _PRIVATE_RANGES)
    except ValueError:
        return False


def get_private_interfaces() -> List[Dict[str, Any]]:
    """Get all private network interfaces on this machine."""
    interfaces = []
    try:
        # Use socket to get interface addresses
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM):
            family, type_, proto, canonname, sockaddr = info
            if family in (socket.AF_INET, socket.AF_INET6):
                ip_str = sockaddr[0]
                if is_private_ip(ip_str):
                    interfaces.append({
                        "ip": ip_str,
                        "family": "IPv4" if family == socket.AF_INET else "IPv6",
                        "hostname": hostname,
                    })
    except Exception as e:
        logger.error(f"Failed to get interfaces: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for iface in interfaces:
        key = (iface["ip"], iface["family"])
        if key not in seen:
            seen.add(key)
            unique.append(iface)

    return unique


def get_best_private_ip() -> Optional[str]:
    """Get the best private IP address for LAN binding.

    Prefers 192.168.x.x (most common home LAN).
    Falls back to 10.x.x.x or 172.16.x.x.
    """
    interfaces = get_private_interfaces()
    if not interfaces:
        return None

    # Sort: prefer 192.168, then 10, then 172.16
    def priority(iface: Dict[str, Any]) -> int:
        ip = iface["ip"]
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172."):
            return 2
        return 3

    interfaces.sort(key=priority)
    return interfaces[0]["ip"]


def add_lan_origin(ip: str, ssl_enabled: bool = False) -> None:
    """Add a LAN origin to the allowed list."""
    if ssl_enabled:
        _ALLOWED_ORIGINS.add(f"https://{ip}")
        _ALLOWED_ORIGINS.add(f"https://{ip}:8765")
        _ALLOWED_ORIGINS.add(f"https://{ip}:8766")
        logger.info(f"Added LAN origin (HTTPS): https://{ip}")
    else:
        _ALLOWED_ORIGINS.add(f"http://{ip}")
        _ALLOWED_ORIGINS.add(f"http://{ip}:8765")
        _ALLOWED_ORIGINS.add(f"http://{ip}:8766")
        logger.info(f"Added LAN origin (HTTP): http://{ip}")


def validate_origin(origin: Optional[str], allowed_host: str = "127.0.0.1",
                     ssl_enabled: bool = False) -> bool:
    """Validate a WebSocket origin against allowed origins.

    Returns True if origin is allowed.
    When ssl_enabled=True, HTTP origins are rejected.
    """
    if not origin:
        # No origin header (mobile apps, some clients)
        return True

    # When SSL is enabled, reject HTTP origins explicitly
    if ssl_enabled:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(origin)
            if parsed.scheme == "http":
                # Allow localhost/127.0.0.1 HTTP for dev only
                if parsed.hostname not in ("127.0.0.1", "localhost", "[::1]"):
                    logger.warning(f"HTTP origin rejected (SSL enabled): {origin}")
                    return False
        except Exception:
            pass

    # Check against allowed origins
    for allowed in _ALLOWED_ORIGINS:
        if origin.startswith(allowed):
            return True

    # Check if origin matches the allowed host
    try:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        if parsed.hostname in (allowed_host, "127.0.0.1", "localhost", "[::1]"):
            return True
    except Exception:
        pass

    logger.warning(f"Origin rejected: {origin}")
    return False


def check_firewall_status() -> Dict[str, Any]:
    """Check Windows Firewall status for the gateway ports.

    Returns status information without modifying firewall.
    """
    result = {
        "firewall_detected": False,
        "rule_exists_8765": False,
        "rule_exists_8766": False,
        "action_required": False,
        "command_hint": "",
    }

    try:
        # Check if Windows Firewall is active
        cmd = 'netsh advfirewall show allprofiles state'
        output = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        if "ON" in output.stdout:
            result["firewall_detected"] = True

        # Check for existing rules
        cmd = 'netsh advfirewall firewall show rule name=all dir=in | findstr "8765 8766"'
        output = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        if "8765" in output.stdout:
            result["rule_exists_8765"] = True
        if "8766" in output.stdout:
            result["rule_exists_8766"] = True

        # Determine if action is required
        if result["firewall_detected"] and (not result["rule_exists_8765"] or not result["rule_exists_8766"]):
            result["action_required"] = True
            result["command_hint"] = (
                'netsh advfirewall firewall add rule name="Golden AI Studio" '
                'dir=in action=allow protocol=TCP localport=8765 profile=private\n'
                'netsh advfirewall firewall add rule name="Golden AI Gateway" '
                'dir=in action=allow protocol=TCP localport=8766 profile=private'
            )

    except Exception as e:
        logger.error(f"Firewall check failed: {e}")

    return result


class LanConfig:
    """LAN mode configuration for the gateway.

    Default: disabled (127.0.0.1 only).
    When enabled: binds to private network interface.
    SSL mode: GOLDEN_SSL=1 enables HTTPS/WSS.
    """

    def __init__(self):
        self._enabled = False
        self._ssl_enabled = False
        self._bind_address = "127.0.0.1"
        self._gateway_port = 8766
        self._http_port = 8765

        # Check environment
        self._check_env()

    def _check_env(self) -> None:
        """Check environment variables for LAN and SSL configuration."""
        lan_mode = os.environ.get("GOLDEN_GATEWAY_LAN", "0").strip()
        if lan_mode in ("1", "true", "yes", "on"):
            self.enable()

        ssl_mode = os.environ.get("GOLDEN_SSL", "0").strip()
        if ssl_mode in ("1", "true", "yes", "on"):
            self._ssl_enabled = True

    def enable(self) -> Dict[str, Any]:
        """Enable LAN mode. Returns configuration result."""
        if self._enabled:
            return {"ok": True, "message": "LAN mode already enabled"}

        best_ip = get_best_private_ip()
        if not best_ip:
            return {
                "ok": False,
                "error": "No private network interface found",
                "interfaces": get_private_interfaces(),
            }

        self._bind_address = best_ip
        self._enabled = True

        # Add LAN origins (with SSL awareness)
        add_lan_origin(best_ip, ssl_enabled=self._ssl_enabled)

        # Check firewall
        firewall = check_firewall_status()

        # Build URLs based on SSL mode
        scheme = "https" if self._ssl_enabled else "http"
        ws_scheme = "wss" if self._ssl_enabled else "ws"

        logger.info(f"LAN mode enabled: {best_ip} (SSL={self._ssl_enabled})")
        return {
            "ok": True,
            "bind_address": best_ip,
            "gateway_url": f"{ws_scheme}://{best_ip}:{self._gateway_port}/ws",
            "http_url": f"{scheme}://{best_ip}:{self._http_port}",
            "ssl_enabled": self._ssl_enabled,
            "firewall": firewall,
        }

    def disable(self) -> None:
        """Disable LAN mode (back to localhost only)."""
        self._enabled = False
        self._bind_address = "127.0.0.1"
        logger.info("LAN mode disabled")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def ssl_enabled(self) -> bool:
        return self._ssl_enabled

    @property
    def bind_address(self) -> str:
        return self._bind_address

    def http_bind_addresses(self) -> Tuple[str, ...]:
        """Keep local Desktop access while retaining the explicit LAN listener."""
        hosts = ["127.0.0.1"]
        if self._enabled and self._bind_address not in hosts:
            hosts.append(self._bind_address)
        return tuple(hosts)

    @property
    def gateway_port(self) -> int:
        return self._gateway_port

    @property
    def http_port(self) -> int:
        return self._http_port

    @property
    def ws_scheme(self) -> str:
        return "wss" if self._ssl_enabled else "ws"

    @property
    def http_scheme(self) -> str:
        return "https" if self._ssl_enabled else "http"

    def status(self) -> Dict[str, Any]:
        """Return LAN configuration status."""
        return {
            "lan_enabled": self._enabled,
            "ssl_enabled": self._ssl_enabled,
            "bind_address": self._bind_address,
            "gateway_port": self._gateway_port,
            "http_port": self._http_port,
            "ws_scheme": self.ws_scheme,
            "http_scheme": self.http_scheme,
            "private_interfaces": get_private_interfaces(),
            "firewall": check_firewall_status(),
        }


# ─── Singleton ────────────────────────────────────────────────

_instance: Optional[LanConfig] = None


def get_lan_config() -> LanConfig:
    """Get or create the LAN configuration singleton."""
    global _instance
    if _instance is None:
        _instance = LanConfig()
    return _instance
