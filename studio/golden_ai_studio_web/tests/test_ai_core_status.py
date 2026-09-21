from jarvis_core.orchestrator.model_router import ProviderAdapter
from jarvis_core.orchestrator.models import ProviderState
from jarvis_core.service import JarvisService


class _ResearchStatus:
    def status(self):
        return {
            "selected": "tavily",
            "fallback_count": 0,
            "providers": {
                "tavily": {
                    "status": "AVAILABLE",
                    "configured": True,
                    "last_success": 1710000000.0,
                    "last_error": "",
                    "cooldown_active": False,
                }
            },
        }


def test_ai_core_status_reuses_runtime_state(tmp_path):
    service = JarvisService(str(tmp_path))
    try:
        adapter = ProviderAdapter("gemini", lambda **_: "ok", cloud=True)
        adapter.last_model = "gemini-3.8-flash"
        adapter.last_latency_ms = 321
        adapter.last_success = 1710000000.0
        service.orchestrator.models.register_provider(adapter)
        service.research_provider = _ResearchStatus()
        with service._ai_status_lock:
            service._last_request_telemetry = {
                "request_id": "request-1",
                "session_id": "desktop",
                "route": "ASSISTED_RESEARCH",
                "tools_used": ["web_research"],
                "llm_provider": "gemini",
                "llm_model": "gemini-3.8-flash",
                "research_provider": "tavily",
                "source_count": 5,
                "fallback_used": False,
                "total_latency_ms": 321,
            }

        status = service.ai_core_status()
        assert status["llm"]["active_provider"] == "gemini"
        assert status["llm"]["active_model"] == "gemini-3.8-flash"
        assert status["research"]["provider"] == "tavily"
        assert status["research"]["status"] == "ONLINE"
        assert status["last_request"]["route"] == "ASSISTED_RESEARCH"
        assert status["last_request"]["source_count"] == 5
        assert status["overall_status"] == "ONLINE"
    finally:
        service.close()


def test_ai_core_status_marks_unconfigured_provider(tmp_path):
    service = JarvisService(str(tmp_path))
    try:
        service.orchestrator.models.register_provider(
            ProviderAdapter("gemini", lambda **_: "ok", cloud=True))
        statuses = {item["name"]: item for item in service.ai_core_status()["providers"]}
        assert statuses["gemini"]["status"] == "ONLINE"
        assert statuses["groq"]["status"] == "NOT_CONFIGURED"
        assert statuses["openrouter"]["status"] == "NOT_CONFIGURED"
    finally:
        service.close()
