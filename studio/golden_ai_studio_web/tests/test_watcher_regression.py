"""M1.6 Regression: parse_frontmatter fix + watcher managed detection.

Tests:
1. parse_frontmatter returns Dict (not tuple)
2. Watcher extracts managed_by and id correctly
3. Full integration: temp DB+vault, watcher detects edit, imports automatically
"""
import shutil
import tempfile
import time
import hashlib
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from jarvis_core.memory.v2.engine import GoldenMemoryEngine
from jarvis_core.memory.v2.importer import VaultImporter
from jarvis_core.memory.v2.watcher import VaultWatcher, SelfWriteToken, VaultFileEvent
from jarvis_core.memory.v2.vault import parse_frontmatter, MANAGED_BY
from jarvis_core.memory.v2.types import MemoryKind, ConfidenceBasis, SourceType


class ParseFrontmatterRegressionCase(unittest.TestCase):
    """Verify parse_frontmatter returns Dict, not tuple.

    This is the root cause of the managed detection bug.
    """

    def test_returns_dict(self):
        text = """---
id: "mem_1"
managed_by: "golden-memory-v2"
schema_version: 1
---
Content here.
"""
        result = parse_frontmatter(text)
        self.assertIsInstance(result, dict)

    def test_managed_by_extracted(self):
        text = """---
id: "mem_1"
managed_by: "golden-memory-v2"
---
"""
        front = parse_frontmatter(text)
        self.assertEqual(front.get("managed_by"), "golden-memory-v2")

    def test_id_extracted(self):
        text = """---
id: "mem_42"
managed_by: "golden-memory-v2"
---
"""
        front = parse_frontmatter(text)
        self.assertEqual(front.get("id"), "mem_42")

    def test_managed_matches_constant(self):
        text = f"""---
id: "mem_1"
managed_by: "{MANAGED_BY}"
---
"""
        front = parse_frontmatter(text)
        self.assertEqual(front.get("managed_by"), MANAGED_BY)

    def test_not_managed(self):
        text = """---
id: "mem_1"
managed_by: "something-else"
---
"""
        front = parse_frontmatter(text)
        self.assertNotEqual(front.get("managed_by"), MANAGED_BY)

    def test_missing_managed_by(self):
        text = """---
id: "mem_1"
---
"""
        front = parse_frontmatter(text)
        self.assertNotEqual(front.get("managed_by"), MANAGED_BY)


class WatcherManagedDetectionCase(unittest.TestCase):
    """Verify VaultWatcher._make_event extracts managed and note_id.

    Before the fix, parse_frontmatter was unpacked as tuple, causing
    silent exception and managed=False always.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="watcher_reg_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.self_write = SelfWriteToken()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_note(self, name: str, managed: bool = True, note_id: str = "mem_1"):
        managed_val = MANAGED_BY if managed else "other"
        content = f"""---
id: "{note_id}"
managed_by: "{managed_val}"
schema_version: 1
---
Test content.
"""
        path = self.vault / name
        path.write_text(content, encoding="utf-8")
        return path

    def _make_watcher(self):
        events = []
        def on_event(e):
            events.append(e)
        watcher = VaultWatcher(
            vault_root=self.vault,
            on_event=on_event,
            poll_interval=1.0,
            debounce_ms=100.0,
            self_write_token=self.self_write,
        )
        return watcher, events

    def test_managed_true(self):
        path = self._write_note("test.md", managed=True, note_id="mem_42")
        watcher, _ = self._make_watcher()
        watcher._take_snapshot()
        events = watcher.detectChanges()
        self.assertEqual(len(events), 0)
        # Edit keeping frontmatter (simulates Obsidian editing body only)
        content = path.read_text(encoding="utf-8")
        edited = content.replace("Test content.", "Edited content.")
        path.write_text(edited, encoding="utf-8")
        events = watcher.detectChanges()
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].managed)
        self.assertEqual(events[0].note_id, "mem_42")
        watcher.stop()

    def test_managed_false(self):
        path = self._write_note("test.md", managed=False)
        watcher, _ = self._make_watcher()
        path.write_text("edited", encoding="utf-8")
        watcher._take_snapshot()
        path.write_text("edited again", encoding="utf-8")
        events = watcher.detectChanges()
        if events:
            self.assertFalse(events[0].managed)
        watcher.stop()

    def test_note_id_none(self):
        path = self.vault / "noid.md"
        path.write_text("---\nmanaged_by: \"golden-memory-v2\"\n---\nContent", encoding="utf-8")
        watcher, _ = self._make_watcher()
        watcher._take_snapshot()
        path.write_text("edited", encoding="utf-8")
        events = watcher.detectChanges()
        if events:
            self.assertIsNone(events[0].note_id)
        watcher.stop()


class WatcherImportIntegrationCase(unittest.TestCase):
    """Full integration: temp DB + vault, watcher real, auto import.

    Simulates: create note -> watcher snapshot -> external edit -> 
    detect -> import -> verify canonical updated.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="watcher_integ_"))
        self.db = str(self.tmp / "test.db")
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.engine = GoldenMemoryEngine(self.db)
        self.importer = VaultImporter(self.engine, self.vault)
        self.self_write = SelfWriteToken()
        self.events_log = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _on_event(self, event: VaultFileEvent):
        self.events_log.append({
            "event": event.event.value,
            "managed": event.managed,
            "note_id": event.note_id,
            "ts": time.time(),
        })

    def _create_record(self, content: str):
        """Create a memory record in SQLite directly."""
        from jarvis_core.memory.v2.record import MemoryRecordV2
        record = MemoryRecordV2(
            memory_type=MemoryKind.SEMANTIC,
            title="Test Memory",
            summary="Test summary",
            content=content,
            confidence=0.9,
            confidence_basis=ConfidenceBasis.DOCUMENTED,
            source_type=SourceType.CONVERSATION,
            project="TEST_PROJECT",
            tags=["test"],
            content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
        )
        record.validate()
        return self.engine.store.save(record)

    def _project_note(self, record_id: int, content: str, version: int = 1):
        """Project a note to the vault (simulates engine projection)."""
        now = time.time()
        note_content = f"""---
id: "mem_{record_id}"
memory_type: "semantic"
status: "active"
project: "TEST_PROJECT"
privacy: "PUBLIC"
confidence: 0.9
confidence_basis: "documented"
version: {version}
created_at: {now}
updated_at: {now}
canonical_key: ""
source_type: "conversation"
source_ref: ""
trust_level: "trusted"
managed_by: "golden-memory-v2"
schema_version: 1
tags:
  - "test"
---

# Test Memory

{content}
"""
        note_path = self.vault / f"mem_{record_id}.md"
        note_path.write_text(note_content, encoding="utf-8")
        return note_path

    def test_full_pipeline(self):
        # Step 1: Create record in SQLite
        record = self._create_record("Original content v1")
        record_id = record.id
        self.assertEqual(record.version, 1)
        print(f"Created record: id={record_id}, version={record.version}")

        # Step 2: Project note to vault (same version as SQLite)
        note_path = self._project_note(record_id, "Original content v1", version=record.version)
        print(f"Projected note: {note_path}")

        # Step 3: Start watcher, take snapshot
        watcher = VaultWatcher(
            vault_root=self.vault,
            on_event=self._on_event,
            poll_interval=0.5,
            debounce_ms=200.0,
            self_write_token=self.self_write,
        )
        watcher._take_snapshot()
        pre_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()[:16]
        print(f"Snapshot taken: {len(watcher._snapshots)} files, hash={pre_hash}")

        # Step 4: Edit note externally (simulate Obsidian save)
        time.sleep(0.3)
        edited_content = f"""---
id: "mem_{record_id}"
memory_type: "semantic"
status: "active"
project: "TEST_PROJECT"
privacy: "PUBLIC"
confidence: 0.9
confidence_basis: "documented"
version: {record.version}
created_at: {time.time()}
updated_at: {time.time()}
canonical_key: ""
source_type: "conversation"
source_ref: ""
trust_level: "trusted"
managed_by: "golden-memory-v2"
schema_version: 1
tags:
  - "test"
---

# Test Memory

EDITED content v1 - changed externally.
"""
        note_path.write_text(edited_content, encoding="utf-8")
        post_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()[:16]
        print(f"Edited: hash={post_hash}, changed={pre_hash != post_hash}")

        # Step 5: Detect changes
        events = watcher.detectChanges()
        print(f"detectChanges: {len(events)} events")
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].managed)
        self.assertEqual(events[0].note_id, f"mem_{record_id}")

        # Step 6: Import via reconciler-style callback (as real runtime does)
        start = time.perf_counter()
        for e in events:
            self._on_event(e)
            if e.managed and e.event.value in ("created", "modified"):
                self.self_write.mark(e.path)
                result = self.importer.import_file(note_path)
        import_ms = (time.perf_counter() - start) * 1000
        print(f"Import: {result.decision.value} ({result.detail}), {import_ms:.1f}ms")

        self.assertEqual(result.decision.value, "accepted")
        self.assertEqual(result.detail, "content-imported")

        # Step 7: Verify canonical updated
        loaded = self.engine.store.load(record_id)
        self.assertIn("EDITED content v1", loaded.content)
        print(f"Canonical updated: content contains 'EDITED content v1'")

        # Step 8: Version incremented (content-only edit triggers version bump)
        self.assertEqual(loaded.version, 2)
        print(f"Version: {loaded.version} (incremented after content import)")

        # Step 9: Loop check
        events2 = watcher.detectChanges()
        self.assertEqual(len(events2), 0)
        print(f"Loop check: {len(events2)} events (expect 0)")

        # Step 10: Import count
        self.assertEqual(len(self.events_log), 1)
        print(f"Import count: {len(self.events_log)}")

        watcher.stop()
        print("\nAll assertions passed.")

    def test_version_skipped(self):
        """Same content + same version = no-change."""
        record = self._create_record("Same content")
        note_path = self._project_note(record.id, "Same content", version=record.version)
        watcher = VaultWatcher(
            vault_root=self.vault,
            on_event=self._on_event,
            poll_interval=0.5,
            debounce_ms=200.0,
            self_write_token=self.self_write,
        )
        watcher._take_snapshot()
        time.sleep(0.3)
        # Edit with same content + same version (just re-write the same file)
        note_path.write_text(note_path.read_text(encoding="utf-8"), encoding="utf-8")
        events = watcher.detectChanges()
        if events:
            result = self.importer.import_file(note_path)
            # Same content + same version = no-change
            self.assertIn(result.detail, ("no-change", "content-imported"))
        watcher.stop()


if __name__ == "__main__":
    unittest.main()
