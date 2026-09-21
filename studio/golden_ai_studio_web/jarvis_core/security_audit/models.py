"""Jarvis Security Audit — Models

Estruturas de dados para findings de segurança.
READ-ONLY — nunca executa correções.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class CheckCategory(str, Enum):
    NETWORK = "network"
    AUTH = "auth"
    CREDENTIALS = "credentials"
    PLUGINS = "plugins"
    TOOLS = "tools"
    FILESYSTEM = "filesystem"
    EXTERNAL_CONTENT = "external_content"
    MODEL_CONFIG = "model_config"
    GOLDEN_MT5 = "golden_mt5"
    AUDIT_LOG = "audit_log"


@dataclass
class Finding:
    """Um finding de segurança individual."""
    id: str
    title: str
    severity: Severity
    category: CheckCategory
    description: str
    evidence: str = ""
    recommendation: str = ""
    auto_fix_available: bool = False
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "category": self.category.value,
            "description": self.description,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "auto_fix_available": self.auto_fix_available,
            "timestamp": self.timestamp,
        }


@dataclass
class CheckResult:
    """Resultado de um check individual."""
    check_name: str
    category: CheckCategory
    findings: list = field(default_factory=list)
    error: str = ""
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return len(self.findings) == 0 and not self.error

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity == Severity.HIGH for f in self.findings)


@dataclass
class AuditReport:
    """Relatório completo de auditoria."""
    findings: list = field(default_factory=list)
    check_results: list = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: float = 0.0

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    def summary(self) -> dict:
        return {
            "total_findings": self.total_findings,
            "critical": self.critical_count,
            "high": self.high_count,
            "warning": self.warning_count,
            "info": self.info_count,
            "checks_run": len(self.check_results),
            "checks_passed": sum(1 for c in self.check_results if c.passed),
            "duration_ms": self.duration_ms,
        }

    def findings_by_category(self) -> dict:
        result = {}
        for f in self.findings:
            cat = f.category.value
            if cat not in result:
                result[cat] = []
            result[cat].append(f.to_dict())
        return result

    def findings_by_severity(self) -> dict:
        result = {}
        for f in self.findings:
            sev = f.severity.value
            if sev not in result:
                result[sev] = []
            result[sev].append(f.to_dict())
        return result
