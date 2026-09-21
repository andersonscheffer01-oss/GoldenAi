from __future__ import annotations

import json
from pathlib import Path


ALLOWED_COMMANDS = frozenset({
    "verificar_status_pc",
    "verificar_ollama",
    "verificar_jarvis",
    "verificar_mt5",
    "abrir_aplicativo_autorizado",
})

BLOCKED_COMMANDS = frozenset({
    "executar_shell",
    "executar_cmd",
    "executar_powershell",
    "apagar_arquivo",
    "mover_arquivo",
    "baixar_programa",
    "instalar_programa",
    "alterar_registro",
    "reiniciar_computador",
    "desligar_computador",
    "enviar_ordem_trading",
    "pagamento",
    "transferencia",
})


DEFAULT_PROGRAMS = {
    "programas": {
        "golden_jarvis": {"caminho": r"C:\GoldenAI\jarvis\run_jarvis.bat"},
        "metatrader": {"caminho": ""},
        "navegador": {"caminho": ""},
    }
}


def is_allowed(command: str) -> bool:
    return command in ALLOWED_COMMANDS and command not in BLOCKED_COMMANDS


def validate_program_key(program_key: str) -> str:
    key = str(program_key or "").strip()
    forbidden = ("\\", "/", ":", "..", ".exe", ".bat", ".ps1")
    if not key or any(part in key for part in forbidden):
        raise ValueError("Use somente a chave de um programa autorizado.")
    return key


def load_programs(path: Path) -> dict:
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_PROGRAMS, indent=2), encoding="utf-8")
        return DEFAULT_PROGRAMS
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("programas"), dict):
        raise ValueError("Arquivo de programas autorizados invalido.")
    return data


def resolve_program_path(path: Path, program_key: str) -> Path:
    key = validate_program_key(program_key)
    data = load_programs(path)
    item = data["programas"].get(key)
    if not item or not item.get("caminho"):
        raise FileNotFoundError("Este programa ainda nao foi configurado.")
    program_path = Path(str(item["caminho"]))
    if not program_path.exists():
        raise FileNotFoundError("Este programa ainda nao foi configurado.")
    return program_path
