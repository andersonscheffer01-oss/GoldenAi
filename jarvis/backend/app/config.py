from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.network import discover_private_ipv4_addresses


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = Field(default="Golden Jarvis", alias="JARVIS_APP_NAME")
    environment: str = Field(default="development", alias="JARVIS_ENVIRONMENT")
    host: str = Field(default="0.0.0.0", alias="JARVIS_HOST")
    port: int = Field(default=8780, alias="JARVIS_PORT")
    database_url: str = Field(default="sqlite:///./data/jarvis_runtime.db", alias="JARVIS_DATABASE_URL")
    secret_key: str = Field(default="alterar_esta_chave_local_com_mais_de_32_caracteres", alias="JARVIS_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="JARVIS_ACCESS_TOKEN_EXPIRE_MINUTES")
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, alias="JARVIS_UPLOAD_MAX_BYTES")
    upload_max_size_mb: int | None = Field(default=None, alias="JARVIS_UPLOAD_MAX_SIZE_MB")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", alias="JARVIS_OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5vl:7b", alias="JARVIS_OLLAMA_MODEL")
    ollama_timeout_seconds: float = Field(default=120, alias="JARVIS_OLLAMA_TIMEOUT_SECONDS")
    chat_max_message_length: int = Field(default=4000, alias="JARVIS_CHAT_MAX_MESSAGE_LENGTH")
    chat_history_limit: int = Field(default=20, alias="JARVIS_CHAT_HISTORY_LIMIT")
    receipt_max_pages: int = Field(default=5, alias="JARVIS_RECEIPT_MAX_PAGES")
    receipt_max_image_width: int = Field(default=1800, alias="JARVIS_RECEIPT_MAX_IMAGE_WIDTH")
    receipt_max_image_height: int = Field(default=2400, alias="JARVIS_RECEIPT_MAX_IMAGE_HEIGHT")
    alert_check_interval_seconds: int = Field(default=300, alias="JARVIS_ALERT_CHECK_INTERVAL_SECONDS")
    alert_default_time: str = Field(default="09:00", alias="JARVIS_ALERT_DEFAULT_TIME")
    alerts_enabled: bool = Field(default=True, alias="JARVIS_ALERTS_ENABLED")
    pending_action_expire_minutes: int = Field(default=15, alias="JARVIS_PENDING_ACTION_EXPIRE_MINUTES")
    push_enabled: bool = Field(default=False, alias="JARVIS_PUSH_ENABLED")
    server_public_url: str = Field(default="http://127.0.0.1:8780", alias="JARVIS_SERVER_PUBLIC_URL")
    trusted_hosts: str = Field(default="127.0.0.1,localhost,testserver", alias="JARVIS_TRUSTED_HOSTS")
    local_ips: str = Field(default="", alias="JARVIS_LOCAL_IPS")
    log_level: str = Field(default="INFO", alias="JARVIS_LOG_LEVEL")
    log_max_bytes: int = Field(default=10 * 1024 * 1024, alias="JARVIS_LOG_MAX_BYTES")
    log_backup_count: int = Field(default=10, alias="JARVIS_LOG_BACKUP_COUNT")
    allowed_origins: str = Field(
        default="http://127.0.0.1:8780,http://localhost:8780",
        alias="JARVIS_ALLOWED_ORIGINS",
    )
    open_finance_provider: str = Field(default="pluggy", alias="JARVIS_OPEN_FINANCE_PROVIDER")
    pluggy_client_id: str = Field(default="", alias="PLUGGY_CLIENT_ID")
    pluggy_client_secret: str = Field(default="", alias="PLUGGY_CLIENT_SECRET")

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def validate_production(self):
        insecure_keys = {
            "alterar_esta_chave",
            "alterar_esta_chave_local_com_mais_de_32_caracteres",
            "",
        }
        if self.upload_max_size_mb is not None:
            self.upload_max_bytes = self.upload_max_size_mb * 1024 * 1024
        if self.environment == "production":
            if self.secret_key in insecure_keys or len(self.secret_key) < 32:
                raise ValueError("JARVIS_SECRET_KEY forte e externa e obrigatoria em producao.")
            if not self.server_public_url.startswith("https://"):
                raise ValueError("JARVIS_SERVER_PUBLIC_URL deve usar HTTPS em producao.")
            if any(not origin.startswith("https://") for origin in self.origins):
                raise ValueError("JARVIS_ALLOWED_ORIGINS deve conter apenas HTTPS em producao.")
        if self.open_finance_provider != "pluggy":
            raise ValueError("Somente o fluxo Meu Pluggy esta habilitado para Open Finance.")
        return self

    @property
    def pluggy_configured(self) -> bool:
        return bool(self.pluggy_client_id.strip() and self.pluggy_client_secret.strip())

    @property
    def pluggy_base_url(self) -> str:
        return "https://api.pluggy.ai"

    @property
    def origins(self) -> list[str]:
        origins = [item.strip() for item in self.allowed_origins.split(",") if item.strip()]
        if self.environment != "production":
            origins.extend(f"http://{ip}:{self.port}" for ip in self.local_ipv4_addresses)
        return list(dict.fromkeys(origins))

    @property
    def hosts(self) -> list[str]:
        hosts = [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]
        if self.environment != "production":
            hosts.extend(self.local_ipv4_addresses)
        return list(dict.fromkeys(hosts))

    @property
    def local_ipv4_addresses(self) -> list[str]:
        configured = [item.strip() for item in self.local_ips.split(",") if item.strip()]
        discovered = discover_private_ipv4_addresses() if self.environment != "production" else []
        return list(dict.fromkeys([*configured, *discovered]))

    @property
    def safe_ollama_url(self) -> str:
        """Keep the internal provider URL server-side and normalize its path."""
        return self.ollama_base_url.rstrip("/")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url.startswith("sqlite:///./"):
            relative = self.database_url.replace("sqlite:///./", "", 1)
            return "sqlite:///" + str((ROOT_DIR / relative).resolve()).replace("\\", "/")
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
