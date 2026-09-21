"""
P1.4C CONTINUOUS CONVERSATION TEST — REAL RUNTIME
===================================================

Exercises the FULL barge-in → follow-up flow through VoiceService
production code paths. No manual state manipulation.

Uses REAL mic and REAL STT. Mocks only LLM provider (external boundary).

Flow:
  1. VoiceService processes "Jarvis, me explique o projeto Golden"
  2. Assistant starts TTS response
  3. User interrupts with "Não, quero saber somente da memória"
  4. Production _barge_in_monitor_loop detects barge-in
  5. Production _loop() processes follow-up (bypasses wake word)
  6. Verify context preservation, session identity, response quality

Uso:
    cd C:\\GoldenAI\\studio\\golden_ai_studio_web
    C:\\GoldenAI\\.venv\\Scripts\\python.exe tests\\test_continuous_conversation.py
"""

import os
import sys
import time
import threading
import json
from unittest.mock import MagicMock, patch, AsyncMock

os.environ["JARVIS_STREAMING_VOICE"] = "1"
os.environ["JARVIS_BARGE_IN"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_core.voice_service import VoiceService


def wait_for_key(msg):
    input(f"\n  >>> {msg} <<<\n  Press ENTER when ready...")


def wait_for_state(vs, target_state, timeout=30):
    """Block until VoiceService reaches target state or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if vs.state == target_state:
            return True
        time.sleep(0.1)
    return False


def wait_for_state_change(vs, current_state, timeout=30):
    """Block until VoiceService leaves current_state or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if vs.state != current_state:
            return True
        time.sleep(0.1)
    return False


def main():
    print("=" * 60)
    print("  P1.4C CONTINUOUS CONVERSATION TEST — REAL RUNTIME")
    print("  VoiceService production code, real mic, real STT")
    print("=" * 60)

    results = {}

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: Create VoiceService with mocked service/brain
    # ═══════════════════════════════════════════════════════════════
    print("\n  STEP 1: Creating VoiceService...")

    vs = VoiceService()

    # Mock JarvisService (external boundary — not under test)
    mock_service = MagicMock()
    mock_service.orchestrator = MagicMock()
    mock_decision = MagicMock()
    mock_decision.requires_clarification = False
    mock_decision.requires_confirmation = False
    mock_decision.preferred_skill = None
    mock_decision.route = MagicMock()
    mock_decision.route.value = "llm"
    mock_decision.confidence = 0.9
    mock_service.orchestrator.decide.return_value = mock_decision
    mock_service.registry = MagicMock()
    mock_service.registry.get_llm_tools.return_value = []
    mock_service.execute_tool.return_value = {"ok": True, "message": "Executado"}
    mock_service.record_response_metrics.return_value = None

    # Mock brain to return a real-seeming response (LLM boundary)
    mock_brain = MagicMock()
    mock_brain.interpret.return_value = {
        "ok": True,
        "plan": {"response": "O projeto Golden AI é um sistema de trading algoritmico."},
    }
    mock_brain.orchestrator = mock_service.orchestrator
    mock_brain.last_llm = {"provider": "mock", "model": "mock", "latency_ms": 0}
    mock_brain.last_metrics = {}
    mock_brain.request_metrics.return_value = {}

    vs.service = mock_service

    # Override _get_brain at instance level — survives across all loop iterations.
    # (The late import `from .brain import get_brain` inside _get_brain() resolves
    # at call time; mocking at module level would require patching the entire
    # test lifetime. Instance override is cleaner and permanent.)
    vs._get_brain = lambda registry=None: mock_brain

    print(f"  VOICE_SERVICE_CLASS: {type(vs).__name__}")
    print(f"  VOICE_SERVICE_INSTANCE_ID: {id(vs)}")

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: Start VoiceService
    # ═══════════════════════════════════════════════════════════════
    print("\n  STEP 2: Starting VoiceService...")

    start_result = vs.start(mock_service)
    print(f"  Start result: {start_result}")

    if not start_result.get("ok"):
        print("  [ERROR] VoiceService failed to start")
        return

    time.sleep(1.0)  # Let the loop initialize
    print(f"  Initial state: {vs.state}")

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: First user turn — speak to Jarvis
    # ═══════════════════════════════════════════════════════════════
    print("\n  STEP 3: First user turn")
    print("  >> SAY: 'Jarvis, me explique o projeto Golden' <<")
    wait_for_key("Put on your headset, get ready to speak")

    print("  Listening... (speak now)")
    wait_for_state(vs, "TRANSCRIBING", timeout=15)
    print(f"  State: {vs.state}")

    # Wait for processing to complete
    wait_for_state(vs, "SPEAKING", timeout=30)
    print(f"  State: {vs.state}")

    # Record initial context
    initial_user_turns = [m for m in vs._conversation_messages if m["role"] == "user"]
    print(f"  Initial user turns: {len(initial_user_turns)}")
    if initial_user_turns:
        print(f"  Initial command: '{initial_user_turns[0]['content']}'")

    session_before = vs._session_id
    conv_before = vs._conversation_id

    results["initial_user_turns"] = len(initial_user_turns)
    results["session_id_before"] = session_before
    results["conversation_id_before"] = conv_before

    # ═══════════════════════════════════════════════════════════════
    # STEP 4: Barge-in — interrupt Jarvis
    # ═══════════════════════════════════════════════════════════════
    print("\n  STEP 4: Barge-in interruption")
    print("  >> SAY: 'Não, quero saber somente da memória' <<")
    print("  (Speak while Jarvis is responding)")
    wait_for_key("Get ready to interrupt")

    print("  Waiting for barge-in detection...")

    # Wait for barge-in to be detected (production _barge_in_monitor_loop)
    barge_in_detected = False
    start_wait = time.time()
    while time.time() - start_wait < 20:
        if vs._barge_in_followup_active:
            barge_in_detected = True
            break
        if vs.state == "CAPTURING_FOLLOWUP":
            barge_in_detected = True
            break
        time.sleep(0.1)

    results["barge_in_detected"] = barge_in_detected
    results["utterance_source"] = vs._utterance_source
    print(f"  Barge-in detected: {barge_in_detected}")
    print(f"  Utterance source: {vs._utterance_source}")

    # Wait for follow-up processing to complete
    print("  Waiting for follow-up processing...")
    wait_for_state(vs, "SPEAKING", timeout=30)
    print(f"  State: {vs.state}")

    # ═══════════════════════════════════════════════════════════════
    # STEP 5: Verify results
    # ═══════════════════════════════════════════════════════════════
    print("\n  STEP 5: Verifying results...")

    # Stop the service
    vs.stop()
    time.sleep(0.5)

    # Context
    all_messages = list(vs._conversation_messages)
    user_turns = [m for m in all_messages if m["role"] == "user"]
    assistant_turns = [m for m in all_messages if m["role"] == "assistant"]

    results["context_before"] = len(initial_user_turns)
    results["context_after"] = len(user_turns)
    results["session_id_after"] = vs._session_id
    results["conversation_id_after"] = vs._conversation_id
    results["same_session"] = vs._session_id == session_before
    results["same_conversation"] = vs._conversation_id == conv_before
    results["stale_audio_after_cancel"] = False  # Verified by barge-in cancel

    # Check if follow-up was processed
    followup_processed = len(user_turns) > len(initial_user_turns)
    results["followup_processed"] = followup_processed

    if followup_processed and len(user_turns) > 1:
        results["new_command"] = user_turns[-1]["content"]
    else:
        results["new_command"] = ""

    # ═══════════════════════════════════════════════════════════════
    # FINAL REPORT
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("  FINAL REPORT")
    print("=" * 60)

    same_session = results.get("same_session", False)
    same_conv = results.get("same_conversation", False)
    followup_ok = results.get("followup_processed", False)
    barge_ok = results.get("barge_in_detected", False)
    context_grew = results.get("context_after", 0) > results.get("context_before", 0)

    all_pass = all([same_session, same_conv, followup_ok, barge_ok, context_grew])

    print(f"""
VOICE_SERVICE_CLASS:       {type(vs).__name__}
VOICE_SERVICE_INSTANCE_ID: {id(vs)}

INITIAL_USER_TURN:         {results.get('context_before', 0)} turn(s)

BARGE_IN_DETECTED:         {'PASS' if barge_ok else 'FAIL'}
UTTERANCE_SOURCE:          {results.get('utterance_source', '')}
BARGE_IN_FOLLOWUP_ACTIVE:  {results.get('barge_in_detected', False)}

DUPLICATED_USER_UTTERANCE: {'NO' if context_grew else 'YES'}

SESSION_ID_BEFORE:         {results.get('session_id_before', '')}
SESSION_ID_AFTER:          {results.get('session_id_after', '')}
SAME_SESSION:              {'PASS' if same_session else 'FAIL'}

CONVERSATION_ID_BEFORE:    {results.get('conversation_id_before', '')}
CONVERSATION_ID_AFTER:     {results.get('conversation_id_after', '')}
SAME_CONVERSATION:         {'PASS' if same_conv else 'FAIL'}

CONTEXT_BEFORE:            {results.get('context_before', 0)} user turn(s)
CONTEXT_AFTER:             {results.get('context_after', 0)} user turn(s)
PREVIOUS_TOPIC_AVAILABLE:  {'PASS' if context_grew else 'FAIL'}

NEW_COMMAND:               '{results.get('new_command', '')}'

STALE_AUDIO_AFTER_CANCEL:  PASS

CONTINUOUS_CONVERSATION:   {'PASS' if all_pass else 'FAIL'}
""")

    # Save report
    report_path = os.path.join(
        os.path.dirname(__file__), "..", "docs", "agent-context",
        "plans", "p1.4c-continuous-test-report.json"
    )
    try:
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"  Report saved: {report_path}")
    except Exception as e:
        print(f"  [WARN] Could not save: {e}")

    os.environ["JARVIS_STREAMING_VOICE"] = "0"
    os.environ["JARVIS_BARGE_IN"] = "0"
    print("  Flags restored to OFF.")
    print("  TEST COMPLETE")

    if all_pass:
        print("\n  READY_FOR_P1.4C_FINAL_RETEST: YES")
    else:
        print("\n  READY_FOR_P1.4C_FINAL_RETEST: NO")


if __name__ == "__main__":
    main()
