from pathlib import Path
import socket

import pytest

from conftest import _loopback_host
from jarvis_core.config import resolve_api_key


def test_network_guard_allows_loopback_and_rejects_public_targets():
    assert _loopback_host("127.0.0.1")
    assert _loopback_host("::1")
    assert _loopback_host("localhost")
    assert not _loopback_host("generativelanguage.googleapis.com")
    assert not _loopback_host("203.0.113.10")


@pytest.mark.network_guard_probe
def test_network_guard_blocks_before_external_connect():
    with pytest.raises(OSError, match="TEST_NETWORK_EGRESS_BLOCKED"):
        socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=0.01)


def test_test_mode_never_reads_real_key_sources(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "real-value-must-not-be-used")
    monkeypatch.delenv("TEST_GEMINI_API_KEY", raising=False)

    def fail_if_real_key_file_is_read():
        raise AssertionError("test mode attempted to inspect provider key file")

    from jarvis_core import config
    monkeypatch.setattr(config, "_load_keys_file", fail_if_real_key_file_is_read)
    assert resolve_api_key("GEMINI_API_KEY", "gemini_api_key") is None


def test_manual_model_benchmark_requires_explicit_live_opt_in():
    source = (Path(__file__).with_name("benchmark_jarvis_models.py")
              .read_text(encoding="utf-8"))
    guard = 'if os.environ.get("GOLDEN_ALLOW_LIVE_MODEL_BENCHMARK") != "1":'
    assert guard in source
    assert source.index(guard) < source.index("_out = run_r2(_tag)")
    assert "resolve_api_key(*identity)" in source
    assert "?key=" not in source
    assert '"x-goog-api-key"' in source
