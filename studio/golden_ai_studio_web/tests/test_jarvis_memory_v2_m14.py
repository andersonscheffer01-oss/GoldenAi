"""M1.4: consolidação determinística, deduplicação e contradições."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from jarvis_core.memory.v2 import (
    ConsolidationKind, GoldenMemoryEngine, MemoryKind, MemorySecurityError,
    RecordStatus, SourceType)
from jarvis_core.orchestrator.models import DataClassification


def make_engine(embed=None):
    tmp = tempfile.TemporaryDirectory()
    engine = GoldenMemoryEngine(Path(tmp.name) / "memory.db", embed=embed,
                                embedding_model="test-vector")
    return engine, tmp


class ConsolidationM14Case(unittest.TestCase):
    def test_exact_duplicate_reinforces_evidence_and_history(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember("Preferência de tema escuro", source_ref="chat:1")
            second = engine.remember(" preferência DE TEMA escuro ", source_ref="chat:2")
            self.assertEqual(first.id, second.id)
            self.assertEqual(ConsolidationKind.EXACT_DUPLICATE,
                             engine.last_consolidation.kind)
            self.assertEqual(2, second.version)
            self.assertEqual("chat:2", second.metadata["consolidation_evidence"][-1]["source_ref"])
            self.assertEqual(1, len(engine.list_versions(first.id)))
        finally:
            tmp.cleanup()

    def test_semantic_duplicate_uses_vector_and_keeps_one_record(self):
        engine, tmp = make_engine(embed=lambda text: [1.0, 0.5, 0.25])
        try:
            first = engine.remember("Usuário prefere respostas objetivas", project="jarvis")
            second = engine.remember("Responda sempre de forma curta", project="jarvis")
            self.assertEqual(first.id, second.id)
            self.assertEqual(ConsolidationKind.SEMANTIC_DUPLICATE,
                             engine.last_consolidation.kind)
        finally:
            tmp.cleanup()

    def test_related_information_is_complement_not_merge(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember("O modelo de voz usa cache local rápido")
            second = engine.remember("O modelo de voz usa fila assíncrona")
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(ConsolidationKind.COMPLEMENT,
                             engine.last_consolidation.kind)
            self.assertEqual(RecordStatus.ACTIVE, second.status)
            self.assertEqual(first.id,
                             second.metadata["consolidation"]["related_memory_id"])
        finally:
            tmp.cleanup()

    def test_unrelated_information_is_new(self):
        engine, tmp = make_engine()
        try:
            engine.remember("A voz principal usa português brasileiro")
            second = engine.remember("O radar acompanha ouro e dólar")
            self.assertEqual(ConsolidationKind.NEW, engine.last_consolidation.kind)
            self.assertEqual(RecordStatus.ACTIVE, second.status)
        finally:
            tmp.cleanup()

    def test_canonical_update_preserves_old_version_and_privacy(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember(
                "Modelo principal = A", canonical_key="voice:model", project="golden",
                source_type=SourceType.SYSTEM,
                privacy=DataClassification.SENSITIVE)
            updated = engine.remember(
                "Modelo principal = B", canonical_key="voice:model", project="golden",
                source_type=SourceType.USER_EXPLICIT,
                privacy=DataClassification.PUBLIC)
            self.assertEqual(first.id, updated.id)
            self.assertEqual(2, updated.version)
            self.assertEqual(DataClassification.SENSITIVE, updated.privacy)
            self.assertIn("Modelo principal = A",
                          engine.list_versions(first.id)[0]["content"])
        finally:
            tmp.cleanup()

    def test_lower_trust_canonical_change_stays_disputed(self):
        engine, tmp = make_engine()
        try:
            first = engine.remember(
                "Provider principal = Groq", canonical_key="llm:provider",
                source_type=SourceType.USER_EXPLICIT)
            incoming = engine.remember(
                "Provider principal = Outro", canonical_key="llm:provider",
                source_type=SourceType.CONVERSATION)
            self.assertNotEqual(first.id, incoming.id)
            self.assertEqual(RecordStatus.DISPUTED, incoming.status)
            self.assertEqual(RecordStatus.ACTIVE, engine.get(first.id).status)
        finally:
            tmp.cleanup()

    def test_stronger_contradiction_supersedes_old_record(self):
        engine, tmp = make_engine()
        try:
            old = engine.remember("modelo principal = qwen", source_type=SourceType.AGENT,
                                  confidence=0.6)
            new = engine.remember("modelo principal = llama", source_type=SourceType.USER_EXPLICIT,
                                  confidence=0.9)
            self.assertEqual(ConsolidationKind.CONTRADICTION,
                             engine.last_consolidation.kind)
            self.assertEqual(RecordStatus.ACTIVE, new.status)
            self.assertEqual(RecordStatus.SUPERSEDED, engine.get(old.id).status)
        finally:
            tmp.cleanup()

    def test_equal_trust_contradiction_is_disputed(self):
        engine, tmp = make_engine()
        try:
            old = engine.remember("provedor de voz = groq", source_type=SourceType.SYSTEM)
            new = engine.remember("provedor de voz = local", source_type=SourceType.SYSTEM)
            self.assertEqual(ConsolidationKind.UNCERTAIN,
                             engine.last_consolidation.kind)
            self.assertEqual(RecordStatus.DISPUTED, new.status)
            self.assertEqual(RecordStatus.ACTIVE, engine.get(old.id).status)
        finally:
            tmp.cleanup()

    def test_structured_memory_never_auto_merges_by_similarity(self):
        engine, tmp = make_engine(embed=lambda text: [1.0, 1.0])
        try:
            first = engine.remember("Decisão: manter provider A", MemoryKind.DECISION)
            second = engine.remember("Decisão: continuar provider A", MemoryKind.DECISION)
            self.assertNotEqual(first.id, second.id)
            self.assertEqual(ConsolidationKind.UNCERTAIN,
                             engine.last_consolidation.kind)
            self.assertEqual(RecordStatus.ACTIVE, second.status)
        finally:
            tmp.cleanup()

    def test_exact_and_canonical_dedup_are_project_isolated(self):
        engine, tmp = make_engine()
        try:
            a = engine.remember("Mesmo conteúdo", project="a", canonical_key="setting:x")
            b = engine.remember("Mesmo conteúdo", project="b", canonical_key="setting:x")
            c = engine.remember("Conteúdo alterado", project="b", canonical_key="setting:x")
            self.assertNotEqual(a.id, b.id)
            self.assertEqual(b.id, c.id)
            self.assertEqual("Mesmo conteúdo", engine.get(a.id).content)
        finally:
            tmp.cleanup()

    def test_privacy_boundary_prevents_public_from_merging_sensitive(self):
        engine, tmp = make_engine(embed=lambda text: [1.0, 0.0])
        try:
            sensitive = engine.remember("Preferência confidencial", project="x",
                                        privacy=DataClassification.SENSITIVE)
            public = engine.remember("Preferência privada semelhante", project="x",
                                     privacy=DataClassification.PUBLIC)
            self.assertNotEqual(sensitive.id, public.id)
            self.assertEqual(DataClassification.SENSITIVE,
                             engine.get(sensitive.id).privacy)
        finally:
            tmp.cleanup()

    def test_secret_is_still_rejected(self):
        engine, tmp = make_engine()
        try:
            with self.assertRaises(MemorySecurityError):
                engine.remember("segredo", privacy=DataClassification.SECRET)
        finally:
            tmp.cleanup()

    def test_embedding_failure_degrades_without_losing_write(self):
        def broken(_):
            raise RuntimeError("offline")
        engine, tmp = make_engine(embed=broken)
        try:
            rec = engine.remember("Memória gravada mesmo sem vetor")
            self.assertTrue(rec.id)
            self.assertEqual(ConsolidationKind.NEW, engine.last_consolidation.kind)
        finally:
            tmp.cleanup()

    def test_concurrent_exact_writes_create_one_identity(self):
        engine, tmp = make_engine()
        try:
            ids, errors = [], []
            def worker(index):
                try:
                    ids.append(engine.remember("Conteúdo concorrente", source_ref=str(index)).id)
                except Exception as exc:
                    errors.append(exc)
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            self.assertEqual(1, len(set(ids)))
        finally:
            tmp.cleanup()

    def test_small_batch_stays_bounded_without_embeddings(self):
        engine, tmp = make_engine()
        try:
            start = time.perf_counter()
            for index in range(20):
                engine.remember("registro único número %s conteúdo %s" % (index, index * 17),
                                project="perf")
            self.assertLess(time.perf_counter() - start, 3.0)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
