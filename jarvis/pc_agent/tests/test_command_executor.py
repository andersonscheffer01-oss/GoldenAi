import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import command_executor
from command_executor import execute_command


def test_blocks_shell_command(tmp_path):
    result = execute_command({"tipo": "executar_shell", "payload": {}}, server_url="http://127.0.0.1:8780", allowed_programs_file=tmp_path / "programs.json")
    assert result["ok"] is False
    assert result["erro_codigo"] == "COMANDO_BLOQUEADO"


def test_open_program_requires_configured_key(tmp_path):
    programs = tmp_path / "programs.json"
    programs.write_text(json.dumps({"programas": {"golden_jarvis": {"caminho": ""}}}), encoding="utf-8")
    result = execute_command({"tipo": "abrir_aplicativo_autorizado", "payload": {"programa": "golden_jarvis"}}, server_url="http://127.0.0.1:8780", allowed_programs_file=programs)
    assert result["ok"] is False
    assert result["erro_codigo"] == "PROGRAMA_NAO_CONFIGURADO"


def test_status_command_uses_health_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(command_executor, "system_status", lambda **kwargs: {"jarvis": "ativo"})
    result = execute_command({"tipo": "verificar_status_pc", "payload": {}}, server_url="http://127.0.0.1:8780", allowed_programs_file=tmp_path / "programs.json")
    assert result["ok"] is True
    assert result["resultado"]["jarvis"] == "ativo"
