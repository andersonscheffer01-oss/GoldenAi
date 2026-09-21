"""Check Ollama availability."""
import httpx

print("OLLAMA:")
try:
    r = httpx.get("http://localhost:11434/api/tags", timeout=5)
    if r.status_code == 200:
        models = r.json().get("models", [])
        print(f"  Status: RUNNING ({len(models)} models)")
        for m in models[:5]:
            name = m["name"]
            print(f"    - {name}")
    else:
        print(f"  Status: ERROR {r.status_code}")
except Exception as e:
    print(f"  Status: NOT RUNNING ({e})")
