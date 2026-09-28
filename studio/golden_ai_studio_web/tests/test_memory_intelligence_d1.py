import tempfile

from jarvis_core.brain import JarvisBrain
from jarvis_core.memory.boundary import CanonicalMemoryBoundary
from jarvis_core.memory.v2 import GoldenMemoryEngine
from jarvis_core.memory.v2.types import RecordStatus, SourceType
from jarvis_core.orchestrator.models import DataClassification
from jarvis_core.registry import ToolRegistry


class LegacyStub:
    def __init__(self):
        self.calls = 0

    def get_context(self, *args, **kwargs):
        self.calls += 1
        return "LEGACY SHOULD NOT WIN"


def _engine(root):
    return GoldenMemoryEngine(root + "/memory.db", vault_root=root + "/vault")


def test_memory_first_retrieval_returns_provenance_and_project_context():
    with tempfile.TemporaryDirectory() as root:
        engine = _engine(root)
        engine.remember("Python stable release is tracked by the Golden project.",
                        title="Python", project="Golden",
                        metadata={"freshness": "CURRENT"})
        engine.remember("Unrelated XAUUSD note.", title="Trading", project="Trading")
        boundary = CanonicalMemoryBoundary(engine)

        result = boundary.retrieve("Python stable release", project="Golden")

        assert result["sufficient"] is True
        assert result["results"]
        assert result["results"][0].project == "Golden"
        assert result["provenance"][0]["freshness"] == "CURRENT"
        assert result["provenance"][0]["source_type"] == "system"


def test_validated_current_knowledge_outranks_stale_and_superseded_history():
    with tempfile.TemporaryDirectory() as root:
        engine = _engine(root)
        current = engine.remember(
            "Python current stable version is the validated project fact.",
            title="Current", project="Golden",
            metadata={"freshness": "CURRENT"}, confidence=0.7)
        stale = engine.remember(
            "Python current stable version was an old project fact.",
            title="Old", project="Golden",
            metadata={"freshness": "STALE"}, confidence=0.99)
        superseded = engine.remember(
            "Python current stable version was superseded.",
            title="Superseded", project="Golden",
            metadata={"freshness": "STALE"}, confidence=0.99)
        engine.update(superseded.id, status=RecordStatus.SUPERSEDED)
        result = CanonicalMemoryBoundary(engine).retrieve(
            "Python current stable version", project="Golden", include_history=True)

        ids = [item.memory_id for item in result["results"]]
        assert ids[0] == current.id
        assert stale.id in ids
        assert superseded.id in ids
        assert result["provenance"][0]["freshness"] == "CURRENT"


def test_classification_and_retrieval_failure_are_fail_closed_without_core_failure():
    with tempfile.TemporaryDirectory() as root:
        engine = _engine(root)
        engine.remember("Internal project memory.", project="Golden")
        try:
            engine.remember("Secret memory", privacy=DataClassification.SECRET)
        except Exception:
            pass
        result = CanonicalMemoryBoundary(engine).retrieve("Secret memory")
        assert all(item.privacy != "SECRET" for item in result["results"])

        class BrokenEngine:
            store = object()

            def hybrid_search(self, *args, **kwargs):
                raise RuntimeError("retrieval unavailable")

        legacy = LegacyStub()
        brain = JarvisBrain(ToolRegistry(), legacy, memory_v2=BrokenEngine())
        assert brain._get_memory_context("project question") == "LEGACY SHOULD NOT WIN"
        assert brain.last_memory_retrieval["fallback"] is True
        brain.close()


def test_brain_uses_canonical_memory_before_legacy_and_research_reuse_is_bounded():
    with tempfile.TemporaryDirectory() as root:
        engine = _engine(root)
        engine.remember(
            "Validated Python project knowledge.", project="Golden",
            metadata={"freshness": "CURRENT",
                      "research": {"state": "validated"}},
            source_ref="https://docs.python.org/3/", source_type=SourceType.OFFICIAL_DOCS)
        legacy = LegacyStub()
        brain = JarvisBrain(ToolRegistry(), legacy, memory_v2=engine)
        context = brain._get_memory_context("Validated Python project knowledge")
        assert "MEMORY_CONTEXT" in context
        assert brain.last_memory_retrieval["mode"] == "memory-first"
        assert legacy.calls == 0
        reuse = CanonicalMemoryBoundary(engine).research_reuse(
            "Python project knowledge", project="Golden")
        assert reuse["reusable"] is True
        brain.close()
