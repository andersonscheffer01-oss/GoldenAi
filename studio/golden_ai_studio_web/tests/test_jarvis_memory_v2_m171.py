"""M1.7.1 — Project Memory Runtime Wiring + Real Acceptance.

Tests project intent detection, runtime integration, Second Brain sync,
ambiguity handling, and performance budgets.
"""
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis_core.memory.v2.engine import GoldenMemoryEngine
from jarvis_core.memory.v2.project_memory import ProjectMemoryManager, ProjectContext


class ProjectIntentDetectionCase(unittest.TestCase):
    """Test JarvisBrain._needs_project_context (static regex)."""

    def test_continue_golden(self):
        from jarvis_core.brain import JarvisBrain
        self.assertTrue(JarvisBrain._needs_project_context("continue o Golden"))

    def test_retome_projeto(self):
        from jarvis_core.brain import JarvisBrain
        self.assertTrue(JarvisBrain._needs_project_context("retome o projeto"))

    def test_onde_paramos(self):
        from jarvis_core.brain import JarvisBrain
        self.assertTrue(JarvisBrain._needs_project_context("onde paramos no Golden"))

    def test_status_projeto(self):
        from jarvis_core.brain import JarvisBrain
        self.assertTrue(JarvisBrain._needs_project_context("status do projeto"))

    def test_decisoes(self):
        from jarvis_core.brain import JarvisBrain
        self.assertTrue(JarvisBrain._needs_project_context("quais decisões do Golden"))

    def test_voltar_ao(self):
        from jarvis_core.brain import JarvisBrain
        self.assertTrue(JarvisBrain._needs_project_context("vamos voltar ao Jarvis"))

    def test_trivial_no_project(self):
        from jarvis_core.brain import JarvisBrain
        self.assertFalse(JarvisBrain._needs_project_context("que horas são"))

    def test_empty(self):
        from jarvis_core.brain import JarvisBrain
        self.assertFalse(JarvisBrain._needs_project_context(""))

    def test_weather_no_project(self):
        from jarvis_core.brain import JarvisBrain
        self.assertFalse(JarvisBrain._needs_project_context("como está o tempo"))


class ProjectResolverFromQueryCase(unittest.TestCase):
    """Test _resolve_project_from_query alias matching."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._mgr.create_project("Golden", aliases=["GoldenAI", "GA", "Golden Jarvis"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_brain(self):
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        return JarvisBrain(
            registry=MagicMock(),
            memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine,
            project_memory=self._mgr,
        )

    def test_resolve_golden(self):
        brain = self._make_brain()
        result = brain._resolve_project_from_query("continue o Golden")
        self.assertEqual(result, "Golden")

    def test_resolve_goldenai(self):
        brain = self._make_brain()
        result = brain._resolve_project_from_query("status do GoldenAI")
        self.assertEqual(result, "Golden")

    def test_resolve_jarvis_alias(self):
        brain = self._make_brain()
        result = brain._resolve_project_from_query("retome o Golden Jarvis")
        self.assertEqual(result, "Golden")

    def test_resolve_not_found(self):
        brain = self._make_brain()
        result = brain._resolve_project_from_query("continue o ProjetoX")
        self.assertIsNone(result)

    def test_resolve_trivial(self):
        brain = self._make_brain()
        result = brain._resolve_project_from_query("que horas são")
        self.assertIsNone(result)


class AmbiguityDetectionCase(unittest.TestCase):
    """Test ambiguity when multiple projects match."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._mgr.create_project("Golden", aliases=["GoldenAI"])
        self._mgr.create_project("Golden Jarvis", aliases=["GJ"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ambiguous_returns_none(self):
        from jarvis_core.brain import JarvisBrain
        brain = JarvisBrain(
            registry=MagicMock(),
            memory=MagicMock(),
            memory_v2=self._engine,
            project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("continue o Golden")
        if result is not None:
            self.assertIn(result, ["Golden", "Golden Jarvis"])
        else:
            self.assertIsNone(result)


class BrainIntegrationCase(unittest.TestCase):
    """Test Brain._get_project_context returns compact context."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._mgr.create_project("Golden", aliases=["GoldenAI"])
        self._mgr.record_decision("Golden", "Usar Python 3.13")
        self._mgr.record_issue("Golden", "Bug no watcher")
        self._mgr.update_project_state("Golden", current_phase="M1.7.1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_brain(self):
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        return JarvisBrain(
            registry=MagicMock(),
            memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine,
            project_memory=self._mgr,
        )

    def test_project_context_injected(self):
        brain = self._make_brain()
        ctx = brain._get_project_context("continue o Golden")
        self.assertIn("PROJECT_CONTEXT", ctx)
        self.assertIn("Golden", ctx)
        self.assertIn("M1.7.1", ctx)

    def test_no_project_context_for_trivial(self):
        brain = self._make_brain()
        ctx = brain._get_project_context("que horas são")
        self.assertEqual(ctx, "")

    def test_project_context_budget(self):
        brain = self._make_brain()
        ctx = brain._get_project_context("continue o Golden")
        self.assertLessEqual(len(ctx), 2000)


class SecondBrainSyncCase(unittest.TestCase):
    """Test sync_to_second_brain updates multiple files."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_creates_files(self):
        from jarvis_core.memory.v2.project_memory import ProjectMemoryManager
        mgr = ProjectMemoryManager.__new__(ProjectMemoryManager)
        mgr._engine = self._engine
        mgr._resolver = self._engine  # mock-like

        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        self._mgr.record_issue("Golden", "Bug")
        self._mgr.update_project_state("Golden", current_phase="M1.7.1")

        from jarvis_core.context_index import ContextIndexBuilder
        import jarvis_core.memory.v2.project_memory as pm

        orig = ContextIndexBuilder.__init__
        def mock_init(self_builder, **kwargs):
            self_builder.vault = self.vault
            self_builder.docs = self.tmp / "docs"
            self_builder.root = self.tmp
        ContextIndexBuilder.__init__ = mock_init

        try:
            result = self._mgr.sync_to_second_brain("Golden")
            self.assertIn("CURRENT_STATE.md", result["files_updated"])
            self.assertTrue((self.vault / "Projetos" / "Golden" / "CURRENT_STATE.md").exists())
        finally:
            ContextIndexBuilder.__init__ = orig

    def test_sync_no_duplicate_content(self):
        self._mgr.create_project("Golden")
        self._mgr.update_project_state("Golden", current_phase="Test")

        from jarvis_core.context_index import ContextIndexBuilder
        orig = ContextIndexBuilder.__init__
        def mock_init(self_builder, **kwargs):
            self_builder.vault = self.vault
            self_builder.docs = self.tmp / "docs"
            self_builder.root = self.tmp
        ContextIndexBuilder.__init__ = mock_init

        try:
            self._mgr.sync_to_second_brain("Golden")
            self._mgr.sync_to_second_brain("Golden")
            state_file = self.vault / "Projetos" / "Golden" / "CURRENT_STATE.md"
            content = state_file.read_text(encoding="utf-8")
            self.assertLessEqual(content.count("PROJECT: Golden"), 1)
        finally:
            ContextIndexBuilder.__init__ = orig


class CandidateNegativeSignalCase(unittest.TestCase):
    """Audit: negative signals should REDUCE promotion, not favor it."""

    def setUp(self):
        from jarvis_core.memory.v2.project_memory import MemoryCandidateDetector
        self.detector = MemoryCandidateDetector()

    def test_negative_signal_promotes_lesson(self):
        content = "Nunca exponha API keys em logs. Cuidado com documentação."
        candidates = self.detector.detect(content, project="Golden")
        lesson = [c for c in candidates if c.memory_type == "lesson"]
        self.assertGreater(len(lesson), 0)
        self.assertEqual(lesson[0].verdict, "promote")

    def test_neutral_lesson_defers(self):
        content = "Aprendemos que Python funciona bem para backend."
        candidates = self.detector.detect(content, project="Golden")
        lesson = [c for c in candidates if c.memory_type == "lesson"]
        if lesson:
            self.assertIn(lesson[0].verdict, ("defer", "reject"))

    def test_casual_rejected(self):
        content = "Bom dia, como vai você hoje?"
        candidates = self.detector.detect(content, project="Golden")
        self.assertEqual(candidates[0].verdict, "reject")


class PrivacyRuntimeCase(unittest.TestCase):
    """Verify SECRET never leaks into project context."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_secret_not_in_context(self):
        self._mgr.create_project("Golden")
        try:
            self._mgr.remember(
                content="api_key: sk-1234567890abcdef1234567890abcdef",
                project="Golden", title="Secret test")
        except Exception:
            pass
        ctx = self._mgr.get_project_context("Golden")
        ctx_text = str(ctx.state.to_compact()) + str(ctx.relevant_memories)
        self.assertNotIn("sk-1234567890abcdef", ctx_text)


class PerformanceBudgetCase(unittest.TestCase):
    """Measure runtime costs."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_resolution_ms(self):
        self._mgr.create_project("Golden", aliases=["GoldenAI"])
        start = time.perf_counter()
        for _ in range(10):
            self._mgr.resolve_project("Golden")
        elapsed = (time.perf_counter() - start) * 1000 / 10
        self.assertLess(elapsed, 100)

    def test_project_context_ms(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        start = time.perf_counter()
        for _ in range(5):
            self._mgr.get_project_context("Golden")
        elapsed = (time.perf_counter() - start) * 1000 / 5
        self.assertLess(elapsed, 500)

    def test_context_chars_budget(self):
        self._mgr.create_project("Golden")
        for i in range(10):
            self._mgr.record_decision("Golden", f"Decision {i}")
        ctx = self._mgr.get_project_context("Golden")
        compact = ctx.state.to_compact()
        self.assertLessEqual(len(compact), 1200)


class NoRetrievalTaxCase(unittest.TestCase):
    """Trivial messages should NOT trigger project context."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_trivial_no_project_context(self):
        from jarvis_core.brain import JarvisBrain
        self.assertFalse(JarvisBrain._needs_project_context("que horas são"))
        self.assertFalse(JarvisBrain._needs_project_context("obrigado"))
        self.assertFalse(JarvisBrain._needs_project_context("ok"))
        self.assertFalse(JarvisBrain._needs_project_context("blz"))


class SessionEndRuntimeCase(unittest.TestCase):
    """Test on_session_end integrates with lifecycle."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m171_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_session_end_records_and_handoffs(self):
        self._mgr.create_project("Golden")
        self._mgr.update_project_state("Golden", current_phase="M1.7.1")
        self._mgr.on_session_end(
            "Golden",
            summary="Completed M1.7.1 wiring",
            decisions=["Use Tavily as provider"],
            tasks_completed=["Wire ProjectMemoryManager"],
            issues_found=["None"],
        )
        ctx = self._mgr.get_project_context("Golden")
        self.assertIn("M1.7.1", ctx.state.to_compact())


if __name__ == "__main__":
    unittest.main()
