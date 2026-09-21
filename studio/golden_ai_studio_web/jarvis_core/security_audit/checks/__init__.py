"""Jarvis Security Audit — Checks

Cada check é uma função que retorna lista de Findings.
READ-ONLY — nunca modifica estado.
"""

import os
import re
import time
from pathlib import Path

from ..models import CheckCategory, Finding, Severity


def check_network_exposure(root: Path) -> list:
    """NETWORK: Verifica portas e bind address do Jarvis."""
    findings = []

    # Portas conhecidas do Jarvis
    known_ports = {
        8765: "Golden AI Studio (server_agent.py)",
        8780: "Jarvis Backend",
        11434: "Ollama",
    }

    # Verificar se server_agent.py tem bind address perigoso
    server_agent = root / "studio" / "golden_ai_studio_web" / "server_agent.py"
    if server_agent.exists():
        content = server_agent.read_text(encoding="utf-8", errors="ignore")

        # Verificar se está bindando em 0.0.0.0
        if re.search(r"0\.0\.0\.0", content):
            findings.append(Finding(
                id="NET-001",
                title="Server binding to 0.0.0.0",
                severity=Severity.HIGH,
                category=CheckCategory.NETWORK,
                description="server_agent.py may bind to all interfaces (0.0.0.0), exposing Jarvis to the network.",
                evidence="Bind address 0.0.0.0 found in server_agent.py",
                recommendation="Bind to 127.0.0.1 or specific LAN interface. Use firewall rules.",
            ))

        # Verificar se há rate limiting
        if "rate_limit" not in content.lower() and "throttl" not in content.lower():
            findings.append(Finding(
                id="NET-002",
                title="No rate limiting detected",
                severity=Severity.WARNING,
                category=CheckCategory.NETWORK,
                description="server_agent.py does not appear to have rate limiting.",
                evidence="No rate_limit or throttle patterns found",
                recommendation="Consider adding rate limiting for production use.",
            ))

    return findings


def check_authentication(root: Path) -> list:
    """AUTH: Verifica autenticação em endpoints sensíveis."""
    findings = []

    server_agent = root / "studio" / "golden_ai_studio_web" / "server_agent.py"
    if server_agent.exists():
        content = server_agent.read_text(encoding="utf-8", errors="ignore")

        # Verificar se há auth check
        has_auth = bool(re.search(r"auth|token|bearer|api_key", content, re.IGNORECASE))
        if not has_auth:
            findings.append(Finding(
                id="AUTH-001",
                title="No authentication mechanism detected",
                severity=Severity.WARNING,
                category=CheckCategory.AUTH,
                description="server_agent.py does not appear to have authentication.",
                evidence="No auth/token/bearer patterns found in server_agent.py",
                recommendation="Add authentication for remote access scenarios.",
            ))

    return findings


def check_credentials(root: Path) -> list:
    """CREDENTIALS: Verifica secrets expostos em código."""
    findings = []

    # Padrões que indicam secrets hardcoded
    secret_patterns = [
        (r'(?i)(?:api_key|apikey|secret|password|token)\s*=\s*["\'][A-Za-z0-9_\-]{20,}["\']',
         "Possible hardcoded secret"),
        (r'(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}',
         "Possible hardcoded bearer token"),
    ]

    # Arquivos para verificar (não verificar .env, config protegido)
    check_dirs = [
        root / "studio" / "golden_ai_studio_web",
        root / "core",
        root / "plugins",
    ]

    checked_files = set()
    for check_dir in check_dirs:
        if not check_dir.exists():
            continue
        for py_file in check_dir.rglob("*.py"):
            if py_file in checked_files:
                continue
            if "__pycache__" in str(py_file):
                continue
            if "backups" in str(py_file):
                continue
            if "test" in py_file.name.lower():
                continue
            if "references" in str(py_file):
                continue

            checked_files.add(py_file)
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for pattern, desc in secret_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # Redact o valor do match
                    redacted = re.sub(
                        r'(["\'])([^"\']{4})[^"\']*(["\'])',
                        r'\1\2***REDACTED\3',
                        match if isinstance(match, str) else str(match)
                    )
                    findings.append(Finding(
                        id=f"CRED-{py_file.stem[:8]}",
                        title=desc,
                        severity=Severity.HIGH,
                        category=CheckCategory.CREDENTIALS,
                        description=f"Possible hardcoded secret in {py_file.name}",
                        evidence=f"Pattern found: {redacted}",
                        recommendation="Move secrets to config/api_keys.json or environment variables.",
                    ))

    # Verificar .env exposto
    env_file = root / ".env"
    if env_file.exists():
        findings.append(Finding(
            id="CRED-ENV",
            title=".env file exists at project root",
            severity=Severity.INFO,
            category=CheckCategory.CREDENTIALS,
            description=".env file found at project root.",
            evidence=f"Path: {env_file}",
            recommendation="Ensure .env is in .gitignore and not accessible via web server.",
        ))

    return findings


def check_plugins(root: Path) -> list:
    """PLUGINS: Verifica segurança do plugin system."""
    findings = []

    plugins_dir = root / "plugins"
    if not plugins_dir.exists():
        return findings

    # Verificar se backups podem ser carregados
    backups_dir = plugins_dir / "backups"
    if backups_dir.exists():
        findings.append(Finding(
            id="PLUG-001",
            title="Plugin backups directory exists",
            severity=Severity.INFO,
            category=CheckCategory.PLUGINS,
            description="plugins/backups/ directory exists. Verify plugin loader excludes it.",
            evidence=f"Path: {backups_dir}",
            recommendation="Plugin loader uses glob('*.py') which is non-recursive. Safe by design.",
        ))

    # Verificar plugins com permissions perigosas
    for py_file in plugins_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        if py_file.name == "plugin_loader.py":
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if "high_risk" in content:
            findings.append(Finding(
                id=f"PLUG-{py_file.stem[:8]}",
                title=f"Plugin declares high_risk permission",
                severity=Severity.WARNING,
                category=CheckCategory.PLUGINS,
                description=f"Plugin {py_file.name} declares high_risk permission.",
                evidence=f"File: {py_file.name}",
                recommendation="Review plugin permissions. high_risk triggers confirmation flow.",
            ))

    return findings


def check_tools(root: Path) -> list:
    """TOOLS: Verifica ferramentas perigosas registradas."""
    findings = []

    # Verificar service.py para tools de risco
    service_file = root / "studio" / "golden_ai_studio_web" / "jarvis_core" / "service.py"
    if service_file.exists():
        content = service_file.read_text(encoding="utf-8", errors="ignore")

        # Verificar se há tools de shutdown/reboot
        dangerous_tools = ["shutdown", "reboot", "restart_computer"]
        for tool in dangerous_tools:
            if tool in content:
                findings.append(Finding(
                    id=f"TOOL-{tool.upper()}",
                    title=f"Dangerous tool available: {tool}",
                    severity=Severity.WARNING,
                    category=CheckCategory.TOOLS,
                    description=f"Tool '{tool}' is available in JarvisService.",
                    evidence=f"Found in service.py",
                    recommendation="Ensure this tool requires confirmation and is audit-logged.",
                ))

    return findings


def check_filesystem(root: Path) -> list:
    """FILESYSTEM: Verifica proteção de diretórios."""
    findings = []

    # Verificar se config/api_keys.json existe e tem permissões adequadas
    keys_file = root / "config" / "api_keys.json"
    if keys_file.exists():
        findings.append(Finding(
            id="FS-001",
            title="API keys file exists",
            severity=Severity.INFO,
            category=CheckCategory.FILESYSTEM,
            description="config/api_keys.json exists. Ensure it is not served via HTTP.",
            evidence=f"Path: {keys_file}",
            recommendation="Verify HTTP server does not serve config/ directory.",
        ))

    # Verificar golden_runtime.db
    db_file = root / "studio" / "golden_ai_studio_web" / "golden_runtime.db"
    if db_file.exists():
        findings.append(Finding(
            id="FS-002",
            title="SQLite database exposed",
            severity=Severity.INFO,
            category=CheckCategory.FILESYSTEM,
            description="golden_runtime.db exists in web-accessible directory.",
            evidence=f"Path: {db_file}",
            recommendation="Ensure HTTP server does not serve .db files.",
        ))

    return findings


def check_external_content(root: Path) -> list:
    """EXTERNAL_CONTENT: Verifica boundary com conteúdo externo."""
    findings = []

    # Verificar se web content é sanitizado
    internet_dir = root / "core" / "internet"
    if internet_dir.exists():
        sanitizer = internet_dir / "content_sanitizer.py"
        if sanitizer.exists():
            findings.append(Finding(
                id="EXT-001",
                title="Content sanitizer exists",
                severity=Severity.INFO,
                category=CheckCategory.EXTERNAL_CONTENT,
                description="core/internet/content_sanitizer.py exists for external content handling.",
                evidence=f"Path: {sanitizer}",
                recommendation="Ensure all external content passes through sanitizer.",
            ))
        else:
            findings.append(Finding(
                id="EXT-002",
                title="No content sanitizer found",
                severity=Severity.WARNING,
                category=CheckCategory.EXTERNAL_CONTENT,
                description="core/internet/ exists but no content_sanitizer.py found.",
                evidence=f"Directory: {internet_dir}",
                recommendation="Implement content sanitization for external input.",
            ))

    return findings


def check_model_config(root: Path) -> list:
    """MODEL_CONFIG: Verifica configuração de modelos."""
    findings = []

    # Verificar model_router.py para referências de modelo
    router_file = root / "studio" / "golden_ai_studio_web" / "jarvis_core" / "orchestrator" / "model_router.py"
    if router_file.exists():
        content = router_file.read_text(encoding="utf-8", errors="ignore")

        # Verificar se há modelos hardcoded que podem não existir
        model_refs = re.findall(r'"([^"]+/[^"]+)"', content)
        suspicious = [m for m in model_refs if "/" in m and not m.startswith("ollama/") and "timeout" not in m.lower()]
        if suspicious:
                findings.append(Finding(
                    id="MODEL-001",
                    title="External model references found",
                    severity=Severity.INFO,
                    category=CheckCategory.MODEL_CONFIG,
                    description=f"Model references found in model_router.py: {len(suspicious)} models",
                    evidence=f"Models: {', '.join(suspicious[:5])}",
                    recommendation="Verify model IDs are valid and providers are configured.",
                ))

    return findings


def check_golden_mt5(root: Path) -> list:
    """GOLDEN_MT5: Verifica boundary entre plugins/LLM e MT5."""
    findings = []

    # Verificar se há rotas diretas de plugin para MT5
    server_agent = root / "studio" / "golden_ai_studio_web" / "server_agent.py"
    if server_agent.exists():
        content = server_agent.read_text(encoding="utf-8", errors="ignore")

        # Verificar se plugins podem acessar MT5 diretamente
        if "PLUGIN_REGISTRY" in content and "mt5" in content.lower():
            # Verificar se há isolamento
            if "SecurityManager" in content:
                findings.append(Finding(
                    id="GMT5-001",
                    title="Plugin→MT5 boundary controlled",
                    severity=Severity.INFO,
                    category=CheckCategory.GOLDEN_MT5,
                    description="Plugin execution passes through SecurityManager before MT5 access.",
                    evidence="SecurityManager check found in server_agent.py",
                    recommendation="Continue enforcing SecurityManager boundary.",
                ))
            else:
                findings.append(Finding(
                    id="GMT5-002",
                    title="Plugin→MT5 boundary unclear",
                    severity=Severity.HIGH,
                    category=CheckCategory.GOLDEN_MT5,
                    description="Plugin execution may bypass SecurityManager for MT5 access.",
                    evidence="No SecurityManager check found near MT5 code",
                    recommendation="Ensure all plugin→MT5 calls go through SecurityManager.",
                ))

    # Verificar mt5_connector.py
    mt5_file = root / "studio" / "golden_ai_studio_web" / "mt5_connector.py"
    if mt5_file.exists():
        findings.append(Finding(
            id="GMT5-003",
            title="MT5 connector exists",
            severity=Severity.INFO,
            category=CheckCategory.GOLDEN_MT5,
            description="mt5_connector.py exists. Verify no direct LLM→MT5 path.",
            evidence=f"Path: {mt5_file}",
            recommendation="Audit MT5 entry points periodically.",
        ))

    return findings


def check_audit_log(root: Path) -> list:
    """AUDIT_LOG: Verifica qualidade do audit logging."""
    findings = []

    audit_file = root / "studio" / "golden_ai_studio_web" / "jarvis_core" / "audit.py"
    if audit_file.exists():
        content = audit_file.read_text(encoding="utf-8", errors="ignore")

        # Verificar se secrets são redacted
        if "_sanitize" in content and "REDACTED" in content:
            findings.append(Finding(
                id="AUDIT-001",
                title="Audit log has secret redaction",
                severity=Severity.INFO,
                category=CheckCategory.AUDIT_LOG,
                description="AuditLog has _sanitize method with REDACTED markers.",
                evidence="Found _sanitize and REDACTED in audit.py",
                recommendation="Periodically review SENSITIVE set for completeness.",
            ))
        else:
            findings.append(Finding(
                id="AUDIT-002",
                title="Audit log may not redact secrets",
                severity=Severity.HIGH,
                category=CheckCategory.AUDIT_LOG,
                description="AuditLog does not appear to have secret redaction.",
                evidence="No _sanitize or REDACTED found in audit.py",
                recommendation="Implement secret redaction in audit logging.",
            ))

        # Verificar se failures são registradas
        if "error" in content.lower() or "exception" in content.lower():
            findings.append(Finding(
                id="AUDIT-003",
                title="Audit log captures errors",
                severity=Severity.INFO,
                category=CheckCategory.AUDIT_LOG,
                description="AuditLog appears to capture error conditions.",
                evidence="Error/exception handling found in audit.py",
                recommendation="Ensure all tool failures are audit-logged.",
            ))

    return findings
