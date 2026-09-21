"""Testes de interacao: input, send, workers, overlay, voz sem duplicar."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from jarvis_desktop.api_client import JarvisApiClient
from jarvis_desktop.main_window import MainWindow
from jarvis_desktop.theme import apply_theme


class FakeClient(JarvisApiClient):
    def __init__(self):
        super().__init__("http://127.0.0.1:9")
        self.posts = []

    def _post(self, path, payload=None, timeout=None):
        self.posts.append(path)
        if path == "/api/jarvis/chat":
            return {"ok": True, "response": "USD: R$ 5,13.", "tool": "get_exchange_rate",
                    "model": "qwen2.5-coder:14b", "route": "MARKET_DATA",
                    "skill": "market_data", "confidence": 0.94,
                    "tool_provider": "awesomeapi"}
        if path == "/api/jarvis/tasks/list":
            return {"ok": True, "tasks": []}
        return {"ok": True}


def make_window():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    client = FakeClient()
    win = MainWindow(client)
    win.show()
    return app, win, client


class InteractionCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.win, cls.client = make_window()

    def test_input_enabled_and_typing(self):
        import time
        inp = self.win.chat.input
        self.assertTrue(inp.isVisible() and inp.isEnabled() and not inp.isReadOnly())
        for _ in range(100):
            self.app.processEvents()
            time.sleep(0.02)
            if self.win.isActiveWindow():
                break
        QTest.mouseClick(inp, Qt.LeftButton, pos=inp.rect().center())
        self.app.processEvents()
        if not inp.hasFocus():
            inp.setFocus()  # offscreen nem sempre entrega foco no clique sintetico
            self.app.processEvents()
        self.assertTrue(inp.hasFocus())
        inp.clear()
        QTest.keyClicks(inp, "qual a cotacao do dolar")
        self.assertEqual("qual a cotacao do dolar", inp.text())

    def test_send_click_delivers_response(self):
        self.win.state.backend_online = True
        inp = self.win.chat.input
        inp.clear()
        QTest.keyClicks(inp, "que horas sao xyz")
        before = len(self.client.posts)
        QTest.mouseClick(self.win.chat.send, Qt.LeftButton)
        for _ in range(200):
            self.app.processEvents()
            import time
            time.sleep(0.05)
            if "/api/jarvis/chat" in self.client.posts[before:]:
                break
        for _ in range(100):
            self.app.processEvents()
            import time
            time.sleep(0.05)
        html = self.win.chat.history.toHtml()
        self.assertIn("que horas sao xyz", html)
        self.assertIn("5,13", html)
        self.assertEqual("", self.win.chat.input.text())

    def test_enter_sends(self):
        self.win.state.backend_online = True
        inp = self.win.chat.input
        inp.clear()
        QTest.keyClicks(inp, "oi enter")
        QTest.keyClick(inp, Qt.Key_Return)
        self.assertEqual("", inp.text())

    def test_overlays_do_not_capture_mouse(self):
        self.assertTrue(self.win.centralWidget().testAttribute(Qt.WA_TransparentForMouseEvents))
        self.assertNotIn("mousePressEvent", MainWindow.__dict__)
        self.assertNotIn("mouseMoveEvent", MainWindow.__dict__)
        # drag vive SOMENTE na title bar
        self.assertIn("mousePressEvent", type(self.win.titlebar).__dict__)

    def test_workers_retained_until_finished(self):
        import time
        done = []
        self.win._run(lambda: {"ok": True}, done.append)
        self.assertTrue(len(self.win._pending_workers) >= 1)
        for _ in range(100):
            self.app.processEvents()
            time.sleep(0.02)
            if done:
                break
        self.assertTrue(done)
        for _ in range(50):
            self.app.processEvents()
            time.sleep(0.02)
        self.assertEqual({}, self.win._pending_workers)

    def test_voice_mirror_without_resubmit(self):
        self.win.state.backend_online = True
        # baseline zerada: simula primeira leitura (evento antigo nao espelha)
        self.win._voice_baseline = False
        self.win._seen_event_id = 0
        chat_posts = len([p for p in self.client.posts if p == "/api/jarvis/chat"])
        base = {"ok": True, "state": "WAITING_WAKE", "running": True,
                "last_heard": "antigo", "last_response": "antiga",
                "last_event": {"id": 5, "heard": "antigo", "response": "antiga",
                               "route": "CONVERSATION"},
                "stats": {"commands": 5, "errors": 0, "heard": 9}}
        self.win.on_voice(dict(base))
        html0 = self.win.chat.history.toHtml()
        self.assertNotIn("antigo", html0)
        # sem evento novo (ruido ignorado): nada entra, nada reenvia
        self.win.on_voice({"ok": True, "state": "WAITING_WAKE", "running": True,
                           "last_heard": "ruido ambiente xyz", "last_response": "",
                           "last_event": {"id": 5}, "stats": {}})
        self.assertNotIn("ruido ambiente xyz", self.win.chat.history.toHtml())
        # novo evento executado: espelha par + metadados, SEM /api/jarvis/chat
        done = {"ok": True, "state": "SPEAKING", "running": True,
                "last_heard": "que horas sao voz", "last_response": "Sao 10h voz.",
                "last_event": {"id": 6, "heard": "que horas sao voz",
                               "response": "Sao 10h voz.", "route": "SYSTEM",
                               "skill": "system", "confidence": 1.0,
                               "tool": "get_time", "tool_provider": "",
                               "timings": {"execution_ms": 12}},
                "stats": {"commands": 6, "errors": 0, "heard": 10}}
        self.win.on_voice(dict(done))
        html1 = self.win.chat.history.toHtml()
        self.assertIn("que horas sao voz", html1)
        self.assertIn("Sao 10h voz.", html1)
        self.assertEqual("SYSTEM", self.win.state.last_route)
        self.assertEqual("system", self.win.state.last_skill)
        chat_posts1 = len([p for p in self.client.posts if p == "/api/jarvis/chat"])
        self.assertEqual(chat_posts, chat_posts1)
        # repeticao nao duplica
        self.win.on_voice(dict(done))
        self.assertEqual(html1, self.win.chat.history.toHtml())

    def test_request_to_response_appends_jarvis(self):
        """request -> resposta final -> append JARVIS + HUD + scroll."""
        import time
        self.win.state.backend_online = True
        self.win.submit_message("ping jarvis 777", source="typed")
        for _ in range(200):
            self.app.processEvents()
            time.sleep(0.05)
            if not self.win._pending_workers and "ping jarvis 777" in self.win.chat.history.toHtml():
                break
        html = self.win.chat.history.toHtml()
        self.assertIn("ping jarvis 777", html)
        self.assertIn("5,13", html)  # bolha JARVIS com a resposta final
        self.assertEqual("CONCLUÍDO", self.win.state.jarvis)
        sb = self.win.chat.history.verticalScrollBar()
        self.assertEqual(sb.maximum(), sb.value())
        self.assertEqual({}, self.win._pending_workers)

    def test_route_meta_updates_immediately(self):
        """Metadados da resposta (route/skill/provider) sem depender de poll."""
        import time
        self.win.state.backend_online = True
        self.win.submit_message("ping meta 888", source="typed")
        for _ in range(200):
            self.app.processEvents()
            time.sleep(0.05)
            if not self.win._pending_workers and "ping meta 888" in self.win.chat.history.toHtml():
                break
        meta = self.win.chat.meta.text()
        self.assertIn("MARKET_DATA", meta)  # route veio na resposta
        self.assertIn("market_data", meta)
        self.assertIn("AWESOMEAPI", meta)
        self.assertEqual("MARKET_DATA", self.win.state.last_route)
        self.assertEqual("market_data", self.win.state.last_skill)
        self.assertEqual("awesomeapi", self.win.state.last_provider)

    def test_empty_submit_noop(self):
        before = len(self.client.posts)
        self.win.submit_message("   ", source="typed")
        self.assertEqual(before, len(self.client.posts))


if __name__ == "__main__":
    unittest.main()
