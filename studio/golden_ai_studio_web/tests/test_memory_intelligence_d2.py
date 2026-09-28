import tempfile

from jarvis_core.memory.v2 import (FetchedSource, GoldenMemoryEngine,
                                   LearningEngine, ResearchEngine,
                                   StaticResearchProvider)
from jarvis_core.memory.v2.project_memory import MemoryCandidate, ProjectMemoryManager
from jarvis_core.memory.v2.types import ConfidenceBasis, RecordStatus, SourceType
from jarvis_core.orchestrator.models import DataClassification


def test_candidate_lifecycle_requires_explicit_promotion():
    with tempfile.TemporaryDirectory() as root:
        engine = GoldenMemoryEngine(root + "/memory.db")
        manager = ProjectMemoryManager(engine)
        deferred = MemoryCandidate(content="defer this", project="Golden", verdict="defer")
        rejected = MemoryCandidate(content="reject this", project="Golden", verdict="reject")
        assert manager.promote_candidate(deferred) is None
        assert manager.promote_candidate(rejected) is None
        promoted = MemoryCandidate(
            content="Decisão validada do projeto Golden.", project="Golden",
            memory_type="decision", confidence=0.9, verdict="promote",
            confidence_basis="documented", source_type="official_docs")
        record = manager.promote_candidate(promoted)
        assert record is not None
        assert record.project == "Golden"
        assert record.memory_type.value == "decision"


def test_user_override_is_not_silently_overwritten_by_lower_trust_evidence():
    with tempfile.TemporaryDirectory() as root:
        engine = GoldenMemoryEngine(root + "/memory.db")
        original = engine.remember(
            "Provider escolhido = Ollama local.",
            canonical_key="decision:Golden:provider",
            project="Golden", source_type=SourceType.USER_EXPLICIT,
            confidence_basis=ConfidenceBasis.USER_CONFIRMED, confidence=0.95)
        incoming = engine.remember(
            "Provider escolhido = cloud externo.",
            canonical_key="decision:Golden:provider",
            project="Golden", source_type=SourceType.WEB_ARTICLE,
            confidence_basis=ConfidenceBasis.SOURCE_CONFIRMED, confidence=0.95)
        assert original.content == "Provider escolhido = Ollama local."
        assert incoming.status == RecordStatus.DISPUTED
        assert engine.get(original.id).content == original.content


def test_conflict_history_restart_and_duplicate_write_protection():
    with tempfile.TemporaryDirectory() as root:
        path = root + "/memory.db"
        engine = GoldenMemoryEngine(path)
        first = engine.remember("A decisão validada é usar o provider local.",
                                project="Golden", source_type=SourceType.USER_EXPLICIT,
                                confidence=0.95)
        duplicate = engine.remember("A decisão validada é usar o provider local.",
                                    project="Golden", source_type=SourceType.USER_EXPLICIT,
                                    confidence=0.95)
        assert first.id == duplicate.id
        replacement = engine.remember(
            "A decisão validada é usar o provider cloud.", project="Golden",
            source_type=SourceType.OFFICIAL_DOCS, confidence=0.95)
        assert replacement.id != first.id
        restored = GoldenMemoryEngine(path)
        assert restored.get(first.id).content == first.content
        assert restored.get(replacement.id).content == replacement.content


def test_research_learning_promotes_supported_knowledge_without_secret_persistence():
    with tempfile.TemporaryDirectory() as root:
        engine = GoldenMemoryEngine(root + "/memory.db")
        learning = LearningEngine(
            engine, ResearchEngine(StaticResearchProvider([
                FetchedSource("Docs", "https://docs.example.com/a",
                              "Feature D is documented and validated.", "official")
            ])))
        report = learning.research_and_learn(
            "feature d", project="Golden", privacy=DataClassification.PUBLIC)
        assert report.promoted == 1
        assert engine.search("Feature D", limit=5)
        try:
            engine.remember("token=do-not-store", privacy=DataClassification.SECRET)
        except Exception:
            pass
        assert not engine.search("token do not store", limit=5)
