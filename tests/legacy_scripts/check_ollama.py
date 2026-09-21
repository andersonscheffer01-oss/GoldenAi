import sys
sys.path.insert(0, r"c:\GoldenAI")
from core.models.ollama_provider import OllamaProvider

provider = OllamaProvider()
connected = provider.is_connected()
print(f"Ollama connected: {connected}")
if connected:
    models = provider.list_models()
    print(f"Models available: {len(models)}")
    for m in models:
        print(f"  - {m.name}")
else:
    print("Ollama daemon is not running. Try: ollama serve")