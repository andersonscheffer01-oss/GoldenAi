import pathlib

p = pathlib.Path("tests/core/test_codex_self_development_v1.py")
t = p.read_text(encoding="utf-8")

# Add ExecutionService import
old_import = "from core.config import CodingAgentConfig, GoldenAISettings, load_settings"
new_import = """from core.config import CodingAgentConfig, GoldenAISettings, load_settings
from core.execution import ExecutionService, PermissionMode"""
if old_import in t:
    t = t.replace(old_import, new_import)

# Fix setUp to set execution mode
old_setup = """        self.pm = PermissionManager(self.settings)

    def tearDown(self) -> None:"""
new_setup = """        self.pm = PermissionManager(self.settings)
        self.pm.execution.set_mode(PermissionMode.AUTO_SAFE)

    def tearDown(self) -> None:"""
if old_setup in t:
    t = t.replace(old_setup, new_setup)

p.write_text(t, encoding="utf-8")
print("Fixed E2E test - added execution mode setting")