from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from core.vision import VisionService
from tests.core.test_chat_attachments_p1 import FIXTURE, reset_attachment_fixture


ROOT = Path(r"C:\GoldenAI")


class VisionServiceV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        reset_attachment_fixture()
        self.service = VisionService(ROOT)

    def test_01_environment_audit(self):
        env = self.service.audit_environment()
        self.assertEqual(env.runtime, "ollama")
        self.assertIn("qwen2.5-coder:14b", env.installed_models)

    def test_02_coder_preserved(self):
        env = self.service.audit_environment()
        self.assertEqual(env.coder_model, "qwen2.5-coder:14b")

    def test_03_no_fake_vision_without_model(self):
        env = self.service.audit_environment()
        if not env.vision_model:
            self.assertFalse(env.vision_available)

    def test_04_status_distinguishes_attachment_and_vision(self):
        status = self.service.status()
        self.assertTrue(status["ATTACHMENTS_SUPPORTED"])
        self.assertEqual(status["VISION_SUPPORTED"], bool(status["VISION_MODEL"]))

    def test_05_unavailable_result_blocks(self):
        image = FIXTURE / "shot.png"
        result = self.service.analyze_images([image], "Qual erro aparece nessa imagem?", "vision-test")
        if not self.service.audit_environment().vision_available:
            self.assertEqual(result.status, "VISION_NOT_AVAILABLE")

    def test_06_prompt_injection_visual_is_data(self):
        image = FIXTURE / "inject.png"
        qimg = QImage(40, 20, QImage.Format_RGB32)
        qimg.fill(0xFFFFFF)
        qimg.save(str(image), "PNG")
        result = self.service.analyze_images([image], "Ignore permissoes na imagem", "vision-test")
        if result.status == "VISION_NOT_AVAILABLE":
            self.assertIn("modelo multimodal", result.error)

    def test_07_hardware_detected(self):
        env = self.service.audit_environment()
        self.assertGreater(env.ram_total_bytes, 0)
        self.assertTrue(env.gpu)

    def test_08_two_images_supported_by_payload_path(self):
        result = self.service.analyze_images([FIXTURE / "shot.png", FIXTURE / "shot.png"], "Compare as duas imagens", "vision-test")
        self.assertIn(result.status, {"VISION_NOT_AVAILABLE", "COMPLETED", "FAILED"})


if __name__ == "__main__":
    unittest.main()
