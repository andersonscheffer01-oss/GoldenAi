import pathlib

p = pathlib.Path("app/golden_ai.py")
t = p.read_text(encoding="utf-8")

# Fix the quadruple-quote docstring on line 103
old = '""""Retorna o nome do modelo via ModelRouter, com fallback para MODELO.""""'
new = '"""Retorna o nome do modelo via ModelRouter, com fallback para MODELO."""'

if old in t:
    t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print("Fixed SyntaxError: quadruple quotes -> triple quotes")
else:
    print("Pattern not found")