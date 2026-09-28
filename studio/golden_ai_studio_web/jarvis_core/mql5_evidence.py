"""Canonical, non-executing MQL5 compile/test evidence contracts.

This module models provenance and reconciles artifacts. It deliberately does not
launch MetaEditor, MT5, Strategy Tester, a terminal, or any order surface.
Execution remains a future capability gate below JarvisService security.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from .robot_catalog import parameter_fingerprint


PARAMETER_ORIGINS = (
    "EA_DEFAULT", "PRESET", "USER_DEFINED", "OPTIMIZER_GENERATED",
    "JARVIS_SUGGESTED",
)
RUN_STATUSES = (
    "PLANNED", "STARTED", "COMPLETED", "FAILED", "CANCELLED", "STALE",
)
COMPILE_STATUSES = ("COMPILE_SUCCESS", "COMPILE_FAILED", "COMPILE_UNKNOWN")
RECONCILIATION_STATUSES = (
    "RECONCILED", "UNRESOLVED", "STALE_RUN", "DUPLICATE_RESULT", "MISMATCH",
)
PARSER_VERSION = "golden-mql5-evidence-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "TRUNCATED"
    if isinstance(value, dict):
        return {str(k)[:100]: _bounded(v, depth + 1)
                for k, v in list(value.items())[:200]}
    if isinstance(value, list):
        return [_bounded(item, depth + 1) for item in value[:200]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def artifact_hash(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(content: bytes | str) -> str:
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    return hashlib.sha256(raw).hexdigest()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.endswith(";"):
        value = value[:-1].rstrip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"')
    lowered = value.casefold()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"[-+]?\d+", value):
        try:
            return int(value)
        except ValueError:
            pass
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?", value):
        try:
            return float(value)
        except ValueError:
            pass
    return value


@dataclass(frozen=True)
class Mql5ParameterDefinition:
    name: str
    type: str
    default: Any
    description: str = ""
    optimization_suitability: str = "UNKNOWN"
    source_artifact_id: str = ""
    source_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


@dataclass(frozen=True)
class EffectiveParameterSet:
    values: dict[str, Any]
    origin: str
    fingerprint: str
    source_artifact_id: str = ""
    preset_artifact_id: str = ""
    source_ref: str = ""

    @classmethod
    def create(cls, values: dict[str, Any], origin: str,
               source_artifact_id: str = "", preset_artifact_id: str = "",
               source_ref: str = "") -> "EffectiveParameterSet":
        normalized_origin = str(origin or "").upper()
        if normalized_origin not in PARAMETER_ORIGINS:
            raise ValueError("INVALID_PARAMETER_ORIGIN")
        safe_values = normalize_parameters(values)
        return cls(safe_values, normalized_origin, parameter_fingerprint(safe_values),
                   source_artifact_id, preset_artifact_id, source_ref)

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


@dataclass(frozen=True)
class TesterConfiguration:
    symbol: str = "NOT_PRESENT"
    timeframe: str = "NOT_PRESENT"
    tester_model: str = "NOT_PRESENT"
    date_from: Any = "NOT_PRESENT"
    date_to: Any = "NOT_PRESENT"
    deposit: Any = "NOT_PRESENT"
    currency: str = "NOT_PRESENT"
    leverage: Any = "NOT_PRESENT"
    terminal_build: str = "NOT_PRESENT"
    tester_build: str = "NOT_PRESENT"
    config_artifact_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


@dataclass(frozen=True)
class TestRunIdentity:
    test_run_id: str
    robot_id: str = "NOT_PRESENT"
    robot_version: str = "NOT_PRESENT"
    source_artifact_id: str = "NOT_PRESENT"
    compiled_artifact_id: str = "NOT_PRESENT"
    source_hash: str = "NOT_PRESENT"
    compiled_hash: str = "NOT_PRESENT"
    preset_artifact_id: str = "NOT_PRESENT"
    parameter_fingerprint: str = "NOT_PRESENT"
    created_at: str = ""
    started_at: str = "NOT_PRESENT"
    finished_at: str = "NOT_PRESENT"
    status: str = "PLANNED"

    @classmethod
    def create(cls, robot_id: str, robot_version: str = "NOT_PRESENT",
               source_artifact_id: str = "NOT_PRESENT",
               compiled_artifact_id: str = "NOT_PRESENT",
               source_hash: str = "NOT_PRESENT",
               compiled_hash: str = "NOT_PRESENT",
               preset_artifact_id: str = "NOT_PRESENT",
               parameter_fingerprint_value: str = "NOT_PRESENT",
               test_run_id: Optional[str] = None) -> "TestRunIdentity":
        return cls(
            test_run_id=test_run_id or "run_" + uuid.uuid4().hex,
            robot_id=robot_id,
            robot_version=robot_version,
            source_artifact_id=source_artifact_id,
            compiled_artifact_id=compiled_artifact_id,
            source_hash=source_hash,
            compiled_hash=compiled_hash,
            preset_artifact_id=preset_artifact_id,
            parameter_fingerprint=parameter_fingerprint_value,
            created_at=_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


@dataclass(frozen=True)
class GoldenTestRunManifest:
    identity: TestRunIdentity
    tester: TesterConfiguration
    parameters: EffectiveParameterSet
    expected_result_artifacts: tuple[str, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()
    manifest_hash: str = ""

    @classmethod
    def create(cls, identity: TestRunIdentity, tester: TesterConfiguration,
               parameters: EffectiveParameterSet,
               expected_result_artifacts: Iterable[str] = (),
               provenance: Iterable[dict[str, Any]] = ()) -> "GoldenTestRunManifest":
        if (identity.parameter_fingerprint not in {"", "NOT_PRESENT"} and
                identity.parameter_fingerprint != parameters.fingerprint):
            raise ValueError("MANIFEST_PARAMETER_FINGERPRINT_MISMATCH")
        draft = cls(identity, tester, parameters,
                    tuple(expected_result_artifacts),
                    tuple(_bounded(item) for item in provenance))
        payload = draft.to_dict(include_hash=False)
        return cls(identity, tester, parameters, draft.expected_result_artifacts,
                   draft.provenance, content_hash(json.dumps(payload, sort_keys=True,
                                                             ensure_ascii=True)))

    def to_dict(self, include_hash: bool = True) -> dict[str, Any]:
        result = {
            "test_run_id": self.identity.test_run_id,
            "identity": self.identity.to_dict(),
            "tester": self.tester.to_dict(),
            "parameters": self.parameters.to_dict(),
            "expected_result_artifacts": list(self.expected_result_artifacts),
            "provenance": list(self.provenance),
        }
        if include_hash:
            result["manifest_hash"] = self.manifest_hash
        return _bounded(result)


@dataclass(frozen=True)
class CompileEvidence:
    evidence_id: str
    robot_id: str
    source_artifact_id: str
    source_hash: str
    compiler: str
    compiler_version: str
    timestamp: str
    status: str
    errors: int | str
    warnings: int | str
    compiled_artifact_id: str = "NOT_PRESENT"
    compiled_hash: str = "NOT_PRESENT"
    log_artifact_id: str = "NOT_PRESENT"
    log_hash: str = "NOT_PRESENT"
    log_excerpt: str = ""
    provenance: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


@dataclass(frozen=True)
class ResultEvidence:
    evidence_id: str
    artifact_id: str
    artifact_hash: str
    parser_version: str
    test_run_id: str = "NOT_PRESENT"
    robot_id: str = "NOT_PRESENT"
    symbol: str = "NOT_PRESENT"
    timeframe: str = "NOT_PRESENT"
    period: dict[str, Any] = field(default_factory=dict)
    model: str = "NOT_PRESENT"
    parameters: dict[str, Any] | str = "NOT_PRESENT"
    parameter_fingerprint: str = "NOT_PRESENT"
    metrics: dict[str, Any] = field(default_factory=dict)
    tester_metadata: dict[str, Any] | str = "NOT_PRESENT"
    missing_fields: tuple[str, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    test_run_id: str
    reason: str
    result_artifact_id: str = "NOT_PRESENT"
    result_artifact_hash: str = "NOT_PRESENT"
    mismatches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _bounded(asdict(self))


def parse_mql5_inputs(content: str, source_artifact_id: str = "",
                     source_ref: str = "") -> list[Mql5ParameterDefinition]:
    """Parse only observed MQL5 `input type name = value;` declarations."""
    definitions: list[Mql5ParameterDefinition] = []
    pattern = re.compile(
        r"^\s*input\s+(?P<type>[A-Za-z_][A-Za-z0-9_:]*)\s+"
        r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<default>[^;]+);?"
    )
    for line_number, line in enumerate(str(content or "").splitlines(), start=1):
        match = pattern.search(line)
        if not match or match.group("type").casefold() == "group":
            continue
        description = ""
        if "//" in line:
            description = line.split("//", 1)[1].strip()
        optimization = "UNKNOWN"
        if re.search(r"optim|otimiz", description, re.I):
            optimization = "EXPLICITLY_DOCUMENTED"
        definitions.append(Mql5ParameterDefinition(
            name=match.group("name"), type=match.group("type"),
            default=_parse_scalar(match.group("default")),
            description=description, optimization_suitability=optimization,
            source_artifact_id=source_artifact_id,
            source_ref=source_ref or f"line:{line_number}",
        ))
    return definitions


def normalize_parameters(values: dict[str, Any]) -> dict[str, Any]:
    """Normalize effective values without changing their semantic types."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        normalized_key = re.sub(r"\s+", "_", str(key).strip()).casefold()
        if normalized_key:
            result[normalized_key] = _bounded(value)
    return {key: result[key] for key in sorted(result)}


def parse_set_parameters(content: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line in str(content or "").splitlines():
        line = line.strip()
        if not line or line.startswith((";", "#")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _parse_scalar(value.split("||", 1)[0])
    return normalize_parameters(values)


def _decode_log(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_compile_log(log_path: Path | str, robot_id: str,
                      source_artifact_id: str, source_hash: str,
                      compiler: str = "MetaEditor",
                      compiler_version: str = "NOT_PRESENT",
                      compiled_path: Optional[Path | str] = None) -> CompileEvidence:
    path = Path(log_path)
    raw = path.read_bytes()
    log = _decode_log(raw)
    match = re.search(r"Result\s*:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?",
                      log, re.I)
    errors: int | str = int(match.group(1)) if match else "NOT_PRESENT"
    warnings: int | str = int(match.group(2)) if match else "NOT_PRESENT"
    status = ("COMPILE_SUCCESS" if match and errors == 0 else
              "COMPILE_FAILED" if match else "COMPILE_UNKNOWN")
    compiled_hash = artifact_hash(compiled_path) if compiled_path and Path(compiled_path).is_file() else "NOT_PRESENT"
    return CompileEvidence(
        evidence_id="compile_" + content_hash(raw)[:24], robot_id=robot_id,
        source_artifact_id=source_artifact_id, source_hash=source_hash,
        compiler=compiler, compiler_version=compiler_version, timestamp=_now(),
        status=status, errors=errors, warnings=warnings,
        compiled_hash=compiled_hash,
        log_hash=content_hash(raw),
        log_excerpt=log[-4000:],
        provenance=({"source_ref": str(path), "evidence_type": "COMPILE_LOG"},),
    )


def parse_result_json(path: Path | str, artifact_id: Optional[str] = None) -> ResultEvidence:
    result_path = Path(path)
    raw = result_path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("RESULT_JSON_OBJECT_REQUIRED")
    stats = parsed.get("stats") if isinstance(parsed.get("stats"), dict) else parsed
    supported_metrics = (
        "initial_balance", "initial_deposit", "total_pnl", "profit", "gross_profit",
        "gross_loss", "max_drawdown", "drawdown", "relative_drawdown",
        "total_trades", "trades", "wins", "losses", "win_rate", "profit_factor",
        "expected_payoff", "sharpe", "return_pct",
    )
    metrics = {key: _bounded(stats[key]) for key in supported_metrics if key in stats}
    parameters = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else "NOT_PRESENT"
    parameters = normalize_parameters(parameters) if isinstance(parameters, dict) else parameters
    metadata_keys = ("terminal_build", "tester_build", "build", "tester_model", "model")
    metadata = {key: _bounded(stats.get(key, parsed.get(key)))
                for key in metadata_keys if stats.get(key, parsed.get(key)) is not None}
    fields = {
        "test_run_id": ("test_run_id",), "robot_id": ("robot_id", "robot"),
        "symbol": ("symbol",), "timeframe": ("timeframe",),
    }
    values = {name: next((stats.get(key, parsed.get(key)) for key in keys
                          if stats.get(key, parsed.get(key)) is not None), "NOT_PRESENT")
              for name, keys in fields.items()}
    period = {key: _bounded(stats[key]) for key in
              ("period_start", "period_end", "period_days") if key in stats}
    missing = tuple(sorted(set(
        [name for name, value in values.items() if value == "NOT_PRESENT"] +
        (["parameters"] if parameters == "NOT_PRESENT" else []) +
        (["tester_metadata"] if not metadata else [])
    )))
    raw_hash = content_hash(raw)
    return ResultEvidence(
        evidence_id="result_" + raw_hash[:24], artifact_id=artifact_id or "artifact_" + raw_hash[:24],
        artifact_hash=raw_hash, parser_version=PARSER_VERSION,
        test_run_id=str(values["test_run_id"]), robot_id=str(values["robot_id"]),
        symbol=str(values["symbol"]), timeframe=str(values["timeframe"]),
        period=period, model=str(stats.get("model") or "NOT_PRESENT"),
        parameters=parameters,
        parameter_fingerprint=(parameter_fingerprint(parameters)
                               if isinstance(parameters, dict) and parameters else "NOT_PRESENT"),
        metrics=metrics, tester_metadata=metadata or "NOT_PRESENT", missing_fields=missing,
        provenance=({"source_ref": str(result_path), "parser_version": PARSER_VERSION},),
    )


def reconcile_result(manifest: GoldenTestRunManifest, result: ResultEvidence,
                     known_result_hashes: Iterable[str] = (),
                     stale_run_ids: Iterable[str] = ()) -> ReconciliationResult:
    run_id = manifest.identity.test_run_id
    if run_id in set(stale_run_ids):
        return ReconciliationResult("STALE_RUN", run_id, "run was explicitly marked stale")
    if (result.artifact_hash in set(known_result_hashes) or
            result.artifact_id in manifest.expected_result_artifacts or
            result.artifact_hash in manifest.expected_result_artifacts):
        return ReconciliationResult("DUPLICATE_RESULT", run_id, "result artifact hash was already recorded",
                                    result.evidence_id, result.artifact_hash)
    if result.test_run_id != run_id:
        return ReconciliationResult("MISMATCH", run_id, "result does not carry the manifest test_run_id",
                                    result.evidence_id, result.artifact_hash, ("test_run_id",))
    mismatches = []
    if result.robot_id not in {"NOT_PRESENT", manifest.identity.robot_id}:
        mismatches.append("robot_id")
    if (manifest.tester.symbol != "NOT_PRESENT" and result.symbol != "NOT_PRESENT" and
            manifest.tester.symbol != result.symbol):
        mismatches.append("symbol")
    if (manifest.tester.timeframe != "NOT_PRESENT" and result.timeframe != "NOT_PRESENT" and
            manifest.tester.timeframe != result.timeframe):
        mismatches.append("timeframe")
    if (manifest.identity.parameter_fingerprint not in {"", "NOT_PRESENT"} and
            result.parameter_fingerprint != "NOT_PRESENT" and
            manifest.identity.parameter_fingerprint != result.parameter_fingerprint):
        mismatches.append("parameter_fingerprint")
    if mismatches:
        return ReconciliationResult("MISMATCH", run_id, "result conflicts with manifest identity",
                                    result.evidence_id, result.artifact_hash, tuple(mismatches))
    return ReconciliationResult("RECONCILED", run_id, "manifest identity and result evidence match",
                                result.evidence_id, result.artifact_hash)


class StrategyTesterAdapterDesign:
    """Bounded planning surface; real process execution is intentionally absent."""

    execution_mode = "DESIGN_ONLY"
    trade_authority = "NONE"

    @staticmethod
    def plan(manifest: GoldenTestRunManifest, managed_root: Path | str) -> dict[str, Any]:
        root = Path(managed_root).resolve()
        run_dir = (root / manifest.identity.test_run_id).resolve()
        try:
            run_dir.relative_to(root)
        except ValueError:
            return {"ok": False, "error": "RUN_DIRECTORY_OUTSIDE_MANAGED_ROOT"}
        return {
            "ok": True, "execution_mode": "DESIGN_ONLY", "trade_authority": "NONE",
            "test_run_id": manifest.identity.test_run_id,
            "managed_run_directory": str(run_dir),
            "manifest_hash": manifest.manifest_hash,
            "process_lifecycle": ["START", "TIMEOUT", "CANCEL", "CLEANUP", "VERIFY"],
            "parallelism": "BOUNDED_SINGLE_RUN",
            "start": "NOT_IMPLEMENTED",
        }


__all__ = [
    "COMPILE_STATUSES", "CompileEvidence", "EffectiveParameterSet",
    "GoldenTestRunManifest", "Mql5ParameterDefinition", "PARAMETER_ORIGINS",
    "PARSER_VERSION", "RECONCILIATION_STATUSES", "ReconciliationResult",
    "ResultEvidence", "RUN_STATUSES", "StrategyTesterAdapterDesign",
    "TestRunIdentity", "TesterConfiguration", "artifact_hash", "content_hash",
    "normalize_parameters", "parameter_fingerprint", "parse_compile_log",
    "parse_mql5_inputs", "parse_result_json", "parse_set_parameters",
    "reconcile_result",
]
