import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from allowlist import is_allowed, validate_program_key


def test_allowed_and_blocked_commands():
    assert is_allowed("verificar_status_pc")
    assert is_allowed("abrir_aplicativo_autorizado")
    assert not is_allowed("executar_shell")
    assert not is_allowed("executar_powershell")
    assert not is_allowed("enviar_ordem_trading")


def test_program_key_rejects_paths():
    assert validate_program_key("golden_jarvis") == "golden_jarvis"
    for value in [r"C:\Windows\cmd.exe", "../cmd", "app.bat", ""]:
        try:
            validate_program_key(value)
            raised = False
        except ValueError:
            raised = True
        assert raised
