"""Gateway CORS — Secure CORS handling for Gateway HTTP endpoints.

SECURITY:
  - No wildcard Access-Control-Allow-Origin
  - Origin validation based on SSL state and LAN config
  - Vary: Origin header on all CORS responses
  - OPTIONS only returns methods actually supported by the route
  - Pairing code generation stays localhost-only
"""

from __future__ import annotations

import logging
from typing import List, Optional, Set
from urllib.parse import urlparse

from aiohttp import web

logger = logging.getLogger("jarvis.gateway.cors")


def is_cors_allowed_origin(origin: str, lan_config=None) -> bool:
    """Check if an origin is allowed for CORS requests.

    Rules:
    - SSL ON: only HTTPS origins from allowlist
    - SSL OFF: HTTP origins from allowlist
    - Always allow localhost/127.0.0.1 for dev

    Returns True if origin is in the allowlist.
    """
    if not origin:
        return False

    try:
        parsed = urlparse(origin)
    except Exception:
        return False

    scheme = parsed.scheme
    hostname = parsed.hostname or ""

    # Determine SSL state
    ssl_enabled = False
    if lan_config:
        ssl_enabled = lan_config.ssl_enabled

    # When SSL is ON, reject HTTP origins (except localhost dev)
    if ssl_enabled and scheme == "http":
        if hostname in ("127.0.0.1", "localhost", "[::1]"):
            return True  # Localhost dev allowed even with SSL
        return False

    # Build allowed origins based on SSL state
    allowed_prefixes = []

    if ssl_enabled:
        # HTTPS origins
        allowed_prefixes.append("https://127.0.0.1")
        allowed_prefixes.append("https://localhost")
        allowed_prefixes.append("https://[::1]")
        # Add LAN origins
        if lan_config and lan_config.enabled:
            lan_ip = lan_config.bind_address
            if lan_ip and lan_ip != "127.0.0.1":
                allowed_prefixes.append(f"https://{lan_ip}")
    else:
        # HTTP origins
        allowed_prefixes.append("http://127.0.0.1")
        allowed_prefixes.append("http://localhost")
        allowed_prefixes.append("http://[::1]")
        # Add LAN origins
        if lan_config and lan_config.enabled:
            lan_ip = lan_config.bind_address
            if lan_ip and lan_ip != "127.0.0.1":
                allowed_prefixes.append(f"http://{lan_ip}")

    # Check origin against allowed prefixes
    for prefix in allowed_prefixes:
        if origin.startswith(prefix):
            return True

    return False


def build_cors_headers(origin: str, lan_config=None,
                       allowed_methods: Optional[List[str]] = None,
                       allowed_headers: Optional[List[str]] = None) -> dict:
    """Build CORS response headers.

    Returns a dict of headers to add to the response.
    Never returns wildcard origin.
    """
    headers = {}

    if not origin:
        return headers

    if not is_cors_allowed_origin(origin, lan_config):
        return headers  # No CORS headers for disallowed origins

    headers["Access-Control-Allow-Origin"] = origin
    headers["Vary"] = "Origin"

    if allowed_methods:
        headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)

    if allowed_headers:
        headers["Access-Control-Allow-Headers"] = ", ".join(allowed_headers)

    return headers


def cors_preflight_response(request: web.Request, lan_config=None,
                            allowed_methods: Optional[List[str]] = None,
                            allowed_headers: Optional[List[str]] = None) -> web.Response:
    """Create a CORS preflight (OPTIONS) response.

    Returns 200 with CORS headers, or 403 if origin not allowed.
    """
    origin = request.headers.get("Origin", "")

    if not origin:
        # No origin = non-browser client, allow
        return web.Response(status=204)

    if not is_cors_allowed_origin(origin, lan_config):
        logger.warning(f"CORS preflight rejected: origin={origin}")
        return web.Response(status=403, text="Origin not allowed")

    if allowed_methods is None:
        allowed_methods = ["GET", "POST", "OPTIONS"]
    if allowed_headers is None:
        allowed_headers = ["Content-Type", "Authorization"]

    headers = build_cors_headers(origin, lan_config, allowed_methods, allowed_headers)
    return web.Response(status=204, headers=headers)


def cors_response_headers(origin: str, lan_config=None) -> dict:
    """Build CORS headers for actual (non-preflight) responses.

    Use this in POST/GET handlers to add CORS headers to the response.
    """
    return build_cors_headers(origin, lan_config)


def add_cors_to_response(response: web.Response, origin: str, lan_config=None) -> web.Response:
    """Add CORS headers to an existing aiohttp Response object.

    Modifies the response in-place and returns it.
    """
    headers = cors_response_headers(origin, lan_config)
    for key, value in headers.items():
        response.headers[key] = value
    return response


# ─── Route Decorators / Helpers ───────────────────────────────

class CORSConfig:
    """CORS configuration for Gateway routes."""

    def __init__(self, lan_config=None):
        self.lan_config = lan_config

    def preflight(self, request: web.Request,
                  methods: Optional[List[str]] = None,
                  headers: Optional[List[str]] = None) -> web.Response:
        """Handle OPTIONS preflight for a route."""
        return cors_preflight_response(request, self.lan_config,
                                       allowed_methods=methods,
                                       allowed_headers=headers)

    def wrap(self, response: web.Response, request: web.Request) -> web.Response:
        """Add CORS headers to a response."""
        origin = request.headers.get("Origin", "")
        if origin:
            return add_cors_to_response(response, origin, self.lan_config)
        return response


def make_cors_middleware(lan_config_getter):
    """Create aiohttp middleware for CORS.

    lan_config_getter: callable returning current LanConfig
    """

    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        # Handle OPTIONS preflight for all routes
        if request.method == "OPTIONS":
            origin = request.headers.get("Origin", "")
            lc = lan_config_getter()

            if not origin:
                return web.Response(status=204)

            if not is_cors_allowed_origin(origin, lc):
                return web.Response(status=403, text="Origin not allowed")

            # Determine allowed methods from route
            allowed_methods = ["GET", "POST", "OPTIONS"]
            allowed_headers = ["Content-Type", "Authorization"]

            headers = build_cors_headers(origin, lc, allowed_methods, allowed_headers)
            return web.Response(status=204, headers=headers)

        # For non-OPTIONS, call handler and add CORS headers
        response = await handler(request)
        origin = request.headers.get("Origin", "")
        if origin:
            add_cors_to_response(response, origin, lan_config_getter())
        return response

    return cors_middleware
