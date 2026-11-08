#!/usr/bin/env python3
"""
🎯 Golden AI — Claude Provider via OpenRouter
Integra o Claude ao Golden AI para análises avançadas.
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

# ============================================================
# CONFIGURAÇÃO
# ============================================================

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
PROJECT_ROOT = Path(
    os.environ.get("GOLDENAI_ROOT")
    or Path(__file__).resolve().parents[2]
).resolve()

# Modelos disponíveis
CLAUDE_MODELS = {
    "cohere-code": {
        "id": "cohere/north-mini-code:free",
        "name": "⚡ Cohere Code (Grátis - Ultra Rápido)",
        "description": "Especialista em programação com resposta instantânea",
        "cost": "Grátis",
        "speed": "Instantâneo (1-2s)",
        "quality": "Excelente para código",
    },
    "nvidia-lightning": {
        "id": "nvidia/nemotron-3.5-lightning:free",
        "name": "⚡ NVIDIA Nemotron (Grátis - Rápido)",
        "description": "Modelo de alta velocidade e precisão da NVIDIA",
        "cost": "Grátis",
        "speed": "Muito rápido",
        "quality": "Alta",
    },
    "openrouter-free": {
        "id": "openrouter/free",
        "name": "🤖 Auto Grátis (Melhor Disponível)",
        "description": "Roteia automaticamente para o melhor modelo grátis",
        "cost": "Grátis",
        "speed": "Rápido",
        "quality": "Ótima",
    },
    "claude-sonnet": {
        "id": "anthropic/claude-sonnet-4",
        "name": "Claude Sonnet 4",
        "description": "Equilíbrio entre velocidade e qualidade",
        "cost": "$3/M tokens",
        "speed": "Rápido",
        "quality": "Muito alta",
    },
    "claude-haiku": {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Claude 3.5 Haiku",
        "description": "Mais rápido, bom para respostas curtas",
        "cost": "$0.25/M tokens",
        "speed": "Muito rápido",
        "quality": "Boa",
    },
}

# System prompt especializado em MQL5/MT5
MQL5_SYSTEM_PROMPT = """Você é o Golden AI, um assistente especializado em:

1. **MQL5/MQL4** - Programação de Expert Advisors, Indicadores e Scripts para MetaTrader 5
2. **MetaTrader 5** - Configuração, otimização e análise de estratégias
3. **Trading** - Análise técnica, gestão de risco, backtesting
4. **Código** - Análise, debug, refatoração de qualquer linguagem

## Suas Capacidades:
- Ler e analisar arquivos MQL5 (até 10.000 linhas)
- Criar e editar robôs EA
- Otimizar parâmetros de trading
- Executar comandos no sistema
- Limpar cache, lixeira, arquivos temporários
- Pesquisar na internet
- Analisar imagens e PDFs

## Formato de Resposta:
- Use **Markdown** formatado
- Use **tabelas** para comparar dados
- Use **emojis** para indicar status
- Seja **direto e prático**
- Responda em **português**

## Quando o usuário enviar código MQL5:
1. Analise a estrutura (funções, inputs, lógica)
2. Identifique bugs ou melhorias
3. Sugira otimizações
4. Ofereça para editar diretamente

## Quando o usuário pedir para executar algo:
1. Use as ferramentas disponíveis (list_directory, read_file, etc.)
2. Execute comandos quando necessário
3. Retorne resultados formatados"""


class ClaudeProvider:
    """Provider para Claude via OpenRouter"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = OPENROUTER_API_URL
    
    def _config_path(self):
        """Retorna o path do arquivo de configuração (relativo ao projeto)"""
        candidate = PROJECT_ROOT / "config" / "api_keys.json"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate
    
    def set_api_key(self, key):
        """Define e salva a API key em arquivo para persistência"""
        self.api_key = key
        config_path = self._config_path()
        
        config = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding='utf-8'))
            except:
                pass
        
        config["openrouter_api_key"] = key
        config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
        print(f"[GOLDEN] API key salva em: {config_path}")
    
    def load_api_key(self):
        """Carrega a API key do arquivo de configuração"""
        config_path = self._config_path()
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding='utf-8'))
                key = config.get("openrouter_api_key", "")
                if key:
                    self.api_key = key
                    print(f"[GOLDEN] API key carregada de: {config_path}")
            except Exception as e:
                print(f"[GOLDEN] Erro ao carregar API key: {e}")
        return self.api_key
    
    def chat(self, messages, model="anthropic/claude-sonnet-4", stream=False):
        """Envia mensagem para o Claude via OpenRouter"""
        if not self.api_key:
            return {"error": "API key não configurada. Use:configure_api_key SUA_KEY"}
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8765",
            "X-Title": "Golden AI Studio",
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "max_tokens": 4096,
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.base_url, data=data, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')
            return {"error": f"Erro HTTP {e.code}: {error_body[:500]}"}
        except Exception as e:
            return {"error": f"Erro: {str(e)}"}
    
    def chat_stream(self, messages, model="anthropic/claude-sonnet-4"):
        """Envia mensagem com streaming"""
        if not self.api_key:
            yield {"error": "API key não configurada"}
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8765",
            "X-Title": "Golden AI Studio",
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": 4096,
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.base_url, data=data, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    line = line.decode('utf-8', errors='replace').strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            if "choices" in chunk and chunk["choices"]:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    yield {"token": delta["content"]}
                        except:
                            pass
        except Exception as e:
            yield {"error": str(e)}
    
    def analyze_mql5(self, code, question="Analise este código MQL5"):
        """Analisa código MQL5 com Claude"""
        messages = [
            {"role": "system", "content": MQL5_SYSTEM_PROMPT},
            {"role": "user", "content": f"{question}\n\n```mql5\n{code}\n```"}
        ]
        
        result = self.chat(messages)
        if "error" in result:
            return result["error"]
        
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]
        
        return "Erro ao obter resposta"
    
    def optimize_strategy(self, strategy_data):
        """Otimiza estratégia de trading"""
        messages = [
            {"role": "system", "content": MQL5_SYSTEM_PROMPT},
            {"role": "user", "content": f"Otimize esta estratégia de trading e sugira os melhores parâmetros:\n\n{json.dumps(strategy_data, indent=2)}"}
        ]
        
        result = self.chat(messages)
        if "error" in result:
            return result["error"]
        
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]
        
        return "Erro ao obter resposta"


# Instância global
claude_provider = ClaudeProvider()
claude_provider.load_api_key()


def get_claude_provider():
    """Retorna o provider Claude"""
    return claude_provider

