from jarvis_core.memory.v2 import GoldenMemoryEngine
from jarvis_core.memory.v2.types import RecordStatus, RelationType
from jarvis_core.scientific_memory import CanonicalScientificMemory, ScientificContractType


def test_contract_matrix_reuses_canonical_concepts():
    matrix = CanonicalScientificMemory.contract_matrix()
    assert {item["legacy_concept"] for item in matrix} == {
        "typed evidence", "revisions", "conflicts", "supersession",
        "experiment links", "hypothesis links",
    }
    assert all(item["decision"] == "ADAPT" for item in matrix)


def test_scientific_records_preserve_history_and_relationships(tmp_path):
    engine = GoldenMemoryEngine(tmp_path / "memory.db", audit=lambda *_: None)
    adapter = CanonicalScientificMemory(engine)
    first = adapter.remember(adapter.prepare(
        ScientificContractType.EVIDENCE, "Evidence one", source="test",
        artifact="artifact-a", confidence=0.8,
    ))
    second = adapter.remember(adapter.prepare(
        ScientificContractType.REVISION, "Revision two", source="test",
        revises_id=first["scientific_id"],
    ))
    assert first["ok"] and second["ok"]
    assert first["memory_id"] != second["memory_id"]
    assert engine.get(first["memory_id"]) is not None
    assert engine.get(second["memory_id"]) is not None
    assert second["relations"][0]["relation_type"] == "revises"
    assert engine.get(first["memory_id"]).status == RecordStatus.ACTIVE
    assert engine.get(second["memory_id"]).status == RecordStatus.ACTIVE
    assert engine.validate_graph()["ok"] is True
    assert adapter.status()["schema_change_required"] is False


def test_confidence_preserves_unknown_and_explicit_values(tmp_path):
    engine = GoldenMemoryEngine(tmp_path / "memory.db", audit=lambda *_: None)
    adapter = CanonicalScientificMemory(engine)
    cases = ((None, "UNKNOWN"), (0.0, "KNOWN"),
             (0.5, "KNOWN"), (1.0, "KNOWN"))
    for index, (confidence, state) in enumerate(cases):
        saved = adapter.remember(adapter.prepare(
            ScientificContractType.EVIDENCE, f"confidence case {index}",
            source="fixture", confidence=confidence))
        record = engine.get(saved["memory_id"])
        assert saved["canonical_confidence"] == confidence
        assert saved["confidence_state"] == state
        assert record.metadata["scientific_confidence"] == confidence
        assert record.metadata["confidence_state"] == state


def test_conflict_preserves_both_records_and_marks_canonical_status(tmp_path):
    engine = GoldenMemoryEngine(tmp_path / "memory.db", audit=lambda *_: None)
    adapter = CanonicalScientificMemory(engine)
    evidence = adapter.remember(adapter.prepare(
        ScientificContractType.EVIDENCE, "claim A", source="test"))
    conflict = adapter.remember(adapter.prepare(
        ScientificContractType.CONFLICT, "claim B contradicts claim A",
        source="test", conflicts_with_id=evidence["scientific_id"]))
    assert evidence["ok"] and conflict["ok"]
    assert evidence["memory_id"] != conflict["memory_id"]
    assert engine.get(evidence["memory_id"]).content == "claim A"
    assert engine.get(evidence["memory_id"]).status == RecordStatus.DISPUTED
    assert engine.get(conflict["memory_id"]).status == RecordStatus.DISPUTED
    assert conflict["relations"][0]["relation_type"] == "contradicts"


def test_supersession_preserves_old_record_and_marks_status(tmp_path):
    engine = GoldenMemoryEngine(tmp_path / "memory.db", audit=lambda *_: None)
    adapter = CanonicalScientificMemory(engine)
    old = adapter.remember(adapter.prepare(
        ScientificContractType.EVIDENCE, "old claim", source="test"))
    new = adapter.remember(adapter.prepare(
        ScientificContractType.SUPERSESSION, "new claim", source="test",
        supersedes_id=old["scientific_id"]))
    assert new["relations"][0]["relation_type"] == "supersedes"
    assert engine.get(old["memory_id"]).status == RecordStatus.SUPERSEDED
    assert engine.get(old["memory_id"]).content == "old claim"
    assert engine.get(new["memory_id"]).status == RecordStatus.ACTIVE
