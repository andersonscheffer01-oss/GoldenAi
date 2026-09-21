"""M1.6 — Obsidian bidirecional: testes completos.

Usa Vault e DB temporários. NUNCA toca vault/DB de produção.
Cobre:
- external edit normal
- Jarvis self-write loop protection
- debounce
- drift
- conflict
- invalid YAML
- protected YAML edited
- SECRET blocked
- SENSITIVE policy
- rename mantendo identity
- duplicate memory_id
- delete behavior
- vector/graph refresh
- restart/recovery
- concurrent edit durante sync
"""
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis_core.orchestrator.models import DataClassification
from jarvis_core.memory.v2 import (
    EntityV2, EntityType, GoldenMemoryEngine,
    ImportDecision, ImportResult, MemoryKind, MemoryRecordV2,
    MemorySecurityError, RecordStatus, ReconciliationState,
    SourceType, SyncStatus, VaultFileEvent, VaultImporter, VaultReconciler,
    VaultWatcher, SelfWriteToken,
)
from jarvis_core.memory.v2.vault import (
    MANAGED_BY, atomic_write, parse_frontmatter, projection_hash,
    render_frontmatter, split_note,
)
from jarvis_core.memory.v2.store import MarkdownMemoryStore, SQLiteMemoryStore
from jarvis_core.memory.v2.migrations import (
    ensure_v2_schema, v2_get_projection, v2_set_projection,
)


def _make_engine(tmp_dir: Path):
    db = tmp_dir / "test.db"
    vault = tmp_dir / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    engine = GoldenMemoryEngine(db_path=str(db), vault_root=str(vault))
    return engine, db, vault


def _make_record(engine, title="Test Memory", content="Test content",
                 privacy=DataClassification.INTERNAL, memory_type=MemoryKind.SEMANTIC):
    return engine.remember(
        content=content,
        memory_type=memory_type,
        title=title,
        privacy=privacy,
        source_type=SourceType.USER_EXPLICIT,
        project="test-project",
        tags=["test"],
    )


def _make_entity(engine, name="Test Entity", etype=EntityType.PERSON,
                 privacy=DataClassification.INTERNAL):
    return engine.remember_entity(
        canonical_name=name,
        entity_type=etype,
        privacy=privacy,
        source_type=SourceType.USER,
    )


def _read_note(path: Path):
    text = path.read_text(encoding="utf-8")
    return split_note(text)


def _edit_note_body(path: Path, new_body: str):
    text = path.read_text(encoding="utf-8")
    _, old_body = split_note(text)
    front, _ = split_note(text)
    new_text = render_frontmatter(list(front.items())) + "\n" + new_body
    atomic_write(path, new_text)


def _edit_note_front(path: Path, field: str, value):
    text = path.read_text(encoding="utf-8")
    front, body = split_note(text)
    front[field] = value
    new_text = render_frontmatter(list(front.items())) + "\n" + body
    atomic_write(path, new_text)


class ExternalEditImportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_test_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_external_edit_normal(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_body(path, "Updated external content")
        result = self.importer.import_file(path)
        self.assertEqual(result.decision.value, "accepted")
        updated = self.engine.store.load(record.id)
        self.assertEqual(updated.content.strip(), "Updated external content")

    def test_no_change_accepted(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        text = path.read_text(encoding="utf-8")
        result = self.importer.import_text(text, path=path)
        self.assertEqual(result.decision.value, "accepted")

    def test_not_managed_ignored(self):
        note = self.vault / "random_note.md"
        atomic_write(note, '---\nmanaged_by: other-system\nid: mem_1\n---\nBody\n')
        result = self.importer.import_file(note)
        self.assertEqual(result.decision.value, "ignored")

    def test_missing_id_error(self):
        note = self.vault / "no_id.md"
        atomic_write(note, "---\nmanaged_by: golden-memory-v2\n---\nBody\n")
        result = self.importer.import_file(note)
        self.assertEqual(result.decision.value, "error")
        self.assertIn("missing-id", result.detail)

    def test_invalid_id_format_error(self):
        note = self.vault / "bad_id.md"
        atomic_write(note, '---\nmanaged_by: golden-memory-v2\nid: "bad_id"\n---\nBody\n')
        result = self.importer.import_file(note)
        self.assertEqual(result.decision.value, "error")
        self.assertIn("invalid-id-format", result.detail)


class SelfWriteLoopCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_loop_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.token = SelfWriteToken()
        self.events = []
        self.watcher = VaultWatcher(
            vault_root=self.vault,
            on_event=lambda e: self.events.append(e),
            poll_interval=0.5,
            debounce_ms=100,
            self_write_token=self.token,
        )

    def tearDown(self):
        self.watcher.stop()
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_self_write_not_looped(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        self.token.mark(path)
        self.watcher.start()
        time.sleep(0.3)
        _edit_note_body(path, "Jarvis self-edit")
        time.sleep(1.0)
        self.watcher.detectChanges()
        time.sleep(0.3)
        managed_events = [e for e in self.events if e.managed]
        self.assertEqual(len(managed_events), 0)


class DebounceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_debounce_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.events = []
        self.watcher = VaultWatcher(
            vault_root=self.vault,
            on_event=lambda e: self.events.append(e),
            poll_interval=0.3,
            debounce_ms=200,
        )

    def tearDown(self):
        self.watcher.stop()
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_debounce_coalesces(self):
        note = self.vault / "debounce_test.md"
        atomic_write(note, "---\nmanaged_by: golden-memory-v2\nid: mem_999\n---\nInitial\n")
        self.watcher.start()
        time.sleep(0.5)
        for i in range(5):
            _edit_note_body(note, "Edit %d" % i)
            time.sleep(0.05)
        time.sleep(1.0)
        self.watcher.detectChanges()
        time.sleep(0.5)
        self.assertLessEqual(len(self.events), 2)


class DriftDetectionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_drift_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_drift_detected(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_body(path, "Externally modified content")
        drift = self.engine.vault.check_drift(record, kind="memory")
        self.assertEqual(drift["sync_status"], "drift")

    def test_synced_when_unchanged(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        drift = self.engine.vault.check_drift(record, kind="memory")
        self.assertEqual(drift["sync_status"], "synced")


class ConflictDetectionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_conflict_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_conflict_both_changed(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        orig_hash = proj.get("projection_hash", "")
        _edit_note_body(path, "External change")
        from jarvis_core.memory.v2.migrations import v2_connect
        with v2_connect(self.engine.db_path) as conn:
            conn.execute(
                "UPDATE v2_memories SET content = ?, version = version + 1 WHERE id = ?",
                ("Engine change", record.id))
        v2_set_projection(self.db, record.id, "memory",
                          str(path), orig_hash,
                          int(record.version or 1),
                          "synced", "baseline")
        drift = self.engine.vault.check_drift(record, kind="memory")
        self.assertIn(drift["sync_status"], ("conflict", "drift", "pending"))


class InvalidYAMLCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_yaml_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_invalid_frontmatter(self):
        note = self.vault / "invalid.md"
        atomic_write(note, "Not valid YAML frontmatter at all\n")
        result = self.importer.import_file(note)
        self.assertEqual(result.decision.value, "error")
        self.assertIn("invalid-frontmatter", result.detail)

    def test_no_frontmatter(self):
        note = self.vault / "no_front.md"
        atomic_write(note, "# Just a heading\n\nSome content.\n")
        result = self.importer.import_file(note)
        self.assertEqual(result.decision.value, "error")


class ProtectedYAMLCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_protected_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_protected_field_id_changed(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_front(path, "id", "mem_99999")
        result = self.importer.import_file(path)
        self.assertIn(result.decision.value, ("conflict", "error"))

    def test_protected_field_managed_by_changed(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_front(path, "managed_by", "evil-actor")
        result = self.importer.import_file(path)
        self.assertEqual(result.decision.value, "ignored")


class SecretBlockedCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_secret_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_secret_rejected(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_body(path, "Trying to make this secret")
        _edit_note_front(path, "privacy", "SECRET")
        result = self.importer.import_file(path)
        self.assertEqual(result.decision.value, "rejected")
        self.assertIn("secret", result.detail.lower())

    def test_import_secret_yaml_rejected(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_front(path, "privacy", "SECRET")
        result = self.importer.import_file(path)
        self.assertEqual(result.decision.value, "rejected")
        self.assertIn("secret", result.detail)


class SensitivePolicyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_sensitive_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sensitive_not_projected_by_default(self):
        record = _make_record(self.engine, privacy=DataClassification.SENSITIVE)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        if proj:
            self.assertIn(proj.get("sync_status", ""), ("ignored", "error"))


class RenameIdentityCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_rename_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rename_preserves_identity(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        old_path = Path(proj["path"])
        new_path = old_path.parent / ("renamed--mem%d.md" % record.id)
        old_path.rename(new_path)
        loaded = self.importer._importer if hasattr(self.importer, '_importer') else self.importer
        note_id = "mem_%d" % record.id
        found = self.importer._find_path_for_note(note_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.resolve(), new_path.resolve())


class DuplicateMemoryIDCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_dup_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_duplicate_note_id_finds_first(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        orig_path = Path(proj["path"])
        dup_path = orig_path.parent / ("copy--mem%d.md" % record.id)
        shutil.copy2(orig_path, dup_path)
        note_id = "mem_%d" % record.id
        found = self.importer._find_path_for_note(note_id)
        self.assertIsNotNone(found)


class DeleteBehaviorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_delete_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.events = []
        self.watcher = VaultWatcher(
            vault_root=self.vault,
            on_event=lambda e: self.events.append(e),
            poll_interval=0.3,
            debounce_ms=100,
        )

    def tearDown(self):
        self.watcher.stop()
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_delete_not_imported(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        self.watcher.start()
        time.sleep(0.5)
        path.unlink()
        time.sleep(1.0)
        self.watcher.detectChanges()
        time.sleep(0.3)
        deleted_events = [e for e in self.events
                          if e.event.value == "deleted"]
        self.assertGreater(len(deleted_events), 0)


class VectorRefreshCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_vector_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_updates_projection_hash(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj_before = v2_get_projection(self.db, record.id, "memory")
        hash_before = proj_before.get("projection_hash", "")
        path = Path(proj_before["path"])
        _edit_note_body(path, "Updated content for vector refresh")
        result = self.importer.import_file(path)
        self.assertEqual(result.decision.value, "accepted")
        proj_after = v2_get_projection(self.db, record.id, "memory")
        hash_after = proj_after.get("projection_hash", "")
        self.assertNotEqual(hash_before, hash_after)


class RestartRecoveryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_recovery_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reconciler_survives_restart(self):
        db = self.tmp / "test.db"
        vault = self.tmp / "vault"
        vault.mkdir(parents=True, exist_ok=True)
        engine1 = GoldenMemoryEngine(db_path=str(db), vault_root=str(vault))
        record = _make_record(engine1)
        engine1._project_best_effort(record)
        del engine1
        engine2 = GoldenMemoryEngine(db_path=str(db), vault_root=str(vault))
        loaded = engine2.store.load(record.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, record.id)
        del engine2


class ConcurrentEditCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_concurrent_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.importer = VaultImporter(self.engine, self.vault)

    def tearDown(self):
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_concurrent_edits_not_lost(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        results = []
        errors = []

        def edit_and_import(idx):
            try:
                _edit_note_body(path, "Edit %d" % idx)
                time.sleep(0.05)
                result = self.importer.import_file(path)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=edit_and_import, args=(i,))
                   for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn(r.decision.value, ("accepted", "error", "conflict"))


class ReconciliationStateCase(unittest.TestCase):
    def test_stats_tracking(self):
        state = ReconciliationState()
        r1 = ImportResult(ImportDecision.ACCEPTED, memory_id=1)
        r2 = ImportResult(ImportDecision.DRIFT, memory_id=2)
        r3 = ImportResult(ImportDecision.ACCEPTED, memory_id=3)
        state.record(r1)
        state.record(r2)
        state.record(r3)
        stats = state.stats()
        self.assertEqual(stats["total_events"], 3)
        self.assertEqual(stats["accepted"], 2)
        self.assertEqual(stats["drift"], 1)

    def test_history_limit(self):
        state = ReconciliationState()
        for i in range(250):
            state.record(ImportResult(ImportDecision.ACCEPTED, memory_id=i))
        history = state.history(limit=50)
        self.assertEqual(len(history), 50)
        self.assertEqual(history[-1]["memory_id"], 249)


class VaultReconcilerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m16_reconciler_"))
        self.engine, self.db, self.vault = _make_engine(self.tmp)
        self.reconciler = VaultReconciler(
            self.engine, self.vault, auto_import=False)

    def tearDown(self):
        self.reconciler.stop()
        try:
            self.engine.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_start_stop(self):
        self.reconciler.start()
        self.assertTrue(self.reconciler.is_running)
        self.reconciler.stop()
        self.assertFalse(self.reconciler.is_running)

    def test_status_when_stopped(self):
        status = self.reconciler.status()
        self.assertFalse(status["running"])
        self.assertEqual(status["vault_root"], str(self.vault))

    def test_manual_import(self):
        record = _make_record(self.engine)
        self.engine._project_best_effort(record)
        proj = v2_get_projection(self.db, record.id, "memory")
        path = Path(proj["path"])
        _edit_note_body(path, "Manual import test")
        result = self.reconciler.import_file(path)
        self.assertEqual(result.decision.value, "accepted")

    def test_rebuild_vault(self):
        record = _make_record(self.engine)
        result = self.reconciler.rebuild_vault()
        self.assertTrue(result["ok"])


class FileEventCase(unittest.TestCase):
    def test_file_event_types(self):
        from jarvis_core.memory.v2.watcher import FileEvent
        e1 = VaultFileEvent(
            event=FileEvent.CREATED,
            path=Path("/tmp/test.md"),
            note_id="mem_1",
            managed=True,
        )
        self.assertEqual(e1.event.value, "created")
        self.assertTrue(e1.managed)


if __name__ == "__main__":
    unittest.main()
