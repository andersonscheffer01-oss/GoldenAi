from __future__ import annotations

import builtins
import hashlib
import runpy
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.computer import (  # noqa: E402
    find_installed_app,
    get_current_datetime,
    get_disk_usage,
    get_mt5_status,
    get_system_info,
    launch_allowed_app,
    list_mt5_eas,
    list_mt5_terminals,
    list_processes,
    open_folder,
)
from core.permissions import PermissionManager  # noqa: E402


MQ5_FILES = [
    ROOT / "projetos" / "robo_teste.mq5",
    ROOT / "projetos" / "Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_motor_globals():
    original_input = builtins.input
    builtins.input = lambda prompt="": "sair"
    try:
        return runpy.run_path(str(ROOT / "app" / "golden_ai.py"))
    finally:
        builtins.input = original_input


class ComputerToolsTests(unittest.TestCase):
    def audit_text(self) -> str:
        path = ROOT / "logs" / f"audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_datetime_returns_real_local_fields(self):
        info = get_current_datetime()
        self.assertRegex(info["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(info["time"], r"^\d{2}:\d{2}:\d{2}$")
        self.assertTrue(info["weekday"])
        self.assertTrue(info["iso_timestamp"])

    def test_system_info_has_safe_ram_and_cpu_fields(self):
        info = get_system_info()
        self.assertIn("windows_version", info)
        self.assertIn("cpu_model", info)
        self.assertGreaterEqual(info["logical_cpus"], 1)
        self.assertIn("ram_total_bytes", info)
        self.assertIn("ram_available_bytes", info)

    def test_disk_usage_allowed_for_goldenai(self):
        info = get_disk_usage(r"C:\GoldenAI")
        self.assertTrue(info["ok"])
        self.assertGreater(info["total_bytes"], 0)
        self.assertGreaterEqual(info["free_bytes"], 0)

    def test_disk_usage_blocks_personal_documents(self):
        info = get_disk_usage(str(Path.home() / "Documents"))
        self.assertFalse(info["ok"])
        self.assertIn("blocks", info["error"].lower())

    def test_process_list_has_no_command_line(self):
        rows = list_processes("", limit=10)
        self.assertIsInstance(rows, list)
        if rows:
            self.assertIn("name", rows[0])
            self.assertIn("pid", rows[0])
            self.assertNotIn("command_line", rows[0])

    def test_find_installed_app_does_not_execute(self):
        info = find_installed_app("notepad")
        self.assertIn("found", info)
        self.assertEqual(info["name"], "notepad")

    def test_launch_non_allowlisted_app_is_blocked(self):
        info = launch_allowed_app("cmd.exe")
        self.assertFalse(info["ok"])
        self.assertIn("not allowlisted", info["error"])

    def test_open_folder_blocks_system32(self):
        info = open_folder(r"C:\Windows\System32")
        self.assertFalse(info["ok"])
        self.assertIn("not allowlisted", info["error"])

    def test_permission_manager_blocks_general_external_read(self):
        manager = PermissionManager()
        decision = manager.can_read_external_safe("mt5_read", Path.home() / "Documents")
        self.assertFalse(decision.allowed)

    def test_mt5_read_tools_do_not_modify_mq5_files(self):
        before = {str(path): sha256(path) for path in MQ5_FILES if path.exists()}
        get_mt5_status()
        list_mt5_terminals()
        list_mt5_eas()
        after = {str(path): sha256(path) for path in MQ5_FILES if path.exists()}
        self.assertEqual(before, after)

    def test_motor_registry_audits_datetime_tool(self):
        motor = load_motor_globals()
        result = motor["executar_tool_core"]("get_current_datetime", {})
        self.assertIsInstance(result, dict)
        text = self.audit_text()
        self.assertIn("get_current_datetime", text)
        self.assertIn("TOOL_COMPLETED", text)

    def test_motor_blocks_non_allowlisted_execute_tool(self):
        motor = load_motor_globals()
        result = motor["executar_tool_core"]("launch_allowed_app", {"name": "cmd.exe"})
        self.assertIn("not allowlisted", str(result))
        self.assertIn("TOOL_DENIED", self.audit_text())


if __name__ == "__main__":
    unittest.main()
