"""Read-only projection of the isolated Golden Scalper Arena report."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ARENA_REPORT_PATH = REPO_ROOT / "projetos" / "GoldenScalperArena" / "Data" / "experiments" / "latest_report.json"
SECURITY = {
    "read_only": True,
    "simulation_only": True,
    "execution_authority": "NONE",
    "real_orders": False,
}


def _unavailable(error_code: str, message: str) -> dict:
    return {
        "ok": False,
        "status": "UNAVAILABLE",
        "error_code": error_code,
        "message": message,
        "security": dict(SECURITY),
        "report": None,
    }


def load_arena_report() -> dict:
    """Load the latest local report without executing the Arena or MT5."""
    try:
        report = json.loads(ARENA_REPORT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _unavailable("ARENA_REPORT_NOT_FOUND", "Relatório da Arena ainda não foi gerado.")
    except (OSError, UnicodeError):
        return _unavailable("ARENA_REPORT_READ_FAILED", "Não foi possível ler o relatório da Arena.")
    except json.JSONDecodeError:
        return _unavailable("ARENA_REPORT_INVALID_JSON", "O relatório da Arena não é um JSON válido.")

    if not isinstance(report, dict):
        return _unavailable("ARENA_REPORT_INVALID_SCHEMA", "O relatório da Arena tem formato inválido.")
    report_security = report.get("security")
    if report_security != SECURITY:
        return _unavailable("ARENA_SECURITY_CONTRACT_INVALID", "O relatório não confirma o contrato somente leitura.")
    return {
        "ok": True,
        "status": "AVAILABLE",
        "security": dict(SECURITY),
        "report": report,
    }


__all__ = ["ARENA_REPORT_PATH", "SECURITY", "load_arena_report"]

