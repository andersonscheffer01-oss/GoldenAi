from __future__ import annotations

from datetime import datetime, timezone
import json
import socket

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from ..audit import registrar_auditoria
from ..config import get_settings
from ..database import SessionLocal, check_database
from ..config import ROOT_DIR
from ..network import discover_private_ipv4_addresses


router = APIRouter(prefix="/api", tags=["health"])


def port_online(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


@router.get("/startup-status")
def startup_status():
    state_file = ROOT_DIR / "logs" / "startup-state.json"
    state = {}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8-sig")) if state_file.exists() else {}
    except (OSError, ValueError):
        state = {}
    addresses = discover_private_ipv4_addresses()
    ip = addresses[0] if addresses else None
    return {
        "jarvis": "online",
        "ollama": "online" if port_online(11434) else "offline",
        "port": 8780,
        "local_ip": ip,
        "local_url": "http://127.0.0.1:8780/app",
        "lan_url": f"http://{ip}:8780/app" if ip else None,
        "last_startup": state.get("last_startup"),
        "last_health_check": state.get("last_health_check"),
        "startup_status": state.get("status", "manual"),
        "startup_error": state.get("error") or None,
        "sleep_notice": "O acesso pelo celular para quando o computador estiver desligado, suspenso ou hibernando.",
    }


@router.get("/health")
def health_check():
    settings = get_settings()
    try:
        check_database()
        return {
            "status": "ok",
            "application": "active",
            "service": "golden-jarvis",
            "environment": settings.environment,
            "database": "connected",
            "version": "0.9.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "storage": "available" if (ROOT_DIR / "uploads").exists() else "initializing",
        }
    except Exception as exc:
        try:
            with SessionLocal() as db:
                registrar_auditoria(db, None, "erro_interno", "health", str(exc), None, False)
        except Exception:
            pass
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "application": "degraded",
                "service": "golden-jarvis",
                "environment": settings.environment,
                "database": "unavailable",
                "version": "0.9.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "storage": "unknown",
            },
        )
