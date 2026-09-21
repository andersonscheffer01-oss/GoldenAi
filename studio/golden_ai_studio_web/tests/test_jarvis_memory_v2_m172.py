"""M1.7.2 — Auto Second Brain Sync + Dynamic Project Resolution.

Tests: dirty flag, auto sync, write-if-changed, dynamic resolution,
ambiguity, failure isolation, fast path, performance.
"""
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from jarvis_core.memory.v2.engine import GoldenMemoryEngine
from jarvis_core.memory.v2.project_memory import ProjectMemoryManager
from jarvis_core.context_index import ContextIndexBuilder


class DirtyFlagCase(unittest.TestCase):
    """Test dirty flag tracking."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_initial_clean(self):
        self.assertEqual(len(self._mgr._dirty_projects), 0)

    def test_mark_dirty_on_state_change(self):
        self._mgr.create_project("Golden")
        self._mgr.update_project_state("Golden", current_phase="M1.7.2")
        self.assertIn("Golden", self._mgr._dirty_projects)

    def test_mark_dirty_on_decision(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        self.assertIn("Golden", self._mgr._dirty_projects)

    def test_mark_dirty_on_issue(self):
        self._mgr.create_project("Golden")
        self._mgr.record_issue("Golden", "Bug")
        self.assertIn("Golden", self._mgr._dirty_projects)

    def test_mark_dirty_on_lesson(self):
        self._mgr.create_project("Golden")
        self._mgr.record_lesson("Golden", "Never expose secrets")
        self.assertIn("Golden", self._mgr._dirty_projects)

    def test_mark_dirty_on_session_end(self):
        self._mgr.create_project("Golden")
        self._mgr.on_session_end("Golden", summary="Test session")
        self.assertEqual(len(self._mgr._dirty_projects), 0)

    def test_no_dirty_on_trivial(self):
        self._mgr.create_project("Golden")
        self._mgr.get_current_state("Golden")
        self.assertEqual(len(self._mgr._dirty_projects), 0)


class AutoSyncCase(unittest.TestCase):
    """Test auto sync triggers."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._orig_ci = ContextIndexBuilder.__init__
        def mock_init(self_builder, **kwargs):
            self_builder.vault = self.vault
            self_builder.docs = self.tmp / "docs"
            self_builder.root = self.tmp
        ContextIndexBuilder.__init__ = mock_init

    def tearDown(self):
        ContextIndexBuilder.__init__ = self._orig_ci
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_session_end_triggers_sync(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        self._mgr.on_session_end("Golden", summary="Done")
        state_file = self.vault / "Projetos" / "Golden" / "CURRENT_STATE.md"
        self.assertTrue(state_file.exists())

    def test_trivial_session_no_sync(self):
        self._mgr.create_project("Golden")
        self._mgr.get_current_state("Golden")
        state_file = self.vault / "Projetos" / "Golden" / "CURRENT_STATE.md"
        self.assertFalse(state_file.exists())

    def test_sync_if_dirty(self):
        self._mgr.create_project("Golden")
        self._mgr._mark_dirty("Golden")
        results = self._mgr._sync_if_dirty()
        self.assertIn("Golden", results)
        self.assertEqual(len(self._mgr._dirty_projects), 0)

    def test_sync_failure_isolation(self):
        self._mgr.create_project("Golden")
        self._mgr._mark_dirty("Golden")
        from jarvis_core.context_index import ContextIndexBuilder
        ContextIndexBuilder.__init__ = self._orig_ci
        results = self._mgr._sync_if_dirty()
        self.assertIn("Golden", results)
        self.assertTrue("error" in results["Golden"] or len(results["Golden"].get("files_updated", [])) > 0)
        ContextIndexBuilder.__init__ = lambda s, **k: None


class WriteIfChangedCase(unittest.TestCase):
    """Test hash-based write-if-changed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_write_always_writes(self):
        path = self.tmp / "test.md"
        result = self._mgr._write_if_changed(path, "hello")
        self.assertTrue(result)
        self.assertEqual(path.read_text(encoding="utf-8"), "hello")

    def test_same_content_skips_write(self):
        path = self.tmp / "test.md"
        self._mgr._write_if_changed(path, "hello")
        result = self._mgr._write_if_changed(path, "hello")
        self.assertFalse(result)

    def test_different_content_writes(self):
        path = self.tmp / "test.md"
        self._mgr._write_if_changed(path, "hello")
        result = self._mgr._write_if_changed(path, "world")
        self.assertTrue(result)
        self.assertEqual(path.read_text(encoding="utf-8"), "world")


class DebounceCoalescingCase(unittest.TestCase):
    """Test multiple mutations → one sync."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._orig_ci = ContextIndexBuilder.__init__
        def mock_init(self_builder, **kwargs):
            self_builder.vault = self.vault
            self_builder.docs = self.tmp / "docs"
            self_builder.root = self.tmp
        ContextIndexBuilder.__init__ = mock_init

    def tearDown(self):
        ContextIndexBuilder.__init__ = self._orig_ci
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_multiple_mutations_one_sync(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Decision 1")
        self._mgr.record_issue("Golden", "Issue 1")
        self._mgr.record_lesson("Golden", "Lesson 1")
        self.assertIn("Golden", self._mgr._dirty_projects)
        self._mgr._sync_if_dirty()
        state_file = self.vault / "Projetos" / "Golden" / "CURRENT_STATE.md"
        self.assertTrue(state_file.exists())


class WatcherNoLoopCase(unittest.TestCase):
    """Test sync does not create watcher loop."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._orig_ci = ContextIndexBuilder.__init__
        def mock_init(self_builder, **kwargs):
            self_builder.vault = self.vault
            self_builder.docs = self.tmp / "docs"
            self_builder.root = self.tmp
        ContextIndexBuilder.__init__ = mock_init

    def tearDown(self):
        ContextIndexBuilder.__init__ = self._orig_ci
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_writes_deduped(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        r1 = self._mgr.sync_to_second_brain("Golden")
        r2 = self._mgr.sync_to_second_brain("Golden")
        self.assertGreater(len(r1.get("files_updated", [])), 0)
        self.assertEqual(len(r2.get("files_updated", [])), 0)
        self.assertGreater(len(r2.get("skipped", [])), 0)


class DynamicResolutionCase(unittest.TestCase):
    """Test entity-graph-based resolution without hardcoded list."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dynamic_project_resolved(self):
        self._mgr.create_project("MeuRobo", aliases=["MR", "Meu Robo"])
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        brain = JarvisBrain(
            registry=MagicMock(), memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine, project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("continue o MeuRobo")
        self.assertEqual(result, "MeuRobo")

    def test_dynamic_alias_resolved(self):
        self._mgr.create_project("MeuRobo", aliases=["MR"])
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        brain = JarvisBrain(
            registry=MagicMock(), memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine, project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("status do MR")
        self.assertEqual(result, "MeuRobo")

    def test_new_project_works_without_code_change(self):
        self._mgr.create_project("NovoProjeto", aliases=["NP"])
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        brain = JarvisBrain(
            registry=MagicMock(), memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine, project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("continue o NovoProjeto")
        self.assertEqual(result, "NovoProjeto")


class AmbiguityCase(unittest.TestCase):
    """Test AMBIGUOUS detection."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ambiguous_returns_signal(self):
        self._mgr.create_project("Golden", aliases=["ga"])
        self._mgr.create_project("GA Tools", aliases=["ga"])
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        brain = JarvisBrain(
            registry=MagicMock(), memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine, project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("continue o GA")
        self.assertEqual(result, "AMBIGUOUS")

    def test_not_found_returns_none(self):
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        brain = JarvisBrain(
            registry=MagicMock(), memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine, project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("continue o UnknownProject")
        self.assertIsNone(result)

    def test_resolved_returns_name(self):
        self._mgr.create_project("Golden")
        from jarvis_core.brain import JarvisBrain
        from jarvis_core.orchestrator import CentralOrchestrator
        brain = JarvisBrain(
            registry=MagicMock(), memory=MagicMock(),
            orchestrator=CentralOrchestrator(MagicMock()),
            memory_v2=self._engine, project_memory=self._mgr,
        )
        result = brain._resolve_project_from_query("continue o Golden")
        self.assertEqual(result, "Golden")


class FailureIsolationCase(unittest.TestCase):
    """Test sync failure does not break canonical memory."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_failure_preserves_memory(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        self._mgr._mark_dirty("Golden")
        from jarvis_core.context_index import ContextIndexBuilder
        orig = ContextIndexBuilder.__init__
        ContextIndexBuilder.__init__ = lambda s, **k: (_ for _ in ()).throw(IOError("disk full"))
        try:
            results = self._mgr._sync_if_dirty()
            self.assertIn("Golden", results)
            self.assertIn("error", results["Golden"])
        finally:
            ContextIndexBuilder.__init__ = orig
        memories = self._mgr.get_decisions("Golden")
        self.assertGreater(len(memories), 0)


class FastPathCase(unittest.TestCase):
    """Test zero tax on trivial messages."""

    def test_trivial_no_project_context(self):
        from jarvis_core.brain import JarvisBrain
        self.assertFalse(JarvisBrain._needs_project_context("ok"))
        self.assertFalse(JarvisBrain._needs_project_context("obrigado"))
        self.assertFalse(JarvisBrain._needs_project_context("que horas são"))
        self.assertFalse(JarvisBrain._needs_project_context("blz"))
        self.assertFalse(JarvisBrain._needs_project_context("")),
        self.assertFalse(JarvisBrain._needs_project_context(" sim "))
        self.assertFalse(JarvisBrain._needs_project_context("não"))
        self.assertFalse(JarvisBrain._needs_project_context("tudo bem"))
        self.assertFalse(JarvisBrain._needs_project_context("valeu"))
        self.assertFalse(JarvisBrain._needs_project_context("beleza"))
        self.assertFalse(JarvisBrain._needs_project_context("com certeza"))
        self.assertFalse(JarvisBrain._needs_project_context("entendido"))
        self.assertFalse(JarvisBrain._needs_project_context("perfeito"))
        self.assertFalse(JarvisBrain._needs_project_context("show"))
        self.assertFalse(JarvisBrain._needs_project_context("legal"))
        self.assertFalse(JarvisBrain._needs_project_context("massa"))
        self.assertFalse(JarvisBrain._needs_project_context("top"))
        self.assertFalse(JarvisBrain._needs_project_context("ok, obrigado"))
        self.assertFalse(JarvisBrain._needs_project_context("beleza, valeu"))
        self.assertFalse(JarvisBrain._needs_project_context("show de bola"))


class PerformanceCase(unittest.TestCase):
    """Measure sync performance."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m172_"))
        self.db = str(self.tmp / "test.db")
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self._engine = GoldenMemoryEngine(self.db)
        self._mgr = ProjectMemoryManager(self._engine)
        self._orig_ci = ContextIndexBuilder.__init__
        def mock_init(self_builder, **kwargs):
            self_builder.vault = self.vault
            self_builder.docs = self.tmp / "docs"
            self_builder.root = self.tmp
        ContextIndexBuilder.__init__ = mock_init

    def tearDown(self):
        ContextIndexBuilder.__init__ = self._orig_ci
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_ms(self):
        self._mgr.create_project("Golden")
        self._mgr.record_decision("Golden", "Use Python")
        start = time.perf_counter()
        self._mgr.sync_to_second_brain("Golden")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed, 500)

    def test_noop_sync_skips(self):
        self._mgr.create_project("Golden")
        self._mgr.sync_to_second_brain("Golden")
        start = time.perf_counter()
        self._mgr.sync_to_second_brain("Golden")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed, 200)


if __name__ == "__main__":
    unittest.main()
