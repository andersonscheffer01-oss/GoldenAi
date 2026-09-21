from pathlib import Path

import pytest

from app.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def production_settings(**overrides):
    values = {
        "JARVIS_ENVIRONMENT": "production",
        "JARVIS_SECRET_KEY": "x" * 48,
        "JARVIS_SERVER_PUBLIC_URL": "https://jarvis.example.com",
        "JARVIS_ALLOWED_ORIGINS": "https://jarvis.example.com",
        "JARVIS_TRUSTED_HOSTS": "jarvis.example.com",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_requires_strong_external_secret():
    with pytest.raises(ValueError):
        production_settings(JARVIS_SECRET_KEY="alterar_esta_chave")


def test_production_requires_https_public_url_and_origins():
    with pytest.raises(ValueError):
        production_settings(JARVIS_SERVER_PUBLIC_URL="http://jarvis.example.com")
    with pytest.raises(ValueError):
        production_settings(JARVIS_ALLOWED_ORIGINS="http://jarvis.example.com")


def test_production_upload_limit_alias_and_hosts():
    settings = production_settings(JARVIS_UPLOAD_MAX_SIZE_MB=10)
    assert settings.upload_max_bytes == 10 * 1024 * 1024
    assert settings.hosts == ["jarvis.example.com"]


def test_deployment_does_not_publish_private_services():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"80:80"' in compose and '"443:443"' in compose
    assert '"8780:8780"' not in compose
    assert '"5432:5432"' not in compose
    assert '"11434:11434"' not in compose
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "postgresql-client" in dockerfile
    assert "COPY deploy ./deploy" in dockerfile


def test_service_worker_never_caches_api_or_uploads():
    worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
    assert "STATIC_ASSETS.includes(url.pathname)" in worker
    assert "/api/" not in worker.split("const STATIC_ASSETS", 1)[1].split("];", 1)[0]
    assert "/uploads/" not in worker.split("const STATIC_ASSETS", 1)[1].split("];", 1)[0]


def test_uploads_are_not_mounted_as_public_static_files():
    main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert 'app.mount("/uploads"' not in main


def test_health_contract_has_no_sensitive_configuration(client=None):
    health_source = (ROOT / "backend" / "app" / "routers" / "health.py").read_text(encoding="utf-8")
    for secret_name in ("secret_key", "database_url", "ollama_base_url", "password", "token"):
        assert secret_name not in health_source
