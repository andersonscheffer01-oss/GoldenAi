"""Debug script: Run Codex CLI with improved prompt."""
import sys
import os
import subprocess
import time
import json
import re
from pathlib import Path

sys.path.insert(0, r"c:\GoldenAI")

# Create buggy file
sandbox = Path(r"C:\GoldenAI\sandbox\self_development_test")
sandbox.mkdir(parents=True, exist_ok=True)
buggy = sandbox / "buggy_code.py"
buggy.write_text('def add(a, b):\n    return a - b\n', encoding="utf-8")

print(f"Before: {buggy.read_text()}")
print(f"Workdir: {sandbox}")
print()

# Improved prompt - explicitly request _edit_file tool call
prompt = (
    "You are a coding agent. Edit the file buggy_code.py. "
    "The function add(a, b) currently returns a - b (subtraction). "
    "Change it to return a + b (addition). "
    "Use the _edit_file tool to make this change. "
    "Do NOT use nano, vim, sed, or any interactive editor. "
    "Output the _edit_file tool call with the full corrected file content."
)

# Build command
codex_path = "codex"
cmd = [
    codex_path, "exec",
    "--oss",
    "--local-provider", "ollama",
    "-m", "qwen2.5-coder:14b",
    "-C", str(sandbox),
    "-s", "workspace-write",
    "--skip-git-repo-check",
    "--ignore-user-config",
    "-o", str(sandbox / "codex_last_message.txt"),
    prompt,
]

print("Command:", " ".join(cmd))
print()

# Build env without OPENAI_API_KEY
env = dict(os.environ)
env.pop("OPENAI_API_KEY", None)
env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")

start = time.monotonic()
try:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(sandbox),
        shell=True,
        env=env,
    )
    duration = time.monotonic() - start
    print(f"Exit code: {proc.returncode}")
    print(f"Duration: {duration:.1f}s")
    print(f"STDOUT:")
    print(proc.stdout[:3000])
    print(f"STDERR (first 500):")
    print(proc.stderr[:500])
except subprocess.TimeoutExpired:
    print("TIMEOUT after 120s")
except Exception as e:
    print(f"Error: {e}")

print()
print(f"After: {buggy.read_text()}")

# Check last message
last_msg = sandbox / "codex_last_message.txt"
if last_msg.exists():
    print(f"Last message: {last_msg.read_text()[:500]}")

# Parse tool calls
from core.tools.external.adapters.codex_cli import CodexCLIAdapter
adapter = CodexCLIAdapter()
full_text = proc.stdout + "\n" + (last_msg.read_text() if last_msg.exists() else "")
tool_calls = adapter._parse_tool_calls(full_text)
print(f"\nTool calls found: {len(tool_calls)}")
for tc in tool_calls:
    print(f"  {tc}")