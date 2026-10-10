from pathlib import Path

import pytest

from jarvis_core.golden_bridge import GoldenReadBridge
from jarvis_core.market_read_models import (
    SOURCE_DISABLED,
    UNKNOWN,
    build_market_intelligence_snapshot,
    session_observation,
)
from jarvis_core.models import Risk, SideEffectClass
from jarvis_core.service import JarvisService
from jarvis_core.runtime_profile import DEFAULT_PROFILE, WEB_AI_SAFE_PROFILE, set_active_runtime_profile


def _envelope(data, status="AVAILABLE", source="fixture"):
    return {
        "ok": status == "AVAILABLE",
        "availability": status,
        "freshness": "FRESH" if status == "AVAILABLE" else status,
        "observed_at": "2026-09-29T12:00:00+00:00",
        "provenance": {"source_module": source, "provider": source,
                       "freshness_state": "FRESH"},
        "data": data,
    }


def test_market_snapshot_normalizes_provenance_and_preserves_unknowns():
    payload = build_market_intelligence_snapshot(
        overview=_envelope({
            "updated_at": "2026-09-29T12:00:00+00:00",
            "assets": [{"symbol": "XAUUSD", "price": 2300.0, "group": "Metais"}],
            "news": [
                {"title": "Gold", "url": "https://example.test/gold", "source": "A"},
                {"title": "Gold", "url": "https://example.test/gold", "source": "A"},
            ],
            "macro": {"indicators": [{"id": "CPI", "name": "CPI", "value": 3.2, "unit": "%"}]},
            "economic_calendar": [],
            "sources": [{"name": "Fixture", "state": "online"}],
        }),
        chart=_envelope({"price": 2300.0, "candles": [], "levels": [], "structure_events": []}),
        scanner=_envelope({"normalized_results": [{
            "symbol": "XAUUSD", "selected_setup": "BOS", "score": 72,
            "readiness": "SETUP_DETECTED", "market_regime": "TREND",
        }]}),
        risk=_envelope({"risk_state": "UNKNOWN"}),
        validation=_envelope({"history": [{"evidence_class": "BACKTEST"}]}),
        symbol="XAUUSD", timeframe="M15", correlation_id="corr-b42",
    )

    assert payload["read_only"] is True
    assert payload["snapshot_id"].startswith("market_snapshot_")
    assert payload["correlation_id"] == "corr-b42"
    assert len(payload["news"]) == 1
    assert payload["news"][0]["sentiment"] == UNKNOWN
    assert payload["scanner"]["score_semantics"] == "SCORE_NOT_PROBABILITY"
    assert payload["robot_matcher_precursors"]["setup"] == "BOS"
    assert payload["performance"]["evidence_type_counts"] == {"BACKTEST": 1}
    assert "NO_VERIFIED_METRICS_IN_SOURCE" in payload["performance"]["limitations"]
    assert payload["matcher_authority"] == "NOT_IMPLEMENTED_IN_B4_2"


def test_source_disabled_is_explicit_and_never_becomes_zero():
    payload = build_market_intelligence_snapshot(
        overview=_envelope({"assets": [], "news": [], "macro": {}}, SOURCE_DISABLED),
        chart=_envelope({}, SOURCE_DISABLED),
        scanner=_envelope({}, SOURCE_DISABLED),
        risk=_envelope({}, SOURCE_DISABLED),
        validation=_envelope({}, SOURCE_DISABLED),
        symbol="XAUUSD", timeframe="M15", correlation_id="corr-disabled",
    )
    assert payload["status"] == SOURCE_DISABLED
    assert payload["source_availability"]["scanner"]["status"] == SOURCE_DISABLED
    assert payload["market_map"] == []
    assert payload["performance"]["sample_count"] == 0


def test_session_observation_uses_iana_dst_boundaries():
    from datetime import datetime, timezone

    london_before = session_observation(datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc))
    london_after = session_observation(datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc))
    new_york_before = session_observation(datetime(2026, 3, 8, 6, 30, tzinfo=timezone.utc))
    new_york_after = session_observation(datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc))

    assert london_before["sessions"]["LONDON"]["utc_offset"] == 0
    assert london_after["sessions"]["LONDON"]["utc_offset"] == 1
    assert new_york_before["sessions"]["NEW_YORK"]["utc_offset"] == -5
    assert new_york_after["sessions"]["NEW_YORK"]["utc_offset"] == -4


def test_bridge_builds_one_correlated_read_snapshot_without_execution():
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {"mt5_enabled": False})())
    bridge._market_overview = lambda: {"ok": True, "assets": [], "macro": {}, "news": []}
    bridge._market_chart = lambda symbol, timeframe: {"ok": False, "status": "SOURCE_DISABLED"}
    bridge.scanner_snapshot = lambda symbol, limit: {"ok": False, "availability": SOURCE_DISABLED, "data": {}}
    bridge.risk_detail = lambda: {"ok": False, "availability": SOURCE_DISABLED, "data": {}}
    bridge.validation_detail = lambda limit: {"ok": True, "data": {"history": []}}

    result = bridge.market_intelligence_snapshot("XAUUSD", "M15", "corr-test")

    assert result["ok"] is True
    assert result["correlation_id"] == "corr-test"
    assert result["data"]["execution_authority"] == "NONE"
    assert result["data"]["source_availability"]["risk"]["status"] == SOURCE_DISABLED


def test_service_exposes_b42_snapshot_as_low_risk_read_only_tool(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        tool = service.registry.get("golden_market_intelligence_snapshot")
        assert tool is not None
        assert tool.risk == Risk.LOW
        assert tool.side_effect_class == SideEffectClass.READ_ONLY
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(tool.security_requirements)
        analysis = service.registry.get("golden_panel_analysis")
        assert analysis is not None
        assert analysis.risk == Risk.LOW
        assert analysis.side_effect_class == SideEffectClass.READ_ONLY
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(analysis.security_requirements)
        discovery = service.registry.get("golden_panel_symbol_discovery")
        assert discovery is not None
        assert discovery.risk == Risk.LOW
        assert discovery.side_effect_class == SideEffectClass.READ_ONLY
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(discovery.security_requirements)
        market = service.registry.get("golden_panel_market_snapshot")
        assert market.risk == Risk.LOW
        assert market.side_effect_class == SideEffectClass.READ_ONLY
        assert market.capability_name == "market_data.read"
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(market.security_requirements)
        live_market = service.registry.get("golden_panel_market_update")
        assert live_market is not None
        assert live_market.risk == Risk.LOW
        assert live_market.side_effect_class == SideEffectClass.READ_ONLY
        assert live_market.capability_name == "market_data.read.current"
        assert set(("READ_ONLY", "NO_SIDE_EFFECT", "NO_TRADING")) <= set(live_market.security_requirements)
        assert service.registry.get("order_send") is None
        assert service.registry.get("position_close") is None
        assert service.registry.get("autotrading_change") is None
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_panel_analysis_does_not_call_model_without_real_candles(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        def read_tool(_name, arguments, **_kwargs):
            return {"ok": True, "data": {"ok": False,
                "status": "SOURCE_UNAVAILABLE", "timeframe": arguments["timeframe"],
                "asset": {"provider": "MT5", "provider_symbol": "XAUUSD",
                          "asset_class": "METALS"},
                "instrument": {}, "candles": [],
                "state": {"market_data_available": False, "freshness": "UNKNOWN"},
                "quote": {}, "provenance": {"source": "fixture"}}}
        service.execute_tool = read_tool
        service.golden_bridge.panel_macro_news = lambda *_args: {"data": {}}
        service.generate_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Brain não deve ser chamado sem candles"))

        result = service.golden_panel_analysis(
            "XAUUSD", "M15", "corr-offline", "MT5", "mt5:XAUUSD", "XAUUSD", "METALS")

        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["directional_bias"] == "UNAVAILABLE"
        assert result["execution_authority"] == "NONE"
        assert result["live_authorized"] is False
        assert result["order_sent"] is False
        assert result["position_mutated"] is False
        assert result["position_state"] == "NOT_REQUESTED"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


@pytest.mark.parametrize(("router_mode", "analysis_case"), [
    ("success", "baseline"),
    ("success", "direction_down"),
    ("success", "direction_lateral"),
    ("success", "direction_neutral"),
    ("success", "direction_undefined_null"),
    ("success", "unjustified_undefined"),
    ("success", "missing_direction"),
    ("success", "invalid_direction"),
    ("success", "missing_confidence"),
    ("success", "invalid_confidence"),
    ("provider_error", "baseline"),
    ("tool_proposal", "baseline"),
])
def test_panel_analysis_validates_structured_model_result_and_provenance(
        tmp_path, monkeypatch, router_mode, analysis_case):
    import json
    import time

    from jarvis_core import brain as brain_module
    from jarvis_core.brain import JarvisBrain
    from jarvis_core.orchestrator.models import ProviderResult, ProviderState

    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    brain = JarvisBrain(service.registry, service.legacy_memory,
                        orchestrator=service.orchestrator,
                        memory_v2=getattr(service, "memory_v2", None),
                        project_memory=getattr(service, "project_memory", None))
    monkeypatch.setattr(brain_module, "get_brain", lambda *_args, **_kwargs: brain)
    try:
        candles = [{"time": f"2026-10-03T12:{i:02d}:00+00:00", "close": 2300.0 + i,
                    "time_epoch": 1791028800 + i * 900,
                    "timestamp_interpretation": "UTC_PROJECTION_UNVERIFIED",
                    "open": 2299.0 + i, "high": 2301.0 + i, "low": 2298.0 + i}
                   for i in range(50)]
        def market_snapshot(_name, arguments, **_kwargs):
            timeframe = arguments["timeframe"]
            return {"ok": True, "data": {"ok": True, "status": "AVAILABLE",
                "snapshot_id": f"snapshot-fixture-{timeframe}",
                "asset": {"display_name": "Gold", "provider": "MT5",
                    "provider_symbol": "XAUUSD", "asset_class": "METALS"},
                "instrument": {"symbol": "XAUUSD", "currency_base": "XAU",
                               "currency_quote": "USD"},
                "quote": {"bid": 2349.0, "ask": 2350.0, "last": 2350.0,
                          "time": int(time.time()) + 3600,
                          "time_msc": (int(time.time()) + 3600) * 1000,
                          "timestamp_interpretation": "UTC_PROJECTION_UNVERIFIED",
                          "freshness": "UNKNOWN"},
                "candles": candles, "timeframe": timeframe, "candle_count": 50,
                "state": {"market_data_available": True, "freshness": "UNKNOWN"},
                "provenance": {"source": "MT5 fixture",
                               "capability": "MT5_MARKET_DATA_READ"}}}
        receive_counter = iter((1_000_000_000, 3_000_000_000, 5_000_000_000))
        tick_counter = iter((1791028800000, 1791028800000, 1791028802000))
        def market_read(name, arguments, **kwargs):
            if name == "golden_panel_market_update":
                received = next(receive_counter)
                tick_time_msc = next(tick_counter)
                return {"ok": True, "data": {"ok": True,
                    "received_monotonic_ns": received,
                    "quote": {"time_msc": tick_time_msc,
                              "bid": 2349.0 - received / 1_000_000_000,
                              "ask": 2350.0 - received / 1_000_000_000}}}
            return market_snapshot(name, arguments, **kwargs)
        service.execute_tool = market_read
        service.golden_bridge.panel_macro_news = lambda *_args: {"data": {
            "macro": {"status": "UNAVAILABLE", "freshness": "UNKNOWN", "facts": []},
            "economic_events": {"status": "UNAVAILABLE", "freshness": "UNKNOWN", "facts": []},
            "news": {"status": "UNAVAILABLE", "freshness": "UNKNOWN", "facts": []}}}
        structured = {
            "market_state": "TREND", "market_structure": "observed structure",
            "directional_bias": "ALTA", "trend": "observed trend", "momentum": "unknown",
            "breakout_context": "unknown", "volatility": "unknown",
            "support_levels": [2298.0], "resistance_levels": [2350.0], "confidence": 62,
            "entry_scenario": "scenario only", "invalidation": "condition only",
            "alternative_scenario": "alternative only", "target_scenario": "scenario only",
            "multi_timeframe_summary": "unverified",
            "macro_context": "unavailable", "news_event_risk": "unavailable",
            "summary": "structured summary",
            "risk_warnings": ["No trade authority"],
        }
        if analysis_case == "direction_down":
            structured.update(directional_bias="BAIXA", confidence=41)
        elif analysis_case == "direction_lateral":
            structured.update(directional_bias="LATERAL", confidence=55)
        elif analysis_case == "direction_neutral":
            structured.update(directional_bias="NEUTRA", confidence=50)
        elif analysis_case == "direction_undefined_null":
            structured.update(directional_bias="INDEFINIDA", confidence=None,
                              summary="Dados técnicos conflitantes; direção indeterminada.")
        elif analysis_case == "unjustified_undefined":
            structured.update(directional_bias="INDEFINIDA", confidence=None,
                              market_structure="", summary="")
        elif analysis_case == "missing_direction":
            structured.pop("directional_bias")
        elif analysis_case == "invalid_direction":
            structured["directional_bias"] = "BULLISH"
        elif analysis_case == "missing_confidence":
            structured.pop("confidence")
        elif analysis_case == "invalid_confidence":
            structured["confidence"] = 101
        router_calls = []
        router_outputs = []
        canonical_calls = []
        tool_calls = []
        original_execute_tool = service.execute_tool
        original_generate_response = service.generate_response

        def tracked_execute_tool(name, *args, **kwargs):
            tool_calls.append(name)
            return original_execute_tool(name, *args, **kwargs)

        service.execute_tool = tracked_execute_tool

        def tracked_generate_response(message, **kwargs):
            canonical_calls.append((message, kwargs))
            return original_generate_response(message, **kwargs)

        service.generate_response = tracked_generate_response

        def mock_model_router(messages, **kwargs):
            assert brain._allowed_tools == set()
            router_calls.append((messages, kwargs))
            if router_mode == "provider_error":
                return ProviderResult(
                    ok=False, provider="fixture", model="fixture-model",
                    state=ProviderState.OFFLINE, error="fixture unavailable",
                    attempts=({"provider": "gemini", "result": "OFFLINE",
                               "error_code": "PROVIDER_OR_INTEGRATION_FAILURE"},))
            output = (json.dumps({"response": json.dumps(structured)})
                      if router_mode == "success"
                      else json.dumps({"tool": "golden_panel_analysis", "args": {}}))
            router_outputs.append(output)
            return ProviderResult(
                ok=True, provider="fixture", model="fixture-model",
                state=ProviderState.AVAILABLE, output=output)

        service.orchestrator.models.execute = mock_model_router

        result = service.golden_panel_analysis(
            symbol="XAUUSD", timeframe="M15", correlation_id="corr-ready",
            provider="MT5", provider_asset_id="mt5:XAUUSD",
            provider_symbol="XAUUSD", asset_class="METALS")

        assert result["persistence"]["persisted"] is True
        stored = service.golden_analysis_repository.get(result["analysis_id"])
        assert stored["analysis"]["analysis_id"] == result["analysis_id"]
        assert stored["correlation_id"] == "corr-ready"
        assert len(router_calls) == 1
        _messages, router_kwargs = router_calls[0]
        assert router_kwargs["one_shot"] is True
        assert len(canonical_calls) == 1
        prompt, brain_kwargs = canonical_calls[0]
        assert router_kwargs["profile"]
        assert 'um único campo `response`' in prompt
        assert 'string contendo o objeto JSON da análise' in prompt
        assert brain_kwargs["surface"] == "market"
        assert brain_kwargs["include_memory_context"] is False
        assert brain_kwargs["record_conversation"] is False
        assert brain._allowed_tools is None
        assert brain.last_metrics["tool_catalog_size"] == 0
        assert tool_calls == (["golden_panel_market_snapshot"] * 6
                              + ["golden_panel_market_update"] * 3)
        valid_analysis_cases = {
            "baseline", "direction_down", "direction_lateral", "direction_neutral",
            "direction_undefined_null",
        }
        if router_mode == "success" and analysis_case in valid_analysis_cases:
            assert result["status"] == "PARTIAL"
            assert result["directional_bias"] == structured["directional_bias"]
            assert result["support_levels"] == [2298.0]
            assert result["resistance_levels"] == [2350.0]
            assert result["model"] == {"provider": "fixture", "name": "fixture-model"}
            assert result["response_validation"]["status"] == "VALID"
            assert result["response_validation"]["confidence_state"] == (
                "EXPLICIT_NULL" if structured["confidence"] is None else "NUMERIC")
            envelope = json.loads(router_outputs[0])
            assert set(envelope) == {"response"}
            parsed_analysis = json.loads(envelope["response"])
            assert set(parsed_analysis) == {
                "market_state", "market_structure", "directional_bias", "trend",
                "momentum", "breakout_context", "volatility", "support_levels",
                "resistance_levels", "multi_timeframe_summary", "macro_context",
                "news_event_risk", "confidence", "entry_scenario",
                "alternative_scenario", "invalidation", "target_scenario", "summary",
                "risk_warnings",
            }
            assert parsed_analysis == structured
        elif router_mode == "success":
            assert result["status"] == "ERROR"
            if analysis_case in {"missing_direction", "missing_confidence"}:
                assert result["validation_error_code"] == "REQUIRED_FIELDS_MISSING"
                expected_missing = ("directional_bias" if analysis_case == "missing_direction"
                                    else "confidence")
                assert result["response_validation"]["missing_fields"] == [expected_missing]
            else:
                expected_invalid = ("directional_bias" if analysis_case == "invalid_direction"
                                    else "confidence" if analysis_case == "invalid_confidence"
                                    else "market_structure")
                expected_code = ("INVALID_DIRECTIONAL_BIAS"
                                 if analysis_case == "invalid_direction"
                                 else "INVALID_CONFIDENCE" if analysis_case == "invalid_confidence"
                                 else "UNJUSTIFIED_INDETERMINATE_DIRECTION")
                assert result["validation_error_code"] == expected_code
                expected_invalid_fields = (["market_structure", "summary"]
                    if analysis_case == "unjustified_undefined" else [expected_invalid])
                assert result["response_validation"]["invalid_fields"] == expected_invalid_fields
            panel_audit = next(item for item in service.audit.recent(10)
                               if item["tool"] == "golden_panel_analysis")
            audit_result = json.loads(panel_audit["result"])
            assert audit_result["response_validation"] == result["response_validation"]
            assert audit_result["validation_error_code"] == result["validation_error_code"]
            assert "directional_bias" not in audit_result
            assert "confidence" not in audit_result
        else:
            assert result["status"] == "ERROR"
            if router_mode == "provider_error":
                assert result["summary"] == "Brain/ModelRouter indisponível."
                assert result["model_error_code"] == "PROVIDER_OR_INTEGRATION_FAILURE"
                panel_audit = next(item for item in service.audit.recent(10)
                                   if item["tool"] == "golden_panel_analysis")
                audit_result = json.loads(panel_audit["result"])
                assert audit_result["model_error_code"] == (
                    "PROVIDER_OR_INTEGRATION_FAILURE")
                assert "private" not in panel_audit["result"]
            else:
                assert result["summary"] == "Brain/ModelRouter indisponível."
                assert brain.last_metrics["llm_result_type"] == "PARSE_ERROR"
            assert result["execution_authority"] == "NONE"
            assert result["analysis_mode"] == "INDEPENDENT"
            assert result["request_type"] == "ON_DEMAND"
            assert result["analysis_status"] == result["status"]
            assert result["signal_status"] == "NOT_CONFIRMED"
            assert result["execution_status"] == "NOT_EXECUTED"
            assert result["opportunities"] == []
            assert result["opportunity_status"] == "NOT_RETURNED_BY_MODEL"
            assert result["order_sent"] is False
        assert result["position_mutated"] is False
        assert result["position_state"] == "NOT_REQUESTED"

        market_context = brain_kwargs["market_context"]
        assert "scanner" not in market_context
        assert "radar" not in market_context
        context_text = json.dumps(market_context).casefold()
        assert all(term not in context_text for term in (
            "selected_setup", "confluence_score", "scanner_score", "meta_strategy",
            "fullanalyzer", "masteranalyzer"))
        if router_mode == "success" and analysis_case in valid_analysis_cases:
            assert result["sources"]["technical"]["freshness"] == "UNKNOWN"
            assert set(result["sources"]["timeframes"]) == {"M1", "M5", "M15", "H1", "H4", "D1"}
            assert result["temporal_restriction"] is True
            assert result["context_availability"]["data_recency"] == "OBSERVED"
            assert result["temporal_restriction"] is True
            assert result["context_availability"]["absolute_utc"] == "UNKNOWN"
            assert brain_kwargs["market_context"]["temporal"][
                "RAW_TIMESTAMP_RELATION"] == "FUTURE_TIMESTAMP_UNVERIFIED"
            assert brain_kwargs["market_context"]["temporal"][
                "DATA_RECENCY_OBSERVED"] == "OBSERVED"
            recency_observation = brain_kwargs["market_context"]["temporal"][
                "RECENCY_OBSERVATION"]
            assert recency_observation["receive_interval_ms"] == 2000.0
            assert recency_observation["raw_tick_time_msc_start"] == 1791028800000
            assert recency_observation["raw_tick_time_msc_end"] > recency_observation[
                "raw_tick_time_msc_start"]
    finally:
        brain.close()
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_panel_recency_requires_local_receive_and_tick_progression(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        first = {"ok": True, "received_monotonic_ns": 1_000_000_000,
                 "quote": {"time_msc": 1000}}
        progressed = {"ok": True, "received_monotonic_ns": 2_000_000_000,
                      "quote": {"time_msc": 2000}}
        unchanged_tick = {"ok": True, "received_monotonic_ns": 3_000_000_000,
                          "quote": {"time_msc": 1000}}
        missing_receive = {"ok": True, "quote": {"time_msc": 3000}}
        too_short = {"ok": True, "received_monotonic_ns": 1_500_000_000,
                     "quote": {"time_msc": 2000}}
        timestamp_only = {"ok": True, "received_at": "2030-01-01T00:00:00Z",
                          "quote": {"time": 1893456000}}

        assert service._tick_recency_evidence(first, progressed) == (
            "OBSERVED", "LOCAL_RECEIVE_AND_TICK_PROGRESSION",
            {"receive_interval_ms": 1000.0, "raw_tick_time_msc_start": 1000,
             "raw_tick_time_msc_end": 2000, "tick_time_msc_delta": 1000,
             "bid_start": None, "ask_start": None, "bid_end": None, "ask_end": None})
        assert service._tick_recency_evidence(first, unchanged_tick)[0] == "UNKNOWN"
        assert service._tick_recency_evidence(first, missing_receive)[0] == "UNKNOWN"
        assert service._tick_recency_evidence(first, too_short)[0] == "UNKNOWN"
        assert service._tick_recency_evidence(first, timestamp_only)[0] == "UNKNOWN"
        assert service._tick_recency_evidence(first, {"ok": False})[0] == "UNKNOWN"

        later_progress = {"ok": True, "received_monotonic_ns": 5_000_000_000,
                          "quote": {"time_msc": 2000}}
        window_result = service._tick_recency_window_evidence(
            [first, unchanged_tick, later_progress])
        assert window_result[0] == "OBSERVED"
        assert window_result[2]["receive_interval_ms"] == 2000.0
        assert window_result[2]["raw_tick_time_msc_start"] == 1000
        assert window_result[2]["raw_tick_time_msc_end"] == 2000
        no_progress = {"ok": True, "received_monotonic_ns": 5_000_000_000,
                       "quote": {"time_msc": 1000}}
        assert service._tick_recency_window_evidence(
            [first, unchanged_tick, no_progress])[0] == "UNKNOWN"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_panel_analysis_fields_remain_compatible_with_desktop_rendering():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "jarvis_ui" / "src" / "desktop-shell.js").read_text(
        encoding="utf-8")
    renderer = shell[shell.index("function renderPanelAnalysis"):
                     shell.index("const observer = new MutationObserver", shell.index(
                         "function renderPanelAnalysis"))]

    assert '"PARTIAL"' in renderer
    assert 'result.directional_bias || "UNAVAILABLE"' in renderer
    assert 'Number.isFinite(result.confidence)' in renderer
    assert '"CONFIANÇA DO MODELO · NÃO PROBABILIDADE"' in renderer


def test_brain_can_answer_panel_without_retrieving_or_recording_conversation():
    from types import SimpleNamespace
    from jarvis_core.brain import JarvisBrain

    decision = SimpleNamespace(
        route=SimpleNamespace(value="CONVERSATION"), intent="conceptual_question",
        preferred_model_profile=None)
    orchestrator = SimpleNamespace(
        last_decision=None, skills={}, decide=lambda *_args, **_kwargs: decision)
    brain = JarvisBrain(registry=object(), orchestrator=orchestrator)
    prior_history = [{"time": 1, "input": "prior", "plan": {"response": "kept"},
                      "source": "text"}]
    brain.history = list(prior_history)
    brain._get_memory_context = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("panel analysis must not retrieve Jarvis memory"))
    llm_calls = []
    brain._call_llm = lambda _text, memory_context="", **kwargs: (
        llm_calls.append((memory_context, kwargs)) or
        {"ok": True, "response": '{"response":"grounded"}', "provider": "fixture"})

    try:
        result = brain.generate_response(
            "Analyze factual BTCUSD context", source="text",
            conversation_history=[], market_context={"symbol": "BTCUSD"},
            include_memory_context=False, record_history=False)

        assert result["ok"] is True
        assert result["response"] == "grounded"
        assert llm_calls[0][0] == ""
        assert llm_calls[0][1]["conversation_history"] == []
        assert brain.history == prior_history
    finally:
        brain.close()


def test_brain_unwraps_structured_market_json_from_canonical_response_envelope():
    import json
    from types import SimpleNamespace
    from jarvis_core.brain import JarvisBrain

    decision = SimpleNamespace(
        route=SimpleNamespace(value="CONVERSATION"), intent="conceptual_question",
        preferred_model_profile=None)
    orchestrator = SimpleNamespace(
        last_decision=None, skills={}, decide=lambda *_args, **_kwargs: decision)
    brain = JarvisBrain(registry=object(), orchestrator=orchestrator)
    market_result = {"market_state": "OBSERVED", "directional_bias": "INDEFINIDA"}
    encoded_market_result = json.dumps(market_result)
    rejected = brain._parse_llm_response(encoded_market_result)
    assert rejected == {
        "ok": False,
        "error": "Tool call inválido ou contém campos não permitidos.",
    }
    brain._call_llm = lambda *_args, **_kwargs: {
        "ok": True,
        "response": json.dumps({"response": encoded_market_result}),
        "provider": "fixture",
        "model": "fixture-model",
    }

    try:
        result = brain.generate_response(
            "Analise os fatos anexados", market_context={"surface": "market"},
            include_memory_context=False, record_history=False)

        assert result["ok"] is True
        assert json.loads(result["response"]) == market_result
    finally:
        brain.close()


def test_canonical_panel_response_keeps_audit_but_skips_conversation_history(
        tmp_path, monkeypatch):
    from jarvis_core import brain as brain_module

    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    calls = []

    class BrainFixture:
        last_llm = {}

        def generate_response(self, message, **kwargs):
            calls.append((message, kwargs))
            return {"ok": True, "response": "grounded", "provider": "fixture"}

    monkeypatch.setattr(brain_module, "get_brain", lambda *_args, **_kwargs: BrainFixture())
    try:
        result = service.generate_response(
            "facts only", surface="market", conversation_id="panel-once",
            market_context={"symbol": "BTCUSD"},
            audit_context={"correlation_id": "panel-audit-corr"},
            include_memory_context=False, record_conversation=False)

        assert result["ok"] is True
        assert calls[0][1]["include_memory_context"] is False
        assert calls[0][1]["record_history"] is False
        assert service._conversation_snapshot("panel-once") == []
        rows = service.audit.recent(1)
        assert rows[0]["command"] == "canonical_ai_response"
        assert rows[0]["audit_envelope"]["correlation_id"] == "panel-audit-corr"
    finally:
        service.close()


def test_panel_analysis_tool_obeys_security_manager_deny_without_market_calls(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.security.rules["golden_panel_analysis"] = "deny"
        service._active_audit_context = {"correlation_id": "panel-deny-corr"}
        service.golden_panel_analysis = lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("denied analysis must not call market sources or model"))

        result = service.execute_tool(
            "golden_panel_analysis", {"symbol": "BTCUSD", "timeframe": "M15",
                "correlation_id": "panel-deny-corr", "provider": "MT5",
                "provider_asset_id": "mt5:BTCUSD", "provider_symbol": "BTCUSD",
                "asset_class": "CRYPTO"}, command="security-test")

        assert result["ok"] is False
        assert "bloqueada" in result["error"]
        assert service.state.value == "IDLE"
        assert service.audit.recent(1)[0]["audit_envelope"]["security_decision"] == "DENY"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


@pytest.mark.parametrize(("mode", "request_type", "reason", "status"), [
    ("STRATEGY", "ON_DEMAND", "STRATEGY_RULESET_UNAVAILABLE", "STRATEGY_UNAVAILABLE"),
    ("INDEPENDENT", "MONITORING", "MONITORING_NOT_ACTIVE", "MONITORING_DISABLED"),
])
def test_panel_analysis_modes_fail_closed_before_sources_or_model(
        tmp_path, mode, request_type, reason, status):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.execute_tool = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("modo indisponível não pode consultar fontes"))
        service.generate_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("modo indisponível não pode chamar Brain/ModelRouter"))

        result = service.golden_panel_analysis(
            "BTCUSD", "M15", "mode-gate", "MT5", "mt5:BTCUSD", "BTCUSD", "CRYPTO",
            analysis_mode=mode, request_type=request_type, strategy_id="ma_cross")

        assert result["status"] == status
        assert result["reason_code"] == reason
        assert result["analysis_mode"] == mode
        assert result["execution_authority"] == "NONE"
        assert result["signal_status"] == "NOT_CONFIRMED"
        assert result["execution_status"] == "NOT_EXECUTED"
        audited = next(row for row in service.audit.recent(5)
                       if row["tool"] == "golden_panel_analysis")
        assert audited["audit_envelope"]["correlation_id"] == "mode-gate"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_panel_opportunities_require_available_evidence_and_are_never_signals():
    frames = {
        "M5": {"status": "AVAILABLE", "snapshot_id": "snap-m5"},
        "M15": {"status": "UNAVAILABLE", "snapshot_id": "snap-m15"},
    }
    valid = {
        "horizon": "SCALP", "direction": "ALTA", "rationale": "Fixture rationale",
        "confirmation_conditions": ["Condition from fixture"],
        "conditional_entry": None, "invalidation": "Fixture invalidation",
        "risk": "Unknown; no sizing", "target": "Fixture target",
        "evidence_timeframes": ["M5"],
    }
    normalized = JarvisService._normalize_panel_opportunities([valid, {
        "horizon": "DAY_TRADE", "direction": "BAIXA", "rationale": "Invalid ref",
        "confirmation_conditions": ["Condition"],
        "conditional_entry": "Conditional only", "invalidation": "Invalidation",
        "risk": "Unknown", "target": "Target",
        "evidence_timeframes": ["M15"],
    }], frames, "analysis-fixture")

    assert len(normalized) == 1
    assert normalized[0]["classification"] == "OPPORTUNITY_NOT_SIGNAL"
    assert normalized[0]["signal_confirmed"] is False
    assert normalized[0]["execution_authority"] == "NONE"
    assert normalized[0]["evidence_references"] == ["snap-m5"]
    assert JarvisService._normalize_panel_opportunities(
        [valid], frames, "analysis-fixture",
        requested_style="SWING") == []


def test_panel_horizon_coverage_does_not_infer_session_data():
    coverage = JarvisService._panel_horizon_contract({
        "M1": {"status": "AVAILABLE", "snapshot_id": "s1"},
        "M5": {"status": "UNAVAILABLE", "snapshot_id": "s5"},
        "H1": {"status": "AVAILABLE", "snapshot_id": "sh1"},
        "H4": {"status": "UNAVAILABLE", "snapshot_id": "sh4"},
        "D1": {"status": "UNAVAILABLE", "snapshot_id": "sd1"},
    })

    assert [(row["style"], row["status"]) for row in coverage] == [
        ("SCALP", "PARTIAL"), ("DAY_TRADE", "PARTIAL"), ("SWING", "PARTIAL")]
    assert all(any("UTC" in item for item in row["limitations"])
               for row in coverage)


def test_panel_factual_context_reuses_golden_sources_without_strategy_conclusions(monkeypatch):
    import market_data

    calls = []
    def macro_snapshot(_symbols):
        calls.append("macro")
        return {"updated_at": "raw-macro-time", "indicators": [{
            "id": "CPI", "name": "Consumer prices", "value": 3.1,
            "previous": 3.0, "unit": "%", "date": "2026-10-01",
            "score": 88, "bias": "BUY", "trade_direction": "LONG"}]}
    def economic_calendar():
        calls.append("calendar")
        return ([{"event": "CPI", "currency": "USD",
            "date": "2026-10-04", "importance": "high", "actual": "UNKNOWN",
            "source": "fixture"}], "fixture-calendar")
    def market_news():
        calls.append("news")
        return ([{"title": "Observed headline", "source": "fixture",
                  "published_at": "2026-10-03T10:00:00Z", "topic": "macro"}],
                "fixture-news")
    monkeypatch.setattr(market_data, "_macro_snapshot", macro_snapshot)
    monkeypatch.setattr(market_data, "_economic_calendar", economic_calendar)
    monkeypatch.setattr(market_data, "_market_news", market_news)

    result = GoldenReadBridge().panel_macro_news(
        "BTCUSD", "CRYPTO", {"currency_base": "BTC", "currency_quote": "USD"},
        "corr-factual")
    payload = result["data"]
    serialized = str(payload).casefold()

    assert calls == ["macro", "calendar", "news"]
    assert payload["macro"]["facts"][0]["value"] == 3.1
    assert payload["macro"]["facts"][0]["derived"] is False
    assert payload["economic_events"]["facts"][0]["event"] == "CPI"
    assert payload["news"]["facts"][0]["title"] == "Observed headline"
    assert all(term not in serialized for term in ("score", "trade_direction", "buy", "long"))
    assert payload["execution_authority"] == "NONE"
    assert payload["read_only"] is True


def test_panel_analysis_stops_on_stale_technical_context(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        def read_tool(_name, arguments, **_kwargs):
            candles = [{"time": f"2026-10-01T00:{i:02d}:00+00:00", "open": 1.0,
                        "high": 1.1, "low": 0.9, "close": 1.0} for i in range(50)]
            return {"ok": True, "data": {"ok": True, "status": "PARTIAL",
                "snapshot_id": "stale-snapshot", "timeframe": arguments["timeframe"],
                "asset": {"display_name": "Gold", "provider": "MT5",
                    "provider_symbol": "XAUUSD", "asset_class": "METALS"},
                "instrument": {"symbol": "XAUUSD"}, "quote": {"freshness": "STALE"},
                "candles": candles,
                "state": {"market_data_available": True, "freshness": "STALE"},
                "provenance": {"source": "fixture"}}}
        service.execute_tool = read_tool
        service.golden_bridge.panel_macro_news = lambda *_args: {"data": {}}
        service.generate_response = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Brain não deve analisar candles stale"))

        result = service.golden_panel_analysis(
            "XAUUSD", "M15", "corr-stale", "MT5", "mt5:XAUUSD", "XAUUSD", "METALS")

        assert result["status"] == "STALE"
        assert result["directional_bias"] == "UNAVAILABLE"
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_b42_route_and_ui_keep_one_canonical_market_boundary():
    root = Path(__file__).resolve().parents[1]
    server = (root / "server_agent.py").read_text(encoding="utf-8")
    app = (root / "jarvis_ui" / "src" / "app.js").read_text(encoding="utf-8")
    assert "/api/jarvis/golden/market-intelligence" in server
    assert "/api/jarvis/golden/panel-analysis" in server
    assert "/api/jarvis/golden/symbol-discovery" in server
    assert "/api/jarvis/golden/market-data" in server
    assert "/api/jarvis/golden/market-live" in server
    assert "golden_panel_analysis" in server
    assert '"analysis_mode": str(payload.get("analysis_mode") or "INDEPENDENT")' in server
    assert "golden_market_intelligence_snapshot" in server
    assert "/api/jarvis/golden/market-intelligence" in app
    assert "/api/scanner/" not in app[app.index("const b3State ="):app.index("window.JarvisB3Refresh")]
    assert "order_send" not in app[app.index("const b3State ="):app.index("window.JarvisB3Refresh")]


def test_panel_crypto_picker_invalidates_old_external_selection_and_has_no_fallback():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "jarvis_ui" / "src" / "desktop-shell.js").read_text(encoding="utf-8")
    market_data_source = (root / "market_data.py").read_text(encoding="utf-8").casefold()
    assert 'saved.provider !== "MT5"' in shell
    assert "localStorage.removeItem(panelAssetStorageKey)" in shell
    assert '["SOURCE_UNAVAILABLE", "SOURCE_DISABLED", "SOURCE_DISABLED_BY_PROFILE"]' in shell
    assert "catálogo mt5 indisponível" in shell.casefold()
    assert 'assetSelect?.addEventListener("change"' in shell
    assert 'asset.provider_asset_id === `mt5:${asset.provider_symbol}`' in shell
    assert "coingecko" not in market_data_source
    assert "api.binance" not in market_data_source


def test_panel_discovery_is_mt5_only_and_disabled_state_is_explicit(monkeypatch):
    from jarvis_core.tools import market_readonly
    monkeypatch.setattr(market_readonly, "mt5_search_symbols", lambda *_args: {
        "status": "AVAILABLE", "assets": [{"provider": "MT5",
            "provider_asset_id": "mt5:BTCUSD", "provider_symbol": "BTCUSD",
            "symbol": "BTCUSD", "display_name": "Bitcoin", "asset_class": "CRYPTO",
            "source_available": True}], "enumerated_count": 1,
        "classification_counts": {"CRYPTO": 1},
    })
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_read_models_enabled": True, "mt5_market_data_read_enabled": True,
    })())
    crypto = bridge.panel_symbol_discovery("BTC", "CRYPTO", "corr-discovery")
    assert crypto["data"]["assets"][0]["provider"] == "MT5"
    assert set(crypto["data"]["sources"]) == {"MT5"}
    assert crypto["data"]["execution_authority"] == "NONE"
    assert crypto["provenance"]["correlation_id"] == "corr-discovery"

    disabled = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_read_models_enabled": True, "mt5_market_data_read_enabled": False,
    })()).panel_symbol_discovery("", "CRYPTO")
    assert disabled["data"]["status"] == "SOURCE_DISABLED"
    assert disabled["data"]["assets"] == []


def test_mt5_symbol_discovery_classifies_real_metadata_without_mutation(monkeypatch):
    from types import SimpleNamespace
    from jarvis_core.tools import market_readonly

    symbols = [
        SimpleNamespace(name="EURUSD.a", description="Euro vs US Dollar",
                        path="Forex\\Majors", currency_base="EUR", currency_profit="USD"),
        SimpleNamespace(name="GOLDx", description="Gold Spot", path="Metals\\Gold",
                        currency_base="XAU", currency_profit="USD"),
        SimpleNamespace(name="BTCUSD.r", description="Bitcoin CFD", path="Crypto\\BTC",
                        currency_base="BTC", currency_profit="USD"),
    ]
    class FakeMT5:
        def symbols_get(self):
            return symbols
        def symbol_info(self, _name):
            return SimpleNamespace(digits=2, point=0.01, trade_tick_size=0.01,
                                   trade_contract_size=1.0)

    monkeypatch.setattr(market_readonly, "_market_data_connection",
                        lambda: (FakeMT5(), None, ""))
    result = market_readonly.mt5_search_symbols("USD", "ALL")

    assert {item["asset_class"] for item in result["assets"]} == {"FOREX", "METALS", "CRYPTO"}
    assert {item["provider_symbol"] for item in result["assets"]} == {
        "EURUSD.a", "GOLDx", "BTCUSD.r"}
    assert all(item["market_data_available"] is False for item in result["assets"])
    assert all(item["digits"] == 2 and item["point_size"] == 0.01
               for item in result["assets"])


def test_mt5_blank_query_enumerates_all_classified_provider_symbols(monkeypatch):
    from types import SimpleNamespace
    from jarvis_core.tools import market_readonly

    symbols = [SimpleNamespace(name=f"EURUSD.{suffix}", description="Euro vs Dollar",
                               path="Forex\\Majors", currency_base="EUR", currency_profit="USD")
               for suffix in ("a", "b", "c")]
    class FakeMT5:
        def symbols_get(self): return symbols
        def symbol_info(self, _name):
            return SimpleNamespace(digits=5, point=0.00001, trade_tick_size=0.00001,
                                   trade_contract_size=100000)

    monkeypatch.setattr(market_readonly, "_market_data_connection", lambda: (FakeMT5(), None, ""))
    result = market_readonly.mt5_search_symbols("", "FOREX")
    assert result["status"] == "AVAILABLE"
    assert {item["provider_symbol"] for item in result["assets"]} == {
        "EURUSD.a", "EURUSD.b", "EURUSD.c"}


def test_mt5_bitcoin_discovery_keeps_broker_identity_and_conflicting_metadata(monkeypatch):
    from types import SimpleNamespace
    from jarvis_core.tools import market_readonly

    class FakeMT5:
        def symbols_get(self):
            return [SimpleNamespace(name="XBTUSD.pro", description="Bitcoin vs US Dollar",
                                    path="Crypto\\Bitcoin", currency_base="USD",
                                    currency_profit="USD"),
                    SimpleNamespace(name="BCHUSD", description="Bitcoin Cash vs US Dollar",
                                    path="Crypto\\Bitcoin Cash", currency_base="BCH",
                                    currency_profit="USD")]
        def symbol_info(self, symbol):
            base = "USD" if symbol == "XBTUSD.pro" else "BCH"
            quote = "USD"
            return SimpleNamespace(digits=2, point=0.01, trade_tick_size=0.01,
                trade_contract_size=1.0, currency_base=base, currency_profit=quote,
                trade_mode=4, trade_exemode=2, start_time=0, expiration_time=0)
        def symbol_info_tick(self, symbol):
            assert symbol == "XBTUSD.pro", "Bitcoin Cash is not the Bitcoin contract"
            return SimpleNamespace(time=1791057600)
        def __getattr__(self, name):
            if name in {"symbol_select", "account_info", "orders_get", "positions_get",
                        "order_send", "shutdown"}:
                raise AssertionError(f"forbidden MT5 API called: {name}")
            raise AttributeError(name)

    monkeypatch.setattr(market_readonly, "_market_data_connection",
                        lambda: (FakeMT5(), None, ""))
    result = market_readonly.mt5_search_symbols("", "CRYPTO")
    asset = next(row for row in result["assets"] if row["provider_symbol"] == "XBTUSD.pro")
    bitcoin_cash = next(row for row in result["assets"] if row["provider_symbol"] == "BCHUSD")

    assert asset["provider_symbol"] == "XBTUSD.pro"
    assert asset["provider_asset_id"] == "mt5:XBTUSD.pro"
    assert asset["display_name"] == "Bitcoin"
    assert asset["currency_base_reported"] == "USD"
    assert asset["currency_profit_reported"] == "USD"
    assert asset["price_unit"] is None
    assert asset["metadata_warnings"] == [
        "BROKER_CURRENCY_METADATA_CONFLICTS_WITH_BITCOIN_IDENTITY"]
    assert asset["last_tick_timestamp"] is not None
    assert asset["session_metadata"]["trade_mode"] == 4
    assert bitcoin_cash["display_name"] == "Bitcoin Cash vs US Dollar"
    assert bitcoin_cash["last_tick_timestamp"] is None


def test_mt5_snapshot_uses_only_quote_instrument_and_candle_read_methods(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from jarvis_core.tools import market_readonly

    now = int(datetime.now(timezone.utc).timestamp())
    calls = []
    class FakeMT5:
        TIMEFRAME_M15 = 15
        def symbol_info(self, symbol):
            calls.append(("symbol_info", symbol))
            return SimpleNamespace(name=symbol, description="Euro vs US Dollar",
                path="Forex\\Majors", currency_base="EUR", currency_profit="USD",
                digits=5, point=0.00001, trade_tick_size=0.00001, trade_mode=4)
        def symbol_info_tick(self, symbol):
            calls.append(("symbol_info_tick", symbol))
            return SimpleNamespace(bid=1.1, ask=1.1001, last=1.1,
                                   time=now, time_msc=now * 1000 + 123)
        def copy_rates_from_pos(self, symbol, timeframe, start, count):
            calls.append(("copy_rates_from_pos", symbol, timeframe, start, count))
            return [{"time": now - (count - index) * 900, "open": 1.0 + index / 1000,
                     "high": 1.01 + index / 1000, "low": 0.99 + index / 1000,
                     "close": 1.005 + index / 1000, "tick_volume": 12,
                     "real_volume": 0} for index in range(count)]
        def __getattr__(self, name):
            if name in {"account_info", "orders_get", "positions_get", "order_send",
                        "symbol_select", "shutdown"}:
                raise AssertionError(f"forbidden MT5 API called: {name}")
            raise AttributeError(name)

    monkeypatch.setattr(market_readonly, "_market_data_connection",
                        lambda: (FakeMT5(), SimpleNamespace(data_path="approved-root"), ""))
    result = market_readonly.mt5_market_data_snapshot("EURUSD.a", "M15", 60)

    assert result["asset"]["asset_class"] == "FOREX"
    assert result["instrument"]["currency_base"] == "EUR"
    assert result["quote"]["bid"] == 1.1
    assert result["quote"]["time"] == now
    assert result["quote"]["time_epoch"] == now
    assert result["quote"]["time_msc"] == now * 1000 + 123
    assert len(result["candles"]) == 60
    assert result["candles"][-1]["time_interpretation"] == "UTC_PROJECTION_UNVERIFIED"
    assert result["state"]["time_status"] == "UNKNOWN"
    assert result["state"]["temporal_authority"] == "UNKNOWN"
    assert result["state"]["freshness"] == "UNKNOWN"
    assert result["state"]["market_data_available"] is True
    assert result["status"] == "PARTIAL"
    assert "TEMPORAL_AUTHORITY_UNKNOWN" in result["state"]["partial_reasons"]
    assert result["technical_context"]["status"] == "AVAILABLE"
    assert result["provenance"]["capability"] == "MT5_MARKET_DATA_READ"
    assert {call[0] for call in calls} == {
        "symbol_info", "symbol_info_tick", "copy_rates_from_pos"}


def test_market_data_connection_never_initializes_when_approved_terminal_is_absent(monkeypatch):
    import sys
    from types import SimpleNamespace
    import psutil
    from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE, set_active_runtime_profile, DEFAULT_PROFILE
    from jarvis_core.tools import market_readonly

    initialize_calls = []
    monkeypatch.setattr(psutil, "process_iter", lambda _attrs: [])
    monkeypatch.setitem(sys.modules, "MetaTrader5", SimpleNamespace(
        initialize=lambda **_kwargs: initialize_calls.append(True) or True))
    set_active_runtime_profile(WEB_AI_SAFE_PROFILE)
    try:
        mt5, terminal, reason = market_readonly._market_data_connection()
        assert mt5 is None and terminal is None
        assert reason == "APPROVED_TERMINAL_NOT_RUNNING"
        assert initialize_calls == []
    finally:
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_market_data_connection_rejects_wrong_terminal_data_root(monkeypatch):
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import psutil
    from jarvis_core.runtime_profile import WEB_AI_SAFE_PROFILE, set_active_runtime_profile, DEFAULT_PROFILE
    from jarvis_core.tools import market_readonly

    approved_exe = str(market_readonly._TERMINAL_PATHS[0].resolve())
    process = SimpleNamespace(pid=18772,
        info={"name": "terminal64.exe", "exe": approved_exe})
    initialize_calls = []
    monkeypatch.setattr(psutil, "process_iter", lambda _attrs: [process])
    monkeypatch.setitem(sys.modules, "MetaTrader5", SimpleNamespace(
        initialize=lambda **_kwargs: initialize_calls.append(True) or True,
        terminal_info=lambda: SimpleNamespace(connected=True,
            data_path=str(Path.home() / "MetaQuotes" / "Terminal" / "WRONG_ROOT"))))
    set_active_runtime_profile(WEB_AI_SAFE_PROFILE)
    try:
        mt5, terminal, reason = market_readonly._market_data_connection()
        assert mt5 is None and terminal is not None
        assert reason == "APPROVED_DATA_ROOT_MISMATCH"
        assert initialize_calls == [True]
    finally:
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_external_provider_identity_is_rejected_for_crypto_snapshot():
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_data_read_enabled": True, "mt5_market_data_read_enabled": True,
    })())
    result = bridge.panel_market_snapshot(
        "CoinGecko", "bitcoin", "BTC", "CRYPTO", "M15", 120, "corr-btc")
    data = result["data"]
    assert data["status"] == "IDENTITY_MISMATCH"
    assert data["execution_authority"] == "NONE"


def test_crypto_panel_analysis_rejects_external_provider_before_model(tmp_path, monkeypatch):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.orchestrator.models.execute = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("External provider must be rejected before model"))
        result = service.golden_panel_analysis(
            "BTC", "M15", "corr-crypto", "CoinGecko", "bitcoin", "BTC", "CRYPTO")

        assert result["status"] in {"INSUFFICIENT_DATA", "UNAVAILABLE"}
        assert result.get("identity_error") or result.get("status") == "UNAVAILABLE"
        assert result["support_levels"] == result["resistance_levels"] == []
        assert result["algorithmic_strength"]["score"] is None
        assert result["execution_authority"] == "NONE"
        assert result["order_sent"] is False
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)


def test_panel_discovery_exposes_only_dynamically_discovered_mt5_crypto(monkeypatch):
    variants = [{"provider": "MT5", "provider_asset_id": f"mt5:{symbol}",
                 "provider_symbol": symbol, "symbol": symbol,
                 "display_symbol": symbol, "display_name": "Bitcoin",
                 "asset_class": "CRYPTO", "source_available": True,
                 "market_data_available": False, "description": desc}
                for symbol, desc in (("BTCUSD", "Bitcoin vs US Dollar"),
                                     ("BTCUSD.r", "Bitcoin USD contract r"))]
    from jarvis_core.tools import market_readonly
    monkeypatch.setattr(market_readonly, "mt5_search_symbols", lambda *_args: {
        "status": "AVAILABLE", "assets": variants, "enumerated_count": 538,
        "classification_counts": {"CRYPTO": 9},
    })
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_read_models_enabled": True,
        "market_data_read_enabled": True,
        "mt5_market_data_read_enabled": True,
    })())

    result = bridge.panel_symbol_discovery("BTC", "CRYPTO", "corr-btc-catalog")
    assets = result["data"]["assets"]

    assert {(row["provider"], row["provider_asset_id"], row["provider_symbol"])
            for row in assets} == {
                ("MT5", "mt5:BTCUSD", "BTCUSD"),
                ("MT5", "mt5:BTCUSD.r", "BTCUSD.r"),
            }
    assert set(result["data"]["sources"]) == {"MT5"}
    assert result["data"]["sources"]["MT5"]["status"] == "AVAILABLE"
    assert result["data"]["execution_authority"] == "NONE"


def test_mt5_crypto_snapshot_preserves_exact_provider_symbol_and_never_fuses(monkeypatch):
    from jarvis_core.golden_bridge import GoldenReadBridge
    from jarvis_core.tools import market_readonly
    snapshot_calls = []
    monkeypatch.setattr(market_readonly, "mt5_market_data_snapshot",
                        lambda symbol, timeframe, count: snapshot_calls.append(
                            (symbol, timeframe, count)) or {
                            "ok": True, "status": "PARTIAL", "provider": "MT5",
                            "asset": {"asset_id": f"mt5:{symbol}",
                                      "provider_symbol": symbol,
                                      "asset_class": "CRYPTO", "provider": "MT5"},
                            "candles": [], "read_only": True,
                            "provenance": {"provider": "MT5"},
                        })
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_data_read_enabled": True, "mt5_market_data_read_enabled": True,
    })())

    result = bridge.panel_market_snapshot(
        "MT5", "mt5:BTCUSD.r", "BTCUSD.r", "CRYPTO", "M15", 120, "corr-btc-mt5")

    assert result["data"]["provider"] == "MT5"
    assert result["data"]["asset"]["provider_symbol"] == "BTCUSD.r"
    assert result["data"]["provenance"]["provider"] == "MT5"
    assert snapshot_calls == [("BTCUSD.r", "M15", 120)]


def test_mt5_live_update_reads_only_one_forming_candle_and_current_tick(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from jarvis_core.tools import market_readonly

    now = int(datetime.now(timezone.utc).timestamp())
    calls = []
    class FakeMT5:
        TIMEFRAME_M15 = 15
        def symbol_info(self, symbol):
            calls.append(("symbol_info", symbol))
            return SimpleNamespace(name=symbol, description="Bitcoin vs US Dollar",
                                   path="Crypto\\BTC", currency_base="BTC",
                                   currency_profit="USD")
        def symbol_info_tick(self, symbol):
            calls.append(("symbol_info_tick", symbol))
            return SimpleNamespace(bid=100.0, ask=101.0, last=100.5,
                                   time=now, time_msc=now * 1000 + 456)
        def copy_rates_from_pos(self, symbol, timeframe, start, count):
            calls.append(("copy_rates_from_pos", symbol, timeframe, start, count))
            return [{"time": now - now % 900, "open": 100.0, "high": 102.0,
                     "low": 99.0, "close": 101.0, "tick_volume": 12, "real_volume": 0}]
        def __getattr__(self, name):
            if name in {"account_info", "orders_get", "positions_get", "order_send",
                        "symbol_select", "shutdown"}:
                raise AssertionError(f"forbidden MT5 API called: {name}")
            raise AttributeError(name)

    monkeypatch.setattr(market_readonly, "_market_data_connection",
                        lambda: (FakeMT5(), SimpleNamespace(), ""))
    result = market_readonly.mt5_market_data_update("BTCUSD", "M15")

    assert result["ok"] is True
    assert result["provider"] == "MT5"
    assert result["quote"]["bid"] == 100.0
    assert result["quote"]["ask"] == 101.0
    assert result["quote"]["time"] == now
    assert result["quote"]["time_epoch"] == now
    assert result["quote"]["time_msc"] == now * 1000 + 456
    assert result["candle"]["close"] == 101.0
    assert result["candle"]["time_interpretation"] == "UTC_PROJECTION_UNVERIFIED"
    assert result["time_status"] == "UNKNOWN"
    assert result["temporal_authority"] == "UNKNOWN"
    assert result["asset_class"] == "CRYPTO"
    assert result["freshness"] == "UNKNOWN"
    assert "observed_at" not in result
    assert [call for call in calls if call[0] == "copy_rates_from_pos"] == [
        ("copy_rates_from_pos", "BTCUSD", 15, 0, 1)]
    assert {call[0] for call in calls} == {"symbol_info", "symbol_info_tick", "copy_rates_from_pos"}


def test_live_market_bridge_rejects_provider_identity_mismatch(monkeypatch):
    from jarvis_core import golden_bridge
    from jarvis_core.golden_bridge import GoldenReadBridge
    monkeypatch.setattr(golden_bridge, "_envelope", lambda _capability, payload, *_args, **_kwargs: payload)
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_data_read_enabled": True, "mt5_market_data_read_enabled": True,
    })())
    result = bridge.panel_market_update("MT5", "mt5:BTCUSD", "EURUSD", "CRYPTO", "M15")
    assert result["status"] == "IDENTITY_MISMATCH"


def test_live_market_bridge_keeps_source_time_unknown_and_reconciles_class(monkeypatch):
    from jarvis_core.tools import market_readonly
    monkeypatch.setattr(market_readonly, "mt5_market_data_update", lambda *_args: {
        "ok": True, "status": "AVAILABLE", "provider": "MT5",
        "provider_symbol": "BTCUSD", "asset_class": "CRYPTO", "timeframe": "M15",
        "quote": {"bid": 100.0, "ask": 101.0},
        "candle": {"time_epoch": 100}, "received_at": "2026-10-03T00:00:00+00:00",
        "freshness": "UNKNOWN", "read_only": True,
    })
    bridge = GoldenReadBridge(runtime_profile=type("Profile", (), {
        "market_data_read_enabled": True, "mt5_market_data_read_enabled": True,
    })())
    result = bridge.panel_market_update("MT5", "mt5:BTCUSD", "BTCUSD", "CRYPTO", "M15")
    assert result["data"]["asset_class"] == "CRYPTO"
    assert result["freshness"] == "UNKNOWN"
    assert result["data"]["freshness"] == "UNKNOWN"


def test_mt5_crypto_clock_skew_and_missing_quote_fail_closed(monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from jarvis_core.tools import market_readonly

    now = int(datetime.now(timezone.utc).timestamp())
    class FakeMT5:
        TIMEFRAME_M15 = 15
        def symbol_info(self, symbol):
            return SimpleNamespace(name=symbol, description="Bitcoin vs US Dollar",
                path="Crypto\\BTC", currency_base="USD", currency_profit="USD",
                digits=2, point=0.01, trade_tick_size=0.01, trade_mode=4)
        def symbol_info_tick(self, _symbol):
            return SimpleNamespace(bid=100.0, ask=101.0, last=100.5,
                                   time=now + 3 * 3600)
        def copy_rates_from_pos(self, _symbol, _tf, _start, count):
            return [{"time": now + 3 * 3600 - (count - index) * 900,
                     "open": 100.0, "high": 102.0, "low": 99.0,
                     "close": 101.0, "tick_volume": 10, "real_volume": 0}
                    for index in range(count)]

    monkeypatch.setattr(market_readonly, "_market_data_connection",
                        lambda: (FakeMT5(), SimpleNamespace(data_path="approved-root"), ""))
    result = market_readonly.mt5_market_data_snapshot("BTCUSD", "M15", 120)

    assert result["quote"]["bid"] == 100.0
    assert result["state"]["freshness"] == "UNKNOWN"
    assert result["state"]["market_session"] == "UNKNOWN"
    assert result["state"]["provider_epoch_relation"] == "AHEAD_OF_LOCAL_UTC_UNVERIFIED"
    assert result["state"]["timestamp_comparison"] == "UNVERIFIED_PROVIDER_EPOCH_VS_LOCAL_UTC"
    assert result["state"]["quote_epoch_delta_seconds_unverified"] > 300
    assert result["state"]["stale"] is None
    assert result["state"]["market_data_available"] is True
    assert result["state"]["freshness"] == "UNKNOWN"
    assert result["state"]["temporal_authority"] == "UNKNOWN"
    assert result["quote"]["time_epoch"] == now + 3 * 3600
    assert result["quote"]["time_msc"] is None
    assert "PROVIDER_EPOCH_DIFFERS_FROM_LOCAL_UTC_UNVERIFIED" in result["state"]["partial_reasons"]
    assert "TEMPORAL_AUTHORITY_UNKNOWN" in result["provenance"]["warnings"]


def test_mt5_bitcoin_analysis_rejects_stale_snapshot_without_model_call(tmp_path):
    service = JarvisService(str(tmp_path), runtime_profile=WEB_AI_SAFE_PROFILE)
    try:
        service.golden_bridge.panel_market_snapshot = lambda *_args, **_kwargs: {
            "ok": True, "status": "PARTIAL", "data": {
                "ok": True, "status": "PARTIAL", "snapshot_id": "btc-mt5-stale",
                "asset": {"asset_id": "mt5:BTCUSD", "display_name": "Bitcoin",
                          "provider": "MT5", "provider_symbol": "BTCUSD",
                          "asset_class": "CRYPTO"},
                "instrument": {"quote_currency": "USD"},
                "quote": {"bid": 100.0, "ask": 101.0, "freshness": "UNKNOWN"},
                "candles": [{"time": "2026-10-03T12:00:00+00:00", "close": 100}],
                "technical_context": {"status": "AVAILABLE"},
                "state": {"market_data_available": False, "freshness": "UNKNOWN",
                          "market_session": "UNKNOWN"},
                "provenance": {"provider": "MT5", "fetched_at": "now",
                               "capability": "MT5_MARKET_DATA_READ"},
            },
        }
        service.orchestrator.models.execute = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("MT5 stale/unknown evidence must not reach the model"))

        result = service.golden_panel_analysis(
            "BTCUSD", "M15", "corr-btc-stale", "MT5", "mt5:BTCUSD",
            "BTCUSD", "CRYPTO")

        assert result["provider"] == "MT5"
        assert result["provider_symbol"] == "BTCUSD"
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["model"]["provider"] == "NONE"
        assert result["execution_authority"] == "NONE"
        assert result["order_sent"] is False
    finally:
        service.close()
        set_active_runtime_profile(DEFAULT_PROFILE)
