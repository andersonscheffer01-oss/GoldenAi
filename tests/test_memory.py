"""
Testes unitários para core/memory/service.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory.service import ScientificMemoryService, new_memory_id
from core.safety import EvidenceLevel


# ============================================================
# TESTES
# ============================================================

def test_new_memory_id():
    """Gera IDs únicos com prefixo."""
    id1 = new_memory_id()
    id2 = new_memory_id()
    assert id1.startswith("knowledge_")
    assert id1 != id2
    print("OK test_new_memory_id")


def test_new_memory_id_prefix():
    """Gera IDs com prefixo customizado."""
    id1 = new_memory_id("revision")
    assert id1.startswith("revision_")
    print("OK test_new_memory_id_prefix")


def test_store_and_get_knowledge():
    """Armazena e recupera um item de conhecimento."""
    svc = ScientificMemoryService(str(ROOT))
    item = svc.store_knowledge(
        topic="teste_topic",
        statement="Esta e uma afiliacao de teste",
        evidence_level=EvidenceLevel.SOURCE_CLAIM,
        source_type="USER_NOTE",
        source_id="test_session",
        confidence=0.5,
        tags=["teste"],
    )
    assert item.knowledge_id.startswith("knowledge_")
    assert item.topic == "teste_topic"

    # Recupera
    retrieved = svc.get_knowledge(item.knowledge_id)
    assert retrieved is not None
    assert retrieved["statement"] == "Esta e uma afiliacao de teste"
    print("OK test_store_and_get_knowledge")


def test_search_knowledge():
    """Busca itens de conhecimento."""
    svc = ScientificMemoryService(str(ROOT))
    # Armazena item único para busca
    item = svc.store_knowledge(
        topic="busca_teste_unico_xyz",
        statement="Item para busca unica",
        evidence_level=EvidenceLevel.OBSERVED,
        source_type="MARKET",
        tags=["busca_teste"],
    )
    # Busca por topic
    results = svc.search_knowledge(text="busca_teste_unico_xyz", limit=5)
    assert len(results) > 0
    assert any(r.get("knowledge_id") == item.knowledge_id for r in results)
    print("OK test_search_knowledge")


def test_get_topic_summary():
    """Retorna resumo de um tópico."""
    svc = ScientificMemoryService(str(ROOT))
    svc.store_knowledge(
        topic="resumo_teste_abc",
        statement="Item de resumo",
        evidence_level=EvidenceLevel.SOURCE_CLAIM,
        source_type="USER_NOTE",
    )
    summary = svc.get_topic_summary("resumo_teste_abc", limit=5)
    assert "items" in summary
    assert "conflicts" in summary
    assert summary["topic"] == "resumo_teste_abc"
    print("OK test_get_topic_summary")


def test_get_knowledge_not_found():
    """Retorna None para item inexistente."""
    svc = ScientificMemoryService(str(ROOT))
    result = svc.get_knowledge("knowledge_inexistente_12345")
    assert result is None
    print("OK test_get_knowledge_not_found")


def test_evidence_levels():
    """Testa diferentes níveis de evidência."""
    svc = ScientificMemoryService(str(ROOT))
    for level in [EvidenceLevel.OBSERVED, EvidenceLevel.SOURCE_CLAIM, EvidenceLevel.TESTED]:
        item = svc.store_knowledge(
            topic=f"evidence_test_{level.value}",
            statement=f"Teste para nivel {level.value}",
            evidence_level=level,
            source_type="USER_NOTE",
        )
        assert item.evidence_level == level
    print("OK test_evidence_levels")


def test_confidence_clamp():
    """Confidence é limitado entre 0 e 1."""
    svc = ScientificMemoryService(str(ROOT))
    item = svc.store_knowledge(
        topic="clamp_test",
        statement="Teste de clamp",
        evidence_level=EvidenceLevel.SOURCE_CLAIM,
        source_type="USER_NOTE",
        confidence=5.0,  # Deve ser limitado a 1.0
    )
    assert item.confidence == 1.0
    print("OK test_confidence_clamp")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GOLDEN AI - TESTES DE MEMORIA CIENTIFICA")
    print("=" * 60)
    print()

    tests = [
        test_new_memory_id,
        test_new_memory_id_prefix,
        test_store_and_get_knowledge,
        test_search_knowledge,
        test_get_topic_summary,
        test_get_knowledge_not_found,
        test_evidence_levels,
        test_confidence_clamp,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAILED {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Resultado: {passed} passaram, {failed} falharam de {len(tests)}")
    print("=" * 60)
