"""M1.7 — Project Memory: testes completos.

Usa DBs temporários. NUNCA modifica vault/DB de produção.
"""
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from jarvis_core.memory.v2.project_memory import (
    ProjectMemoryManager,
    ProjectResolver,
    ProjectRecord,
    ProjectState,
    ProjectContext,
    HandoffData,
    MemoryCandidate,
    MemoryCandidateDetector,
    SessionLongTermExtractor,
    HandoffGenerator,
    ProjectStatus,
    Freshness,
    CandidateVerdict,
    Provenance,
    Scope,
    _project_canonical_key,
    _decision_key,
    _issue_key,
    _lesson_key,
    _handoff_key,
    _state_key,
    PROJECT_STATE_MAX_CHARS,
    MEMORY_RETRIEVAL_MAX_ITEMS,
    HANDOFF_MAX_CHARS,
)


class CanonicalKeyCase(unittest.TestCase):
    def test_project_canonical_key(self):
        k = _project_canonical_key("Golden", "decision", "use Tavily")
        self.assertIn("golden", k)
        self.assertIn("decision", k)
        self.assertIn("tavily", k.lower())

    def test_decision_key(self):
        k = _decision_key("Golden", "Use Python 3.13")
        self.assertIn("decision", k)
        self.assertIn("golden", k)

    def test_issue_key(self):
        k = _issue_key("Golden", "Bug in watcher")
        self.assertIn("issue", k)

    def test_lesson_key(self):
        k = _lesson_key("Golden", "Never expose secrets")
        self.assertIn("lesson", k)

    def test_handoff_key(self):
        k = _handoff_key("Golden")
        self.assertIn("handoff", k)

    def test_state_key(self):
        k = _state_key("Golden")
        self.assertIn("state", k)


class ProjectRecordCase(unittest.TestCase):
    def test_defaults(self):
        rec = ProjectRecord()
        self.assertEqual(rec.name, "")
        self.assertEqual(rec.status, "active")
        self.assertEqual(rec.aliases, [])

    def test_with_values(self):
        rec = ProjectRecord(
            entity_id=1, name="Golden", aliases=["GoldenAI"],
            root_path="C:/GoldenAI", status="active",
        )
        self.assertEqual(rec.entity_id, 1)
        self.assertEqual(rec.name, "Golden")
        self.assertIn("GoldenAI", rec.aliases)


class ProjectStateCase(unittest.TestCase):
    def test_to_compact(self):
        state = ProjectState(
            project="Golden", status="active",
            current_phase="M1.7", next_step="Test",
            blockers=["blocker1"], important_files=["engine.py"],
            known_issues=["issue1"],
        )
        text = state.to_compact()
        self.assertIn("Golden", text)
        self.assertIn("M1.7", text)
        self.assertIn("blocker1", text)
        self.assertIn("engine.py", text)
        self.assertLessEqual(len(text), PROJECT_STATE_MAX_CHARS)

    def test_freshness_in_compact(self):
        state = ProjectState(project="Golden", freshness="CURRENT")
        text = state.to_compact()
        self.assertIn("CURRENT", text)


class MemoryCandidateDetectorCase(unittest.TestCase):
    def setUp(self):
        self.detector = MemoryCandidateDetector()

    def test_empty_content(self):
        result = self.detector.detect("")
        self.assertEqual(result, [])

    def test_short_content(self):
        result = self.detector.detect("hi")
        self.assertEqual(result, [])

    def test_decision_detection(self):
        content = "Decidimos usar Tavily como provider principal. A opção foi escolhida após testes."
        result = self.detector.detect(content, project="Golden")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0].verdict, "promote")
        self.assertEqual(result[0].memory_type, "decision")

    def test_lesson_detection(self):
        content = "Nunca exponha senhas em logs. Cuidado com API keys em documentação."
        result = self.detector.detect(content, project="Golden")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0].verdict, "promote")
        self.assertEqual(result[0].memory_type, "lesson")

    def test_procedure_detection(self):
        content = "Sempre executar py_compile antes de commitar. Procedimento: passo a passo de verificação."
        result = self.detector.detect(content, project="Golden")
        self.assertGreater(len(result), 0)

    def test_status_detection(self):
        content = "M1.6 concluído. M1.7 em andamento. Próximo passo: testes."
        result = self.detector.detect(content, project="Golden")
        self.assertGreater(len(result), 0)

    def test_no_signal_reject(self):
        content = "The weather is nice today and I like programming in general."
        result = self.detector.detect(content, project="Golden")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0].verdict, "reject")

    def test_multiple_candidates(self):
        content = "Decidimos usar Tavily. Nunca esqueça: sempre compilar antes de commitar."
        result = self.detector.detect(content, project="Golden")
        self.assertGreater(len(result), 1)


class ProjectResolverCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="proj_mem_"))
        self.db_path = str(self.tmp / "test.db")
        self._cleanup_imports()

    def tearDown(self):
        self._cleanup_imports()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cleanup_imports(self):
        import importlib
        for mod_name in list(importlib.sys.modules.keys()):
            if "golden_runtime" in mod_name:
                del importlib.sys.modules[mod_name]

    def _make_engine(self):
        from jarvis_core.memory.v2.engine import GoldenMemoryEngine
        return GoldenMemoryEngine(self.db_path)

    def test_resolve_nonexistent(self):
        engine = self._make_engine()
        resolver = ProjectResolver(engine)
        result = resolver.resolve("Nonexistent")
        self.assertIsNone(result)

    def test_resolve_or_create(self):
        engine = self._make_engine()
        resolver = ProjectResolver(engine)
        rec = resolver.resolve_or_create("Golden", aliases=["GoldenAI"])
        self.assertEqual(rec.name, "Golden")
        self.assertIn("GoldenAI", rec.aliases)
        self.assertGreater(rec.entity_id, 0)

    def test_resolve_existing(self):
        engine = self._make_engine()
        resolver = ProjectResolver(engine)
        rec1 = resolver.resolve_or_create("Golden")
        rec2 = resolver.resolve_or_create("Golden")
        self.assertEqual(rec1.entity_id, rec2.entity_id)

    def test_list_projects(self):
        engine = self._make_engine()
        resolver = ProjectResolver(engine)
        resolver.resolve_or_create("Golden")
        resolver.resolve_or_create("Jarvis")
        projects = resolver.list_projects()
        names = [p.name for p in projects]
        self.assertIn("Golden", names)
        self.assertIn("Jarvis", names)

    def test_update_aliases(self):
        engine = self._make_engine()
        resolver = ProjectResolver(engine)
        rec = resolver.resolve_or_create("Golden", aliases=["GA"])
        rec2 = resolver.resolve_or_create("Golden", aliases=["GoldenAI"])
        self.assertIn("GoldenAI", rec2.aliases)
        self.assertIn("GA", rec2.aliases)


class ProjectMemoryManagerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="proj_mem_"))
        self.db_path = str(self.tmp / "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_manager(self):
        from jarvis_core.memory.v2.engine import GoldenMemoryEngine
        engine = GoldenMemoryEngine(self.db_path)
        return ProjectMemoryManager(engine)

    def test_create_project(self):
        mgr = self._make_manager()
        rec = mgr.create_project("Golden", aliases=["GoldenAI"])
        self.assertEqual(rec.name, "Golden")
        self.assertGreater(rec.entity_id, 0)

    def test_get_project(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        rec = mgr.get_project("Golden")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.name, "Golden")

    def test_list_projects(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.create_project("Jarvis")
        projects = mgr.list_projects()
        self.assertGreaterEqual(len(projects), 2)

    def test_resolve_project(self):
        mgr = self._make_manager()
        mgr.create_project("Golden", aliases=["GoldenAI", "GA"])
        rec = mgr.resolve_project("GoldenAI")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.name, "Golden")

    def test_update_project_state(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        state = mgr.update_project_state(
            "Golden",
            status="active",
            current_phase="M1.7",
            next_step="Write tests",
            blockers=["test bug"],
            important_files=["engine.py"],
        )
        self.assertEqual(state.project, "Golden")
        self.assertEqual(state.status, "active")
        self.assertEqual(state.current_phase, "M1.7")
        self.assertEqual(state.next_step, "Write tests")
        self.assertIn("test bug", state.blockers)
        self.assertIn("engine.py", state.important_files)

    def test_get_current_state_unknown(self):
        mgr = self._make_manager()
        state = mgr.get_current_state("Nonexistent")
        self.assertEqual(state.freshness, "UNKNOWN")

    def test_remember(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.remember(
            content="Test memory for Golden project",
            project="Golden",
            title="Test memory",
        )
        self.assertIsNotNone(result)

    def test_get_memories(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.remember(
            content="Golden uses Python for backend",
            project="Golden",
            title="Tech stack",
        )
        memories = mgr.get_memories("Golden")
        self.assertIsInstance(memories, list)

    def test_record_decision(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.record_decision("Golden", "Use Tavily as provider")
        self.assertIsNotNone(result)

    def test_get_decisions(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.record_decision("Golden", "Use Tavily")
        decisions = mgr.get_decisions("Golden")
        self.assertIsInstance(decisions, list)

    def test_record_issue(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.record_issue("Golden", "Watcher loop bug")
        self.assertIsNotNone(result)

    def test_get_known_issues(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.record_issue("Golden", "Bug in reconciler")
        issues = mgr.get_known_issues("Golden")
        self.assertIsInstance(issues, list)

    def test_record_lesson(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.record_lesson("Golden", "Never expose secrets")
        self.assertIsNotNone(result)

    def test_record_task_completed(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.record_task_completed("Golden", "M1.6 complete")
        self.assertIsNotNone(result)

    def test_record_status_change(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.record_status_change("Golden", "in-progress")
        self.assertIsNotNone(result)
        state = mgr.get_current_state("Golden")
        self.assertEqual(state.status, "in-progress")

    def test_generate_handoff(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.record_decision("Golden", "Use Python")
        hd = mgr.generate_handoff("Golden")
        self.assertIsInstance(hd, HandoffData)
        self.assertEqual(hd.project, "Golden")

    def test_save_handoff(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        result = mgr.save_handoff("Golden")
        self.assertIsNotNone(result)

    def test_get_handoff(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        text = mgr.get_handoff("Golden")
        self.assertIsInstance(text, str)
        self.assertIn("Golden", text)

    def test_detect_candidates(self):
        mgr = self._make_manager()
        candidates = mgr.detect_candidates(
            "Decidimos usar Tavily. A opção foi escolhida após testes.",
            project="Golden",
        )
        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0].verdict, "promote")

    def test_promote_candidate(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        candidates = mgr.detect_candidates(
            "Decidimos usar Tavily. A opção foi escolhida após testes.",
            project="Golden",
        )
        result = mgr.promote_candidate(candidates[0])
        self.assertIsNotNone(result)

    def test_get_project_context(self):
        mgr = self._make_manager()
        mgr.create_project("Golden", aliases=["GoldenAI"])
        mgr.record_decision("Golden", "Use Python 3.13")
        mgr.record_issue("Golden", "Watcher loop")
        ctx = mgr.get_project_context("Golden")
        self.assertIsInstance(ctx, ProjectContext)
        self.assertEqual(ctx.project, "Golden")
        self.assertIsNotNone(ctx.state)
        self.assertIsInstance(ctx.decisions, list)
        self.assertIsInstance(ctx.known_issues, list)
        self.assertIsInstance(ctx.handoff, str)
        self.assertGreater(ctx.token_estimate, 0)

    def test_get_global_memories(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.remember(content="Global preference: use Portuguese", project="Golden")
        globals_ = mgr.get_global_memories("preference")
        self.assertIsInstance(globals_, list)

    def test_on_session_end(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.on_session_end(
            "Golden",
            summary="Completed M1.7 tests",
            decisions=["Use Tavily"],
            tasks_completed=["Write tests"],
            issues_found=["Bug in resolver"],
        )
        state = mgr.get_current_state("Golden")
        self.assertIsNotNone(state)

    def test_sync_to_second_brain(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        mgr.update_project_state("Golden", current_phase="M1.7")
        result = mgr.sync_to_second_brain("Golden")
        self.assertIn("CURRENT_STATE.md", result["files_updated"])


class HandoffDataCase(unittest.TestCase):
    def test_to_compact(self):
        hd = HandoffData(
            project="Golden", status="active",
            done="M1.0-M1.6 done", current="M1.7",
            next_step="Test", blockers=["blocker1"],
            files=["engine.py"], decisions=["Use Python"],
            known_issues=["Bug"],
        )
        text = hd.to_compact()
        self.assertIn("Golden", text)
        self.assertIn("M1.7", text)
        self.assertLessEqual(len(text), HANDOFF_MAX_CHARS)

    def test_empty_handoff(self):
        hd = HandoffData(project="Golden")
        text = hd.to_compact()
        self.assertIn("Golden", text)


class TokenBudgetCase(unittest.TestCase):
    def test_state_max_chars(self):
        state = ProjectState(
            project="Golden", status="active",
            current_phase="M1.7",
            current_work="Building project memory",
            next_step="Write tests",
            blockers=["b1", "b2", "b3", "b4", "b5"],
            important_files=["f1.py", "f2.py", "f3.py"],
            known_issues=["i1", "i2", "i3", "i4", "i5"],
        )
        text = state.to_compact()
        self.assertLessEqual(len(text), PROJECT_STATE_MAX_CHARS)

    def test_handoff_max_chars(self):
        hd = HandoffData(
            project="Golden", status="active",
            done="A" * 500, current="B" * 500,
            next_step="C" * 500,
        )
        text = hd.to_compact()
        self.assertLessEqual(len(text), HANDOFF_MAX_CHARS)


class FreshnessCase(unittest.TestCase):
    def test_unknown_when_no_timestamp(self):
        mgr_mgr_tmp = Path(tempfile.mkdtemp(prefix="proj_mem_"))
        try:
            from jarvis_core.memory.v2.engine import GoldenMemoryEngine
            engine = GoldenMemoryEngine(str(mgr_mgr_tmp / "test.db"))
            mgr = ProjectMemoryManager(engine)
            state = mgr.get_current_state("Nonexistent")
            self.assertEqual(state.freshness, "UNKNOWN")
        finally:
            shutil.rmtree(mgr_mgr_tmp, ignore_errors=True)


class ScopeCase(unittest.TestCase):
    def test_project_scope(self):
        self.assertEqual(Scope.PROJECT.value, "project")

    def test_global_scope(self):
        self.assertEqual(Scope.GLOBAL.value, "global")


class ProvenanceCase(unittest.TestCase):
    def test_known(self):
        self.assertEqual(Provenance.KNOWN.value, "known")

    def test_inferred(self):
        self.assertEqual(Provenance.INFERRED.value, "inferred")

    def test_unknown(self):
        self.assertEqual(Provenance.UNKNOWN.value, "unknown")


class PrivacyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="proj_mem_"))
        self.db_path = str(self.tmp / "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_manager(self):
        from jarvis_core.memory.v2.engine import GoldenMemoryEngine
        engine = GoldenMemoryEngine(self.db_path)
        return ProjectMemoryManager(engine)

    def test_secret_rejected(self):
        mgr = self._make_manager()
        mgr.create_project("Golden")
        with self.assertRaises(Exception):
            mgr.remember(
                content="api_key: sk-1234567890abcdef1234567890abcdef",
                project="Golden",
                title="Secret test",
            )


if __name__ == "__main__":
    unittest.main()
