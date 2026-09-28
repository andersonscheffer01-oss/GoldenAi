from pathlib import Path

from jarvis_core import JarvisService

class DesktopCenter:
    """Mantém as rotas antigas usando o núcleo modular do Jarvis."""
    def __init__(self):
        self.service = JarvisService(
            Path(__file__).resolve().parent, task_db_mode="production")

    def status(self):
        return self.service.status()

    def execute(self, command):
        return self.service.execute_command(command)

    def confirm(self, token):
        return self.service.confirm(token)

DESKTOP_CENTER = DesktopCenter()
