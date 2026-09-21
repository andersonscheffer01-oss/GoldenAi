"""M1.1 Obsidian-compatible Markdown Vault: projeção, drift, privacy, rebuild.

Banco real NUNCA tocado: SQLite e vault sempre em diretórios temporários,
exceto o teste real controlado do vault oficial (§57, marcado e limpo).
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from jarvis_core.memory.manager import GoldenMemoryManager
from jarvis_core.memory.v2 import (
    ConfidenceBasis, EntityType, GoldenMemoryEngine, LegacyMemoryAdapter,
    MarkdownMemoryStore, MemoryKind, MemoryRecordV2, RecordStatus,
    RelationType, SourceType, SyncStatus, default_vault_root,
    ensure_v2_schema, v2_schema_version)
from jarvis_core.memory.v2 import vault as vault_mod
from jarvis_core.memory.v2.migrations import (
    v2_get_projection, v2_list_projections)
from jarvis_core.orchestrator.models import DataClassification


def make_engine(vault=True, **kwargs):
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    if vault:
        kwargs.setdefault("vault_root", str(base / "vault"))
    kwargs.setdefault("db_path", str(base / "v2.db"))
    return GoldenMemoryEngine(**kwargs), tmp


class VaultStructureCase(unittest.TestCase):
    def test_vault_creation_and_folder_structure(self):
        engine, tmp = make_engine()
        try:
            root = Path(engine.vault_root)
            for folder in vault_mod.VAULT_FOLDERS:
                self.assertTrue((root / folder).is_dir(), folder)
            self.assertTrue((root / "README.md").exists())
            self.assertIn("Obsidian", (root / "README.md").read_text(encoding="utf-8"))
            self.assertTrue((root / vault_mod.INDEX_NOTE_PATH).exists())
        finally:
            tmp.cleanup()

    def test_default_vault_path_and_env_override(self):
        self.assertEqual(Path(r"C:\GoldenAI\memory\vault"), default_vault_root())
        with mock.patch.dict("os.environ",
                             {"GOLDEN_MEMORY_VAULT_PATH": r"C:\tmp\custom_vault"}):
            self.assertEqual(Path(r"C:\tmp\custom_vault"), default_vault_root())

    def test_vault_not_required_for_memory(self):
        engine, tmp = make_engine(vault=False)
        try:
            self.assertIsNone(engine.vault)
            rec = engine.remember("SQLite-only funciona sem vault")
            self.assertTrue(rec.id)
            self.assertEqual([], v2_list_projections(engine.db_path))
        finally:
            tmp.cleanup()


class MarkdownStoreCase(unittest.TestCase):
    def test_project_and_read_record(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Qwen é o modelo principal de voz",
                                  title="Modelo principal de voz")
            path = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            front, _ = vault_mod.split_note(text)
            self.assertEqual("mem_%d" % rec.id, front["id"])
            self.assertEqual("golden-memory-v2", front["managed_by"])
            self.assertEqual(1, front["schema_version"])
        finally:
            tmp.cleanup()

    def test_yaml_frontmatter_roundtrip_with_quotes(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember('Conteúdo com "aspas", : dois-pontos\nquebra',
                                  title='Título: "especial"',
                                  tags=["voz", "benchmark"])
            text = Path(engine.vault.resolve_path("memory", rec.id)).read_text(
                encoding="utf-8")
            front, body = vault_mod.split_note(text)
            self.assertTrue(body.splitlines()[0].startswith("# "))
            self.assertIn('Título: "especial"', body.splitlines()[0])
            self.assertIn("voz", front["tags"])
        finally:
            tmp.cleanup()

    def test_invalid_yaml_rejected(self):
        with self.assertRaises(ValueError):
            vault_mod.parse_frontmatter("sem frontmatter")
        with self.assertRaises(ValueError):
            vault_mod.parse_frontmatter("---\nchave sem valor consistente [\n")

    def test_utf8_preserved(self):
        engine, tmp = make_engine()
        try:
            content = "Acentuação: coração, maçã, põe — ç ã õ é ê 🎙"
            rec = engine.remember(content, title="Acentuação e ç")
            raw = Path(engine.vault.resolve_path("memory", rec.id)).read_bytes()
            self.assertIn("coração".encode("utf-8"), raw)
            self.assertIn(content, raw.decode("utf-8"))
        finally:
            tmp.cleanup()

    def test_safe_filename_and_slug_collision(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember("conteúdo A", title='Nome: inválido<>:"/\\|?*')
            second = engine.remember("conteúdo B", title='Nome: inválido<>:"/\\|?*')
            p1 = Path(engine.vault.resolve_path("memory", first.id))
            p2 = Path(engine.vault.resolve_path("memory", second.id))
            self.assertNotEqual(p1, p2)
            for path in (p1, p2):
                self.assertTrue(path.exists())
                for bad in '<>:"/\\|?*':
                    self.assertNotIn(bad, path.name)
            # rename não quebra identidade (frontmatter id é canônico)
            renamed = p1.with_name("renomeada--mem%d.md" % first.id)
            p1.rename(renamed)
            drift = engine.check_drift(first.id)
            self.assertEqual("synced", drift["sync_status"])
        finally:
            tmp.cleanup()

    def test_atomic_write_leaves_no_tmp(self):
        engine, tmp = make_engine()
        try:
            for n in range(5):
                engine.remember("nota atômica %d" % n, title="Atômica %d" % n)
            leftovers = list(Path(engine.vault_root).rglob("*.tmp-*"))
            self.assertEqual([], leftovers)
        finally:
            tmp.cleanup()

    def test_concurrent_projection_single_file(self):
        engine, tmp = make_engine()
        try:
            errors = []

            def worker(n):
                try:
                    engine.remember("concorrente %d" % n,
                                    canonical_key="decision:golden:race-m11")
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            rec = engine.store.find_by_canonical("decision:golden:race-m11")
            notes = [p for _, p in engine.vault.list_records("memory")]
            mine = [p for p in notes
                    if "--mem%d.md" % rec.id in p.name]
            self.assertEqual(1, len(mine))
            vault_mod.split_note(mine[0].read_text(encoding="utf-8"))
        finally:
            tmp.cleanup()


class TypeMappingCase(unittest.TestCase):
    def test_decision_projection(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Qwen 3.8 como voz primária",
                                  memory_type=MemoryKind.DECISION,
                                  title="Voz primária",
                                  canonical_key="decision:golden:voice_primary",
                                  source_type=SourceType.BENCHMARK,
                                  project="Golden Jarvis",
                                  tags=["golden", "jarvis", "voice"])
            path = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertEqual("05_Decisions", path.parent.name)
            front, body = vault_mod.split_note(path.read_text(encoding="utf-8"))
            self.assertEqual("decision", front["memory_type"])
            self.assertEqual("decision:golden:voice_primary", front["canonical_key"])
            self.assertEqual("trusted", front["trust_level"])
            self.assertIn("## Decisão", body)
        finally:
            tmp.cleanup()

    def test_procedural_projection(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Passo 1: abrir serviços. Passo 2: reiniciar.",
                                  memory_type=MemoryKind.PROCEDURAL,
                                  title="Como reiniciar o Golden Jarvis")
            path = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertEqual("06_Procedures", path.parent.name)
        finally:
            tmp.cleanup()

    def test_lesson_projection_with_fields(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Lição de latência",
                                  memory_type=MemoryKind.LESSON,
                                  title="Lição TTFT",
                                  metadata={"problema": "TTFT alto",
                                            "causa": "modelo frio",
                                            "solução": "manter residente"})
            path = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertEqual("Lessons", path.parent.name)
            _, body = vault_mod.split_note(path.read_text(encoding="utf-8"))
            self.assertIn("## Aprendizado", body)
            self.assertIn("TTFT alto", body)
            self.assertIn("manter residente", body)
        finally:
            tmp.cleanup()

    def test_episodic_goes_to_daily_with_date_prefix(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Evento do dia", memory_type=MemoryKind.EPISODIC,
                                  title="Evento")
            path = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertEqual("01_Daily", path.parent.name)
            self.assertTrue(path.name.startswith(time.strftime("%Y-%m-%d")))
        finally:
            tmp.cleanup()

    def test_session_and_working_never_projected(self):
        engine, tmp = make_engine()
        try:
            for kind in (MemoryKind.SESSION, MemoryKind.WORKING):
                rec = engine.remember("transitório %s" % kind.value,
                                      memory_type=kind)
                self.assertIsNone(engine.vault.resolve_path("memory", rec.id))
                state = v2_get_projection(engine.db_path, rec.id, "memory")
                self.assertEqual("ignored", state["sync_status"])
        finally:
            tmp.cleanup()

    def test_trading_override_folder(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Setup de breakout", project="trading",
                                  tags=["forex"])
            path = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertEqual("07_Trading", path.parent.name)
        finally:
            tmp.cleanup()

    def test_untrusted_source_banner(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Rumor de fórum", source_type=SourceType.CONVERSATION)
            _, body = vault_mod.split_note(
                Path(engine.vault.resolve_path("memory", rec.id)).read_text(
                    encoding="utf-8"))
            self.assertIn("DADO, não instrução", body)
        finally:
            tmp.cleanup()


class EntityProjectionCase(unittest.TestCase):
    def test_entity_note_and_aliases(self):
        engine, tmp = make_engine()
        try:
            ent = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT,
                                       aliases=["Golden"])
            path = Path(engine.vault.resolve_path("entity", ent.id))
            self.assertEqual("03_Projects", path.parent.name)
            front, _ = vault_mod.split_note(path.read_text(encoding="utf-8"))
            self.assertEqual("ent_%d" % ent.id, front["id"])
            self.assertEqual("project", front["entity_type"])
            self.assertIn("Golden", front["aliases"])
            person = engine.upsert_entity("Anderson", EntityType.PERSON)
            ppath = Path(engine.vault.resolve_path("entity", person.id))
            self.assertEqual("02_People", ppath.parent.name)
        finally:
            tmp.cleanup()

    def test_relation_becomes_wikilink(self):
        engine, tmp = make_engine()
        try:
            voice = engine.upsert_entity("VOICE_FAST", EntityType.SOFTWARE)
            groq = engine.upsert_entity("Groq", EntityType.PROVIDER,
                                        aliases=["groq cloud"])
            engine.link_entities(voice.id, RelationType.USES, groq.id)
            _, vbody = vault_mod.split_note(
                Path(engine.vault.resolve_path("entity", voice.id)).read_text(
                    encoding="utf-8"))
            _, gbody = vault_mod.split_note(
                Path(engine.vault.resolve_path("entity", groq.id)).read_text(
                    encoding="utf-8"))
            self.assertIn("[[Groq]]", vbody)
            self.assertIn("[[VOICE_FAST]]", gbody)
            # sem relação inventada: terceiros não aparecem
            self.assertNotIn("[[Qwen", vbody)
        finally:
            tmp.cleanup()


class LifecycleCase(unittest.TestCase):
    def test_archive_moves_to_90_archive(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Nota temporária", title="Temp")
            before = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertTrue(before.exists())
            self.assertTrue(engine.archive(rec.id))
            after = Path(engine.vault.resolve_path("memory", rec.id))
            self.assertEqual("90_Archive", after.parent.name)
            self.assertTrue(after.exists())
            self.assertFalse(before.exists())
        finally:
            tmp.cleanup()

    def test_superseded_keeps_note_with_status(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Modelo A", memory_type=MemoryKind.DECISION,
                                  canonical_key="decision:test:sup",
                                  metadata={"superseded_by": "mem_novo"})
            engine.update(rec.id, content="Modelo B",
                          status=RecordStatus.SUPERSEDED)
            front, body = vault_mod.split_note(
                Path(engine.vault.resolve_path("memory", rec.id)).read_text(
                    encoding="utf-8"))
            self.assertEqual("superseded", front["status"])
            self.assertEqual(2, front["version"])
            self.assertIn("mem_novo", body)
            versions = engine.list_versions(rec.id)
            self.assertEqual(1, len(versions))
        finally:
            tmp.cleanup()

    def test_version_metadata_updates(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("v1", title="Versões")
            engine.update(rec.id, content="v2")
            front, _ = vault_mod.split_note(
                Path(engine.vault.resolve_path("memory", rec.id)).read_text(
                    encoding="utf-8"))
            self.assertEqual(2, front["version"])
            notes = [p for _, p in engine.vault.list_records("memory")
                     if "--mem%d.md" % rec.id in p.name]
            self.assertEqual(1, len(notes))
        finally:
            tmp.cleanup()


class PrivacyCase(unittest.TestCase):
    def test_public_and_internal_projected(self):
        engine, tmp = make_engine()
        try:
            for privacy in (DataClassification.PUBLIC, DataClassification.INTERNAL):
                rec = engine.remember("conteúdo %s" % privacy.value,
                                      privacy=privacy)
                state = v2_get_projection(engine.db_path, rec.id, "memory")
                self.assertEqual("synced", state["sync_status"])
                self.assertTrue(Path(state["path"]).exists())
        finally:
            tmp.cleanup()

    def test_sensitive_restricted_by_default(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("conteúdo sensível",
                                  privacy=DataClassification.SENSITIVE)
            self.assertTrue(rec.id)  # SQLite canônico preservado
            state = v2_get_projection(engine.db_path, rec.id, "memory")
            self.assertEqual("ignored", state["sync_status"])
            self.assertIsNone(engine.vault.resolve_path("memory", rec.id))
        finally:
            tmp.cleanup()

    def test_secret_projection_blocked(self):
        engine, tmp = make_engine()
        try:
            rec = MemoryRecordV2(content="x", privacy=DataClassification.SECRET)
            rec.id = 424242
            ok, reason = vault_mod.export_decision(rec)
            self.assertFalse(ok)
            self.assertEqual("secret-prohibited", reason)
        finally:
            tmp.cleanup()

    def test_secret_scrub_blocks_title_with_credential(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Conteúdo limpo", title="nota password: 123")
            state = v2_get_projection(engine.db_path, rec.id, "memory")
            self.assertEqual("error", state["sync_status"])
            self.assertIn("security-block", state["detail"])
            self.assertIsNone(engine.vault.resolve_path("memory", rec.id))
        finally:
            tmp.cleanup()


class SyncDriftCase(unittest.TestCase):
    def test_sync_state_and_projection_hash(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Estado de sync", title="Sync")
            state = v2_get_projection(engine.db_path, rec.id, "memory")
            self.assertEqual("synced", state["sync_status"])
            self.assertEqual(rec.version, state["projection_version"])
            on_disk = Path(state["path"]).read_text(encoding="utf-8")
            self.assertEqual(vault_mod.projection_hash(on_disk),
                             state["projection_hash"])
        finally:
            tmp.cleanup()

    def test_external_edit_detected_as_drift(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Original", title="Drift")
            path = Path(engine.vault.resolve_path("memory", rec.id))
            path.write_text(path.read_text(encoding="utf-8") + "\nEdição manual.\n",
                            encoding="utf-8")
            drift = engine.check_drift(rec.id)
            self.assertEqual("drift", drift["sync_status"])
            # nada importado: SQLite intacto
            self.assertEqual("Original", engine.get(rec.id).content)
            # rebuild não apaga edição sem saber origem: re-projeta canônico
            engine.rebuild_vault()
            self.assertEqual("synced", engine.check_drift(rec.id)["sync_status"])
        finally:
            tmp.cleanup()

    def test_record_update_without_reprojection_is_pending(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Base", title="Pendente")
            current = engine.store.load(rec.id)
            current.content = "Base alterada direto no SQLite"
            engine.store.update(current)
            drift = engine.check_drift(rec.id)
            self.assertEqual("pending", drift["sync_status"])
        finally:
            tmp.cleanup()

    def test_both_changed_is_conflict(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Base", title="Conflito")
            current = engine.store.load(rec.id)
            current.content = "SQLite mudou"
            engine.store.update(current)
            path = Path(engine.vault.resolve_path("memory", rec.id))
            path.write_text(path.read_text(encoding="utf-8") + "\nManual.\n",
                            encoding="utf-8")
            drift = engine.check_drift(rec.id)
            self.assertEqual("conflict", drift["sync_status"])
        finally:
            tmp.cleanup()


class RebuildCase(unittest.TestCase):
    def test_rebuild_recreates_missing_notes(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Recriar", title="Rebuild")
            path = Path(engine.vault.resolve_path("memory", rec.id))
            path.unlink()
            self.assertEqual("pending", engine.check_drift(rec.id)["sync_status"])
            report = engine.rebuild_vault()
            self.assertEqual(1, report["projected"])
            self.assertTrue(path.exists())
            self.assertEqual("synced", engine.check_drift(rec.id)["sync_status"])
        finally:
            tmp.cleanup()

    def test_dry_run_changes_nothing(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Dry", title="DryRun")
            path = Path(engine.vault.resolve_path("memory", rec.id))
            path.unlink()
            report = engine.rebuild_vault(dry_run=True)
            self.assertTrue(report["dry_run"])
            self.assertIn(rec.id, report["would_create"])
            self.assertFalse(path.exists())
        finally:
            tmp.cleanup()

    def test_dry_run_reports_archive_and_conflict(self):
        engine, tmp = make_engine()
        try:
            archived = engine.remember("Arq", title="ArqDry")
            engine.store.set_status(archived.id, RecordStatus.ARCHIVED)
            conflicted = engine.remember("Conf", title="ConfDry")
            cpath = Path(engine.vault.resolve_path("memory", conflicted.id))
            cpath.write_text(cpath.read_text(encoding="utf-8") + "\nManual.\n",
                             encoding="utf-8")
            report = engine.rebuild_vault(dry_run=True)
            self.assertIn(archived.id, report["would_archive"])
            self.assertIn(conflicted.id, report["would_conflict"])
        finally:
            tmp.cleanup()

    def test_safe_rebuild_preserves_human_notes(self):
        engine, tmp = make_engine()
        try:
            human = Path(engine.vault_root) / "04_Knowledge" / "Minhas ideias.md"
            human.write_text("# Minhas ideias\n\nTexto humano.\n", encoding="utf-8")
            engine.remember("Gerenciada", title="Gerenciada")
            report = engine.rebuild_vault()
            self.assertTrue(human.exists())
            self.assertIn("Minhas ideias", human.read_text(encoding="utf-8"))
            managed = [n for n, _ in engine.vault.list_records("memory")]
            self.assertTrue(all(n.startswith("mem_") for n in managed))
            self.assertFalse(engine.vault.delete_projection_if_safe(999999))
        finally:
            tmp.cleanup()

    def test_managed_file_detection(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Gerenciada", title="Detect")
            listed = dict(engine.vault.list_records("memory"))
            self.assertIn("mem_%d" % rec.id, listed)
        finally:
            tmp.cleanup()


class FailureCase(unittest.TestCase):
    def test_disk_failure_degrades_without_losing_memory(self):
        engine, tmp = make_engine()
        try:
            rec_before = engine.remember("Antes da falha")
            self.assertTrue(rec_before.id)
            with mock.patch.object(vault_mod, "atomic_write",
                                   side_effect=OSError("disk full")):
                rec = engine.remember("Durante a falha de disco")
                self.assertTrue(rec.id)  # SQLite confirmada
                self.assertEqual("Durante a falha de disco",
                                 engine.get(rec.id).content)
                state = v2_get_projection(engine.db_path, rec.id, "memory")
                self.assertIn(state["sync_status"], ("pending", "error"))
        finally:
            tmp.cleanup()

    def test_invalid_vault_path_degrades(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            engine = GoldenMemoryEngine(
                str(Path(tmp.name) / "v2.db"),
                vault_root=str(Path(tmp.name) / "bad\x00path"))
            self.assertIsNone(engine.vault)
            self.assertTrue(engine._vault_error)
            rec = engine.remember("Funciona sem vault válido")
            self.assertTrue(rec.id)
            state = v2_get_projection(engine.db_path, rec.id, "memory")
            self.assertEqual("pending", state["sync_status"])
        finally:
            tmp.cleanup()

    def test_vault_path_as_file_degrades(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            blocker = Path(tmp.name) / "blocker"
            blocker.write_text("sou um arquivo", encoding="utf-8")
            engine = GoldenMemoryEngine(str(Path(tmp.name) / "v2.db"),
                                        vault_root=str(blocker))
            self.assertIsNone(engine.vault)
            rec = engine.remember("SQLite segue canônico")
            self.assertEqual("SQLite segue canônico",
                             engine.get(rec.id).content)
        finally:
            tmp.cleanup()


class MigrationLegacyCase(unittest.TestCase):
    def test_migration_v2_idempotent_with_projections(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = str(Path(tmp.name) / "v2.db")
            self.assertEqual(4, ensure_v2_schema(path))
            self.assertEqual(4, ensure_v2_schema(path))
            self.assertEqual(4, v2_schema_version(path))
        finally:
            tmp.cleanup()

    def test_legacy_preserved_and_projectable_readonly(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            legacy = GoldenMemoryManager(tmp.name)
            before = legacy.db.memory_count(active=None)
            rid = legacy.remember("Anderson prefere respostas curtas",
                                  category=None, namespace="jarvis")
            engine = GoldenMemoryEngine(
                str(Path(tmp.name) / "jarvis" / "golden_memory.db"),
                vault_root=str(Path(tmp.name) / "vault"))
            adapter = LegacyMemoryAdapter(legacy)
            found = adapter.recall("respostas curtas")
            self.assertTrue(found)
            target = next(r for r in found if r.content.startswith("Anderson"))
            target.id = 700001 + int(rid or 0)
            result = engine.project_legacy(target)
            self.assertEqual("synced", result["sync_status"])
            after = legacy.db.memory_count(active=None)
            self.assertEqual(before + 1, after)  # só o remember; projeção não toca
        finally:
            tmp.cleanup()


class RegressionCase(unittest.TestCase):
    def test_voice_fast_path_unaffected_by_vault(self):
        from jarvis_core.orchestrator.orchestrator import CentralOrchestrator
        from jarvis_core.registry import ToolRegistry
        engine, tmp = make_engine()
        try:
            engine.remember("Memória com vault ativo")
            orch = CentralOrchestrator(ToolRegistry(), audit=None)
            for text, route in (("que horas são", "SYSTEM"),
                                ("cotação do dólar", "MARKET_DATA"),
                                ("abra ele", "CLARIFY")):
                decision = orch.decide(text, source="voice", voice_capture=True)
                self.assertEqual(route, decision.route.value)
                self.assertFalse(decision.requires_ai and
                                 decision.requires_planning)
        finally:
            tmp.cleanup()

    def test_session_followup_working_memory_intact(self):
        engine, tmp = make_engine()
        try:
            engine.working.put("turn", {"topic": "Forex"}, ttl_seconds=60)
            self.assertEqual({"topic": "Forex"}, engine.working.get("turn"))
            engine.remember("Memória persistente com vault")
            self.assertEqual({"topic": "Forex"}, engine.working.get("turn"))
        finally:
            tmp.cleanup()

    def test_projection_latency_delta_printed(self):
        plain, t1 = make_engine(vault=False)
        try:
            started = time.perf_counter()
            plain.remember("Baseline sem vault")
            plain_ms = (time.perf_counter() - started) * 1000
        finally:
            t1.cleanup()
        vaulted, t2 = make_engine()
        try:
            started = time.perf_counter()
            vaulted.remember("Com projeção Markdown")
            vault_ms = (time.perf_counter() - started) * 1000
            print("perf m11 remember_plain=%.0fms remember_vault=%.0fms delta=%.0fms"
                  % (plain_ms, vault_ms, vault_ms - plain_ms))
            self.assertLess(vault_ms, 2000)
        finally:
            t2.cleanup()


if __name__ == "__main__":
    unittest.main()
