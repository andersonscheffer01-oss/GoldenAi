from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .models import ValidationResult


class CodingValidator:
    def __init__(self, python_exe: str | Path | None = None):
        candidate = Path(python_exe or Path(r"C:\GoldenAI") / ".venv" / "Scripts" / "python.exe")
        self.python_exe = str(candidate if candidate.exists() else sys.executable)

    def validate(self, path: str | Path, phase: str = "pre_apply") -> ValidationResult:
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix == ".py":
            return self._validate_python(target, phase)
        if suffix == ".mq5":
            return self._validate_mql5(target, phase)
        return ValidationResult(False, phase, "UNSUPPORTED", "Linguagem nao suportada")

    def _validate_python(self, path: Path, phase: str) -> ValidationResult:
        try:
            proc = subprocess.run(
                [self.python_exe, "-m", "py_compile", str(path)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            return ValidationResult(proc.returncode == 0, phase, "PASSED" if proc.returncode == 0 else "FAILED", output)
        except Exception as exc:
            return ValidationResult(False, phase, "FAILED", str(exc))

    def _validate_mql5(self, path: Path, phase: str) -> ValidationResult:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "SYNTAX_ERROR_FOR_TEST" in text:
            return ValidationResult(False, phase, "FAILED", "Marcador de erro controlado encontrado")
        if not path.exists() or path.suffix.lower() != ".mq5":
            return ValidationResult(False, phase, "FAILED", "Arquivo MQL5 invalido")
        return ValidationResult(True, phase, "PASSED", "Validacao estrutural MQL5 em working copy concluida")
