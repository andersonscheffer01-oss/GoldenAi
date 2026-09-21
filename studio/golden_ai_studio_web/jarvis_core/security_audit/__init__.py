"""Jarvis Security Audit

READ-ONLY security audit system for Jarvis.
Scans, classifies, reports, recommends.
Never auto-fixes.

Usage:
    from jarvis_core.security_audit import AuditEngine, Severity, CheckCategory
    engine = AuditEngine()
    report = engine.run()
    print(report.summary())
"""

from .engine import AuditEngine
from .models import AuditReport, CheckCategory, CheckResult, Finding, Severity

__all__ = [
    "AuditEngine",
    "AuditReport",
    "CheckCategory",
    "CheckResult",
    "Finding",
    "Severity",
]
