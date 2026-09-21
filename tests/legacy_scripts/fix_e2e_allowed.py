import pathlib

p = pathlib.Path("debug_e2e.py")
t = p.read_text(encoding="utf-8")

# Add C:\GoldenAI\sandbox to allowed_paths
old = "    allowed_paths=(root / \"sandbox\", root / \"data\", root / \"logs\"),"
new = "    allowed_paths=(root / \"sandbox\", root / \"data\", root / \"logs\", Path(r\"C:\\GoldenAI\\sandbox\")),"

if old in t:
    t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print("Fixed: added C:\\GoldenAI\\sandbox to allowed_paths")
else:
    print("Pattern not found")