"""Validated, device-scoped snapshots of the existing manual trend scan."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone


CONTRACT_VERSION = "trend-scan-v1"
MAX_SCAN_ITEMS = 5000
MAX_STATE_BYTES = 8_000_000
_CLASSES = {"FOREX", "METALS", "CRYPTO", "INDICES", "COMMODITIES",
            "STOCKS", "ETF", "OTHER", "OTHER_UNKNOWN"}
_FILTERS = {"ALL", "FOREX", "INDICES", "STOCKS", "ETF", "CRYPTO",
            "COMMODITIES_METALS", "OTHER_UNKNOWN"}
_STATES = {"PENDENTE", "AVALIADO", "DADOS INSUFICIENTES", "INDISPONÍVEL", "FALHO"}
_FRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
_RESULT_FIELDS = {"trend", "strength", "directional_score", "score_semantics",
                  "alignment", "timeframe_divergence", "applied_timeframe_weights",
                  "extended_trend_risk", "data_state", "freshness",
                  "temporal_authority", "absolute_utc_verified", "tick_volume_state",
                  "stale_timeframes", "macro_news_inputs", "snapshot_ids",
                  "methodology_version", "execution_authority", "asset_class_source",
                  "terminal_data_root_fingerprints"}
_FRAME_FIELDS = {"timeframe", "snapshot_id", "candle_count", "raw_candle_time_start",
                 "raw_candle_time_end", "freshness", "temporal_authority", "provider",
                 "provider_symbol", "status", "directional_score", "trend_classification",
                 "trend", "volatility_percent", "breakout_context", "volume_state",
                 "tick_volume_ratio", "extension_distance_atr", "extended_risk",
                 "components"}
_COMPONENT_FIELDS = {"ma_spread_atr", "price_location_atr", "momentum_10_candles",
                     "directional_persistence_20", "observed_breakout_20_candles"}
_SENSITIVE_KEYS = ("password", "secret", "token", "credential", "authorization",
                   "cookie", "api_key", "private_key", "prompt", "reasoning_trace")
_LEGACY_OPTIONAL_STATE_FIELDS = {"catalog_observation", "result_authority"}


def _json_value(value, depth=0):
    if depth > 5:
        raise ValueError("SCAN_NESTING_LIMIT")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("NONFINITE_SCAN_NUMBER")
        return value
    if isinstance(value, str):
        if len(value) > 256:
            raise ValueError("SCAN_FIELD_TOO_LONG")
        return value
    if isinstance(value, list):
        if len(value) > 32:
            raise ValueError("SCAN_LIST_LIMIT")
        return [_json_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 32:
            raise ValueError("SCAN_FIELD_LIMIT")
        cleaned = {}
        for key, item in value.items():
            name = str(key)[:64]
            if any(marker in name.casefold() for marker in _SENSITIVE_KEYS):
                raise ValueError("SENSITIVE_SCAN_FIELD_FORBIDDEN")
            cleaned[name] = _json_value(item, depth + 1)
        return cleaned
    raise ValueError("INVALID_SCAN_VALUE")


def _identity(source):
    if not isinstance(source, dict):
        raise ValueError("INVALID_ASSET_IDENTITY")
    symbol = source.get("provider_symbol")
    asset_id = source.get("provider_asset_id")
    asset_class = source.get("asset_class")
    if (source.get("provider") != "MT5" or not isinstance(symbol, str)
            or not re.fullmatch(r"[A-Za-z0-9._#-]{1,64}", symbol)
            or asset_id != f"mt5:{symbol}" or asset_class not in _CLASSES):
        raise ValueError("INVALID_ASSET_IDENTITY")
    return {"provider": "MT5", "provider_asset_id": asset_id,
            "provider_symbol": symbol,
            "display_symbol": str(source.get("display_symbol") or symbol)[:64],
            "display_name": str(source.get("display_name") or symbol)[:120],
            "asset_class": asset_class,
            "asset_class_source": str(source.get("asset_class_source") or "UNKNOWN")[:48]}


def _universe_hash(items):
    canonical = "\n".join("\0".join((item["asset"]["provider_asset_id"],
                                     item["asset"]["provider_symbol"],
                                     item["asset"]["asset_class"])) for item in items)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _result(source, asset):
    if not isinstance(source, dict):
        raise ValueError("INVALID_SCAN_RESULT")
    reported = source.get("asset")
    if (not isinstance(reported, dict) or
            any(reported.get(key) != asset[key] for key in
                ("provider", "provider_asset_id", "provider_symbol",
                 "display_symbol", "display_name", "asset_class",
                 "asset_class_source"))):
        raise ValueError("RESULT_IDENTITY_MISMATCH")
    frames = source.get("evaluated_timeframes", [])
    if not isinstance(frames, list) or len(frames) > 7:
        raise ValueError("INVALID_SCAN_FRAMES")
    cleaned_frames, seen = [], set()
    for frame in frames:
        if not isinstance(frame, dict) or frame.get("timeframe") not in _FRAMES:
            raise ValueError("INVALID_SCAN_FRAME")
        if frame["timeframe"] in seen:
            raise ValueError("DUPLICATE_SCAN_FRAME")
        seen.add(frame["timeframe"])
        components = frame.get("components")
        if components is not None and (
                not isinstance(components, dict) or
                set(components) - _COMPONENT_FIELDS or
                any(not isinstance(value, (int, float)) or isinstance(value, bool)
                    for value in components.values())):
            raise ValueError("INVALID_SCAN_COMPONENTS")
        cleaned_frames.append(_json_value({key: frame[key] for key in _FRAME_FIELDS
                                           if key in frame}))
    cleaned = {key: source[key] for key in _RESULT_FIELDS if key in source}
    alignment = cleaned.get("alignment")
    if alignment is not None and (not isinstance(alignment, dict)
                                  or set(alignment) - {"aligned", "available"}):
        raise ValueError("INVALID_SCAN_ALIGNMENT")
    weights = cleaned.get("applied_timeframe_weights")
    if weights is not None and (not isinstance(weights, dict) or set(weights) - _FRAMES):
        raise ValueError("INVALID_SCAN_WEIGHTS")
    fingerprints = cleaned.get("terminal_data_root_fingerprints")
    if fingerprints is not None and (not isinstance(fingerprints, list) or
            any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in fingerprints)):
        raise ValueError("INVALID_TERMINAL_FINGERPRINT")
    cleaned["asset"] = {key: asset[key] for key in
                        ("provider", "provider_asset_id", "provider_symbol",
                         "display_symbol", "display_name", "asset_class",
                         "asset_class_source")}
    cleaned["evaluated_timeframes"] = cleaned_frames
    errors = source.get("read_errors", [])
    if not isinstance(errors, list) or len(errors) > 7:
        raise ValueError("INVALID_SCAN_READ_ERRORS")
    cleaned["read_errors"] = [
        {"timeframe": str(error.get("timeframe") or "UNKNOWN")[:8],
         "error_code": str(error.get("error_code") or "UNKNOWN")[:64]}
        for error in errors if isinstance(error, dict)]
    if len(cleaned["read_errors"]) != len(errors):
        raise ValueError("INVALID_SCAN_READ_ERRORS")
    if cleaned.get("execution_authority", "NONE") != "NONE":
        raise ValueError("TRADING_RESULT_FORBIDDEN")
    return _json_value(cleaned)


def _normalize(scan):
    if not isinstance(scan, dict) or scan.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("UNSUPPORTED_SCAN_CONTRACT")
    try:
        scan_id = str(uuid.UUID(str(scan.get("scan_id"))))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("INVALID_SCAN_ID") from exc
    raw_items = scan.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= MAX_SCAN_ITEMS:
        raise ValueError("INVALID_UNIVERSE_TOTAL")
    if scan.get("universe_total") != len(raw_items):
        raise ValueError("UNIVERSE_TOTAL_MISMATCH")
    if scan.get("asset_class_filter") not in _FILTERS:
        raise ValueError("INVALID_SCAN_FILTER")
    created_at = scan.get("created_at")
    try:
        parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_SCAN_CREATED_AT") from exc
    items, seen = [], set()
    counts = {"evaluated": 0, "insufficient": 0, "unavailable": 0,
              "failed": 0, "pending": 0}
    count_keys = {"AVALIADO": "evaluated", "DADOS INSUFICIENTES": "insufficient",
                  "INDISPONÍVEL": "unavailable", "FALHO": "failed",
                  "PENDENTE": "pending"}
    for source in raw_items:
        if not isinstance(source, dict) or source.get("state") not in _STATES:
            raise ValueError("INVALID_SCAN_ITEM")
        asset = _identity(source.get("asset"))
        selected = scan["asset_class_filter"]
        matches_filter = (selected == "ALL" or selected == asset["asset_class"]
                          or selected == "COMMODITIES_METALS" and asset["asset_class"] in {"COMMODITIES", "METALS"}
                          or selected == "OTHER_UNKNOWN" and asset["asset_class"] in {"OTHER", "OTHER_UNKNOWN"})
        if not matches_filter:
            raise ValueError("ASSET_OUTSIDE_FROZEN_FILTER")
        if asset["provider_asset_id"] in seen:
            raise ValueError("DUPLICATE_SCAN_ASSET")
        seen.add(asset["provider_asset_id"])
        state = source["state"]
        result = source.get("result")
        if result is not None:
            result = _result(result, asset)
        if state == "AVALIADO" and (result is None or
                not isinstance(result.get("directional_score"), (int, float)) or
                isinstance(result.get("directional_score"), bool)):
            raise ValueError("EVALUATED_RESULT_REQUIRED")
        if state == "AVALIADO" and (
                sum(frame.get("status") == "AVAILABLE" for frame in result["evaluated_timeframes"]) < 3
                or result.get("data_state") == "INSUFFICIENT_DATA"
                or result["read_errors"]):
            raise ValueError("EVALUATED_COVERAGE_MISMATCH")
        if state == "DADOS INSUFICIENTES" and result is not None and (
                result["read_errors"] or
                (isinstance(result.get("directional_score"), (int, float))
                 and sum(frame.get("status") == "AVAILABLE" for frame in
                         result["evaluated_timeframes"]) >= 3
                 and result.get("data_state") != "INSUFFICIENT_DATA")):
            raise ValueError("INSUFFICIENT_RESULT_MISMATCH")
        if state == "PENDENTE" and result is not None:
            raise ValueError("PENDING_RESULT_FORBIDDEN")
        retry_count, batch_index = source.get("retry_count"), source.get("batch_index")
        if (not isinstance(retry_count, int) or isinstance(retry_count, bool)
                or not 0 <= retry_count <= 1000 or
                (batch_index is not None and (not isinstance(batch_index, int)
                 or isinstance(batch_index, bool) or batch_index < 0))):
            raise ValueError("INVALID_SCAN_BATCH")
        if state == "PENDENTE" and batch_index is not None and retry_count == 0:
            raise ValueError("PENDING_BATCH_MISMATCH")
        correlation_id = str(source.get("batch_correlation_id") or "")
        if correlation_id and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", correlation_id):
            raise ValueError("INVALID_BATCH_CORRELATION")
        counts[count_keys[state]] += 1
        items.append({"asset": asset, "state": state, "result": result,
                      "error": str(source.get("error") or "")[:80],
                      "retry_count": retry_count, "batch_index": batch_index,
                      "batch_correlation_id": correlation_id,
                      "batch_observed_at": str(source.get("batch_observed_at") or "UNKNOWN")[:80]})
    if [item["asset"]["provider_asset_id"] for item in items] != sorted(seen):
        raise ValueError("UNIVERSE_ORDER_MISMATCH")
    digest = _universe_hash(items)
    if scan.get("universe_hash") != digest:
        raise ValueError("UNIVERSE_HASH_MISMATCH")
    supplied_counts = scan.get("summary")
    if not isinstance(supplied_counts, dict) or any(
            supplied_counts.get(key) != value for key, value in counts.items()):
        raise ValueError("SCAN_COUNTS_MISMATCH")
    if sum(counts.values()) != len(items):
        raise ValueError("SCAN_INVARIANT_FAILED")
    excluded = scan.get("excluded", [])
    if not isinstance(excluded, list) or len(excluded) > MAX_SCAN_ITEMS:
        raise ValueError("INVALID_SCAN_EXCLUSIONS")
    exclusions = []
    for entry in excluded:
        if (not isinstance(entry, dict) or entry.get("reason") not in
                {"NON_CANONICAL_MT5_IDENTITY", "UNSUPPORTED_ASSET_CLASS",
                 "DUPLICATE_PROVIDER_ASSET_ID"}):
            raise ValueError("INVALID_SCAN_EXCLUSION")
        exclusions.append({"provider_asset_id": str(entry.get("provider_asset_id") or "UNKNOWN")[:96],
                           "reason": entry["reason"]})
    excluded_summary = {}
    for entry in exclusions:
        excluded_summary[entry["reason"]] = excluded_summary.get(entry["reason"], 0) + 1
    if scan.get("excluded_summary") != excluded_summary:
        raise ValueError("SCAN_EXCLUSIONS_MISMATCH")
    observation = scan.get("catalog_observation") or {}
    if not isinstance(observation, dict):
        raise ValueError("INVALID_CATALOG_OBSERVATION")
    catalog_observation = {
        "status": str(observation.get("status") or "UNKNOWN")[:48],
        "observed_at": str(observation.get("observed_at") or "UNKNOWN")[:80],
        "enumerated_count": observation.get("enumerated_count")
        if isinstance(observation.get("enumerated_count"), int)
        and not isinstance(observation.get("enumerated_count"), bool) else None,
    }
    next_batch = scan.get("next_batch_index")
    if (not isinstance(next_batch, int) or isinstance(next_batch, bool)
            or not 0 <= next_batch <= len(items) + 1000):
        raise ValueError("INVALID_NEXT_BATCH")
    normalized = {"scan_id": scan_id, "contract_version": CONTRACT_VERSION,
                  "created_at": created_at, "universe_total": len(items),
                  "asset_class_filter": scan["asset_class_filter"],
                  "universe_hash": digest, "universe_hash_core": digest,
                  "hash_authority": "CORE_RECOMPUTED_FROM_CLIENT_UNIVERSE_NOT_CATALOG_REDISCOVERY",
                  "result_authority": "CLIENT_RETURNED_RANKING_NOT_REVALIDATED_AGAINST_MT5",
                  "catalog_observation": catalog_observation,
                  "excluded": exclusions, "excluded_summary": excluded_summary,
                  "next_batch_index": next_batch, "paused": scan.get("paused") is True,
                  "items": items, "summary": counts}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_BYTES:
        raise ValueError("SCAN_SIZE_LIMIT")
    return normalized, encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class GoldenTrendScanRepository:
    """Uses TaskDatabase transactions; never reads market data or changes task rows."""

    def __init__(self, task_database):
        self.database = task_database

    @staticmethod
    def _actor(actor_id):
        if (not isinstance(actor_id, str) or not actor_id.startswith("device:")
                or not re.fullmatch(r"device:[A-Za-z0-9_.:-]{1,128}", actor_id)):
            raise ValueError("DESKTOP_DEVICE_IDENTITY_REQUIRED")
        return actor_id

    def save(self, scan, actor_id, base_revision):
        actor = self._actor(actor_id)
        normalized, encoded, digest = _normalize(scan)
        if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
            raise ValueError("INVALID_SCAN_REVISION")
        now = datetime.now(timezone.utc).isoformat()
        with self.database._lock, self.database.connect(rows=True) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM golden_trend_scans WHERE scan_id=?",
                             (normalized["scan_id"],)).fetchone()
            if row:
                if row["actor_id"] != actor:
                    raise ValueError("SCAN_ACCESS_DENIED")
                self._verify_row(row)
                if row["state_sha256"] == digest:
                    return {"persisted": True, "duplicate": True,
                            "revision": row["revision"], "scan_id": normalized["scan_id"],
                            "universe_hash_core": normalized["universe_hash_core"],
                            "updated_at": row["updated_at"]}
                if row["revision"] != base_revision:
                    raise ValueError("STALE_SCAN_REVISION")
                previous = json.loads(row["state_json"])
                if (previous["universe_hash_core"] != normalized["universe_hash_core"]
                        or previous["created_at"] != normalized["created_at"]
                        or previous["asset_class_filter"] != normalized["asset_class_filter"]
                        or previous["catalog_observation"] != normalized["catalog_observation"]
                        or previous["excluded"] != normalized["excluded"]):
                    raise ValueError("FROZEN_UNIVERSE_CONFLICT")
                changed = 0
                for old, new in zip(previous["items"], normalized["items"]):
                    if old["asset"] != new["asset"]:
                        raise ValueError("FROZEN_ASSET_CONFLICT")
                    if old == new:
                        continue
                    if old["state"] not in {"PENDENTE", "FALHO"}:
                        raise ValueError("SETTLED_RESULT_IMMUTABLE")
                    if old["state"] == "FALHO" and new["retry_count"] <= old["retry_count"]:
                        raise ValueError("RETRY_COUNT_REQUIRED")
                    changed += 1
                if (changed > 4 or normalized["next_batch_index"] not in {
                        previous["next_batch_index"], previous["next_batch_index"] + 1}
                        or changed and normalized["next_batch_index"] == previous["next_batch_index"]):
                    raise ValueError("BATCH_LIMIT_EXCEEDED")
                revision = row["revision"] + 1
                db.execute("UPDATE golden_trend_scans SET updated_at=?,revision=?,state_sha256=?,"
                           "state_json=? WHERE scan_id=?",
                           (now, revision, digest, encoded, normalized["scan_id"]))
            else:
                if base_revision != 0 or normalized["next_batch_index"] != 0 or any(
                        item["state"] != "PENDENTE" for item in normalized["items"]):
                    raise ValueError("INITIAL_SCAN_MUST_BE_PENDING")
                revision = 1
                db.execute("""INSERT INTO golden_trend_scans(
                    scan_id,contract_version,actor_id,created_at,updated_at,revision,
                    universe_hash_client,universe_hash_core,state_sha256,state_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (normalized["scan_id"], CONTRACT_VERSION, actor,
                     normalized["created_at"], now, revision, scan["universe_hash"],
                     normalized["universe_hash_core"], digest, encoded))
        return {"persisted": True, "duplicate": False, "revision": revision,
                "scan_id": normalized["scan_id"],
                "universe_hash_core": normalized["universe_hash_core"],
                "updated_at": now}

    @staticmethod
    def _batch_state(result):
        if not isinstance(result, dict):
            return "FALHO", "RESULT_MISSING"
        if result.get("read_errors"):
            error = result["read_errors"][0] if isinstance(result["read_errors"], list) else {}
            return "FALHO", str(error.get("error_code") or "SNAPSHOT_READ_FAILED")[:80]
        frames = result.get("evaluated_timeframes")
        frames = frames if isinstance(frames, list) else []
        available = sum(frame.get("status") == "AVAILABLE" for frame in frames
                        if isinstance(frame, dict))
        score = result.get("directional_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool) \
                and available >= 3 and result.get("data_state") != "INSUFFICIENT_DATA":
            return "AVALIADO", ""
        if frames and all(isinstance(frame, dict) and frame.get("status") in
                          {"SOURCE_UNAVAILABLE", "SOURCE_DISABLED"} for frame in frames):
            return "INDISPONÍVEL", ""
        if result.get("status") == "SOURCE_UNAVAILABLE" and not available:
            return "INDISPONÍVEL", ""
        return "DADOS INSUFICIENTES", ""

    def apply_batch_results(self, scan_id, actor_id, base_revision, batch_index,
                            batch_asset_ids, results, metadata=None,
                            retry_of_failed_assets=False):
        """Evolve one persisted scan from bounded result rows.

        The caller supplies facts from the canonical ranking reader; this
        method owns the state transition and delegates final integrity to save.
        """
        actor = self._actor(actor_id)
        if (isinstance(base_revision, bool) or not isinstance(base_revision, int)
                or base_revision < 1 or isinstance(batch_index, bool)
                or not isinstance(batch_index, int) or batch_index < 0):
            raise ValueError("INVALID_BATCH_REVISION")
        ids = [str(value) for value in batch_asset_ids] if isinstance(batch_asset_ids, list) else []
        if not 1 <= len(ids) <= 4 or len(set(ids)) != len(ids):
            raise ValueError("INVALID_BATCH_ASSET_IDS")
        rows = results if isinstance(results, list) else []
        by_id = {str(row.get("asset", {}).get("provider_asset_id")): row
                  for row in rows if isinstance(row, dict)}
        if sorted(by_id) != sorted(ids):
            raise ValueError("BATCH_IDENTITY_MISMATCH")
        current = self.get(scan_id, actor)
        if not current:
            raise ValueError("SCAN_NOT_FOUND")
        if current["revision"] != base_revision:
            current_items = {item["asset"]["provider_asset_id"]: item
                             for item in current["scan"]["items"]}
            canonical_rows = {}
            for asset_id in ids:
                item = current_items.get(asset_id, {})
                row = by_id[asset_id]
                canonical_rows[asset_id] = _result(row, item["asset"])
            if all(current_items.get(asset_id, {}).get("batch_index") == batch_index
                   and current_items.get(asset_id, {}).get("result") == canonical_rows[asset_id]
                   for asset_id in ids):
                return {"persisted": True, "duplicate": True,
                        "revision": current["revision"], "scan_id": str(scan_id),
                        "universe_hash_core": current["scan"]["universe_hash_core"],
                        "updated_at": current["updated_at"]}
            raise ValueError("STALE_SCAN_REVISION")
        scan = current["scan"]
        items = scan["items"]
        item_by_id = {item["asset"]["provider_asset_id"]: item for item in items}
        for asset_id in ids:
            item = item_by_id.get(asset_id)
            row = by_id[asset_id]
            if item is None or row.get("asset") != item["asset"]:
                raise ValueError("RESULT_IDENTITY_MISMATCH")
            if item["state"] not in {"PENDENTE", "FALHO"}:
                continue
            was_failed = item["state"] == "FALHO"
            item["result"] = row
            item["state"], item["error"] = self._batch_state(row)
            item["batch_index"] = batch_index
            if item["state"] != "FALHO":
                item["error"] = ""
            if was_failed and (retry_of_failed_assets or item["state"] != "FALHO"):
                item["retry_count"] = min(1000, int(item.get("retry_count") or 0) + 1)
        scan["next_batch_index"] = max(int(scan.get("next_batch_index") or 0), batch_index + 1)
        scan["paused"] = False
        counts = {"evaluated": 0, "insufficient": 0, "unavailable": 0,
                  "failed": 0, "pending": 0}
        mapping = {"AVALIADO": "evaluated", "DADOS INSUFICIENTES": "insufficient",
                   "INDISPONÍVEL": "unavailable", "FALHO": "failed", "PENDENTE": "pending"}
        for item in items:
            counts[mapping[item["state"]]] += 1
        scan["summary"] = counts
        return self.save(scan, actor, base_revision)

    @staticmethod
    def _verify_row(row):
        encoded = row["state_json"]
        if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != row["state_sha256"]:
            raise ValueError("SCAN_STATE_CORRUPTED")
        try:
            state = json.loads(encoded)
            normalized, recoded, digest = _normalize(state)
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("SCAN_STATE_CORRUPTED") from exc
        legacy_state = isinstance(state, dict) and not (
            _LEGACY_OPTIONAL_STATE_FIELDS & set(state)
        )
        legacy_encoded = json.dumps(
            {key: value for key, value in normalized.items()
             if key not in _LEGACY_OPTIONAL_STATE_FIELDS},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        valid_encoding = (recoded == encoded and digest == row["state_sha256"]) or (
            legacy_state and legacy_encoded == encoded)
        if (not valid_encoding or normalized["scan_id"] != row["scan_id"]
                or normalized["universe_hash_core"] != row["universe_hash_core"]
                or row["contract_version"] != CONTRACT_VERSION):
            raise ValueError("SCAN_STATE_CORRUPTED")
        return normalized

    def get(self, scan_id, actor_id):
        actor = self._actor(actor_id)
        try:
            identifier = str(uuid.UUID(str(scan_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("INVALID_SCAN_ID") from exc
        with self.database.read_only(rows=True) as db:
            row = db.execute("SELECT * FROM golden_trend_scans WHERE scan_id=? AND actor_id=?",
                             (identifier, actor)).fetchone()
        if not row:
            return None
        scan = self._verify_row(row)
        return {"scan": scan, "revision": row["revision"], "updated_at": row["updated_at"]}

    def latest(self, actor_id):
        actor = self._actor(actor_id)
        with self.database.read_only(rows=True) as db:
            row = db.execute("SELECT * FROM golden_trend_scans WHERE actor_id=? "
                             "ORDER BY updated_at DESC, scan_id DESC LIMIT 1", (actor,)).fetchone()
        if not row:
            return None
        scan = self._verify_row(row)
        return {"scan": scan, "revision": row["revision"], "updated_at": row["updated_at"]}


__all__ = ["GoldenTrendScanRepository", "CONTRACT_VERSION"]
