"""Golden robot catalog, provenance model, and subordinate operational store.

The catalog deliberately stays in Jarvis Core and keeps discovery separate
from trading, MT5, Strategy Tester, and durable memory writes. Its subordinate
SQLite store owns only catalog state, evidence, and association history.
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
import sqlite3


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
ASSOCIATION_STATUSES = (
    "VERIFIED", "HIGH_CONFIDENCE", "AMBIGUOUS", "UNRESOLVED", "CONFLICTING"
)
CATALOG_SCHEMA_VERSION = 1

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


def _parameter_fingerprint(parameters: dict[str, Any]) -> str:
    normalized = json.dumps(sorted((str(key).casefold(), _bounded(value))
                                   for key, value in parameters.items()),
                            separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def parameter_fingerprint(parameters: dict[str, Any]) -> str:
    """Public canonical fingerprint shared by catalog and evidence contracts."""
    return _parameter_fingerprint(parameters)


def _logical_robot_id(name: str, version: str, role: str) -> str:
    """Keep executable identity independent from path and content revisions."""
    material = ":".join((_normal_key(name), str(version or "UNKNOWN"),
                          str(role or "UNKNOWN").upper()))
    return "robot_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _merge_identity_items(existing: list[dict[str, Any]], incoming: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    merged = list(existing or [])
    positions = {str(item.get(key) or ""): index for index, item in enumerate(merged)}
    for item in incoming or []:
        candidate = _bounded(dict(item))
        identity = str(candidate.get(key) or "")
        if not identity:
            raise ValueError(f"{key.upper()}_REQUIRED")
        if identity in positions:
            prior = merged[positions[identity]]
            if key == "sha256" and prior.get("sha256") != candidate.get("sha256"):
                raise ValueError("IDENTITY_COLLISION")
            merged[positions[identity]] = {**prior, **candidate}
        else:
            positions[identity] = len(merged)
            merged.append(candidate)
    return merged


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
    association_status: str = "UNRESOLVED"
    robot_id: str = ""
    candidate_robot_ids: list[str] = field(default_factory=list)
    association_signals: list[str] = field(default_factory=list)
    association_reason: str = ""
    identity_hints: list[str] = field(default_factory=list)
    parameter_fingerprint: str = ""
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "relative_path": self.relative_path,
            "robot_id": self.robot_id or None,
            "candidate_robot_ids": list(self.candidate_robot_ids),
            "association_status": self.association_status,
            "association_signals": list(self.association_signals),
            "association_reason": self.association_reason,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "model": self.model,
            "date_range": _bounded(self.date_range),
            "parameters": _bounded(self.parameters),
            "parameter_fingerprint": self.parameter_fingerprint,
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
    classification: str = "UNKNOWN"
    campaign_associations: list[dict[str, Any]] = field(default_factory=list)
    temporal_contexts: list[dict[str, Any]] = field(default_factory=list)
    source_artifacts: list[dict[str, Any]] = field(default_factory=list)
    compiled_artifacts: list[dict[str, Any]] = field(default_factory=list)
    parameter_presets: list[dict[str, Any]] = field(default_factory=list)
    parameter_sets: list[dict[str, Any]] = field(default_factory=list)
    aliases: list[dict[str, Any]] = field(default_factory=list)
    compile_evidence: list[dict[str, Any]] = field(default_factory=list)
    test_runs: list[dict[str, Any]] = field(default_factory=list)
    latest_test_status: str = "NOT_PRESENT"
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
            "classification": self.classification,
            "artifact_role": self.artifact_role,
            "source_available": bool(self.source_artifacts),
            "compiled_available": bool(self.compiled_artifacts),
            "source_artifacts": list(self.source_artifacts),
            "compiled_artifacts": list(self.compiled_artifacts),
            "parameter_presets": list(self.parameter_presets),
            "parameter_set_count": len(self.parameter_sets),
            "compile_evidence_count": len(self.compile_evidence),
            "test_run_count": len(self.test_runs),
            "latest_test_status": self.latest_test_status,
            "test_runs": list(self.test_runs),
            "backtest_artifacts": list(self.backtest_artifacts),
            "campaign_associations": list(self.campaign_associations),
            "temporal_contexts": list(self.temporal_contexts),
            "aliases": list(self.aliases),
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
                "campaign_associations": list(self.campaign_associations),
                "temporal_contexts": list(self.temporal_contexts),
                "supported_symbols": list(self.supported_symbols),
                "supported_timeframes": list(self.supported_timeframes),
                "parameter_sets": list(self.parameter_sets),
                "compile_evidence": list(self.compile_evidence),
                "test_runs": list(self.test_runs),
                "latest_test_status": self.latest_test_status,
                "aliases": list(self.aliases),
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
    backtests_verified: int = 0
    backtests_high_confidence: int = 0
    backtests_ambiguous: int = 0
    backtests_unresolved: int = 0
    backtests_conflicting: int = 0
    association_examples: list[dict[str, Any]] = field(default_factory=list)
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
            "association_counts": {
                "VERIFIED": self.backtests_verified,
                "HIGH_CONFIDENCE": self.backtests_high_confidence,
                "AMBIGUOUS": self.backtests_ambiguous,
                "UNRESOLVED": self.backtests_unresolved,
                "CONFLICTING": self.backtests_conflicting,
            },
            "association_examples": list(self.association_examples),
            "conflicts": self.conflicts,
            "unknowns": self.unknowns,
            "unassociated_artifacts": list(self.unassociated_artifacts),
            "errors": list(self.errors),
        }


def default_catalog_store_path(workspace_root: Optional[Path | str] = None) -> Path:
    root = Path(workspace_root or Path(__file__).resolve().parents[3]).resolve()
    return root / "studio" / "golden_ai_studio_web" / "jarvis" / "robot_catalog.db"


class RobotCatalogStore:
    """Persistence owner for catalog state; independent from memory/tasks/audit DBs."""

    def __init__(self, path: Path | str):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        connection = self._connection
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS catalog_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS robot_records (
                robot_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS robot_overrides (
                robot_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS robot_artifacts (
                artifact_id TEXT PRIMARY KEY,
                robot_id TEXT,
                kind TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                current_path TEXT NOT NULL,
                path_history_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS robot_associations (
                artifact_id TEXT PRIMARY KEY,
                robot_id TEXT,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS catalog_scan_runs (
                scan_id TEXT PRIMARY KEY,
                started_at REAL NOT NULL,
                completed_at REAL NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS catalog_evidence (
                evidence_id TEXT PRIMARY KEY,
                robot_id TEXT,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        row = connection.execute(
            "SELECT value FROM catalog_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO catalog_meta(key, value) VALUES('schema_version', ?)",
                (str(CATALOG_SCHEMA_VERSION),),
            )
        elif int(row["value"]) != CATALOG_SCHEMA_VERSION:
            raise RuntimeError("ROBOT_CATALOG_SCHEMA_VERSION_UNSUPPORTED")
        connection.commit()

    def load(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], Optional[dict[str, Any]]]:
        records = {
            row["robot_id"]: json.loads(row["payload_json"])
            for row in self._connection.execute("SELECT robot_id, payload_json FROM robot_records")
        }
        overrides = {
            row["robot_id"]: json.loads(row["payload_json"])
            for row in self._connection.execute("SELECT robot_id, payload_json FROM robot_overrides")
        }
        row = self._connection.execute(
            "SELECT payload_json FROM catalog_scan_runs ORDER BY completed_at DESC LIMIT 1"
        ).fetchone()
        return records, overrides, (json.loads(row["payload_json"]) if row else None)

    def save_override(self, robot_id: str, override: dict[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO robot_overrides(robot_id, payload_json, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(robot_id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at",
            (robot_id, json.dumps(override, ensure_ascii=True), float(override.get("updated_at", time.time()))),
        )
        self._connection.commit()

    def save_scan(self, records: dict[str, "RobotRecord"], report: "DiscoveryReport") -> None:
        now = time.time()
        with self._connection:
            for record in records.values():
                payload = record.to_dict(detail=True)
                self._connection.execute(
                    "INSERT INTO robot_records(robot_id, payload_json, first_seen_at, last_seen_at, updated_at) "
                    "VALUES(?, ?, ?, ?, ?) ON CONFLICT(robot_id) DO UPDATE SET payload_json=excluded.payload_json, "
                    "last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at",
                    (record.robot_id, json.dumps(payload, ensure_ascii=True), record.discovered_at,
                     record.last_seen_at, now),
                )
                for artifact in (record.source_artifacts + record.compiled_artifacts +
                                 record.parameter_presets + record.documentation_artifacts +
                                 record.backtest_artifacts + record.optimization_artifacts):
                    self._save_artifact(record.robot_id, artifact, now)
                for backtest in record.backtest_artifacts + record.optimization_artifacts:
                    self._connection.execute(
                        "INSERT INTO robot_associations(artifact_id, robot_id, status, payload_json, updated_at) "
                        "VALUES(?, ?, ?, ?, ?) ON CONFLICT(artifact_id) DO UPDATE SET robot_id=excluded.robot_id, "
                        "status=excluded.status, payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                        (backtest["artifact_id"], record.robot_id,
                         backtest.get("association_status", "UNRESOLVED"),
                         json.dumps(backtest, ensure_ascii=True), now),
                    )
            for item in report.unassociated_artifacts:
                artifact_id = item.get("artifact_id")
                if not artifact_id:
                    continue
                payload = dict(item)
                payload.setdefault("kind", "BACKTEST")
                payload.setdefault("sha256", "")
                payload.setdefault("relative_path", "")
                self._save_artifact("", payload, now)
                self._connection.execute(
                    "INSERT INTO robot_associations(artifact_id, robot_id, status, payload_json, updated_at) "
                    "VALUES(?, NULL, ?, ?, ?) ON CONFLICT(artifact_id) DO UPDATE SET robot_id=NULL, "
                    "status=excluded.status, payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                    (artifact_id, item.get("association_status", "UNRESOLVED"),
                     json.dumps(item, ensure_ascii=True), now),
                )
            report_payload = report.to_dict()
            scan_id = hashlib.sha256((str(report.scanned_at) + json.dumps(report_payload, sort_keys=True)).encode()).hexdigest()[:32]
            self._connection.execute(
                "INSERT OR REPLACE INTO catalog_scan_runs(scan_id, started_at, completed_at, payload_json) VALUES(?, ?, ?, ?)",
                (scan_id, report.scanned_at, now, json.dumps(report_payload, ensure_ascii=True)),
            )

    def _save_artifact(self, robot_id: str, artifact: dict[str, Any], now: float) -> None:
        row = self._connection.execute(
            "SELECT path_history_json, first_seen_at FROM robot_artifacts WHERE artifact_id = ?",
            (artifact["artifact_id"],),
        ).fetchone()
        history = json.loads(row["path_history_json"]) if row else []
        current_path = str(artifact.get("relative_path", ""))
        if current_path and current_path not in history:
            history.append(current_path)
        self._connection.execute(
            "INSERT INTO robot_artifacts(artifact_id, robot_id, kind, sha256, current_path, path_history_json, payload_json, first_seen_at, last_seen_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(artifact_id) DO UPDATE SET robot_id=excluded.robot_id, "
            "current_path=excluded.current_path, path_history_json=excluded.path_history_json, payload_json=excluded.payload_json, "
            "last_seen_at=excluded.last_seen_at",
            (artifact["artifact_id"], robot_id, artifact.get("kind", "UNKNOWN"), artifact.get("sha256", ""),
             current_path, json.dumps(history, ensure_ascii=True), json.dumps(artifact, ensure_ascii=True),
             row["first_seen_at"] if row else now, now),
        )

    def save_production_association(self, record: "RobotRecord",
                                    evidence_items: list[dict[str, Any]]) -> None:
        """Atomically persist a production association through the catalog owner."""
        now = time.time()
        with self._connection:
            self._connection.execute(
                "INSERT INTO robot_records(robot_id, payload_json, first_seen_at, last_seen_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?) ON CONFLICT(robot_id) DO UPDATE SET payload_json=excluded.payload_json, "
                "last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at",
                (record.robot_id, json.dumps(record.to_dict(detail=True), ensure_ascii=True),
                 record.discovered_at or now, record.last_seen_at or now, now),
            )
            for artifact in (record.source_artifacts + record.compiled_artifacts +
                             record.parameter_presets + record.backtest_artifacts):
                self._save_artifact(record.robot_id, artifact, now)
            for artifact in record.backtest_artifacts:
                self._connection.execute(
                    "INSERT INTO robot_associations(artifact_id, robot_id, status, payload_json, updated_at) "
                    "VALUES(?, ?, ?, ?, ?) ON CONFLICT(artifact_id) DO UPDATE SET robot_id=excluded.robot_id, "
                    "status=excluded.status, payload_json=excluded.payload_json, updated_at=excluded.updated_at",
                    (artifact["artifact_id"], record.robot_id,
                     artifact.get("association_status", "VERIFIED"),
                     json.dumps(artifact, ensure_ascii=True), now),
                )
            for item in evidence_items:
                evidence_id = str(item.get("evidence_id") or item.get("test_run_id") or "")
                if not evidence_id:
                    raise ValueError("EVIDENCE_ID_REQUIRED")
                self._connection.execute(
                    "INSERT INTO catalog_evidence(evidence_id, robot_id, kind, status, payload_json, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(evidence_id) DO UPDATE SET robot_id=excluded.robot_id, "
                    "kind=excluded.kind, status=excluded.status, payload_json=excluded.payload_json",
                    (evidence_id, record.robot_id, "TEST_RUN",
                     str(item.get("status") or "HISTORICAL_PRODUCTION_EVIDENCE"),
                     json.dumps(_bounded(item), ensure_ascii=True), now),
                )

    def history_counts(self) -> dict[str, int]:
        return {
            "robots": int(self._connection.execute("SELECT COUNT(*) FROM robot_records").fetchone()[0]),
            "artifacts": int(self._connection.execute("SELECT COUNT(*) FROM robot_artifacts").fetchone()[0]),
            "scan_runs": int(self._connection.execute("SELECT COUNT(*) FROM catalog_scan_runs").fetchone()[0]),
        }

    def artifact_history(self, artifact_id: str) -> list[str]:
        row = self._connection.execute(
            "SELECT path_history_json FROM robot_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        return json.loads(row["path_history_json"]) if row else []

    def save_evidence(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        evidence_id = str(payload.get("evidence_id") or payload.get("test_run_id") or "")
        if not evidence_id:
            raise ValueError("EVIDENCE_ID_REQUIRED")
        now = time.time()
        with self._connection:
            self._connection.execute(
                "INSERT INTO catalog_evidence(evidence_id, robot_id, kind, status, payload_json, created_at) "
                "VALUES(?, ?, ?, ?, ?, ?) ON CONFLICT(evidence_id) DO UPDATE SET robot_id=excluded.robot_id, "
                "kind=excluded.kind, status=excluded.status, payload_json=excluded.payload_json",
                (evidence_id, payload.get("robot_id") or payload.get("identity", {}).get("robot_id"),
                 kind, str(payload.get("status") or payload.get("identity", {}).get("status") or "UNKNOWN"),
                 json.dumps(_bounded(payload), ensure_ascii=True), now),
            )
        return {"ok": True, "evidence_id": evidence_id, "kind": kind, "read_only": False}

    def evidence_for_robot(self, robot_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT kind, payload_json FROM catalog_evidence WHERE robot_id = ? ORDER BY created_at",
            (robot_id,),
        )
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.setdefault("evidence_kind", row["kind"])
            result.append(payload)
        return result

    def close(self) -> None:
        self._connection.close()


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
                 approved_roots: Optional[Iterable[Path | str]] = None,
                 storage_path: Optional[Path | str] = None):
        self._lock = threading.RLock()
        self.workspace_root = Path(workspace_root or Path(__file__).resolve().parents[3]).resolve()
        self.approved_roots = tuple(Path(root).resolve() for root in (
            approved_roots or default_approved_roots(self.workspace_root)))
        self._store = RobotCatalogStore(storage_path) if storage_path else None
        self._robots: dict[str, RobotRecord] = {}
        self._user_overrides: dict[str, dict[str, Any]] = {}
        self._last_report: Optional[DiscoveryReport] = None
        if self._store:
            stored_records, stored_overrides, _ = self._store.load()
            self._user_overrides = stored_overrides
            self._robots = {
                robot_id: self._record_from_payload(payload)
                for robot_id, payload in stored_records.items()
            }
            for record in self._robots.values():
                self._hydrate_evidence(record)

    @staticmethod
    def _record_from_payload(payload: dict[str, Any]) -> RobotRecord:
        known = {item.name for item in __import__("dataclasses").fields(RobotRecord)}
        values = {key: payload[key] for key in known if key in payload}
        values["provenance"] = [EvidenceClaim(**claim) for claim in payload.get("provenance", [])]
        return RobotRecord(**values)

    def _hydrate_evidence(self, record: RobotRecord) -> None:
        if not self._store:
            return
        for evidence in self._store.evidence_for_robot(record.robot_id):
            kind = evidence.get("evidence_kind", "")
            if kind == "COMPILE":
                evidence_id = str(evidence.get("evidence_id") or "")
                record.compile_evidence = [existing for existing in record.compile_evidence
                                           if not evidence_id or existing.get("evidence_id") != evidence_id]
                record.compile_evidence.append(evidence)
            elif kind == "TEST_RUN":
                test_run_id = str(evidence.get("test_run_id") or
                                   evidence.get("manifest", {}).get("test_run_id") or
                                   evidence.get("manifest", {}).get("identity", {}).get("test_run_id") or "")
                record.test_runs = [existing for existing in record.test_runs
                                    if not test_run_id or existing.get("test_run_id") != test_run_id]
                record.test_runs.append(evidence)
            if kind == "TEST_RUN":
                parameters = evidence.get("manifest", {}).get("parameters")
                parameter_fingerprint = (str(parameters.get("fingerprint") or "")
                                         if isinstance(parameters, dict) else "")
                if (isinstance(parameters, dict) and not any(
                        (parameter_fingerprint and
                         str(existing.get("fingerprint") or "") == parameter_fingerprint) or
                        _claim_value(existing) == _claim_value(parameters)
                        for existing in record.parameter_sets)):
                    record.parameter_sets.append(parameters)
        if record.test_runs:
            record.latest_test_status = str(record.test_runs[-1].get("status") or
                                            record.test_runs[-1].get("identity", {}).get("status") or
                                            "UNKNOWN")

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
                        parameter_sets=list(old.parameter_sets) if old else [],
                        compile_evidence=list(old.compile_evidence) if old else [],
                        test_runs=list(old.test_runs) if old else [],
                        latest_test_status=(old.latest_test_status if old else "NOT_PRESENT"),
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
                    version = _match(r"#property\s+version\s+['\"]([^'\"]+)", content) or "UNKNOWN"
                    robot_id = _logical_robot_id(path.stem, version, role)
                    record = add_robot(robot_id, _human_name(path.stem), role)
                    item = artifact.to_dict()
                    record.source_artifacts.append(item)
                    record.version = version
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
                    robot_id = _logical_robot_id(path.stem, "UNKNOWN", "COMPILED_ONLY")
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
                        preset = self._parse_preset(path)
                        item.update(preset)
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
                status, record, candidates, signals, reason = self._associate_backtest(
                    parsed, robots, source_by_stem, compiled_by_stem)
                parsed.association_status = status
                parsed.association_confidence = status
                parsed.candidate_robot_ids = candidates
                parsed.association_signals = signals
                parsed.association_reason = reason
                if record is not None:
                    parsed.robot_id = record.robot_id
                    record.backtest_artifacts.append(parsed.to_dict())
                    if artifact.kind == "OPTIMIZATION":
                        record.optimization_artifacts.append(parsed.to_dict())
                    self._claim(record, "backtest_evidence", artifact.relative_path,
                                "OPTIMIZATION_EVIDENCE" if artifact.kind == "OPTIMIZATION" else "BACKTEST_EVIDENCE",
                                "FACT_FROM_SOURCE", artifact, reason=reason)
                else:
                    parsed.provenance.append({
                        "evidence_type": "UNKNOWN", "fact_source": "UNKNOWN",
                        "reason": reason,
                    })
                    report.unassociated_artifacts.append(parsed.to_dict())
                if status == "VERIFIED":
                    report.backtests_verified += 1
                elif status == "HIGH_CONFIDENCE":
                    report.backtests_high_confidence += 1
                elif status == "AMBIGUOUS":
                    report.backtests_ambiguous += 1
                elif status == "CONFLICTING":
                    report.backtests_conflicting += 1
                else:
                    report.backtests_unresolved += 1
                if status in {"VERIFIED", "HIGH_CONFIDENCE"}:
                    report.backtests_associated += 1
                else:
                    report.backtests_unassociated += 1
                if len(report.association_examples) < 12:
                    report.association_examples.append({
                        "artifact": artifact.relative_path,
                        "status": status,
                        "robot_id": parsed.robot_id or None,
                        "candidates": candidates,
                        "signals": signals,
                        "reason": reason,
                    })

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
            if self._store:
                self._store.save_scan(robots, report)
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
            if self._store:
                self._store.save_override(str(robot_id), override)
            return {"ok": True, "robot": record.to_dict(detail=True)}

    def record_compile_evidence(self, robot_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        """Attach compiler evidence; this never compiles or opens MetaEditor."""
        with self._lock:
            record = self._robots.get(str(robot_id))
            if record is None:
                return {"ok": False, "error": "ROBOT_NOT_FOUND", "robot_id": str(robot_id)}
            item = _bounded(dict(evidence))
            item.setdefault("robot_id", str(robot_id))
            item.setdefault("evidence_kind", "COMPILE")
            if item not in record.compile_evidence:
                record.compile_evidence.append(item)
            if self._store:
                self._store.save_evidence("COMPILE", item)
            return {"ok": True, "read_only": False, "evidence": item}

    def record_test_run(self, robot_id: str, manifest: dict[str, Any],
                        result: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Persist a manifest/result pair without starting a tester process."""
        with self._lock:
            record = self._robots.get(str(robot_id))
            if record is None:
                return {"ok": False, "error": "ROBOT_NOT_FOUND", "robot_id": str(robot_id)}
            item = {"robot_id": str(robot_id), "evidence_kind": "TEST_RUN",
                    "manifest": _bounded(manifest), "result": _bounded(result) if result else None,
                    "test_run_id": manifest.get("test_run_id") or manifest.get("identity", {}).get("test_run_id"),
                    "status": (result or {}).get("status") or manifest.get("identity", {}).get("status", "PLANNED")}
            if not item["test_run_id"]:
                return {"ok": False, "error": "TEST_RUN_ID_REQUIRED"}
            record.test_runs = [existing for existing in record.test_runs
                                if existing.get("test_run_id") != item["test_run_id"]]
            record.test_runs.append(item)
            parameter_set = manifest.get("parameters")
            if isinstance(parameter_set, dict) and parameter_set not in record.parameter_sets:
                record.parameter_sets.append(parameter_set)
            record.latest_test_status = str(item["status"])
            if self._store:
                self._store.save_evidence("TEST_RUN", item)
            return {"ok": True, "read_only": False, "test_run": item}

    def associate_production_evidence(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Apply an already validated, idempotent production association plan."""
        with self._lock:
            if plan.get("dry_run_status") != "SAFE_TO_APPLY":
                return {"ok": False, "error": "ASSOCIATION_PLAN_NOT_SAFE", "plan": plan}
            logical = plan.get("logical_robot") if isinstance(plan.get("logical_robot"), dict) else {}
            robot_id = str(logical.get("robot_id") or "")
            if not robot_id or str(logical.get("classification")) != "PRODUCTION_ROBOT":
                return {"ok": False, "error": "PRODUCTION_IDENTITY_REQUIRED"}
            record = self._robots.get(robot_id)
            if record is None:
                now = time.time()
                record = RobotRecord(
                    robot_id=robot_id, name=str(logical.get("name") or robot_id),
                    status="DISCOVERED", classification="PRODUCTION_ROBOT", artifact_role="EA",
                    discovered_at=now, last_seen_at=now,
                    known_limitations=["HISTORICAL_EVIDENCE_ONLY", "CURRENT_COMPILED_ARTIFACT_NOT_TESTED_BY_B4_5",
                                       "ANALYSIS_ONLY", "NOT_AUTHORIZED_FOR_LIVE_TRADING"],
                )
                self._robots[robot_id] = record
            elif record.classification not in {"UNKNOWN", "PRODUCTION_ROBOT"}:
                return {"ok": False, "error": "IDENTITY_COLLISION", "robot_id": robot_id}
            record.classification = "PRODUCTION_ROBOT"
            record.status = record.status if record.status in {"DISCOVERED", "CANDIDATE", "INACTIVE", "BLOCKED", "ARCHIVED"} else "DISCOVERED"
            record.source_artifacts = _merge_identity_items(record.source_artifacts, plan.get("source_artifacts", []), "sha256")
            record.compiled_artifacts = _merge_identity_items(record.compiled_artifacts, plan.get("compiled_artifacts", []), "sha256")
            record.backtest_artifacts = _merge_identity_items(record.backtest_artifacts, plan.get("backtest_artifacts", []), "artifact_id")
            record.parameter_sets = _merge_identity_items(record.parameter_sets, plan.get("parameter_sets", []), "fingerprint")
            record.test_runs = _merge_identity_items(record.test_runs, plan.get("test_runs", []), "test_run_id")
            record.campaign_associations = _merge_identity_items(record.campaign_associations, plan.get("campaigns", []), "campaign_id")
            record.temporal_contexts = _merge_identity_items(record.temporal_contexts, plan.get("temporal_contexts", []), "context_fingerprint")
            record.latest_test_status = "HISTORICAL_PRODUCTION_EVIDENCE"
            record.known_limitations = list(dict.fromkeys(record.known_limitations + [
                "B4.5_RESULTS_BOUND_TO_HISTORICAL_COMPILED_ARTIFACT_ONLY",
                "CURRENT_COMPILED_ARTIFACT_HAS_ZERO_B4.5_RESULTS",
            ]))
            if not any(claim.claim_id == f"{robot_id}:production_association" for claim in record.provenance):
                record.provenance.append(EvidenceClaim(
                    claim_id=f"{robot_id}:production_association", field="production_association",
                    value=True, evidence_type="TEST_RESULT", fact_source="TEST_RESULT",
                    source_ref=str(plan.get("campaign_id") or ""), confidence="HIGH",
                    reason="B4.5 historical evidence indexed without changing trading authority",
                ))
            if self._store:
                self._store.save_production_association(record, plan.get("evidence_items", []))
            return {"ok": True, "read_only": False, "association_status": "PERSISTED",
                    "robot": record.to_dict(detail=True), "plan": plan}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "read_only": True,
                "catalog_version": self.CATALOG_VERSION,
                "persistence": "SUBORDINATE_SQLITE" if self._store else "IN_MEMORY_READ_MODEL",
                "storage_path": str(self._store.path) if self._store else None,
                "schema_migration": "CATALOG_SCHEMA_V1" if self._store else "NOT_REQUIRED",
                "trade_authority": "NONE",
                "scanned": self._last_report is not None,
                "report": self._last_report.to_dict() if self._last_report else None,
                "robots": [item.to_dict() for item in self._sorted_robots()],
            }

    def close(self) -> None:
        with self._lock:
            if self._store:
                self._store.close()

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
    def _parse_preset(path: Path) -> dict[str, Any]:
        parameters: dict[str, Any] = {}
        try:
            content = _text(path, limit=2_000_000)
        except OSError:
            return {"parameter_fingerprint": "", "parameter_count": 0, "parameters": {}}
        for line in content.splitlines():
            value = line.strip()
            if not value or value.startswith((";", "#")) or "=" not in value:
                continue
            key, raw = value.split("=", 1)
            raw = raw.split("||", 1)[0].strip()
            key = key.strip()
            if not key:
                continue
            lowered = raw.casefold()
            if lowered in {"true", "false"}:
                parsed: Any = lowered == "true"
            else:
                try:
                    parsed = float(raw) if any(char in raw for char in ".eE") else int(raw)
                except ValueError:
                    parsed = raw
            parameters[key] = parsed
        return {
            "parameter_fingerprint": _parameter_fingerprint(parameters) if parameters else "",
            "parameter_count": len(parameters),
            "parameters": _bounded(parameters),
        }

    @staticmethod
    def _compatible(record: RobotRecord, parsed: BacktestEvidence) -> list[str]:
        signals = []
        symbol = _normal_key(parsed.symbol)
        if symbol != "unknown" and any(symbol == _normal_key(item) for item in record.supported_symbols):
            signals.append("symbol_match")
        timeframe = _normal_key(parsed.timeframe)
        if timeframe != "unknown" and any(timeframe in _normal_key(item) for item in record.supported_timeframes):
            signals.append("timeframe_match")
        return signals

    @classmethod
    def _associate_backtest(cls, parsed: BacktestEvidence,
                            robots: dict[str, RobotRecord],
                            source_by_stem: dict[str, list[RobotRecord]],
                            compiled_by_stem: dict[str, list[RobotRecord]]) -> tuple[str, Optional[RobotRecord], list[str], list[str], str]:
        by_id = {record.robot_id: record for record in robots.values()}
        direct: dict[str, list[str]] = {}
        for hint in parsed.identity_hints:
            key = _normal_key(hint)
            candidates = []
            for record in robots.values():
                if key in {_normal_key(record.name), _normal_key(record.robot_id)}:
                    candidates.append(record.robot_id)
                if any(key == _normal_key(alias.get("value", "")) for alias in record.aliases):
                    candidates.append(record.robot_id)
            direct[hint] = sorted(set(candidates))
        direct_ids = sorted({item for items in direct.values() for item in items})
        strategy_key = _normal_key(parsed.strategy)
        name_matches = source_by_stem.get(strategy_key, []) or compiled_by_stem.get(strategy_key, [])
        strategy_ids = sorted({record.robot_id for record in name_matches})
        alias_ids = sorted({record.robot_id for record in robots.values()
                            if any(strategy_key == _normal_key(alias.get("value", ""))
                                   for alias in record.aliases)})
        strong_ids = sorted(set(strategy_ids + alias_ids))
        if direct_ids and strong_ids and set(direct_ids) != set(strong_ids):
            return "CONFLICTING", None, sorted(set(direct_ids + strong_ids)), ["identifier_conflict"], \
                "explicit EA identifier conflicts with strategy/alias evidence"
        if len(direct_ids) > 1:
            return "CONFLICTING", None, direct_ids, ["multiple_explicit_identifiers"], \
                "more than one explicit robot identity was present"
        if len(direct_ids) == 1:
            record = by_id[direct_ids[0]]
            signals = ["exact_ea_identifier"] + cls._compatible(record, parsed)
            return "VERIFIED", record, direct_ids, signals, "explicit robot identifier matched catalog identity"
        if len(strong_ids) > 1:
            return "AMBIGUOUS", None, strong_ids, ["multiple_exact_strategy_candidates"], \
                "strategy name or alias matched multiple catalog identities"
        if len(strong_ids) == 1:
            record = by_id[strong_ids[0]]
            signal = "alias_exact" if strong_ids[0] in alias_ids and not strategy_ids else "exact_robot_identifier"
            return "VERIFIED", record, strong_ids, [signal] + cls._compatible(record, parsed), \
                "exact robot identity or documented alias matched"

        fingerprint = parsed.parameter_fingerprint
        preset_candidates = []
        if fingerprint:
            preset_candidates = [record for record in robots.values()
                                 if any(item.get("parameter_fingerprint") == fingerprint
                                        for item in record.parameter_presets)]
        if len(preset_candidates) > 1:
            return "AMBIGUOUS", None, sorted(item.robot_id for item in preset_candidates), \
                ["parameter_fingerprint_match", "multiple_preset_candidates"], \
                "parameter fingerprint matched multiple presets"
        if len(preset_candidates) == 1:
            record = preset_candidates[0]
            compatibility = cls._compatible(record, parsed)
            if len(compatibility) >= 1:
                return "HIGH_CONFIDENCE", record, [record.robot_id], \
                    ["parameter_fingerprint_match"] + compatibility, \
                    "exact preset fingerprint plus source compatibility matched"
            return "UNRESOLVED", None, [record.robot_id], ["parameter_fingerprint_match"], \
                "preset matched but no independent symbol/timeframe compatibility"
        return "UNRESOLVED", None, [], [], \
            "no exact identity, documented alias, or evidence-bearing preset match"

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
        aliases = re.findall(
            r"(?:alias|aliases|nome\s+(?:anterior|antigo)|legacy\s+name)\s*[:=]\s*([^\n<;]+)",
            content, re.I,
        )
        for alias in aliases:
            value = alias.strip().strip("\"'")
            if not value or _normal_key(value) == _normal_key(record.name):
                continue
            item = {"value": value, "source_artifact_id": artifact.artifact_id,
                    "source_ref": artifact.relative_path,
                    "authority": "DOCUMENTATION_ALIAS"}
            if item not in record.aliases:
                record.aliases.append(item)
                cls._claim(record, "alias", value, "DOCUMENTATION_VERIFIED",
                           "FACT_FROM_DOCUMENTATION", artifact,
                           reason="explicit alias claim in documentation")

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
        identity_hints = []
        for key in ("ea", "ea_name", "expert", "expert_name", "robot", "robot_name", "robot_id"):
            value = stats.get(key, data.get(key))
            if value not in (None, ""):
                identity_hints.append(str(value))
        raw_parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
        parameter_fingerprint = _parameter_fingerprint(raw_parameters) if raw_parameters else ""
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
            identity_hints=identity_hints,
            parameter_fingerprint=parameter_fingerprint,
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
    "ASSOCIATION_STATUSES", "EVIDENCE_TYPES", "FACT_SOURCES", "LIFECYCLE_STATES",
    "BacktestEvidence", "RobotCatalogStore", "default_catalog_store_path",
    "DiscoveryReport", "EvidenceClaim", "RobotArtifact", "RobotCatalogReadModel",
    "RobotRecord", "default_approved_roots", "parameter_fingerprint",
]
