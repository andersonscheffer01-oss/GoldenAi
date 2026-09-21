from __future__ import annotations

import subprocess
from pathlib import Path

from allowlist import is_allowed, resolve_program_path
from health_checks import check_jarvis, check_mt5, check_ollama, system_status


def execute_command(command: dict, *, server_url: str, allowed_programs_file: Path) -> dict:
    tipo = command.get("tipo")
    payload = command.get("payload") or {}
    if not is_allowed(str(tipo)):
        return {"ok": False, "erro_codigo": "COMANDO_BLOQUEADO", "erro_mensagem": "Comando nao autorizado."}

    try:
        if tipo == "verificar_status_pc":
            return {"ok": True, "resultado": system_status(server_url=server_url)}
        if tipo == "verificar_ollama":
            return {"ok": True, "resultado": check_ollama()}
        if tipo == "verificar_jarvis":
            return {"ok": True, "resultado": {"status": check_jarvis(server_url)}}
        if tipo == "verificar_mt5":
            return {"ok": True, "resultado": {"status": check_mt5()}}
        if tipo == "abrir_aplicativo_autorizado":
            program_path = resolve_program_path(allowed_programs_file, str(payload.get("programa", "")))
            subprocess.Popen([str(program_path)], shell=False)
            return {"ok": True, "resultado": {"programa": payload.get("programa"), "status": "aberto"}}
    except FileNotFoundError as exc:
        return {"ok": False, "erro_codigo": "PROGRAMA_NAO_CONFIGURADO", "erro_mensagem": str(exc)}
    except Exception as exc:
        return {"ok": False, "erro_codigo": "ERRO_EXECUCAO", "erro_mensagem": str(exc)}
    return {"ok": False, "erro_codigo": "COMANDO_DESCONHECIDO", "erro_mensagem": "Comando nao reconhecido."}
