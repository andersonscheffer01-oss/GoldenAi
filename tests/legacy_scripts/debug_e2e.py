"""Debug E2E: Use CodexCLIAdapter.execute_task directly."""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, r"c:\GoldenAI")

from core.config import GoldenAISettings
from core.permissions import PermissionManager
from core.execution import ExecutionService, PermissionMode
from core.tools.external.adapters.codex_cli import CodexCLIAdapter

# Create temp settings that allow execution
tmp = tempfile.TemporaryDirectory()
root = Path(tmp.name) / "GoldenAI"
(root / "sandbox" / "self_development_test").mkdir(parents=True, exist_ok=True)
(root / "logs").mkdir(parents=True)
(root / "data").mkdir(parents=True)
(root / "backups").mkdir(parents=True)

settings = GoldenAISettings(
    root=root,
    sandbox_dir=root / "sandbox",
    logs_dir=root / "logs",
    data_dir=root / "data",
    backups_dir=root / "backups",
    allowed_paths=(root / "sandbox", root / "data", root / "logs"),
    protected_paths=(root / "app", root / "core"),
    read_only=False,
    write_enabled=True,
    command_execution_enabled=True,
)

pm = PermissionManager(settings)
pm.execution.set_mode(PermissionMode.FULL)

# Create buggy file in the REAL sandbox (not temp)
sandbox_dir = Path(r"C:\GoldenAI\sandbox\self_development_test")
sandbox_dir.mkdir(parents=True, exist_ok=True)
buggy = sandbox_dir / "buggy_code.py"
buggy.write_text('def add(a, b):\n    return a - b\n', encoding="utf-8")

print(f"Before: {buggy.read_text()}")
print(f"Workdir: {sandbox_dir}")
print()

# Create adapter with the permissive settings
adapter = CodexCLIAdapter(permission_manager=pm, settings=settings)

# Use improved prompt
prompt = (
    "You are a coding agent. Edit the file buggy_code.py. "
    "The function add(a, b) currently returns a - b (subtraction). "
    "Change it to return a + b (addition). "
    "Use the _edit_file tool to make this change. "
    "Do NOT use nano, vim, sed, or any interactive editor. "
    "Output the _edit_file tool call with the full corrected file content."
)

print("Running Codex CLI via adapter...")
result = adapter.execute_task(
    prompt=prompt,
    workdir=str(sandbox_dir),
    timeout=120,
)

print(f"Success: {result.success}")
print(f"Status: {result.status}")
print(f"Message: {result.message}")
print(f"Exit code: {result.exit_code}")
print(f"Duration: {result.duration:.1f}s")
print(f"Files modified: {result.files_modified}")
print(f"Tool calls found: {result.metadata.get('tool_calls_found', 0)}")
print(f"Tool calls applied: {result.metadata.get('tool_calls_applied', 0)}")
print(f"Apply errors: {result.metadata.get('apply_errors', [])}")
print(f"Provider: {result.metadata.get('provider')}")
print(f"Local only: {result.metadata.get('local_only')}")
print(f"Paid fallback: {result.metadata.get('paid_fallback')}")
print()
print(f"After: {buggy.read_text()}")

# Check if the fix was applied
content = buggy.read_text(encoding="utf-8")
if "a + b" in content:
    print("\n*** SUCCESS: Bug was fixed! File contains 'a + b' ***")
else:
    print("\n*** FAILURE: Bug was NOT fixed. File still contains 'a - b' ***")

tmp.cleanup()