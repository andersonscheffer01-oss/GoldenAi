from pathlib import Path


ROOT = Path(__file__).parents[1]
UI = ROOT / "jarvis_ui"
DESKTOP = ROOT / "jarvis_desktop"


def test_desktop_shell_lazy_loads_experience_only_for_native_identity():
    source = (UI / "src" / "desktop-shell.js").read_text(encoding="utf-8")
    assert 'window.__JARVIS_DESKTOP__ === true' in source
    assert 'import("./desktop-jarvis-experience.js?v=20261107-gemini-provider-lock-1")' in source
    assert "mountDesktopJarvisExperience" in source


def test_experience_is_scoped_to_jarvis_conversation_and_reuses_existing_widgets():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    stylesheet = (UI / "src" / "desktop-jarvis-experience.css").read_text(encoding="utf-8")
    assert 'document.querySelector(\'[data-view="conversa"]\')' in source
    assert '.gTaskPanel' in source and '.gChatCard' in source and '.gCmdCard' in source
    assert 'window.Gateway.httpPost' in source
    assert '/api/jarvis/voice-service/profile' in source
    assert '/api/jarvis/voice-service/gemini/connect' in source
    assert '/api/jarvis/voice-service/gemini/authorize' in source
    assert '/api/jarvis/voice-service/gemini/disconnect' in source
    assert '/api/jarvis/voice-service/microphone/probe' in source
    assert '/api/jarvis/tasks/cancel' in source
    assert '/api/jarvis/approvals/list' in source
    assert '#app[data-desktop-shell="1"]' in stylesheet
    assert "MT5" not in source


def test_panel_renders_read_only_multi_agent_council():
    source = (UI / "src" / "desktop-shell.js").read_text(encoding="utf-8")
    assert "function renderPanelMultiAgent(report)" in source
    assert "Conselho Multiagente de Mercado" in source
    assert "renderPanelMultiAgent(result.multi_agent)" in source
    assert "Nenhum agente possui autoridade" in source


def test_experience_targets_the_view_container_not_navigation_button():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "document.querySelector('.gView[data-view=\"conversa\"]')" in source


def test_reference_conversation_sidebar_contains_only_persisted_archived_history():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "function loadReferenceConversations" in source
    assert "function saveReferenceConversations" in source
    assert "function archiveReferenceConversation" in source
    assert "Nenhuma conversa anterior" in source
    assert "const defaultConversations" not in source
    assert 'state.referenceConversations = [fresh' not in source
    assert 'window.addEventListener("beforeunload", () => archiveReferenceConversation(state))' in source


def test_settings_gateway_post_preserves_authenticated_gateway_context():
    source = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "gateway.httpPost.bind(gateway)" in source


def test_chat_route_executes_explicit_mcp_requests_before_brain_planning():
    source = (ROOT / "server_agent.py").read_text(encoding="utf-8")
    parse = source.index("explicit_intent = jarvis._parse(text)")
    brain = source.index("brain = get_brain(jarvis.registry)")
    assert parse < brain
    assert 'str(explicit_intent[0]).startswith("mcp:")' in source
    assert '"model": "mcp-direct"' in source


def test_desktop_shell_still_uses_canonical_ui_without_public_web_query():
    settings = (DESKTOP / "settings.py").read_text(encoding="utf-8")
    window = (DESKTOP / "web_window.py").read_text(encoding="utf-8")
    assert 'return origin.rstrip("/") + "/jarvis_ui/jarvis.html"' in settings
    assert 'target = ui_url(self.core_origin)' in window
    assert 'jarvis_ui/jarvis.html?surface=desktop' not in settings


def test_public_html_is_not_modified_by_desktop_experience_loader():
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    assert "desktop-jarvis-experience.js" not in html
    assert "desktop-jarvis-experience.css" not in html


def test_voice_and_microphone_states_are_truthful_and_separated():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "VOICE_DISABLED_BY_PROFILE" in source
    assert "GEMINI LIVE · AGUARDANDO" in source
    assert "function microphoneState" in source
    assert "PERMISSION DENIED" in source
    assert "SELECTED · MISSING" in source
    assert "AUTHORIZATION REQUIRED" in source
    assert "não é uma falha de hardware" in source
    assert "voice?.microphone?.selected_id" in source


def test_gemini_authorization_is_forwarded_to_microphone_controls():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "voiceAuthorizationPayload(state" in source
    assert "microphone/select" in source and "microphone/probe" in source
    assert "microphone/calibrate" in source


def test_repeated_voice_errors_are_throttled():
    source = (UI / "src" / "desktop-voice.js").read_text(encoding="utf-8")
    assert "lastErrorKey" in source and "lastErrorAt" in source
    assert "5000" in source


def test_gemini_mode_is_explicit_and_not_hidden_inside_local_voice_test():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert 'data-dj-voice-test' in source
    assert 'state.settings.voiceMode === "gemini_live"' in source
    assert 'pronto para conectar' in source
    assert 'authorization_token' in source


def test_gemini_start_requests_scoped_authorization_before_connecting():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    start = source.index('/api/jarvis/voice-service/gemini/authorize')
    connect = source.index('/api/jarvis/voice-service/gemini/connect')
    assert start < connect
    assert '{ confirm: true }' in source
    assert '/api/jarvis/voice-service/gemini/audio/start' in source
    assert '/api/jarvis/voice-service/gemini/audio/stop' in source


def test_setup_diagnostic_is_explicit_and_precedes_no_audio_path():
    source = (ROOT / "jarvis_ui" / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "data-dj-gemini-setup" in source
    assert "/api/jarvis/voice-service/gemini/setup-diagnostic" in source
    setup = source.index("/api/jarvis/voice-service/gemini/setup-diagnostic")
    start_handler = source.index('$("[data-dj-gemini-start]", surface)')
    audio = source.index("/api/jarvis/voice-service/gemini/audio/start", start_handler)
    assert setup < audio


def test_setup_diagnostic_surfaces_only_sanitized_runtime_metadata():
    source = (ROOT / "jarvis_ui" / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "function setupDiagnosticSummary" in source
    for field in ("last_error_class", "last_error_category", "remote_close_reason",
                  "google_genai_version", "api_version", "runtime_instance_id",
                  "correlation_id", "credential?.resolution"):
        assert field in source
    assert "local-test-secret" not in source


def test_gemini_start_surfaces_authorization_connection_and_audio_errors():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "Gemini Live não iniciado" in source
    assert "GEMINI_LIVE_CONNECT_FAILED" in source
    assert "GEMINI_LIVE_AUDIO_START_FAILED" in source
    assert "VOICE_AUTHORIZATION_REQUIRED" in source


def test_gemini_preview_does_not_report_a_duplicate_request_as_a_connection_failure():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "state.geminiAudio?.preview_active === true" in source
    assert "Prévia Gemini já está em andamento; use PARAR TESTE para interromper." in source
    assert "previewButton.disabled = previewActive" in source


def test_failed_gemini_handshake_is_not_displayed_as_missing_authorization():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "state.geminiFailure" in source
    assert "GEMINI LIVE · ERRO" in source
    assert 'data?.gemini_authorization === "NOT_AUTHORIZED"' in source


def test_image_capability_does_not_simulate_generation():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert '/api/jarvis/vision/status' in source
    assert "GERAÇÃO INDISPONÍVEL" in source
    assert "nenhum sucesso é simulado" in source


def test_core_state_and_hidden_thinking_are_scoped_to_desktop_view():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    stylesheet = (UI / "src" / "desktop-jarvis-experience.css").read_text(encoding="utf-8")
    assert "function syncCoreState" in source
    assert "data-state" in source
    assert '.djThinkingSlot #thinkingBar[hidden]' in stylesheet
    assert 'data-state="warn"' in stylesheet


def test_personality_is_applied_through_voice_only_presentation_seam():
    voice = (ROOT / "jarvis_core" / "voice_service.py").read_text(encoding="utf-8")
    brain = (ROOT / "jarvis_core" / "brain.py").read_text(encoding="utf-8")
    assert "_apply_personality_to_brain" in voice
    assert "_voice_style_instruction" in brain
    assert "Nunca altere ferramentas, permissões" in brain


def test_gemini_preview_reports_received_audio_and_output_failures():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "audio?.audio?.output" in source
    assert "Áudio Gemini recebido e em reprodução" in source
    assert "Saída Gemini falhou" in source


def test_gemini_voice_change_is_validated_and_deferred_when_session_is_active():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    for voice in ("Zephyr", "Charon", "Kore", "Sadachbia", "Sadaltager", "Sulafat"):
        assert f'"{voice}"' in source
    assert "GEMINI_VOICE_UNSUPPORTED" in source
    assert "voice_change_requires_reconnect" in source
    assert "/api/jarvis/voice-service/gemini/reconnect" in source
    assert "Voz e personalidade aplicadas à sessão Gemini Live." in source


def test_gemini_audio_toggle_reuses_the_canonical_voice_service_owner():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "function toggleGeminiAudio" in source
    assert "__JARVIS_GEMINI_AUDIO_TOGGLE__" in source
    assert "/api/jarvis/voice-service/gemini/audio/start" in source
    assert "/api/jarvis/voice-service/gemini/audio/stop" in source
    assert "/api/jarvis/voice-service/gemini/audio/capture/start" in source
    assert "/api/jarvis/voice-service/gemini/audio/capture/stop" in source
    assert "GEMINI_AUDIO_TOGGLE_IN_PROGRESS" in source
    assert "publishGeminiAudioState" in source
    assert "function interruptGeminiAudio" in source
    assert "__JARVIS_GEMINI_AUDIO_INTERRUPT__" in source
    assert "/api/jarvis/voice-service/gemini/audio/interrupt" in source
    assert "Turno encerrado — aguardando resposta Gemini" in source
    assert "__JARVIS_SUPPRESS_GEMINI_TRANSCRIPT_UNTIL__ = 0" in source


def test_gemini_ptt_distinguishes_microphone_capture_from_output_bridge():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "const active = state?.geminiAudio?.capture_active === true" in source
    assert "const currentlyActive = state.geminiAudio?.capture_active === true" in source
    assert "result?.audio?.capture_active === true" in app
    assert "__JARVIS_GEMINI_AUDIO_INTERRUPT__" in app


def test_gemini_start_publishes_live_mode_before_audio_toggle():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    start = source.index('$("[data-dj-gemini-start]", surface)')
    assert 'window.__JARVIS_DESKTOP_VOICE_MODE__ = "gemini_live"' in source[start:]
    assert 'modeSelect.value = "gemini_live"' in source
    assert "/api/jarvis/voice-service/gemini/renew" in source


def test_desktop_gemini_connects_automatically_when_live_mode_is_selected():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert 'voiceMode: "gemini_live"' in source
    assert "function autoConnectGeminiLive" in source
    assert "_autoConnectAttempted" in source
    assert 'start.click()' in source


def test_desktop_voice_surface_never_exposes_local_tts_as_a_mode():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    assert '<option value="local">' not in source
    assert 'TESTAR VOZ LOCAL' not in source
    assert '<option value="local">Local (Golden)</option>' not in html
    assert 'TESTAR VOZ LOCAL' not in html
    assert 'LOCAL · ENABLED' not in app
    assert 'voiceMode: "gemini_live"' in app
    assert 'settings.voiceMode = "gemini_live"' in app


def test_desktop_voice_and_microphone_controls_are_centralized_in_settings():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    stylesheet = (UI / "src" / "desktop-jarvis-experience.css").read_text(encoding="utf-8")
    assert 'surface.classList.add("djSettingsCentralized")' in source
    assert 'rail.hidden = true' in source
    assert "djSettingsCentralized .djExperienceGrid" in stylesheet
    assert 'id="settingsGeminiStartBtn"' in html
    assert 'id="settingsGeminiStopBtn"' in html
    assert 'id="settingsGeminiSetupBtn"' in html


def test_explicit_profile_changes_can_refresh_an_expired_voice_grant():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    assert "options.authorize" in source
    assert 'configureProfile(surface, state, { voice: requestedVoice }, { authorize: true })' in source
    assert 'configureProfile(surface, state, { personality: requestedPersona }, { authorize: true })' in source
    assert "voiceAuthorizationPayload(state, payload)" in source


def test_typed_gemini_turn_uses_the_same_authorized_audio_session():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "/api/jarvis/voice-service/gemini/text" in source
    assert "__JARVIS_GEMINI_SEND_TEXT__" in source
    assert "texto enviado ao Gemini Live" in app
    assert "could execute a tool outside the Live conversation" in app
    assert 'renderResponse({ reply: out.text, typing: false, speak: false })' in app


def test_processing_indicator_is_response_scoped_and_research_bypasses_live_tools():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert 'function showThinking(label = "pensando…")' in app
    assert "function hideThinking()" in app
    assert 'if (appState === "thinking" || appState === "executing") showThinking();' in app
    assert 'else hideThinking();' in app
    assert 'showThinking("pensando…")' in app
    assert 'thinkingBar.hidden = false' in app
    assert 'thinkingBar.hidden = true' in app
    assert "function isResearchRequest(text)" in app
    assert "async function speakDesktopGeminiReply(text)" in app
    assert "Leia em português brasileiro" in app
    assert "&& !isResearchRequest(text)" in app
    assert "pesquis" in app and "cotac" in app and "internet" in app


def test_gemini_live_routes_computer_and_image_requests_to_the_canonical_gateway():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "function isComputerUseRequest(text)" in app
    assert "function isImageRequest(text)" in app
    assert "&& !isComputerUseRequest(text)" in app
    assert "&& !isImageRequest(text)" in app
    assert "isResearchRequest(input) || isComputerUseRequest(input) || isImageRequest(input)" in app
    assert 'submitCommand(input, "voz", { skipUserEcho: true })' in app
    assert "__JARVIS_GEMINI_AUDIO_INTERRUPT__" in app
    assert "SecurityManager confirmations" in app


def test_gemini_live_routes_xauusd_analysis_to_the_read_only_gateway():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "function isMarketAnalysisRequest(text)" in app
    assert "function isNegatedMarketAnalysisRequest(text)" in app
    assert "function compactMarketGatewayReply(request)" in app
    assert "A análise que você pediu foi concluída" in app
    assert "ouro|gold|xauusd" in app
    assert "entrada|entry|setup|stop|take|alvo" in app
    assert "&& !isMarketAnalysisRequest(text)" in app
    assert "|| isMarketAnalysisRequest(label)" in app


def test_mcp_status_never_uses_gemini_live_text_endpoint():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    assert "function isExternalMcpRequest(text)" in app
    assert r"/\bmcps?\b/" in app
    assert "function isMcpStatusRequest(text)" in app
    assert "async function handleMcpStatusRequest()" in app
    assert '"/api/jarvis/extensions/status"' in app
    assert "await handleMcpStatusRequest();" in app
    assert "await speakDesktopGeminiReply(reply);" in app
    assert "&& !isExternalMcpRequest(text)" in app
    assert "GEMINI_LIVE_TEXT_FAILED" in app
    assert "finally {\n    hideThinking();\n    setState(\"idle\");\n  }" in app


def test_live_voice_actions_interrupt_tool_free_session_before_gateway_dispatch():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    start = app.index("const gatewayVoiceRequest")
    end = app.index('if (Number(window.__JARVIS_SUPPRESS_GEMINI_TRANSCRIPT_UNTIL__', start)
    branch = app[start:end]
    assert "Date.now() + 15000" in branch
    assert "interrupt" in branch
    assert "isMarketAnalysisRequest(input)" in branch
    assert "isExternalMcpRequest(input)" in branch
    assert "finally" in branch and 'submitCommand(input, "voz", { skipUserEcho: true })' in branch


def test_typed_gemini_turn_always_clears_processing_state():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    start = app.index("__JARVIS_GEMINI_SEND_TEXT__")
    end = app.index("// Local-only actions", start)
    branch = app[start:end]
    assert "try {" in branch and "finally" in branch
    assert "waitForGeminiTurn();" in branch
    assert "if (!awaitingAnswer) finishGeminiTurn();" in branch
    assert "if (output) finishGeminiTurn();" in app


def test_thinking_indicator_has_a_safe_default_label_and_no_stuck_legacy_text():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    assert 'label = "pensando…"' in app
    assert 'id="thinkingText">pensando…</span>' in html
    assert 'thinkingText.textContent = "processando"' not in app


def test_gemini_connect_keeps_output_bridge_when_push_to_talk_is_muted():
    source = (UI / "src" / "desktop-jarvis-experience.js").read_text(encoding="utf-8")
    start = source.index("const audio = await post(\"/api/jarvis/voice-service/gemini/audio/start\"")
    assert "capture: false" in source[start:source.index("if (!audio?.ok)", start)]


def test_push_to_talk_button_has_explicit_muted_and_active_states():
    app = (UI / "src" / "app.js").read_text(encoding="utf-8")
    styles = (UI / "src" / "styles.css").read_text(encoding="utf-8")
    html = (UI / "jarvis.html").read_text(encoding="utf-8")
    assert "setMicButtonState" in app
    assert "ptt-active" in app and "ptt-muted" in app
    assert "jarvis:gemini-audio-state" in app
    assert "#micBtn.ptt-active" in styles and "#micBtn.ptt-muted" in styles
    assert 'aria-pressed="false"' in html and 'data-ptt="off"' in html
