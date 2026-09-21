import os

import pytest

import config


def test_remote_agent_rejects_plain_http(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://jarvis.example.com")
    monkeypatch.setenv("JARVIS_IDENTITY_FILE", str(tmp_path / "identity.json"))
    with pytest.raises(ValueError):
        config.get_settings()


def test_remote_agent_accepts_https(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SERVER_URL", "https://jarvis.example.com")
    monkeypatch.setenv("JARVIS_IDENTITY_FILE", str(tmp_path / "identity.json"))
    assert config.get_settings().server_url == "https://jarvis.example.com"
