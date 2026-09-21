from __future__ import annotations

import ipaddress
import socket


def is_private_ipv4(value: str) -> bool:
    """Return whether value is an RFC1918 IPv4 address usable on the LAN."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and address.is_private and not address.is_loopback


def discover_private_ipv4_addresses() -> list[str]:
    """Discover active private IPv4 addresses without exposing public interfaces."""
    candidates: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.add(item[4][0])
    except OSError:
        pass

    route_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        route_socket.connect(("10.255.255.255", 1))
        candidates.add(route_socket.getsockname()[0])
    except OSError:
        pass
    finally:
        route_socket.close()

    return sorted(value for value in candidates if is_private_ipv4(value))
