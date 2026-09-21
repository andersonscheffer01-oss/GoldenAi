from pathlib import Path

from app.config import Settings
from app.network import is_private_ipv4


ROOT = Path(__file__).resolve().parents[2]


def test_development_listens_on_lan_and_trusts_configured_private_ip():
    settings = Settings(
        JARVIS_ENVIRONMENT="development",
        JARVIS_LOCAL_IPS="192.168.1.100",
    )
    assert settings.host == "0.0.0.0"
    assert "192.168.1.100" in settings.hosts
    assert "http://192.168.1.100:8780" in settings.origins
    assert "*" not in settings.hosts
    assert "*" not in settings.origins


def test_production_does_not_automatically_trust_local_ips():
    settings = Settings(
        JARVIS_ENVIRONMENT="production",
        JARVIS_SECRET_KEY="x" * 48,
        JARVIS_SERVER_PUBLIC_URL="https://jarvis.example.com",
        JARVIS_ALLOWED_ORIGINS="https://jarvis.example.com",
        JARVIS_TRUSTED_HOSTS="jarvis.example.com",
        JARVIS_LOCAL_IPS="192.168.1.100",
    )
    assert settings.hosts == ["jarvis.example.com"]
    assert settings.origins == ["https://jarvis.example.com"]


def test_private_ipv4_filter_rejects_public_loopback_and_ipv6():
    assert is_private_ipv4("192.168.1.100")
    assert is_private_ipv4("10.0.0.8")
    assert is_private_ipv4("172.16.4.2")
    assert not is_private_ipv4("127.0.0.1")
    assert not is_private_ipv4("8.8.8.8")
    assert not is_private_ipv4("::1")


def test_frontend_uses_relative_routes_and_pwa_scope():
    frontend = ROOT / "frontend"
    scripts = "\n".join(path.read_text(encoding="utf-8") for path in (frontend / "assets" / "js").glob("*.js"))
    manifest = (frontend / "manifest.json").read_text(encoding="utf-8")
    worker = (frontend / "sw.js").read_text(encoding="utf-8")
    assert "http://127.0.0.1" not in scripts
    assert "http://localhost" not in scripts
    assert '"start_url": "./app"' in manifest
    assert '"scope": "./"' in manifest
    assert "127.0.0.1" not in worker
    assert "localhost" not in worker


def test_firewall_is_documented_but_not_changed_by_startup():
    batch = (ROOT / "run_jarvis.bat").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "New-NetFirewallRule" not in batch
    assert 'Golden Jarvis 8780 Local Network' in readme
    assert "-Profile Private" in readme
