from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audit import AuditEvent, AuditLogger
from core.config import GoldenAISettings, load_settings
from core.experiments import ExperimentRepository
from core.jobs import JobManager, JobStatus
from core.memory import EvidenceType, KnowledgeItem
from core.permissions import PermissionManager
from core.safety import EvidenceLevel, is_untrusted_content
from core.tools import CheckpointService, ToolDefinition, ToolRegistry, sha256_file
from media_study import MediaStudyService
from quant import StrategySpec


class CoreV3Tests(unittest.TestCase):
    def test_config_loads(self):
        settings = load_settings()
        self.assertTrue(settings.root.exists())
        self.assertTrue(settings.read_only)

    def test_permission_manager_blocks_write_when_read_only(self):
        manager = PermissionManager(load_settings())
        decision = manager.can_write(ROOT / "projetos" / "x.txt", explicit_authorization=True)
        self.assertFalse(decision.allowed)

    def test_audit_logger_creates_valid_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(tmp)
            path = logger.record(AuditEvent(action_type="test", status="OK", target="unit"))
            payload = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(payload["action_type"], "test")
            self.assertIn("action_id", payload)

    def test_sqlite_creates_and_recovers_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ExperimentRepository(Path(tmp) / "golden_ai.db")
            experiment_id = repo.create_experiment("Unit experiment", hypothesis="safe foundation")
            row = repo.get_experiment(experiment_id)
            self.assertIsNotNone(row)
            self.assertEqual(row["title"], "Unit experiment")

    def test_knowledge_item_preserves_evidence_level(self):
        item = KnowledgeItem(
            knowledge_id="k1",
            topic="risk",
            statement="Claim is not validated.",
            evidence_type=EvidenceType.SOURCE_CLAIM,
            source_type="video",
            source_id="s1",
            source_location="00:00",
            confidence=0.2,
            validation_status=EvidenceLevel.SOURCE_CLAIM.value,
        )
        self.assertEqual(item.evidence_type, EvidenceType.SOURCE_CLAIM)
        self.assertEqual(item.validation_status, "SOURCE_CLAIM")

    def test_job_manager_executes_simple_job(self):
        manager = JobManager(max_workers=1)
        job = manager.submit("unit", lambda: 42)
        manager.futures[job.job_id].result(timeout=5)
        self.assertEqual(manager.get(job.job_id).status, JobStatus.COMPLETED)
        self.assertEqual(manager.get(job.job_id).result, 42)

    def test_job_with_error_becomes_failed(self):
        manager = JobManager(max_workers=1)
        def fail():
            raise RuntimeError("boom")
        job = manager.submit("unit_error", fail)
        with self.assertRaises(RuntimeError):
            manager.futures[job.job_id].result(timeout=5)
        self.assertEqual(manager.get(job.job_id).status, JobStatus.FAILED)

    def test_checkpoint_create_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "sample.txt"
            source.write_text("before", encoding="utf-8")
            settings = GoldenAISettings(
                root=tmp_path,
                projects_dir=tmp_path,
                backups_dir=tmp_path / "backups",
                logs_dir=tmp_path / "logs",
                experiments_dir=tmp_path / "experiments",
                sandbox_dir=tmp_path / "sandbox",
                data_dir=tmp_path / "data",
                read_only=False,
                write_enabled=True,
                allowed_paths=(tmp_path,),
                protected_paths=(),
            )
            manager = PermissionManager(settings)
            service = CheckpointService(tmp_path / "checkpoints", manager)
            record = service.create_checkpoint(source, reason="unit")
            source.write_text("after", encoding="utf-8")
            service.restore_checkpoint(record.checkpoint_id, explicit_authorization=True)
            self.assertEqual(source.read_text(encoding="utf-8"), "before")

    def test_sha256_before_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hash.txt"
            path.write_text("a", encoding="utf-8")
            first = sha256_file(path)
            path.write_text("b", encoding="utf-8")
            self.assertNotEqual(first, sha256_file(path))

    def test_tool_registry_registers_tool(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition("hello", "hello", {}, "read", lambda: "ok"))
        self.assertEqual(registry.execute("hello"), "ok")

    def test_tool_registry_rejects_tool_without_permission(self):
        registry = ToolRegistry()
        registry.register(ToolDefinition("write", "write", {}, "write", lambda path: "bad", "write"))
        with self.assertRaises(PermissionError):
            registry.execute("write", path=str(ROOT / "projetos" / "x.txt"))

    def test_strategy_spec_keeps_unknown_fields(self):
        spec = StrategySpec(
            name="s",
            symbol="XAUUSD",
            timeframe="M5",
            unknowns={"entry_quality": "not specified"},
        )
        self.assertIn("entry_quality", spec.unknowns)

    def test_media_study_does_not_execute_content_commands(self):
        service = MediaStudyService()
        study = service.import_media("video.mp4", "video")
        self.assertEqual(study.trust_classification, "UNTRUSTED_DATA")
        self.assertTrue(is_untrusted_content("video"))
        with self.assertRaises(NotImplementedError):
            service.transcribe(study.study_id)


if __name__ == "__main__":
    unittest.main()
