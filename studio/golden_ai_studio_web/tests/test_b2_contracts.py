from datetime import datetime, timezone

from jarvis_core.b2_contracts import (
    EvidenceClass,
    FreshnessPolicy,
    FreshnessState,
    build_recovery_manifest,
    content_fingerprint,
    stable_json,
    provenance_for_payload,
)


def test_observed_at_is_not_inferred_from_received_at():
    result = provenance_for_payload(
        {"status": "AVAILABLE", "value": 1}, "source-a", "TEST",
        received_at="2026-09-28T12:00:00+00:00", capability="tick",
    )
    assert result.observed_at is None
    assert result.freshness_state == FreshnessState.UNKNOWN.value


def test_freshness_is_provider_aware_and_deterministic():
    policy = FreshnessPolicy(fresh_seconds=30, recent_seconds=120)
    observed = "2026-09-28T11:59:50+00:00"
    result = provenance_for_payload(
        {"status": "AVAILABLE", "updated_at": observed, "value": 1},
        "source-a", "TEST", EvidenceClass.CALCULATED.value,
        received_at="2026-09-28T12:00:00+00:00", policy=policy,
        capability="tick", now=datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc).timestamp(),
    )
    assert result.freshness_state == FreshnessState.FRESH.value
    assert result.age_seconds == 10.0


def test_fingerprint_is_stable_for_key_order():
    assert content_fingerprint({"b": 2, "a": 1}) == content_fingerprint({"a": 1, "b": 2})


def test_recovery_manifest_is_read_only_and_deterministic(tmp_path):
    target = tmp_path / "data" / "market_ai_audit.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text('{"event":"read"}\n', encoding="utf-8")
    (tmp_path / "device_registry.json").write_text("should not inventory", encoding="utf-8")
    first = build_recovery_manifest(tmp_path)
    second = build_recovery_manifest(tmp_path)
    assert first["import_executed"] is False
    assert first["schema_change_required"] is False
    assert first["manifest_hash"] == second["manifest_hash"]
    assert first["entries"][0]["classification"] == "UNIQUE"


def test_recovery_manifest_classification_and_decision_are_separate(tmp_path):
    base = tmp_path
    files = {
        "data/trade_journal/unique.jsonl": '{"validated": true, "event": "unique"}\n',
        "data/trade_journal/duplicate_a.jsonl": '{"event": "duplicate"}\n',
        "data/trade_journal/duplicate_b.jsonl": '{"event": "duplicate"}\n',
        "data/setup_database/superseded.jsonl": '{"status": "SUPERSEDED", "supersedes_id": "old"}\n',
        "data/setup_database/unknown.txt": "unclassified fixture source\n",
        "data/trade_journal/fixture_case.jsonl": '{"event": "fixture"}\n',
        "jarvis/runtime.db": "fixture database bytes\n",
        "data/trade_journal/backups/old.jsonl": '{"event": "backup"}\n',
    }
    for relative, content in files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    manifest = build_recovery_manifest(base)
    by_name = {item["source_record_identity"].split("/")[-1]: item
                for item in manifest["entries"]}
    assert by_name["unique.jsonl"]["classification"] == "UNIQUE"
    assert by_name["unique.jsonl"]["recovery_decision"] == "RECOVER"
    assert by_name["duplicate_a.jsonl"]["classification"] == "DUPLICATED"
    assert by_name["duplicate_a.jsonl"]["recovery_decision"] == "REFERENCE_ONLY"
    assert by_name["superseded.jsonl"]["classification"] == "SUPERSEDED"
    assert by_name["superseded.jsonl"]["recovery_decision"] == "REFERENCE_ONLY"
    assert by_name["unknown.txt"]["classification"] == "UNKNOWN"
    assert by_name["unknown.txt"]["recovery_decision"] == "NEEDS_VALIDATION"
    assert by_name["fixture_case.jsonl"]["classification"] == "FIXTURE"
    assert by_name["fixture_case.jsonl"]["recovery_decision"] == "DO_NOT_IMPORT"
    assert by_name["runtime.db"]["classification"] == "RUNTIME"
    assert by_name["runtime.db"]["recovery_decision"] == "DO_NOT_IMPORT"
    assert by_name["old.jsonl"]["classification"] == "BACKUP"
    assert by_name["old.jsonl"]["recovery_decision"] == "PRESERVE_IN_PLACE"
    assert all(item["classification"] != item["recovery_decision"]
               for item in manifest["entries"])
    assert manifest["import_executed"] is False


def test_fingerprint_sanitizes_nested_secrets_before_hashing():
    payload_a = {"b": 2, "nested": [{"api_key": "A", "value": 1}],
                 "authorization": "Bearer A", "a": 1}
    payload_b = {"a": 1, "authorization": "Bearer B",
                 "nested": [{"api_key": "B", "value": 1}], "b": 2}
    assert content_fingerprint(payload_a) == content_fingerprint(payload_b)
    assert "Bearer A" not in stable_json(payload_a)
    assert "Bearer B" not in stable_json(payload_b)
    changed = {**payload_a, "b": 3}
    assert content_fingerprint(changed) != content_fingerprint(payload_a)
    assert content_fingerprint({"value": None}) == content_fingerprint({"value": None})
