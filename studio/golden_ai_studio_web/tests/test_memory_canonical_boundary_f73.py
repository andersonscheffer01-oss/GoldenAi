import tempfile

from jarvis_core.service import JarvisService


def test_service_memory_tools_use_v2_without_legacy_dual_write():
    with tempfile.TemporaryDirectory() as root:
        service = JarvisService(root)
        before = service.legacy_memory.db.memory_count(active=None)

        created = service._memory_remember(
            "A preferência canônica do projeto é usar o MT5.", "jarvis")
        assert created["ok"] is True
        assert created["store"] == "v2"
        assert service.legacy_memory.db.memory_count(active=None) == before

        record = service.memory_v2.get(created["id"])
        assert record is not None
        assert record.project == "jarvis"
        assert record.source_ref == ""
        assert record.source_type.value == "user_explicit"

        found = service._memory_search("preferência MT5", "jarvis")
        assert found["store"] == "v2"
        assert found["count"] == 1
        recent = service._memory_recent(5, "jarvis")
        assert recent["store"] == "v2"
        assert recent["count"] == 1

        service.close()
