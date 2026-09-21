"""M1.2 Knowledge Graph: identidade, aliases, merge, relações tipadas,
consultas limitadas, provenance, privacy, versionamento, Obsidian.

Banco real NUNCA tocado: tudo em diretórios temporários.
"""
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from jarvis_core.memory.v2 import (
    ConfidenceBasis, EntityType, GoldenMemoryEngine, GraphPath,
    MemoryKind, MemorySecurityError, MemoryValidationError, RecordStatus,
    RelationType, ResolutionStatus, SourceType, ensure_v2_schema,
    v2_schema_version)
from jarvis_core.memory.v2 import vault as vault_mod
from jarvis_core.memory.v2.migrations import v2_get_projection
from jarvis_core.orchestrator.models import DataClassification


def make_engine(**kwargs):
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    kwargs.setdefault("vault_root", str(base / "vault"))
    kwargs.setdefault("db_path", str(base / "v2.db"))
    return GoldenMemoryEngine(**kwargs), tmp


def build_dataset(engine):
    """Dataset controlado §55 (somente DB de teste)."""
    gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
    voice = engine.upsert_entity("VOICE_FAST", EntityType.COMPONENT)
    qwen = engine.upsert_entity("Qwen 3.8 27B", EntityType.MODEL,
                                aliases=["Qwen 3.8"])
    groq = engine.upsert_entity("Groq", EntityType.PROVIDER)
    whisper = engine.upsert_entity("Faster-Whisper", EntityType.SOFTWARE)
    mt5 = engine.upsert_entity("MetaTrader 5", EntityType.SOFTWARE,
                               aliases=["MT5"])
    xau = engine.upsert_entity("XAUUSD", EntityType.ASSET, aliases=["Gold"])
    cac1 = engine.upsert_entity("CA + C1", EntityType.STRATEGY)
    engine.link_entities(gj.id, RelationType.HAS_COMPONENT, voice.id)
    engine.link_entities(voice.id, RelationType.USES_MODEL, qwen.id)
    engine.link_entities(qwen.id, RelationType.PROVIDED_BY, groq.id)
    engine.link_entities(gj.id, RelationType.USES, whisper.id)
    engine.link_entities(gj.id, RelationType.INTEGRATES_WITH, mt5.id)
    engine.link_entities(cac1.id, RelationType.TRADES_ASSET, xau.id)
    return {"gj": gj, "voice": voice, "qwen": qwen, "groq": groq,
            "whisper": whisper, "mt5": mt5, "xau": xau, "cac1": cac1}


class EntityCanonicalCase(unittest.TestCase):
    def test_entity_canonical_create(self):
        engine, tmp = make_engine()
        try:
            ent = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            self.assertTrue(ent.id)
            self.assertEqual(1, ent.version)
            node = engine.get_entity(ent.id)
            self.assertEqual("Golden Jarvis", node.canonical_name)
            self.assertEqual("project", node.entity_type)
        finally:
            tmp.cleanup()

    def test_entity_idempotency(self):
        engine, tmp = make_engine()
        try:
            first = engine.upsert_entity("Groq", EntityType.PROVIDER)
            second = engine.upsert_entity("Groq", EntityType.PROVIDER)
            self.assertEqual(first.id, second.id)
            self.assertEqual(1, second.version)
        finally:
            tmp.cleanup()

    def test_normalization_is_conservative(self):
        engine, tmp = make_engine()
        try:
            upper = engine.upsert_entity("GOLDEN JARVIS", EntityType.PROJECT)
            lower = engine.upsert_entity("golden jarvis", EntityType.PROJECT)
            self.assertNotEqual(upper.id, lower.id)  # nomes distintos: não funde
            q1 = engine.upsert_entity("Qwen 3.8", EntityType.MODEL)
            q2 = engine.upsert_entity("Qwen 3.8 27B", EntityType.MODEL)
            self.assertNotEqual(q1.id, q2.id)  # tokens distintos: não funde
        finally:
            tmp.cleanup()

    def test_entity_types_catalog(self):
        for kind in ("person", "project", "model", "provider", "software",
                     "strategy", "asset", "document", "system", "company",
                     "concept", "component", "device", "other"):
            self.assertTrue(EntityType(kind))
        with self.assertRaises(ValueError):
            EntityType("decision")  # decisão é MemoryRecord, não entidade

    def test_entity_update_versions(self):
        engine, tmp = make_engine()
        try:
            ent = engine.upsert_entity("Nome Antigo", EntityType.SYSTEM)
            updated = engine.update_entity(ent.id, canonical_name="Nome Novo")
            self.assertEqual(2, updated.version)
            versions = engine.store.entity_versions(ent.id)
            self.assertEqual(1, len(versions))
            self.assertEqual("Nome Antigo", versions[0]["canonical_name"])
        finally:
            tmp.cleanup()


class AliasCase(unittest.TestCase):
    def test_alias_exact_resolve(self):
        engine, tmp = make_engine()
        try:
            mt5 = engine.upsert_entity("MetaTrader 5", EntityType.SOFTWARE,
                                       aliases=["MT5"])
            found = engine.find_entity("MT5")
            self.assertIsNotNone(found)
            self.assertEqual(mt5.id, found.entity_id)
        finally:
            tmp.cleanup()

    def test_alias_normalized_resolve(self):
        engine, tmp = make_engine()
        try:
            engine.upsert_entity("MetaTrader 5", EntityType.SOFTWARE,
                                 aliases=["Meta Trader 5"])
            found = engine.find_entity("meta trader  5")
            self.assertIsNotNone(found)
            self.assertEqual("MetaTrader 5", found.canonical_name)
        finally:
            tmp.cleanup()

    def test_ambiguous_alias_never_guessed(self):
        engine, tmp = make_engine()
        try:
            engine.upsert_entity("XAUUSD", EntityType.ASSET, aliases=["Ouro"])
            engine.upsert_entity("Ouro Conceito", EntityType.CONCEPT,
                                 aliases=["ouro"])
            self.assertIsNone(engine.find_entity("OURO"))
            resolution = engine.resolve_entity("ouro")
            self.assertEqual(ResolutionStatus.AMBIGUOUS, resolution.status)
            self.assertEqual(2, len(resolution.candidates))
            conflicts = engine.store.alias_conflicts()
            self.assertTrue(any(c["normalized_alias"] == "ouro"
                                for c in conflicts))
        finally:
            tmp.cleanup()

    def test_resolve_not_found(self):
        engine, tmp = make_engine()
        try:
            resolution = engine.resolve_entity("entidade fantasma xyz")
            self.assertEqual(ResolutionStatus.NOT_FOUND, resolution.status)
        finally:
            tmp.cleanup()


class MergeCase(unittest.TestCase):
    def test_merge_rewiring_and_aliases(self):
        engine, tmp = make_engine()
        try:
            gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            qwen = engine.upsert_entity("Qwen", EntityType.MODEL)
            qwen_full = engine.upsert_entity("Qwen 3.8 27B", EntityType.MODEL)
            engine.link_entities(gj.id, RelationType.USES, qwen.id)
            summary = engine.merge_entities(qwen.id, qwen_full.id,
                                            source_ref="test-merge")
            self.assertEqual(qwen.id, summary["source_id"])
            self.assertEqual(1, summary["moved_relations"])
            self.assertGreaterEqual(summary["moved_aliases"], 1)
            merged = engine.store.get_entity(qwen.id)
            self.assertEqual(RecordStatus.MERGED, merged.status)
            self.assertIn(qwen.id, engine.store.get_entity(
                qwen_full.id).metadata.get("merged_from", []))
            # alias histórico resolve p/ destino
            self.assertEqual(qwen_full.id, engine.find_entity("Qwen").entity_id)
            # relação re-ligada ao destino
            outs = engine.outgoing_relations(gj.id)
            self.assertTrue(any(n.node.entity_id == qwen_full.id for n in outs))
        finally:
            tmp.cleanup()

    def test_merge_drops_duplicate_preserving_evidence(self):
        engine, tmp = make_engine()
        try:
            gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            qwen = engine.upsert_entity("Qwen", EntityType.MODEL)
            qwen_full = engine.upsert_entity("Qwen 3.8 27B", EntityType.MODEL)
            dup = engine.link_entities(gj.id, RelationType.USES, qwen.id)
            keep = engine.link_entities(gj.id, RelationType.USES, qwen_full.id)
            mem = engine.remember("Evidência de uso",
                                  source_type=SourceType.TEST)
            engine.add_relation_evidence(dup.id, mem.id, note="bench")
            engine.merge_entities(qwen.id, qwen_full.id)
            remaining = [r for r in engine.store.get_relations(gj.id)
                         if r["relation_type"] == "uses"]
            self.assertEqual(1, len(remaining))
            evidences = engine.relation_evidence(keep.id)
            self.assertTrue(any(e["memory_id"] == mem.id for e in evidences))
        finally:
            tmp.cleanup()

    def test_merge_rollback_on_failure(self):
        engine, tmp = make_engine()
        try:
            gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            qwen = engine.upsert_entity("Qwen", EntityType.MODEL)
            engine.link_entities(gj.id, RelationType.USES, qwen.id)
            before = engine.store.get_relations(gj.id)
            with self.assertRaises(KeyError):
                engine.merge_entities(qwen.id, 999999)
            self.assertEqual(RecordStatus.ACTIVE,
                             engine.store.get_entity(qwen.id).status)
            self.assertEqual(len(before), len(engine.store.get_relations(gj.id)))
        finally:
            tmp.cleanup()

    def test_archive_referenced_entity_keeps_relations(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            self.assertTrue(engine.archive_entity(d["groq"].id))
            self.assertEqual(RecordStatus.ARCHIVED,
                             engine.store.get_entity(d["groq"].id).status)
            # relação preservada no SQLite (endpoint inativo, não deletada)
            rels = engine.store.get_relations(
                d["qwen"].id, statuses=("active", "superseded", "archived"))
            self.assertTrue(any(r["target_entity_id"] == d["groq"].id
                                for r in rels))
            path = Path(engine.vault.resolve_path("entity", d["groq"].id))
            self.assertEqual("90_Archive", path.parent.name)
        finally:
            tmp.cleanup()


class RelationCase(unittest.TestCase):
    def test_relation_create_and_duplicate_idempotent(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            again = engine.link_entities(d["gj"].id, RelationType.USES,
                                         d["whisper"].id)
            first = [r for r in engine.store.get_relations(d["gj"].id)
                     if r["relation_type"] == "uses"][0]
            self.assertEqual(first["id"], again.id)
        finally:
            tmp.cleanup()

    def test_symmetric_reverse_is_duplicate(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            rev = engine.link_entities(d["mt5"].id, RelationType.INTEGRATES_WITH,
                                       d["gj"].id)
            fwd = [r for r in engine.store.get_relations(d["gj"].id)
                   if r["relation_type"] == "integrates_with"][0]
            self.assertEqual(fwd["id"], rev.id)
        finally:
            tmp.cleanup()

    def test_directed_reverse_is_distinct(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            back = engine.link_entities(d["whisper"].id, RelationType.USES,
                                        d["gj"].id)
            fwd = [r for r in engine.store.get_relations(d["gj"].id)
                   if r["relation_type"] == "uses"
                   and r["target_entity_id"] == d["whisper"].id][0]
            self.assertNotEqual(fwd["id"], back.id)
        finally:
            tmp.cleanup()

    def test_inverse_derived_on_target_side(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            labels = dict(engine._labeled_relations(d["groq"].id))
            self.assertIn("provides", labels)
            self.assertEqual("Qwen 3.8 27B", labels["provides"])
            qlabels = dict(engine._labeled_relations(d["qwen"].id))
            self.assertEqual("VOICE_FAST", qlabels["model_used_by"])
            self.assertEqual("Groq", qlabels["provided_by"])
        finally:
            tmp.cleanup()

    def test_self_edge_blocked(self):
        engine, tmp = make_engine()
        try:
            gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            with self.assertRaises(MemoryValidationError):
                engine.link_entities(gj.id, RelationType.USES, gj.id)
            with self.assertRaises(MemoryValidationError):
                engine.link_entities(gj.id, RelationType.RELATED_TO, gj.id)
        finally:
            tmp.cleanup()

    def test_relation_privacy_never_downgrades(self):
        engine, tmp = make_engine()
        try:
            gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            internal = engine.upsert_entity("Interno", EntityType.SYSTEM)
            rel = engine.link_entities(gj.id, RelationType.USES, internal.id,
                                       privacy=DataClassification.PUBLIC)
            self.assertEqual(DataClassification.INTERNAL, rel.privacy)
        finally:
            tmp.cleanup()

    def test_relation_provenance_and_confidence(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            rel = engine.link_entities(
                d["voice"].id, RelationType.USES_MODEL, d["qwen"].id,
                confidence=0.9, confidence_basis=ConfidenceBasis.TEST_CONFIRMED,
                source_type=SourceType.TEST, source_ref="bench-p12")
            fetched = engine.get_relation(rel.id)
            self.assertEqual(0.9, fetched.confidence)
            stored = engine.store.get_relation(rel.id)
            self.assertEqual(ConfidenceBasis.TEST_CONFIRMED,
                             stored.confidence_basis)
            self.assertEqual(SourceType.TEST, stored.source_type)
            self.assertEqual("bench-p12", stored.source_ref)
        finally:
            tmp.cleanup()

    def test_relation_supersede_preserves_history(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            rel = [r for r in engine.store.get_relations(d["voice"].id)
                   if r["relation_type"] == "uses_model"][0]
            updated = engine.supersede_relation(rel["id"], note="trocou modelo")
            self.assertEqual(RecordStatus.SUPERSEDED, updated.status)
            self.assertEqual(2, updated.version)
            versions = engine.store.relation_versions(rel["id"])
            self.assertEqual(1, len(versions))
            self.assertEqual("active", versions[0]["status"])
        finally:
            tmp.cleanup()

    def test_relation_update_versioning(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            current = engine.store.get_relation(
                [r for r in engine.store.get_relations(d["gj"].id)
                 if r["relation_type"] == "uses"][0]["id"])
            current.confidence = 0.7
            updated = engine.store.update_relation(current)
            self.assertEqual(2, updated.version)
            self.assertEqual(1, len(engine.store.relation_versions(updated.id)))
        finally:
            tmp.cleanup()

    def test_unknown_relation_type_rejected(self):
        from jarvis_core.memory.v2.record import RelationV2
        rel = RelationV2(source_entity_id=1, target_entity_id=2)
        rel.relation_type = "ama_muito"
        with self.assertRaises(MemoryValidationError):
            rel.validate()


class MemoryEntityLinkCase(unittest.TestCase):
    def test_memory_entity_link_both_directions(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            mem = engine.remember("P1.2 STT passou 7/7",
                                  source_type=SourceType.TEST)
            engine.link_memory(mem.id, d["gj"].id)
            engine.link_memory(mem.id, d["whisper"].id)
            linked = engine.entities_for_memory(mem.id)
            self.assertEqual({"Golden Jarvis", "Faster-Whisper"},
                             {n.canonical_name for n in linked})
            back = engine.memories_for_entity(d["gj"].id)
            self.assertTrue(any(m["memory_id"] == mem.id for m in back))
            self.assertTrue(engine.unlink_memory(mem.id, d["whisper"].id))
            self.assertEqual({"Golden Jarvis"},
                             {n.canonical_name
                              for n in engine.entities_for_memory(mem.id)})
        finally:
            tmp.cleanup()

    def test_memory_note_shows_linked_entities(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            mem = engine.remember("Memória vinculada",
                                  source_type=SourceType.TEST)
            engine.link_memory(mem.id, d["gj"].id)
            text = Path(engine.vault.resolve_path("memory", mem.id)).read_text(
                encoding="utf-8")
            self.assertIn("[[Golden Jarvis]]", text)
        finally:
            tmp.cleanup()

    def test_relation_multiple_evidence(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            rel = [r for r in engine.store.get_relations(d["gj"].id)
                   if r["relation_type"] == "uses"][0]
            mem1 = engine.remember("Evidência 1", source_type=SourceType.TEST)
            mem2 = engine.remember("Evidência 2", source_type=SourceType.BENCHMARK)
            engine.add_relation_evidence(rel["id"], mem1.id, note="p12")
            engine.add_relation_evidence(rel["id"], mem2.id, note="bench")
            evidences = engine.relation_evidence(rel["id"])
            self.assertEqual(2, len(evidences))
            self.assertEqual({mem1.id, mem2.id},
                             {e["memory_id"] for e in evidences})
        finally:
            tmp.cleanup()


class GraphQueryCase(unittest.TestCase):
    def test_neighbors_outgoing_incoming(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            outs = engine.outgoing_relations(d["gj"].id)
            self.assertTrue(any(n.node.canonical_name == "VOICE_FAST"
                                for n in outs))
            ins = engine.incoming_relations(d["qwen"].id)
            self.assertTrue(any(n.node.canonical_name == "VOICE_FAST"
                                for n in ins))
            for n in outs + ins:
                self.assertTrue(n.edge.relation_id)
                self.assertTrue(n.node.canonical_name)
        finally:
            tmp.cleanup()

    def test_neighbors_filters(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            only_uses = engine.neighbors(d["gj"].id, relation_type="uses")
            self.assertTrue(only_uses)
            self.assertTrue(all(n.edge.relation_type == "uses"
                                for n in only_uses))
            only_soft = engine.neighbors(d["gj"].id, entity_type="software")
            self.assertTrue(only_soft)
            self.assertTrue(all(n.node.entity_type == "software"
                                for n in only_soft))
        finally:
            tmp.cleanup()

    def test_deterministic_ordering(self):
        engine, tmp = make_engine()
        try:
            hub = engine.upsert_entity("Hub", EntityType.SYSTEM)
            names = []
            for name, conf in (("Zeta", 0.9), ("Alfa", 0.9), ("Beta", 0.4)):
                ent = engine.upsert_entity(name, EntityType.SYSTEM)
                names.append(ent)
                engine.link_entities(hub.id, RelationType.USES, ent.id,
                                     confidence=conf)
            first = engine.neighbors(hub.id)
            confs = [n.edge.confidence for n in first]
            self.assertEqual(sorted(confs, reverse=True), confs)
            top = [n.node.canonical_name for n in first
                   if n.edge.confidence == 0.9]
            self.assertEqual(["Alfa", "Zeta"], top)
        finally:
            tmp.cleanup()

    def test_privacy_filtered_graph(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            sens = engine.upsert_entity("Segredo Comercial", EntityType.DOCUMENT,
                                        privacy=DataClassification.SENSITIVE)
            engine.link_entities(d["gj"].id, RelationType.DOCUMENTED_BY,
                                 sens.id)
            default_names = {n.node.canonical_name
                             for n in engine.neighbors(d["gj"].id)}
            self.assertNotIn("Segredo Comercial", default_names)
            wide = {n.node.canonical_name for n in engine.neighbors(
                d["gj"].id, clearance="SENSITIVE")}
            self.assertIn("Segredo Comercial", wide)
            self.assertIsNone(engine.get_entity(sens.id))
            self.assertIsNotNone(engine.get_entity(sens.id,
                                                   clearance="SENSITIVE"))
        finally:
            tmp.cleanup()

    def test_secret_isolation(self):
        engine, tmp = make_engine()
        try:
            sec = engine.upsert_entity("Token Interno", EntityType.DOCUMENT,
                                       privacy=DataClassification.SECRET)
            self.assertIsNone(engine.get_entity(sec.id))
            self.assertEqual(ResolutionStatus.NOT_FOUND,
                             engine.resolve_entity("Token Interno").status)
            self.assertIsNotNone(engine.get_entity(sec.id, clearance="SECRET"))
            self.assertIsNone(engine.vault.resolve_path("entity", sec.id))
            state = v2_get_projection(engine.db_path, sec.id, "entity")
            self.assertEqual("ignored", state["sync_status"])
        finally:
            tmp.cleanup()


class TraversalCase(unittest.TestCase):
    def test_depth_levels(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            depth1 = engine.traverse(d["gj"].id, max_depth=1, max_nodes=50)
            names1 = {n.canonical_name for n in depth1.nodes}
            self.assertIn("VOICE_FAST", names1)
            self.assertIn("Faster-Whisper", names1)
            self.assertIn("MetaTrader 5", names1)
            self.assertNotIn("Qwen 3.8 27B", names1)
            depth2 = engine.traverse(d["gj"].id, max_depth=2, max_nodes=50)
            names2 = {n.canonical_name for n in depth2.nodes}
            self.assertIn("Qwen 3.8 27B", names2)
            self.assertNotIn("Groq", names2)
            depth3 = engine.traverse(d["gj"].id, max_depth=3, max_nodes=50)
            self.assertIn("Groq", {n.canonical_name for n in depth3.nodes})
            self.assertFalse(depth3.truncated)
        finally:
            tmp.cleanup()

    def test_depth_and_node_limits(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            limited = engine.traverse(d["gj"].id, max_depth=1, max_nodes=2)
            self.assertTrue(limited.truncated)
            self.assertLessEqual(len(limited.nodes), 3)
        finally:
            tmp.cleanup()

    def test_cycle_safety(self):
        engine, tmp = make_engine()
        try:
            a = engine.upsert_entity("Ciclo A", EntityType.SYSTEM)
            b = engine.upsert_entity("Ciclo B", EntityType.SYSTEM)
            c = engine.upsert_entity("Ciclo C", EntityType.SYSTEM)
            engine.link_entities(a.id, RelationType.USES, b.id)
            engine.link_entities(b.id, RelationType.USES, c.id)
            engine.link_entities(c.id, RelationType.USES, a.id)
            result = engine.traverse(a.id, max_depth=10, max_nodes=50)
            self.assertEqual(3, len(result.nodes))
            self.assertFalse(result.truncated)
        finally:
            tmp.cleanup()

    def test_shortest_path(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            path = engine.shortest_path(d["gj"].id, d["groq"].id)
            self.assertIsInstance(path, GraphPath)
            self.assertEqual(["Golden Jarvis", "VOICE_FAST", "Qwen 3.8 27B",
                              "Groq"], path.names())
            self.assertEqual(3, len(path.edges))
        finally:
            tmp.cleanup()

    def test_no_path_returns_none(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            lone = engine.upsert_entity("Ilhada", EntityType.SYSTEM)
            self.assertIsNone(engine.shortest_path(d["gj"].id, lone.id))
        finally:
            tmp.cleanup()

    def test_subgraph_contract(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            sub = engine.get_subgraph(d["gj"].id, depth=2, max_nodes=50)
            as_dict = sub.to_dict()
            self.assertEqual(d["gj"].id, as_dict["root"])
            self.assertEqual(2, as_dict["depth"])
            self.assertIn("entities", as_dict)
            self.assertIn("relations", as_dict)
            self.assertIn("truncated", as_dict)
            self.assertTrue(any(e["name"] == "Qwen 3.8 27B"
                                for e in as_dict["entities"]))
        finally:
            tmp.cleanup()


class IntegrityCase(unittest.TestCase):
    def test_clean_graph_validates(self):
        engine, tmp = make_engine()
        try:
            build_dataset(engine)
            report = engine.validate_graph()
            self.assertTrue(report["ok"])
            self.assertEqual(0, report["issue_count"])
        finally:
            tmp.cleanup()

    def test_dangling_and_self_edge_detected(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            raw = sqlite3.connect(str(engine.db_path))
            try:
                raw.execute("PRAGMA foreign_keys=OFF")
                raw.execute(
                    "INSERT INTO v2_relations (source_entity_id, relation_type,"
                    " target_entity_id, confidence, privacy, status,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (d["gj"].id, "uses", 999999, 0.5, "INTERNAL", "active",
                     1.0, 1.0))
                raw.execute(
                    "INSERT INTO v2_relations (source_entity_id, relation_type,"
                    " target_entity_id, confidence, privacy, status,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (d["gj"].id, "uses", d["gj"].id, 0.5, "INTERNAL",
                     "active", 1.0, 1.0))
                raw.commit()
            finally:
                raw.close()
            report = engine.validate_graph()
            codes = {i["code"] for i in report["issues"]}
            self.assertIn("dangling-relation", codes)
            self.assertIn("self-edge", codes)
            self.assertFalse(report["ok"])
        finally:
            tmp.cleanup()

    def test_orphan_detection_no_autodelete(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            lone = engine.upsert_entity("Sozinha", EntityType.SYSTEM)
            orphans = engine.store.orphan_entities()
            self.assertIn(lone.id, orphans)
            self.assertNotIn(d["xau"].id, orphans)
            self.assertIsNotNone(engine.store.get_entity(lone.id))
        finally:
            tmp.cleanup()

    def test_graph_stats_shape(self):
        engine, tmp = make_engine()
        try:
            build_dataset(engine)
            stats = engine.graph_stats()
            self.assertEqual(8, stats["entities_total"])
            self.assertEqual(6, stats["relations_active"])
            self.assertIn("orphan_entities", stats)
            self.assertIn("duplicate_alias_conflicts", stats)
        finally:
            tmp.cleanup()


class ProjectionCase(unittest.TestCase):
    def test_relation_labels_in_markdown(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            gj_text = Path(engine.vault.resolve_path("entity", d["gj"].id)).read_text(
                encoding="utf-8")
            self.assertIn("HAS_COMPONENT → [[VOICE_FAST]]", gj_text)
            self.assertIn("USES → [[Faster-Whisper]]", gj_text)
            voice_text = Path(
                engine.vault.resolve_path("entity", d["voice"].id)).read_text(
                encoding="utf-8")
            self.assertIn("USES_MODEL → [[Qwen 3.8 27B]]", voice_text)
            groq_text = Path(engine.vault.resolve_path("entity", d["groq"].id)).read_text(
                encoding="utf-8")
            self.assertIn("PROVIDES → [[Qwen 3.8 27B]]", groq_text)
        finally:
            tmp.cleanup()

    def test_entity_trust_in_frontmatter(self):
        engine, tmp = make_engine()
        try:
            trusted = engine.upsert_entity("Doc Oficial", EntityType.DOCUMENT,
                                           source_type=SourceType.SYSTEM)
            front, _ = vault_mod.split_note(
                Path(engine.vault.resolve_path("entity", trusted.id)).read_text(
                    encoding="utf-8"))
            self.assertEqual("trusted_internal", front["trust"])
            user = engine.upsert_entity("Nota Humana", EntityType.DOCUMENT,
                                        source_type=SourceType.USER_EXPLICIT)
            ufront, _ = vault_mod.split_note(
                Path(engine.vault.resolve_path("entity", user.id)).read_text(
                    encoding="utf-8"))
            self.assertEqual("user_editable", ufront["trust"])
        finally:
            tmp.cleanup()

    def test_drift_on_graph_change_and_rebuild(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            self.assertEqual(
                "synced",
                engine.check_drift(d["gj"].id, kind="entity")["sync_status"])
            current = engine.store.get_entity(d["gj"].id)
            current.confidence = 0.9
            engine.store.update_entity(current)
            self.assertEqual(
                "pending",
                engine.check_drift(d["gj"].id, kind="entity")["sync_status"])
            engine.rebuild_vault()
            self.assertEqual(
                "synced",
                engine.check_drift(d["gj"].id, kind="entity")["sync_status"])
        finally:
            tmp.cleanup()

    def test_rebuild_wikilinks_and_entity_index(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            note = Path(engine.vault.resolve_path("entity", d["gj"].id))
            note.unlink()
            engine.rebuild_vault()
            rebuilt = note.read_text(encoding="utf-8")
            self.assertIn("HAS_COMPONENT → [[VOICE_FAST]]", rebuilt)
            index = Path(engine.vault_root) / vault_mod.ENTITY_INDEX_PATH
            self.assertTrue(index.exists())
            index_text = index.read_text(encoding="utf-8")
            self.assertIn("[[Golden Jarvis]]", index_text)
            self.assertIn("## project", index_text)
        finally:
            tmp.cleanup()

    def test_human_notes_preserved(self):
        engine, tmp = make_engine()
        try:
            build_dataset(engine)
            human = Path(engine.vault_root) / "03_Projects" / "Ideias.md"
            human.write_text("# Ideias\n\n[[Golden Jarvis]] é legal.\n",
                             encoding="utf-8")
            engine.rebuild_vault()
            self.assertTrue(human.exists())
            self.assertIn("[[Golden Jarvis]]",
                          human.read_text(encoding="utf-8"))
        finally:
            tmp.cleanup()


class ConcurrencyCase(unittest.TestCase):
    def test_concurrent_same_entity_single_row(self):
        engine, tmp = make_engine()
        try:
            ids, errors = [], []

            def worker():
                try:
                    ids.append(engine.upsert_entity("Concorrente",
                                                   EntityType.SYSTEM).id)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            self.assertEqual(1, len(set(ids)))
        finally:
            tmp.cleanup()

    def test_concurrent_same_relation_single_row(self):
        engine, tmp = make_engine()
        try:
            a = engine.upsert_entity("Rel A", EntityType.SYSTEM)
            b = engine.upsert_entity("Rel B", EntityType.SYSTEM)
            ids, errors = [], []

            def worker():
                try:
                    ids.append(engine.link_entities(
                        a.id, RelationType.USES, b.id).id)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            self.assertEqual(1, len(set(ids)))
        finally:
            tmp.cleanup()

    def test_concurrent_alias_race_no_duplicates(self):
        engine, tmp = make_engine()
        try:
            errors = []

            def worker(n):
                try:
                    engine.upsert_entity("Alias Race", EntityType.SYSTEM,
                                         aliases=["race-%d" % (n % 3)])
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(n,))
                       for n in range(9)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            ent = engine.find_entity("Alias Race")
            self.assertEqual(3, len(ent.aliases))
        finally:
            tmp.cleanup()

    def test_concurrent_merge_stays_consistent(self):
        engine, tmp = make_engine()
        try:
            gj = engine.upsert_entity("Golden Jarvis", EntityType.PROJECT)
            q1 = engine.upsert_entity("Qwen", EntityType.MODEL)
            q2 = engine.upsert_entity("Qwen 3.8 27B", EntityType.MODEL)
            engine.link_entities(gj.id, RelationType.USES, q1.id)
            outcomes, errors = [], []

            def worker():
                try:
                    outcomes.append(engine.merge_entities(q1.id, q2.id))
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(1, len(outcomes))
            self.assertEqual(RecordStatus.MERGED,
                             engine.store.get_entity(q1.id).status)
            self.assertTrue(engine.validate_graph()["ok"])
        finally:
            tmp.cleanup()


class PerfCase(unittest.TestCase):
    def test_graph_ops_are_fast(self):
        engine, tmp = make_engine()
        try:
            d = build_dataset(engine)
            marks = {}
            started = time.perf_counter()
            engine.resolve_entity("mt5")
            marks["resolve"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.link_entities(d["gj"].id, RelationType.DOCUMENTED_BY,
                                 d["cac1"].id)
            marks["relation_create"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.neighbors(d["gj"].id)
            marks["neighbors"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.traverse(d["gj"].id, max_depth=2, max_nodes=50)
            marks["depth2"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.shortest_path(d["gj"].id, d["groq"].id)
            marks["shortest_path"] = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            engine.get_subgraph(d["gj"].id, depth=2, max_nodes=50)
            marks["subgraph"] = (time.perf_counter() - started) * 1000
            print("perf m12 " + " ".join("%s=%.0fms" % (k, v)
                                         for k, v in marks.items()))
            for value in marks.values():
                self.assertLess(value, 2000)
        finally:
            tmp.cleanup()


class MigrationCase(unittest.TestCase):
    def test_migration_v3_idempotent(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            path = str(Path(tmp.name) / "v2.db")
            self.assertEqual(4, ensure_v2_schema(path))
            self.assertEqual(4, ensure_v2_schema(path))
            self.assertEqual(4, v2_schema_version(path))
        finally:
            tmp.cleanup()


class RegressionCase(unittest.TestCase):
    def test_m11_vault_intact(self):
        engine, tmp = make_engine()
        try:
            build_dataset(engine)
            human = Path(engine.vault_root) / "04_Knowledge" / "Humana.md"
            human.write_text("# Humana\n", encoding="utf-8")
            report = engine.rebuild_vault()
            self.assertGreater(report["projected"], 0)
            self.assertTrue(human.exists())
            with self.assertRaises(MemorySecurityError):
                engine.remember("segredo",
                                privacy=DataClassification.SECRET)
        finally:
            tmp.cleanup()

    def test_voice_and_fast_paths_unaffected(self):
        from jarvis_core.orchestrator.orchestrator import CentralOrchestrator
        from jarvis_core.registry import ToolRegistry
        engine, tmp = make_engine()
        try:
            build_dataset(engine)
            orch = CentralOrchestrator(ToolRegistry(), audit=None)
            for text, route in (("que horas são", "SYSTEM"),
                                ("cotação do dólar", "MARKET_DATA"),
                                ("abra a calculadora", "WINDOWS"),
                                ("abra ele", "CLARIFY")):
                decision = orch.decide(text, source="voice", voice_capture=True)
                self.assertEqual(route, decision.route.value)
            engine.working.put("turn", {"topic": "Forex"}, ttl_seconds=60)
            self.assertEqual({"topic": "Forex"}, engine.working.get("turn"))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
