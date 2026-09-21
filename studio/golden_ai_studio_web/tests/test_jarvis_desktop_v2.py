"""Testes V2 do desktop: status honestos, sem fake (mocks; Qt offscreen)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jarvis_desktop import status_format as fmt


class StatusFormatCase(unittest.TestCase):
    def test_mask_account_hides_sensitive(self):
        masked = fmt.mask_account("12345678")
        self.assertNotIn("123456", masked)
        self.assertTrue(masked.endswith("78"))
        self.assertEqual("N/D", fmt.mask_account(None))

    def test_provider_badges_cover_all_states(self):
        for state in ("ONLINE", "RATE_LIMITED", "DEGRADED", "TIMEOUT",
                      "AUTH_ERROR", "OFFLINE", "UNKNOWN"):
            badge = fmt.provider_badge(state)
            self.assertIn(state.split("_")[0], badge)
            self.assertTrue(badge[0] in ("●", "○", "!", "?"))

    def test_radar_no_data_when_unconfirmed(self):
        self.assertFalse(fmt.radar_display({})["active"])
        self.assertFalse(fmt.radar_display({"ok": False})["active"])
        self.assertFalse(fmt.radar_display({"ok": True, "running": False})["active"])
        self.assertTrue(fmt.radar_display({"ok": True, "running": True})["active"])

    def test_mt5_disconnected_and_masked(self):
        off = fmt.mt5_display({"connections": {"mt5": {"ok": False}}})
        self.assertFalse(off["connected"])
        on = fmt.mt5_display({"connections": {"mt5": {"ok": True, "account": "987654",
                                                      "server": "HantecMarketsMU-MT5", "balance": 100.0}}})
        self.assertTrue(on["connected"])
        self.assertNotIn("987654", on["account"])
        self.assertEqual("HantecMarketsMU-MT5", on["server"])

    def test_voice_states(self):
        self.assertEqual("○ OFF", fmt.voice_display({}))
        self.assertIn("LISTENING", fmt.voice_display({"ok": True, "state": "OUVINDO"}))
        self.assertIn("ERROR", fmt.voice_display({"ok": True, "state": "ERRO"}))

    def test_task_counts(self):
        counts = fmt.task_counts([{"status": "RUNNING"}, {"status": "QUEUED"},
                                  {"status": "WAITING_CONFIRMATION"}, {"status": "FAILED"},
                                  {"status": "COMPLETED"}])
        self.assertEqual(3, counts["active"])
        self.assertEqual(1, counts["waiting"])
        self.assertEqual(1, counts["errors"])

    def test_gpu_no_data_honest(self):
        g = fmt.gpu_text({})
        self.assertEqual("N/D", g["name"])
        self.assertIsNone(g["util"])
        g2 = fmt.gpu_text({"name": "AMD Radeon RX 9060 XT"})
        self.assertIn("AMD", g2["name"])
        self.assertIsNone(g2["util"])

    def test_bar_blocks(self):
        self.assertIn("N/D", fmt.bar_blocks(None))
        self.assertTrue(fmt.bar_blocks(50).startswith("█" * 5))


class HudStateCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls._app = QApplication.instance() or QApplication([])

    def test_all_states_have_color(self):
        from jarvis_desktop.widgets.hud import HudWidget, state_color
        hud = HudWidget()
        for state in ("OFFLINE", "ONLINE", "AGUARDANDO", "OUVINDO", "TRANSCRIBINDO",
                      "PROCESSANDO", "FALANDO", "PENSANDO", "PLANEJANDO",
                      "EXECUTANDO", "AGUARDANDO CONFIRMAÇÃO", "CONCLUÍDO", "ERRO"):
            hud.set_state(state)
            self.assertEqual(state, hud.state.text())
            self.assertTrue(state_color(state).startswith("#"))

    def test_voice_service_states_map_to_hud(self):
        from jarvis_desktop.state import hud_for_voice
        self.assertEqual("AGUARDANDO", hud_for_voice("WAITING_WAKE"))
        self.assertEqual("OUVINDO", hud_for_voice("LISTENING"))
        self.assertEqual("OUVINDO", hud_for_voice("WAKE_DETECTED"))
        self.assertEqual("TRANSCRIBINDO", hud_for_voice("TRANSCRIBING"))
        self.assertEqual("PROCESSANDO", hud_for_voice("PROCESSING"))
        self.assertEqual("FALANDO", hud_for_voice("SPEAKING"))
        self.assertEqual("ERRO", hud_for_voice("ERROR"))
        self.assertEqual("OFFLINE", hud_for_voice("OFF"))


class OfflineStateCase(unittest.TestCase):
    def test_offline_applies_without_crash(self):
        from jarvis_desktop.state import JarvisState
        st = JarvisState()
        st.apply_status({"ok": False})
        self.assertFalse(st.backend_online)


if __name__ == "__main__":
    unittest.main()
