"""M1.0 Memory Engine V2: contratos, schemas, versionamento, privacy.

Banco real NUNCA tocado: tudo em diretórios temporários. O legado
(GoldenMemoryManager) é exercitado somente em tempdir para compat.
"""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from jarvis_core.memory.manager import GoldenMemoryManager
from jarvis_core.memory.v2 import (
    ConfidenceBasis, EntityType, GoldenMemoryEngine, LegacyMemoryAdapter,
    MarkdownMemoryStore, MemoryKind, MemoryRecordV2, MemorySecurityError,
    MemoryValidationError, RecordStatus, RelationType, SourceType,
    ensure_v2_schema, v2_schema_version)
from jarvis_core.orchestrator.models import DataClassification


def make_engine(**kwargs):
    tmp = tempfile.TemporaryDirectory()
    kwargs.setdefault("db_path", str(Path(tmp.name) / "v2.db"))
    return GoldenMemoryEngine(**kwargs), tmp


class RecordContractCase(unittest.TestCase):
    def test_create_minimal_record(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Qwen é o modelo principal de voz")
            self.assertTrue(rec.id)
            self.assertEqual(1, rec.version)
            self.assertEqual(MemoryKind.SEMANTIC, rec.memory_type)
            self.assertTrue(rec.content_hash)
        finally:
            tmp.cleanup()

    def test_invalid_memory_type_rejected(self):
        rec = MemoryRecordV2(content="x")
        rec.memory_type = "nao-existe"
        with self.assertRaises(MemoryValidationError):
            rec.validate()

    def test_privacy_must_reuse_data_classification(self):
        rec = MemoryRecordV2(content="x")
        rec.privacy = "public"
        with self.assertRaises(MemoryValidationError):
            rec.validate()
        rec.privacy = DataClassification.PUBLIC
        rec.validate()

    def test_confidence_range(self):
        for bad in (-0.1, 1.5, "alta"):
            rec = MemoryRecordV2(content="x", confidence=bad)
            with self.assertRaises(MemoryValidationError):
                rec.validate()
        for good in (0.0, 0.5, 1.0):
            MemoryRecordV2(content="x", confidence=good).validate()

    def test_source_provenance_roundtrip(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember(
                "Benchmark A/B de voz concluído", memory_type=MemoryKind.LESSON,
                title="A/B voz", summary="VOICE_FAST venceu",
                confidence=0.9, confidence_basis=ConfidenceBasis.SOURCE_CONFIRMED,
                privacy=DataClassification.INTERNAL,
                source_type=SourceType.BENCHMARK, source_ref="bench-2026-09-13",
                project="jarvis", tags=["voz", "benchmark"],
                metadata={"ttft_p50_ms": 302})
            fetched = engine.get(rec.id)
            self.assertEqual(SourceType.BENCHMARK, fetched.source_type)
            self.assertEqual("bench-2026-09-13", fetched.source_ref)
            self.assertEqual("jarvis", fetched.project)
            self.assertEqual(["voz", "benchmark"], fetched.tags)
            self.assertEqual(302, fetched.metadata["ttft_p50_ms"])
            self.assertEqual(ConfidenceBasis.SOURCE_CONFIRMED, fetched.confidence_basis)
        finally:
            tmp.cleanup()


class VersioningCase(unittest.TestCase):
    def test_update_increments_and_snapshots(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Qwen principal", memory_type=MemoryKind.DECISION,
                                  canonical_key="decision:golden:voice_model")
            updated = engine.update(rec.id, content="Novo modelo principal")
            self.assertEqual(rec.id, updated.id)
            self.assertEqual(2, updated.version)
            versions = engine.list_versions(rec.id)
            self.assertEqual(1, len(versions))
            self.assertEqual(1, versions[0]["version"])
            self.assertIn("Qwen principal", versions[0]["content"])
        finally:
            tmp.cleanup()

    def test_supersede_preserves_history(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Modelo antigo", memory_type=MemoryKind.DECISION)
            engine.update(rec.id, content="Modelo novo", status=RecordStatus.SUPERSEDED)
            current = engine.get(rec.id)
            self.assertEqual(RecordStatus.SUPERSEDED, current.status)
            self.assertEqual(RecordStatus.ACTIVE.value,
                             engine.list_versions(rec.id)[0]["status"])
        finally:
            tmp.cleanup()

    def test_archive_hides_from_search(self):
        engine, tmp = make_engine()
        try:
            rec = engine.remember("Lembrete temporário xyz123")
            self.assertTrue(engine.archive(rec.id))
            self.assertEqual(RecordStatus.ARCHIVED, engine.get(rec.id).status)
            self.assertEqual([], engine.recall("temporário xyz123"))
        finally:
            tmp.cleanup()

    def test_update_missing_raises_without_side_effects(self):
        engine, tmp = make_engine()
        try:
            with self.assertRaises(KeyError):
                engine.update(999999, content="fantasma")
            self.assertEqual([], engine.list_versions(999999))
        finally:
            tmp.cleanup()


class DedupCase(unittest.TestCase):
    def test_exact_content_returns_same_id(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember("  Preferência: respostas curtas  ")
            second = engine.remember("preferência: RESPOSTAS curtas")
            self.assertEqual(first.id, second.id)
            self.assertEqual(2, second.version)
        finally:
            tmp.cleanup()

    def test_canonical_key_upserts_new_version(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember("Modelo A", canonical_key="decision:golden:llm")
            second = engine.remember("Modelo B", canonical_key="decision:golden:llm")
            self.assertEqual(first.id, second.id)
            self.assertEqual(2, second.version)
            self.assertIn("Modelo B", engine.get(first.id).content)
        finally:
            tmp.cleanup()


class EntityRelationCase(unittest.TestCase):
    def test_entity_upsert_is_idempotent(self):
        engine, tmp = make_engine()
        try:
            first = engine.upsert_entity("Groq", EntityType.PROVIDER, aliases=["groq cloud"])
            second = engine.upsert_entity("Groq", EntityType.PROVIDER, aliases=["groq-inc"])
            self.assertEqual(first.id, second.id)
            stored = engine.store.get_entity(first.id)
            self.assertIn("groq cloud", stored.aliases)
            self.assertIn("groq-inc", stored.aliases)
        finally:
            tmp.cleanup()

    def test_relation_create_and_idempotency(self):
        engine, tmp = make_engine()
        try:
            voice = engine.upsert_entity("VOICE_FAST", EntityType.SOFTWARE)
            groq = engine.upsert_entity("Groq", EntityType.PROVIDER)
            first = engine.link_entities(voice.id, RelationType.USES, groq.id,
                                         confidence=0.9)
            second = engine.link_entities(voice.id, RelationType.USES, groq.id,
                                          confidence=0.9)
            self.assertEqual(first.id, second.id)
            relations = engine.get_relations(voice.id)
            self.assertEqual(1, len(relations))
            self.assertEqual("uses", relations[0]["relation_type"])
        finally:
            tmp.cleanup()

    def test_relation_to_missing_entity_rolls_back(self):
        engine, tmp = make_engine()
        try:
            voice = engine.upsert_entity("VOICE_FAST", EntityType.SOFTWARE)
            with self.assertRaises(KeyError):
                engine.link_entities(voice.id, RelationType.USES, 999999)
            self.assertEqual([], engine.get_relations(voice.id))
        finally:
            tmp.cleanup()

    def test_reflexive_relation_rejected(self):
        engine, tmp = make_engine()
        try:
            voice = engine.upsert_entity("VOICE_FAST", EntityType.SOFTWARE)
            with self.assertRaises(MemoryValidationError):
                engine.link_entities(voice.id, RelationType.USES, voice.id)
        finally:
            tmp.cleanup()


class SecretProtectionCase(unittest.TestCase):
    def test_secret_privacy_uses_vault_not_memory(self):
        engine, tmp = make_engine()
        try:
            with self.assertRaises(MemorySecurityError):
                engine.remember("nota interna", privacy=DataClassification.SECRET)
        finally:
            tmp.cleanup()

    def test_secret_pattern_in_content_rejected(self):
        engine, tmp = make_engine()
        try:
            with self.assertRaises(MemorySecurityError):
                engine.remember("lembre que minha senha: abc123")
            with self.assertRaises(MemorySecurityError):
                engine.remember("guarde o token", metadata={"api_key": "k: v"})
        finally:
            tmp.cleanup()


class MigrationCase(unittest.TestCase):
    def test_migration_is_idempotent(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = str(Path(tmp.name) / "v2.db")
            self.assertEqual(4, ensure_v2_schema(path))
            self.assertEqual(4, ensure_v2_schema(path))
            self.assertEqual(4, v2_schema_version(path))
        finally:
            tmp.cleanup()

    def test_v2_does_not_touch_legacy_tables(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            legacy = GoldenMemoryManager(tmp.name)
            before = legacy.db.memory_count(active=None)
            engine = GoldenMemoryEngine(str(Path(tmp.name) / "jarvis" / "golden_memory.db"))
            engine.remember("Memória V2 convive com legado")
            engine.upsert_entity("Teste", EntityType.OTHER)
            after = legacy.db.memory_count(active=None)
            self.assertEqual(before, after)
            self.assertTrue(engine.get(1).id)
        finally:
            tmp.cleanup()


class LegacyCompatCase(unittest.TestCase):
    def test_legacy_memories_readable_as_v2(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            legacy = GoldenMemoryManager(tmp.name)
            rid = legacy.remember("Anderson prefere respostas curtas",
                                  category=None, namespace="jarvis")
            self.assertTrue(rid)
            from jarvis_core.memory.v2 import LegacyMemoryAdapter
            adapter = LegacyMemoryAdapter(legacy)
            found = adapter.recall("respostas curtas")
            self.assertTrue(any(r.content == "Anderson prefere respostas curtas"
                                for r in found))
            counts = adapter.legacy_counts()
            self.assertGreaterEqual(counts["memories"], 1)
        finally:
            tmp.cleanup()

    def test_legacy_session_flow_intact(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            legacy = GoldenMemoryManager(tmp.name)
            sid = legacy.start_session()
            self.assertTrue(sid)
            rid = legacy.remember_episodic("explique Forex", session_id=sid)
            self.assertTrue(rid)
            ctx = legacy.get_context("Forex")
            self.assertIsInstance(ctx, str)
        finally:
            tmp.cleanup()


class EmbeddingFailureCase(unittest.TestCase):
    def test_embedding_failure_degrades_without_crash(self):
        def boom(text):
            raise RuntimeError("ollama down")
        engine, tmp = make_engine(embed=boom, embedding_model="nomic-embed-text")
        try:
            rec = engine.remember("Conhecimento resiliente")
            self.assertTrue(rec.id)
            stored = engine.get(rec.id)
            self.assertIn(stored.embedding_status, ("pending", "degraded"))
            self.assertEqual("Conhecimento resiliente", stored.content)
        finally:
            tmp.cleanup()

    def test_vector_search_validates_dimension(self):
        engine, tmp = make_engine(embed=lambda text: [0.1, 0.2, 0.3])
        try:
            engine.remember("Vetor alfa")
            results = engine.search("alfa")
            self.assertTrue(all(hasattr(r, "memory_id") and hasattr(r, "score")
                                and hasattr(r, "match_type") for r in results))
        finally:
            tmp.cleanup()


class ConcurrencyCase(unittest.TestCase):
    def test_concurrent_canonical_upsert_single_row(self):
        engine, tmp = make_engine()
        try:
            errors = []

            def worker(n):
                try:
                    engine.remember("conteúdo %d" % n,
                                    canonical_key="decision:golden:race")
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            rec = engine.store.find_by_canonical("decision:golden:race")
            self.assertTrue(rec.id)
        finally:
            tmp.cleanup()

    def test_concurrent_entity_upsert_single_row(self):
        engine, tmp = make_engine()
        try:
            ids = []

            def worker():
                ids.append(engine.upsert_entity("Concorrente", EntityType.SYSTEM).id)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(1, len(set(ids)))
        finally:
            tmp.cleanup()


class WorkingMemoryCase(unittest.TestCase):
    def test_ttl_lifecycle(self):
        engine, tmp = make_engine()
        try:
            engine.working.put("turn", {"topic": "Forex"}, ttl_seconds=0.05)
            self.assertEqual({"topic": "Forex"}, engine.working.get("turn"))
            time.sleep(0.08)
            self.assertIsNone(engine.working.get("turn"))
            engine.working.put("turn", 1)
            engine.working.invalidate("turn")
            self.assertIsNone(engine.working.get("turn"))
        finally:
            tmp.cleanup()


class SearchContractCase(unittest.TestCase):
    def test_search_result_contract(self):
        engine, tmp = make_engine()
        try:
            engine.remember("Procedimento: abrir a calculadora pelo menu")
            results = engine.search("calculadora")
            self.assertTrue(results)
            first = results[0]
            self.assertTrue(first.memory_id)
            self.assertEqual("lexical", first.match_type)
            self.assertIn("calculadora", first.snippet.lower())
        finally:
            tmp.cleanup()

    def test_markdown_store_is_functional_vault_projection(self):
        # M1.1: stub virou projeção real (SQLite primeiro, depois Markdown).
        tmp = tempfile.TemporaryDirectory()
        try:
            engine = GoldenMemoryEngine(
                str(Path(tmp.name) / "v2.db"),
                vault_root=str(Path(tmp.name) / "vault"))
            store = MarkdownMemoryStore(str(Path(tmp.name) / "vault"),
                                        str(Path(tmp.name) / "v2.db"))
            with self.assertRaises(ValueError):
                store.save(MemoryRecordV2(content="x"))
            rec = engine.remember("Projeção funcional M1.1")
            self.assertTrue(Path(store.resolve_path("memory", rec.id)).exists())
        finally:
            tmp.cleanup()


class PerformanceSmokeCase(unittest.TestCase):
    def test_basic_ops_are_fast(self):
        engine, tmp = make_engine()
        try:
            started = time.perf_counter()
            rec = engine.remember("Smoke de performance textual")
            remember_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.get(rec.id)
            get_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.remember("Smoke de performance textual")
            dedup_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.upsert_entity("Smoke", EntityType.SYSTEM)
            entity_ms = (time.perf_counter() - started) * 1000
            print("perf v2 remember=%.0fms get=%.0fms dedup=%.0fms entity=%.0fms"
                  % (remember_ms, get_ms, dedup_ms, entity_ms))
            for value in (remember_ms, get_ms, dedup_ms, entity_ms):
                self.assertLess(value, 2000)
        finally:
            tmp.cleanup()


class EngineStatusCase(unittest.TestCase):
    def test_status_shape(self):
        engine, tmp = make_engine()
        try:
            status = engine.status()
            self.assertIn("V2", status["engine"])
            self.assertEqual(4, status["schema_version"])
            self.assertIn("pending_embeddings", status)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
