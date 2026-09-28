"""Shared B2 contracts for provenance, freshness and legacy recovery.

These contracts are deliberately storage-neutral. They describe observations
and recovery candidates without importing legacy data or creating a database.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class FreshnessState(str, Enum):
    FRESH = "FRESH"
    RECENT = "RECENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceClass(str, Enum):
    VERIFIED_REAL_EVIDENCE = "VERIFIED_REAL_EVIDENCE"
    HISTORICAL_EVIDENCE = "HISTORICAL_EVIDENCE"
    CALCULATED = "CALCULATED"
    SYNTHETIC = "SYNTHETIC"
    DEMO = "DEMO"
    UNKNOWN = "UNKNOWN"


_FINGERPRINT_SECRET_KEYS = frozenset({
    "password", "passwd", "senha", "secret", "client_secret", "token",
    "access_token", "refresh_token", "api_key", "apikey", "authorization",
    "cookie", "session", "credential", "credentials", "private_key",
})
_FINGERPRINT_SECRET_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(password|passwd|senha|secret|client[_-]?secret|token|access[_-]?token|"
    r"refresh[_-]?token|api[_-]?key|authorization|cookie|session|credential|"
    r"private[_-]?key)\s*[:=]\s*([^\s,;\]}]+)"
)
_FINGERPRINT_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[^\s,;\]}]+")


def _fingerprint_key(key: Any) -> str:
    return str(key or "").strip().lower().replace("-", "_")


def sanitize_for_fingerprint(value: Any, key: str = "") -> Any:
    """Remove secret material before canonical serialization and hashing."""
    if _fingerprint_key(key) in _FINGERPRINT_SECRET_KEYS:
        return "<REDACTED>"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    if isinstance(value, dict):
        return {str(item_key): sanitize_for_fingerprint(item, str(item_key))
                for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_fingerprint(item, key) for item in value]
    if isinstance(value, set):
        items = [sanitize_for_fingerprint(item, key) for item in value]
        return sorted(items, key=lambda item: json.dumps(
            item, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    if hasattr(value, "value"):
        return sanitize_for_fingerprint(value.value, key)
    if hasattr(value, "item"):
        try:
            return sanitize_for_fingerprint(value.item(), key)
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return sanitize_for_fingerprint(vars(value), key)
    if isinstance(value, (bytes, bytearray)):
        return {"redacted_payload": True, "size": len(value)}
    if isinstance(value, str):
        redacted = _FINGERPRINT_SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}=<REDACTED>", value)
        return _FINGERPRINT_BEARER_PATTERN.sub("Bearer <REDACTED>", redacted)
    return str(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return _json_safe(value.value)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def stable_json(value: Any) -> str:
    return json.dumps(_json_safe(sanitize_for_fingerprint(value)),
                      ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"))


def content_fingerprint(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _timestamp(value: Any) -> float | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


@dataclass(frozen=True)
class FreshnessPolicy:
    """Capability-aware thresholds; no universal TTL is assumed."""

    fresh_seconds: float
    recent_seconds: float

    def classify(self, observed_at: Any, received_at: Any = None,
                 availability: str = "AVAILABLE", now: float | None = None) -> str:
        normalized = str(availability or "AVAILABLE").upper()
        if normalized in {"UNAVAILABLE", "OFFLINE", "NOT_FOUND"}:
            return FreshnessState.UNAVAILABLE.value
        observed = _timestamp(observed_at)
        if observed is None:
            return FreshnessState.UNKNOWN.value
        current = float(now if now is not None else datetime.now(timezone.utc).timestamp())
        age = max(0.0, current - observed)
        if age <= self.fresh_seconds:
            return FreshnessState.FRESH.value
        if age <= self.recent_seconds:
            return FreshnessState.RECENT.value
        return FreshnessState.STALE.value


FRESHNESS_POLICIES = {
    "tick": FreshnessPolicy(30, 180),
    "scanner": FreshnessPolicy(120, 600),
    "radar": FreshnessPolicy(300, 1800),
    "news": FreshnessPolicy(600, 3600),
    "macro": FreshnessPolicy(900, 86400),
    "candle": FreshnessPolicy(3600, 86400),
    "historical": FreshnessPolicy(0, 0),
}


@dataclass(frozen=True)
class ProvenanceEnvelope:
    source_id: str = ""
    provider_id: str = ""
    source_type: str = ""
    observation_id: str = ""
    correlation_id: str = ""
    artifact_id: str = ""
    observed_at: str | None = None
    received_at: str = ""
    age_seconds: float | None = None
    freshness_state: str = FreshnessState.UNKNOWN.value
    evidence_class: str = EvidenceClass.UNKNOWN.value
    calculation_origin: str = ""
    content_fingerprint: str = ""
    provenance_chain: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"provenance_chain": list(self.provenance_chain)}


def provenance_for_payload(payload: Any, source_id: str, source_type: str,
                           evidence_class: str = EvidenceClass.CALCULATED.value,
                           provider_id: str = "", artifact_id: str = "",
                           correlation_id: str = "", policy: FreshnessPolicy | None = None,
                           capability: str = "", received_at: str | None = None,
                           now: float | None = None) -> ProvenanceEnvelope:
    value = payload if isinstance(payload, dict) else {}
    received = received_at or utc_now()
    # Only source-provided fields can become observed_at. The bridge clock is
    # never silently substituted for an absent source timestamp.
    observed = value.get("observed_at") or value.get("source_timestamp")
    if observed is None:
        observed = value.get("updated_at") or value.get("generated_at")
    observed_text = str(observed) if observed not in (None, "") else None
    observed_epoch = _timestamp(observed)
    received_epoch = _timestamp(received)
    age = None
    if observed_epoch is not None and received_epoch is not None:
        age = round(max(0.0, received_epoch - observed_epoch), 3)
    state = (policy or FRESHNESS_POLICIES.get(capability,
                                              FreshnessPolicy(0, 0))).classify(
                                                  observed, received, value.get("status", "AVAILABLE"),
                                                  now=now)
    return ProvenanceEnvelope(
        source_id=str(source_id or ""), provider_id=str(provider_id or value.get("source") or ""),
        source_type=str(source_type or ""),
        observation_id=str(value.get("observation_id") or ""),
        correlation_id=str(correlation_id or value.get("correlation_id") or ""),
        artifact_id=str(artifact_id or value.get("artifact_id") or ""),
        observed_at=observed_text, received_at=received, age_seconds=age,
        freshness_state=state, evidence_class=str(evidence_class or EvidenceClass.UNKNOWN.value),
        calculation_origin=str(value.get("calculation_origin") or ""),
        content_fingerprint=content_fingerprint(value),
        provenance_chain=tuple(str(item) for item in (value.get("provenance_chain") or ())),
    )


@dataclass(frozen=True)
class RecoveryManifestEntry:
    source_store: str
    source_record_identity: str
    source_type: str
    target_domain: str
    proposed_target: str
    content_fingerprint: str
    provenance: dict[str, Any]
    classification: str
    recovery_decision: str
    conflict_state: str = "UNKNOWN"
    validation_required: bool = True
    size_bytes: int = 0

    @property
    def entry_id(self) -> str:
        return content_fingerprint_value({
            "source_store": self.source_store,
            "source_record_identity": self.source_record_identity,
            "content_fingerprint": self.content_fingerprint,
        })

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"entry_id": self.entry_id}


def content_fingerprint_value(value: Any) -> str:
    return content_fingerprint(value)


_EXCLUDED_NAMES = {".env", "api_keys.json", "device_registry.json", "credentials.json"}
_KNOWN_ROOTS = (
    "data/trade_journal", "data/setup_database", "data/market_ai_audit.jsonl",
    "config/backtest_results", "studio/golden_ai_studio_web/jarvis",
    "jarvis", "vault/Segundo Cerebro",
)


def _read_manifest_markers(path: Path) -> dict[str, Any]:
    """Read bounded structural markers without importing or executing data."""
    if path.suffix.lower() not in {".json", ".jsonl"}:
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
    except OSError:
        return {}
    values: list[Any] = []
    if path.suffix.lower() == ".jsonl":
        for line in text.splitlines():
            try:
                values.append(json.loads(line))
            except (TypeError, ValueError):
                continue
    else:
        try:
            values.append(json.loads(text))
        except (TypeError, ValueError):
            return {}

    markers: dict[str, Any] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for raw_key, item in value.items():
                key = _fingerprint_key(raw_key)
                if key in {"supersedes", "supersedes_id", "superseded_by",
                           "supersession", "supersession_id"} and item not in (None, "", [], {}):
                    markers["superseded"] = True
                if key in {"status", "state"} and str(item).upper() in {
                    "SUPERSEDED", "SUPERSEDED_RECORD"}:
                    markers["superseded"] = True
                if key in {"validated", "validation_status"}:
                    if item is True or str(item).upper() in {
                        "VERIFIED", "VALIDATED", "COMPILE_SUCCESS"}:
                        markers["validated"] = True
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for value in values:
        visit(value)
    return markers


def _classification(relative: str, path: Path, digest_count: int,
                    markers: dict[str, Any]) -> tuple[str, str]:
    normalized = relative.replace("\\", "/").lower()
    if "/backups/" in f"/{normalized}" or normalized.startswith("backups/"):
        return "BACKUP", "reference"
    if normalized.endswith((".db", ".sqlite", ".sqlite3")):
        return "RUNTIME", "runtime"
    if "fixture" in normalized or "/test" in normalized:
        return "FIXTURE", "test"
    if markers.get("superseded"):
        return "SUPERSEDED", "reference"
    if digest_count > 1:
        return "DUPLICATED", "reference"
    if "backtest" in normalized or "journal" in normalized or "audit" in normalized:
        return "UNIQUE", "evidence"
    return "UNKNOWN", "document"


def _recovery_decision(classification: str, validated: bool = False) -> str:
    """Fail-closed policy: classification never implies import approval."""
    return {
        "UNIQUE": "RECOVER" if validated else "NEEDS_VALIDATION",
        "DUPLICATED": "REFERENCE_ONLY",
        "SUPERSEDED": "REFERENCE_ONLY",
        "UNKNOWN": "NEEDS_VALIDATION",
        "FIXTURE": "DO_NOT_IMPORT",
        "RUNTIME": "DO_NOT_IMPORT",
        "BACKUP": "PRESERVE_IN_PLACE",
    }.get(classification, "NEEDS_VALIDATION")


def build_recovery_manifest(root: Path | str, max_entries: int = 400) -> dict[str, Any]:
    """Inventory known candidates without importing or opening databases."""
    base = Path(root).resolve()
    paths: list[Path] = []
    for relative in _KNOWN_ROOTS:
        candidate = base / relative
        if candidate.is_file():
            paths.append(candidate)
        elif candidate.is_dir():
            paths.extend(item for item in candidate.rglob("*") if item.is_file())
    candidates: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: str(item).casefold()):
        if path.name.casefold() in _EXCLUDED_NAMES:
            continue
        try:
            relative = path.relative_to(base).as_posix()
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            candidates.append({"path": path, "relative": relative,
                               "digest": digest.hexdigest(),
                               "markers": _read_manifest_markers(path)})
        except (OSError, ValueError):
            continue

    digest_counts: dict[str, int] = {}
    for item in candidates:
        digest_counts[item["digest"]] = digest_counts.get(item["digest"], 0) + 1

    entries: list[RecoveryManifestEntry] = []
    for item in candidates[:max_entries]:
        path = item["path"]
        relative = item["relative"]
        try:
            classification, target = _classification(
                relative, path, digest_counts[item["digest"]], item["markers"])
            validated = bool(item["markers"].get("validated"))
            decision = _recovery_decision(classification, validated=validated)
            entries.append(RecoveryManifestEntry(
                source_store=relative.split("/", 1)[0],
                source_record_identity=relative,
                source_type=path.suffix.lower().lstrip(".") or "file",
                target_domain=target,
                proposed_target="canonical_jarvis_read_model",
                content_fingerprint=item["digest"],
                provenance={"path": relative, "read_only": True,
                            "evidence_markers": sorted(item["markers"])},
                classification=classification, recovery_decision=decision,
                conflict_state=(classification if classification in {
                    "DUPLICATED", "SUPERSEDED"} else "UNKNOWN"),
                validation_required=not validated,
                size_bytes=path.stat().st_size,
            ))
        except (OSError, ValueError):
            continue
    payload = [entry.to_dict() for entry in entries]
    return {"ok": True, "read_only": True, "import_executed": False,
            "schema_change_required": False, "entries": payload,
            "count": len(payload), "manifest_hash": content_fingerprint(payload)}


__all__ = [
    "EvidenceClass", "FreshnessPolicy", "FreshnessState", "FRESHNESS_POLICIES",
    "ProvenanceEnvelope", "RecoveryManifestEntry", "build_recovery_manifest",
    "content_fingerprint", "provenance_for_payload", "sanitize_for_fingerprint",
    "stable_json", "utc_now",
]
