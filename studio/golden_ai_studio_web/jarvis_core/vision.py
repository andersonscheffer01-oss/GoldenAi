"""
Jarvis Vision — Visão Computacional do Jarvis
=============================================
Captura a tela e analisa via modelo visual (qwen2.5vl:7b no Ollama).

Comandos suportados:
    "Jarvis, veja minha tela"
    "Jarvis, o que esta aparecendo na tela?"
    "Jarvis, veja o MetaTrader"
    "Jarvis, onde esta o botao de configuracoes?"
"""

import base64
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path


class JarvisVision:
    """Visão do Jarvis — captura tela e analisa com modelo visual."""

    def __init__(self):
        self.model = os.getenv("JARVIS_VISION_MODEL", "qwen2.5vl:7b")
        self.timeout = float(os.getenv("JARVIS_VISION_TIMEOUT", "60"))
        self.last_analysis = ""
        self.last_screenshot_path = ""

    # ═══════════════════════════════════════════════════════════════
    # SCREENSHOT
    # ═══════════════════════════════════════════════════════════════

    def capture_screen(self, window: str = "") -> dict:
        """Captura a tela (inteira ou janela especifica). Retorna PNG bytes."""
        try:
            from PIL import ImageGrab

            folder = Path.home() / "Pictures" / "Golden Jarvis"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / time.strftime("visao_%Y%m%d_%H%M%S.png")

            img = ImageGrab.grab(all_screens=True)

            # Reduzir tamanho para economizar tokens (max 1280px largura)
            max_width = 1280
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)))

            img.save(path, "PNG")

            with open(path, "rb") as f:
                png_bytes = f.read()

            self.last_screenshot_path = str(path)
            return {
                "ok": True,
                "png_bytes": png_bytes,
                "path": str(path),
                "width": img.width,
                "height": img.height,
            }
        except ImportError:
            return {"ok": False, "error": "Pillow nao instalado"}
        except Exception as e:
            return {"ok": False, "error": f"Erro captura: {e}"}

    # ═══════════════════════════════════════════════════════════════
    # ANALISE VISUAL VIA OLLAMA
    # ═══════════════════════════════════════════════════════════════

    def analyze_screen(self, question: str = "", window: str = "") -> dict:
        """Captura a tela e analisa com o modelo visual."""
        capture = self.capture_screen(window)
        if not capture.get("ok"):
            return capture

        try:
            import ollama

            prompt = question.strip() or (
                "Descreva o que esta aparecendo nesta tela de computador. "
                "Seja conciso e direto em portugues. "
                "Se houver erro visivel, descreva-o. "
                "Se for um programa, diga qual e e o que esta sendo feito."
            )

            img_b64 = base64.b64encode(capture["png_bytes"]).decode("ascii")

            response = self._call_with_timeout(ollama.chat, model=self.model,
                messages=[{"role": "user", "content": prompt, "images": [img_b64]}],
                stream=False)

            analysis = response.get("message", {}).get("content", "").strip()
            self.last_analysis = analysis

            return {
                "ok": True,
                "analysis": analysis,
                "screenshot_path": capture["path"],
                "model": self.model,
                "question": question,
            }
        except TimeoutError:
            return {"ok": False, "error": f"Visão excedeu o limite de {self.timeout:g} segundos."}
        except ImportError:
            return {"ok": False, "error": "Biblioteca ollama nao instalada"}
        except Exception as e:
            return {"ok": False, "error": f"Erro analise visual: {e}"}

    # ═══════════════════════════════════════════════════════════════
    # ANALISE DE IMAGEM EXTERNA (base64)
    # ═══════════════════════════════════════════════════════════════

    def analyze_image(self, image_b64: str, question: str = "") -> dict:
        """Analisa uma imagem base64 enviada pelo browser."""
        try:
            import ollama

            prompt = question.strip() or "Descreva esta imagem em portugues, de forma concisa."

            response = self._call_with_timeout(ollama.chat, model=self.model,
                messages=[{"role": "user", "content": prompt, "images": [image_b64]}],
                stream=False)

            return {
                "ok": True,
                "analysis": response.get("message", {}).get("content", "").strip(),
                "model": self.model,
            }
        except TimeoutError:
            return {"ok": False, "error": f"Visão excedeu o limite de {self.timeout:g} segundos."}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _call_with_timeout(self, function, **kwargs):
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(function, **kwargs)
        try:
            return future.result(timeout=self.timeout)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    # ═══════════════════════════════════════════════════════════════
    # STATUS
    # ═══════════════════════════════════════════════════════════════

    def status(self) -> dict:
        # Verificar se o modelo visual esta disponivel no Ollama
        vision_available = False
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as r:
                models = json.loads(r.read()).get("models", [])
                vision_available = any(self.model in m.get("name", "") for m in models)
        except Exception:
            pass

        return {
            "model": self.model,
            "timeout": self.timeout,
            "vision_available": vision_available,
            "last_analysis": self.last_analysis[:200] if self.last_analysis else "",
            "last_screenshot": self.last_screenshot_path,
        }


# Singleton
_vision = None

def get_vision() -> JarvisVision:
    global _vision
    if _vision is None:
        _vision = JarvisVision()
    return _vision
