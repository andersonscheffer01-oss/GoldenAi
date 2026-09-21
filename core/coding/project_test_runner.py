from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from core.execution import ExecutionService

from .project_models import ProjectTestResult


class ProjectTestRunner:
    def __init__(self, python_exe: str | Path | None = None, execution: ExecutionService | None = None):
        candidate = Path(python_exe or Path(r"C:\GoldenAI") / ".venv" / "Scripts" / "python.exe")
        self.python_exe = str(candidate if candidate.exists() else sys.executable)
        self.execution = execution or ExecutionService()

    def detect(self, project_root: str | Path) -> tuple[str, list[str]]:
        root = Path(project_root).resolve()
        tests_dir = root / "tests"
        if not tests_dir.exists():
            return "", []
        pytest_available = False
        try:
            proc = subprocess.run([self.python_exe, "-m", "pytest", "--version"], capture_output=True, text=True, timeout=5, check=False)
            pytest_available = proc.returncode == 0
        except Exception:
            pytest_available = False
        has_pytest_config = any((root / name).exists() for name in ("pytest.ini",)) or "pytest" in (root / "pyproject.toml").read_text(encoding="utf-8", errors="ignore") if (root / "pyproject.toml").exists() else False
        if pytest_available and has_pytest_config:
            return "pytest", [self.python_exe, "-m", "pytest", str(tests_dir)]
        return "unittest", [self.python_exe, "-m", "unittest", "discover", "-s", str(tests_dir), "-v"]

    def run(self, project_root: str | Path, task_id: str, phase: str, reports_dir: str | Path, timeout: int = 30) -> ProjectTestResult:
        root = Path(project_root).resolve()
        reports = Path(reports_dir)
        reports.mkdir(parents=True, exist_ok=True)
        runner, command = self.detect(root)
        if not runner:
            result = ProjectTestResult("", [], str(root), 1, "NO_RUNNER", 0, output_path=str(reports / f"{phase}_test_output.txt"))
            Path(result.output_path).write_text("Nenhum runner identificado.", encoding="utf-8")
            return result
        started = time.perf_counter()
        env = None
        try:
            proc = subprocess.run(command, cwd=str(root), capture_output=True, text=True, timeout=timeout, check=False)
            duration = int((time.perf_counter() - started) * 1000)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            output = stdout + stderr
            parsed = self._parse_unittest(output)
            result = ProjectTestResult(
                runner=runner,
                command=command,
                cwd=str(root),
                exit_code=proc.returncode,
                status="PASSED" if proc.returncode == 0 else "FAILED",
                duration_ms=duration,
                tests=parsed["tests"],
                failures=parsed["failures"],
                errors=parsed["errors"],
                skipped=parsed["skipped"],
                stdout=stdout,
                stderr=stderr,
                output_path=str(reports / f"{phase}_test_output.txt"),
            )
            Path(result.output_path).write_text(output, encoding="utf-8")
            self.execution.record_event(
                task_id=task_id,
                category="TEST",
                action=f"{phase.upper()}_TEST_RESULT",
                status="COMPLETED" if result.exit_code == 0 else "FAILED",
                summary=f"{runner}: {result.tests} testes, {result.failures} falhas, {result.errors} erros",
                details=f"output={result.output_path}",
                target=str(root),
                tool_name=runner,
                permission_level="EXECUTE",
                risk_level="MEDIUM",
                duration_ms=duration,
            )
            return result
        except subprocess.TimeoutExpired as exc:
            duration = int((time.perf_counter() - started) * 1000)
            output = (exc.stdout or "") + (exc.stderr or "") + "\nTIMEOUT"
            output_path = reports / f"{phase}_test_output.txt"
            output_path.write_text(output, encoding="utf-8")
            return ProjectTestResult(runner, command, str(root), 124, "TIMEOUT", duration, stdout=exc.stdout or "", stderr=exc.stderr or "", output_path=str(output_path))

    def _parse_unittest(self, output: str) -> dict[str, int]:
        data = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        ran = re.search(r"Ran\s+(\d+)\s+tests?", output)
        if ran:
            data["tests"] = int(ran.group(1))
        failed = re.search(r"FAILED\s+\(([^)]+)\)", output)
        if failed:
            for part in failed.group(1).split(","):
                if "=" in part:
                    key, value = part.strip().split("=", 1)
                    if key in data:
                        data[key] = int(value)
        skipped = re.search(r"skipped=(\d+)", output)
        if skipped:
            data["skipped"] = int(skipped.group(1))
        return data
