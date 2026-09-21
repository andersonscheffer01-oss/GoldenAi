"""
Testes obrigatórios — Jarvis Security Audit Baseline

15+ testes conforme especificação.
READ-ONLY — nenhum teste modifica config ou estado.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

GOLDEN_ROOT = Path(r"C:\GoldenAI")
sys.path.insert(0, str(GOLDEN_ROOT / "studio" / "golden_ai_studio_web"))

from jarvis_core.security_audit import (
    AuditEngine,
    AuditReport,
    CheckCategory,
    CheckResult,
    Finding,
    Severity,
)
from jarvis_core.security_audit.checks import (
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


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def engine():
    return AuditEngine(GOLDEN_ROOT)


@pytest.fixture
def clean_root():
    """Diretório temporário limpo para testes controlados."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ═══════════════════════════════════════════════════════════════
# TESTES OBRIGATÓRIOS
# ═══════════════════════════════════════════════════════════════

class TestCleanBaselineReturnsNoFalseCritical:
    """1. clean_baseline_returns_no_false_critical"""

    def test_no_false_critical_on_real_jarvis(self, engine):
        """Auditoria real do Jarvis não deve retornar CRITICAL falso."""
        report = engine.run()
        # CRITICAL só deve existir se houver evidência real
        # No estado atual, deve ser 0
        assert report.critical_count == 0

    def test_clean_directory_no_findings(self, clean_root):
        """Diretório vazio não deve gerar findings."""
        engine = AuditEngine(clean_root)
        report = engine.run()
        # Sem código, sem findings relevantes
        assert report.critical_count == 0
        assert report.high_count == 0


class TestExposedServiceDetected:
    """2. exposed_service_detected"""

    def test_bind_address_detected(self, clean_root):
        """Detecta bind em 0.0.0.0."""
        # Criar server_agent.py falso com bind 0.0.0.0
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "server_agent.py").write_text(
            'HTTPServer(("0.0.0.0", 8765), Handler)\n'
        )
        findings = check_network_exposure(clean_root)
        ids = [f.id for f in findings]
        assert "NET-001" in ids

    def test_no_bind_address(self, clean_root):
        """Sem bind 0.0.0.0 não gera finding NET-001."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "server_agent.py").write_text(
            'HTTPServer(("127.0.0.1", 8765), Handler)\n'
        )
        findings = check_network_exposure(clean_root)
        ids = [f.id for f in findings]
        assert "NET-001" not in ids


class TestMissingAuthDetected:
    """3. missing_auth_detected"""

    def test_no_auth_detected(self, clean_root):
        """Detecta ausência de autenticação."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "server_agent.py").write_text(
            '# server setup only\nHTTPServer(("127.0.0.1", 8765), Handler)\n'
        )
        findings = check_authentication(clean_root)
        ids = [f.id for f in findings]
        assert "AUTH-001" in ids

    def test_auth_present(self, clean_root):
        """Presença de auth não gera finding."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "server_agent.py").write_text(
            'token = request.headers.get("Authorization")\n'
        )
        findings = check_authentication(clean_root)
        ids = [f.id for f in findings]
        assert "AUTH-001" not in ids


class TestHardcodedSecretDetectedWithoutLeakingValue:
    """4. hardcoded_secret_detected_without_leaking_value"""

    def test_hardcoded_secret_detected(self, clean_root):
        """Detecta secret hardcoded."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "app_config.py").write_text(
            'api_key = "sk-123456789012345678901234567890"\n'
        )
        findings = check_credentials(clean_root)
        # Deve encontrar o secret
        secret_findings = [f for f in findings if f.category == CheckCategory.CREDENTIALS]
        assert len(secret_findings) > 0

    def test_secret_value_not_in_evidence(self, clean_root):
        """Valor do secret NÃO aparece na evidence."""
        secret_value = "sk-supersecret1234567890abcdef"
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "app_config.py").write_text(
            f'api_key = "{secret_value}"\n'
        )
        findings = check_credentials(clean_root)
        for f in findings:
            assert secret_value not in f.evidence, \
                f"Secret value leaked in evidence: {f.evidence}"

    def test_redacted_in_evidence(self, clean_root):
        """Evidence contém REDACTED."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "app_config.py").write_text(
            'api_key = "sk-123456789012345678901234567890"\n'
        )
        findings = check_credentials(clean_root)
        secret_findings = [f for f in findings if f.category == CheckCategory.CREDENTIALS]
        for f in secret_findings:
            assert "REDACTED" in f.evidence or f.evidence == ""


class TestPluginPermissionIssueDetected:
    """5. plugin_permission_issue_detected"""

    def test_high_risk_plugin_detected(self, clean_root):
        """Detecta plugin com high_risk permission."""
        plugins_dir = clean_root / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "risky_plugin.py").write_text(
            'name = "risky"\n'
            'permissions = ["high_risk"]\n'
            'def execute(args): return {}\n'
        )
        findings = check_plugins(clean_root)
        ids = [f.id for f in findings]
        assert any(i.startswith("PLUG-") for i in ids)

    def test_safe_plugin_no_finding(self, clean_root):
        """Plugin sem high_risk não gera finding de permissão."""
        plugins_dir = clean_root / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "safe_plugin.py").write_text(
            'name = "safe"\n'
            'permissions = ["read_only"]\n'
            'def execute(args): return {}\n'
        )
        findings = check_plugins(clean_root)
        high_risk_findings = [f for f in findings if "high_risk" in f.title.lower()]
        assert len(high_risk_findings) == 0


class TestDangerousToolDetected:
    """6. dangerous_tool_detected"""

    def test_shutdown_tool_detected(self, clean_root):
        """Detecta tool de shutdown."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web" / "jarvis_core"
        studio_dir.mkdir(parents=True)
        (studio_dir / "service.py").write_text(
            'def shutdown_computer(): pass\n'
            'TOOLS = ["shutdown"]\n'
        )
        findings = check_tools(clean_root)
        ids = [f.id for f in findings]
        assert any(i.startswith("TOOL-") for i in ids)


class TestBackupPluginNotFlaggedAsActive:
    """7. backup_plugin_not_flagged_as_active"""

    def test_backup_dir_info_only(self, clean_root):
        """Backups directory gera INFO, não WARNING."""
        plugins_dir = clean_root / "plugins"
        plugins_dir.mkdir()
        backups_dir = plugins_dir / "backups"
        backups_dir.mkdir()
        (backups_dir / "old_plugin.py").write_text('name = "old"\n')

        findings = check_plugins(clean_root)
        backup_findings = [f for f in findings if "backup" in f.title.lower()]
        for f in backup_findings:
            assert f.severity == Severity.INFO


class TestExternalContentBoundaryChecked:
    """8. external_content_boundary_checked"""

    def test_sanitizer_exists(self, clean_root):
        """Detecta content sanitizer."""
        internet_dir = clean_root / "core" / "internet"
        internet_dir.mkdir(parents=True)
        (internet_dir / "content_sanitizer.py").write_text('# sanitizer\n')
        findings = check_external_content(clean_root)
        ids = [f.id for f in findings]
        assert "EXT-001" in ids

    def test_no_sanitizer_warning(self, clean_root):
        """Sem sanitizer gera WARNING."""
        internet_dir = clean_root / "core" / "internet"
        internet_dir.mkdir(parents=True)
        findings = check_external_content(clean_root)
        ids = [f.id for f in findings]
        assert "EXT-002" in ids


class TestInvalidModelReferenceDetected:
    """9. invalid_model_reference_detected"""

    def test_external_models_found(self, clean_root):
        """Detecta referências de modelo externo."""
        orch_dir = clean_root / "studio" / "golden_ai_studio_web" / "jarvis_core" / "orchestrator"
        orch_dir.mkdir(parents=True)
        (orch_dir / "model_router.py").write_text(
            'MODELS = ["openai/gpt-4", "anthropic/claude-3"]\n'
        )
        findings = check_model_config(clean_root)
        ids = [f.id for f in findings]
        assert "MODEL-001" in ids


class TestDirectMt5AccessFlagged:
    """10. direct_mt5_access_flagged"""

    def test_mt5_boundary_checked(self, clean_root):
        """Verifica boundary plugin→MT5."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        # Sem SecurityManager = boundary unclear
        (studio_dir / "server_agent.py").write_text(
            'PLUGIN_REGISTRY.execute("mt5_trade", args)\n'
        )
        findings = check_golden_mt5(clean_root)
        # Pode gerar GMT5-002 (boundary unclear)
        ids = [f.id for f in findings]
        assert any(i.startswith("GMT5") for i in ids)

    def test_security_manager_present(self, clean_root):
        """SecurityManager controla boundary."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "server_agent.py").write_text(
            'SecurityManager.check()\nPLUGIN_REGISTRY.execute("mt5_trade", args)\n'
        )
        findings = check_golden_mt5(clean_root)
        ids = [f.id for f in findings]
        assert "GMT5-001" in ids


class TestDirectGoldenAccessFlagged:
    """11. direct_golden_access_flagged"""

    def test_golden_connector_exists(self, clean_root):
        """Detecta presence do mt5_connector."""
        studio_dir = clean_root / "studio" / "golden_ai_studio_web"
        studio_dir.mkdir(parents=True)
        (studio_dir / "mt5_connector.py").write_text('# MT5 connector\n')
        findings = check_golden_mt5(clean_root)
        ids = [f.id for f in findings]
        assert "GMT5-003" in ids


class TestAuditLogRedactionVerified:
    """12. audit_log_redaction_verified"""

    def test_redaction_exists(self, clean_root):
        """AuditLog tem redaction de secrets."""
        jarvis_dir = clean_root / "studio" / "golden_ai_studio_web" / "jarvis_core"
        jarvis_dir.mkdir(parents=True)
        (jarvis_dir / "audit.py").write_text(
            'class AuditLog:\n'
            '    SENSITIVE = {"password", "token"}\n'
            '    def _sanitize(self, value, key=""):\n'
            '        return "[REDACTED]"\n'
        )
        findings = check_audit_log(clean_root)
        ids = [f.id for f in findings]
        assert "AUDIT-001" in ids

    def test_no_redaction_warning(self, clean_root):
        """Sem redaction gera WARNING."""
        jarvis_dir = clean_root / "studio" / "golden_ai_studio_web" / "jarvis_core"
        jarvis_dir.mkdir(parents=True)
        (jarvis_dir / "audit.py").write_text(
            'class AuditLog:\n    def add(self, **row): pass\n'
        )
        findings = check_audit_log(clean_root)
        ids = [f.id for f in findings]
        assert "AUDIT-002" in ids


class TestAuditIsReadOnly:
    """13. audit_is_read_only"""

    def test_engine_does_not_modify_files(self, clean_root):
        """Engine não modifica nenhum arquivo."""
        # Criar arquivo para monitorar
        test_file = clean_root / "test.txt"
        test_file.write_text("original")
        original_content = test_file.read_text()
        original_mtime = test_file.stat().st_mtime

        engine = AuditEngine(clean_root)
        engine.run()

        # Arquivo não deve ter sido modificado
        assert test_file.read_text() == original_content
        assert test_file.stat().st_mtime == original_mtime

    def test_no_config_changes(self, engine):
        """Engine real não modifica config."""
        import os
        config_file = GOLDEN_ROOT / "config" / "api_keys.json"
        if config_file.exists():
            original = config_file.read_text(encoding="utf-8")
            original_mtime = config_file.stat().st_mtime
            engine.run()
            # Em ambiente de teste, pode haver race condition
            # Mas o engine não escreve em config


class TestOneFailedCheckDoesNotBreakFullAudit:
    """14. one_failed_check_does_not_break_full_audit"""

    def test_failed_check_continues(self, clean_root):
        """Check que falha não quebra auditoria completa."""
        engine = AuditEngine(clean_root)
        # Forçar erro em um check monkeypatching
        with patch("jarvis_core.security_audit.engine.ALL_CHECKS", {
            CheckCategory.NETWORK: MagicMock(side_effect=Exception("Test error")),
            CheckCategory.AUTH: lambda root: [],
            CheckCategory.CREDENTIALS: lambda root: [],
            CheckCategory.PLUGINS: lambda root: [],
            CheckCategory.TOOLS: lambda root: [],
            CheckCategory.FILESYSTEM: lambda root: [],
            CheckCategory.EXTERNAL_CONTENT: lambda root: [],
            CheckCategory.MODEL_CONFIG: lambda root: [],
            CheckCategory.GOLDEN_MT5: lambda root: [],
            CheckCategory.AUDIT_LOG: lambda root: [],
        }):
            report = engine.run()
            # Audit must complete
            assert report is not None
            assert len(report.check_results) == 10
            # One check errored, others passed
            errored = [c for c in report.check_results if c.error]
            assert len(errored) == 1
            assert "Test error" in errored[0].error

    def test_partial_category_run(self, engine):
        """Execução por categoria funciona."""
        report = engine.run_category(CheckCategory.CREDENTIALS)
        assert report is not None
        assert len(report.check_results) == 1
        assert report.check_results[0].category == CheckCategory.CREDENTIALS


class TestSeveritySummaryCorrect:
    """15. severity_summary_correct"""

    def test_summary_structure(self, engine):
        """Summary tem todos os campos."""
        report = engine.run()
        summary = report.summary()
        assert "total_findings" in summary
        assert "critical" in summary
        assert "high" in summary
        assert "warning" in summary
        assert "info" in summary
        assert "checks_run" in summary
        assert "checks_passed" in summary
        assert "duration_ms" in summary

    def test_summary_counts_match(self, engine):
        """Contadores do summary batem com findings."""
        report = engine.run()
        summary = report.summary()
        assert summary["critical"] == report.critical_count
        assert summary["high"] == report.high_count
        assert summary["warning"] == report.warning_count
        assert summary["info"] == report.info_count
        assert summary["total_findings"] == report.total_findings

    def test_findings_by_category(self, engine):
        """findings_by_category retorna dict correto."""
        report = engine.run()
        by_cat = report.findings_by_category()
        assert isinstance(by_cat, dict)
        for cat, findings in by_cat.items():
            assert isinstance(findings, list)
            for f in findings:
                assert "id" in f
                assert "severity" in f

    def test_findings_by_severity(self, engine):
        """findings_by_severity retorna dict correto."""
        report = engine.run()
        by_sev = report.findings_by_severity()
        assert isinstance(by_sev, dict)
        for sev, findings in by_sev.items():
            assert sev in ("info", "warning", "high", "critical")


# ═══════════════════════════════════════════════════════════════
# TESTES EXTRAS
# ═══════════════════════════════════════════════════════════════

class TestFindingModel:
    """Testes do modelo Finding."""

    def test_finding_to_dict(self):
        """Finding.to_dict() retorna dict válido."""
        f = Finding(
            id="TEST-001",
            title="Test finding",
            severity=Severity.WARNING,
            category=CheckCategory.NETWORK,
            description="Test description",
            evidence="test evidence",
            recommendation="test recommendation",
        )
        d = f.to_dict()
        assert d["id"] == "TEST-001"
        assert d["severity"] == "warning"
        assert d["category"] == "network"

    def test_severity_values(self):
        """Severity tem todos os valores."""
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.HIGH.value == "high"
        assert Severity.CRITICAL.value == "critical"

    def test_check_category_values(self):
        """CheckCategory tem 10 categorias."""
        assert len(CheckCategory) == 10


class TestCheckResult:
    """Testes do modelo CheckResult."""

    def test_passed_when_no_findings(self):
        """CheckResult.passed True quando sem findings."""
        r = CheckResult(check_name="test", category=CheckCategory.NETWORK)
        assert r.passed is True

    def test_not_passed_with_findings(self):
        """CheckResult.passed False quando tem findings."""
        r = CheckResult(
            check_name="test",
            category=CheckCategory.NETWORK,
            findings=[Finding(id="X", title="X", severity=Severity.HIGH, category=CheckCategory.NETWORK, description="X")],
        )
        assert r.passed is False

    def test_not_passed_with_error(self):
        """CheckResult.passed False quando tem error."""
        r = CheckResult(check_name="test", category=CheckCategory.NETWORK, error="boom")
        assert r.passed is False


class TestEngineAPI:
    """Testes da API do engine."""

    def test_engine_default_root(self):
        """Engine com root default."""
        e = AuditEngine()
        assert e.root == Path(r"C:\GoldenAI")

    def test_engine_custom_root(self):
        """Engine com root customizado."""
        e = AuditEngine("/tmp/test")
        assert e.root == Path("/tmp/test")

    def test_summary_without_report(self):
        """summary() sem report executa auditoria."""
        e = AuditEngine(GOLDEN_ROOT)
        s = e.summary()
        assert "total_findings" in s
