from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
AGENT_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class AgentSettings:
    server_url: str
    device_token: str
    device_name: str
    agent_version: str
    heartbeat_seconds: int
    allowed_programs_file: Path
    identity_file: Path
    log_file: Path


def get_settings() -> AgentSettings:
    _load_env_file(ROOT_DIR / ".env")
    _load_env_file(AGENT_DIR / ".env")
    server_url = os.getenv("JARVIS_SERVER_URL", "http://127.0.0.1:8780").rstrip("/")
    is_local = server_url.startswith(("http://127.0.0.1", "http://localhost", "https://127.0.0.1", "https://localhost"))
    if not is_local and not server_url.startswith("https://"):
        raise ValueError("JARVIS_SERVER_URL remoto deve usar HTTPS com certificado valido.")
    return AgentSettings(
        server_url=server_url,
        device_token=os.getenv("JARVIS_DEVICE_TOKEN", ""),
        device_name=os.getenv("JARVIS_DEVICE_NAME", "PC Anderson"),
        agent_version=os.getenv("JARVIS_AGENT_VERSION", "0.1.0"),
        heartbeat_seconds=max(5, int(os.getenv("JARVIS_HEARTBEAT_SECONDS", "30"))),
        allowed_programs_file=Path(os.getenv("JARVIS_ALLOWED_PROGRAMS_FILE", str(AGENT_DIR / "allowed_programs.json"))),
        identity_file=Path(os.getenv("JARVIS_IDENTITY_FILE", str(AGENT_DIR / "device_identity.json"))),
        log_file=Path(os.getenv("JARVIS_PC_AGENT_LOG", str(ROOT_DIR / "logs" / "pc_agent.log"))),
    )
