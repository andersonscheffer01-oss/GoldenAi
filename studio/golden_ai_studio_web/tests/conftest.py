import ipaddress
import errno
import socket

import pytest


def pytest_configure(config):
    import os

    os.environ["JARVIS_TEST_MODE"] = "1"
    config.addinivalue_line(
        "markers", "network_guard_probe: asserts that the test egress guard blocks a target"
    )


def pytest_collection_modifyitems(config, items):
    import os

    if os.environ.get("GOLDEN_ALLOW_LIVE_TESTS") == "1":
        return
    skip_live_browser = pytest.mark.skip(
        reason="real-browser integration requires explicit GOLDEN_ALLOW_LIVE_TESTS=1"
    )
    for item in items:
        if "test_browser_real.py" in item.nodeid:
            item.add_marker(skip_live_browser)


def _loopback_host(host):
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="ignore")
    if isinstance(host, str) and host.casefold().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def _host_port(address):
    if isinstance(address, tuple) and address:
        return str(address[0])[:80], address[1] if len(address) > 1 else None
    return "non-internet-socket", None


@pytest.fixture(autouse=True)
def deny_non_loopback_network(monkeypatch, request):
    attempts = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_create_connection = socket.create_connection

    def record_and_reject(operation, address):
        host, port = _host_port(address)
        attempts.append(f"{operation}:{host}:{port}")
        raise OSError("TEST_NETWORK_EGRESS_BLOCKED")

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _loopback_host(host):
            return record_and_reject("connect", address)
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _loopback_host(host):
            try:
                record_and_reject("connect_ex", address)
            except OSError:
                return errno.EACCES
        return original_connect_ex(sock, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _loopback_host(host):
            return record_and_reject("dns", (host, None))
        return original_getaddrinfo(host, *args, **kwargs)

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _loopback_host(host):
            return record_and_reject("create_connection", address)
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    yield
    if attempts and request.node.get_closest_marker("network_guard_probe") is None:
        pytest.fail("External network attempt blocked in test: " + ", ".join(attempts))
