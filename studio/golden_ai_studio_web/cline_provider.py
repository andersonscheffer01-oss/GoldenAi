#!/usr/bin/env python3
"""
Golden AI - Cline Provider
Usa a API do Cline (OpenAI-compatible) para acessar modelos via credito Cline.
"""

import json
import os
import urllib.request
import urllib.error
import socket
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

CLINE_API_URL = "https://api.cline.bot/api/v1/chat/completions"
CLINE_MODELS_URL = "https://api.cline.bot/api/v1/models"
CLINE_REQUEST_TIMEOUT = 150

# Modelos ClinePass (assinatura $9.99/mes)
CLINE_MODELS = {
    "cline-deepseek-v4": {
        "id": "cline-pass/deepseek-v4-pro",
        "name": "DeepSeek V4 Pro (ClinePass)",
        "description": "Melhor modelo de programacao open-source",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Muito alta",
    },
    "cline-deepseek-flash": {
        "id": "cline-pass/deepseek-v4-flash",
        "name": "DeepSeek V4 Flash (ClinePass)",
        "description": "Rapido e eficiente",
        "cost": "ClinePass (incluido)",
        "speed": "Muito rapido",
        "quality": "Alta",
    },
    "cline-qwen38": {
        "id": "cline-pass/qwen3.8-max",
        "name": "Qwen 3.8 Max (ClinePass)",
        "description": "Melhor modelo Qwen para codigo",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Muito alta",
    },
    "cline-qwen37": {
        "id": "cline-pass/qwen3.7-max",
        "name": "Qwen 3.7 Max (ClinePass)",
        "description": "Modelo Qwen equilibrado",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Alta",
    },
    "cline-mimo": {
        "id": "cline-pass/mimo-v2.5",
        "name": "MiMo V2.5 (ClinePass)",
        "description": "Modelo Xiaomi para codigo",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Alta",
    },
    "cline-glm": {
        "id": "cline-pass/glm-5.2",
        "name": "GLM 5.2 (ClinePass)",
        "description": "Modelo Zhipu AI para codigo",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Alta",
    },
    "cline-kimi": {
        "id": "cline-pass/kimi-k3",
        "name": "Kimi K3 (ClinePass)",
        "description": "Modelo Moonshot AI",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Alta",
    },
    "cline-minimax": {
        "id": "cline-pass/minimax-m3",
        "name": "MiniMax M3 (ClinePass)",
        "description": "Modelo MiniMax multimodal",
        "cost": "ClinePass (incluido)",
        "speed": "Rapido",
        "quality": "Alta",
    },
}


class ClineProvider:
    """Provider para Cline API (OpenAI-compatible)"""

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("CLINE_API_KEY", "")
        self.base_url = CLINE_API_URL

    def _config_path(self):
        return Path(r"C:\GoldenAI\config\api_keys.json")

    def set_api_key(self, key):
        """Salva a API key do Cline"""
        self.api_key = key
        config_path = self._config_path()
        config = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        config["cline_api_key"] = key
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print("[CLINE] API key salva em: %s" % config_path)

    def load_api_key(self):
        """Carrega a API key do arquivo de configuracao"""
        config_path = self._config_path()
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                key = config.get("cline_api_key", "")
                if key:
                    self.api_key = key
                    print("[CLINE] API key carregada")
            except Exception as e:
                print("[CLINE] Erro ao carregar API key: %s" % e)
        return self.api_key

    def chat(self, messages, model="anthropic/claude-sonnet-4"):
        """Envia mensagem para o Cline"""
        if not self.api_key:
            return {"error": "API key do Cline nao configurada. Use: configure_cline_key SUA_KEY"}

        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": 4096,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=CLINE_REQUEST_TIMEOUT) as resp:
                raw_body = resp.read().decode("utf-8", errors="replace").strip()
                if not raw_body:
                    return {"error": "Cline retornou uma resposta vazia. Tente novamente ou use o DeepSeek V4 Flash."}
                result = json.loads(raw_body)
                # Cline API wraps response in 'data' key
                if "data" in result and isinstance(result["data"], dict):
                    return result["data"]
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            return {"error": "Erro HTTP %d: %s" % (e.code, error_body[:500])}
        except (TimeoutError, socket.timeout):
            return {"error": "Tempo esgotado aguardando o Cline (mais de %ds). Tente o DeepSeek V4 Flash ou Ollama Local." % CLINE_REQUEST_TIMEOUT}
        except Exception as e:
            return {"error": "Erro: %s" % str(e)}

    def chat_stream(self, messages, model="anthropic/claude-sonnet-4"):
        """Envia mensagem com streaming"""
        if not self.api_key:
            yield {"error": "API key do Cline nao configurada"}
            return

        headers = {
            "Authorization": "Bearer %s" % self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": 4096,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    line = line.decode("utf-8", errors="replace").strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            if "choices" in chunk and chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    yield {"token": delta["content"]}
                        except Exception:
                            pass
        except Exception as e:
            yield {"error": str(e)}


# Instancia global
cline_provider = ClineProvider()
cline_provider.load_api_key()


def get_cline_provider():
    """Retorna o provider Cline"""
    return cline_provider
