"""ConversaView: View do modo CONVERSA — animação central + chat + input + status footer."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout, QSizeGrip

from ..widgets.backdrop_v4 import BackdropV4
from ..widgets.animation_foundation import AnimationFoundation
from ..widgets.chat_view import ChatWidget
from ..widgets.status_footer import StatusFooter
from ..theme_v4 import CYAN, GOLD, BG_PANEL, BORDER_SUBTLE, RADIUS_MD


class ConversaView(QWidget):
    """
    View principal do modo CONVERSA.
    Layout:
    - BackdropV4 (fundo)
    - Área central: AnimationFoundation (estados IDLE/LISTENING/PROCESSING/SPEAKING)
    - ChatWidget (reutiliza existente)
    - Input bar (mic + input + send)
    - StatusFooter (CPU/RAM/GPU, Providers, Serviços)
    """

    def __init__(self, on_send, on_voice_toggle, parent=None):
        super().__init__(parent)
        self._on_send = on_send
        self._on_voice = on_voice_toggle

        # Root com backdrop
        self.backdrop = BackdropV4()
        self.setAttribute(Qt.WA_StyledBackground, True)

        root_layout = QVBoxLayout(self.backdrop)
        root_layout.setContentsMargins(16, 8, 16, 8)
        root_layout.setSpacing(6)

        # ===== AREA CENTRAL: AVATAR (45-55% do espaco) =====
        self.animation = AnimationFoundation()
        self.animation.setMinimumHeight(340)
        root_layout.addWidget(self.animation, 3)

        # Separador sutil
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER_SUBTLE}; border: none;")
        root_layout.addWidget(sep)

        # ===== CHAT (compacto) =====
        self.chat = ChatWidget(on_send=on_send, on_voice_toggle=on_voice_toggle)
        self.chat.setMinimumHeight(180)
        self.chat.setMaximumHeight(300)
        root_layout.addWidget(self.chat, 1)

        # ===== STATUS FOOTER =====
        self.status_footer = StatusFooter()
        root_layout.addWidget(self.status_footer, 0)

        # Size grip no canto
        grip_layout = QHBoxLayout()
        grip_layout.addStretch(1)
        grip_layout.addWidget(QSizeGrip(self))
        root_layout.addLayout(grip_layout)

        # Layout principal do widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.backdrop)

    # ===== API para MainWindow =====

    def set_animation_state(self, state: str):
        """Define estado da animação: IDLE, LISTENING, PROCESSING, SPEAKING, OFFLINE, ERROR."""
        self.animation.set_state(state)

    def set_voice_level(self, level: float):
        self.animation.set_voice_level(level)

    def add_waveform_sample(self, sample: float):
        self.animation.add_waveform_sample(sample)

    def start_voice_simulation(self):
        self.animation.start_voice_simulation()

    def stop_voice_simulation(self):
        self.animation.stop_voice_simulation()

    def get_chat_widget(self) -> ChatWidget:
        return self.chat

    def get_status_footer(self) -> StatusFooter:
        return self.status_footer

    def add_user_message(self, text: str):
        self.chat.add_user(text)

    def add_jarvis_message(self, text: str):
        self.chat.add_jarvis(text)

    def set_mic_state(self, listening: bool):
        self.chat.set_mic_state(listening)

    def set_chat_meta(self, route="", brain="", conf="", skill="", provider="", dev_extra="", llm=None):
        self.chat.set_meta(route, brain, conf, skill, provider, dev_extra, llm)