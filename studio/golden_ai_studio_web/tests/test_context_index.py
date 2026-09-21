"""M1.6.1 — Segundo Cerebro / Context Index: testes completos.

Usa diretórios temporários. NUNCA modifica vault/DB de produção.
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from jarvis_core.context_index import (
    ContextIndexBuilder,
    build_master_index,
    build_project_index,
    build_current_state,
    build_file_map,
    update_context_index,
    _extract_frontmatter,
    _truncate,
)


class ExtractFrontmatterCase(unittest.TestCase):
    def test_valid_frontmatter(self):
        text = "---\nlast_updated: 2026-09-14\nscope: test\n---\nContent"
        result = _extract_frontmatter(text)
        self.assertEqual(result["last_updated"], "2026-09-14")
        self.assertEqual(result["scope"], "test")

    def test_no_frontmatter(self):
        result = _extract_frontmatter("Just content")
        self.assertEqual(result, {})

    def test_empty_frontmatter(self):
        result = _extract_frontmatter("---\n---\nContent")
        self.assertEqual(result, {})


class TruncateCase(unittest.TestCase):
    def test_short_text(self):
        self.assertEqual(_truncate("a\nb\nc", 5), "a\nb\nc")

    def test_long_text(self):
        result = _truncate("a\nb\nc\nd\ne", 3)
        self.assertIn("truncated", result)
        self.assertEqual(result.count("\n"), 3)


class MasterIndexCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        (self.vault / "00_Inbox").mkdir()
        (self.vault / "Trading").mkdir()
        (self.vault / "Coding").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_master_index_created(self):
        path = build_master_index(self.vault)
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("Segundo Cerebro", content)
        self.assertIn("Trading", content)
        self.assertIn("Coding", content)

    def test_master_index_has_frontmatter(self):
        path = build_master_index(self.vault)
        content = path.read_text(encoding="utf-8")
        fm = _extract_frontmatter(content)
        self.assertIn("last_updated", fm)
        self.assertEqual(fm["status"], "CURRENT")

    def test_master_index_idempotent(self):
        build_master_index(self.vault)
        build_master_index(self.vault)
        content = (self.vault / "00_INDEX.md").read_text(encoding="utf-8")
        self.assertLess(content.count("Segundo Cerebro"), 3)


class ProjectIndexCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_project_index_created(self):
        path = build_project_index("Golden", self.vault)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, "INDEX.md")

    def test_project_index_content(self):
        path = build_project_index("Golden", self.vault)
        content = path.read_text(encoding="utf-8")
        self.assertIn("Golden", content)


class CurrentStateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()
        self.docs = self.tmp / "docs"
        self.docs.mkdir()
        (self.docs / "CURRENT_WORK.md").write_text("# Work\nM1.6 done", encoding="utf-8")
        (self.docs / "HANDOFF.md").write_text("# Handoff\nM1.6 complete", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_current_state_created(self):
        builder = ContextIndexBuilder(vault_root=self.vault, docs_root=self.docs)
        builder.update_current_state("Golden")
        path = self.vault / "Projetos" / "Golden" / "CURRENT_STATE.md"
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("M1.6 done", content)


class FileMapCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_map_created(self):
        path = build_file_map("Golden", self.vault)
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("Mapa de Arquivos", content)


class BuildAllCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_all(self):
        builder = ContextIndexBuilder(vault_root=self.vault)
        report = builder.build_all()
        self.assertGreater(len(report["files_written"]), 0)
        self.assertTrue((self.vault / "00_INDEX.md").exists())
        self.assertTrue((self.vault / "Projetos" / "Golden" / "INDEX.md").exists())


class UpdateContextIndexCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_context_index(self):
        report = update_context_index(self.vault)
        self.assertGreater(len(report["files_written"]), 0)


class FreshnessCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_indices_have_timestamp(self):
        builder = ContextIndexBuilder(vault_root=self.vault)
        builder.build_all()
        for md in self.vault.rglob("*.md"):
            content = md.read_text(encoding="utf-8")
            fm = _extract_frontmatter(content)
            if fm:
                self.assertIn("last_updated", fm, f"{md.name} missing timestamp")
                self.assertIn("status", fm, f"{md.name} missing status")


class NoEmptyFilesCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_empty_indices(self):
        builder = ContextIndexBuilder(vault_root=self.vault)
        builder.build_all()
        for md in self.vault.rglob("*.md"):
            content = md.read_text(encoding="utf-8")
            self.assertGreater(len(content.strip()), 10, f"{md.name} is too short")


class NonexistentPathCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctx_idx_"))
        self.vault = self.tmp / "vault"
        self.vault.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_all_no_crash(self):
        builder = ContextIndexBuilder(vault_root=self.vault / "nonexistent")
        report = builder.build_all()
        self.assertIsInstance(report, dict)


if __name__ == "__main__":
    unittest.main()
