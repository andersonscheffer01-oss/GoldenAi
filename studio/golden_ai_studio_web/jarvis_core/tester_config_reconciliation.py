"""Deterministic reconciliation for pre-registered Strategy Tester configs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


MATERIALIZATION_VERSION = "jarvis-tester-config-materialization-v1"
_RUN_ID_RE = re.compile(r"^run_[a-f0-9]{32}$")
_CAMPAIGN_ID_RE = re.compile(r"^campaign_[a-f0-9]{32}$")

_SCIENTIFIC_FIELDS = {
    "expert", "expertparameters", "symbol", "period", "model",
    "fromdate", "todate", "deposit", "currency", "leverage",
    "executionmode",
}
_EXECUTION_FIELDS = {
    "enabled", "uselocal", "useremote", "usecloud", "visual",
    "optimization", "shutdownterminal",
}
_SECURITY_FIELDS = {"allowlivetrading", "allowdllimport"}
_OUTPUT_FIELDS = {"report", "replacereport"}


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def materialized_config_fingerprint(content: str) -> str:
    """Hash the exact UTF-8 bytes written to the runtime config file."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _key_name(section: str, key: str) -> str:
    return f"{section.casefold()}.{key.casefold()}"


def classify_config_field(section: str, key: str) -> str:
    """Classify a config key; unknown keys are intentionally fail-closed."""
    del section
    normalized = key.casefold()
    if normalized in _SCIENTIFIC_FIELDS:
        return "SCIENTIFIC_SEMANTIC"
    if normalized in _EXECUTION_FIELDS:
        return "EXECUTION_SEMANTIC"
    if normalized in _SECURITY_FIELDS:
        return "SECURITY"
    if normalized in _OUTPUT_FIELDS:
        return "OUTPUT_ROUTING"
    return "UNKNOWN"


def parse_tester_ini(content: str) -> dict[str, dict[str, str]]:
    """Parse the small INI dialect used by MT5 tester configs."""
    sections: dict[str, dict[str, str]] = {}
    section = ""
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if not section:
                raise ValueError(f"EMPTY_SECTION:{line_number}")
            sections.setdefault(section, {})
            continue
        if "=" not in line or not section:
            raise ValueError(f"INVALID_INI_LINE:{line_number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or key in sections[section]:
            raise ValueError(f"INVALID_OR_DUPLICATE_KEY:{line_number}")
        sections[section][key] = value
    if "Tester" not in sections:
        raise ValueError("TESTER_SECTION_REQUIRED")
    return sections


def _flat(sections: Mapping[str, Mapping[str, str]]) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for section, values in sections.items():
        for key, value in values.items():
            result[_key_name(section, key)] = (section, key, value)
    return result


@dataclass(frozen=True)
class ConfigDifference:
    section: str
    key: str
    old_value: str | None
    new_value: str | None
    classification: str


@dataclass(frozen=True)
class ConfigReconciliation:
    status: str
    scientific_config_fingerprint: str
    materialized_config_fingerprint: str
    output_routing_fingerprint: str
    differences: tuple[ConfigDifference, ...]
    materialization_version: str = MATERIALIZATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["differences"] = [asdict(item) for item in self.differences]
        return payload


def _scientific_payload(sections: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str]]:
    return {
        section: {
            key: value for key, value in values.items()
            if classify_config_field(section, key) != "OUTPUT_ROUTING"
        }
        for section, values in sections.items()
    }


def _output_payload(sections: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str]]:
    return {
        section: {
            key: value for key, value in values.items()
            if classify_config_field(section, key) == "OUTPUT_ROUTING"
        }
        for section, values in sections.items()
        if any(classify_config_field(section, key) == "OUTPUT_ROUTING" for key in values)
    }


def scientific_config_fingerprint(content: str) -> str:
    return _canonical_hash(_scientific_payload(parse_tester_ini(content)))


def output_routing_fingerprint(content: str) -> str:
    return _canonical_hash(_output_payload(parse_tester_ini(content)))


def _bounded_report_path(report: str, output_root: Path) -> None:
    candidate = Path(report.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("REPORT_PATH_OUTSIDE_BOUNDARY")
    resolved = (output_root.resolve() / candidate).resolve()
    try:
        resolved.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValueError("REPORT_PATH_OUTSIDE_BOUNDARY") from exc


def materialize_config(content: str, campaign_id: str, test_run_id: str,
                       output_root: Path | str = ".") -> str:
    """Apply the adapter's bounded report derivation without changing semantics."""
    if not _CAMPAIGN_ID_RE.fullmatch(campaign_id):
        raise ValueError("CAMPAIGN_ID_INVALID")
    if not _RUN_ID_RE.fullmatch(test_run_id):
        raise ValueError("TEST_RUN_ID_INVALID")
    sections = parse_tester_ini(content)
    tester = sections["Tester"]
    if "Report" not in tester:
        raise ValueError("REPORT_KEY_REQUIRED")
    _bounded_report_path(tester["Report"], Path(output_root))
    report = f"Tester\\Jarvis\\{test_run_id}.htm"
    _bounded_report_path(report, Path(output_root))
    lines = content.splitlines()
    in_tester = False
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_tester = stripped[1:-1].strip().casefold() == "tester"
        if in_tester and stripped.casefold().startswith("report="):
            prefix = line[:len(line) - len(line.lstrip())]
            line = f"{prefix}Report={report}"
        output.append(line)
    return "\n".join(output) + "\n"


def reconcile_configs(pre_registered: str, runtime: str,
                      expected_runtime: str | None = None) -> ConfigReconciliation:
    old = parse_tester_ini(pre_registered)
    new = parse_tester_ini(runtime)
    old_flat = _flat(old)
    new_flat = _flat(new)
    differences: list[ConfigDifference] = []
    for name in sorted(set(old_flat) | set(new_flat)):
        old_item = old_flat.get(name)
        new_item = new_flat.get(name)
        old_value = old_item[2] if old_item else None
        new_value = new_item[2] if new_item else None
        if old_value == new_value:
            continue
        section, key = (old_item or new_item)[:2]
        differences.append(ConfigDifference(
            section, key, old_value, new_value,
            classify_config_field(section, key),
        ))
    classes = {item.classification for item in differences}
    if "UNKNOWN" in classes:
        status = "UNKNOWN_CONFIG_DIFFERENCE"
    elif "SECURITY" in classes:
        status = "SECURITY_CONFIG_MISMATCH"
    elif "SCIENTIFIC_SEMANTIC" in classes:
        status = "SCIENTIFIC_CONFIG_MISMATCH"
    elif "EXECUTION_SEMANTIC" in classes:
        status = "EXECUTION_CONFIG_MISMATCH"
    elif differences:
        status = "RECONCILED_WITH_DETERMINISTIC_MATERIALIZATION"
        if expected_runtime is None or runtime != expected_runtime:
            status = "UNEXPECTED_OPERATIONAL_MUTATION"
    else:
        status = "EXACT_MATCH"
    return ConfigReconciliation(
        status=status,
        scientific_config_fingerprint=scientific_config_fingerprint(runtime),
        materialized_config_fingerprint=materialized_config_fingerprint(runtime),
        output_routing_fingerprint=output_routing_fingerprint(runtime),
        differences=tuple(differences),
    )


__all__ = [
    "ConfigDifference", "ConfigReconciliation", "MATERIALIZATION_VERSION",
    "classify_config_field", "materialize_config", "materialized_config_fingerprint",
    "output_routing_fingerprint", "parse_tester_ini", "reconcile_configs",
    "scientific_config_fingerprint",
]
