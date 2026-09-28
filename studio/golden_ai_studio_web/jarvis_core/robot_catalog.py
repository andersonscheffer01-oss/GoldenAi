"""Read-only Golden robot catalog and evidence model.

The catalog deliberately stays in Jarvis Core and keeps discovery separate
from trading, MT5, Strategy Tester, and durable memory writes.  Persistence
is intentionally deferred until a canonical schema migration is authorized.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional


LIFECYCLE_STATES = (
    "DISCOVERED", "CANDIDATE", "ACTIVE", "INACTIVE", "BLOCKED", "ARCHIVED"
)
EVIDENCE_TYPES = (
    "SOURCE_VERIFIED", "DOCUMENTATION_VERIFIED", "CONFIG_VERIFIED",
    "ARTIFACT_OBSERVED", "BACKTEST_EVIDENCE", "OPTIMIZATION_EVIDENCE",
    "FORWARD_TEST_EVIDENCE", "LIVE_OBSERVATION", "USER_DEFINED",
    "JARVIS_INFERRED", "TEST_RESULT", "UNKNOWN"
)
FACT_SOURCES = (
    "FACT_FROM_SOURCE", "FACT_FROM_DOCUMENTATION", "USER_ASSERTION",
    "JARVIS_INFERENCE", "TEST_RESULT", "UNKNOWN"
)

SOURCE_EXTENSIONS = {".mq5", ".mq4"}
COMPILED_EXTENSIONS = {".ex5", ".ex4"}
PRESET_EXTENSIONS = {".set", ".ini"}
DOCUMENTATION_EXTENSIONS = {".xml", ".csv", ".html", ".htm", ".log"}
BACKTEST_EXTENSIONS = {".json"}
TRACKED_EXTENSIONS = (SOURCE_EXTENSIONS | COMPILED_EXTENSIONS |
                      PRESET_EXTENSIONS | DOCUMENTATION_EXTENSIONS |
                      BACKTEST_EXTENSIONS)
EXCLUDED_DIRECTORY_NAMES = {
    ".git", ".venv", "__pycache__", "build", "dist", "node_modules",
    "tests", "test", "fixtures", "fixture", "attachments", "attachment",
    "uploads", "upload", "runtime", "cache", "coverage",
}
EXCLUDED_PATH_MARKERS = {
    "_capability_audit", "_coding_test", "_market_chat", "_quant_chat",
}
ARCHIVED_NAME_MARKERS = ("universal_backtest_ea", "robo_teste")
MULTI_VALUE_CLAIMS = {
    "supported_symbols", "supported_timeframes", "parameter_preset",
    "backtest_evidence",
}
DISCOVERY_KEYWORDS = (
    "robot", "robo", "ea", "strategy", "backtest", "tester", "optimization",
    "otimiz", "range", "pullback", "turtle", "vwap", "trend", "tendencia",
)


def _normal_key(value: str) -> str:
    value = re.sub(r"\.[^.]+$", "", str(value or "").casefold())
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def _human_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", value)).strip() or "Unknown robot"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(path: Path, limit: int = 2_000_000) -> str:
    with path.open("rb") as handle:
        return handle.read(limit).decode("utf-8", errors="replace")


def _bounded(value: Any, depth: int = 0) -> Any:
    """Keep parsed artifact metadata small and JSON-safe."""
    if depth > 3:
        return "TRUNCATED"
    if isinstance(value, dict):
        return {str(k)[:80]: _bounded(v, depth + 1)
                for k, v in list(value.items())[:80]}
    if isinstance(value, list):
        return [_bounded(item, depth + 1) for item in value[:80]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def default_approved_roots(workspace_root: Optional[Path | str] = None) -> tuple[Path, ...]:
    root = Path(workspace_root or Path(__file__).resolve().parents[3]).resolve()
    return (
        root / "projetos",
        root / "studio" / "golden_ai_studio_web",
        root / "config" / "backtest_results",
    )


@dataclass(frozen=True)
class RobotArtifact:
    artifact_id: str
    kind: str
    relative_path: str
    root_label: str
    sha256: str
    size: int
    modified_at: float
    association_confidence: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "relative_path": self.relative_path,
            "root": self.root_label,
            "sha256": self.sha256,
            "size": self.size,
            "modified_at": self.modified_at,
            "association_confidence": self.association_confidence,
        }


@dataclass
class EvidenceClaim:
    claim_id: str
    field: str
    value: Any
    evidence_type: str
    fact_source: str
    source_artifact_id: str = ""
    source_ref: str = ""
    confidence: str = "HIGH"
    reason: str = ""
    conflict_group: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "field": self.field,
            "value": _bounded(self.value),
            "evidence_type": self.evidence_type,
            "fact_source": self.fact_source,
            "source_artifact_id": self.source_artifact_id,
            "source_ref": self.source_ref,
            "confidence": self.confidence,
            "reason": self.reason,
            "conflict_group": self.conflict_group,
        }


@dataclass
class BacktestEvidence:
    artifact_id: str
    relative_path: str
    strategy: str = "UNKNOWN"
    symbol: str = "UNKNOWN"
    timeframe: str = "UNKNOWN"
    model: str = "UNKNOWN"
    date_range: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    parser_confidence: str = "LOW"
    association_confidence: str = "NONE"
    robot_id: str = ""
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path,
            "robot_id": self.robot_id or None,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "model": self.model,
            "date_range": _bounded(self.date_range),
            "parameters": _bounded(self.parameters),
            "metrics": _bounded(self.metrics),
            "parser_confidence": self.parser_confidence,
            "association_confidence": self.association_confidence,
            "provenance": list(self.provenance),
        }


@dataclass
class RobotRecord:
    robot_id: str
    name: str
    version: str = "UNKNOWN"
    status: str = "DISCOVERED"
    source_artifacts: list[dict[str, Any]] = field(default_factory=list)
    compiled_artifacts: list[dict[str, Any]] = field(default_factory=list)
    parameter_presets: list[dict[str, Any]] = field(default_factory=list)
    documentation_artifacts: list[dict[str, Any]] = field(default_factory=list)
    backtest_artifacts: list[dict[str, Any]] = field(default_factory=list)
    optimization_artifacts: list[dict[str, Any]] = field(default_factory=list)
    strategy_family: str = "UNKNOWN"
    supported_symbols: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=list)
    entry_logic_summary: str = "UNKNOWN"
    exit_logic_summary: str = "UNKNOWN"
    risk_model: str = "UNKNOWN"
    position_sizing_model: str = "UNKNOWN"
    stop_loss_behavior: str = "UNKNOWN"
    take_profit_behavior: str = "UNKNOWN"
    trailing_behavior: str = "UNKNOWN"
    grid_usage: str = "UNKNOWN"
    martingale_usage: str = "UNKNOWN"
    hedging_usage: str = "UNKNOWN"
    maximum_positions: Any = "UNKNOWN"
    required_indicators: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    preferred_market_regime: str = "UNKNOWN"
    avoided_market_regime: str = "UNKNOWN"
    session_preferences: str = "UNKNOWN"
    spread_constraints: str = "UNKNOWN"
    news_event_restrictions: str = "UNKNOWN"
    known_failures: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    forward_evidence: str = "NONE"
    live_evidence: str = "NONE"
    discovered_at: float = 0.0
    last_seen_at: float = 0.0
    last_reviewed_at: float = 0.0
    provenance: list[EvidenceClaim] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    user_overrides: list[dict[str, Any]] = field(default_factory=list)
    artifact_role: str = "UNKNOWN"

    def to_dict(self, detail: bool = False) -> dict[str, Any]:
        data = {
            "robot_id": self.robot_id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "artifact_role": self.artifact_role,
            "source_available": bool(self.source_artifacts),
            "compiled_available": bool(self.compiled_artifacts),
            "source_artifacts": list(self.source_artifacts),
            "compiled_artifacts": list(self.compiled_artifacts),
            "parameter_presets": list(self.parameter_presets),
            "documentation_artifacts": list(self.documentation_artifacts),
            "backtest_count": len(self.backtest_artifacts),
            "optimization_evidence": bool(self.optimization_artifacts),
            "forward_evidence": self.forward_evidence,
            "live_evidence": self.live_evidence,
            "strategy_family": self.strategy_family,
            "evidence_summary": self.evidence_summary(),
            "known_limitations": list(dict.fromkeys(self.known_limitations)),
            "conflicts": list(self.conflicts),
            "last_reviewed_at": self.last_reviewed_at,
        }
        if detail:
            data.update({
                "backtest_artifacts": list(self.backtest_artifacts),
                "optimization_artifacts": list(self.optimization_artifacts),
                "supported_symbols": list(self.supported_symbols),
                "supported_timeframes": list(self.supported_timeframes),
                "entry_logic_summary": self.entry_logic_summary,
                "exit_logic_summary": self.exit_logic_summary,
                "risk_model": self.risk_model,
                "position_sizing_model": self.position_sizing_model,
                "stop_loss_behavior": self.stop_loss_behavior,
                "take_profit_behavior": self.take_profit_behavior,
                "trailing_behavior": self.trailing_behavior,
                "grid_usage": self.grid_usage,
                "martingale_usage": self.martingale_usage,
                "hedging_usage": self.hedging_usage,
                "maximum_positions": self.maximum_positions,
                "required_indicators": list(self.required_indicators),
                "dependencies": list(self.dependencies),
                "preferred_market_regime": self.preferred_market_regime,
                "avoided_market_regime": self.avoided_market_regime,
                "session_preferences": self.session_preferences,
                "spread_constraints": self.spread_constraints,
                "news_event_restrictions": self.news_event_restrictions,
                "known_failures": list(self.known_failures),
                "discovered_at": self.discovered_at,
                "last_seen_at": self.last_seen_at,
                "provenance": [claim.to_dict() for claim in self.provenance],
                "user_overrides": list(self.user_overrides),
                "what_we_know": self._what_we_know(),
                "why_we_think": [claim.to_dict() for claim in self.provenance],
                "what_we_do_not_know": list(dict.fromkeys(self.known_limitations)),
                "what_conflicts": list(self.conflicts),
                "what_user_overrides_exist": list(self.user_overrides),
            })
        return data

    def evidence_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for claim in self.provenance:
            summary[claim.evidence_type] = summary.get(claim.evidence_type, 0) + 1
        return summary

    def _what_we_know(self) -> list[str]:
        known = []
        if self.source_artifacts:
            known.append("source artifact observed")
        if self.compiled_artifacts:
            known.append("compiled artifact observed")
        if self.parameter_presets:
            known.append("parameter preset observed")
        if self.backtest_artifacts:
            known.append("backtest artifact parsed")
        if self.strategy_family not in {"UNKNOWN", "CONFLICT"}:
            known.append("strategy family: " + self.strategy_family)
        return known or ["identity observed, details remain unknown"]


@dataclass
class DiscoveryReport:
    scanned_at: float
    roots: list[str]
    files_inspected: int = 0
    robots_discovered: int = 0
    source_backed: int = 0
    compiled_only: int = 0
    source_only: int = 0
    presets_found: int = 0
    backtest_artifacts_found: int = 0
    optimization_artifacts_found: int = 0
    backtests_associated: int = 0
    backtests_unassociated: int = 0
    conflicts: int = 0
    unknowns: int = 0
    unassociated_artifacts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": not self.errors,
            "read_only": True,
            "scanned_at": self.scanned_at,
            "roots": list(self.roots),
            "files_inspected": self.files_inspected,
            "robots_discovered": self.robots_discovered,
            "source_backed": self.source_backed,
            "compiled_only": self.compiled_only,
            "source_only": self.source_only,
            "presets_found": self.presets_found,
            "backtest_artifacts_found": self.backtest_artifacts_found,
            "optimization_artifacts_found": self.optimization_artifacts_found,
            "backtests_associated": self.backtests_associated,
            "backtests_unassociated": self.backtests_unassociated,
            "conflicts": self.conflicts,
            "unknowns": self.unknowns,
            "unassociated_artifacts": list(self.unassociated_artifacts),
            "errors": list(self.errors),
        }


def _artifact(path: Path, root: Path, kind: str, confidence: str = "NONE") -> RobotArtifact:
    stat = path.stat()
    digest = _sha256(path)
    artifact_id = hashlib.sha256((kind + ":" + digest).encode("ascii")).hexdigest()
    return RobotArtifact(
        artifact_id=artifact_id,
        kind=kind,
        relative_path=path.relative_to(root).as_posix(),
        root_label=root.name,
        sha256=digest,
        size=int(stat.st_size),
        modified_at=float(stat.st_mtime),
        association_confidence=confidence,
    )


def _include_file(path: Path, root: Path) -> bool:
    extension = path.suffix.casefold()
    if extension not in TRACKED_EXTENSIONS:
        return False
    parts = {part.casefold() for part in path.relative_to(root).parts}
    if parts & EXCLUDED_PATH_MARKERS:
        return False
    name = path.name.casefold()
    normalized = _normal_key(path.stem)
    if extension in SOURCE_EXTENSIONS | COMPILED_EXTENSIONS | PRESET_EXTENSIONS:
        return True
    if root.name.casefold() == "backtest_results":
        return extension in BACKTEST_EXTENSIONS
    return any(keyword in name or keyword in normalized for keyword in DISCOVERY_KEYWORDS)


def _iter_files(roots: Iterable[Path]) -> Iterable[tuple[Path, Path]]:
    for root in roots:
        root = Path(root).resolve()
        if not root.exists() or not root.is_dir():
            continue
        for current, directories, files in os.walk(root, topdown=True, followlinks=False):
            directories[:] = [name for name in directories
                              if name.casefold() not in EXCLUDED_DIRECTORY_NAMES]
            current_path = Path(current)
            for name in sorted(files, key=str.casefold):
                path = current_path / name
                if _include_file(path, root):
                    yield path, root


def _source_role(content: str) -> str:
    if re.search(r"\bOnTick\s*\(", content) or "CTrade" in content:
        return "EA"
    if re.search(r"\bOnCalculate\s*\(", content):
        return "INDICATOR"
    if re.search(r"\bOnStart\s*\(", content):
        return "SCRIPT"
    return "UNKNOWN"


def _family_for(name: str, content: str = "") -> str:
    value = (name + " " + content[:30000]).casefold()
    if any(token in value for token in ("breakout", "rompimento", "range")):
        return "BREAKOUT"
    if "pullback" in value:
        return "PULLBACK"
    if "turtle" in value:
        return "TREND_FOLLOWING"
    if "vwap" in value:
        return "VWAP"
    if any(token in value for token in ("trend", "tendencia", "ema", "media")):
        return "TREND_FOLLOWING"
    return "UNKNOWN"


def _claim_value(value: Any) -> str:
    return json.dumps(_bounded(value), sort_keys=True, ensure_ascii=True)


class RobotCatalogReadModel:
    """Canonical in-process catalog owner for the first read-only gate."""

    CATALOG_VERSION = 1

    def __init__(self, workspace_root: Optional[Path | str] = None,
                 approved_roots: Optional[Iterable[Path | str]] = None):
        self._lock = threading.RLock()
        self.workspace_root = Path(workspace_root or Path(__file__).resolve().parents[3]).resolve()
        self.approved_roots = tuple(Path(root).resolve() for root in (
            approved_roots or default_approved_roots(self.workspace_root)))
        self._robots: dict[str, RobotRecord] = {}
        self._user_overrides: dict[str, dict[str, Any]] = {}
        self._last_report: Optional[DiscoveryReport] = None

    def discover(self, roots: Optional[Iterable[Path | str]] = None) -> dict[str, Any]:
        """Perform one bounded, read-only scan and replace only discovered facts."""
        with self._lock:
            selected_roots = tuple(Path(root).resolve() for root in (roots or self.approved_roots))
            now = time.time()
            report = DiscoveryReport(
                scanned_at=now,
                roots=[str(root) for root in selected_roots],
            )
            previous = self._robots
            robots: dict[str, RobotRecord] = {}
            source_by_stem: dict[str, list[RobotRecord]] = {}
            compiled_by_stem: dict[str, list[RobotRecord]] = {}
            pending: list[tuple[RobotArtifact, Path, Path]] = []

            for path, root in _iter_files(selected_roots):
                try:
                    extension = path.suffix.casefold()
                    if extension in SOURCE_EXTENSIONS:
                        artifact = _artifact(path, root, "SOURCE")
                    elif extension in COMPILED_EXTENSIONS:
                        artifact = _artifact(path, root, "COMPILED")
                    elif extension in PRESET_EXTENSIONS:
                        artifact = _artifact(path, root, "PRESET")
                    elif extension in BACKTEST_EXTENSIONS and (
                            root.name.casefold() == "backtest_results" or
                            any(marker in path.name.casefold()
                                for marker in ("backtest", "optimization", "otimiz"))):
                        kind = "OPTIMIZATION" if "optimization" in path.name.casefold() or "otimiz" in path.name.casefold() else "BACKTEST"
                        artifact = _artifact(path, root, kind)
                    else:
                        artifact = _artifact(path, root, "DOCUMENTATION")
                    pending.append((artifact, path, root))
                    report.files_inspected += 1
                except (OSError, ValueError) as exc:
                    report.errors.append({"path": str(path), "error": type(exc).__name__})

            def add_robot(robot_id: str, name: str, role: str) -> RobotRecord:
                record = robots.get(robot_id)
                if record is None:
                    old = previous.get(robot_id)
                    record = RobotRecord(
                        robot_id=robot_id, name=name, artifact_role=role,
                        discovered_at=(old.discovered_at if old else now), last_seen_at=now,
                    )
                    robots[robot_id] = record
                else:
                    record.last_seen_at = now
                if record.artifact_role == "UNKNOWN" and role != "UNKNOWN":
                    record.artifact_role = role
                return record

            for artifact, path, root in pending:
                if artifact.kind != "SOURCE":
                    continue
                try:
                    content = _text(path)
                    role = _source_role(content)
                    robot_id = "robot_" + hashlib.sha256(
                        ("source:" + artifact.sha256).encode("ascii")).hexdigest()[:24]
                    record = add_robot(robot_id, _human_name(path.stem), role)
                    item = artifact.to_dict()
                    record.source_artifacts.append(item)
                    record.version = _match(r"#property\s+version\s+['\"]([^'\"]+)", content) or record.version
                    record.strategy_family = record.strategy_family if record.strategy_family != "UNKNOWN" else _family_for(path.stem, content)
                    self._claim(record, "source_available", True, "ARTIFACT_OBSERVED",
                                "FACT_FROM_SOURCE", artifact, reason="MQL source inspected")
                    self._claim(record, "artifact_role", role, "SOURCE_VERIFIED",
                                "FACT_FROM_SOURCE", artifact, reason="lifecycle entrypoint observed")
                    if record.strategy_family != "UNKNOWN":
                        self._claim(record, "strategy_family", record.strategy_family,
                                    "JARVIS_INFERRED", "JARVIS_INFERENCE", artifact,
                                    reason="bounded name/content classification")
                    self._extract_source_claims(record, artifact, content)
                    source_by_stem.setdefault(_normal_key(path.stem), []).append(record)
                except (OSError, UnicodeError) as exc:
                    report.errors.append({"path": str(path), "error": type(exc).__name__})

            for artifact, path, root in pending:
                if artifact.kind != "COMPILED":
                    continue
                matches = source_by_stem.get(_normal_key(path.stem), [])
                if len(matches) == 1:
                    record = matches[0]
                    item = RobotArtifact(**{**artifact.__dict__, "association_confidence": "HIGH"}).to_dict()
                    record.compiled_artifacts.append(item)
                    self._claim(record, "compiled_available", True, "ARTIFACT_OBSERVED",
                                "FACT_FROM_SOURCE", artifact, reason="exact source/compiled stem match")
                else:
                    robot_id = "robot_" + hashlib.sha256(
                        ("compiled:" + artifact.sha256).encode("ascii")).hexdigest()[:24]
                    record = add_robot(robot_id, _human_name(path.stem), "COMPILED_ONLY")
                    record.compiled_artifacts.append(artifact.to_dict())
                    record.known_limitations.append("compiled artifact has no inspected source")
                    self._claim(record, "compiled_available", True, "ARTIFACT_OBSERVED",
                                "UNKNOWN", artifact, reason="compiled artifact observed without verified source")
                compiled_by_stem.setdefault(_normal_key(path.stem), []).append(record)

            for artifact, path, root in pending:
                if artifact.kind not in {"PRESET", "DOCUMENTATION"}:
                    continue
                matches = self._artifact_matches(path, root, source_by_stem,
                                                 compiled_by_stem, robots)
                if len(matches) == 1:
                    record = matches[0]
                    item = RobotArtifact(**{**artifact.__dict__, "association_confidence": "HIGH"}).to_dict()
                    if artifact.kind == "PRESET":
                        record.parameter_presets.append(item)
                        report.presets_found += 1
                        self._claim(record, "parameter_preset", artifact.relative_path,
                                    "CONFIG_VERIFIED", "FACT_FROM_SOURCE", artifact,
                                    reason="exact robot stem match")
                    else:
                        record.documentation_artifacts.append(item)
                        self._parse_documentation_claims(record, artifact, path)
                else:
                    report.unassociated_artifacts.append(artifact.to_dict())

            for artifact, path, root in pending:
                if artifact.kind not in {"BACKTEST", "OPTIMIZATION"}:
                    continue
                if artifact.kind == "OPTIMIZATION":
                    report.optimization_artifacts_found += 1
                else:
                    report.backtest_artifacts_found += 1
                parsed = self._parse_backtest(path, artifact)
                if parsed is None:
                    report.errors.append({"path": str(path), "error": "BACKTEST_PARSE_ERROR"})
                    continue
                strategy_key = _normal_key(parsed.strategy)
                matches = source_by_stem.get(strategy_key, []) or compiled_by_stem.get(strategy_key, [])
                if len(matches) == 1:
                    record = matches[0]
                    parsed.robot_id = record.robot_id
                    parsed.association_confidence = "HIGH"
                    record.backtest_artifacts.append(parsed.to_dict())
                    if artifact.kind == "OPTIMIZATION":
                        record.optimization_artifacts.append(parsed.to_dict())
                    report.backtests_associated += 1
                    self._claim(record, "backtest_evidence", artifact.relative_path,
                                "OPTIMIZATION_EVIDENCE" if artifact.kind == "OPTIMIZATION" else "BACKTEST_EVIDENCE",
                                "FACT_FROM_SOURCE", artifact,
                                reason="exact strategy stem match")
                else:
                    parsed.provenance.append({
                        "evidence_type": "UNKNOWN", "fact_source": "UNKNOWN",
                        "reason": "no deterministic robot association",
                    })
                    report.backtests_unassociated += 1
                    report.unassociated_artifacts.append(parsed.to_dict())

            for record in robots.values():
                record.source_artifacts = _unique_dicts(record.source_artifacts, "artifact_id")
                record.compiled_artifacts = _unique_dicts(record.compiled_artifacts, "artifact_id")
                record.parameter_presets = _unique_dicts(record.parameter_presets, "artifact_id")
                record.documentation_artifacts = _unique_dicts(record.documentation_artifacts, "artifact_id")
                record.backtest_artifacts = _unique_dicts(record.backtest_artifacts, "artifact_id")
                record.optimization_artifacts = _unique_dicts(record.optimization_artifacts, "artifact_id")
                record.status = self._status_for(record)
                record.known_limitations.extend((
                    "forward-test evidence: NONE",
                    "live evidence: NONE",
                ))
                if record.strategy_family == "UNKNOWN":
                    record.known_limitations.append("strategy family is UNKNOWN")
                report.conflicts += len(record.conflicts)
                report.unknowns += sum(1 for claim in record.provenance
                                       if claim.evidence_type == "UNKNOWN")
            report.unknowns += report.backtests_unassociated

            self._robots = robots
            report.robots_discovered = len(robots)
            report.source_backed = sum(bool(item.source_artifacts) for item in robots.values())
            report.compiled_only = sum(bool(item.compiled_artifacts) and not item.source_artifacts
                                       for item in robots.values())
            report.source_only = sum(bool(item.source_artifacts) and not item.compiled_artifacts
                                     for item in robots.values())
            self._last_report = report
            return {"ok": not report.errors, "report": report.to_dict(),
                    "robots": [item.to_dict() for item in self._sorted_robots()]}

    def list(self, status: str = "", limit: int = 100) -> dict[str, Any]:
        with self._lock:
            normalized = str(status or "").upper()
            items = [item.to_dict() for item in self._sorted_robots()
                     if not normalized or item.status == normalized]
            return {"ok": True, "read_only": True, "scanned": self._last_report is not None,
                    "robots": items[:max(1, min(int(limit), 500))],
                    "total": len(items)}

    def detail(self, robot_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._robots.get(str(robot_id))
            if record is None:
                return {"ok": False, "error": "ROBOT_NOT_FOUND", "robot_id": str(robot_id)}
            return {"ok": True, "read_only": True, "robot": record.to_dict(detail=True)}

    def set_user_status(self, robot_id: str, status: str, reason: str = "") -> dict[str, Any]:
        """Apply an explicit user decision without granting trade authority."""
        with self._lock:
            normalized = str(status or "").upper()
            if normalized not in LIFECYCLE_STATES:
                return {"ok": False, "error": "INVALID_ROBOT_STATUS", "allowed": list(LIFECYCLE_STATES)}
            record = self._robots.get(str(robot_id))
            if record is None:
                return {"ok": False, "error": "ROBOT_NOT_FOUND", "robot_id": str(robot_id)}
            override = {
                "field": "status", "value": normalized, "authority": "USER_OVERRIDE",
                "evidence_type": "USER_DEFINED", "fact_source": "USER_ASSERTION",
                "reason": str(reason or "explicit user decision")[:500], "updated_at": time.time(),
            }
            self._user_overrides[str(robot_id)] = override
            record.status = normalized
            record.user_overrides = [override]
            return {"ok": True, "robot": record.to_dict(detail=True)}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "read_only": True,
                "catalog_version": self.CATALOG_VERSION,
                "persistence": "IN_MEMORY_READ_MODEL",
                "schema_migration": "NOT_REQUIRED",
                "trade_authority": "NONE",
                "scanned": self._last_report is not None,
                "report": self._last_report.to_dict() if self._last_report else None,
                "robots": [item.to_dict() for item in self._sorted_robots()],
            }

    def _sorted_robots(self) -> list[RobotRecord]:
        return sorted(self._robots.values(), key=lambda item: (item.name.casefold(), item.robot_id))

    @staticmethod
    def _artifact_matches(path: Path, root: Path,
                          source_by_stem: dict[str, list[RobotRecord]],
                          compiled_by_stem: dict[str, list[RobotRecord]],
                          robots: dict[str, RobotRecord]) -> list[RobotRecord]:
        exact = source_by_stem.get(_normal_key(path.stem), [])
        exact = exact or compiled_by_stem.get(_normal_key(path.stem), [])
        if exact:
            unique = {}
            for record in exact:
                unique[record.robot_id] = record
            return list(unique.values())
        try:
            parent = PurePosixPath(path.relative_to(root).as_posix()).parent
        except ValueError:
            return []
        matches = []
        for record in robots.values():
            artifacts = record.source_artifacts + record.compiled_artifacts
            if any(item.get("root") == root.name and
                   PurePosixPath(item.get("relative_path", "")).parent == parent
                   for item in artifacts):
                matches.append(record)
        unique = {}
        for record in matches:
            unique[record.robot_id] = record
        return list(unique.values())

    def _status_for(self, record: RobotRecord) -> str:
        override = self._user_overrides.get(record.robot_id)
        if override:
            record.user_overrides = [dict(override)]
            return str(override["value"])
        if any(marker in _normal_key(record.name) for marker in ARCHIVED_NAME_MARKERS):
            return "ARCHIVED"
        return "CANDIDATE" if record.artifact_role == "EA" else "DISCOVERED"

    @staticmethod
    def _claim(record: RobotRecord, field: str, value: Any, evidence_type: str,
               fact_source: str, artifact: Optional[RobotArtifact] = None,
               reason: str = "", source_ref: str = "") -> None:
        if evidence_type not in EVIDENCE_TYPES:
            evidence_type = "UNKNOWN"
        if fact_source not in FACT_SOURCES:
            fact_source = "UNKNOWN"
        artifact_id = artifact.artifact_id if artifact else ""
        source_ref = source_ref or (artifact.relative_path if artifact else "")
        conflict_group = ""
        prior = [] if field in MULTI_VALUE_CLAIMS else [
            claim for claim in record.provenance
            if claim.field == field and _claim_value(claim.value) != _claim_value(value)
        ]
        if prior:
            conflict_group = hashlib.sha256((record.robot_id + ":" + field).encode("utf-8")).hexdigest()[:16]
            for claim in prior:
                claim.conflict_group = conflict_group
            record.conflicts.append({
                "field": field, "conflict_group": conflict_group,
                "claims": [claim.claim_id for claim in prior],
                "new_value": _bounded(value),
            })
            if hasattr(record, field) and not isinstance(getattr(record, field), list):
                setattr(record, field, "CONFLICT")
        claim_id = hashlib.sha256((record.robot_id + field + _claim_value(value) + source_ref).encode("utf-8")).hexdigest()[:24]
        record.provenance.append(EvidenceClaim(
            claim_id=claim_id, field=field, value=_bounded(value),
            evidence_type=evidence_type, fact_source=fact_source,
            source_artifact_id=artifact_id, source_ref=source_ref,
            confidence="HIGH" if evidence_type in {"SOURCE_VERIFIED", "CONFIG_VERIFIED", "BACKTEST_EVIDENCE", "ARTIFACT_OBSERVED"} else "MEDIUM",
            reason=reason, conflict_group=conflict_group,
        ))

    @classmethod
    def _extract_source_claims(cls, record: RobotRecord, artifact: RobotArtifact, content: str) -> None:
        symbols = sorted(set(re.findall(r"(?:Simbolo|Symbol)[^=;]*=\s*[\"']([^\"']+)", content, re.I)))
        timeframes = sorted(set(re.findall(r"PERIOD_([A-Z0-9]+)", content)))
        for symbol in symbols:
            if symbol not in record.supported_symbols:
                record.supported_symbols.append(symbol)
        for timeframe in timeframes:
            value = "PERIOD_" + timeframe
            if value not in record.supported_timeframes:
                record.supported_timeframes.append(value)
        if symbols:
            cls._claim(record, "supported_symbols", symbols, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="symbol input declaration observed")
        if timeframes:
            cls._claim(record, "supported_timeframes", timeframes, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="timeframe declaration observed")
        if re.search(r"\b(CTrade|OrderSend|Buy\(|Sell\(|OnTick)\b", content):
            record.entry_logic_summary = "DECLARED_IN_SOURCE"
            cls._claim(record, "entry_logic_summary", record.entry_logic_summary, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="EA execution entrypoint observed; details require review")
        if re.search(r"StopLoss|stop.?loss|STOP_", content, re.I):
            record.stop_loss_behavior = "DECLARED_IN_SOURCE"
            cls._claim(record, "stop_loss_behavior", record.stop_loss_behavior, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="stop-loss declaration observed")
        if re.search(r"TakeProfit|take.?profit|TAKE_", content, re.I):
            record.take_profit_behavior = "DECLARED_IN_SOURCE"
            cls._claim(record, "take_profit_behavior", record.take_profit_behavior, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="take-profit declaration observed")
        if re.search(r"Trailing|trailing", content, re.I):
            record.trailing_behavior = "DECLARED_IN_SOURCE"
            cls._claim(record, "trailing_behavior", record.trailing_behavior, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="trailing declaration observed")
        if re.search(r"risk|risco|percentual", content, re.I):
            record.risk_model = "DECLARED_IN_SOURCE"
            cls._claim(record, "risk_model", record.risk_model, "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="risk-related input or logic observed")
        max_positions = _match(r"(?:MaximoDeOperacoesAbertas|MaxPositions)\s*=\s*(\d+)", content)
        if max_positions:
            record.maximum_positions = int(max_positions)
            cls._claim(record, "maximum_positions", int(max_positions), "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                       reason="maximum open positions input observed")
        for marker, field_name in (("martingale", "martingale_usage"), ("grid", "grid_usage"), ("hedg", "hedging_usage")):
            if marker in content.casefold():
                setattr(record, field_name, "MENTIONED_IN_SOURCE")
                cls._claim(record, field_name, getattr(record, field_name), "SOURCE_VERIFIED", "FACT_FROM_SOURCE", artifact,
                           reason="keyword observed; behavior not inferred")

    @classmethod
    def _parse_documentation_claims(cls, record: RobotRecord, artifact: RobotArtifact, path: Path) -> None:
        try:
            content = _text(path, limit=500_000)
        except OSError:
            return
        family = _match(r"(?:strategy[_ ]?family|familia[_ ]?estrategia)\s*[:=]\s*([A-Za-z0-9 _-]+)", content)
        if family:
            family = _normal_key(family).upper()
            cls._claim(record, "strategy_family", family, "DOCUMENTATION_VERIFIED",
                       "FACT_FROM_DOCUMENTATION", artifact, reason="explicit documentation claim")
            if record.strategy_family == "UNKNOWN":
                record.strategy_family = family
            elif record.strategy_family != family:
                record.strategy_family = "CONFLICT"

    @staticmethod
    def _parse_backtest(path: Path, artifact: RobotArtifact) -> Optional[BacktestEvidence]:
        try:
            data = json.loads(_text(path, limit=8_000_000))
            if not isinstance(data, dict):
                return None
        except (OSError, json.JSONDecodeError, UnicodeError):
            return None
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else data
        strategy = str(stats.get("strategy") or data.get("strategy") or "UNKNOWN")
        metrics = {}
        for target, keys in {
            "initial_deposit": ("initial_deposit", "initial_balance"),
            "profit": ("profit", "total_pnl", "total_profit"),
            "gross_profit": ("gross_profit",), "gross_loss": ("gross_loss",),
            "drawdown": ("drawdown", "max_drawdown"),
            "relative_drawdown": ("relative_drawdown",), "trades": ("trades", "total_trades"),
            "win_rate": ("win_rate",), "profit_factor": ("profit_factor",),
            "expected_payoff": ("expected_payoff",), "sharpe": ("sharpe",),
        }.items():
            for key in keys:
                if key in stats:
                    metrics[target] = _bounded(stats[key])
                    break
        date_range = {key: _bounded(stats[key]) for key in ("period_start", "period_end", "period_days") if key in stats}
        return BacktestEvidence(
            artifact_id=artifact.artifact_id,
            relative_path=artifact.relative_path,
            strategy=strategy,
            symbol=str(stats.get("symbol") or "UNKNOWN"),
            timeframe=str(stats.get("timeframe") or "UNKNOWN"),
            model=str(stats.get("model") or "UNKNOWN"),
            date_range=date_range,
            parameters=_bounded(data.get("parameters") if isinstance(data.get("parameters"), dict) else {}),
            metrics=metrics,
            parser_confidence="HIGH" if "stats" in data else "MEDIUM",
            provenance=[{
                "evidence_type": "OPTIMIZATION_EVIDENCE" if artifact.kind == "OPTIMIZATION" else "BACKTEST_EVIDENCE",
                "fact_source": "TEST_RESULT", "source_ref": artifact.relative_path,
            }],
        )


def _match(pattern: str, content: str) -> str:
    found = re.search(pattern, content, re.I)
    return found.group(1).strip() if found else ""


def _unique_dicts(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        marker = item.get(key) or json.dumps(item, sort_keys=True, ensure_ascii=True)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


__all__ = [
    "EVIDENCE_TYPES", "FACT_SOURCES", "LIFECYCLE_STATES", "BacktestEvidence",
    "DiscoveryReport", "EvidenceClaim", "RobotArtifact", "RobotCatalogReadModel",
    "RobotRecord", "default_approved_roots",
]
