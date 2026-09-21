import re
import threading
from enum import Enum


class OutputMode(str, Enum):
    AUTO = "AUTO"
    VOICE = "VOICE"
    TEXT = "TEXT"
    VOICE_AND_TEXT = "VOICE_AND_TEXT"


class OutputModeManager:
    def __init__(self):
        self.mode = OutputMode.AUTO
        self._lock = threading.Lock()

    def parse(self, text, source="text"):
        content = str(text or "").strip()
        patterns = (
            (OutputMode.VOICE_AND_TEXT, r"\b(fale e escreva|responda falando e por escrito)\b"),
            (OutputMode.TEXT, r"\b(responda por escrito|n[aã]o fale)\b"),
            (OutputMode.VOICE, r"\b(fale comigo|responda falando|(?:mas\s+)?quero ouvir a resposta|responda em [aá]udio)\b"),
        )
        selected = None
        for mode, pattern in patterns:
            if re.search(pattern, content, re.I):
                selected = mode
                content = re.sub(pattern, "", content, flags=re.I)
                content = re.sub(r"\s*[,;:]\s*", " ", content)
                content = re.sub(r"\s+", " ", content).strip(" .,-")
                break
        with self._lock:
            if selected:
                self.mode = selected
            mode = self.mode
        speak = mode in {OutputMode.VOICE, OutputMode.VOICE_AND_TEXT} or (
            mode == OutputMode.AUTO and source == "voice")
        show_text = mode != OutputMode.VOICE or source == "voice"
        return {"content": content, "mode": mode.value, "speak": speak,
                "show_text": show_text, "explicit": bool(selected)}


def to_spoken_text(text):
    value = str(text or "")
    value = re.sub(r"```.*?```", "", value, flags=re.S)
    value = re.sub(r"https?://\S+", "link", value)
    value = re.sub(r"(?m)^\s{0,3}(?:#{1,6}|[-*+] |\d+[.)] )", "", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"\s+", " ", value).strip()


_manager = OutputModeManager()


def get_output_mode_manager():
    return _manager
