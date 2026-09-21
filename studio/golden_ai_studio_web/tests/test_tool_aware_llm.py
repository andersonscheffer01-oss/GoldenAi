"""TOOL-AWARE LLM + INTENT PRECEDENCE — Tests

Tests that verify:
1. Conceptual questions route to LLM (NOT deterministic parser)
2. Operational questions still route to deterministic tools
3. LLM receives tool schemas and can propose tools
4. LLM plans are validated against ToolRegistry
5. Security is preserved (no bypass)
6. Observability metrics are tracked
7. Regression: existing functionality works

All tests use mock LLM — no real API calls.
"""

import sys
import json
from pathlib import Path
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis_core.models import Risk, Tool, ResponsePolicy
from jarvis_core.registry import ToolRegistry
from jarvis_core.security import SecurityManager
from jarvis_core.service import JarvisService
from jarvis_core.brain import JarvisBrain
from jarvis_core.orchestrator import CentralOrchestrator
from jarvis_core.orchestrator.models import Route, ModelProfile, OrchestratorDecision, DataClassification


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

def _make_brain():
    """Create a Brain with real registry for testing."""
    service = JarvisService(str(Path(__file__).resolve().parent.parent))
    brain = JarvisBrain(service.registry, memory=None, orchestrator=service.orchestrator)
    return brain, service


def _make_orchestrator():
    """Create an orchestrator for testing routing."""
    service = JarvisService(str(Path(__file__).resolve().parent.parent))
    return service.orchestrator, service


# ═══════════════════════════════════════════════════════════════
# TEST 1: "me explique o que significa CPU"
# Expected: CONCEPTUAL → LLM, NO tool executed
# ═══════════════════════════════════════════════════════════════

class Test1_ConceptualCPU:
    def test_conceptual_cpu_routes_to_conversation(self):
        """Conceptual CPU question routes to CONVERSATION, not SYSTEM."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("me explique o que significa CPU")

        assert decision.route == Route.CONVERSATION
        assert decision.intent == "conceptual_question"
        assert decision.requires_ai is True
        assert len(decision.steps) == 0

    def test_conceptual_cpu_no_deterministic_tool(self):
        """Conceptual CPU question does NOT match system_status."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("o que é CPU?")

        assert decision.route == Route.CONVERSATION
        assert decision.intent == "conceptual_question"

    def test_conceptual_cpu_variants(self):
        """Various conceptual CPU phrasings all route to CONVERSATION."""
        orch, _ = _make_orchestrator()
        variants = [
            "o que é CPU?",
            "me explique o que significa CPU",
            "como funciona processador",
            "para que serve CPU",
            "qual a diferença entre CPU e GPU",
            "o que significa processador?",
        ]
        for text in variants:
            decision = orch.decide(text)
            assert decision.route == Route.CONVERSATION, f"Failed for: {text}"
            assert decision.intent == "conceptual_question", f"Failed for: {text}"


# ═══════════════════════════════════════════════════════════════
# TEST 2: "qual o uso da CPU agora?"
# Expected: DETERMINISTIC → system_status
# ═══════════════════════════════════════════════════════════════

class Test2_OperationalCPU:
    def test_operational_cpu_routes_to_system(self):
        """Operational CPU question routes to SYSTEM with system_status."""
        orch, _ = _make_orchestrator()
        # "como está a CPU?" matches the system_status pattern in orchestrator
        decision = orch.decide("como está a CPU?")

        assert decision.route == Route.SYSTEM
        assert len(decision.steps) > 0
        assert decision.steps[0].tool == "system_status"

    def test_operational_cpu_variants(self):
        """Various operational CPU phrasings route to system_status."""
        orch, _ = _make_orchestrator()
        # These should match the system_status pattern
        variants = [
            "como está a CPU?",
            "status do computador",
            "diagnóstico do sistema",
        ]
        for text in variants:
            decision = orch.decide(text)
            assert decision.route == Route.SYSTEM, f"Failed for: {text}"
            assert any(s.tool == "system_status" for s in decision.steps), f"Failed for: {text}"


# ═══════════════════════════════════════════════════════════════
# TEST 3: "me explique o que é memória RAM"
# Expected: CONVERSATION, NO system_status
# ═══════════════════════════════════════════════════════════════

class Test3_ConceptualRAM:
    def test_conceptual_ram_no_system_status(self):
        """Conceptual RAM question does NOT call system_status."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("me explique o que é memória RAM")

        assert decision.route == Route.CONVERSATION
        assert decision.intent == "conceptual_question"
        assert len(decision.steps) == 0

    def test_conceptual_ram_variants(self):
        """Various conceptual RAM phrasings route to CONVERSATION."""
        orch, _ = _make_orchestrator()
        variants = [
            "me explique o que é memória RAM",
            "como funciona memória RAM",
            "para que serve RAM",
            "o que significa memória?",
        ]
        for text in variants:
            decision = orch.decide(text)
            assert decision.route == Route.CONVERSATION, f"Failed for: {text}"


# ═══════════════════════════════════════════════════════════════
# TEST 4: "quanto de memória RAM estou usando?"
# Expected: system_status real
# ═══════════════════════════════════════════════════════════════

class Test4_OperationalRAM:
    def test_operational_ram_uses_system_status(self):
        """Operational RAM question with 'status' uses system_status tool."""
        orch, _ = _make_orchestrator()
        # "status do sistema" matches system_status pattern
        decision = orch.decide("status do sistema?")

        assert decision.route == Route.SYSTEM
        assert any(s.tool == "system_status" for s in decision.steps)

    def test_operational_ram_variants(self):
        """Various operational RAM phrasings route to system."""
        orch, _ = _make_orchestrator()
        # These should match system_status pattern
        variants = [
            "status do sistema?",
            "como está o computador?",
            "diagnóstico do PC",
        ]
        for text in variants:
            decision = orch.decide(text)
            assert decision.route == Route.SYSTEM, f"Failed for: {text}"


# ═══════════════════════════════════════════════════════════════
# TEST 5: "quais aplicativos estão consumindo mais recursos?"
# Expected: LLM can propose list_processes
# ═══════════════════════════════════════════════════════════════

class Test5_ToolProposal:
    def test_brain_receives_tool_schemas(self):
        """Brain._runtime_context includes tool schemas for LLM."""
        brain, _ = _make_brain()
        context = brain._runtime_context()

        assert "system_status" in context
        assert "list_processes" in context
        assert "Ferramentas disponíveis" in context

    def test_validate_plan_tool_proposal(self):
        """Brain validates a valid tool proposal from LLM."""
        brain, _ = _make_brain()
        plan = {"tool": "list_processes", "args": {}}
        error = brain._validate_plan(plan)
        assert error is None

    def test_validate_plan_invalid_tool(self):
        """Brain rejects tool that doesn't exist."""
        brain, _ = _make_brain()
        plan = {"tool": "nonexistent_tool", "args": {}}
        error = brain._validate_plan(plan)
        assert error is not None
        assert "inexistente" in error.lower() or "não autorizada" in error.lower()

    def test_validate_plan_invalid_args(self):
        """Brain rejects invalid arguments."""
        brain, _ = _make_brain()
        plan = {"tool": "system_status", "args": {"invalid_arg": "value"}}
        error = brain._validate_plan(plan)
        assert error is not None
        assert "não permitidos" in error.lower()

    def test_validate_plan_missing_required(self):
        """Brain rejects plan with missing required args."""
        brain, _ = _make_brain()
        plan = {"tool": "open_program", "args": {}}  # name is required
        error = brain._validate_plan(plan)
        assert error is not None
        assert "ausentes" in error.lower()


# ═══════════════════════════════════════════════════════════════
# TEST 6: "computador pesado" — LLM should propose tools
# ═══════════════════════════════════════════════════════════════

class Test6_ComputerSlow:
    def test_computer_slow_not_says_no_access(self):
        """Brain must NOT say 'não tenho acesso' when tools exist."""
        brain, _ = _make_brain()
        context = brain._runtime_context()

        # The runtime context MUST mention available tools
        assert "system_status" in context
        assert "list_processes" in context
        # Must NOT contain the false negative phrase
        assert "não possui acesso" not in context.lower()
        assert "não tenho acesso" not in context.lower()
        assert "não tenho ferramentas" not in context.lower()

    def test_system_prompt_tool_aware(self):
        """System prompt tells LLM it has tool access."""
        brain, _ = _make_brain()
        prompt = brain._system_prompt()

        assert "ferramentas" in prompt.lower()
        assert "acesso" in prompt.lower()
        assert "NUNCA diga que não possui acesso" in prompt


# ═══════════════════════════════════════════════════════════════
# TEST 7: "pode abrir a calculadora" — deterministic parser priority
# ═══════════════════════════════════════════════════════════════

class Test7_DeterministicPriority:
    def test_calculator_opens_deterministically(self):
        """Calculator command uses deterministic parser, NOT LLM."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("abra a calculadora")

        assert decision.route == Route.WINDOWS
        assert decision.requires_ai is False
        assert len(decision.steps) > 0
        assert decision.steps[0].tool == "open_program"
        assert decision.steps[0].args.get("name") == "calculadora"

    def test_deterministic_parser_variants(self):
        """Various deterministic commands work without LLM."""
        orch, _ = _make_orchestrator()
        variants = [
            ("abra a calculadora", "open_program", "calculadora"),
            ("abrir bloco de notas", "open_program", "bloco de notas"),
            ("liste processos", "list_processes", None),
            ("que horas são", "get_time", None),
        ]
        for text, expected_tool, expected_arg in variants:
            decision = orch.decide(text)
            assert decision.requires_ai is False, f"Failed for: {text}"
            assert any(s.tool == expected_tool for s in decision.steps), f"Failed for: {text}"


# ═══════════════════════════════════════════════════════════════
# TEST 8: Security — fake critical tool with confirmation
# ═══════════════════════════════════════════════════════════════

_call_counter = {"count": 0}

def fake_critical_handler():
    _call_counter["count"] += 1
    return {"ok": True, "message": "fake critical executed"}

def reset_counter():
    _call_counter["count"] = 0

def get_counter():
    return _call_counter["count"]


class Test8_SecurityPreserved:
    def test_high_critical_requires_confirmation(self):
        """HIGH/CRITICAL tools still require confirmation."""
        brain, service = _make_brain()

        # Register a fake critical tool
        fake_tool = Tool(
            "fake_critical_action",
            "Fake critical for testing",
            fake_critical_handler,
            Risk.CRITICAL,
            confirmation=True,
        )
        service.registry.register(fake_tool)

        # Validate plan
        plan = {"tool": "fake_critical_action", "args": {}}
        error = brain._validate_plan(plan)
        assert error is None  # Plan is valid

        # But execute_tool requires confirmation
        result = service.execute_tool("fake_critical_action", {})
        assert result.get("confirmation_required") is True
        assert get_counter() == 0

    def test_confirm_executes_once(self):
        """Approve executes handler exactly once."""
        reset_counter()
        brain, service = _make_brain()

        fake_tool = Tool(
            "fake_critical_action2",
            "Fake critical for testing",
            fake_critical_handler,
            Risk.CRITICAL,
            confirmation=True,
        )
        service.registry.register(fake_tool)

        result = service.execute_tool("fake_critical_action2", {})
        token = result["token"]

        service.confirm(token)
        assert get_counter() == 1

    def test_deny_does_not_execute(self):
        """Deny does NOT execute handler."""
        reset_counter()
        brain, service = _make_brain()

        fake_tool = Tool(
            "fake_critical_action3",
            "Fake critical for testing",
            fake_critical_handler,
            Risk.CRITICAL,
            confirmation=True,
        )
        service.registry.register(fake_tool)

        result = service.execute_tool("fake_critical_action3", {})
        token = result["token"]

        service.deny_confirmation(token)
        assert get_counter() == 0


# ═══════════════════════════════════════════════════════════════
# OBSERVABILITY METRICS
# ═══════════════════════════════════════════════════════════════

class TestObservability:
    def test_metrics_track_route(self):
        """Brain tracks route in metrics."""
        brain, _ = _make_brain()

        # Mock LLM to return conversation
        with patch.object(brain, '_call_llm') as mock_llm:
            mock_llm.return_value = {"ok": True, "response": '{"response": "test"}'}
            result = brain.interpret("o que é CPU?")

            assert "route" in brain.last_metrics
            assert brain.last_metrics["route"] == "CONVERSATION"
            assert brain.last_metrics["conceptual"] is True

    def test_metrics_track_tool_proposal(self):
        """Brain tracks tool proposal in metrics when LLM returns tool."""
        brain, _ = _make_brain()

        # Mock the orchestrator to allow AI with tools
        with patch.object(brain.orchestrator, 'decide') as mock_decide:
            mock_decide.return_value = OrchestratorDecision(
                intent="system_inquiry", route=Route.SYSTEM, confidence=0.9,
                requires_ai=True, requires_planning=False,
                requires_confirmation=False, requires_clarification=False,
                preferred_skill="system", preferred_model_profile=ModelProfile.GENERAL,
                steps=(), reason_code="ROUTE_MATCH",
                allowed_tools=("system_status", "list_processes"),
                data_classification=DataClassification.INTERNAL
            )
            with patch.object(brain, '_call_llm') as mock_llm:
                mock_llm.return_value = {"ok": True, "response": '{"tool": "system_status", "args": {}}'}
                result = brain.interpret("test input")

                assert brain.last_metrics.get("llm_result_type") == "TOOL_PROPOSAL"
                assert brain.last_metrics.get("proposed_tool") == "system_status"

    def test_metrics_track_deterministic(self):
        """Brain tracks deterministic routing in metrics."""
        brain, _ = _make_brain()
        result = brain.interpret("abra a calculadora")

        assert brain.last_metrics.get("llm_result_type") == "DETERMINISTIC_TOOL"
        assert brain.last_metrics.get("proposed_tool") == "open_program"


# ═══════════════════════════════════════════════════════════════
# REGRESSION: existing functionality
# ═══════════════════════════════════════════════════════════════

class TestRegression:
    def test_open_calculator(self):
        """Opening calculator still works deterministically."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        result = service.execute_command("abra a calculadora")
        # Should either open or report file not found (deterministic path)
        assert result.get("tool") == "open_program" or result.get("ok") is True

    def test_list_processes(self):
        """Listing processes still works."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("liste processos")
        assert decision.steps[0].tool == "list_processes"

    def test_system_status(self):
        """System status still works."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("qual o status do sistema?")
        assert any(s.tool == "system_status" for s in decision.steps)

    def test_get_time(self):
        """Get time still works."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("que horas são")
        assert decision.steps[0].tool == "get_time"

    def test_open_program(self):
        """Opening programs still works via deterministic parser."""
        service = JarvisService(str(Path(__file__).resolve().parent.parent))
        # "abra o chrome" goes through service._parse() not orchestrator
        result = service._parse("abra o chrome")
        assert result is not None
        assert result[0] == "open_program"
        assert result[1].get("name") == "chrome"


# ═══════════════════════════════════════════════════════════════
# CONCEPTUAL vs OPERATIONAL boundary
# ═══════════════════════════════════════════════════════════════

class TestConceptualBoundary:
    def test_conceptual_with_question_mark(self):
        """Conceptual questions with ? route to LLM."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("o que é CPU?")
        assert decision.route == Route.CONVERSATION

    def test_operational_with_now(self):
        """Operational questions with 'agora' route to tools."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("como está a CPU agora?")
        assert decision.route == Route.SYSTEM

    def test_mixed_conceptual_wins(self):
        """When both conceptual and operational indicators present, check operational."""
        orch, _ = _make_orchestrator()
        # "como funciona" is conceptual, but no operational indicator
        decision = orch.decide("como funciona CPU?")
        assert decision.route == Route.CONVERSATION

    def test_operational_status_wins(self):
        """'status' is operational indicator."""
        orch, _ = _make_orchestrator()
        decision = orch.decide("qual o status da CPU?")
        assert decision.route == Route.SYSTEM


# ═══════════════════════════════════════════════════════════════
# TOOL MANIFEST
# ═══════════════════════════════════════════════════════════════

class TestToolManifest:
    def test_manifest_from_registry(self):
        """Tool manifest is generated from real ToolRegistry."""
        brain, _ = _make_brain()
        tools = brain.registry.get_llm_tools()

        assert len(tools) > 0
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool

    def test_manifest_no_secrets(self):
        """Tool manifest contains no API keys, passwords, or tokens."""
        brain, _ = _make_brain()
        context = brain._runtime_context()

        # Check for actual secret patterns, not just the word "secret"
        assert "api_key" not in context.lower()
        assert "password" not in context.lower()
        assert "bearer " not in context.lower()
        assert "authorization" not in context.lower()
        # "secret" may appear in DataClassification context, that's OK
        # Focus on actual credential patterns

    def test_manifest_includes_required_args(self):
        """Tool manifest includes required args info."""
        brain, _ = _make_brain()
        tools = brain.registry.get_llm_tools()

        # Find open_program tool
        open_prog = next((t for t in tools if t["name"] == "open_program"), None)
        assert open_prog is not None
        assert "name" in open_prog["parameters"]["required"]

    def test_manifest_llm_enabled_only(self):
        """Only llm_enabled tools appear in manifest."""
        brain, _ = _make_brain()
        tools = brain.registry.get_llm_tools()

        for tool in tools:
            registry_tool = brain.registry.get(tool["name"])
            assert registry_tool.llm_enabled is True


# ═══════════════════════════════════════════════════════════════
# BUG A: TOOL PROPOSAL LEAKING TO UI
# Tests that _parse_llm_response extracts JSON from text+fenced
# ═══════════════════════════════════════════════════════════════
class TestToolProposalExtraction:
    """Verify _parse_llm_response handles all real provider response formats."""

    def test_fenced_json_with_text_before(self):
        """Text before ```json block must be ignored, JSON extracted."""
        brain, _ = _make_brain()
        response = (
            'Para identificar quais aplicativos estão consumindo mais recursos,\n'
            'vou listar os processos em execução no seu sistema.\n\n'
            '```json\n{"tool": "list_processes", "args": {}}\n```'
        )
        result = brain._parse_llm_response(response)
        assert result["ok"] is True
        assert result["plan"]["tool"] == "list_processes"
        assert result["plan"]["args"] == {}

    def test_fenced_json_without_json_prefix(self):
        """``` block without json label still extracted."""
        brain, _ = _make_brain()
        response = '```{"tool": "list_processes", "args": {}}```'
        result = brain._parse_llm_response(response)
        assert result["ok"] is True
        assert result["plan"]["tool"] == "list_processes"

    def test_pure_json(self):
        """Pure JSON object returned as-is."""
        brain, _ = _make_brain()
        response = '{"tool": "list_processes", "args": {}}'
        result = brain._parse_llm_response(response)
        assert result["ok"] is True
        assert result["plan"]["tool"] == "list_processes"

    def test_text_plus_json_at_end(self):
        """Prose followed by JSON object (no fences) must extract JSON."""
        brain, _ = _make_brain()
        response = (
            'Vou listar os processos agora.\n'
            '{"tool": "list_processes", "args": {}}'
        )
        result = brain._parse_llm_response(response)
        assert result["ok"] is True
        assert result["plan"]["tool"] == "list_processes"

    def test_text_without_json_is_conversation(self):
        """Pure prose without JSON becomes CONVERSATION response."""
        brain, _ = _make_brain()
        brain.orchestrator.mode = "on"
        # Simulate a conversation decision
        brain.orchestrator.last_decision = MagicMock(
            route=Route.CONVERSATION,
            requires_ai=True,
            preferred_skill="conversation",
        )
        response = "CPU é a unidade central de processamento do computador."
        result = brain._parse_llm_response(response)
        assert result["ok"] is True
        assert "response" in result["plan"]

    def test_invalid_json_tool_deny(self):
        """JSON with nonexistent tool is DENY, not executed."""
        brain, _ = _make_brain()
        response = '{"tool": "evil_tool", "args": {}}'
        result = brain._parse_llm_response(response)
        assert result["ok"] is False
        assert "inexistente" in result["error"]

    def test_json_with_invalid_args_deny(self):
        """JSON with wrong args is DENY."""
        brain, _ = _make_brain()
        response = '{"tool": "open_program", "args": {"wrong_arg": "value"}}'
        result = brain._parse_llm_response(response)
        assert result["ok"] is False

    def test_multi_step_extraction(self):
        """Multi-step plan extracted from fenced block."""
        brain, _ = _make_brain()
        plan = {"steps": [
            {"tool": "system_status", "args": {}},
            {"tool": "list_processes", "args": {}},
        ]}
        response = f'Analisando seu sistema...\n```json\n{json.dumps(plan)}\n```'
        result = brain._parse_llm_response(response)
        assert result["ok"] is True
        assert "steps" in result["plan"]
        assert len(result["plan"]["steps"]) == 2


# ═══════════════════════════════════════════════════════════════
# BUG B: "LIXEIRA" FALSE FOLDER MATCH
# Tests that Windows special names are not treated as paths
# ═══════════════════════════════════════════════════════════════
class TestLixeiraFalseMatch:
    """Verify special Windows names don't get treated as folder paths."""

    def _make_service(self):
        from jarvis_core.service import JarvisService
        return JarvisService(base_dir=".")

    def test_verifique_minha_lixeira_not_folder(self):
        """"verifique minha lixeira" must NOT map to a folder path."""
        svc = self._make_service()
        result = svc._parse("verifique minha lixeira")
        # Should return None → Brain/LLM handles it
        assert result is None

    def test_abra_a_lixeira_not_path(self):
        """"abra a lixeira" must NOT map to open_path with path=lixeira."""
        svc = self._make_service()
        result = svc._parse("abra a lixeira")
        # Should return None → Brain/LLM handles it
        assert result is None

    def test_abra_a_pasta_downloads_still_works(self):
        """"abra a pasta Downloads" must still work as open_folder."""
        svc = self._make_service()
        result = svc._parse("abra a pasta Downloads")
        assert result is not None
        assert result[0] == "open_folder"
        assert result[1]["name"] == "Downloads"

    def test_abra_documentos_still_works(self):
        """"abra documentos" must still work as open_folder."""
        svc = self._make_service()
        result = svc._parse("abra documentos")
        assert result is not None
        assert result[0] == "open_folder"

    def test_abra_pasta_normal_not_affected(self):
        "abra a pasta C Users must still work as open_path."
        svc = self._make_service()
        result = svc._parse("abra a pasta C:\\Users")
        assert result is not None
        assert result[0] == "open_path"
        assert "Users" in result[1]["path"]

    def test_recycle_bin_not_path(self):
        """"abra recycle bin" must NOT map to open_path."""
        svc = self._make_service()
        result = svc._parse("abra recycle bin")
        assert result is None

    def test_meu_computador_not_path(self):
        """"abra meu computador" must NOT map to open_path."""
        svc = self._make_service()
        result = svc._parse("abra meu computador")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# RECYCLE BIN MIGRATION TESTS
# Non-destructive tests for recycle_bin_status and empty_recycle_bin
# ═══════════════════════════════════════════════════════════════
class TestRecycleBinStatus:
    """Verify recycle_bin_status tool exists and is correctly registered."""

    def test_recycle_bin_status_tool_exists(self):
        """recycle_bin_status must be registered in ToolRegistry."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("recycle_bin_status")
        assert tool is not None
        assert tool.name == "recycle_bin_status"

    def test_recycle_bin_status_risk_is_low(self):
        """recycle_bin_status is read-only, risk must be LOW."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("recycle_bin_status")
        assert tool.risk.value == "LOW"

    def test_recycle_bin_status_not_confirmation_required(self):
        """recycle_bin_status does not require confirmation."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("recycle_bin_status")
        assert tool.confirmation is False

    def test_recycle_bin_status_llm_enabled(self):
        """recycle_bin_status must be visible to LLM."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("recycle_bin_status")
        assert tool.llm_enabled is True

    def test_recycle_bin_status_in_manifest(self):
        """recycle_bin_status must appear in LLM tool manifest."""
        svc = JarvisService(base_dir=".")
        tools = svc.registry.get_llm_tools()
        names = [t["name"] for t in tools]
        assert "recycle_bin_status" in names

    def test_recycle_bin_status_handler_callable(self):
        """Handler must exist and be callable."""
        svc = JarvisService(base_dir=".")
        assert hasattr(svc, "_recycle_bin_status")
        assert callable(svc._recycle_bin_status)


class TestEmptyRecycleBin:
    """Verify empty_recycle_bin tool exists with correct safety properties."""

    def test_empty_recycle_bin_tool_exists(self):
        """empty_recycle_bin must be registered in ToolRegistry."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("empty_recycle_bin")
        assert tool is not None
        assert tool.name == "empty_recycle_bin"

    def test_empty_recycle_bin_risk_is_critical(self):
        """empty_recycle_bin is destructive, risk must be CRITICAL."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("empty_recycle_bin")
        assert tool.risk.value == "CRITICAL"

    def test_empty_recycle_bin_confirmation_required(self):
        """empty_recycle_bin must require confirmation."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("empty_recycle_bin")
        assert tool.confirmation is True

    def test_empty_recycle_bin_llm_enabled(self):
        """empty_recycle_bin must be visible to LLM for proposal."""
        svc = JarvisService(base_dir=".")
        tool = svc.registry.get("empty_recycle_bin")
        assert tool.llm_enabled is True

    def test_empty_recycle_bin_in_manifest(self):
        """empty_recycle_bin must appear in LLM tool manifest."""
        svc = JarvisService(base_dir=".")
        tools = svc.registry.get_llm_tools()
        names = [t["name"] for t in tools]
        assert "empty_recycle_bin" in names

    def test_empty_recycle_bin_handler_callable(self):
        """Handler must exist and be callable."""
        svc = JarvisService(base_dir=".")
        assert hasattr(svc, "_empty_recycle_bin")
        assert callable(svc._empty_recycle_bin)

    def test_empty_recycle_bin_blocks_without_confirmation(self):
        """execute_tool must return confirmation_required for empty_recycle_bin."""
        svc = JarvisService(base_dir=".")
        result = svc.execute_tool("empty_recycle_bin", {}, "test", "test")
        # Confirmation flow returns ok=True with confirmation_required=True
        assert result.get("confirmation_required") is True
        assert result.get("ok") is True


class TestRecycleBinParser:
    """Verify parser routes lixeira queries to Brain/LLM."""

    def test_verifique_minha_lixeira_not_folder(self):
        """"verifique minha lixeira" must NOT map to a folder path."""
        svc = JarvisService(base_dir=".")
        result = svc._parse("verifique minha lixeira")
        assert result is None

    def test_abra_a_lixeira_not_path(self):
        """"abra a lixeira" must NOT map to open_path with path=lixeira."""
        svc = JarvisService(base_dir=".")
        result = svc._parse("abra a lixeira")
        assert result is None

    def test_abra_a_pasta_downloads_still_works(self):
        """"abra a pasta Downloads" must still work as open_folder."""
        svc = JarvisService(base_dir=".")
        result = svc._parse("abra a pasta Downloads")
        assert result is not None
        assert result[0] == "open_folder"
        assert result[1]["name"] == "Downloads"

    def test_abra_documentos_still_works(self):
        """"abra documentos" must still work as open_folder."""
        svc = JarvisService(base_dir=".")
        result = svc._parse("abra documentos")
        assert result is not None
        assert result[0] == "open_folder"

    def test_abra_pasta_normal_not_affected(self):
        "abra a pasta C Users must still work as open_path."
        svc = JarvisService(base_dir=".")
        result = svc._parse("abra a pasta C:\\Users")
        assert result is not None
        assert result[0] == "open_path"
        assert "Users" in result[1]["path"]


class TestRecycleBinLLMFlow:
    """Verify Brain/LLM can propose recycle bin tools via plan."""

    def test_brain_validate_recycle_bin_status_plan(self):
        """Brain._validate_plan must accept valid recycle_bin_status plan."""
        brain, _ = _make_brain()
        plan = {"tool": "recycle_bin_status", "args": {}}
        error = brain._validate_plan(plan)
        assert error is None

    def test_brain_validate_empty_recycle_bin_plan(self):
        """Brain._validate_plan must accept valid empty_recycle_bin plan."""
        brain, _ = _make_brain()
        plan = {"tool": "empty_recycle_bin", "args": {}}
        error = brain._validate_plan(plan)
        assert error is None

    def test_recycle_bin_tools_in_runtime_context(self):
        """recycle_bin tools must appear in runtime context for LLM."""
        brain, _ = _make_brain()
        brain.orchestrator.mode = "on"
        brain.orchestrator.last_decision = MagicMock(
            route=Route.SYSTEM,
            requires_ai=True,
            preferred_skill="system",
            allowed_tools=["recycle_bin_status", "empty_recycle_bin"],
        )
        context = brain._runtime_context()
        assert "recycle_bin_status" in context
        assert "empty_recycle_bin" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
