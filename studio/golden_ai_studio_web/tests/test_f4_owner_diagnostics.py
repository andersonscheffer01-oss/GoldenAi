from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jarvis_core.audit import AuditLog
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.lifecycle import CoreLifecycle
from jarvis_core.security import SecurityManager


OWNER_PID = 54321
OWNER_ID = {"pid": OWNER_PID, "created_at": 1234.5}


def _lifecycle(tmp_path, identity_results, current_parent):
    identity = patch("jarvis_core.lifecycle._process_identity",
                     side_effect=identity_results)
    identity.start()
    parent = patch("jarvis_core.lifecycle.os.getppid", return_value=current_parent)
    parent.start()
    lifecycle = CoreLifecycle(
        runtime_profile="web-ai-safe",
        auth_manager=AuthManager(_token="owner-test"),
        security_manager=SecurityManager(),
        audit_log=AuditLog(tmp_path / "audit.db"),
        pid=9876,
        parent_pid=OWNER_PID,
    )
    return lifecycle, identity, parent


def test_live_matching_launcher_is_reported_attached(tmp_path):
    lifecycle, identity, parent = _lifecycle(tmp_path, [OWNER_ID, OWNER_ID], OWNER_PID)
    try:
        owner = lifecycle.snapshot()["owner"]
        assert owner["state"] == "LAUNCHER_ATTACHED"
        assert owner["launcher_created_at"] == OWNER_ID["created_at"]
    finally:
        identity.stop()
        parent.stop()


def test_live_launcher_outside_parent_chain_is_distinguished(tmp_path):
    lifecycle, identity, parent = _lifecycle(
        tmp_path, [OWNER_ID, OWNER_ID], current_parent=77777
    )
    try:
        assert lifecycle.snapshot()["owner"]["state"] == "LAUNCHER_ALIVE_NOT_PARENT"
    finally:
        identity.stop()
        parent.stop()


def test_dead_launcher_leaves_core_running_and_reports_orphaned(tmp_path):
    lifecycle, identity, parent = _lifecycle(tmp_path, [OWNER_ID, None], OWNER_PID)
    try:
        snapshot = lifecycle.snapshot()
        assert snapshot["owner"]["state"] == "ORPHANED"
        assert snapshot["lifecycle_state"] == "RUNNING"
        assert snapshot["pid"] == 9876
    finally:
        identity.stop()
        parent.stop()


def test_reused_launcher_pid_is_not_mistaken_for_original_owner(tmp_path):
    replacement = {"pid": OWNER_PID, "created_at": 9876.5}
    lifecycle, identity, parent = _lifecycle(
        tmp_path, [OWNER_ID, replacement], OWNER_PID
    )
    try:
        assert lifecycle.snapshot()["owner"]["state"] == "ORPHANED"
    finally:
        identity.stop()
        parent.stop()


def test_unverifiable_launcher_identity_reports_unknown(tmp_path):
    unknown = {"pid": OWNER_PID, "created_at": None}
    lifecycle, identity, parent = _lifecycle(tmp_path, [unknown, unknown], OWNER_PID)
    try:
        assert lifecycle.snapshot()["owner"]["state"] == "UNKNOWN"
    finally:
        identity.stop()
        parent.stop()
