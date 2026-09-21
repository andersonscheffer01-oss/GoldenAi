from __future__ import annotations

import argparse
import json
import platform
import time
from datetime import datetime, timezone

from client import JarvisAgentClient
from command_executor import execute_command
from config import get_settings
from device_identity import load_identity
from health_checks import system_status
from logger import get_logger


def pair(codigo: str) -> None:
    settings = get_settings()
    logger = get_logger(settings.log_file)
    identity = load_identity(settings.identity_file)
    client = JarvisAgentClient(settings.server_url, "")
    response = client.confirm_pairing(
        codigo,
        settings.device_name,
        settings.agent_version,
        identity.get("sistema_operacional") or platform.system(),
    )
    token = response.get("device_token")
    if not token:
        raise RuntimeError("Pareamento nao retornou token do dispositivo.")
    settings.identity_file.write_text(
        json.dumps({**identity, "pareado_em": datetime.now(timezone.utc).isoformat()}, indent=2),
        encoding="utf-8",
    )
    env_path = settings.identity_file.parent / ".env"
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = [line for line in current.splitlines() if not line.startswith("JARVIS_DEVICE_TOKEN=")]
    lines.append(f"JARVIS_DEVICE_TOKEN={token}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Dispositivo pareado com sucesso")
    print("PC pareado com sucesso. Token salvo localmente no arquivo .env do agente.")


def run_once() -> None:
    settings = get_settings()
    if not settings.device_token:
        raise RuntimeError("Configure JARVIS_DEVICE_TOKEN ou execute agent.py --pair CODIGO.")
    logger = get_logger(settings.log_file)
    identity = load_identity(settings.identity_file)
    client = JarvisAgentClient(settings.server_url, settings.device_token)
    heartbeat = {
        "identificador": identity["identificador"],
        "versao_agente": settings.agent_version,
        "sistema_operacional": identity.get("sistema_operacional") or platform.system(),
        "horario": datetime.now(timezone.utc).isoformat(),
        "status": system_status(settings.server_url, settings.agent_version),
    }
    client.heartbeat(heartbeat)
    logger.info("Heartbeat enviado")
    pending = client.next_command().get("comando")
    if not pending:
        return
    logger.info("Comando autorizado recebido: %s", pending.get("tipo"))
    result = execute_command(pending, server_url=settings.server_url, allowed_programs_file=settings.allowed_programs_file)
    client.send_result(int(pending["id"]), result)
    logger.info("Resultado do comando enviado: %s", pending.get("tipo"))


def run_forever() -> None:
    settings = get_settings()
    logger = get_logger(settings.log_file)
    backoff = settings.heartbeat_seconds
    while True:
        try:
            run_once()
            backoff = settings.heartbeat_seconds
        except Exception as exc:
            logger.error("Erro tecnico do agente: %s", exc)
            backoff = min(backoff * 2, 300)
        time.sleep(backoff)


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden Jarvis PC Agent")
    parser.add_argument("--pair", help="Codigo de pareamento criado na PWA")
    parser.add_argument("--once", action="store_true", help="Executa um heartbeat e um comando pendente")
    args = parser.parse_args()
    if args.pair:
        pair(args.pair)
    elif args.once:
        run_once()
    else:
        run_forever()


if __name__ == "__main__":
    main()
