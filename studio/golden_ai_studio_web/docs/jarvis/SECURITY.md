# Jarvis Security Audit

READ-ONLY security audit system for the Jarvis AI platform.

## Quick Start

```python
from jarvis_core.security_audit import AuditEngine, Severity, CheckCategory

engine = AuditEngine()  # defaults to C:\GoldenAI
report = engine.run()

print(report.summary())
# {'total_findings': 8, 'critical': 0, 'high': 1, 'warning': 1, 'info': 6, ...}

# Run specific category
report = engine.run_category(CheckCategory.CREDENTIALS)

# Get findings by category/severity
by_cat = report.findings_by_category()
by_sev = report.findings_by_severity()
```

## Architecture

```
jarvis_core/security_audit/
├── __init__.py       # Package exports: AuditEngine, models
├── models.py         # Severity, CheckCategory, Finding, CheckResult, AuditReport
├── engine.py         # AuditEngine: run(), run_category(), summary()
└── checks/
    └── __init__.py   # 10 check functions (one per category)
```

## Check Categories

| Category | What it checks |
|----------|---------------|
| `NETWORK` | Bind address exposure (0.0.0.0), port exposure |
| `AUTH` | Authentication presence on API endpoints |
| `CREDENTIALS` | Hardcoded secrets, API keys, tokens (REDACTED in evidence) |
| `PLUGINS` | Plugin permissions, high_risk flags, backup vs active |
| `TOOLS` | Dangerous tool registrations (shutdown, delete, format) |
| `FILESYSTEM` | Path traversal, symlink exposure |
| `EXTERNAL_CONTENT` | Content sanitizer boundary, external content handling |
| `MODEL_CONFIG` | External model references (OpenAI, Anthropic, etc.) |
| `GOLDEN_MT5` | MT5 boundary, SecurityManager enforcement, connector presence |
| `AUDIT_LOG` | Audit redaction verification (REDACTED pattern) |

## Severity Model

- **CRITICAL**: Immediate risk, requires action
- **HIGH**: Significant risk, should be addressed
- **WARNING**: Potential risk, investigate
- **INFO**: Observation, no immediate action needed

## Design Rules

1. **READ-ONLY**: Audit never modifies config, code, or state
2. **No Auto-Fix**: Findings are reported with recommendations, never auto-applied
3. **No Secret Leakage**: Evidence values are always redacted (REDACTED)
4. **Failure Isolation**: One failed check does not break the full audit
5. **No Parallel Systems**: Never replaces SecurityManager, AuditLog, PermissionsManager, or ToolRegistry

## Running Tests

```bash
cd C:\GoldenAI\studio\golden_ai_studio_web
python -m pytest tests/test_security_audit.py -v
```

38 tests covering all 10 categories + model validation + engine API.
