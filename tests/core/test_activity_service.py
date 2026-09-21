from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys

ROOT = Path(r"C:\GoldenAI")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.activity import ActivityService  # noqa: E402


def conv_id_for(day: str) -> str:
    dt = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp() * 1000))


class ActivityServiceTests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        history = root / "studio" / "historico_v2.json"
        logs = root / "logs"
        db = root / "data" / "golden_ai.db"
        history.parent.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)
        service = ActivityService(root=root, db_path=db, history_path=history, logs_dir=logs)
        self.addCleanup(tmp.cleanup)
        return service, history, logs, db

    def write_history(self, history: Path):
        history.write_text(
            json.dumps([
                {
                    "id": conv_id_for("2026-08-12"),
                    "title": "Conversa",
                    "context": r"C:\GoldenAI\projetos\Robo_XAUUSD_EMA_ATR_VWAP_TESTE.mq5",
                    "messages": [
                        {"role": "user", "text": "ola"},
                        {"role": "assistant", "text": "oi"},
                    ],
                },
                {
                    "id": conv_id_for("2026-08-13"),
                    "title": "RAM",
                    "context": r"C:\GoldenAI\projetos\robo_teste.mq5",
                    "messages": [
                        {"role": "user", "text": "quanto de ram?"},
                    ],
                },
            ]),
            encoding="utf-8",
        )

    def write_audit(self, logs: Path):
        rows = [
            {
                "action_id": "a1",
                "action_type": "TOOL_ALLOWED",
                "timestamp": "2026-08-13T13:00:00+00:00",
                "session_id": "s1",
                "tool": "get_system_info",
                "status": "ALLOWED",
                "permission_class": "READ_EXTERNAL_SAFE",
                "target": "",
            },
            {
                "action_id": "a2",
                "action_type": "TOOL_DENIED",
                "timestamp": "2026-08-13T13:01:00+00:00",
                "session_id": "s1",
                "tool": "escrever_arquivo",
                "status": "DENIED",
                "permission_class": "WRITE",
                "target": r"C:\GoldenAI\projetos\robo_teste.mq5",
            },
            {
                "action_id": "a3",
                "action_type": "TOOL_DENIED",
                "timestamp": "2026-08-13T13:02:00+00:00",
                "session_id": "s1",
                "tool": "excluir_backup",
                "status": "DENIED",
                "permission_class": "CRITICAL",
                "target": r"C:\GoldenAI\backups\x.py",
            },
        ]
        (logs / "audit_2026-08-13.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows),
            encoding="utf-8",
        )

    def test_register_session_start_and_end_duration(self):
        service, _, _, _ = self.make_service()
        session_id = service.new_session_id()
        service.start_session(session_id)
        time.sleep(0.01)
        service.end_session(session_id)
        data = service.dashboard()
        self.assertEqual(data["summary"]["total_sessions"], 1)
        self.assertTrue(data["session_time"]["known"])

    def test_register_message_and_count_chats(self):
        service, _, _, _ = self.make_service()
        service.record_message("c1", "user", "oi")
        data = service.dashboard()
        self.assertEqual(data["summary"]["total_chats"], 1)
        self.assertEqual(data["summary"]["user_messages"], 1)

    def test_history_counts_days_and_streak(self):
        service, history, _, _ = self.make_service()
        self.write_history(history)
        data = service.dashboard()
        self.assertEqual(data["summary"]["total_chats"], 2)
        self.assertEqual(data["summary"]["total_messages"], 3)
        self.assertGreaterEqual(data["summary"]["active_days"], 2)
        self.assertGreaterEqual(data["summary"]["longest_streak_days"], 2)

    def test_tool_aggregation_and_security_counts(self):
        service, _, logs, _ = self.make_service()
        self.write_audit(logs)
        data = service.dashboard()
        tools = {row["tool"]: row for row in data["tools"]}
        self.assertEqual(tools["get_system_info"]["allowed"], 1)
        self.assertEqual(tools["escrever_arquivo"]["denied"], 1)
        self.assertEqual(data["security"]["write_denied"], 1)
        self.assertEqual(data["security"]["critical_denied"], 1)

    def test_project_ranking_and_heatmap(self):
        service, history, logs, _ = self.make_service()
        self.write_history(history)
        self.write_audit(logs)
        data = service.dashboard()
        self.assertTrue(any("robo_teste.mq5" in row["project_name"] for row in data["projects"]))
        self.assertTrue(any(day["day"] == "2026-08-13" for day in data["heatmap"]))

    def test_empty_database_does_not_create_false_numbers(self):
        service, _, _, _ = self.make_service()
        data = service.dashboard()
        self.assertEqual(data["summary"]["total_chats"], 0)
        self.assertEqual(data["tools"], [])
        self.assertIn("indisponiveis", data["tokens"]["message"])

    def test_invalid_history_json_does_not_break_dashboard(self):
        service, history, _, _ = self.make_service()
        history.write_text("{invalid", encoding="utf-8")
        data = service.dashboard()
        self.assertEqual(data["summary"]["total_messages"], 0)
        self.assertIn("Historico indisponivel", data["last_error"])

    def test_token_usage_is_marked_unavailable(self):
        service, _, _, _ = self.make_service()
        data = service.dashboard()
        self.assertFalse(data["tokens"]["exact_available"])
        self.assertIn("indisponiveis", data["tokens"]["message"])


if __name__ == "__main__":
    unittest.main()
