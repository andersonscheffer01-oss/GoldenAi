import pathlib

p = pathlib.Path("core/tools/external/adapters/codex_cli.py")
t = p.read_text(encoding="utf-8")

# Fix _apply_tool_call to handle both 'content' and 'new_content'
old = '''            file_path = args.get("file_path", "")
            content = args.get("content", "")'''

new = '''            file_path = args.get("file_path", "") or args.get("path", "")
            content = args.get("content", "") or args.get("new_content", "") or args.get("new_file_content", "")'''

if old in t:
    t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print("Fixed: _apply_tool_call now handles 'new_content' field")
else:
    print("Pattern not found")