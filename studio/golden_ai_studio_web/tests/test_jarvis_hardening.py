import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_core.audit import AuditLog
from jarvis_core.brain import JarvisBrain
from jarvis_core.cancellation import CancellationToken
from jarvis_core.models import Risk
from jarvis_core.service import JarvisService
from jarvis_core.vision import JarvisVision

class JarvisCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = JarvisService(self.temp.name)
        self.registry = self.service.registry
        self.brain = JarvisBrain(self.registry)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    MANDATORY_TOOLS = ("open_program", "close_program", "get_time", "delete_file",
                       "kill_process", "recycle_bin_status", "empty_recycle_bin",
                       "list_processes", "memory_search", "take_screenshot")

    def test_registry_has_unique_valid_tools(self):
        catalog = self.registry.public_catalog()
        self.assertTrue(catalog)
        names = {x["name"] for x in catalog}
        self.assertEqual(len(catalog), len(names))
        for name in self.MANDATORY_TOOLS:
            with self.subTest(name=name):
                self.assertIn(name, names)
        self.assertEqual([], self.registry.validate())

    def test_llm_tools_come_from_registry(self):
        catalog = {x["name"]: x for x in self.registry.public_catalog()}
        tools = self.registry.get_llm_tools()
        llm_names = {x["name"] for x in tools}
        self.assertEqual(llm_names, {n for n, meta in catalog.items() if meta["llm_enabled"]})
        self.assertNotIn("open_any_exe", llm_names)
        self.assertFalse(catalog["open_any_exe"]["llm_enabled"])
        self.assertEqual(len(tools), self.brain.status()["tools_from_registry"])

    def test_parser_valid_and_markdown_json(self):
        fence = chr(96) * 3
        samples = ('{"tool":"get_time","args":{}}',
                   fence + 'json\n{"tool":"get_time","args":{}}\n' + fence)
        for raw in samples:
            parsed = self.brain._parse_llm_response(raw)
            self.assertTrue(parsed["ok"])
            self.assertEqual("get_time", parsed["plan"]["tool"])

    def test_parser_fails_closed(self):
        invalid = ["texto comum", '{"tool":"get_time"',
            '{"tool":"formatar_computador","args":{}}',
            '{"tool":"powershell","args":{"command":"x"}}',
            '{"tool":"delete_everything","args":{}}',
            '{"tool":"open_program","args":{}}',
            '{"tool":"volume_set","args":{"level":"alto"}}',
            '{"tool":"get_time","args":{"command":"x"}}']
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assertFalse(self.brain._parse_llm_response(raw)["ok"])

    def test_service_rejects_unknown_tool_and_arguments(self):
        self.assertFalse(self.service.execute_tool("delete_everything", {})["ok"])
        self.assertFalse(self.service.execute_tool("open_program", {})["ok"])
        self.assertFalse(self.service.execute_tool("get_time", {"command": "x"})["ok"])

    @patch("jarvis_core.service.Path.is_file", return_value=True)
    @patch("jarvis_core.service.Path.exists", return_value=True)
    def test_open_any_exe_classification_and_shell_block(self, _exists, _file):
        tool = self.registry.get("open_any_exe")
        for path in (r"C:\Windows\System32\cmd.exe", r"C:\Windows\System32\powershell.exe",
                     r"C:\x\pwsh.exe", r"C:\x\wscript.exe", r"C:\x\cscript.exe"):
            self.assertIsNotNone(self.service._prepare_execution(tool, {"path": path})[3])
        unknown = self.service._prepare_execution(tool, {"path": r"C:\Other\app.exe"})
        self.assertEqual(Risk.HIGH, unknown[1])
        self.assertTrue(unknown[2])
        download = self.service._prepare_execution(
            tool, {"path": str(Path.home() / "Downloads" / "app.exe")})
        self.assertEqual(Risk.CRITICAL, download[1])
        program_files = self.service._prepare_execution(
            tool, {"path": r"C:\Program Files\Vendor\app.exe"})
        self.assertEqual(Risk.MEDIUM, program_files[1])
        self.assertTrue(program_files[2])

    def test_confirmation_single_use_and_bound_arguments(self):
        self.service.dry_run = True
        approved = str((Path(self.temp.name) / "a.txt").resolve())
        first = self.service.execute_tool("delete_file", {"path": approved})
        self.assertTrue(first["confirmation_required"])
        pending = self.service.security.pending[first["token"]]
        self.assertEqual("delete_file", pending["tool"])
        self.assertEqual(approved, pending["arguments"]["path"])
        self.assertTrue(self.service.confirm(first["token"])["ok"])
        self.assertFalse(self.service.confirm(first["token"])["ok"])

    def test_confirmation_expiry(self):
        tool = self.registry.get("delete_file")
        token = self.service.security.create_confirmation(tool, {"path": "a"}, "delete")
        self.service.security.pending[token]["expires"] = time.time() - 1
        self.assertIsNone(self.service.security.consume(token))

    def test_kill_process_is_high_and_protected(self):
        tool = self.registry.get("kill_process")
        self.assertEqual(Risk.HIGH, tool.risk)
        self.assertTrue(tool.confirmation)
        result = self.service.execute_tool("kill_process", {"name": "lsass.exe"})
        self.assertFalse(result["ok"])
        self.assertIn("protegido", result["error"])

    def test_audit_redacts_nested_secrets_and_large_payload(self):
        audit = AuditLog(Path(self.temp.name) / "audit.db")
        audit.add(arguments={"password": "123", "auth": {"token": "abc"},
                             "items": [{"api_key": "xyz"}],
                             "image_base64": "A" * 10000},
                  result={"authorization": "Bearer test"},
                  command="conectar token=segredo", status="test")
        row = audit.recent(1)[0]
        serialized = row["arguments"] + row["result"]
        serialized += row["command"]
        for secret in ("123", "abc", "xyz", "Bearer test", "segredo"):
            self.assertNotIn(secret, serialized)
        self.assertNotIn("A" * 100, serialized)
        self.assertIn("REDACTED", serialized)

    def test_cancellation_lifecycle_and_emergency_command(self):
        token = CancellationToken()
        self.assertFalse(token.is_cancelled())
        token.request_cancel()
        self.assertTrue(token.is_cancelled())
        token.clear_cancel()
        self.assertFalse(token.is_cancelled())
        result = self.service.execute_command("pare jarvis")
        self.assertTrue(result["cancel_requested"])
        self.assertTrue(self.service.cancellation.is_cancelled())

    def test_brain_timeout_is_controlled(self):
        self.brain.timeout = .01
        fake = types.SimpleNamespace(chat=lambda **kwargs: (time.sleep(.15), {})[1])
        with patch.dict(sys.modules, {"ollama": fake}):
            result = self.brain._call_llm("teste")
        self.assertFalse(result["ok"])
        self.assertIn("limite", result["error"])

    def test_vision_timeout_is_controlled(self):
        vision = JarvisVision()
        vision.timeout = .01
        with self.assertRaises(TimeoutError):
            vision._call_with_timeout(lambda: time.sleep(.15))

    def test_safe_regression_handlers_with_dry_run(self):
        self.service.dry_run = True
        cases = (("get_time", {}), ("system_status", {}),
                 ("open_program", {"name": "calculadora"}),
                 ("close_program", {"name": "calculadora"}),
                 ("open_folder", {"name": "downloads"}),
                 ("list_processes", {}), ("volume_up", {}),
                 ("take_screenshot", {}),
                 ("analyze_screen", {"question": ""}))
        for tool, args in cases:
            with self.subTest(tool=tool):
                self.assertTrue(self.service.execute_tool(tool, args)["ok"])

if __name__ == "__main__":
    unittest.main()
