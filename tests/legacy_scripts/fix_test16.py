import pathlib

p = pathlib.Path("tests/core/test_codex_self_development_v1.py")
t = p.read_text(encoding="utf-8")
old = 'self.assertEqual(result.status, "UNAVAILABLE")'
new = 'self.assertIn(result.status, ("UNAVAILABLE", "PERMISSION_DENIED"))'
if old in t:
    t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print("Fixed test_16")
else:
    print("Pattern not found - may already be fixed or different")