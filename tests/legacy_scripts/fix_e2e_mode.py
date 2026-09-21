import pathlib

p = pathlib.Path("tests/core/test_codex_self_development_v1.py")
t = p.read_text(encoding="utf-8")

# Change AUTO_SAFE to FULL for E2E test
t = t.replace("PermissionMode.AUTO_SAFE", "PermissionMode.FULL")

p.write_text(t, encoding="utf-8")
print("Fixed E2E test - changed to FULL mode")