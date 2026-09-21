"""Jarvis Security Audit — Engine

Orquestra checks de segurança. READ-ONLY.
Nunca modifica config, não auto-corrige.

Uso:
    from jarvis_core.security_audit import AuditEngine
    engine = AuditEngine(root=r"C:\\GoldenAI")
    report = engine.run()
    print(report.summary())
"""

import time
from pathlib import Path

from .models import AuditReport, CheckCategory, CheckResult, Finding, Severity
from .checks import (
    check_network_exposure,
    check_authentication,
    check_credentials,
    check_plugins,
    check_tools,
    check_filesystem,
    check_external_content,
    check_model_config,
    check_golden_mt5,
    check_audit_log,
)


# Mapa de categorias para funções de check
ALL_CHECKS = {
    CheckCategory.NETWORK: check_network_exposure,
    CheckCategory.AUTH: check_authentication,
    CheckCategory.CREDENTIALS: check_credentials,
    CheckCategory.PLUGINS: check_plugins,
    CheckCategory.TOOLS: check_tools,
    CheckCategory.FILESYSTEM: check_filesystem,
    CheckCategory.EXTERNAL_CONTENT: check_external_content,
    CheckCategory.MODEL_CONFIG: check_model_config,
    CheckCategory.GOLDEN_MT5: check_golden_mt5,
    CheckCategory.AUDIT_LOG: check_audit_log,
}


class AuditEngine:
    """Engine de auditoria de segurança do Jarvis.

    READ-ONLY: scan, classify, report, recommend.
    Nunca auto-fix.
    """

    def __init__(self, root=None):
        if root is None:
            root = Path(r"C:\GoldenAI")
        self.root = Path(root)

    def run(self, categories=None) -> AuditReport:
        """Executa auditoria completa ou por categorias.

        Args:
            categories: Lista de CheckCategory para executar.
                       Se None, executa todas.

        Returns:
            AuditReport com findings e check results.
        """
        started = time.perf_counter()
        report = AuditReport(timestamp=time.time())

        checks_to_run = categories or list(ALL_CHECKS.keys())

        for category in checks_to_run:
            check_fn = ALL_CHECKS.get(category)
            if check_fn is None:
                continue

            check_started = time.perf_counter()
            check_name = getattr(check_fn, "__name__", str(check_fn))
            try:
                findings = check_fn(self.root)
                duration = (time.perf_counter() - check_started) * 1000
                result = CheckResult(
                    check_name=check_name,
                    category=category,
                    findings=findings,
                    duration_ms=duration,
                )
            except Exception as e:
                duration = (time.perf_counter() - check_started) * 1000
                check_name = getattr(check_fn, "__name__", str(check_fn))
                result = CheckResult(
                    check_name=check_name,
                    category=category,
                    error=str(e),
                    duration_ms=duration,
                )

            report.check_results.append(result)
            report.findings.extend(result.findings)

        report.duration_ms = (time.perf_counter() - started) * 1000
        return report

    def run_category(self, category: CheckCategory) -> AuditReport:
        """Executa auditoria para uma única categoria."""
        return self.run(categories=[category])

    def summary(self, report: AuditReport = None) -> dict:
        """Retorna resumo da auditoria."""
        if report is None:
            report = self.run()
        return report.summary()
