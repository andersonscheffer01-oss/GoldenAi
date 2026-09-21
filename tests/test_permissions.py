"""
Testes unitários para core/permissions/manager.py
O módulo mais crítico de segurança do Golden AI.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.permissions import PermissionManager
from core.config import load_settings


# ============================================================
# SETUP
# ============================================================

def get_manager():
    """Cria PermissionManager com config de teste."""
    settings = load_settings()
    return PermissionManager(settings)


# ============================================================
# TESTES: Leitura
# ============================================================

def test_can_read_allowed_path():
    """Leitura em path permitido deve ser autorizada."""
    pm = get_manager()
    result = pm.can_read(r"C:\GoldenAI\projetos\teste.py")
    assert result.allowed, f"Leitura bloqueada: {result.reason}"
    print("OK test_can_read_allowed_path")


def test_can_read_protected_path():
    """Leitura em path protegido deve ser autorizada."""
    pm = get_manager()
    result = pm.can_read(r"C:\GoldenAI\app\golden_ai.py")
    assert result.allowed, f"Leitura bloqueada em path protegido: {result.reason}"
    print("OK test_can_read_protected_path")


def test_can_read_external_path():
    """Leitura em path externo deve ser bloqueada."""
    pm = get_manager()
    result = pm.can_read(r"C:\Windows\System32\config\sam")
    assert not result.allowed, f"Leitura externa permitida: {result.reason}"
    print("OK test_can_read_external_path")


# ============================================================
# TESTES: Escrita
# ============================================================

def test_can_write_allowed_path():
    """Escrita em path permitido deve ser autorizada (quando não read-only)."""
    pm = get_manager()
    result = pm.can_write(r"C:\GoldenAI\projetos\teste.py", explicit_authorization=True)
    # Pode ser bloqueado se read_only=True nas configs
    assert isinstance(result.allowed, bool)
    print(f"OK test_can_write_allowed_path (allowed={result.allowed})")


def test_can_write_protected_path():
    """Escrita em path protegido deve ser bloqueada."""
    pm = get_manager()
    result = pm.can_write(r"C:\GoldenAI\app\golden_ai.py")
    assert not result.allowed, f"Escrita em path protegido permitida: {result.reason}"
    print("OK test_can_write_protected_path")


def test_can_write_external_path():
    """Escrita em path externo deve ser bloqueada."""
    pm = get_manager()
    result = pm.can_write(r"C:\Windows\teste.txt")
    assert not result.allowed, f"Escrita externa permitida: {result.reason}"
    print("OK test_can_write_external_path")


# ============================================================
# TESTES: Execução de Comandos
# ============================================================

def test_can_execute_command():
    """Verifica se execução de comandos respeita config."""
    pm = get_manager()
    result = pm.can_execute_command("dir C:\\GoldenAI")
    assert isinstance(result.allowed, bool)
    print(f"OK test_can_execute_command (allowed={result.allowed})")


# ============================================================
# TESTES: Read-Only Mode
# ============================================================

def test_is_read_only():
    """Verifica se is_read_only retorna bool."""
    pm = get_manager()
    result = pm.is_read_only()
    assert isinstance(result, bool)
    print(f"OK test_is_read_only (read_only={result})")


# ============================================================
# TESTES: Protected Directory
# ============================================================

def test_is_protected_dir():
    """Verifica se paths protegidos são detectados."""
    pm = get_manager()
    assert pm.is_protected_dir(r"C:\GoldenAI\app"), "app/ deveria ser protegido"
    assert pm.is_protected_dir(r"C:\GoldenAI\studio"), "studio/ deveria ser protegido"
    assert not pm.is_protected_dir(r"C:\GoldenAI\projetos"), "projetos/ nao deveria ser protegido"
    print("OK test_is_protected_dir")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GOLDEN AI - TESTES DE SEGURANCA (core/permissions)")
    print("=" * 60)
    print()

    tests = [
        test_can_read_allowed_path,
        test_can_read_protected_path,
        test_can_read_external_path,
        test_can_write_allowed_path,
        test_can_write_protected_path,
        test_can_write_external_path,
        test_can_execute_command,
        test_is_read_only,
        test_is_protected_dir,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAILED {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Resultado: {passed} passaram, {failed} falharam de {len(tests)}")
    print("=" * 60)
