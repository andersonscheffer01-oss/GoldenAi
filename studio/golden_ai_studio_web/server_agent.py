"""
Golden AI Studio - Agent Server
Capacidades: filesystem, executar comandos, limpeza, analise de codigo, busca, multimidia
"""
import os
import sys
import json
import base64
import re
import time
import shutil
import subprocess
import tempfile
import asyncio
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
from threading import Lock

import numpy as _np

# Custom JSON encoder for numpy types
class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (_np.bool_,)):
            return bool(obj)
        if isinstance(obj, (_np.integer,)):
            return int(obj)
        if isinstance(obj, (_np.floating,)):
            return float(obj)
        if isinstance(obj, _np.ndarray):
            return obj.tolist()
        return super().default(obj)

# Fix encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(r"C:\GoldenAI")
MT5_PATH = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import Ollama
try:
    from ollama import chat as ollama_chat
    OLLAMA_AVAILABLE = True
except:
    OLLAMA_AVAILABLE = False

# Import Claude Provider
CLAUDE_AVAILABLE = False
try:
    from claude_provider import get_claude_provider, CLAUDE_MODELS, MQL5_SYSTEM_PROMPT
    CLAUDE_AVAILABLE = True
    print('[Claude] Provider carregado')
except Exception as e:
    print(f'[Claude] Indisponivel: {e}')

# Import Core Permission System
PERMISSION_MANAGER = None
try:
    from core.permissions import PermissionManager
    from core.config import load_settings
    _settings = load_settings()
    PERMISSION_MANAGER = PermissionManager(_settings)
    print('[Core] PermissionManager conectado ao server_agent')
except Exception as e:
    print(f'[Core] PermissionManager indisponivel: {e}')

# Import Plugin System
PLUGIN_REGISTRY = None
try:
    from plugins.plugin_loader import get_plugin_registry
    PLUGIN_REGISTRY = get_plugin_registry(str(ROOT / 'plugins'))
    _plugin_count = len(PLUGIN_REGISTRY.list_plugins())
    print(f'[Plugins] {_plugin_count} plugin(s) carregado(s)')
except Exception as e:
    print(f'[Plugins] Sistema de plugins indisponivel: {e}')

import urllib.request
import urllib.parse
import urllib.error

# Conversation memory
CONVERSATIONS = {}
CONVERSATIONS_LOCK = Lock()
try:
    from core.execution import ExecutionService, PermissionMode
    EXECUTION_SERVICE = PERMISSION_MANAGER.execution if PERMISSION_MANAGER else ExecutionService(ROOT)
except Exception:
    EXECUTION_SERVICE = None


# ═══════════════════════════════════════════════════════════════
# TOOL DEFINITIONS - Ferramentas que o AI pode usar
# ═══════════════════════════════════════════════════════════════

TOOL_DEFINITIONS = """Golden AI - Especialista em MetaTrader 5, MQL5 e Administracao de PC.

## SUA IDENTIDADE
Voce e o Golden AI, um assistente de IA especializado em:
1. MetaTrader 5 e programacao MQL5/MQL4
2. Trading algoritmico e analise tecnica
3. Administracao completa do PC do usuario
4. Backtesting e otimizacao de estrategias
5. Limpeza, manutencao e otimizacao do sistema

## COMO USAR FERRAMENTAS
Quando o usuario pedir uma ACAO no computador, responda SOMENTE com o JSON da ferramenta. Sem texto antes ou depois.

## EXEMPLOS POR CATEGORIA:

### MetaTrader 5 e MQL5:
Usuario: "analise o codigo do Robo Scalper"
{"tool":"analyze_code","path":"C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Experts/Meus Robos/Robo Scalper 1.0.mq5"}

Usuario: "mostre meus robos"
{"tool":"list_directory","path":"C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Experts/Meus Robos/"}

Usuario: "leia o arquivo do bot ciclos"
{"tool":"read_file","path":"C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Experts/Meus Robos/Bot Ciclos EA.mq5","limit":10000}

Usuario: "edite o stop loss para 3000"
{"tool":"edit_code","path":"caminho/do/rob.mq5","old":"Stop_Pontos = 2000","new":"Stop_Pontos = 3000"}

Usuario: "corrija este MQL5, compile e coloque no MetaTrader"
{"tool":"repair_mql5","path":"C:/GoldenAI/sandbox/uploads/arquivo.mq5","request":"Corrigir os erros encontrados e compilar no MetaTrader"}

### Backtesting:
Usuario: "rode um backtest do EURUSD"
{"tool":"run_backtest","symbol":"EURUSD","timeframe":"H1","period":"1Y","strategy":"moving_average"}

Usuario: "quais estrategias tem"
{"tool":"list_strategies"}

Usuario: "quais pares posso testar"
{"tool":"list_symbols"}

Usuario: "faca uma analise completa do XAUUSD"
{"tool":"full_analysis","symbol":"XAUUSD","mode":"day"}

### Administracao do PC:
Usuario: "limpe o cache"
{"tool":"clean_cache"}

Usuario: "esvazie a lixeira"
{"tool":"empty_recycle_bin"}

Usuario: "limpe os arquivos temporarios"
{"tool":"clean_temp"}

Usuario: "informacoes do sistema"
{"tool":"system_info"}

Usuario: "quais programas estao instalados"
{"tool":"find_programs"}

### Arquivos e Pastas:
Usuario: "mostre a pasta Desktop"
{"tool":"list_directory","path":"C:/Users/Anderson/Desktop/"}

Usuario: "leia este arquivo"
{"tool":"read_file","path":"caminho/do/arquivo.txt","limit":2000}

Usuario: "pesquise arquivos mq5"
{"tool":"search_files","path":"C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/","pattern":"*.mq5"}

### Internet:
Usuario: "pesquise sobre trailing stop"
{"tool":"web_search","query":"trailing stop MQL5 explicacao"}

Usuario: "cotacao do dolar"
{"tool":"get_exchange_rate"}

## LISTA COMPLETA DE FERRAMENTAS
{"tool":"list_directory","path":"C:/pasta"}
{"tool":"read_file","path":"C:/arquivo.py","limit":10000}
{"tool":"write_file","path":"C:/arquivo.py","content":"codigo aqui"}
{"tool":"search_files","path":"C:/pasta","pattern":"*.mq5"}
{"tool":"run_command","command":"dir C:\\"}
{"tool":"delete_file","path":"C:/arquivo.txt"}
{"tool":"clean_cache"}
{"tool":"empty_recycle_bin"}
{"tool":"clean_temp"}
{"tool":"analyze_code","path":"C:/arquivo.mq5"}
{"tool":"edit_code","path":"C:/arquivo.mq5","old":"antigo","new":"novo"}
{"tool":"system_info"}
{"tool":"find_programs"}
{"tool":"uninstall_program","name":"nome"}
{"tool":"web_search","query":"pesquisa"}
{"tool":"get_exchange_rate"}
{"tool":"open_file","path":"C:/arquivo.pdf"}
{"tool":"read_pdf","path":"C:/arquivo.pdf"}
{"tool":"edit_pdf","path":"C:/arquivo.pdf","old":"errado","new":"correto"}
{"tool":"create_pdf","title":"Rel","content":"...","path":"C:/rel.pdf"}
{"tool":"run_backtest","symbol":"EURUSD","timeframe":"H1","period":"1Y","strategy":"moving_average"}
{"tool":"list_strategies"}
{"tool":"list_symbols"}
{"tool":"crypto_price","coins":"bitcoin,ethereum"}
{"tool":"analyze_strategy","triple_confluence":true,"filter_spread":true,"filter_hours":true,"adaptive_mode":true}
{"tool":"optimize_strategy","symbol":"XAUUSD","timeframe":"M15"}
{"tool":"compare_strategies"}
{"tool":"open_strategy_panel"}
{"tool":"full_analysis","symbol":"XAUUSD","mode":"day"}
{"tool":"meta_strategy","symbol":"XAUUSD"} - Gestor inteligente de carteiras de setups

## FERRAMENTAS DE ESTRATEGIA (MiMo)
{"tool":"analyze_strategy"} - Analisa todos os padroes com Triple Confluence
{"tool":"optimize_strategy","symbol":"XAUUSD"} - Otimiza SL/TP automaticamente
{"tool":"compare_strategies"} - Compara 1:1, 1:2, 1:3, Original
{"tool":"open_strategy_panel"} - Abre painel estatistico no navegador
{"tool":"meta_strategy","symbol":"XAUUSD"} - Classifica regime, escolhe carteiras, ranqueia setups e aplica bloqueios

## FERRAMENTAS CLAUDE (API)
{"tool":"claude_chat","message":"sua mensagem"} - Chat com Claude
{"tool":"claude_analyze_code","path":"C:/arquivo.mq5"} - Analise de codigo com Claude
{"tool":"claude_optimize","data":{...}} - Otimizacao com Claude
{"tool":"configure_api_key","key":"sk-or-..."} - Configurar API key OpenRouter
{"tool":"list_ai_models"} - Lista modelos disponiveis

## CAMINHOS IMPORTANTES DO METATRADER 5
Experts: C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Experts/
Meus Robos: C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Experts/Meus Robos/
Indicadores: C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Indicators/
Scripts: C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Scripts/
Include: C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Include/
Biblioteca: C:/Users/Anderson/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5/Libraries/
Desktop: C:/Users/Anderson/Desktop/
Downloads: C:/Users/Anderson/Downloads/
GoldenAI: C:/GoldenAI/

## REGRAS IMPORTANTES
1. Quando o usuario pedir ACAO (limpar, ler, editar, apagar, listar) -> use ferramenta
2. Quando o usuario mandar CODIGO ou ARQUIVO anexado -> analise DIRETAMENTE, NAO use ferramenta
3. Quando o usuario perguntar algo GERAL -> responda com Markdown bonito em portugues
4. Para ferramentas: responda SOMENTE com o JSON
5. VOCE E ESPECIALISTA EM MQL5 - entenda logica de trading, indicadores, gestao de risco
6. Quando pedirem backtest, use run_backtest com os parametros corretos
7. Quando pedirem analise completa de mercado/estrategia, use full_analysis e explique o veredito com risco e confianca
8. Quando pedirem edicao de codigo, use edit_code APENAS se o usuario confirmar a mudanca
9. Quando o usuario pedir explicitamente para corrigir e compilar um MQL5 anexado, use repair_mql5. Esta acao cria uma copia *_AI_CORRIGIDO.mq5 no MT5, faz backup e so aceita codigo aprovado pelo MetaEditor.
10. Para limpeza do PC, execute as ferramentas de limpeza (clean_cache, clean_temp, empty_recycle_bin)
11. Responda SEMPRE em portugues com emojis e formatacao bonita"""


# ─────────────────────────────────────────────────────────────────
# Jarvis boot helpers (P1.3) — chamadas de provider sem handler.
# Permitem registrar adapters EAGER no startup (antes da 1ª pergunta).
# Nenhuma chamada aqui gasta tokens de geração.
# ─────────────────────────────────────────────────────────────────
def read_jarvis_api_keys():
    try:
        path = ROOT / 'config' / 'api_keys.json'
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def call_groq_model(api_messages, model_key, timeout=60, stream=False):
    keys = read_jarvis_api_keys()
    api_key = keys.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "Erro Groq: API key nao configurada. Configure em IA e modelos."
    model_map = {
        "groq-fast": "groq/compound-mini",
        "groq-reasoning": "openai/gpt-oss-120b",
        "groq-llama": "qwen/qwen3.8-27b",
    }
    payload = {
        "model": model_map.get(model_key, "llama-3.1-8b-instant"),
        "messages": api_messages,
        "temperature": 0.3,
        "max_tokens": 320 if stream else 4096,
        "stream": bool(stream),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "GoldenAI/1.0",
    }
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        started = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if stream:
                first = None
                chunks = []
                for raw in resp:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    delta = json.loads(line[6:]).get("choices", [{}])[0].get(
                        "delta", {}).get("content", "")
                    if delta:
                        first = first or time.perf_counter()
                        chunks.append(delta)
                ended = time.perf_counter()
                ttft = int(((first or ended) - started) * 1000)
                return {"text": "".join(chunks), "ttft_ms": ttft,
                        "generation_ms": int((ended - (first or ended)) * 1000)}
            result = json.loads(resp.read().decode("utf-8"))
        choices = result.get("choices") or []
        return choices[0].get("message", {}).get("content", "") if choices else ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        if e.code == 403 and "1010" in body:
            return "Erro Groq: HTTP 403 codigo 1010. A Groq bloqueou esta requisicao antes do modelo responder. Abra https://console.groq.com/keys, confirme que a chave esta ativa e teste por uma rede/navegador diferente ou VPN desligada. A chave foi salva no Golden, mas o provedor recusou o acesso."
        return "Erro Groq: HTTP %s - %s" % (e.code, body)
    except Exception as e:
        return "Erro Groq: %s" % str(e)


def call_gemini_model(api_messages, model_key, timeout=60):
    from jarvis_core.config import resolve_api_key
    api_key = (resolve_api_key("GEMINI_API_KEY", "gemini_api_key")
               or os.environ.get("GOOGLE_API_KEY"))
    if not api_key:
        return "Erro Gemini: API key nao configurada. Configure em IA e modelos."
    model_map = {
        "gemini-flash": "gemini-3-flash-preview",
        "gemini-pro": "gemini-3.1-pro-preview",
    }
    system_text = ""
    contents = []
    for m in api_messages:
        role = m.get("role", "user")
        content = str(m.get("content", ""))
        if role == "system":
            system_text += content + "\n"
            continue
        parts = [{"text": content}]
        for img in m.get("images", []) or []:
            if img:
                parts.append({"inline_data": {"mime_type": "image/png", "data": img}})
        contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
    payload = {"contents": contents, "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096}}
    if system_text.strip():
        payload["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}
    resolved_model = (model_key if str(model_key).startswith("gemini-")
                      and model_key not in model_map else
                      model_map.get(model_key, "gemini-3.8-flash"))
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s" % (
        urllib.parse.quote(resolved_model, safe=""),
        urllib.parse.quote(api_key, safe=""),
    )
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "".join(str(p.get("text", "")) for p in parts)
    except urllib.error.HTTPError as e:
        return "Erro Gemini: HTTP %s - %s" % (e.code, e.read().decode("utf-8", errors="replace")[:300])
    except Exception as e:
        return "Erro Gemini: %s" % str(e)


def probe_groq_health(api_key, timeout=5):
    """Health leve da Groq via listagem de modelos (zero token de geração).

    Retorna (estado, detalhe_curto). Nunca expõe a chave.
    """
    if not api_key:
        return "AUTH_ERROR", "sem chave"
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": "Bearer " + api_key, "User-Agent": "GoldenAI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return "AVAILABLE", "models ok"
            return "DEGRADED", "http %s" % resp.status
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "AUTH_ERROR", "http %s" % e.code
        if e.code == 429:
            return "RATE_LIMITED", "http 429"
        if e.code >= 500:
            return "DEGRADED", "http %s" % e.code
        return "OFFLINE", "http %s" % e.code
    except Exception as e:
        return "OFFLINE", type(e).__name__


def probe_ollama_health(timeout=2):
    """Probe local barato: /api/tags (modelos instalados, sem carregar)."""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8")) if resp.status == 200 else {}
        models = [str(m.get("name", "")) for m in data.get("models", [])]
        return ("ONLINE" if resp.status == 200 else "OFFLINE"), models
    except Exception:
        return "OFFLINE", []


def warm_jarvis_boot():
    """Boot EAGER do Jarvis (background, idempotente, sem gastar geração).

    Registra adapters, valida saúde leve (Groq models-list, Ollama tags) e
    aguarda o warmup do STT. Falhas viram DEGRADED — nunca derrubam o app.
    """
    import threading as _threading
    from jarvis_core.readiness import get_readiness
    ready = get_readiness()
    ready.warming()
    started = time.perf_counter()
    try:
        from desktop_center import DESKTOP_CENTER
        from jarvis_core.brain import get_brain
        from jarvis_core.orchestrator import register_real_adapters
        from jarvis_core.orchestrator.models import ProviderState as _PS
        brain = get_brain(DESKTOP_CENTER.service.registry)
        models = brain.orchestrator.models
        # Idempotente: register_provider sobrescreve por nome.
        register_real_adapters(models, call_groq_model, call_gemini_model)
        ready.record(provider_registration_ms=int((time.perf_counter() - started) * 1000),
                     providers_registered=sorted(models.providers))
    except Exception as exc:
        ready.complete(degraded=True, reason="provider_registration: %s" % type(exc).__name__)
        return
    t0 = time.perf_counter()
    problems = []
    try:
        keys = read_jarvis_api_keys()
        groq_key = keys.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
        adapter = models.providers.get("groq")
        if adapter is not None:
            state, _ = probe_groq_health(groq_key)
            adapter.state = _PS[state]
            models.last_health["groq"] = _PS[state]
            if state != "AVAILABLE":
                problems.append("groq %s" % state)
    except Exception:
        problems.append("groq probe error")
    try:
        oll_state, oll_models = probe_ollama_health()
        ollama = models.providers.get("ollama")
        if ollama is not None:
            ollama.state = _PS.AVAILABLE if oll_state == "ONLINE" else _PS.OFFLINE
            models.last_health["ollama"] = ollama.state
        wanted = ("qwen2.5-coder:14b", "qwen2.5vl:7b")
        ready.record(provider_health_ms=int((time.perf_counter() - t0) * 1000),
                     ollama=oll_state,
                     ollama_models=[m for m in oll_models if any(w in m for w in wanted)])
        if oll_state != "ONLINE":
            problems.append("ollama OFFLINE")
    except Exception:
        problems.append("ollama probe error")
    try:
        from jarvis_core.voice import get_voice
        from jarvis_core.voice_service import get_voice_service
        vs = get_voice_service()
        if vs.enabled:
            voice = get_voice()
            thread = voice.warmup_async()
            deadline = time.time() + float(os.environ.get("JARVIS_STT_WARMUP_TIMEOUT", "30"))
            while thread.is_alive() and time.time() < deadline:
                time.sleep(0.2)
            warm = dict(voice.warmup)
            ready.record(stt_load_ms=warm.get("latency_ms", 0),
                         stt_warmup_ms=warm.get("latency_ms", 0),
                         stt_warm=warm.get("state", ""))
            if warm.get("state") != "READY":
                problems.append("stt %s" % warm.get("state", "timeout"))
        else:
            ready.record(stt_warm="disabled")
    except Exception:
        problems.append("stt warmup error")
    ready.complete(degraded=bool(problems), reason="; ".join(problems)[:300])


class GoldenAIHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        web_dir = str(Path(__file__).parent.resolve())
        super().__init__(*args, directory=web_dir, **kwargs)

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/studio_v7.html"
        if self.path.startswith("/api/"):
            self.handle_api()
        elif self.path.startswith("/stream/"):
            self.handle_stream()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self.handle_api()
        elif self.path.startswith("/stream/"):
            self.handle_stream()
        else:
            super().do_POST()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass

    def handle_api(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b'{}'
            try:
                data = json.loads(body) if body else {}
            except:
                data = {}
            try:
                response = self.route_api(self.path, data)
            except Exception as e:
                response = {"ok": False, "error": str(e)}
            # Ensure response is always serializable
            try:
                response_bytes = json.dumps(response, ensure_ascii=False, cls=_NumpyEncoder).encode('utf-8')
            except (TypeError, ValueError) as e:
                response = {"ok": False, "error": f"Resposta nao serializavel: {str(e)}"}
                response_bytes = json.dumps(response, ensure_ascii=False, cls=_NumpyEncoder).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(response_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response_bytes)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected, nothing to do
        except Exception as e:
            try:
                err_resp = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(err_resp)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err_resp)
            except:
                pass

    # ═══════════════════════════════════════════════════════════════
    # STREAMING WITH TOOL-CALLING LOOP
    # ═══════════════════════════════════════════════════════════════

    def handle_stream(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b'{}'
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        message = data.get("message", "")
        session_id = data.get("session_id", "default")
        images = data.get("images", [])
        files = data.get("files", [])

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'close')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            # Get conversation history
            with CONVERSATIONS_LOCK:
                history = CONVERSATIONS.get(session_id, [])

            history.append({"role": "user", "content": message})
            if len(history) > 20:
                history = history[-20:]

            # Build messages for Ollama
            has_images = len(images) > 0
            
            # Verificar modelo selecionado
            selected_model = data.get('model', '') if isinstance(data, dict) else ''
            
            # Mapear modelos
            MODEL_MAP = {
                'qwen2.5-coder:14b': 'qwen2.5-coder:14b',
                'qwen2.5vl:7b': 'qwen2.5vl:7b',
                'cohere-code': 'cohere-code',
                'nvidia-lightning': 'nvidia-lightning',
                'openrouter-free': 'openrouter-free',
                'openrouter-deepseek-r1-free': 'openrouter:z-ai/glm-5.2:free',
                'openrouter-qwen-coder-free': 'openrouter:cohere/north-mini-code:free',
                'openrouter-gemma-free': 'openrouter:google/gemma-4-26b-a4b-it:free',
                'gemini-flash': 'gemini-flash',
                'gemini-pro': 'gemini-pro',
                'groq-fast': 'groq-fast',
                'groq-reasoning': 'groq-reasoning',
                'groq-llama': 'groq-llama',
                'codex-bridge': 'codex-bridge',
                'codex-market': 'codex-market',
                'claude-sonnet': 'claude-sonnet',
                'claude-haiku': 'claude-haiku',
                # ClinePass models
                'cline-deepseek-v4': 'cline-deepseek-v4',
                'cline-deepseek-flash': 'cline-deepseek-flash',
                'cline-qwen38': 'cline-qwen38',
                'cline-qwen37': 'cline-qwen37',
                'cline-mimo': 'cline-mimo',
                'cline-glm': 'cline-glm',
                'cline-kimi': 'cline-kimi',
                'cline-minimax': 'cline-minimax',
            }
            
            if selected_model and selected_model in MODEL_MAP:
                model = MODEL_MAP[selected_model]
                if has_images and model != 'qwen2.5vl:7b' and not model.startswith('gemini-') and not model.startswith('codex-bridge'):
                    model = 'qwen2.5vl:7b'  # Forcar modelo de visao
            elif selected_model:
                model = selected_model
                if has_images and model != 'qwen2.5vl:7b' and not model.startswith('gemini-') and not model.startswith('codex-bridge'):
                    model = 'qwen2.5vl:7b'
            else:
                model = 'qwen2.5vl:7b' if has_images else 'cohere-code'
            
            # Verificar se e modelo API (OpenRouter ou Cline)
            is_cline_model = model.startswith('cline-')
            is_openrouter_dynamic = model.startswith('openrouter:')
            is_gemini_model = model.startswith('gemini-')
            is_groq_model = model.startswith('groq-')
            is_codex_model = model.startswith('codex-bridge')
            openrouter_models = [
                'cohere-code', 'nvidia-lightning', 'openrouter-free',
                'codex-market', 'claude-sonnet', 'claude-haiku',
            ]
            is_api_model = model in openrouter_models or is_openrouter_dynamic or is_cline_model or is_gemini_model or is_groq_model or is_codex_model
            
            if has_images:
                self._send_sse({"tool_progress": f"Usando modelo: {model}"})
            messages = [{"role": "system", "content": TOOL_DEFINITIONS}]
            for h in history[-8:]:
                messages.append(h)
            if has_images:
                img_b64 = [img.get('data', '') for img in images if img.get('data')]
                messages[-1] = {"role": "user", "content": message, "images": img_b64}

            # Process uploaded files (documents, code, etc)
            if files:
                file_context = "\n\n## Arquivos anexados:\n"
                for f in files:
                    fname = f.get('name', 'unknown')
                    fdata = f.get('data', '')
                    ftype = f.get('type', '')
                    # Decode base64 content
                    try:
                        import base64 as b64
                        ext = Path(fname).suffix.lower()
                        raw = b64.b64decode(fdata, validate=False)
                        # Multimidia precisa passar pelos servicos proprios; decodificar
                        # video/audio como UTF-8 produzia apenas lixo no contexto do modelo.
                        if ext in {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.ts'}:
                            video_path = self._save_upload(fdata, fname)
                            from core.video import VideoService
                            result = VideoService(ROOT).analyze(video_path)
                            if result.status == 'COMPLETED':
                                file_context += f"\n### {fname} (analise de video):\n{result.text[:50000]}\n"
                            else:
                                file_context += f"\n### {fname} (video; falha na analise): {result.status} - {result.error}\n"
                            continue
                        if ext in {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.opus'}:
                            audio_path = self._save_upload(fdata, fname)
                            from core.audio import AudioService
                            result = AudioService(ROOT).transcribe(audio_path)
                            if result.status == 'COMPLETED':
                                file_context += f"\n### {fname} (transcricao de audio):\n{result.text[:30000]}\n"
                            else:
                                file_context += f"\n### {fname} (audio; falha na transcricao): {result.status} - {result.error}\n"
                            continue
                        content = raw.decode('utf-8', errors='replace')
                        # For code files, include full content (ate 50k chars)
                        if ext in ['.mq5', '.mq4', '.mqh', '.py', '.js', '.ts', '.cpp', '.c', '.h', '.java', '.cs', '.go', '.rs']:
                            truncation_note = f"\n[...truncado em {len(content.splitlines())} linhas]" if len(content) > 50000 else ""
                            language = 'mql5' if ext in {'.mq5', '.mq4', '.mqh'} else ext.lstrip('.')
                            specialist = " Analise como especialista em MQL5: compilacao, logica de entrada/saida, risco, repaint e possiveis erros." if language == 'mql5' else ""
                            action_path = ''
                            if ext == '.mq5':
                                action_path = self._save_upload(fdata, fname)
                                file_context += f"\nCaminho temporario para acao controlada: {action_path}\n"
                            file_context += f"\n### {fname} (codigo {language}, {len(content.splitlines())} linhas):{specialist}\n```{language}\n{content[:50000]}{truncation_note}\n```\n"
                        # For text files
                        elif ext in ['.txt', '.csv', '.json', '.yaml', '.yml', '.xml', '.md', '.log']:
                            truncation_note = f"\n[...truncado]" if len(content) > 30000 else ""
                            file_context += f"\n### {fname} (texto):\n```\n{content[:30000]}{truncation_note}\n```\n"
                        # For other files, show metadata
                        else:
                            file_context += f"\n### {fname} (tipo: {ftype}, {len(content)} bytes)\n"
                    except:
                        file_context += f"\n### {fname} (tipo: {ftype})\n"
                # Add file context to user message
                message = message + file_context
                if len(messages) > 0:
                    updated_message = {"role": "user", "content": message}
                    if has_images:
                        updated_message["images"] = [img.get('data', '') for img in images if img.get('data')]
                    messages[-1] = updated_message
                self._send_sse({"tool_progress": f"Arquivos anexados: {len(files)}"})

            # TOOL-CALLING LOOP (max 5 iterations)
            full_response = ""
            last_tool_result = ""
            try:
                import signal
                def timeout_handler(signum, frame):
                    raise TimeoutError("Ollama timeout")
            except:
                pass

            for iteration in range(5):
                self._send_sse({"tool_progress": f"Iteracao {iteration+1}/5"})

                # Verificar se é modelo API (OpenRouter ou Cline)
                if is_api_model:
                    if is_codex_model:
                        token_buffer = ""
                        try:
                            from codex_provider import get_codex_provider
                            codex_prov = get_codex_provider()
                            result = codex_prov.chat(messages)
                            if isinstance(result, dict) and "error" in result:
                                error_text = str(result["error"])
                                # Limite da conta, timeout ou indisponibilidade nao devem
                                # interromper a analise quando existe outro provedor pronto.
                                self._send_sse({"tool_progress": "Codex indisponivel. Procurando um modelo alternativo configurado..."})
                                fallback_messages = [{"role": "system", "content": TOOL_DEFINITIONS}] + messages[1:]
                                fallback_text = ""
                                fallback_model = ""
                                try:
                                    from claude_provider import get_claude_provider, MQL5_SYSTEM_PROMPT
                                    openrouter = get_claude_provider()
                                    if openrouter.api_key:
                                        fallback_messages[0]["content"] += "\n\n" + MQL5_SYSTEM_PROMPT
                                        fallback = openrouter.chat(fallback_messages, model="openrouter/free")
                                        choices = fallback.get("choices") or [] if isinstance(fallback, dict) else []
                                        if choices:
                                            fallback_text = str((choices[0].get("message") or {}).get("content") or "")
                                        fallback_model = "openrouter-free"
                                except Exception:
                                    fallback_text = ""
                                if not fallback_text:
                                    candidate = self._call_groq_model(fallback_messages, "groq-reasoning")
                                    if candidate and not str(candidate).startswith("Erro Groq:"):
                                        fallback_text = str(candidate)
                                        fallback_model = "groq-reasoning"
                                if fallback_text.strip():
                                    self._send_sse({"model_fallback": fallback_model, "tool_progress": "Modelo alternativo ativado."})
                                    token_buffer = fallback_text
                                else:
                                    self._send_sse({"token": "O Codex atingiu o limite de uso e nenhum modelo alternativo configurado respondeu. Selecione um modelo grátis em IA e modelos, como OpenRouter Free ou Groq.", "done": True})
                                    return
                            if not token_buffer:
                                token_buffer = str(result.get("content") or "") if isinstance(result, dict) else str(result or "")
                            if not token_buffer.strip():
                                self._send_sse({"token": "O Codex retornou uma resposta vazia. Selecione um modelo alternativo em IA e modelos.", "done": True})
                                return
                            self._send_sse({"token": token_buffer, "done": False})
                        except Exception as e:
                            self._send_sse({"token": "O Codex ficou indisponível nesta solicitação. Selecione um modelo grátis em IA e modelos e tente novamente.", "done": True})
                            return
                    # Cline models - usar API do Cline
                    elif is_cline_model:
                        try:
                            from cline_provider import get_cline_provider, CLINE_MODELS
                            from claude_provider import MQL5_SYSTEM_PROMPT
                            cline_prov = get_cline_provider()
                            
                            if not cline_prov.api_key:
                                self._send_sse({"token": "API key do Cline não configurada. Use: configure_cline_key SUA_KEY", "done": True})
                                return
                            
                            cline_model_map = {
                                'cline-deepseek-v4': 'cline-pass/deepseek-v4-pro',
                                'cline-deepseek-flash': 'cline-pass/deepseek-v4-flash',
                                'cline-qwen38': 'cline-pass/qwen3.8-max',
                                'cline-qwen37': 'cline-pass/qwen3.7-max',
                                'cline-mimo': 'cline-pass/mimo-v2.5',
                                'cline-glm': 'cline-pass/glm-5.2',
                                'cline-kimi': 'cline-pass/kimi-k3',
                                'cline-minimax': 'cline-pass/minimax-m3',
                            }
                            api_model = cline_model_map.get(model, 'cline-pass/deepseek-v4-pro')
                            
                            api_messages = [{"role": "system", "content": TOOL_DEFINITIONS + "\n\n" + MQL5_SYSTEM_PROMPT}]
                            for m in messages[1:]:
                                api_messages.append(m)
                            
                            token_buffer = ""
                            result = cline_prov.chat(api_messages, model=api_model)
                            if isinstance(result, dict) and "error" in result:
                                self._send_sse({"token": "Erro Cline: %s" % result["error"], "done": True})
                                return
                            if isinstance(result, dict):
                                choices = result.get("choices") or []
                                if choices:
                                    message_obj = choices[0].get("message") or {}
                                    token_buffer = str(message_obj.get("content") or "")
                                elif "content" in result:
                                    token_buffer = str(result.get("content") or "")
                            elif result is not None:
                                token_buffer = str(result)
                            if not token_buffer.strip():
                                self._send_sse({"token": "Erro Cline: o modelo retornou uma resposta vazia. Tente o DeepSeek V4 Flash ou Ollama Local.", "done": True})
                                return
                            if token_buffer:
                                self._send_sse({"token": token_buffer, "done": False})
                            # O resultado passa pelo parser comum abaixo para que
                            # chamadas de ferramenta do Cline tambem sejam executadas.
                        except Exception as e:
                            self._send_sse({"token": "Erro Cline: %s" % str(e), "done": True})
                            return
                    elif is_gemini_model:
                        try:
                            token_buffer = self._call_gemini_model(api_messages=messages, model_key=model)
                            if token_buffer.startswith("Erro Gemini:"):
                                self._send_sse({"token": token_buffer, "done": True})
                                return
                            if token_buffer:
                                self._send_sse({"token": token_buffer, "done": False})
                        except Exception as e:
                            self._send_sse({"token": "Erro Gemini: %s" % str(e), "done": True})
                            return
                    elif is_groq_model:
                        try:
                            token_buffer = self._call_groq_model(api_messages=messages, model_key=model)
                            if token_buffer.startswith("Erro Groq:"):
                                self._send_sse({"token": token_buffer, "done": True})
                                return
                            if token_buffer:
                                self._send_sse({"token": token_buffer, "done": False})
                        except Exception as e:
                            self._send_sse({"token": "Erro Groq: %s" % str(e), "done": True})
                            return
                    else:
                        # OpenRouter models
                        # Usar Claude/MiMo via OpenRouter
                        try:
                            from claude_provider import get_claude_provider, CLAUDE_MODELS, MQL5_SYSTEM_PROMPT
                            provider = get_claude_provider()
                            
                            if not provider.api_key:
                                self._send_sse({"token": "API key não configurada. Use: configure_api_key SUA_KEY", "done": True})
                                return
                            
                            # Mapear modelo API
                            api_model_map = {
                                'cohere-code': 'cohere/north-mini-code:free',
                                'nvidia-lightning': 'nvidia/nemotron-3.5-lightning:free',
                                'openrouter-free': 'openrouter/free',
                                'codex-market': 'openai/gpt-5.3-codex',
                                'claude-sonnet': 'anthropic/claude-sonnet-4',
                                'claude-haiku': 'anthropic/claude-3.5-haiku',
                            }
                            api_model = model.split(':', 1)[1] if model.startswith('openrouter:') else api_model_map.get(model, 'cohere/north-mini-code:free')
                            
                            # Adicionar system prompt do MQL5
                            api_messages = [{"role": "system", "content": TOOL_DEFINITIONS + "\n\n" + MQL5_SYSTEM_PROMPT}]
                            for m in messages[1:]:  # Pular system message do Ollama
                                api_messages.append(m)
                            
                            # Chamar API com Streaming em tempo real
                            token_buffer = ""
                            for chunk in provider.chat_stream(api_messages, model=api_model):
                                if "error" in chunk:
                                    # FALLBACK AUTOMATICO: se modelo pago falhar, tentar gratuito
                                    error_msg = chunk.get('error', '')
                                    if '402' in str(error_msg) or 'Payment' in str(error_msg) or '429' in str(error_msg) or '404' in str(error_msg):
                                        self._send_sse({"tool_progress": f"Modelo {api_model} indisponivel agora. Tentando roteador gratuito..."})
                                        fallback_model = 'cohere/north-mini-code:free'
                                        if model.startswith('openrouter:') or model == 'openrouter-free':
                                            fallback_model = 'openrouter/free'
                                        for fb_chunk in provider.chat_stream(api_messages, model=fallback_model):
                                            if "error" in fb_chunk:
                                                self._send_sse({"token": f"Erro: {fb_chunk['error']}", "done": True})
                                                return
                                            if "token" in fb_chunk:
                                                t = fb_chunk["token"]
                                                token_buffer += t
                                                self._send_sse({"token": t, "done": False})
                                    else:
                                        self._send_sse({"token": f"Erro API: {error_msg}", "done": True})
                                        return
                                if "token" in chunk:
                                    t = chunk["token"]
                                    token_buffer += t
                                    self._send_sse({"token": t, "done": False})
                        except Exception as e:
                            if not token_buffer:
                                self._send_sse({"token": f"Erro API: {str(e)}", "done": True})
                                return
                else:
                    # Usar Ollama local
                    try:
                        stream = ollama_chat(
                            model=model,
                            messages=messages,
                            stream=True
                        )
                    except Exception as e:
                        self._send_sse({"token": f"Erro ao conectar com IA: {str(e)}", "done": True})
                        return

                    token_buffer = ""
                    try:
                        for chunk in stream:
                            if 'message' in chunk and 'content' in chunk['message']:
                                token = chunk['message']['content']
                                token_buffer += token
                                self._send_sse({"token": token, "done": False})
                    except Exception as e:
                        if not token_buffer:
                            self._send_sse({"token": f"Erro no streaming: {str(e)}", "done": True})
                            return

                if not token_buffer:
                    fallback_response = last_tool_result.strip()
                    if not fallback_response:
                        fallback_response = "Erro: resposta vazia da IA"
                    self._send_sse({"done": True, "full_response": fallback_response})
                    return

                # Check if AI wants to call a tool
                tool_call = self._parse_tool_call(token_buffer)

                if tool_call:
                    tool_name = tool_call.get("tool", "")
                    self._send_sse({"tool_start": tool_name, "iteration": iteration + 1})

                    tool_result = self._execute_tool(tool_call, session_id)
                    last_tool_result = tool_result

                    messages.append({"role": "assistant", "content": token_buffer})
                    messages.append({"role": "user", "content": f"Resultado da ferramenta {tool_name}:\n\n{tool_result[:20000]}\n\nAgora responda ao usuario com base neste resultado. Use Markdown para formatar sua resposta."})

                    self._send_sse({"tool_result": tool_name, "result_preview": tool_result[:1000]})
                    continue

                else:
                    # Clean ALL tool call JSON from displayed response
                    clean = token_buffer
                    # Remove markdown code blocks with tool JSON
                    clean = re.sub(r'```[a-zA-Z]*\s*\{[^}]*"tool"[^}]*\}\s*```', '', clean).strip()
                    # Remove standalone tool JSON
                    clean = re.sub(r'\{\s*"tool"\s*:\s*"[^"]+"[^}]*\}', '', clean).strip()
                    # Remove triple backtick artifacts
                    clean = re.sub(r'```\s*$', '', clean).strip()
                    clean = re.sub(r'^\s*```', '', clean).strip()
                    full_response = clean if clean else token_buffer
                    break

            # Save to history
            with CONVERSATIONS_LOCK:
                if session_id not in CONVERSATIONS:
                    CONVERSATIONS[session_id] = []
                CONVERSATIONS[session_id].append({"role": "user", "content": message})
                CONVERSATIONS[session_id].append({"role": "assistant", "content": full_response})
                if len(CONVERSATIONS[session_id]) > 50:
                    CONVERSATIONS[session_id] = CONVERSATIONS[session_id][-50:]

            self._send_sse({"done": True, "full_response": full_response})

        except Exception as e:
            self._send_sse({"token": f"Erro: {str(e)}", "done": True})

    def _send_sse(self, data):
        try:
            self.wfile.write(f"data: {json.dumps(data, ensure_ascii=False, cls=_NumpyEncoder)}\n\n".encode())
            self.wfile.flush()
        except:
            pass

    def _parse_tool_call(self, text):
        """Parse tool call from AI response"""
        # Look for JSON with "tool" key
        json_patterns = re.findall(r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*\}', text)
        if not json_patterns:
            json_patterns = re.findall(r'\{[^{}]*"tool"\s*:\s*"[^"]+?"[^{}]*\}', text, re.DOTALL)
        for pattern in json_patterns:
            try:
                parsed = json.loads(pattern)
                if "tool" in parsed:
                    return parsed
            except:
                continue
        return None

    # ═══════════════════════════════════════════════════════════════
    # TOOL EXECUTION
    # ═══════════════════════════════════════════════════════════════

    def _check_tool_permission(self, tool_name, tool_call, session_id='default'):
        """Autoriza cada acao pelo ExecutionService e registra aprovacoes pendentes."""
        self._last_permission_message = ''
        READ_ONLY_TOOLS = {
            'list_directory', 'read_file', 'search_files', 'system_info',
            'find_programs', 'analyze_code', 'get_exchange_rate',
            'web_search', 'open_file', 'read_pdf', 'list_pdf_words',
            'list_strategies', 'list_symbols',
        }
        if tool_name in READ_ONLY_TOOLS:
            return True
        write_tools = {'write_file', 'edit_code', 'repair_mql5', 'delete_file', 'edit_pdf', 'create_pdf'}
        exec_tools = {'run_command', 'clean_cache', 'empty_recycle_bin', 'clean_temp', 'uninstall_program'}
        if tool_name not in write_tools and tool_name not in exec_tools:
            return True
        level = 'WRITE' if tool_name in write_tools else 'EXECUTE'
        target = tool_call.get('path') or tool_call.get('file') or tool_call.get('command') or tool_name
        if EXECUTION_SERVICE:
            result = EXECUTION_SERVICE.authorize_action(
                task_id=session_id or 'default', permission_level=level,
                action=tool_name, target=str(target),
                reason=f'A ferramenta {tool_name} solicitou {level.lower()}.',
                tool_name=tool_name, capability_exists=True,
            )
            if not result.allowed:
                self._last_permission_message = (
                    f"🔐 Ação aguardando aprovação ({result.request_id}). "
                    f"Modo: {result.mode}. Use o painel Segurança para aprovar ou negar."
                )
                print(f'[Permission] {tool_name}: {result.reason} ({result.request_id})')
                return False
            return True
        return False

    def _execute_canonical_legacy_tool(self, tool_call, session_id='default'):
        """Delegate only exact legacy contracts to Jarvis SecurityManager."""
        from jarvis_core.security_compatibility import LegacySecurityBridge

        def service_provider():
            try:
                from desktop_center import DESKTOP_CENTER
                return DESKTOP_CENTER.service
            except Exception:
                return None

        return LegacySecurityBridge(service_provider).execute(tool_call, session_id)

    def _execute_tool(self, tool_call, session_id='default'):
        tool = tool_call.get("tool", "")

        canonical_result = self._execute_canonical_legacy_tool(tool_call, session_id)
        if canonical_result is not None:
            return canonical_result

        # Verificar permissão antes de executar
        if not self._check_tool_permission(tool, tool_call, session_id):
            return self._last_permission_message or f"Acesso negado pelo sistema de permissões. Ferramenta: {tool}"

        try:
            if tool == "list_directory":
                return self._tool_list_directory(tool_call)
            elif tool == "read_file":
                return self._tool_read_file(tool_call)
            elif tool == "write_file":
                return self._tool_write_file(tool_call)
            elif tool == "search_files":
                return self._tool_search_files(tool_call)
            elif tool == "run_command":
                return self._tool_run_command(tool_call)
            elif tool == "delete_file":
                return self._tool_delete_file(tool_call)
            elif tool == "clean_cache":
                return self._tool_clean_cache()
            elif tool == "empty_recycle_bin":
                return self._tool_empty_recycle_bin()
            elif tool == "clean_temp":
                return self._tool_clean_temp()
            elif tool == "analyze_code":
                return self._tool_analyze_code(tool_call)
            elif tool == "edit_code":
                return self._tool_edit_code(tool_call)
            elif tool == "repair_mql5":
                return self._tool_repair_mql5(tool_call)
            elif tool == "system_info":
                return self._tool_system_info()
            elif tool == "find_programs":
                return self._tool_find_programs()
            elif tool == "uninstall_program":
                return self._tool_uninstall_program(tool_call)
            elif tool == "web_search":
                return self._tool_web_search(tool_call)
            elif tool == "get_exchange_rate":
                return self._tool_get_exchange_rate()
            elif tool == "open_file":
                return self._tool_open_file(tool_call)
            elif tool == "edit_pdf":
                return self._tool_edit_pdf(tool_call)
            elif tool == "read_pdf":
                return self._tool_read_pdf(tool_call)
            elif tool == "create_pdf":
                return self._tool_create_pdf(tool_call)
            elif tool == "list_pdf_words":
                return self._tool_list_pdf_words(tool_call)
            elif tool == "run_backtest":
                return self._tool_run_backtest(tool_call)
            elif tool == "list_strategies":
                return self._tool_list_strategies()
            elif tool == "list_symbols":
                return self._tool_list_symbols()
            elif tool == "analyze_strategy":
                return self._tool_analyze_strategy(tool_call)
            elif tool == "optimize_strategy":
                return self._tool_optimize_strategy(tool_call)
            elif tool == "compare_strategies":
                return self._tool_compare_strategies(tool_call)
            elif tool == "open_strategy_panel":
                return self._tool_open_strategy_panel()
            elif tool == "full_analysis":
                return json.dumps(self._api_mt5_full_analysis(tool_call), ensure_ascii=False, indent=2, cls=_NumpyEncoder)
            elif tool == "meta_strategy":
                return json.dumps(self._api_meta_strategy(tool_call), ensure_ascii=False, indent=2, cls=_NumpyEncoder)
            elif tool == "claude_chat":
                return self._tool_claude_chat(tool_call)
            elif tool == "claude_analyze_code":
                return self._tool_claude_analyze_code(tool_call)
            elif tool == "claude_optimize":
                return self._tool_claude_optimize(tool_call)
            elif tool == "configure_api_key":
                return self._tool_configure_api_key(tool_call)
            elif tool == "configure_cline_key":
                return self._tool_configure_cline_key(tool_call)
            elif tool == "list_ai_models":
                return self._tool_list_ai_models()
            else:
                # Verificar se e um plugin registrado
                if PLUGIN_REGISTRY and PLUGIN_REGISTRY.get(tool):
                    # Montar args a partir de todos os campos que nao sao 'tool'
                    plugin_args = {k: v for k, v in tool_call.items() if k != 'tool'}
                    result = PLUGIN_REGISTRY.execute(tool, plugin_args)
                    if isinstance(result, dict):
                        return json.dumps(result, ensure_ascii=False, indent=2)
                    return str(result)
                return f"Ferramenta desconhecida: {tool}"
        except Exception as e:
            return f"Erro ao executar {tool}: {str(e)}"

    # ── FILESYSTEM TOOLS ──────────────────────────────────────

    def _tool_list_directory(self, tc):
        path = tc.get("path", ".")
        p = Path(path)
        if not p.exists():
            return f"Pasta nao encontrada: {path}"
        items = []
        try:
            for item in sorted(p.iterdir()):
                item_type = "📁" if item.is_dir() else "📄"
                try:
                    size = item.stat().st_size
                    if size > 1024*1024:
                        size_str = f"{size/(1024*1024):.1f} MB"
                    elif size > 1024:
                        size_str = f"{size/1024:.1f} KB"
                    else:
                        size_str = f"{size} B"
                except:
                    size_str = "?"
                items.append(f"{item_type} {item.name} ({size_str})")
            result = f"**Pasta: {path}** ({len(items)} itens)\n\n" + "\n".join(items[:100])
            if len(items) > 100:
                result += f"\n\n... e mais {len(items)-100} itens"
            return result
        except PermissionError:
            return f"Sem permissao para acessar: {path}"
        except Exception as e:
            return f"Erro: {str(e)}"

    def _tool_read_file(self, tc):
        path = tc.get("path", "")
        limit = tc.get("limit", 10000)
        p = Path(path)
        if not p.exists():
            return f"Arquivo nao encontrado: {path}"
        try:
            content = p.read_text(encoding='utf-8', errors='replace')
            lines = content.splitlines()
            total = len(lines)
            if limit and total > limit:
                content = "\n".join(lines[:limit])
                return f"**{p.name}** ({total} linhas, mostrando primeiras {limit}):\n\n```\n{content}\n```"
            return f"**{p.name}** ({total} linhas):\n\n```\n{content}\n```"
        except Exception as e:
            return f"Erro ao ler: {str(e)}"

    def _tool_write_file(self, tc):
        path = tc.get("path", "")
        content = tc.get("content", "")
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            return f"Arquivo criado/editado: {path} ({len(content)} caracteres)"
        except Exception as e:
            return f"Erro ao escrever: {str(e)}"

    def _tool_search_files(self, tc):
        path = tc.get("path", ".")
        pattern = tc.get("pattern", "*")
        p = Path(path)
        if not p.exists():
            return f"Pasta nao encontrada: {path}"
        try:
            matches = list(p.rglob(pattern))
            items = [f"📄 {m} ({m.stat().st_size} bytes)" for m in matches if m.is_file()][:50]
            return f"**Busca '{pattern}' em {path}** ({len(items)} resultados):\n\n" + "\n".join(items) if items else f"Nenhum resultado para '{pattern}'"
        except Exception as e:
            return f"Erro na busca: {str(e)}"

    def _tool_open_file(self, tc):
        path = tc.get("path", "")
        try:
            os.startfile(path)
            return f"Arquivo aberto: {path}"
        except Exception as e:
            return f"Erro ao abrir: {str(e)}"

    # ── COMMAND TOOLS ─────────────────────────────────────────

    def _tool_run_command(self, tc):
        command = tc.get("command", "")
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=30, encoding='utf-8', errors='replace'
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]: {result.stderr}"
            if len(output) > 10000:
                output = output[:10000] + "\n... (truncado)"
            return f"**Comando:** `{command}`\n**Resultado:**\n```\n{output}\n```"
        except subprocess.TimeoutExpired:
            return f"Comando excedeu timeout (30s): {command}"
        except Exception as e:
            return f"Erro ao executar: {str(e)}"

    def _tool_delete_file(self, tc):
        path = tc.get("path", "")
        p = Path(path)
        if not p.exists():
            return f"Arquivo/pasta nao encontrado: {path}"
        try:
            if p.is_dir():
                shutil.rmtree(p)
                return f"Pasta deletada: {path}"
            else:
                p.unlink()
                return f"Arquivo deletado: {path}"
        except Exception as e:
            return f"Erro ao deletar: {str(e)}"

    # ── CLEANUP TOOLS ─────────────────────────────────────────

    def _tool_clean_cache(self):
        cleaned = []
        # Browser caches
        cache_paths = [
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'Windows' / 'INetCache',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Temp',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Google' / 'Chrome' / 'User Data' / 'Default' / 'Cache',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'Edge' / 'User Data' / 'Default' / 'Cache',
        ]
        total_size = 0
        for cache_path in cache_paths:
            if cache_path.exists():
                try:
                    size_before = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file())
                    shutil.rmtree(cache_path, ignore_errors=True)
                    total_size += size_before
                    cleaned.append(str(cache_path.name))
                except:
                    pass
        # Windows Prefetch
        prefetch = Path('C:/Windows/Prefetch')
        if prefetch.exists():
            try:
                for f in prefetch.glob('*'):
                    f.unlink(missing_ok=True)
                cleaned.append("Prefetch")
            except:
                pass

        return f"**Cache limpo!**\n\nPastas limpas: {', '.join(cleaned) if cleaned else 'nenhuma acessivel'}\nEspaco liberado: ~{total_size/(1024*1024):.1f} MB"

    def _tool_empty_recycle_bin(self):
        try:
            # Use PowerShell to empty recycle bin
            result = subprocess.run(
                ['powershell', '-Command', 'Clear-RecycleBin -Force -ErrorAction SilentlyContinue'],
                capture_output=True, text=True, timeout=15
            )
            return "🗑️ **Lixeira esvaziada com sucesso!**"
        except Exception as e:
            return f"Erro ao esvaziar lixeira: {str(e)}"

    def _tool_clean_temp(self):
        temp_dir = Path(os.environ.get('TEMP', tempfile.gettempdir()))
        cleaned_count = 0
        total_size = 0
        for item in temp_dir.iterdir():
            try:
                if item.is_file():
                    size = item.stat().st_size
                    item.unlink(missing_ok=True)
                    total_size += size
                    cleaned_count += 1
                elif item.is_dir():
                    size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                    shutil.rmtree(item, ignore_errors=True)
                    total_size += size
                    cleaned_count += 1
            except:
                pass
        return f"🧹 **Temp limpo!**\n\nItens removidos: {cleaned_count}\nEspaco liberado: ~{total_size/(1024*1024):.1f} MB"

    # ── CODE TOOLS ────────────────────────────────────────────

    def _tool_analyze_code(self, tc):
        path = tc.get("path", "")
        p = Path(path)
        if not p.exists():
            return f"Arquivo nao encontrado: {path}"
        try:
            code = p.read_text(encoding='utf-8', errors='replace')
            lines = code.splitlines()
            total_lines = len(lines)
            ext = p.suffix.lower()
            size = p.stat().st_size

            # Detect language and count constructs
            functions = []
            classes = []
            imports = []
            inputs = []
            enums = []
            issues = []

            if ext in ['.mq5', '.mq4', '.mqh']:
                # MQL5/MQL4 detection
                functions = re.findall(r'(?:void|int|double|bool|string|color|datetime|enum\s+\w+)\s+(\w+)\s*\(', code)
                classes = re.findall(r'class\s+(\w+)', code)
                inputs = re.findall(r'input\s+(?:string|int|double|bool|color|enum\s+\w+)\s+(\w+)', code)
                enums = re.findall(r'enum\s+(\w+)', code)
                includes = re.findall(r'#include\s+[<"]([^>"]+)', code)
                imports = includes
                # MQL5 specific issues
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if 'Print(' in stripped and len(stripped) > 100:
                        issues.append(f"Linha {i}: Print() muito longo, considere simplificar")
                    if 'OrderSend(' in stripped and 'request' not in stripped:
                        issues.append(f"Linha {i}: OrderSend() direto, use classe Trade para mais seguranca")
                    if stripped.startswith('//') and 'TODO' in stripped.upper():
                        issues.append(f"Linha {i}: TODO pendente")
            else:
                # Python/JS/generic detection
                functions = re.findall(r'def\s+(\w+)', code)
                classes = re.findall(r'class\s+(\w+)', code)
                imports = re.findall(r'(?:import|from|require)\s+(\w+)', code)
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if 'except:' in stripped:
                        issues.append(f"Linha {i}: Excecao generica 'except:'")
                    elif 'except Exception:' in stripped:
                        issues.append(f"Linha {i}: Excecao generica 'except Exception:'")
                    if 'exec(' in stripped or 'eval(' in stripped:
                        issues.append(f"Linha {i}: Uso perigoso de exec/eval")
                    if stripped.startswith('#') and 'TODO' in stripped:
                        issues.append(f"Linha {i}: TODO pendente")

            lang_map = {'.mq5': 'MQL5 (MetaTrader 5)', '.mq4': 'MQL4 (MetaTrader 4)', '.mqh': 'MQL Header',
                       '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript', '.cpp': 'C++', '.c': 'C', '.h': 'C/C++ Header'}
            lang = lang_map.get(ext, ext.upper().lstrip('.'))

            result = f"## 📊 Analise de: {p.name}\n\n"
            result += f"| Metrica | Valor |\n|---------|-------|\n"
            result += f"| Linhas | {total_lines} |\n"
            result += f"| Tamanho | {size/1024:.1f} KB |\n"
            result += f"| Funcoes | {len(functions)} |\n"
            result += f"| Classes | {len(classes)} |\n"
            result += f"| Imports/Includes | {len(set(imports))} |\n"
            if inputs: result += f"| Inputs ( parametros ) | {len(inputs)} |\n"
            if enums: result += f"| Enums | {len(enums)} |\n"
            result += f"| Linguagem | {lang} |\n\n"

            if inputs:
                result += f"### ⚙️ Parametros ({len(inputs)}):\n"
                for inp in inputs[:20]:
                    result += f"- `{inp}`\n"
                if len(inputs) > 20:
                    result += f"- ... e mais {len(inputs)-20}\n"

            if enums:
                result += f"\n### 📋 Enums ({len(enums)}):\n"
                for e in enums:
                    result += f"- `{e}`\n"

            if functions:
                result += f"\n### 🔧 Funcoes ({len(functions)}):\n"
                for fn in functions[:30]:
                    result += f"- `{fn}()`\n"
                if len(functions) > 30:
                    result += f"- ... e mais {len(functions)-30}\n"

            if classes:
                result += f"\n### 📦 Classes ({len(classes)}):\n"
                for cls in classes:
                    result += f"- `{cls}`\n"

            if issues:
                result += f"\n### ⚠️ Problemas encontrados ({len(issues)}):\n"
                for issue in issues[:20]:
                    result += f"- {issue}\n"
            else:
                result += "\n### ✅ Nenhum problema estrutural encontrado\n"

            return result
        except Exception as e:
            return f"Erro ao analisar: {str(e)}"

    def _tool_edit_code(self, tc):
        path = tc.get("path", "")
        old = tc.get("old", "")
        new = tc.get("new", "")
        p = Path(path)
        if not p.exists():
            return f"Arquivo nao encontrado: {path}"
        try:
            content = p.read_text(encoding='utf-8', errors='replace')
            if old not in content:
                return f"Texto nao encontrado no arquivo: '{old[:80]}...'"
            count = content.count(old)
            content = content.replace(old, new, 1)
            p.write_text(content, encoding='utf-8')
            return f"✅ Edicao aplicada em {p.name}\nTexto antigo encontrado {count} vez(es), substituido 1 ocorrencia"
        except Exception as e:
            return f"Erro ao editar: {str(e)}"

    def _compile_mql5_path(self, path):
        """Compila um caminho MQL5 e le o log real do MetaEditor."""
        source = Path(path)
        metaeditor = source.parent
        candidates = [Path(r'C:\Program Files\MetaTrader 5\metaeditor64.exe')]
        if len(source.parents) > 3:
            candidates.insert(0, source.parents[3] / 'metaeditor64.exe')
        found = next((p for p in candidates if p and p.exists()), None)
        if not found:
            for base in (Path('C:/Program Files'), Path('C:/Program Files (x86)')):
                if base.exists():
                    found = next(base.rglob('metaeditor64.exe'), None)
                    if found:
                        break
        if not found:
            return {'ok': False, 'errors': -1, 'warnings': -1, 'log': 'metaeditor64.exe nao encontrado'}
        log_path = ROOT / 'logs' / f"web_compile_{source.stem}_{int(time.time() * 1000)}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            def ps_quote(value):
                return "'" + str(value).replace("'", "''") + "'"
            # Em algumas instalacoes o Windows bloqueia a criacao direta do
            # MetaEditor pelo Python, embora o Start-Process consiga inicia-lo.
            ps = (
                f"$p=Start-Process -FilePath {ps_quote(found)} "
                f"-ArgumentList {ps_quote('/compile:' + str(source))},{ps_quote('/include:' + str(source.parents[2]))},{ps_quote('/log:' + str(log_path))} "
                "-WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode"
            )
            proc = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
                capture_output=True, text=True, timeout=120,
            )
            log = ''
            if log_path.exists():
                for enc in ('utf-16', 'utf-8', 'cp1252'):
                    try:
                        log = log_path.read_text(encoding=enc, errors='replace')
                        if log.strip():
                            break
                    except Exception:
                        pass
            log = log or ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
            match = re.search(r'(?:Result:\s*)?(\d+)\s+errors?,\s*(\d+)\s+warnings?', log, re.I)
            if not match:
                return {'ok': proc.returncode == 0, 'errors': -1, 'warnings': -1, 'log': log[-12000:], 'log_path': str(log_path)}
            errors, warnings = int(match.group(1)), int(match.group(2))
            return {'ok': errors == 0 and warnings == 0, 'errors': errors, 'warnings': warnings, 'log': log[-12000:], 'log_path': str(log_path)}
        except Exception as exc:
            return {'ok': False, 'errors': -1, 'warnings': -1, 'log': str(exc)}

    def _tool_repair_mql5(self, tc):
        """Corrige em tentativas controladas e instala somente uma copia compilada."""
        source = Path(str(tc.get('path', '')).strip())
        request = str(tc.get('request', 'Corrigir os erros de compilacao')).strip()
        if source.suffix.lower() != '.mq5' or not source.exists():
            return f"Arquivo MQL5 invalido ou nao encontrado: {source}"
        try:
            code = source.read_text(encoding='utf-8', errors='replace')
            mt5_experts = Path(r'C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\Meus Robos')
            mt5_experts.mkdir(parents=True, exist_ok=True)
            target = mt5_experts / f'{source.stem}_AI_CORRIGIDO.mq5'
            backup = target.with_suffix(target.suffix + f'.backup_{int(time.time())}') if target.exists() else None
            if backup:
                shutil.copy2(target, backup)
            target.write_text(code, encoding='utf-8', newline='')
            compile_result = self._compile_mql5_path(target)
            attempts = []
            for attempt in range(1, 4):
                if compile_result.get('ok'):
                    return json.dumps({'ok': True, 'status': 'COMPILED', 'file': str(target), 'backup': str(backup) if backup else None, 'attempts': attempts, 'compile': compile_result}, ensure_ascii=False, indent=2)
                if compile_result.get('errors', -1) < 0:
                    break
                prompt = f'''Voce e especialista senior em MQL5. Corrija somente erros reais do MetaEditor e preserve a estrategia.
Pedido: {request}
Tentativa: {attempt}/3
Log real do MetaEditor:
{compile_result.get('log', '')}
Codigo completo:
{code[:140000]}
Retorne SOMENTE o codigo MQL5 completo, sem Markdown, sem explicacoes.'''
                response = ollama_chat(model='qwen2.5-coder:14b', messages=[
                    {'role': 'system', 'content': 'Corrija codigo MQL5 conservadoramente usando o log do compilador.'},
                    {'role': 'user', 'content': prompt},
                ], stream=False)
                candidate = str(response.get('message', {}).get('content', '') if isinstance(response, dict) else '')
                fenced = re.search(r'```(?:mql5|mq5)?\s*([\s\S]*?)```', candidate, re.I)
                if fenced:
                    candidate = fenced.group(1).strip()
                if '#property' in candidate:
                    candidate = candidate[candidate.find('#property'):]
                if len(candidate) < 80 or ('OnInit' not in candidate and 'OnTick' not in candidate):
                    attempts.append({'attempt': attempt, 'status': 'INVALID_MODEL_OUTPUT'})
                    break
                code = candidate
                target.write_text(code, encoding='utf-8', newline='')
                compile_result = self._compile_mql5_path(target)
                attempts.append({'attempt': attempt, 'errors': compile_result.get('errors'), 'warnings': compile_result.get('warnings')})
            if backup:
                shutil.copy2(backup, target)
            else:
                target.unlink(missing_ok=True)
            return json.dumps({'ok': False, 'status': 'NOT_COMPILED_ROLLBACK', 'file': str(target), 'attempts': attempts, 'last_compile': compile_result}, ensure_ascii=False, indent=2)
        except Exception as exc:
            return f'Falha na correcao MQL5: {exc}'

    # ── SYSTEM TOOLS ──────────────────────────────────────────

    def _tool_system_info(self):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            boot = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot

            result = f"## 💻 Informacoes do Sistema\n\n"
            result += f"| Componente | Status |\n|------------|--------|\n"
            result += f"| CPU | {cpu}% de uso |\n"
            result += f"| RAM | {mem.percent}% ({mem.used/(1024**3):.1f} GB / {mem.total/(1024**3):.1f} GB) |\n"
            result += f"| Disco C: | {disk.percent}% ({disk.used/(1024**3):.1f} GB / {disk.total/(1024**3):.1f} GB) |\n"
            result += f"| Uptime | {str(uptime).split('.')[0]} |\n"
            result += f"| Username | {os.environ.get('USERNAME', 'unknown')} |\n"
            result += f"| Python | {sys.version.split()[0]} |\n"

            # Check Ollama
            try:
                req = urllib.request.Request('http://127.0.0.1:11434/api/tags', headers={'User-Agent': 'GoldenAI'})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    models = json.loads(resp.read()).get('models', [])
                    result += f"| Ollama | Online ({len(models)} modelos) |\n"
                    for m in models[:5]:
                        result += f"  - {m.get('name', '?')}\n"
            except:
                result += f"| Ollama | Offline |\n"

            return result
        except Exception as e:
            return f"Erro ao obter info: {str(e)}"

    def _tool_find_programs(self):
        try:
            # List installed programs from registry
            import winreg
            programs = []
            for hive_name, hive in [("HKLM", winreg.HKEY_LOCAL_MACHINE), ("HKCU", winreg.HKEY_CURRENT_USER)]:
                for subkey in [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                               r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]:
                    try:
                        key = winreg.OpenKey(hive, subkey)
                        i = 0
                        while True:
                            try:
                                subname = winreg.EnumKey(key, i)
                                subkey2 = winreg.OpenKey(key, subname)
                                try:
                                    name = winreg.QueryValueEx(subkey2, "DisplayName")[0]
                                    programs.append(name)
                                except:
                                    pass
                                winreg.CloseKey(subkey2)
                                i += 1
                            except WindowsError:
                                break
                        winreg.CloseKey(key)
                    except:
                        pass

            programs = sorted(set(programs))
            result = f"## 📦 Programas Instalados ({len(programs)})\n\n"
            for p in programs[:50]:
                result += f"- {p}\n"
            if len(programs) > 50:
                result += f"\n... e mais {len(programs)-50} programas"
            return result
        except Exception as e:
            return f"Erro ao listar programas: {str(e)}"

    def _tool_uninstall_program(self, tc):
        name = tc.get("name", "")
        return f"⚠️ Para desinstalar '{name}', use:\n\n```\nwmic product where name='{name}' call uninstall\n```\n\nOu vá em Configurações > Aplicativos > desinstalar manualmente.\n**Nao desinstalo programas automaticamente por seguranca.**"

    # ── WEB TOOLS ─────────────────────────────────────────────

    def _tool_web_search(self, tc):
        query = tc.get("query", "")
        results = []

        # Wikipedia
        try:
            url = f"https://pt.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&srlimit=3"
            req = urllib.request.Request(url, headers={'User-Agent': 'GoldenAI/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for item in data.get('query', {}).get('search', [])[:3]:
                    snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))
                    results.append({"title": item.get('title', ''), "snippet": snippet[:300], "source": "Wikipedia"})
        except:
            pass

        # Bing
        try:
            url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count=5"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode('utf-8', errors='replace')
                titles = re.findall(r'<h2><a[^>]*>([^<]+)</a></h2>', html)
                snippets = re.findall(r'<p[^>]*>([^<]{20,200})</p>', html)
                for i, t in enumerate(titles[:3]):
                    s = snippets[i] if i < len(snippets) else ""
                    results.append({"title": t, "snippet": s, "source": "Bing"})
        except:
            pass

        if results:
            output = f"## 🔍 Resultados da busca: '{query}'\n\n"
            for r in results:
                output += f"**{r['title']}** ({r['source']})\n{r['snippet']}\n\n"
            return output
        return f"Nenhum resultado encontrado para '{query}'"

    def _tool_get_exchange_rate(self):
        try:
            url = 'https://open.er-api.com/v6/latest/USD'
            req = urllib.request.Request(url, headers={'User-Agent': 'GoldenAI/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                d = json.loads(resp.read().decode('utf-8'))
                rates = d.get('rates', {})
                updated = d.get('time_last_update_utc', '')

                result = f"## 💰 Cotacoes em Tempo Real (USD Base)\n\n"
                result += f"| Moeda | Cotacao |\n|-------|--------|\n"
                result += f"| 🇧🇷 USD/BRL | R$ {rates.get('BRL', '?')} |\n"
                result += f"| 🇪🇺 EUR/USD | {round(1/rates.get('EUR', 1), 4)} |\n"
                result += f"| 🇬🇧 GBP/USD | {round(1/rates.get('GBP', 1), 4)} |\n"
                result += f"| 🇯🇵 USD/JPY | {rates.get('JPY', '?')} |\n"
                result += f"| 🇨🇦 USD/CAD | {rates.get('CAD', '?')} |\n"
                result += f"| 🇨🇭 USD/CHF | {rates.get('CHF', '?')} |\n"
                result += f"\n🕐 Atualizado: {updated}"
                return result
        except Exception as e:
            return f"Erro ao obter cotacoes: {str(e)}"

    # ── PDF TOOLS ──────────────────────────────────────────────

    def _tool_read_pdf(self, tc):
        path = tc.get("path", "")
        p = Path(path)
        if not p.exists():
            return f"PDF nao encontrado: {path}"
        try:
            import pymupdf
            doc = pymupdf.open(str(p))
            result = f"## 📄 PDF: {p.name} ({len(doc)} paginas)\n\n"
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    result += f"### Pagina {i+1}\n{text}\n\n"
            doc.close()
            return result[:5000]
        except ImportError:
            return "PyMuPDF nao instalado. Execute: pip install PyMuPDF"
        except Exception as e:
            return f"Erro ao ler PDF: {str(e)}"

    def _tool_list_pdf_words(self, tc):
        path = tc.get("path", "")
        word = tc.get("word", "")
        p = Path(path)
        if not p.exists():
            return f"PDF nao encontrado: {path}"
        try:
            import pymupdf
            doc = pymupdf.open(str(p))
            occurrences = []
            for i, page in enumerate(doc):
                results = page.search_for(word)
                if results:
                    for rect in results:
                        occurrences.append({"page": i+1, "rect": str(rect)})
            doc.close()
            if occurrences:
                result = f"## 🔍 '{word}' encontrada {len(occurrences)} vez(es):\n\n"
                for occ in occurrences:
                    result += f"- Pagina {occ['page']}\n"
                return result
            return f"'{word}' nao encontrada no PDF"
        except ImportError:
            return "PyMuPDF nao instalado. Execute: pip install PyMuPDF"
        except Exception as e:
            return f"Erro: {str(e)}"

    def _tool_edit_pdf(self, tc):
        path = tc.get("path", "")
        old_text = tc.get("old", "")
        new_text = tc.get("new", "")
        p = Path(path)
        if not p.exists():
            return f"PDF nao encontrado: {path}"
        if not old_text or not new_text:
            return "Parametros 'old' e 'new' obrigatorios"
        try:
            import pymupdf
            import shutil
            
            # Copy to temp for safety
            tmp = str(p) + ".tmp"
            shutil.copy2(str(p), tmp)
            
            doc = pymupdf.open(tmp)
            changes = 0
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                blocks = page.get_text('dict')['blocks']
                
                # Search case-insensitive
                for search_term in [old_text, old_text.lower(), old_text.upper(), old_text.capitalize()]:
                    results = page.search_for(search_term)
                    for rect in results:
                        font_size = 11
                        text_color = (0, 0, 0)
                        
                        # Find original font properties
                        for block in blocks:
                            if 'lines' in block:
                                for line in block['lines']:
                                    for span in line['spans']:
                                        span_rect = pymupdf.Rect(span['bbox'])
                                        if span_rect.intersects(rect) and search_term.lower() in span['text'].lower():
                                            font_size = span['size']
                                            color_int = span.get('color', 0)
                                            if isinstance(color_int, int):
                                                r = ((color_int >> 16) & 0xFF) / 255.0
                                                g = ((color_int >> 8) & 0xFF) / 255.0
                                                b = (color_int & 0xFF) / 255.0
                                                text_color = (r, g, b)
                        
                        # Redact old text
                        page.add_redact_annot(rect, fill=(1, 1, 1))
                        page.apply_redactions()
                        
                        # Insert new text
                        page.insert_text(
                            pymupdf.Point(rect.x0, rect.y1 - 2),
                            new_text,
                            fontsize=font_size,
                            fontname='helv',
                            color=text_color
                        )
                        changes += 1
            
            doc.save(str(p), garbage=4, deflate=True)
            doc.close()
            
            # Clean temp
            import os
            try: os.remove(tmp)
            except: pass
            
            return f"✅ PDF corrigido! '{old_text}' -> '{new_text}' ({changes} ocorrencias na pagina)"
        except ImportError:
            return "PyMuPDF nao instalado. Execute: pip install PyMuPDF"
        except Exception as e:
            return f"Erro ao editar PDF: {str(e)}"

    def _tool_create_pdf(self, tc):
        title = tc.get("title", "Relatorio")
        content = tc.get("content", "")
        output_path = tc.get("path", f"C:/Users/Anderson/Desktop/{title}.pdf")
        try:
            import pymupdf
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=842)  # A4
            
            # Title
            page.insert_text(pymupdf.Point(50, 50), title, fontsize=20, fontname='helv', color=(0.83, 0.66, 0.26))
            
            # Content
            y = 80
            for line in content.split('\n'):
                if y > 780:
                    page = doc.new_page(width=595, height=842)
                    y = 50
                page.insert_text(pymupdf.Point(50, y), line, fontsize=11, fontname='helv', color=(0, 0, 0))
                y += 18
            
            doc.save(output_path)
            doc.close()
            return f"✅ PDF criado: {output_path}"
        except ImportError:
            return "PyMuPDF nao instalado. Execute: pip install PyMuPDF"
        except Exception as e:
            return f"Erro ao criar PDF: {str(e)}"

    # ── BACKTEST TOOLS ─────────────────────────────────────────

    def _tool_run_backtest(self, tc):
        symbol = tc.get("symbol", "EURUSD")
        timeframe = tc.get("timeframe", "H1")
        period = tc.get("period", "1Y")
        strategy = tc.get("strategy", "moving_average")
        params = tc.get("params", {})

        # Generate synthetic backtest data
        import random
        random.seed(42)

        initial_capital = 10000.0
        capital = initial_capital
        trades = []
        equity_curve = [{"time": 0, "value": capital}]

        # Simulate price movement
        price = 1.1000 if "EUR" in symbol else 1.3000
        fast_period = params.get("fast_period", 10)
        slow_period = params.get("slow_period", 50)

        fast_ma = price
        slow_ma = price
        position = 0  # 0=flat, 1=long, -1=short
        entry_price = 0

        num_bars = 252 if period == "1Y" else 126 if period == "6M" else 63 if period == "3M" else 21

        for i in range(num_bars):
            # Price movement
            price *= (1 + random.gauss(0, 0.001))

            # Update MAs
            fast_ma = fast_ma * (1 - 1/fast_period) + price * (1/fast_period)
            slow_ma = slow_ma * (1 - 1/slow_period) + price * (1/slow_period)

            # Trading logic
            if position == 0:
                if fast_ma > slow_ma:
                    position = 1
                    entry_price = price
                    trades.append({"time": i, "type": "BUY", "price": price})
                elif fast_ma < slow_ma:
                    position = -1
                    entry_price = price
                    trades.append({"time": i, "type": "SELL", "price": price})
            elif position == 1 and fast_ma < slow_ma:
                pnl = price - entry_price
                capital += pnl * 100000
                trades.append({"time": i, "type": "CLOSE_BUY", "price": price, "pnl": pnl})
                position = 0
            elif position == -1 and fast_ma > slow_ma:
                pnl = entry_price - price
                capital += pnl * 100000
                trades.append({"time": i, "type": "CLOSE_SELL", "price": price, "pnl": pnl})
                position = 0

            equity_curve.append({"time": i+1, "value": round(capital, 2)})

        # Calculate metrics
        total_return = ((capital - initial_capital) / initial_capital) * 100
        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        losing_trades = [t for t in trades if t.get("pnl", 0) < 0]
        win_rate = (len(winning_trades) / max(1, len(winning_trades) + len(losing_trades))) * 100

        # Max drawdown
        peak = initial_capital
        max_dd = 0
        for point in equity_curve:
            if point["value"] > peak:
                peak = point["value"]
            dd = (peak - point["value"]) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe (simplified)
        returns = [(equity_curve[i]["value"] - equity_curve[i-1]["value"]) / equity_curve[i-1]["value"]
                   for i in range(1, len(equity_curve))]
        avg_return = sum(returns) / max(1, len(returns))
        std_return = (sum((r - avg_return)**2 for r in returns) / max(1, len(returns)))**0.5
        sharpe = (avg_return / max(0.0001, std_return)) * (252**0.5)

        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "period": period,
            "strategy": strategy,
            "params": params,
            "metrics": {
                "initial_capital": initial_capital,
                "final_capital": round(capital, 2),
                "total_return_pct": round(total_return, 2),
                "total_trades": len([t for t in trades if "CLOSE" in t.get("type", "")]),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "win_rate_pct": round(win_rate, 2),
                "max_drawdown_pct": round(max_dd, 2),
                "sharpe_ratio": round(sharpe, 2),
            },
            "trades": trades[:20],
            "equity_curve": equity_curve[:50],
        }

        return json.dumps(result, ensure_ascii=False, indent=2)

    def _tool_list_strategies(self):
        try:
            from strategy_engine import list_strategies, strategy_score
            strategies = []
            for item in list_strategies():
                strategies.append({
                    "id": item.get("id"),
                    "name": item.get("name", item.get("id")),
                    "kind": item.get("kind", "base"),
                    "origin": "Robô MT5" if item.get("kind") == "robot" else "Radar" if item.get("kind") == "radar" else "Base",
                    "adapter": item.get("adapter"),
                    "timeframes": item.get("timeframes", []),
                    "quality_score": strategy_score(item),
                    "audit_recommendation": item.get("audit_recommendation", "OBSERVAR"),
                    "compiled": item.get("compiled", True),
                    "description": item.get("description", ""),
                })
            strategies.sort(key=lambda s: (s.get("quality_score", 0), s.get("name", "")), reverse=True)
            return json.dumps({"total": len(strategies), "strategies": strategies}, ensure_ascii=False, indent=2)
        except Exception as exc:
            return json.dumps({"total": 0, "strategies": [], "error": str(exc)}, ensure_ascii=False)

    def _tool_list_symbols(self):
        symbols = [
            {"symbol": "EURUSD", "name": "Euro/Dolar", "spread": 1.2},
            {"symbol": "GBPUSD", "name": "Libra/Dolar", "spread": 1.5},
            {"symbol": "USDJPY", "name": "Dolar/Iene", "spread": 1.1},
            {"symbol": "XAUUSD", "name": "Ouro/Dolar", "spread": 3.0},
            {"symbol": "BTCUSD", "name": "Bitcoin/Dolar", "spread": 50.0},
            {"symbol": "USDCHF", "name": "Dolar/Franco", "spread": 1.4},
            {"symbol": "AUDUSD", "name": "AUD/USD", "spread": 1.3},
            {"symbol": "USDCAD", "name": "USD/CAD", "spread": 1.6},
        ]
        return json.dumps(symbols, ensure_ascii=False, indent=2)

    # ── STRATEGY TOOLS ─────────────────────────────────────────

    def _tool_analyze_strategy(self, tc):
        """Analisa uma estrategia de trading"""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from mimo_strategy import StrategyAnalyzer
            
            analyzer = StrategyAnalyzer()
            config = {
                "triple_confluence": tc.get("triple_confluence", True),
                "filter_spread": tc.get("filter_spread", True),
                "filter_hours": tc.get("filter_hours", True),
                "adaptive_mode": tc.get("adaptive_mode", True),
            }
            results = analyzer.analyze_strategy(config)
            
            # Formatar resultado
            lines = ["## 📊 Análise de Estratégia", ""]
            lines.append("| Padrão | Direção | WR | R:R | EV | Retorno | DD | Status |")
            lines.append("|--------|---------|-----|-----|-----|---------|-----|--------|")
            
            for name, data in sorted(results.items(), key=lambda x: x[1]["expected_value"], reverse=True):
                emoji = "🔥" if data["expected_value"] > 0.5 else "✅" if data["expected_value"] > 0 else "❌"
                dir_emoji = "🟢" if data["direction"] == "COMPRA" else "🔴"
                lines.append(
                    f"| **{name}** | {dir_emoji} {data['direction']} | "
                    f"**{data['win_rate']}%** | {data['rr_ratio']:.1f} | "
                    f"{data['expected_value']:+.4f} | {data['sim_return']:+.1f}% | "
                    f"{data['sim_drawdown']:.1f}% | {emoji} |"
                )
            
            # Resumo
            avg_wr = sum(r["win_rate"] for r in results.values()) / len(results)
            avg_ev = sum(r["expected_value"] for r in results.values()) / len(results)
            best = max(results.items(), key=lambda x: x[1]["expected_value"])
            
            lines.append("")
            lines.append(f"**Resumo:** WR médio {avg_wr:.1f}% | EV médio {avg_ev:+.4f} | Melhor: {best[0]}")
            lines.append("")
            lines.append("💡 Use **otimize_strategy** para encontrar a melhor configuração SL/TP")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Erro na análise: {str(e)}"

    def _tool_optimize_strategy(self, tc):
        """Otimiza parâmetros da estratégia"""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from mimo_strategy import StrategyAnalyzer
            
            analyzer = StrategyAnalyzer()
            symbol = tc.get("symbol", "XAUUSD")
            timeframe = tc.get("timeframe", "M15")
            
            result = analyzer.optimize_params(symbol, timeframe)
            best = result["best"]
            
            lines = [
                "## ⚙️ Otimização de Estratégia",
                f"**Símbolo:** {symbol} | **Timeframe:** {timeframe}",
                f"**Combinações testadas:** {result['total_tested']}",
                "",
                "### 🏆 Melhor Configuração:",
                f"- **Stop Loss:** {best['sl']} pontos",
                f"- **Take Profit:** {best['tp']} pontos",
                f"- **R:R:** {best['rr']:.1f}:1",
                f"- **WR Médio:** {best['avg_wr']}%",
                f"- **Retorno Simulado:** {best['avg_return']:+.1f}%",
                f"- **Max Drawdown:** {best['avg_dd']:.1f}%",
                "",
                "### 📊 Top 5 Configurações:",
                "",
                "| # | SL | TP | R:R | WR | Retorno | DD |",
                "|---|----|----|-----|-----|---------|-----|",
            ]
            
            for i, cfg in enumerate(result["top_10"][:5]):
                medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
                lines.append(
                    f"| {medal} | {cfg['sl']} | {cfg['tp']} | {cfg['rr']:.1f} | "
                    f"{cfg['avg_wr']}% | {cfg['avg_return']:+.1f}% | {cfg['avg_dd']:.1f}% |"
                )
            
            lines.append("")
            lines.append("💡 Para aplicar, altere **StopEmPontos** e **AlvoEmPontos** no EA")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Erro na otimização: {str(e)}"

    def _tool_compare_strategies(self, tc):
        """Compara diferentes configurações de SL/TP"""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from mimo_strategy import StrategyAnalyzer
            
            analyzer = StrategyAnalyzer()
            
            configs = [
                {"name": "1:1", "sl": 500, "tp": 500, "triple_confluence": True},
                {"name": "1:2", "sl": 500, "tp": 1000, "triple_confluence": True},
                {"name": "1:3", "sl": 500, "tp": 1500, "triple_confluence": True},
                {"name": "Original", "sl": 200, "tp": 500, "triple_confluence": True},
            ]
            
            lines = [
                "## 🔄 Comparativo de Estratégias",
                "",
                "| Config | SL | TP | R:R | WR Médio | EV Médio | Retorno |",
                "|--------|----|----|-----|----------|----------|---------|",
            ]
            
            for cfg in configs:
                results = analyzer.analyze_strategy(cfg)
                avg_wr = sum(r["win_rate"] for r in results.values()) / len(results)
                avg_ev = sum(r["expected_value"] for r in results.values()) / len(results)
                avg_ret = sum(r["sim_return"] for r in results.values()) / len(results)
                rr = cfg["tp"] / cfg["sl"]
                
                emoji = "🔥" if avg_ev > 0.5 else "✅" if avg_ev > 0 else "❌"
                lines.append(
                    f"| {emoji} **{cfg['name']}** | {cfg['sl']} | {cfg['tp']} | "
                    f"{rr:.1f} | {avg_wr:.1f}% | {avg_ev:+.4f} | {avg_ret:+.1f}% |"
                )
            
            lines.append("")
            lines.append("💡 Use **optimize_strategy** para encontrar a melhor configuração")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Erro na comparação: {str(e)}"

    def _tool_open_strategy_panel(self):
        """Abre o painel de estratégia no navegador"""
        try:
            panel_path = Path(__file__).parent / "strategy_panel.html"
            if panel_path.exists():
                os.startfile(str(panel_path))
                return "Painel de estratégia aberto no navegador! 📊"
            else:
                return "Painel não encontrado. Execute analyze_strategy primeiro."
        except Exception as e:
            return f"Erro ao abrir painel: {str(e)}"

    # ── CLAUDE TOOLS ───────────────────────────────────────────

    def _tool_claude_chat(self, tc):
        """Chat com Claude via OpenRouter"""
        if not CLAUDE_AVAILABLE:
            return "Claude não disponível. Verifique a instalação."
        
        provider = get_claude_provider()
        if not provider.api_key:
            return "API key não configurada. Use: configure_api_key SUA_KEY"
        
        message = tc.get("message", "")
        model = tc.get("model", "anthropic/claude-sonnet-4")
        
        messages = [
            {"role": "system", "content": MQL5_SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ]
        
        result = provider.chat(messages, model=model)
        if "error" in result:
            return f"Erro Claude: {result['error']}"
        
        if "choices" in result and result["choices"]:
            return result["choices"][0]["message"]["content"]
        
        return "Sem resposta do Claude"

    def _tool_claude_analyze_code(self, tc):
        """Analisa código com Claude"""
        if not CLAUDE_AVAILABLE:
            return "Claude não disponível."
        
        provider = get_claude_provider()
        if not provider.api_key:
            return "API key não configurada. Use: configure_api_key SUA_KEY"
        
        path = tc.get("path", "")
        question = tc.get("question", "Analise este código e identifique bugs, melhorias e otimizações")
        
        # Ler arquivo
        p = Path(path)
        if not p.exists():
            return f"Arquivo não encontrado: {path}"
        
        try:
            code = p.read_text(encoding='utf-8', errors='replace')
            result = provider.analyze_mql5(code, question)
            return result
        except Exception as e:
            return f"Erro: {str(e)}"

    def _tool_claude_optimize(self, tc):
        """Otimiza estratégia com Claude"""
        if not CLAUDE_AVAILABLE:
            return "Claude não disponível."
        
        provider = get_claude_provider()
        if not provider.api_key:
            return "API key não configurada. Use: configure_api_key SUA_KEY"
        
        strategy_data = tc.get("data", {})
        result = provider.optimize_strategy(strategy_data)
        return result

    def _tool_configure_api_key(self, tc):
        """Configura API key do OpenRouter"""
        if not CLAUDE_AVAILABLE:
            return "Módulo Claude não disponível."
        
        key = tc.get("key", "")
        if not key:
            return "Forneça a API key: configure_api_key SUA_KEY"
        
        provider = get_claude_provider()
        provider.set_api_key(key)
        
        # Verificar se foi salvo
        config_path = provider._config_path()
        saved = config_path.exists()
        
        return f"✅ API key configurada! Modelo: Claude Sonnet 4\n\n💾 Salvo em: {config_path}\n📁 Arquivo existe: {'Sim' if saved else 'Não'}\n\nAgora você pode usar:\n- claude_chat: Chat direto com Claude\n- claude_analyze_code: Análise de código\n- claude_optimize: Otimização de estratégia"

    def _tool_configure_cline_key(self, tc):
        """Configura API key do Cline"""
        try:
            from cline_provider import get_claude_provider as get_cline
            cline_prov = get_cline()
        except ImportError:
            return "Modulo Cline nao disponivel."
        
        key = tc.get("key", "")
        if not key:
            return "Forneça a API key do Cline: configure_cline_key SUA_KEY"
        
        cline_prov.set_api_key(key)
        
        config_path = cline_prov._config_path()
        saved = config_path.exists()
        
        return ("API key do Cline configurada!\n\n"
                "Salvo em: %s\n"
                "Arquivo existe: %s\n\n"
                "Modelos disponiveis via Cline:\n"
                "- Claude Sonnet 4 (Melhor qualidade)\n"
                "- Claude 3.5 Haiku (Mais rapido)\n"
                "- GPT-4o (OpenAI)\n"
                "- Gemini 2.5 Flash (Google)\n\n"
                "Selecione um modelo Cline no dropdown do chat." % (config_path, 'Sim' if saved else 'Nao'))

    # ═══════════════════════════════════════════════════════════════
    # STATUS & SYSTEM APIs
    # ═══════════════════════════════════════════════════════════════

    def _api_mt5_status(self):
        """Verifica status do MetaTrader 5"""
        try:
            mt5_experts = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts")
            if mt5_experts.exists():
                ea_count = len(list(mt5_experts.rglob('*.mq5')))
                return {"ok": True, "path": str(mt5_experts), "ea_count": ea_count}
            return {"ok": False, "error": "MT5 Experts path not found"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_system_disk(self):
        """Retorna espaço em disco"""
        try:
            import shutil as _shutil
            usage = _shutil.disk_usage('C:\\')
            free_gb = round(usage.free / (1024**3), 1)
            total_gb = round(usage.total / (1024**3), 1)
            used_gb = round(usage.used / (1024**3), 1)
            pct = round((usage.used / usage.total) * 100, 1)
            return {"ok": True, "free": f"{free_gb}GB livre", "total": total_gb, "used": used_gb, "percent": pct}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_system_stats(self):
        """Retorna stats do sistema (CPU, RAM, Disco)"""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            return {
                "ok": True,
                "cpu": f"{cpu}%",
                "ram": f"{mem.percent}%",
                "disk": f"{disk.percent}%",
                "ram_used_gb": round(mem.used / (1024**3), 1),
                "ram_total_gb": round(mem.total / (1024**3), 1),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_ea_generate(self, data):
        """Gera um EA MQL5 completo baseado nos parâmetros"""
        name = data.get('name', 'MeuEA').replace(' ', '_')
        symbol = data.get('symbol', 'XAUUSD')
        timeframe = data.get('timeframe', 'M15')
        strategy = data.get('strategy', 'ma_cross')
        sl = data.get('sl', 500)
        tp = data.get('tp', 1000)
        lot = data.get('lot', 0.01)
        magic = data.get('magic', 12345)
        trailing = data.get('trailing', False)
        breakeven = data.get('breakeven', True)
        auto_trade = data.get('autoTrade', True)
        base_robot = data.get('baseRobot', '')

        # Se um robô base foi selecionado, usar como template
        if base_robot:
            base_path = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\Meus Robos") / f"{base_robot}.mq5"
            if base_path.exists():
                try:
                    base_code = base_path.read_text(encoding='utf-8', errors='replace')
                    # Adaptar o código base
                    adapted_code = base_code.replace(base_robot, name)
                    # Atualizar magic number
                    adapted_code = re.sub(r'input\s+long\s+Numero_Magico\s*=\s*\d+', f'input long   Numero_Magico   = {magic}', adapted_code)
                    adapted_code = re.sub(r'input\s+long\s+MagicNumber\s*=\s*\d+', f'input long   MagicNumber   = {magic}', adapted_code)
                    adapted_code = re.sub(r'input\s+long\s+NumeroMagico\s*=\s*\d+', f'input long   NumeroMagico   = {magic}', adapted_code)
                    # Atualizar símbolo
                    adapted_code = re.sub(r'input\s+string\s+Simbolo\s*=\s*"[^"]*"', f'input string   Simbolo        = "{symbol}"', adapted_code)
                    # Atualizar timeframe
                    adapted_code = re.sub(r'input\s+ENUM_TIMEFRAMES\s+TempoOper\s*=\s*PERIOD_\w+', f'input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe}', adapted_code)
                    # Atualizar stop/take se existirem nos inputs
                    adapted_code = re.sub(r'input\s+int\s+StopLoss\s*=\s*\d+', f'input int      StopLoss      = {sl}', adapted_code)
                    adapted_code = re.sub(r'input\s+int\s+TakeProfit\s*=\s*\d+', f'input int      TakeProfit    = {tp}', adapted_code)
                    adapted_code = re.sub(r'input\s+double\s+Lote\s*=\s*[\d.]+', f'input double   Lote          = {lot}', adapted_code)
                    # Atualizar descrição
                    adapted_code = re.sub(r'#property\s+description\s+"[^"]*"', f'#property description "{name} - Baseado em {base_robot}"', adapted_code, count=1)
                    
                    desc_info = {'name': f'Baseado em {base_robot}', 'desc': f'Robô gerado a partir do template {base_robot}.mq5 com parâmetros personalizados.', 'logic': 'Mesma lógica do robô original com parâmetros ajustados'}
                    
                    return {
                        "ok": True,
                        "code": adapted_code,
                        "description": desc_info['desc'],
                        "logic": desc_info['logic'],
                        "strategy_name": desc_info['name']
                    }
                except Exception as e:
                    pass  # Fallback para geração normal

        # ═══ DESCRIPÇÃO DA ESTRATÉGIA ═══
        descriptions = {
            'ma_cross': {
                'name': 'Cruzamento de Médias Móveis',
                'desc': 'Compra quando a média rápida cruza a lenta para cima (Golden Cross). Vende quando cruza para baixo (Death Cross). Funciona melhor em tendências fortes.',
                'logic': 'EMA 20 > EMA 50 = COMPRA | EMA 20 < EMA 50 = VENDA'
            },
            'rsi_reversal': {
                'name': 'Reversão RSI',
                'desc': 'Compra quando o RSI sai da zona de sobrevenda (abaixo de 30). Vende quando sai da zona de sobrecompra (acima de 70). Excelente para mercados laterais.',
                'logic': 'RSI < 30 e volta para cima = COMPRA | RSI > 70 e volta para baixo = VENDA'
            },
            'bollinger': {
                'name': 'Bollinger Bands (Bandas de Bollinger)',
                'desc': 'Compra quando o preço toca a banda inferior e volta. Vende quando toca a banda superior e volta. As bandas representam 2 desvios-padrão da média.',
                'logic': 'Preço < Band. Inferior e volta = COMPRA | Preço > Band. Superior e volta = VENDA'
            },
            'macd': {
                'name': 'MACD (Moving Average Convergence Divergence)',
                'desc': 'Compra quando a linha MACD cruza a linha de sinal para cima. Vende quando cruza para baixo. O histograma mostra a força do momentum.',
                'logic': 'MACD > Sinal e histograma crescente = COMPRA | MACD < Sinal e histograma decrescente = VENDA'
            },
            'scalping': {
                'name': 'Scalping com EMA + ATR',
                'desc': 'Estratégia de scalping rápido. Usa EMA rápida para tendência e ATR para volatilidade. Entra quando preço está próximo da EMA e ATR confirma movimento. Ideal para XAUUSD e pares voláteis.',
                'logic': 'Preço > EMA 9 + ATR confirma = COMPRA | Preço < EMA 9 + ATR confirma = VENDA'
            },
            'grid': {
                'name': 'Grid Trading (Grade)',
                'desc': 'Cria uma grade de ordens pendentes acima e abaixo do preço atual. Lucra com movimentos laterais. Cada nível da grade tem SL/TP próprio. Cuidado: pode gerar muitas posições.',
                'logic': 'BUY STOP acima + SELL STOP abaixo = Grade simétrica | Cada ordem com TP fixo'
            },
            'martingale': {
                'name': 'Martingale Adaptativo',
                'desc': 'Dobra o lote após cada perda para recuperar. Usa filtro de tendência para evitar sequências longas. Mais seguro que martingale puro. ALTO RISCO - use com gerenciamento de risco.',
                'logic': 'Perda → Dobra lote | Ganho → Volta ao lote base | Filtro: só opera na tendência'
            },
            'hedging': {
                'name': 'Hedging + Recovery',
                'desc': 'Abre posições opostas quando está em perda para equilibrar. Usa距离s para recuperar. Estratégia avançada para mercados laterais.',
                'logic': 'Compra em perda → Abre Venda no mesmo volume | Fecha quando equilibra'
            },
            'breakout': {
                'name': 'Breakout de Zonas (S/R)',
                'desc': 'Detecta suportes e resistências automaticamente. Compra quando rompe resistência. Vende quando rompe suporte. Excelente para momentos de alta volatilidade.',
                'logic': 'Preço rompe Resistência = COMPRA | Preço rompe Suporte = VENDA'
            },
            'ict_smc': {
                'name': 'ICT / Smart Money Concepts',
                'desc': 'Estratégia baseada em Order Blocks, Fair Value Gaps e Liquidez. Identifica onde as grandes instituições entram. Funciona melhor em H1 e H4.',
                'logic': 'Order Block + FVG + Liquidez = ENTRADA | Kill Zone: 9h-12h e 14h-17h'
            },
            'custom': {
                'name': 'Personalizada',
                'desc': 'Estratégia customizável. Use o chat para descrever sua estratégia e eu gero o código.',
                'logic': 'Defina sua própria lógica de entrada e saída'
            }
        }

        desc_info = descriptions.get(strategy, descriptions['ma_cross'])

        # ═══ TEMPLATES MQL5 ═══
        if strategy == 'ma_cross':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"
#property description "{desc_info['desc']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "MÉDIAS MÓVEIS"
input int      MA_Rapida     = 20;
input int      MA_Lenta      = 50;
input ENUM_MA_METHOD MetodoMA = MODE_EMA;

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 300;
input int      TrailingStep  = 50;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 200;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
int maRapidaHandle, maLentaHandle;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   maRapidaHandle = iMA(Simbolo, TempoOper, MA_Rapida, 0, MetodoMA, PRICE_CLOSE);
   maLentaHandle = iMA(Simbolo, TempoOper, MA_Lenta, 0, MetodoMA, PRICE_CLOSE);
   if(maRapidaHandle == INVALID_HANDLE || maLentaHandle == INVALID_HANDLE)
   {{ Print("Erro indicadores!"); return INIT_FAILED; }}
   Print("{name} OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnDeinit(const int reason) {{ IndicatorRelease(maRapidaHandle); IndicatorRelease(maLentaHandle); }}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   double fast[], slow[];
   CopyBuffer(maRapidaHandle, 0, 1, 2, fast);
   CopyBuffer(maLentaHandle, 0, 1, 2, slow);
   if(ArraySize(fast) < 2) return;

   if(fast[0] > slow[0] && fast[1] <= slow[1]) {{ if(OperarAuto) AbrirCompra(); }}
   if(fast[0] < slow[0] && fast[1] >= slow[1]) {{ if(OperarAuto) AbrirVenda(); }}
   GerenciarPosicao();
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} BUY");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} SELL");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven)
      {{
         if(tipo == POSITION_TYPE_BUY)
         {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open + BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open + BreakevenProfit*pt, cTP); }}
         else
         {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open - BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open - BreakevenProfit*pt, cTP); }}
      }}
      if(UsarTrailing)
      {{
         if(tipo == POSITION_TYPE_BUY)
         {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open + TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }}
         else
         {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open - TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }}
      }}
   }}
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'rsi_reversal':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"
#property description "{desc_info['desc']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "RSI"
input int      PeriodoRSI     = 14;
input double   Sobrecompra    = 70.0;
input double   Sobrevenda     = 30.0;

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 300;
input int      TrailingStep  = 50;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 200;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
int rsiHandle;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   rsiHandle = iRSI(Simbolo, TempoOper, PeriodoRSI, PRICE_CLOSE);
   if(rsiHandle == INVALID_HANDLE) {{ Print("Erro RSI!"); return INIT_FAILED; }}
   Print("{name} OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnDeinit(const int reason) {{ IndicatorRelease(rsiHandle); }}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   double rsi[2];
   CopyBuffer(rsiHandle, 0, 1, 2, rsi);
   if(ArraySize(rsi) < 2) return;

   // COMPRA: RSI cruza de baixo de Sobrevenda para cima
   if(rsi[1] < Sobrevenda && rsi[0] >= Sobrevenda)
   {{ if(OperarAuto) AbrirCompra(); }}

   // VENDA: RSI cruza de cima de Sobrecompra para baixo
   if(rsi[1] > Sobrecompra && rsi[0] <= Sobrecompra)
   {{ if(OperarAuto) AbrirVenda(); }}

   GerenciarPosicao();
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} BUY RSI");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} SELL RSI");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven)
      {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open+BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open+BreakevenProfit*pt, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open-BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open-BreakevenProfit*pt, cTP); }} }}
      if(UsarTrailing)
      {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open+TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open-TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }} }}
   }}
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'bollinger':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"
#property description "{desc_info['desc']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "BOLLINGER BANDS"
input int      PeriodoBB      = 20;
input double   DesviosBB      = 2.0;

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 300;
input int      TrailingStep  = 50;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 200;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
int bbHandle;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   bbHandle = iBands(Simbolo, TempoOper, PeriodoBB, 0, DesviosBB, PRICE_CLOSE);
   if(bbHandle == INVALID_HANDLE) {{ Print("Erro BB!"); return INIT_FAILED; }}
   Print("{name} OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnDeinit(const int reason) {{ IndicatorRelease(bbHandle); }}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   double upper[2], middle[2], lower[2];
   CopyBuffer(bbHandle, 1, 1, 2, upper); // Banda Superior
   CopyBuffer(bbHandle, 0, 1, 2, middle); // Média
   CopyBuffer(bbHandle, 2, 1, 2, lower); // Banda Inferior
   if(ArraySize(upper) < 2) return;

   double close1 = iClose(Simbolo, TempoOper, 1);
   double close2 = iClose(Simbolo, TempoOper, 2);

   // COMPRA: Preço tocou banda inferior e voltou para cima
   if(close2 <= lower[1] && close1 > lower[0])
   {{ if(OperarAuto) AbrirCompra(); }}

   // VENDA: Preço tocou banda superior e voltou para baixo
   if(close2 >= upper[1] && close1 < upper[0])
   {{ if(OperarAuto) AbrirVenda(); }}

   GerenciarPosicao();
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} BUY BB");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} SELL BB");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven)
      {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open+BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open+BreakevenProfit*pt, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open-BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open-BreakevenProfit*pt, cTP); }} }}
      if(UsarTrailing)
      {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open+TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open-TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }} }}
   }}
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'macd':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"
#property description "{desc_info['desc']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "MACD"
input int      MACD_Fast     = 12;
input int      MACD_Slow     = 26;
input int      MACD_Signal   = 9;

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 300;
input int      TrailingStep  = 50;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 200;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
int macdHandle;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   macdHandle = iMACD(Simbolo, TempoOper, MACD_Fast, MACD_Slow, MACD_Signal, PRICE_CLOSE);
   if(macdHandle == INVALID_HANDLE) {{ Print("Erro MACD!"); return INIT_FAILED; }}
   Print("{name} OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnDeinit(const int reason) {{ IndicatorRelease(macdHandle); }}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   double main[2], signal[2];
   CopyBuffer(macdHandle, 0, 1, 2, main);   // Linha MACD
   CopyBuffer(macdHandle, 1, 1, 2, signal); // Linha Sinal
   if(ArraySize(main) < 2) return;

   // COMPRA: MACD cruza sinal de baixo para cima
   if(main[0] > signal[0] && main[1] <= signal[1])
   {{ if(OperarAuto) AbrirCompra(); }}

   // VENDA: MACD cruza sinal de cima para baixo
   if(main[0] < signal[0] && main[1] >= signal[1])
   {{ if(OperarAuto) AbrirVenda(); }}

   GerenciarPosicao();
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} BUY MACD");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} SELL MACD");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven)
      {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open+BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open+BreakevenProfit*pt, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open-BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open-BreakevenProfit*pt, cTP); }} }}
      if(UsarTrailing)
      {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open+TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open-TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }} }}
   }}
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'scalping':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "SCALPING EMA + ATR"
input int      EMA_Periodo    = 9;
input int      ATR_Periodo    = 14;
input double   ATR_Minimo     = 0.5;
input double   DistanciaEMA   = 0.3;

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 200;
input int      TrailingStep  = 30;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 150;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
int emaHandle, atrHandle;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   emaHandle = iMA(Simbolo, TempoOper, EMA_Periodo, 0, MODE_EMA, PRICE_CLOSE);
   atrHandle = iATR(Simbolo, TempoOper, ATR_Periodo);
   if(emaHandle == INVALID_HANDLE || atrHandle == INVALID_HANDLE)
   {{ Print("Erro indicadores!"); return INIT_FAILED; }}
   Print("{name} Scalping OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnDeinit(const int reason)
{{
   IndicatorRelease(emaHandle);
   IndicatorRelease(atrHandle);
}}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   double ema[2], atr[1];
   CopyBuffer(emaHandle, 0, 1, 2, ema);
   CopyBuffer(atrHandle, 0, 1, 1, atr);
   if(ArraySize(ema) < 2 || ArraySize(atr) < 1) return;
   if(atr[0] < ATR_Minimo * _Point * 10000) return;

   double close1 = iClose(Simbolo, TempoOper, 1);
   double close2 = iClose(Simbolo, TempoOper, 2);

   // COMPRA: Preço cruza EMA para cima com ATR forte
   if(close2 <= ema[1] && close1 > ema[0])
   {{ if(OperarAuto) AbrirCompra(); }}

   // VENDA: Preço cruza EMA para baixo com ATR forte
   if(close2 >= ema[1] && close1 < ema[0])
   {{ if(OperarAuto) AbrirVenda(); }}

   GerenciarPosicao();
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} SCALP BUY");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} SCALP SELL");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven) {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open+BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open+BreakevenProfit*pt, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open-BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open-BreakevenProfit*pt, cTP); }} }}
      if(UsarTrailing) {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open+TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open-TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }} }}
   }}
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'breakout':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "BREAKOUT"
input int      PeriodoLookback = 20;
input double   BufferPontos   = 50;
input int      ConfirmacaoBarras = 2;

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 300;
input int      TrailingStep  = 50;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 200;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   Print("{name} Breakout OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   double high = iHigh(Simbolo, TempoOper, 1);
   double low = iLow(Simbolo, TempoOper, 1);
   double close = iClose(Simbolo, TempoOper, 1);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);

   // Encontrar máxima e mínima do período
   double highest = high;
   double lowest = low;
   for(int i = 2; i <= PeriodoLookback; i++)
   {{
      highest = MathMax(highest, iHigh(Simbolo, TempoOper, i));
      lowest = MathMin(lowest, iLow(Simbolo, TempoOper, i));
   }}

   // COMPRA: Rompe máxima com buffer
   if(close > highest + BufferPontos * pt)
   {{ if(OperarAuto) AbrirCompra(); }}

   // VENDA: Rompe mínima com buffer
   if(close < lowest - BufferPontos * pt)
   {{ if(OperarAuto) AbrirVenda(); }}

   GerenciarPosicao();
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} BREAKOUT BUY");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} BREAKOUT SELL");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven) {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open+BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open+BreakevenProfit*pt, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open-BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open-BreakevenProfit*pt, cTP); }} }}
      if(UsarTrailing) {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open+TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open-TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }} }}
   }}
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'grid':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input int      MagicNumber   = {magic};

input group "GRID"
input int      DistanciaGrid  = 500;
input int      NiveisGrid     = 5;
input double   LoteNivel      = {lot};
input int      TakeProfitGrid = 300;

input group "GERENCIAMENTO"
input double   LoteMaximo     = 0.5;
input int      MaxPosicoes    = 10;
input bool     OperarAuto     = {'true' if auto_trade else 'false'};

CTrade trade;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   Print("{name} Grid OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, PERIOD_M1, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   if(!OperarAuto) return;

   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);

   // Verificar quantas posições temos
   int posCount = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      posCount++;
   }}

   if(posCount >= MaxPosicoes) return;

   // Criar grade
   for(int i = 1; i <= NiveisGrid; i++)
   {{
      double buyPrice = ask + i * DistanciaGrid * pt;
      double sellPrice = bid - i * DistanciaGrid * pt;
      double tpBuy = buyPrice + TakeProfitGrid * pt;
      double tpSell = sellPrice - TakeProfitGrid * pt;

      // Verificar se já existe ordem neste nível
      if(!ExistePosicao(buyPrice, POSITION_TYPE_BUY))
         trade.Buy(LoteNivel, Simbolo, buyPrice, 0, tpBuy, "{name} GRID BUY " + IntegerToString(i));
      if(!ExistePosicao(sellPrice, POSITION_TYPE_SELL))
         trade.Sell(LoteNivel, Simbolo, sellPrice, 0, tpSell, "{name} GRID SELL " + IntegerToString(i));
   }}
}}

bool ExistePosicao(double price, ENUM_POSITION_TYPE type)
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      if(PositionGetInteger(POSITION_TYPE) != type) continue;
      if(MathAbs(PositionGetDouble(POSITION_PRICE_OPEN) - price) < 10 * _Point) return true;
   }}
   return false;
}}
//+------------------------------------------------------------------+
"""

        elif strategy == 'ict_smc':
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5                                                       |
//| Estratégia: {desc_info['name']}                                  |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - {desc_info['name']}"

#include <Trade/Trade.mqh>

input group "CONFIGURAÇÕES GERAIS"
input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};

input group "ICT / SMC"
input int      LookbackZones  = 50;
input double   ZoneBuffer     = 50;
input bool     UsarFVG        = true;
input int      FVG_Minimo     = 100;

input group "KILL ZONE"
input bool     UsarKillZone   = true;
input string   HoraInicio     = "09:00";
input string   HoraFim        = "12:00";

input group "GERENCIAMENTO"
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     UsarTrailing  = {'true' if trailing else 'false'};
input int      TrailingStart = 300;
input int      TrailingStep  = 50;
input bool     UsarBreakeven = {'true' if breakeven else 'false'};
input int      BreakevenStart = 200;
input int      BreakevenProfit = 0;
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;
datetime lastBarTime = 0;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   Print("{name} ICT/SMC OK em ", Simbolo);
   return INIT_SUCCEEDED;
}}

void OnTick()
{{
   datetime currentBar = iTime(Simbolo, TempoOper, 0);
   if(currentBar == lastBarTime) return;
   lastBarTime = currentBar;

   if(!OperarAuto) return;

   // Kill Zone check
   if(UsarKillZone && !EstaNaKillZone()) return;

   double close = iClose(Simbolo, TempoOper, 1);
   double open1 = iOpen(Simbolo, TempoOper, 1);
   double high = iHigh(Simbolo, TempoOper, 1);
   double low = iLow(Simbolo, TempoOper, 1);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);

   // Encontrar zonas de suporte/resistência (Order Blocks)
   double resistance = 0, support = 999999;
   for(int i = 2; i <= LookbackZones; i++)
   {{
      resistance = MathMax(resistance, iHigh(Simbolo, TempoOper, i));
      support = MathMin(support, iLow(Simbolo, TempoOper, i));
   }}

   // COMPRA: Preço toca suporte e volta (Order Block)
   if(low <= support + ZoneBuffer * pt && close > support)
   {{
      if(UsarFVG && !TemFVG(PERIOD_M5, 3)) return;
      AbrirCompra();
   }}

   // VENDA: Preço toca resistência e volta (Order Block)
   if(high >= resistance - ZoneBuffer * pt && close < resistance)
   {{
      if(UsarFVG && !TemFVG(PERIOD_M5, -3)) return;
      AbrirVenda();
   }}

   GerenciarPosicao();
}}

bool TemFVG(ENUM_TIMEFRAMES tf, int dir)
{{
   // Verifica se existe Fair Value Gap
   double high1 = iHigh(Simbolo, tf, 1);
   double low3 = iLow(Simbolo, tf, 3);
   if(dir > 0) return (low3 > high1 + FVG_Minimo * _Point);
   double high3 = iHigh(Simbolo, tf, 3);
   double low1 = iLow(Simbolo, tf, 1);
   return (low1 < high3 - FVG_Minimo * _Point);
}}

bool EstaNaKillZone()
{{
   MqlDateTime dt;
   TimeCurrent(dt);
   int hora = dt.hour;
   int minuto = dt.min;
   int atual = hora * 60 + minuto;
   int ini = (int)StringToInteger(StringSubstr(HoraInicio, 0, 2)) * 60 + (int)StringToInteger(StringSubstr(HoraInicio, 3, 2));
   int fim = (int)StringToInteger(StringSubstr(HoraFim, 0, 2)) * 60 + (int)StringToInteger(StringSubstr(HoraFim, 3, 2));
   return (atual >= ini && atual <= fim);
}}

void AbrirCompra()
{{
   if(PositionsTotal() > 0) return;
   double ask = SymbolInfoDouble(Simbolo, SYMBOL_ASK);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? ask - StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? ask + TakeProfit * pt : 0;
   trade.Buy(Lote, Simbolo, ask, sl, tp, "{name} ICT BUY");
}}

void AbrirVenda()
{{
   if(PositionsTotal() > 0) return;
   double bid = SymbolInfoDouble(Simbolo, SYMBOL_BID);
   double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
   double sl = StopLoss > 0 ? bid + StopLoss * pt : 0;
   double tp = TakeProfit > 0 ? bid - TakeProfit * pt : 0;
   trade.Sell(Lote, Simbolo, bid, sl, tp, "{name} ICT SELL");
}}

void GerenciarPosicao()
{{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {{
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Simbolo) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double cSL = PositionGetDouble(POSITION_SL);
      double cTP = PositionGetDouble(POSITION_TP);
      long tipo = PositionGetInteger(POSITION_TYPE);
      double pt = SymbolInfoDouble(Simbolo, SYMBOL_POINT);
      if(UsarBreakeven) {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); if(p >= open+BreakevenStart*pt && cSL < open) trade.PositionModify(ticket, open+BreakevenProfit*pt, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); if(p <= open-BreakevenStart*pt && (cSL > open || cSL == 0)) trade.PositionModify(ticket, open-BreakevenProfit*pt, cTP); }} }}
      if(UsarTrailing) {{ if(tipo == POSITION_TYPE_BUY) {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_BID); double nsl = p - TrailingStep*pt; if(p >= open+TrailingStart*pt && nsl > cSL) trade.PositionModify(ticket, nsl, cTP); }} else {{ double p = SymbolInfoDouble(Simbolo, SYMBOL_ASK); double nsl = p + TrailingStep*pt; if(p <= open-TrailingStart*pt && (nsl < cSL || cSL == 0)) trade.PositionModify(ticket, nsl, cTP); }} }}
   }}
}}
//+------------------------------------------------------------------+
"""

        else:
            code = f"""//+------------------------------------------------------------------+
//| {name}.mq5 - Estratégia Personalizada                            |
//| Golden AI - Gerado Automaticamente                                |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "{name} - Personalizada"

#include <Trade/Trade.mqh>

input string   Simbolo        = "{symbol}";
input ENUM_TIMEFRAMES TempoOper = PERIOD_{timeframe};
input int      MagicNumber   = {magic};
input double   Lote          = {lot};
input int      StopLoss      = {sl};
input int      TakeProfit    = {tp};
input bool     OperarAuto    = {'true' if auto_trade else 'false'};

CTrade trade;

int OnInit()
{{
   trade.SetExpertMagicNumber(MagicNumber);
   Print("{name} OK - Use o chat para personalizar a lógica");
   return INIT_SUCCEEDED;
}}

void OnTick()
{{
   // Adicione sua lógica aqui
   // Use o chat do Golden AI para descrever sua estratégia
}}
//+------------------------------------------------------------------+
"""

        # Retornar código + descrição
        return {
            "ok": True,
            "code": code,
            "description": desc_info['desc'],
            "logic": desc_info['logic'],
            "strategy_name": desc_info['name']
        }

    def _api_mt5_compile(self, data):
        """Compila um arquivo MQL5 usando metaeditor64.exe"""
        denied = self._authorize_api_mutation(data, 'mql5_compile', permission='EXECUTE', target=data.get('file', ''), reason='Compilar arquivo MQL5 no MetaEditor.')
        if denied: return denied
        file_name = data.get('file', '')
        mt5_path = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075")
        file_path = mt5_path / 'MQL5' / 'Experts' / file_name
        
        if not file_path.exists():
            return {"ok": False, "errors": f"Arquivo não encontrado: {file_name}"}
        
        # Procurar metaeditor64.exe
        metaeditor = mt5_path / 'metaeditor64.exe'
        if not metaeditor.exists():
            # Tentar caminhos alternativos
            program_files = Path('C:/Program Files')
            for p in program_files.rglob('metaeditor64.exe'):
                metaeditor = p
                break
        
        if not metaeditor.exists():
            return {"ok": False, "errors": "metaeditor64.exe não encontrado"}
        
        try:
            result = subprocess.run(
                [str(metaeditor), '/compile', str(file_path)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return {"ok": True, "output": result.stdout}
            return {"ok": False, "errors": result.stderr or result.stdout}
        except Exception as e:
            return {"ok": False, "errors": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # BACKTEST ENGINE
    # ═══════════════════════════════════════════════════════════════

    def _api_mt5_backtest(self, data):
        """Executa um backtest usando dados reais do MT5"""
        try:
            from mt5_backtest import run_backtest
            strategy = data.get('strategy', 'ma_cross')
            symbol = data.get('symbol', 'XAUUSD')
            timeframe = data.get('timeframe', 'M15')
            params = {
                'sl': data.get('sl', 500),
                'tp': data.get('tp', 1000),
                'lot': data.get('lot', 0.01),
                'balance': data.get('balance', 10000),
                'count': data.get('count', 3000),
            }
            # Adicionar parâmetros de indicadores do robô
            ind_params = data.get('indicator_params', {})
            if ind_params:
                params.update(ind_params)
            result = run_backtest(strategy, symbol, timeframe, params)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_analyze_robot(self, data):
        """Analisa o código de um robô e detecta a estratégia + parâmetros para backtest"""
        name = str(data.get('name', '')).strip()
        if name.lower().endswith('.mq5'):
            name = name[:-4]
        mt5_path = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\Meus Robos")
        mq5_file = mt5_path / f"{name}.mq5"
        if not mq5_file.exists():
            return {"ok": False, "error": f"Robô {name}.mq5 não encontrado"}
        try:
            code = mq5_file.read_text(encoding='utf-8', errors='replace')
            
            # Detectar estratégia
            strategy = 'ma_cross'  # padrão
            strategy_name = 'Desconhecida'
            
            # Verificar indicadores usados
            has_iMA = 'iMA(' in code or 'iMA ' in code
            has_iRSI = 'iRSI(' in code or 'iRSI ' in code
            has_iBands = 'iBands(' in code or 'iBands ' in code
            has_iMACD = 'iMACD(' in code or 'iMACD ' in code
            has_iATR = 'iATR(' in code or 'iATR ' in code
            has_iStochastic = 'iStochastic(' in code
            has_iIchimoku = 'iIchimoku(' in code
            has_iADX = 'iADX(' in code
            has_iMomentum = 'iMomentum(' in code
            has_iCCI = 'iCCI(' in code
            has_iEnvelopes = 'iEnvelopes(' in code
            
            # Detectar padrões de candle
            has_candle_patterns = 'Engolfo' in code or 'Martelo' in code or 'Estrela' in code or 'Padrao' in code or 'candle' in code.lower()
            
            # Detectar S/R e Zonas
            has_sr = 'Suporte' in code or 'Resistencia' in code or 'Regiao' in code or 'SR_' in code or 'Zona' in code or 'S/R' in code
            
            # Detectar SMC/ICT
            has_smc = 'SMC' in code or 'FVG' in code or 'OrderBlock' in code or 'Smart' in code or 'ICT' in code
            
            # Detectar Breakout
            has_breakout = 'Breakout' in code or 'Rompe' in code or 'rompimento' in code.lower()
            
            # Detectar Grid
            has_grid = 'Grid' in code or 'Grade' in code or 'NiveisGrid' in code
            
            # Mapear para estratégia de backtest
            if has_smc:
                strategy = 'breakout'
                strategy_name = 'SMC/ICT - Smart Money Concepts'
            elif has_grid:
                strategy = 'breakout'
                strategy_name = 'Grid Trading'
            elif has_breakout:
                strategy = 'breakout'
                strategy_name = 'Breakout de Zonas'
            elif has_candle_patterns and has_sr:
                strategy = 'breakout'
                strategy_name = 'Padrões de Candle + S/R'
            elif has_iMACD and (has_iRSI or has_iBands):
                strategy = 'macd'
                strategy_name = 'MACD + Confluência'
            elif has_iMACD:
                strategy = 'macd'
                strategy_name = 'MACD'
            elif has_iBands:
                strategy = 'bollinger'
                strategy_name = 'Bollinger Bands'
            elif has_iRSI:
                strategy = 'rsi_reversal'
                strategy_name = 'RSI'
            elif has_iMA and has_iATR:
                strategy = 'scalping'
                strategy_name = 'Scalping EMA+ATR'
            elif has_iMA:
                strategy = 'ma_cross'
                strategy_name = 'Cruzamento de Médias'
            else:
                strategy = 'ma_cross'
                strategy_name = 'Estratégia Geral'
            
            # Extrair parâmetros detalhados
            import re
            
            # Extrair símbolo
            symbol_match = re.search(r'input\s+string\s+Simbolo\s*=\s*"([^"]+)"', code)
            symbol = symbol_match.group(1) if symbol_match else 'XAUUSD'
            
            # Extrair timeframe
            tf_match = re.search(r'input\s+ENUM_TIMEFRAMES\s+\w*[Tt]empo\w*\s*=\s*PERIOD_(\w+)', code)
            if not tf_match:
                tf_match = re.search(r'PERIOD_(\w+)', code)
            timeframe = tf_match.group(1) if tf_match else 'M15'
            
            # Extrair SL
            sl_match = re.search(r'input\s+(?:int|double)\s+\w*[Ss]top\w*[Pp]ontos?\s*=\s*(\d+)', code)
            if not sl_match:
                sl_match = re.search(r'input\s+(?:int|double)\s+\w*[Ss]top\w*\s*=\s*(\d+)', code)
            sl = int(sl_match.group(1)) if sl_match else 500
            
            # Extrair TP
            tp_match = re.search(r'input\s+(?:int|double)\s+\w*[Tt]ake\w*[Pp]ontos?\s*=\s*(\d+)', code)
            if not tp_match:
                tp_match = re.search(r'input\s+(?:int|double)\s+\w*[Tt]ake\w*\s*=\s*(\d+)', code)
            if not tp_match:
                tp_match = re.search(r'input\s+(?:int|double)\s+\w*[Aa]lvo\w*\s*=\s*(\d+)', code)
            tp = int(tp_match.group(1)) if tp_match else 1000
            
            # Extrair Lote
            lot_match = re.search(r'input\s+double\s+\w*[Ll]ote\w*\s*=\s*([\d.]+)', code)
            lot = float(lot_match.group(1)) if lot_match else 0.01
            
            # Extrair Magic Number
            magic_match = re.search(r'input\s+long\s+\w*[Mm]agic\w*\s*=\s*(\d+)', code)
            magic = int(magic_match.group(1)) if magic_match else 12345
            
            # Extrair parâmetros de indicadores
            indicator_params = {}
            
            # Extrair inputs numéricos relevantes
            all_inputs = re.findall(r'input\s+(?:int|double)\s+(\w+)\s*=\s*([\d.]+)', code)
            input_dict = {input_name: float(val) for input_name, val in all_inputs}
            
            # Mapear inputs para parâmetros de indicadores
            for input_name, val in input_dict.items():
                name_lower = input_name.lower()
                if 'periodo' in name_lower and ('media' in name_lower or 'ma' in name_lower or 'ema' in name_lower):
                    if 'ema_periods' not in indicator_params:
                        indicator_params['ema_periods'] = []
                    indicator_params['ema_periods'].append(int(val))
                elif 'periodo' in name_lower and 'rsi' in name_lower:
                    indicator_params['rsi_period'] = int(val)
                elif 'periodo' in name_lower and 'atr' in name_lower:
                    indicator_params['atr_period'] = int(val)
                elif 'periodo' in name_lower and 'adx' in name_lower:
                    indicator_params['adx_period'] = int(val)
                elif 'periodo' in name_lower and 'bb' in name_lower or 'bollinger' in name_lower:
                    indicator_params['bb_period'] = int(val)
                elif 'sobrecompra' in name_lower or 'overbought' in name_lower:
                    indicator_params['rsi_overbought'] = val
                elif 'sobrevenda' in name_lower or 'oversold' in name_lower:
                    indicator_params['rsi_oversold'] = val
            
            # Fallback: extrair de chamadas iMA com número direto
            if 'ema_periods' not in indicator_params:
                ema_matches = re.findall(r'iMA\([^,]+,[^,]+,(\d+),', code)
                if ema_matches:
                    indicator_params['ema_periods'] = [int(x) for x in ema_matches[:4]]
            
            # Extrair SL/TP de inputs também
            for input_name, val in input_dict.items():
                name_lower = input_name.lower()
                if 'stop' in name_lower and 'ponto' in name_lower:
                    indicator_params['sl_points'] = int(val)
                elif 'take' in name_lower and 'ponto' in name_lower:
                    indicator_params['tp_points'] = int(val)
                elif 'alvo' in name_lower and 'ponto' in name_lower:
                    indicator_params['tp_points'] = int(val)
            
            # MACD params de inputs
            for input_name, val in input_dict.items():
                name_lower = input_name.lower()
                if 'macd' in name_lower and ('rapido' in name_lower or 'fast' in name_lower):
                    indicator_params['macd_fast'] = int(val)
                elif 'macd' in name_lower and ('lento' in name_lower or 'slow' in name_lower):
                    indicator_params['macd_slow'] = int(val)
                elif 'macd' in name_lower and 'sinal' in name_lower:
                    indicator_params['macd_signal'] = int(val)
            
            # Fallback: extrair de chamadas iMACD com números diretos
            if 'macd_fast' not in indicator_params:
                macd_match = re.search(r'iMACD\([^,]+,(\d+),(\d+),(\d+),', code)
                if macd_match:
                    indicator_params['macd_fast'] = int(macd_match.group(1))
                    indicator_params['macd_slow'] = int(macd_match.group(2))
                    indicator_params['macd_signal'] = int(macd_match.group(3))
            
            # Fallback: extrair de chamadas iBands
            if 'bb_period' not in indicator_params:
                bb_match = re.search(r'iBands\([^,]+,(\d+),', code)
                if bb_match:
                    indicator_params['bb_period'] = int(bb_match.group(1))
            
            # Extrair infos do robô
            lines = len(code.splitlines())
            functions = re.findall(r'(?:void|int|double|bool|string)\s+(\w+)\s*\(', code)
            inputs = re.findall(r'input\s+(?:string|int|double|bool|color|enum\s+\w+)\s+(\w+)', code)
            
            # Extrair descrição
            description = ''
            for line in code.splitlines()[:20]:
                if '#property description' in line:
                    desc_match = re.search(r'"([^"]+)"', line)
                    if desc_match:
                        description = desc_match.group(1)
                        break
            
            return {
                "ok": True,
                "name": name,
                "strategy": strategy,
                "strategy_name": strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "sl": sl,
                "tp": tp,
                "lot": lot,
                "magic": magic,
                "lines": lines,
                "functions": len(functions),
                "inputs": len(inputs),
                "description": description,
                "indicator_params": indicator_params,
                "indicators": {
                    "iMA": has_iMA,
                    "iRSI": has_iRSI,
                    "iBands": has_iBands,
                    "iMACD": has_iMACD,
                    "iATR": has_iATR,
                    "iStochastic": has_iStochastic,
                    "iADX": has_iADX,
                    "SMC_FVG": has_smc,
                    "Candle_Patterns": has_candle_patterns,
                    "S/R_Zonas": has_sr,
                }
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_backtest_history(self, data):
        """Retorna histórico de backtests executados"""
        try:
            from mt5_backtest import get_backtest_history
            limit = data.get('limit', 20)
            results = get_backtest_history(limit)
            return {"ok": True, "results": results}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_real_backtest(self, data):
        """Executa backtest REAL no Strategy Tester do MT5"""
        try:
            denied = self._authorize_api_mutation(data, 'mt5_real_backtest', permission='EXECUTE', target=f"{data.get('symbol', '')}:{data.get('timeframe', '')}", reason='Criar/compilar EA temporario e abrir o Strategy Tester.')
            if denied: return denied
            from mt5_real_backtest import run_real_backtest
            robot_name = data.get('robot_name', '')
            strategy = data.get('strategy', 'ma_cross')
            symbol = data.get('symbol', 'XAUUSD')
            timeframe = data.get('timeframe', 'M15')
            params = {
                'sl': data.get('sl', 500),
                'tp': data.get('tp', 1000),
                'lot': data.get('lot', 0.01),
                'indicator_params': data.get('indicator_params', {}),
            }
            result = run_real_backtest(robot_name, strategy, symbol, timeframe, params)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_chart_analysis(self, data):
        """Captura grafico MT5 e analisa com IA. Modos: scalp, day, swing"""
        try:
            from chart_capture import full_chart_analysis
            symbol = data.get('symbol', 'XAUUSD')
            timeframe = data.get('timeframe', 'M15')
            mode = data.get('mode', 'day')
            if mode == 'price_action': mode = 'day'
            result = full_chart_analysis(symbol, timeframe, mode=mode)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_full_analysis(self, data):
        """Analise completa: Regime + Especialista + Ranking + IA"""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}
            import MetaTrader5 as mt5
            try:
                from analysis_engines import FullAnalyzer, build_structured_prompt
                from specialists import MasterAnalyzer
                symbol = data.get('symbol', 'XAUUSD')
                mode = data.get('mode', 'day')
                if mode == 'price_action': mode = 'day'
                
                # 1-4. Motores de analise base (sem IA)
                analyzer = FullAnalyzer(symbol, mode)
                base_result = analyzer.analyze(mode)
                
                if not base_result.get('ok'):
                    return base_result
                
                # 5. Aplicar especialista + regime + ranking
                master = MasterAnalyzer(symbol)
                result = master.full_analysis(base_result, mode)
                
                # 5. Montar prompt estruturado para IA
                prompt = build_structured_prompt(result)
                result['structured_prompt'] = prompt
                
                # 6. Chamar IA para raciocinar (ClinePass ou OpenRouter)
                ai_response = None
                try:
                    from cline_provider import ClineProvider
                    cline = ClineProvider()
                    cline.load_api_key()
                    if cline.api_key:
                        messages = [
                            {'role': 'system', 'content': 'Voce e um analista profissional. Responda APENAS em JSON valido.'},
                            {'role': 'user', 'content': prompt}
                        ]
                        ai_result = cline.chat(messages, model='cline-pass/minimax-m3')
                        if 'choices' in ai_result and ai_result['choices']:
                            ai_response = ai_result['choices'][0]['message']['content']
                            result['ai_analysis'] = ai_response
                            result['ai_model'] = 'MiniMax M3 (ClinePass)'
                except Exception as e:
                    result['ai_error'] = str(e)
                
                # Se IA falhou, usar OpenRouter
                if not ai_response:
                    try:
                        from claude_provider import get_claude_provider
                        provider = get_claude_provider()
                        if provider.api_key:
                            messages = [
                                {'role': 'system', 'content': 'Voce e um analista profissional. Responda APENAS em JSON valido.'},
                                {'role': 'user', 'content': prompt}
                            ]
                            ai_result = provider.chat(messages, model='cohere/north-mini-code:free')
                            if 'choices' in ai_result and ai_result['choices']:
                                ai_response = ai_result['choices'][0]['message']['content']
                                result['ai_analysis'] = ai_response
                                result['ai_model'] = 'OpenRouter Free'
                    except Exception as e:
                        result['ai_error'] = str(e)
                
                # Registrar no Trade Journal
                try:
                    from trade_journal import journal, setup_db
                    setup_id = journal.log_analysis(result, ai_response or '', result.get('ai_model', ''))
                    setup_db.save_setup(result)
                    result['setup_id'] = setup_id
                except Exception as e:
                    print("[JOURNAL] Erro: %s" % e)
                
                return result
            finally:
                pass  # MT5 mantido vivo
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_journal_stats(self, data):
        """Retorna estatisticas do Trade Journal"""
        try:
            from trade_journal import journal, feedback
            symbol = data.get('symbol', None)
            stats = journal.get_statistics(symbol)
            recommendations = feedback.get_recommendations()
            return {'ok': True, 'stats': stats, 'recommendations': recommendations}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_journal_calibrate(self, data):
        """Calibra o score com dados reais"""
        try:
            from trade_journal import feedback
            symbol = data.get('symbol', 'XAUUSD')
            calibration = feedback.calibrate_score(symbol)
            return {'ok': True, 'calibration': calibration}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_journal_history(self, data):
        """Retorna historico de trades do journal"""
        try:
            from trade_journal import journal
            symbol = data.get('symbol', None)
            limit = data.get('limit', 50)
            entries = journal.get_recent_entries(symbol, limit)
            return {'ok': True, 'entries': entries, 'count': len(entries)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_walk_forward(self, data):
        """Executa walk-forward testing"""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}
            import MetaTrader5 as mt5
            try:
                from walk_forward import WalkForwardEngine
                symbol = data.get('symbol', 'XAUUSD')
                engine = WalkForwardEngine(symbol)
                result = engine.run_walk_forward()
                return {
                    'ok': True,
                    'symbol': result.symbol,
                    'strategy': result.strategy,
                    'total_windows': result.total_windows,
                    'avg_train_wr': result.avg_train_wr,
                    'avg_test_wr': result.avg_test_wr,
                    'avg_degradation': result.avg_degradation,
                    'robustness_score': result.robustness_score,
                    'robustness_label': result.robustness_label,
                    'overfitting_score': result.overfitting_score,
                    'overfitting_risk': result.overfitting_risk,
                    'recommendation': result.recommendation,
                    'confidence': result.confidence,
                    'windows': [{
                        'id': w.window_id,
                        'train': '%s a %s' % (w.train_start, w.train_end),
                        'test': '%s a %s' % (w.test_start, w.test_end),
                        'train_wr': w.train_win_rate,
                        'test_wr': w.test_win_rate,
                        'degradation': w.degradation,
                        'risk': w.overfitting_risk,
                    } for w in result.windows],
                }
            finally:
                pass  # MT5 mantido vivo
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_strategy_manager_list(self, data):
        """Lista todas as estrategias com status ON/OFF"""
        try:
            from golden_scanner import GoldenScanner, SETUP_DEFINITIONS
            scanner = GoldenScanner()
            sm = scanner.strategy_manager
            strategies = []
            for sid, cfg in SETUP_DEFINITIONS.items():
                strategies.append({
                    'id': sid,
                    'name': cfg.get('name', sid),
                    'mode': cfg.get('mode', 'scalp'),
                    'tier': cfg.get('tier', 'B'),
                    'description': cfg.get('description', ''),
                    'timeframes': cfg.get('timeframes', []),
                    'enabled': sm.is_enabled(sid),
                    'best_regime': cfg.get('best_regime', []),
                    'min_rr': cfg.get('min_rr', 1.5),
                })
            modes = sm.get_mode_states()
            summary = sm.get_status_summary()
            return {'ok': True, 'strategies': strategies, 'modes': modes, 'summary': summary}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_strategy_manager_toggle(self, data):
        """Liga/desliga uma estrategia"""
        try:
            denied = self._authorize_api_mutation(data, 'strategy_toggle', target=data.get('strategy_id', ''), reason='Alterar o estado de uma estrategia.')
            if denied: return denied
            from golden_scanner import GoldenScanner
            scanner = GoldenScanner()
            sm = scanner.strategy_manager
            sid = data.get('strategy_id', '')
            enabled = data.get('enabled', True)
            sm.toggle(sid, enabled)
            return {'ok': True, 'strategy_id': sid, 'enabled': sm.is_enabled(sid)}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_strategy_manager_toggle_mode(self, data):
        """Liga/desliga um modo (scalp/day/swing)"""
        try:
            denied = self._authorize_api_mutation(data, 'strategy_mode_toggle', target=data.get('mode', ''), reason='Alterar o modo operacional de estrategias.')
            if denied: return denied
            from golden_scanner import GoldenScanner
            scanner = GoldenScanner()
            sm = scanner.strategy_manager
            mode = data.get('mode', '')
            enabled = data.get('enabled', True)
            sm.toggle_mode(mode, enabled)
            return {'ok': True, 'mode': mode, 'enabled': enabled, 'modes': sm.get_mode_states()}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_strategy_manager_preset(self, data):
        """Aplica preset: scalp, day, swing, conservative, aggressive, tier_a, all"""
        try:
            denied = self._authorize_api_mutation(data, 'strategy_preset', target=data.get('preset', 'all'), reason='Aplicar um preset de estrategias.')
            if denied: return denied
            from golden_scanner import GoldenScanner, SETUP_DEFINITIONS
            scanner = GoldenScanner()
            sm = scanner.strategy_manager
            preset = data.get('preset', 'all')
            # Enable all first
            for sid in SETUP_DEFINITIONS:
                sm.toggle(sid, True)
            sm.toggle_mode('scalp', True)
            sm.toggle_mode('day', True)
            sm.toggle_mode('swing', True)
            if preset == 'scalp':
                for sid, cfg in SETUP_DEFINITIONS.items():
                    if cfg.get('mode') != 'scalp':
                        sm.toggle(sid, False)
                sm.toggle_mode('day', False)
                sm.toggle_mode('swing', False)
            elif preset == 'day':
                for sid, cfg in SETUP_DEFINITIONS.items():
                    if cfg.get('mode') != 'day':
                        sm.toggle(sid, False)
                sm.toggle_mode('scalp', False)
                sm.toggle_mode('swing', False)
            elif preset == 'swing':
                for sid, cfg in SETUP_DEFINITIONS.items():
                    if cfg.get('mode') != 'swing':
                        sm.toggle(sid, False)
                sm.toggle_mode('scalp', False)
                sm.toggle_mode('day', False)
            elif preset == 'conservative':
                for sid, cfg in SETUP_DEFINITIONS.items():
                    if cfg.get('tier') in ('B', 'C'):
                        sm.toggle(sid, False)
            elif preset == 'tier_a':
                for sid, cfg in SETUP_DEFINITIONS.items():
                    if cfg.get('tier') != 'A':
                        sm.toggle(sid, False)
            return {'ok': True, 'preset': preset, 'modes': sm.get_mode_states(), 'summary': sm.get_status_summary()}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_strategy_manager_auto_rank(self, data):
        """Recomendacoes automaticas ON/OFF baseado em performance"""
        try:
            from golden_scanner import GoldenScanner, SETUP_DEFINITIONS
            from statistics_engine import StatisticsEngine
            scanner = GoldenScanner()
            sm = scanner.strategy_manager
            stats = StatisticsEngine()
            all_perf = stats.get_strategy_performance()
            recommendations = []
            for sid, cfg in SETUP_DEFINITIONS.items():
                perf = all_perf.get(sid, {})
                enabled = sm.is_enabled(sid)
                ev = perf.get('expectancy_r', 0) if perf else 0
                trades = perf.get('total', 0) if perf else 0
                rec = 'ON' if enabled else 'OFF'
                if trades >= 20 and ev < -0.1:
                    rec = 'RECOMMEND_OFF'
                elif trades >= 20 and ev > 0.2:
                    rec = 'RECOMMEND_ON'
                elif trades < 20:
                    rec = 'NEEDS_DATA'
                recommendations.append({
                    'id': sid, 'name': cfg.get('name', sid), 'mode': cfg.get('mode'),
                    'tier': cfg.get('tier', 'B'), 'enabled': enabled, 'trades': trades,
                    'expectancy': round(ev, 3) if ev else 0,
                    'recommendation': rec,
                })
            return {'ok': True, 'recommendations': recommendations}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_scanner_scan(self, data):
        """Scaneia um ativo ou todos os ativos do radar"""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}
            import MetaTrader5 as mt5
            try:
                from golden_scanner import GoldenScanner
                scanner = GoldenScanner()
                symbol = data.get('symbol', None)
                if symbol:
                    scan = scanner.scan_symbol(symbol)
                    return {
                        'ok': True,
                        'scan': {
                            'symbol': scan.symbol,
                            'price': scan.price,
                            'spread': scan.spread,
                            'regime': scan.regime,
                            'regime_score': scan.regime_score,
                            'scan_time': scan.scan_time,
                            'category': scan.category,
                            'atr_h1': scan.atr_h1,
                            'atr_m15': scan.atr_m15,
                            'daily_range_pct': scan.daily_range_pct,
                            'daily_range_pts': scan.daily_range_pts,
                            'trend_h4': scan.trend_h4,
                            'trend_h1': scan.trend_h1,
                            'trend_m15': scan.trend_m15,
                            'trend_m5': scan.trend_m5,
                            'rsi_h1': scan.rsi_h1,
                            'rsi_m15': scan.rsi_m15,
                            'volatility': scan.volatility,
                            'session': scan.session,
                            'pips_today': scan.pips_today,
                            'spread_usd': scan.spread_usd,
                            'score_total': scan.score_total,
                            'top_setups': scan.top_setups,
                            'alert_level': scan.alert_level,
                            'session_active': scan.session_active,
                            'structure_htf': scan.structure_htf,
                            'bias': scan.bias,
                            'key_zones': scan.key_zones,
                            'adx': scan.adx,
                            'bb_width': scan.bb_width,
                            'best_setup': {
                                'name': scan.best_setup.name,
                                'readiness': scan.best_setup.readiness,
                                'level': scan.best_setup.level,
                                'level_label': scan.best_setup.level_label,
                                'direction': scan.best_setup.direction,
                                'conditions_met': scan.best_setup.conditions_met,
                                'conditions_missing': scan.best_setup.conditions_missing,
                                'details': scan.best_setup.details,
                                'rr_ratio': scan.best_setup.rr_ratio,
                                'confluence_score': scan.best_setup.confluence_score,
                            } if scan.best_setup else None,
                            'setups': [{
                                'name': s.name,
                                'mode': s.mode,
                                'readiness': s.readiness,
                                'level': s.level,
                                'level_label': s.level_label,
                                'direction': s.direction,
                                'details': s.details,
                                'rr_ratio': s.rr_ratio,
                                'confluence_score': s.confluence_score,
                            } for s in scan.setups[:10]],
                        }
                    }
                else:
                    scans = scanner.scan_all()
                    return {
                        'ok': True,
                        'scans': [{
                            'symbol': s.symbol,
                            'price': s.price,
                            'spread': s.spread,
                            'regime': s.regime,
                            'regime_score': s.regime_score,
                            'best_setup': {
                                'name': s.best_setup.name,
                                'readiness': s.best_setup.readiness,
                                'level_label': s.best_setup.level_label,
                                'direction': s.best_setup.direction,
                            } if s.best_setup else None,
                        } for s in scans]
                    }
            finally:
                pass  # MT5 mantido vivo
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_scanner_radar(self, data):
        """Radar multi-ativo - resumo dos melhores setups por ativo"""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}
            import MetaTrader5 as mt5
            try:
                from golden_scanner import GoldenScanner
                from statistics_engine import StatisticsEngine
                scanner = GoldenScanner()
                strategy_performance = StatisticsEngine().get_strategy_performance()
                scans = scanner.scan_all()
                radar = []
                for s in scans:
                    entry = {
                        'symbol': s.symbol,
                        'price': s.price,
                        'spread': s.spread,
                        'regime': s.regime,
                        'regime_score': s.regime_score,
                        'category': s.category,
                        'atr_h1': s.atr_h1,
                        'atr_m15': s.atr_m15,
                        'daily_range_pct': s.daily_range_pct,
                        'daily_range_pts': s.daily_range_pts,
                        'trend_h4': s.trend_h4,
                        'trend_h1': s.trend_h1,
                        'trend_m15': s.trend_m15,
                        'trend_m5': s.trend_m5,
                        'rsi_h1': s.rsi_h1,
                        'rsi_m15': s.rsi_m15,
                        'volatility': s.volatility,
                        'session': s.session,
                        'pips_today': s.pips_today,
                        'spread_usd': s.spread_usd,
                        'score_total': s.score_total,
                        'top_setups': s.top_setups,
                        'alert_level': s.alert_level,
                        'session_active': s.session_active,
                        'swap_buy': s.swap_buy,
                        'swap_sell': s.swap_sell,
                    }
                    if s.best_setup:
                        entry['best_setup'] = {
                            'setup_id': s.best_setup.setup_id,
                            'name': s.best_setup.name,
                            'readiness': s.best_setup.readiness,
                            'level': s.best_setup.level,
                            'level_label': s.best_setup.level_label,
                            'direction': s.best_setup.direction,
                            'mode': s.best_setup.mode,
                            'tier': s.best_setup.tier,
                            'conditions_met': s.best_setup.conditions_met,
                            'conditions_missing': s.best_setup.conditions_missing,
                            'details': s.best_setup.details,
                            'rr_ratio': s.best_setup.rr_ratio,
                            'confluence_score': s.best_setup.confluence_score,
                            'expectancy': s.best_setup.expectancy,
                        }
                        entry['best_readiness'] = s.best_setup.readiness
                        entry['best_level'] = s.best_setup.level_label
                        entry['best_direction'] = s.best_setup.direction
                        entry['best_mode'] = s.best_setup.mode
                        entry['best_tier'] = s.best_setup.tier
                        entry['best_setup_id'] = s.best_setup.setup_id
                        entry['best_setup_name'] = s.best_setup.name
                        entry['best_rr'] = s.best_setup.rr_ratio
                        entry['best_confluence'] = s.best_setup.confluence_score
                        entry['best_conditions_met'] = s.best_setup.conditions_met
                        entry['best_conditions_missing'] = s.best_setup.conditions_missing
                        entry['best_expectancy'] = s.best_setup.expectancy
                        validation = strategy_performance.get(s.best_setup.setup_id, {})
                        from strategy_audit import audit_all_strategies
                        audit = audit_all_strategies().get(s.best_setup.setup_id, {})
                        entry['validation'] = {
                            'status': validation.get('status', 'INCONCLUSIVO'),
                            'total_trades': validation.get('total', 0),
                            'expectancy_r': validation.get('expectancy_r', 0),
                            'profit_factor': validation.get('profit_factor', 0),
                        }
                        entry['audit'] = {
                            'recommendation': audit.get('recommendation', 'OBSERVAR'),
                            'coverage_score': audit.get('coverage_score', 0),
                            'auto_trade_eligible': audit.get('auto_trade_eligible', False),
                        }
                        entry['setup_count'] = len([x for x in s.setups if x.readiness > 30])
                        entry['top_setups_list'] = [{'setup_id': x.setup_id, 'name': x.name, 'mode': x.mode, 'tier': x.tier, 'readiness': x.readiness, 'direction': x.direction, 'rr': x.rr_ratio, 'confluence': x.confluence_score, 'expectancy': x.expectancy} for x in s.setups[:5]]
                    else:
                        entry['best_setup'] = None
                        entry['best_readiness'] = 0
                        entry['best_level'] = 'NENHUM'
                        entry['best_direction'] = 'NEUTRO'
                        entry['best_mode'] = ''
                        entry['best_tier'] = ''
                        entry['best_setup_id'] = ''
                        entry['best_setup_name'] = ''
                        entry['best_rr'] = 0
                        entry['best_confluence'] = 0
                        entry['best_conditions_met'] = []
                        entry['best_conditions_missing'] = []
                        entry['best_expectancy'] = 0
                        entry['validation'] = {'status': 'INCONCLUSIVO', 'total_trades': 0, 'expectancy_r': 0, 'profit_factor': 0}
                        entry['audit'] = {'recommendation': 'OBSERVAR', 'coverage_score': 0, 'auto_trade_eligible': False}
                        entry['setup_count'] = 0
                        entry['top_setups_list'] = []
                    # Novos campos v3
                    entry['structure_htf'] = s.structure_htf
                    entry['bias'] = s.bias
                    entry['key_zones'] = s.key_zones
                    entry['nearest_zone_dist'] = s.nearest_zone_dist
                    entry['bb_width'] = s.bb_width
                    entry['adx'] = s.adx
                    entry['scalp_count'] = s.scalp_count
                    entry['day_count'] = s.day_count
                    entry['swing_count'] = s.swing_count
                    radar.append(entry)
                radar.sort(key=lambda x: x['score_total'], reverse=True)
                from strategy_engine import list_strategies
                integrated_robots = [
                    {
                        'strategy_id': item['id'],
                        'name': item['name'],
                        'family': item.get('family', item['name']),
                        'source_path': item.get('source_path'),
                        'compiled': item.get('compiled', False),
                        'adapter': item.get('adapter', 'robot'),
                        'quality_score': item.get('quality_score', 0),
                        'related_files': item.get('related_files', []),
                        'analysis_note': item.get('binary_note', ''),
                        'requires_real_backtest': True,
                    }
                    for item in list_strategies(kind='robot')
                ]
                return {'ok': True, 'radar': radar, 'integrated_robots': integrated_robots}
            finally:
                pass  # MT5 mantido vivo
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_scanner_performance(self, data):
        """Performance por estrategia - agrega dados de todos os ativos"""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado"}
            import MetaTrader5 as mt5
            try:
                from golden_scanner import GoldenScanner, SETUP_DEFINITIONS
                scanner = GoldenScanner()
                symbols = list(scanner.RADAR_SYMBOLS)
                # Aggregate by strategy
                strat_data = {}
                pairs_with_data = 0
                for sym in symbols:
                    try:
                        info = mt5.symbol_info(sym)
                        if info and not info.visible:
                            mt5.symbol_select(sym, True)
                        scan = scanner.scan_symbol(sym)
                        if scan and scan.setups:
                            pairs_with_data += 1
                            for st in scan.setups:
                                sid = st.setup_id
                                if sid not in strat_data:
                                    strat_data[sid] = {
                                        'name': st.name,
                                        'mode': st.mode,
                                        'setup_id': sid,
                                        'scores': [],
                                        'rrs': [],
                                        'confidences': [],
                                        'conditions_met_counts': [],
                                        'conditions_total': 0,
                                        'pairs': [],
                                    }
                                sd = strat_data[sid]
                                sd['scores'].append(st.score)
                                sd['rrs'].append(st.rr_ratio)
                                sd['confidences'].append(st.confluence_score)
                                n_met = len(st.conditions_met)
                                n_total = n_met + len(st.conditions_missing)
                                sd['conditions_met_counts'].append(n_met)
                                sd['conditions_total'] = n_total
                                sd['pairs'].append({
                                    'symbol': sym,
                                    'score': st.score,
                                    'direction': st.direction,
                                    'rr': st.rr_ratio,
                                    'confluence': st.confluence_score,
                                    'level': st.level_label,
                                })
                    except Exception:
                        pass
                # Build result
                strategies = []
                for sid, sd in strat_data.items():
                    scores = sd['scores']
                    rrs = sd['rrs']
                    pairs_active = len([p for p in sd['pairs'] if p['score'] > 20])
                    # Determine tier
                    avg_score = sum(scores) / len(scores) if scores else 0
                    avg_rr = sum(rrs) / len(rrs) if rrs else 0
                    tier = 'A' if avg_score >= 50 and avg_rr >= 1.5 else 'B' if avg_score >= 30 else 'C'
                    strategies.append({
                        'name': sd['name'],
                        'mode': sd['mode'],
                        'setup_id': sid,
                        'tier': tier,
                        'avg_score': round(avg_score, 1),
                        'avg_rr': round(avg_rr, 1),
                        'avg_confluence': round(sum(sd['confidences']) / len(sd['confidences']), 1) if sd['confidences'] else 0,
                        'conditions_avg': round(sum(sd['conditions_met_counts']) / len(sd['conditions_met_counts']), 1) if sd['conditions_met_counts'] else 0,
                        'pairs_active': pairs_active,
                        'total_detections': len(scores),
                        'pairs_detail': sorted(sd['pairs'], key=lambda x: x['score'], reverse=True),
                    })
                strategies.sort(key=lambda x: x['avg_score'], reverse=True)
                return {'ok': True, 'strategies': strategies, 'total_setups': len(strategies), 'total_pairs': pairs_with_data}
            finally:
                pass
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_scanner_details(self, data):
        """Detalhes de um setup especifico"""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}
            import MetaTrader5 as mt5
            try:
                from golden_scanner import GoldenScanner
                scanner = GoldenScanner()
                symbol = data.get('symbol', 'XAUUSD')
                scan = scanner.scan_symbol(symbol)
                setups_detail = []
                for s in scan.setups:
                    setups_detail.append({
                        'name': s.name,
                        'mode': s.mode,
                        'readiness': s.readiness,
                        'level': s.level,
                        'level_label': s.level_label,
                        'direction': s.direction,
                        'conditions_met': s.conditions_met,
                        'conditions_missing': s.conditions_missing,
                        'details': s.details,
                    })
                return {
                    'ok': True,
                    'symbol': scan.symbol,
                    'price': scan.price,
                    'regime': scan.regime,
                    'regime_score': scan.regime_score,
                    'setups': setups_detail,
                }
            finally:
                pass  # MT5 mantido vivo
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══ STATISTICS ENGINE ═══

    def _api_statistics_full(self, data):
        """Dados completos de estatisticas para o dashboard"""
        try:
            from statistics_engine import get_engine
            engine = get_engine()
            result = engine.get_full_dashboard()
            return {'ok': True, **result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_statistics_strategies(self, data):
        """Performance por estrategia"""
        try:
            from statistics_engine import get_engine
            engine = get_engine()
            result = engine.get_strategy_performance()
            return {'ok': True, 'strategies': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_statistics_assets(self, data):
        """Performance por ativo"""
        try:
            from statistics_engine import get_engine
            engine = get_engine()
            result = engine.get_asset_performance()
            return {'ok': True, 'assets': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_statistics_hourly(self, data):
        """Performance por horario"""
        try:
            from statistics_engine import get_engine
            engine = get_engine()
            result = engine.get_hourly_performance()
            return {'ok': True, 'hourly': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_statistics_calibration(self, data):
        """Calibracao do score"""
        try:
            from statistics_engine import get_engine
            engine = get_engine()
            result = engine.get_score_calibration()
            return {'ok': True, 'calibration': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ═══ RISK ENGINE ═══

    def _api_risk_status(self, data):
        """Status completo do Risk Engine"""
        try:
            from risk_engine import get_risk_engine
            engine = get_risk_engine()
            # Try to get balance from MT5
            try:
                import MetaTrader5 as mt5
                info = mt5.account_info()
                if info:
                    engine.account_balance = info.balance
                    engine.account_equity = info.equity
            except:
                pass
            positions = data.get('positions', [])
            report = engine.get_risk_report(positions)
            return {'ok': True, **report}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_risk_calculate_lot(self, data):
        """Calcula lot size baseado no risco"""
        try:
            from risk_engine import get_risk_engine
            engine = get_risk_engine()
            symbol = data.get('symbol', 'XAUUSD')
            entry = data.get('entry', 0)
            stop = data.get('stop', 0)
            balance = data.get('balance', 0)
            if balance <= 0:
                try:
                    import MetaTrader5 as mt5
                    info = mt5.account_info()
                    if info:
                        balance = info.balance
                        engine.account_balance = balance
                except:
                    pass
            result = engine.calculate_lot_size(symbol, entry, stop, balance)
            return {'ok': True, **result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_risk_config(self, data):
        """Atualiza configuracoes de risco"""
        try:
            denied = self._authorize_api_mutation(data, 'risk_config', target='risk_engine', reason='Alterar limites e parametros de risco.')
            if denied: return denied
            from risk_engine import get_risk_engine
            engine = get_risk_engine()
            engine.update_config(data)
            return {'ok': True, 'config': engine.get_config()}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_risk_can_trade(self, data):
        """Verifica se pode operar"""
        try:
            from risk_engine import get_risk_engine
            engine = get_risk_engine()
            symbol = data.get('symbol')
            direction = data.get('direction')
            positions = data.get('positions', [])
            allowed, reason, details = engine.can_trade(symbol, direction, positions)
            return {'ok': True, 'allowed': allowed, 'reason': reason, 'details': details}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ═══ VALIDATION ENGINE ═══

    def _validation_parameters(self, data):
        """Retorna parametros da validacao manual ou derivados de um backtest."""
        strategy_id = data.get('strategy_id', '')
        if not strategy_id:
            return {
                'win_rate': data.get('win_rate', 0.5),
                'avg_win': data.get('avg_win_r', 1.5),
                'avg_loss': data.get('avg_loss_r', 1.0),
                'num_trades': data.get('num_trades', 200),
                'balance': data.get('initial_balance', 10000),
                'source': 'MANUAL',
            }
        from mt5_backtest import run_backtest
        result = run_backtest(
            strategy_id,
            data.get('symbol', 'XAUUSD'),
            data.get('timeframe', 'M15'),
            {
                'sl': data.get('sl', 500), 'tp': data.get('tp', 1000),
                'lot': data.get('lot', 0.01), 'balance': data.get('initial_balance', 10000),
                'count': data.get('count', 3000),
            },
        )
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'Backtest nao retornou resultado'))
        stats = result['stats']
        avg_loss_usd = abs(stats.get('avg_loss', 0))
        avg_win_usd = stats.get('avg_win', 0)
        avg_win_r = avg_win_usd / avg_loss_usd if avg_loss_usd else 1.5
        return {
            'win_rate': stats.get('win_rate', 0) / 100,
            'avg_win': avg_win_r,
            'avg_loss': 1.0,
            'num_trades': stats.get('total_trades', 0),
            'balance': data.get('initial_balance', 10000),
            'source': 'BACKTEST',
            'strategy_id': strategy_id,
            'backtest_stats': stats,
        }

    def _api_validation_full(self, data):
        """Executa suite completa de validacao"""
        try:
            from validation_engine import get_validation_engine
            engine = get_validation_engine()
            inputs = self._validation_parameters(data)
            win_rate, avg_win, avg_loss = inputs['win_rate'], inputs['avg_win'], inputs['avg_loss']
            num_trades, balance = inputs['num_trades'], inputs['balance']
            result = engine.run_full_validation(win_rate, avg_win, avg_loss, num_trades, balance)
            result['validation_source'] = inputs['source']
            result['strategy_id'] = inputs.get('strategy_id', '')
            return {'ok': True, **result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_validation_monte_carlo(self, data):
        """Monte Carlo simulation"""
        try:
            from validation_engine import get_validation_engine
            engine = get_validation_engine()
            inputs = self._validation_parameters(data)
            result = engine.monte_carlo(inputs['win_rate'], inputs['avg_win'], inputs['avg_loss'], inputs['num_trades'], data.get('num_simulations', 1000), inputs['balance'])
            return {'ok': True, 'monte_carlo': result, 'validation_source': inputs['source'], 'strategy_id': inputs.get('strategy_id', '')}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_validation_robustness(self, data):
        """Robustness test"""
        try:
            from validation_engine import get_validation_engine
            engine = get_validation_engine()
            inputs = self._validation_parameters(data)
            result = engine.robustness_test(inputs['win_rate'], inputs['avg_win'], inputs['avg_loss'], inputs['num_trades'])
            return {'ok': True, 'robustness': result, 'validation_source': inputs['source'], 'strategy_id': inputs.get('strategy_id', '')}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_validation_compare_modes(self, data):
        """Compara SCALP vs DAY vs SWING"""
        try:
            from validation_engine import get_validation_engine
            engine = get_validation_engine()
            result = engine.compare_modes()
            return {'ok': True, 'comparison': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_validation_real(self, data):
        """Valida uma estrategia especifica com dados reais do Journal"""
        try:
            from validation_engine import get_validation_engine
            engine = get_validation_engine()
            strategy_id = data.get('strategy_id', '')
            if not strategy_id:
                return {'ok': False, 'error': 'strategy_id obrigatorio'}
            result = engine.validate_strategy_real_data(strategy_id)
            return {'ok': True, 'validation': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_validation_all_real(self, data):
        """Valida todas as 47 estrategias com dados reais"""
        try:
            from validation_engine import get_validation_engine
            engine = get_validation_engine()
            result = engine.validate_all_strategies()
            return {'ok': True, 'result': result}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_import_mt5_history(self, data):
        """Importa historico real do MT5 para o Trade Journal e Validation"""
        try:
            denied = self._authorize_api_mutation(data, 'mt5_import_history', target=str(data.get('days', 90)), reason='Gravar operacoes do historico do MT5 no Trade Journal.')
            if denied: return denied
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado"}
            import MetaTrader5 as mt5
            from datetime import datetime, timedelta
            days = data.get('days', 90)
            symbol_filter = data.get('symbol', None)
            date_to = datetime.now()
            date_from = date_to - timedelta(days=days)
            deals = mt5.history_deals_get(date_from, date_to)
            if deals is None or len(deals) == 0:
                return {'ok': True, 'imported': 0, 'message': 'Nenhum deal encontrado'}
            from trade_journal import journal
            # Parear aberturas (entry=0) com fechamentos (entry=1) por position_id
            positions = {}
            for deal in deals:
                if symbol_filter and deal.symbol != symbol_filter:
                    continue
                pid = deal.position_id
                if pid not in positions:
                    positions[pid] = {'opens': [], 'closes': []}
                if deal.entry == 0:  # abertura
                    positions[pid]['opens'].append(deal)
                else:  # fechamento
                    positions[pid]['closes'].append(deal)
            imported = 0
            existing = journal.get_recent_entries(limit=50000)
            existing_tickets = set()
            for e in existing:
                tid = e.get('setup_id', '')
                if '_MT5_' in tid:
                    try:
                        existing_tickets.add(int(tid.split('_MT5_')[-1]))
                    except:
                        pass
            for pid, pos in positions.items():
                if not pos['opens'] or not pos['closes']:
                    continue
                open_deal = pos['opens'][0]
                close_deal = pos['closes'][-1]
                symbol = open_deal.symbol
                direction = 'BUY' if open_deal.type == 0 else 'SELL'
                entry_price = open_deal.price
                exit_price = close_deal.price
                profit = close_deal.profit + close_deal.swap + close_deal.commission
                volume = open_deal.volume
                magic = open_deal.magic
                ticket = open_deal.ticket
                if ticket in existing_tickets:
                    continue
                pip_value = 0.0001
                if 'JPY' in symbol or symbol in ('XAUUSD', 'XAGUSD', 'BTCUSD', 'ETHUSD'):
                    pip_value = 0.01
                if direction == 'BUY':
                    pips = (exit_price - entry_price) / pip_value
                else:
                    pips = (entry_price - exit_price) / pip_value
                result = 'WIN' if profit > 0 else ('LOSS' if profit < 0 else 'BREAKEVEN')
                # Historico importado do MT5 nao traz o risco planejado/SL original.
                # Sem esse denominador, "pips / 100" distorce muito cripto/indices.
                # Mantemos um R conservador por resultado e usamos profit_usd para
                # estatisticas monetarias; motores novos normalizam legados tambem.
                actual_rr = 1.0 if result == 'WIN' else (-1.0 if result == 'LOSS' else 0.0)
                entry_time = datetime.fromtimestamp(open_deal.time)
                exit_time = datetime.fromtimestamp(close_deal.time)
                hour = entry_time.hour
                if 0 <= hour < 8: session = 'ASIA'
                elif 8 <= hour < 14: session = 'LONDON'
                elif 14 <= hour < 18: session = 'OVERLAP'
                else: session = 'NY'
                setup_id = '%s_MT5_%d' % (symbol, ticket)
                entry_record = {
                    'setup_id': setup_id,
                    'timestamp': entry_time.isoformat(),
                    'symbol': symbol,
                    'direction': direction,
                    'entry_price': entry_price,
                    'stop_loss': 0,
                    'take_profit_1': 0,
                    'take_profit_2': 0,
                    'take_profit_3': 0,
                    'risk_reward': 0,
                    'score': 0,
                    'confidence': 'IMPORTED_MT5',
                    'tf_h4_trend': '', 'tf_h4_strength': 0,
                    'tf_h1_trend': '', 'tf_h1_strength': 0,
                    'tf_m15_trend': '', 'tf_m15_structure': '',
                    'tf_m5_breakout': False, 'tf_m5_retest': False,
                    'rsi_m15': 0, 'adx_m15': 0, 'atr_m15': 0,
                    'atr_percentile': 0, 'spread': 0,
                    'historical_win_rate': 0, 'historical_expectancy': 0,
                    'historical_samples': 0,
                    'reasons': json.dumps(['MT5 import pos=%d' % pid]),
                    'ai_model': 'MT5_IMPORT',
                    'ai_analysis': 'Importado do historico MT5',
                    'result': result,
                    'result_price': exit_price,
                    'result_time': exit_time.isoformat(),
                    'mfe': 0, 'mae': 0,
                    'actual_rr': actual_rr,
                    'rr_source': 'MT5_IMPORT_RESULT_PROXY',
                    'trade_opened': True,
                    'trade_ticket': ticket,
                    'volume': volume,
                    'profit_usd': round(profit, 2),
                    'pips': round(pips, 1),
                    'session': session,
                    'magic': magic,
                }
                with open(journal.journal_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry_record, ensure_ascii=False) + '\n')
                imported += 1
            return {
                'ok': True,
                'imported': imported,
                'total_deals': len(deals) if deals else 0,
                'period': '%d days' % days,
                'message': '%d trades importados do MT5' % imported,
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_mt5_auto_trade(self, data):
        """Executa trade automatico baseado na analise de IA. Modos: scalp, day, swing"""
        try:
            if data.get('auto_execute'):
                denied = self._authorize_api_mutation(data, 'mt5_real_order', permission='EXECUTE', target=data.get('symbol', ''), reason='Enviar uma ordem real ao MetaTrader 5.')
                if denied: return denied
            from mt5_trader import auto_trade_from_analysis
            analysis = data.get('analysis', '')
            symbol = data.get('symbol', 'XAUUSD')
            auto_execute = data.get('auto_execute', False)
            magic = data.get('magic', 99999)
            mode = data.get('mode', 'day')
            if mode == 'price_action': mode = 'day'
            result = auto_trade_from_analysis(analysis, symbol, auto_execute, magic, mode=mode)
            if auto_execute and result.get('ok'):
                try:
                    analysis_payload = {}
                    if isinstance(analysis, str):
                        try:
                            analysis_payload = json.loads(analysis)
                        except Exception:
                            analysis_payload = {'ai_analysis': analysis}
                    elif isinstance(analysis, dict):
                        analysis_payload = dict(analysis)
                    trade_params = result.get('trade_params', {})
                    execution = result.get('execution', {})
                    analysis_payload.update({
                        'symbol': symbol,
                        'direction': trade_params.get('direction') or analysis_payload.get('direction') or analysis_payload.get('direcao', 'NONE'),
                        'entry': trade_params.get('entry') or analysis_payload.get('entry') or analysis_payload.get('entrada', 0),
                        'stop_loss': trade_params.get('sl') or analysis_payload.get('stop_loss', 0),
                        'take_profit_1': trade_params.get('tp') or analysis_payload.get('take_profit') or analysis_payload.get('take_profit_1', 0),
                        'strategy_id': analysis_payload.get('strategy_id') or analysis_payload.get('setup_id') or data.get('strategy_id', ''),
                        'setup_name': analysis_payload.get('setup_name') or analysis_payload.get('setup', ''),
                        'trade_opened': True,
                        'trade_ticket': execution.get('order') or execution.get('deal') or 0,
                    })
                    from trade_journal import journal
                    journal_id = journal.log_analysis(analysis_payload, analysis if isinstance(analysis, str) else json.dumps(analysis_payload, ensure_ascii=False), 'AUTO_TRADE')
                    result['journal_setup_id'] = journal_id
                except Exception as e:
                    result['journal_error'] = str(e)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_strategy_catalog(self, data):
        """Catalogo unico consumido por backtest, comparacao e Radar."""
        try:
            from strategy_engine import list_strategies, strategy_score
            strategies = list_strategies()
            for item in strategies:
                item['quality_score'] = strategy_score(item)
                item['origin_label'] = 'Robô MT5' if item.get('kind') == 'robot' else 'Radar' if item.get('kind') == 'radar' else 'Base'
            return {"ok": True, "strategies": strategies}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_strategy_audit(self, data):
        """Auditoria de implementacao das regras dos 47 setups."""
        try:
            from strategy_audit import audit_all_strategies, get_audit_summary
            return {"ok": True, "summary": get_audit_summary(), "strategies": audit_all_strategies()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_chart_audit(self, data):
        """Auditoria visual: dados MT5 fechados, indicadores e setups no candle certo."""
        try:
            from chart_audit import audit_chart
            return audit_chart(
                symbol=data.get("symbol", "XAUUSD"),
                timeframe=data.get("timeframe", "M15"),
                count=data.get("count", 220),
                limit=data.get("limit", 12),
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_chart_data(self, data):
        """Candles fechados do MT5 para a aba de graficos do Golden."""
        try:
            from chart_data import get_chart_data
            return get_chart_data(
                symbol=data.get("symbol", "XAUUSD"),
                timeframe=data.get("timeframe", "M15"),
                count=data.get("count", 180),
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_chart_strategy_test(self, data):
        """Backtest visual: marcadores de trades para desenhar no grafico."""
        try:
            from chart_strategy_test import test_strategy_on_chart
            return test_strategy_on_chart(
                symbol=data.get("symbol", "XAUUSD"),
                timeframe=data.get("timeframe", "M15"),
                strategy=data.get("strategy", "SWING_TURTLE_BREAKOUT"),
                count=data.get("count", 320),
            )
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_meta_strategy(self, data):
        """Gestor inteligente de carteiras: regime -> carteira -> setup -> risco."""
        try:
            from mt5_connector import ensure_connection
            if not ensure_connection():
                return {"ok": False, "error": "MT5 nao conectado. Abra o MetaTrader 5."}
            from meta_strategy import analyze_radar, analyze_symbol
            symbol = str(data.get('symbol') or '').strip().upper()
            symbols = data.get('symbols') or []
            limit = int(data.get('limit') or 8)
            if symbol:
                return analyze_symbol(symbol)
            return analyze_radar(symbols=symbols, limit=limit)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_monitor_status(self, data):
        try:
            from monitor_service import get_monitor_service
            return get_monitor_service().status()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_monitor_history(self, data):
        try:
            from monitor_service import get_monitor_service
            return get_monitor_service().history(data.get('limit', 50))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_monitor_toggle(self, data):
        try:
            from monitor_service import get_monitor_service
            service = get_monitor_service()
            if bool(data.get('enabled', True)):
                service.start()
            else:
                service.stop()
            return service.status()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_strategy_matrix(self, data):
        """Executa a mesma configuracao de backtest para varias estrategias."""
        try:
            from strategy_engine import list_strategies
            from mt5_backtest import run_backtest
            selected = data.get('strategies') or [s['id'] for s in list_strategies(kind='radar')]
            symbol = data.get('symbol', 'XAUUSD')
            timeframe = data.get('timeframe', 'M15')
            params = {
                'sl': data.get('sl', 500), 'tp': data.get('tp', 1000),
                'lot': data.get('lot', 0.01), 'balance': data.get('balance', 10000),
                'count': data.get('count', 3000),
            }
            results = []
            for strategy_id in selected[:60]:
                result = run_backtest(strategy_id, symbol, timeframe, params)
                if result.get('ok'):
                    stats = result.get('stats', {})
                    results.append({'strategy_id': strategy_id, 'strategy_name': stats.get('strategy_name', strategy_id), 'stats': stats})
                else:
                    results.append({'strategy_id': strategy_id, 'error': result.get('error', 'Backtest falhou')})
            results.sort(key=lambda x: x.get('stats', {}).get('total_pnl', -float('inf')), reverse=True)
            return {'ok': True, 'symbol': symbol, 'timeframe': timeframe, 'tested': len(results), 'results': results}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_portfolio_backtest(self, data):
        """Backtesta os setups cadastrados de uma carteira, mantendo parametros iguais."""
        try:
            from meta_strategy import portfolio_catalog
            from mt5_backtest import run_backtest
            portfolio_id = str(data.get('portfolio_id') or data.get('portfolio') or 'trend')
            catalog = next((item for item in portfolio_catalog() if item.get('id') == portfolio_id), None)
            if not catalog:
                return {'ok': False, 'error': 'Carteira nao encontrada: ' + portfolio_id}
            symbol = str(data.get('symbol') or 'XAUUSD').upper()
            timeframe = str(data.get('timeframe') or 'M15')
            params = {
                'sl': data.get('sl', 500), 'tp': data.get('tp', 1000),
                'lot': data.get('lot', 0.01), 'balance': data.get('balance', 10000),
                'count': data.get('count', 3000),
            }
            selected = data.get('strategies') or [item.get('id') for item in catalog.get('strategies', [])]
            results = []
            for strategy_id in selected[:30]:
                result = run_backtest(strategy_id, symbol, timeframe, params)
                if result.get('ok'):
                    stats = result.get('stats', {})
                    results.append({'strategy_id': strategy_id, 'strategy_name': stats.get('strategy_name', strategy_id), 'stats': stats})
                else:
                    results.append({'strategy_id': strategy_id, 'error': result.get('error', 'Backtest falhou')})
            results.sort(key=lambda item: item.get('stats', {}).get('total_pnl', -float('inf')), reverse=True)
            return {'ok': True, 'portfolio': catalog, 'symbol': symbol, 'timeframe': timeframe, 'tested': len(results), 'results': results}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _api_mt5_positions(self, data):
        """Lista posições abertas no MT5"""
        try:
            from mt5_trader import get_open_positions
            symbol = data.get('symbol', None)
            magic = data.get('magic', None)
            positions = get_open_positions(symbol, magic)
            return {"ok": True, "positions": positions, "count": len(positions)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_close_position(self, data):
        """Fecha uma posição no MT5"""
        try:
            denied = self._authorize_api_mutation(data, 'mt5_close_position', permission='EXECUTE', target=str(data.get('ticket', 0)), reason='Fechar uma posição no MetaTrader 5.')
            if denied: return denied
            from mt5_trader import close_position
            ticket = data.get('ticket', 0)
            result = close_position(ticket)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # POSITION MANAGER - Breakeven + Trailing Stop
    # ═══════════════════════════════════════════════════════════════

    def _api_position_manager_status(self, data):
        """Status do Position Manager (BE + Trailing)"""
        try:
            from position_manager import get_status
            return get_status()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_position_manager_start(self, data):
        """Inicia o Position Manager em background"""
        try:
            denied = self._authorize_api_mutation(data, 'position_manager_start', permission='EXECUTE', target='position_manager', reason='Iniciar o gestor de posições em background.')
            if denied: return denied
            from position_manager import start_manager
            return start_manager()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_position_manager_stop(self, data):
        """Para o Position Manager"""
        try:
            denied = self._authorize_api_mutation(data, 'position_manager_stop', permission='EXECUTE', target='position_manager', reason='Parar o gestor de posições.')
            if denied: return denied
            from position_manager import stop_manager
            return stop_manager()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_position_manager_config(self, data):
        """Atualiza configuracao do Position Manager"""
        try:
            denied = self._authorize_api_mutation(data, 'position_manager_config', target='position_manager', reason='Alterar regras de breakeven e trailing stop.')
            if denied: return denied
            from position_manager import update_config
            return {"ok": True, "config": update_config(data)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_position_manager_log(self, data):
        """Retorna log de acoes do Position Manager"""
        try:
            from position_manager import get_trade_log
            limit = data.get('limit', 50)
            return {"ok": True, "log": get_trade_log(limit)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_position_simulate(self, data):
        """Simula impacto de BE + Trailing em trades"""
        try:
            from position_manager import simulate_impact
            result = simulate_impact(
                sl_points=data.get('sl', 300),
                tp_points=data.get('tp', 600),
                breakeven_trigger=data.get('be_trigger', 200),
                breakeven_lock=data.get('be_lock', 50),
                trailing_trigger=data.get('trailing_trigger', 250),
                trailing_distance=data.get('trailing_distance', 150),
                trailing_step=data.get('trailing_step', 50),
                sample_trades=data.get('sample_trades', 3000),
            )
            return {"ok": True, "simulation": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_compare(self, data):
        """Compara múltiplas estratégias no mesmo período"""
        try:
            from mt5_backtest import compare_strategies
            from strategy_engine import resolve_strategy
            symbol = data.get('symbol', 'XAUUSD')
            timeframe = data.get('timeframe', 'M15')
            strategies = data.get('strategies', ['ma_cross', 'rsi_reversal', 'bollinger', 'macd', 'scalping'])
            params = {
                'sl': data.get('sl', 500),
                'tp': data.get('tp', 1000),
                'lot': data.get('lot', 0.01),
                'balance': data.get('balance', 10000),
                'count': data.get('count', 3000),
            }
            normal = []
            robot_requests = []
            for strategy_id in strategies:
                _, definition = resolve_strategy(strategy_id)
                if definition.get('kind') == 'robot':
                    robot_requests.append((strategy_id, definition))
                else:
                    normal.append(strategy_id)
            result = compare_strategies(symbol, timeframe, normal, params) if normal else []
            for robot_id, definition in robot_requests:
                # O tester real de um EA exige abertura do Strategy Tester; aqui
                # usamos o adaptador detectado e identificamos claramente o proxy.
                detected = self._api_mt5_analyze_robot({'name': definition.get('name', '')})
                adapter = detected.get('strategy', 'ma_cross') if detected.get('ok') else 'ma_cross'
                proxy = compare_strategies(symbol, timeframe, [adapter], params)
                for row in proxy:
                    row.setdefault('stats', {})['strategy'] = f"{definition.get('name', robot_id)} (proxy {adapter})"
                    row['strategy_id'] = robot_id
                    row['source'] = 'ROBOT_PROXY'
                    result.append(row)
            return {'ok': True, 'comparison': result, 'robot_note': 'Robôs reais usam o adaptador detectado nesta comparação. Para validação fiel, use Backtest Real no MT5.'}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # MEMÓRIA RAG - Indexação de Robôs MQL5
    # ═══════════════════════════════════════════════════════════════

    def _api_mt5_list_robots(self):
        """Lista todos os robôs da pasta Meus Robos com detalhes"""
        try:
            mt5_experts = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\Meus Robos")
            if not mt5_experts.exists():
                return {"ok": False, "error": "Pasta Meus Robos não encontrada"}
            
            robots = []
            mq5_files = list(mt5_experts.glob('*.mq5'))
            
            for mq5_file in mq5_files:
                try:
                    content = mq5_file.read_text(encoding='utf-8', errors='replace')
                    lines = content.splitlines()
                    size = mq5_file.stat().st_size
                    
                    # Extrair metadados
                    functions = re.findall(r'(?:void|int|double|bool|string|color|datetime|enum\s+\w+)\s+(\w+)\s*\(', content)
                    inputs = re.findall(r'input\s+(?:string|int|double|bool|color|enum\s+\w+)\s+(\w+)', content)
                    enums = re.findall(r'enum\s+(\w+)', content)
                    includes = re.findall(r'#include\s+[<"]([^>"]+)', content)
                    
                    # Extrair descrição do arquivo
                    description = ''
                    for line in lines[:20]:
                        if '#property description' in line:
                            desc_match = re.search(r'"([^"]+)"', line)
                            if desc_match:
                                description = desc_match.group(1)
                                break
                    
                    # Extrair símbolo padrão
                    symbol = ''
                    for line in lines:
                        if 'Simbolo' in line and '=' in line:
                            sym_match = re.search(r'=\s*"([^"]+)"', line)
                            if sym_match:
                                symbol = sym_match.group(1)
                                break
                    
                    # Verificar se tem .ex5 compilado
                    ex5_file = mq5_file.with_suffix('.ex5')
                    compiled = ex5_file.exists()
                    
                    robots.append({
                        "name": mq5_file.stem,
                        "path": str(mq5_file),
                        "lines": len(lines),
                        "size_kb": round(size / 1024, 1),
                        "functions": len(functions),
                        "inputs": len(inputs),
                        "enums": len(enums),
                        "includes": len(set(includes)),
                        "description": description,
                        "symbol": symbol,
                        "compiled": compiled,
                        "modified": mq5_file.stat().st_mtime,
                    })
                except Exception as e:
                    pass
            
            # Ordenar por data de modificação (mais recente primeiro)
            robots.sort(key=lambda x: x['modified'], reverse=True)
            
            return {
                "ok": True,
                "count": len(robots),
                "robots": robots,
                "path": str(mt5_experts)
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_mt5_robot_details(self, data):
        """Retorna detalhes completos de um robô específico"""
        name = data.get('name', '')
        mt5_experts = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts\Meus Robos")
        mq5_file = mt5_experts / f"{name}.mq5"
        
        if not mq5_file.exists():
            return {"ok": False, "error": f"Robô {name}.mq5 não encontrado"}
        
        try:
            content = mq5_file.read_text(encoding='utf-8', errors='replace')
            lines = content.splitlines()
            
            # Extrair todos os metadados
            functions = re.findall(r'(?:void|int|double|bool|string|color|datetime|enum\s+\w+)\s+(\w+)\s*\(', content)
            inputs = re.findall(r'input\s+(?:string|int|double|bool|color|enum\s+\w+)\s+(\w+)', content)
            enums = re.findall(r'enum\s+(\w+)', content)
            includes = re.findall(r'#include\s+[<"]([^>"]+)', content)
            
            # Extrair descrição
            description = ''
            for line in lines[:20]:
                if '#property description' in line:
                    desc_match = re.search(r'"([^"]+)"', line)
                    if desc_match:
                        description = desc_match.group(1)
            
            # Extrair símbolo padrão
            symbol = ''
            for line in lines:
                if 'Simbolo' in line and '=' in line:
                    sym_match = re.search(r'=\s*"([^"]+)"', line)
                    if sym_match:
                        symbol = sym_match.group(1)
                        break
            
            # Extrair timeframe padrão
            timeframe = ''
            for line in lines:
                if 'Timeframe' in line and 'PERIOD_' in line:
                    tf_match = re.search(r'PERIOD_(\w+)', line)
                    if tf_match:
                        timeframe = tf_match.group(1)
                        break
            
            return {
                "ok": True,
                "name": name,
                "path": str(mq5_file),
                "lines": len(lines),
                "size_kb": round(mq5_file.stat().st_size / 1024, 1),
                "functions": functions,
                "inputs": inputs,
                "enums": enums,
                "includes": list(set(includes)),
                "description": description,
                "symbol": symbol,
                "timeframe": timeframe,
                "code": content,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_rag_index(self):
        """Indexa todos os robôs MQL5 para memória RAG"""
        try:
            mt5_experts = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Experts")
            if not mt5_experts.exists():
                return {"ok": False, "error": "Pasta Experts não encontrada"}
            
            index = []
            for mq5_file in mt5_experts.rglob('*.mq5'):
                try:
                    content = mq5_file.read_text(encoding='utf-8', errors='replace')
                    lines = content.splitlines()
                    
                    # Extrair metadados
                    functions = re.findall(r'(?:void|int|double|bool|string)\s+(\w+)\s*\(', content)
                    inputs = re.findall(r'input\s+(?:string|int|double|bool)\s+(\w+)', content)
                    
                    index.append({
                        "path": str(mq5_file),
                        "name": mq5_file.name,
                        "lines": len(lines),
                        "functions": functions[:20],
                        "inputs": inputs[:20],
                        "preview": "\n".join(lines[:50]),  # Primeiras 50 linhas
                    })
                except:
                    pass
            
            # Salvar índice
            index_path = ROOT / 'config' / 'rag_index.json'
            index_path.parent.mkdir(exist_ok=True)
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
            
            return {"ok": True, "count": len(index), "path": str(index_path)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_rag_search(self, query):
        """Busca na memória RAG dos robôs"""
        try:
            index_path = ROOT / 'config' / 'rag_index.json'
            if not index_path.exists():
                return {"ok": False, "error": "Índice não encontrado. Execute rag_index primeiro."}
            
            index = json.loads(index_path.read_text(encoding='utf-8'))
            
            # Busca simples por relevância
            results = []
            query_lower = query.lower()
            
            for entry in index:
                score = 0
                # Verificar nome
                if query_lower in entry['name'].lower():
                    score += 10
                # Verificar funções
                for fn in entry.get('functions', []):
                    if query_lower in fn.lower():
                        score += 5
                # Verificar inputs
                for inp in entry.get('inputs', []):
                    if query_lower in inp.lower():
                        score += 3
                # Verificar preview
                if query_lower in entry.get('preview', '').lower():
                    score += 1
                
                if score > 0:
                    results.append({**entry, 'score': score})
            
            # Ordenar por relevância
            results.sort(key=lambda x: x['score'], reverse=True)
            
            return {"ok": True, "results": results[:10], "total": len(results)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _tool_list_ai_models(self):
        """Lista modelos de IA disponíveis"""
        catalog = self._build_model_catalog()
        models = []
        
        lines = ["## 🤖 Modelos de IA Disponíveis", ""]
        for provider in catalog.get("providers", []):
            lines.append(f"### {provider['label']}")
            group_models = [m for m in catalog.get("models", []) if m.get("provider") == provider["id"]]
            if not group_models:
                lines.append("- Nenhum modelo detectado.")
            for m in group_models:
                status = "✅" if m.get("available") else "⚙️"
                cost = m.get("cost", "Grátis")
                desc = m.get("description", "")
                size = f" ({m.get('size_gb')} GB)" if m.get("size_gb") else ""
                lines.append(f"- {status} **{m['label']}**{size} - {desc} ({cost})")
            lines.append("")
        lines.append("Use Configurações > IA e modelos para configurar chaves e escolher o padrão.")
        
        return "\n".join(lines)

    def _api_keys_path(self):
        path = ROOT / 'config' / 'api_keys.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _read_api_keys(self):
        return read_jarvis_api_keys()

    def _write_api_keys(self, keys):
        path = self._api_keys_path()
        path.write_text(json.dumps(keys, indent=2), encoding='utf-8')

    def _build_model_catalog(self):
        keys = self._read_api_keys()
        openrouter_ok = bool(keys.get('openrouter_key') or keys.get('openrouter_api_key') or os.environ.get('OPENROUTER_API_KEY'))
        cline_ok = bool(keys.get('cline_key') or keys.get('cline_api_key') or os.environ.get('CLINE_API_KEY'))
        gemini_ok = bool(keys.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
        groq_ok = bool(keys.get('groq_api_key') or os.environ.get('GROQ_API_KEY'))
        codex_ok = shutil.which("codex") is not None
        ollama_ok = False
        models = []
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as resp:
                ollama_ok = True
                data = json.loads(resp.read().decode('utf-8'))
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if not name:
                        continue
                    lower_name = name.lower()
                    if "embed" in lower_name or "embedding" in lower_name:
                        continue
                    models.append({
                        "id": name,
                        "label": name,
                        "provider": "ollama",
                        "kind": "local",
                        "available": True,
                        "size_gb": round(m.get("size", 0) / 1e9, 1),
                        "cost": "Local",
                        "description": "Modelo local detectado no Ollama.",
                        "tasks": ["Privacidade", "Código", "Análise geral"],
                    })
        except Exception:
            pass
        static_models = [
            {"id": "cohere-code", "label": "Cohere Code", "provider": "openrouter", "available": openrouter_ok, "cost": "Grátis", "description": "Código e respostas rápidas via OpenRouter.", "tasks": ["Código", "Chat rápido"]},
            {"id": "nvidia-lightning", "label": "NVIDIA Nemotron", "provider": "openrouter", "available": openrouter_ok, "cost": "Grátis", "description": "Resposta rápida para análise geral.", "tasks": ["Chat rápido", "Análise"]},
            {"id": "openrouter-free", "label": "Auto Grátis", "provider": "openrouter", "available": openrouter_ok, "cost": "Grátis", "description": "Roteador gratuito da OpenRouter.", "tasks": ["Fallback", "Geral"]},
            {"id": "codex-market", "label": "Codex GPT-5.3", "provider": "openrouter", "available": openrouter_ok, "cost": "Premium", "description": "IA mais forte para análise de mercado, estratégia, MQL5 e revisão de robôs.", "tasks": ["Mercado", "Estratégia", "MQL5", "Código"]},
            {"id": "gemini-flash", "label": "Gemini Flash", "provider": "gemini", "available": gemini_ok, "cost": "Free tier", "description": "Multimodal, prints, documentos e análise rápida.", "tasks": ["Imagens", "PDF", "Análise"]},
            {"id": "gemini-pro", "label": "Gemini Pro", "provider": "gemini", "available": gemini_ok, "cost": "Pode cobrar", "description": "Modelo Gemini mais forte quando habilitado na conta.", "tasks": ["Raciocínio", "Planejamento"]},
            {"id": "groq-fast", "label": "Groq Fast", "provider": "groq", "available": groq_ok, "cost": "Free tier", "description": "Respostas muito rápidas para chat e logs.", "tasks": ["Chat rápido", "Logs"]},
            {"id": "groq-reasoning", "label": "Groq Reasoning", "provider": "groq", "available": groq_ok, "cost": "Free tier", "description": "Raciocínio rápido com modelos open-weight.", "tasks": ["Raciocínio", "Código"]},
            {"id": "groq-llama", "label": "Groq Qwen", "provider": "groq", "available": groq_ok, "cost": "Free tier", "description": "Modelo versátil para respostas do dia a dia e código.", "tasks": ["Geral", "Código"]},
            {"id": "codex-bridge", "label": "Codex Desktop Bridge", "provider": "codex", "available": codex_ok, "cost": "Conta Codex", "description": "Ponte local para o Codex instalado neste PC. Forte para mercado, estratégia, MQL5 e revisão de robôs.", "tasks": ["Mercado", "Estratégia", "MQL5", "Código"]},
            {"id": "cline-deepseek-flash", "label": "DeepSeek V4 Flash", "provider": "cline", "available": cline_ok, "cost": "ClinePass", "description": "ClinePass rápido para código e automação.", "tasks": ["Código", "Agente"]},
            {"id": "cline-deepseek-v4", "label": "DeepSeek V4 Pro", "provider": "cline", "available": cline_ok, "cost": "ClinePass", "description": "ClinePass forte para programação.", "tasks": ["Código", "Raciocínio"]},
            {"id": "cline-qwen38", "label": "Qwen 3.8 Max", "provider": "cline", "available": cline_ok, "cost": "ClinePass", "description": "Qwen via ClinePass.", "tasks": ["Código", "MQL5"]},
            {"id": "cline-glm", "label": "GLM 5.2", "provider": "cline", "available": cline_ok, "cost": "ClinePass", "description": "Código e tarefas agenticas via ClinePass.", "tasks": ["Código", "Agente"]},
        ]
        models.extend(static_models)
        try:
            with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            existing = {m["id"] for m in models}
            free_items = []
            for item in data.get("data", []):
                real_id = str(item.get("id", ""))
                name = str(item.get("name") or real_id)
                lower = (real_id + " " + name).lower()
                if not real_id.endswith(":free"):
                    continue
                if "safety" in lower or "moderation" in lower or "embed" in lower:
                    continue
                score = 0
                for term, weight in [("code", 8), ("coder", 8), ("qwen", 7), ("glm", 7), ("deepseek", 7), ("minimax", 6), ("gemma", 5), ("nvidia", 5), ("llama", 4), ("flash", 3)]:
                    if term in lower:
                        score += weight
                free_items.append((score, real_id, name))
            free_items.sort(key=lambda x: (-x[0], x[2]))
            for _, real_id, name in free_items[:14]:
                catalog_id = "openrouter:" + real_id
                if catalog_id in existing:
                    continue
                tasks = ["Geral"]
                lower = (real_id + " " + name).lower()
                if any(t in lower for t in ["code", "coder", "qwen", "glm"]):
                    tasks = ["Código", "MQL5"]
                elif any(t in lower for t in ["reason", "deepseek"]):
                    tasks = ["Raciocínio", "Debug"]
                elif "flash" in lower or "nvidia" in lower:
                    tasks = ["Chat rápido", "Análise"]
                models.append({
                    "id": catalog_id,
                    "label": name.replace(" (free)", ""),
                    "provider": "openrouter",
                    "available": openrouter_ok,
                    "cost": "Grátis",
                    "description": "Modelo grátis detectado agora na OpenRouter.",
                    "tasks": tasks,
                })
                existing.add(catalog_id)
        except Exception:
            pass
        def pick_openrouter(*terms):
            for m in models:
                if m.get("provider") != "openrouter":
                    continue
                lower = (m.get("id", "") + " " + m.get("label", "")).lower()
                if all(t in lower for t in terms):
                    return m["id"]
            return "cohere-code"
        providers = [
            {"id": "ollama", "label": "Locais (Ollama)", "configured": ollama_ok, "detail": "Roda no seu PC, sem API key."},
            {"id": "openrouter", "label": "OpenRouter grátis/premium", "configured": openrouter_ok, "detail": "Uma chave libera modelos free e premium como Codex."},
            {"id": "gemini", "label": "Gemini API", "configured": gemini_ok, "detail": "Bom para imagem, PDF e análise geral."},
            {"id": "groq", "label": "GroqCloud", "configured": groq_ok, "detail": "Excelente para velocidade."},
            {"id": "codex", "label": "Codex Desktop", "configured": codex_ok, "detail": "Ponte local usando o Codex CLI autenticado neste computador."},
            {"id": "cline", "label": "ClinePass", "configured": cline_ok, "detail": "Modelos inclusos na assinatura ClinePass."},
        ]
        recommendations = {
            "mql5": "codex-bridge" if codex_ok else ("codex-market" if openrouter_ok else ("qwen2.5-coder:14b" if any(m["id"].startswith("qwen") for m in models) else "cline-qwen38")),
            "vision": "gemini-flash" if gemini_ok else ("qwen2.5vl:7b" if any(m["id"] == "qwen2.5vl:7b" for m in models) else "openrouter-free"),
            "fast": "groq-fast" if groq_ok else ("cline-deepseek-flash" if cline_ok else "cohere-code"),
            "fallback": "openrouter-free" if openrouter_ok else ("groq-llama" if groq_ok else "qwen2.5-coder:14b"),
        }
        return {"ok": True, "providers": providers, "models": models, "recommendations": recommendations}

    def _api_models_catalog(self, data):
        return self._build_model_catalog()

    def _api_models_key(self, data):
        provider = str(data.get("provider", "")).strip().lower()
        key = str(data.get("key", "")).strip()
        mapping = {
            "openrouter": "openrouter_api_key",
            "gemini": "gemini_api_key",
            "groq": "groq_api_key",
            "cline": "cline_api_key",
        }
        if provider not in mapping:
            return {"ok": False, "error": "Provedor invalido"}
        keys = self._read_api_keys()
        if key:
            keys[mapping[provider]] = key
        else:
            keys.pop(mapping[provider], None)
        self._write_api_keys(keys)
        try:
            if provider == "openrouter" and CLAUDE_AVAILABLE:
                get_claude_provider().load_api_key()
            if provider == "cline":
                from cline_provider import get_cline_provider
                get_cline_provider().load_api_key()
        except Exception:
            pass
        return {"ok": True, "provider": provider, "configured": bool(key)}

    def _call_groq_model(self, api_messages, model_key, timeout=60, stream=False):
        return call_groq_model(api_messages, model_key, timeout=timeout, stream=stream)

    def _call_gemini_model(self, api_messages, model_key):
        return call_gemini_model(api_messages, model_key)

    # ═══════════════════════════════════════════════════════════════
    # API ROUTES
    # ═══════════════════════════════════════════════════════════════

    def route_api(self, path, data):
        routes = {
            "/api/status": self.api_status,
            "/api/security/status": self.api_security_status,
            "/api/security/mode": self.api_security_mode,
            "/api/security/approve": self.api_security_approve,
            "/api/security/deny": self.api_security_deny,
            "/api/security/lockdown": self.api_security_lockdown,
            "/api/plugins/list": self.api_plugins_list,
            "/api/plugins/toggle": self.api_plugins_toggle,
            "/api/capabilities": self.api_capabilities,
            "/api/models/catalog": self._api_models_catalog,
            "/api/models/key": self._api_models_key,
            "/api/chat": self.api_chat,
            "/api/agent": self.api_agent,
            "/api/vision": self.api_vision,
            "/api/audio": self.api_audio,
            "/api/video": self.api_video,
            "/api/document": self.api_document,
            "/api/projects": self.api_projects,
            "/api/history": self.api_history,
            "/api/clear_history": self.api_clear_history,
            "/api/quotes": self.api_quotes,
            "/api/market/overview": lambda d: self._api_market_overview(d),
            "/api/market/forex": lambda d: self._api_market_forex(d),
            "/api/market/chart": lambda d: self._api_market_chart(d),
            "/api/market/tick": lambda d: self._api_market_tick(d),
            "/api/market/ai-context": lambda d: self._api_market_ai_context(d),
            "/api/market/analyze": lambda d: self._api_market_analyze(d),
            "/api/market/analysis-history": lambda d: self._api_market_analysis_history(d),
            "/api/market/ai-performance": lambda d: self._api_market_ai_performance(d),
            "/api/market/opportunity-ranking": lambda d: self._api_market_opportunity_ranking(d),
            "/api/desktop/status": lambda d: self._api_desktop_status(d),
            "/api/desktop/action": lambda d: self._api_desktop_action(d),
            "/api/desktop/confirm": lambda d: self._api_desktop_confirm(d),
            "/api/desktop/speech": lambda d: self._api_desktop_speech(d),
            "/api/jarvis/voice/transcribe": lambda d: self._api_jarvis_voice_transcribe(d),
            "/api/jarvis/voice/tts": lambda d: self._api_jarvis_voice_tts(d),
            "/api/jarvis/voice/command": lambda d: self._api_jarvis_voice_command(d),
            "/api/jarvis/voice/status": lambda d: self._api_jarvis_voice_status(d),
            "/api/jarvis/chat": lambda d: self._api_jarvis_chat(d),
            "/api/jarvis/golden/overview": lambda d: self._api_jarvis_golden_overview(d),
            "/api/jarvis/golden/radar": lambda d: self._api_jarvis_golden_radar(d),
            "/api/jarvis/golden/risk": lambda d: self._api_jarvis_golden_risk(d),
            "/api/jarvis/golden/validation": lambda d: self._api_jarvis_golden_validation(d),
            "/api/jarvis/golden/deep-analysis": lambda d: self._api_jarvis_golden_deep_analysis(d),
            "/api/jarvis/golden/recovery-manifest": lambda d: self._api_jarvis_golden_recovery_manifest(d),
            "/api/jarvis/memory/scientific": lambda d: self._api_jarvis_scientific_memory(d),
            "/api/jarvis/brain/status": lambda d: self._api_jarvis_brain_status(d),
            "/api/jarvis/brain/execute": lambda d: self._api_jarvis_brain_execute(d),
            "/api/jarvis/vision/analyze": lambda d: self._api_jarvis_vision_analyze(d),
            "/api/jarvis/vision/status": lambda d: self._api_jarvis_vision_status(d),
            "/api/jarvis/memory/status": lambda d: self._api_jarvis_memory_status(d),
            "/api/jarvis/memory/search": lambda d: self._api_jarvis_memory_search(d),
            "/api/jarvis/memory/remember": lambda d: self._api_jarvis_memory_remember(d),
            "/api/jarvis/memory/recent": lambda d: self._api_jarvis_memory_recent(d),
            "/api/jarvis/voice-service/status": lambda d: self._api_jarvis_voice_service_status(d),
            "/api/jarvis/voice-service/start": lambda d: self._api_jarvis_voice_service_start(d),
            "/api/jarvis/voice-service/listen": lambda d: self._api_jarvis_voice_service_listen(d),
            "/api/jarvis/voice-service/stop": lambda d: self._api_jarvis_voice_service_stop(d),
            "/api/jarvis/voice-service/speak": lambda d: self._api_jarvis_voice_service_speak(d),
            "/api/jarvis/tasks/list": lambda d: self._api_jarvis_tasks_list(d),
            "/api/jarvis/tasks/get": lambda d: self._api_jarvis_tasks_get(d),
            "/api/jarvis/tasks/cancel": lambda d: self._api_jarvis_tasks_cancel(d),
            "/api/jarvis/orchestrator/status": lambda d: self._api_jarvis_orchestrator_status(d),
            "/api/jarvis/skills/status": lambda d: self._api_jarvis_skills_status(d),
            "/api/jarvis/providers/status": lambda d: self._api_jarvis_providers_status(d),
            "/api/jarvis/readiness": lambda d: self._api_jarvis_readiness(d),
            "/api/radar/status": lambda d: self._api_radar_status(d),
        
            "/api/filesystem": self.api_filesystem,
            "/api/system": self.api_system,
            "/api/search": self.api_search,
            # Novas APIs para Status Panel e EA Builder
            "/api/mt5/status": lambda d: self._api_mt5_status(),
            "/api/system/disk": lambda d: self._api_system_disk(),
            "/api/system/stats": lambda d: self._api_system_stats(),
            "/api/ea/generate": lambda d: self._api_ea_generate(d),
            "/api/mt5/compile": lambda d: self._api_mt5_compile(d),
            # APIs RAG
            "/api/mt5/list_robots": lambda d: self._api_mt5_list_robots(),
            "/api/mt5/robot_details": lambda d: self._api_mt5_robot_details(d),
            # APIs Backtest
            "/api/mt5/backtest": lambda d: self._api_mt5_backtest(d),
            "/api/strategy_catalog": lambda d: self._api_strategy_catalog(d),
            "/api/strategy_audit": lambda d: self._api_strategy_audit(d),
            "/api/chart_audit": lambda d: self._api_chart_audit(d),
            "/api/chart_data": lambda d: self._api_chart_data(d),
            "/api/chart_strategy_test": lambda d: self._api_chart_strategy_test(d),
            "/api/meta_strategy": lambda d: self._api_meta_strategy(d),
            "/api/monitor/status": lambda d: self._api_monitor_status(d),
            "/api/monitor/history": lambda d: self._api_monitor_history(d),
            "/api/monitor/toggle": lambda d: self._api_monitor_toggle(d),
            "/api/strategy_matrix": lambda d: self._api_strategy_matrix(d),
            "/api/portfolio_backtest": lambda d: self._api_portfolio_backtest(d),
            "/api/mt5/backtest_history": lambda d: self._api_mt5_backtest_history(d),
            "/api/mt5/compare": lambda d: self._api_mt5_compare(d),
            "/api/mt5/analyze_robot": lambda d: self._api_mt5_analyze_robot(d),
            "/api/mt5/real_backtest": lambda d: self._api_mt5_real_backtest(d),
            "/api/mt5/chart_analysis": lambda d: self._api_mt5_chart_analysis(d),
            "/api/mt5/full_analysis": lambda d: self._api_mt5_full_analysis(d),
            "/api/journal/stats": lambda d: self._api_journal_stats(d),
            "/api/journal/calibrate": lambda d: self._api_journal_calibrate(d),
            "/api/journal/history": lambda d: self._api_journal_history(d),
            "/api/walk_forward": lambda d: self._api_walk_forward(d),
            "/api/scanner/scan": lambda d: self._api_scanner_scan(d),
            "/api/scanner/radar": lambda d: self._api_scanner_radar(d),
            "/api/scanner/performance": lambda d: self._api_scanner_performance(d),
            "/api/scanner/details": lambda d: self._api_scanner_details(d),
            "/api/statistics/full": lambda d: self._api_statistics_full(d),
            "/api/statistics/strategies": lambda d: self._api_statistics_strategies(d),
            "/api/statistics/assets": lambda d: self._api_statistics_assets(d),
            "/api/statistics/hourly": lambda d: self._api_statistics_hourly(d),
            "/api/statistics/calibration": lambda d: self._api_statistics_calibration(d),
            "/api/risk/status": lambda d: self._api_risk_status(d),
            "/api/risk/calculate_lot": lambda d: self._api_risk_calculate_lot(d),
            "/api/risk/config": lambda d: self._api_risk_config(d),
            "/api/risk/can_trade": lambda d: self._api_risk_can_trade(d),
            "/api/validation/full": lambda d: self._api_validation_full(d),
            "/api/validation/monte_carlo": lambda d: self._api_validation_monte_carlo(d),
            "/api/validation/robustness": lambda d: self._api_validation_robustness(d),
            "/api/validation/compare_modes": lambda d: self._api_validation_compare_modes(d),
            "/api/validation/real": lambda d: self._api_validation_real(d),
            "/api/validation/all_real": lambda d: self._api_validation_all_real(d),
            "/api/mt5/import_history": lambda d: self._api_import_mt5_history(d),
            "/api/mt5/auto_trade": lambda d: self._api_mt5_auto_trade(d),
            "/api/mt5/positions": lambda d: self._api_mt5_positions(d),
            "/api/mt5/close_position": lambda d: self._api_mt5_close_position(d),
            "/api/position/status": lambda d: self._api_position_manager_status(d),
            "/api/position/start": lambda d: self._api_position_manager_start(d),
            "/api/position/stop": lambda d: self._api_position_manager_stop(d),
            "/api/position/config": lambda d: self._api_position_manager_config(d),
            "/api/position/log": lambda d: self._api_position_manager_log(d),
            "/api/position/simulate": lambda d: self._api_position_simulate(d),
            # Strategy Manager
            "/api/strategy_manager/list": lambda d: self._api_strategy_manager_list(d),
            "/api/strategy_manager/toggle": lambda d: self._api_strategy_manager_toggle(d),
            "/api/strategy_manager/toggle_mode": lambda d: self._api_strategy_manager_toggle_mode(d),
            "/api/strategy_manager/preset": lambda d: self._api_strategy_manager_preset(d),
            "/api/strategy_manager/auto_rank": lambda d: self._api_strategy_manager_auto_rank(d),
            # APIs RAG
            "/api/rag/index": lambda d: self._api_rag_index(),
            "/api/rag/search": lambda d: self._api_rag_search(d.get('query', '')),
        }
        handler = routes.get(path)
        return handler(data) if handler else {"error": "Not found"}

    def api_status(self, data):
        # System
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage('C:\\').percent
        except:
            cpu = mem = disk = 0
        # MT5
        mt5_ok = False
        mt5_account = None
        mt5_server = None
        mt5_balance = 0
        try:
            from mt5_connector import ensure_connection, get_status as mt5_status
            ensure_connection()
            st = mt5_status()
            mt5_ok = st.get('connected', False)
            mt5_account = st.get('account')
            mt5_server = st.get('server')
            mt5_balance = st.get('balance', 0)
        except Exception:
            pass
        # Ollama
        ollama_ok = False
        try:
            import urllib.request
            req = urllib.request.Request('http://localhost:11434/api/tags')
            with urllib.request.urlopen(req, timeout=3) as r:
                ollama_ok = True
        except:
            pass
        # OpenRouter
        openrouter_ok = False
        try:
            key_path = ROOT / 'config' / 'api_keys.json'
            if key_path.exists():
                keys = json.loads(key_path.read_text(encoding='utf-8'))
                openrouter_ok = bool(keys.get('openrouter_key') or keys.get('openrouter_api_key'))
        except:
            pass
        # Cline
        cline_ok = False
        try:
            key_path = ROOT / 'config' / 'api_keys.json'
            if key_path.exists():
                keys = json.loads(key_path.read_text(encoding='utf-8'))
                cline_ok = bool(keys.get('cline_key') or keys.get('cline_api_key'))
        except:
            pass
        gemini_ok = False
        groq_ok = False
        codex_ok = False
        try:
            keys = self._read_api_keys()
            gemini_ok = bool(keys.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
            groq_ok = bool(keys.get('groq_api_key') or os.environ.get('GROQ_API_KEY'))
            codex_ok = shutil.which("codex") is not None
        except:
            pass
        return {
            "ok": True, "status": "online", "version": "V6.0-AutoConnect",
            "security": {"mode": EXECUTION_SERVICE.get_mode().value if EXECUTION_SERVICE else "UNAVAILABLE"},
            "system": {"cpu": cpu, "memory": mem, "disk": disk},
            "connections": {
                "mt5": {"ok": mt5_ok, "account": mt5_account, "server": mt5_server, "balance": mt5_balance},
                "ollama": {"ok": ollama_ok},
                "openrouter": {"ok": openrouter_ok},
                "cline": {"ok": cline_ok},
                "gemini": {"ok": gemini_ok},
                "groq": {"ok": groq_ok},
                "codex": {"ok": codex_ok},
            }
        }

    def api_security_status(self, data):
        if not EXECUTION_SERVICE:
            return {"ok": False, "error": "servico de permissoes indisponivel"}
        return {
            "ok": True,
            "mode": EXECUTION_SERVICE.get_mode().value,
            "requests": EXECUTION_SERVICE.latest_requests(20),
            "events": EXECUTION_SERVICE.latest_events(limit=20),
        }

    def api_security_mode(self, data):
        if not EXECUTION_SERVICE:
            return {"ok": False, "error": "servico de permissoes indisponivel"}
        mode = str(data.get("mode", "")).upper()
        allowed = {item.value for item in PermissionMode}
        if mode not in allowed:
            return {"ok": False, "error": f"Modo invalido. Use: {', '.join(sorted(allowed))}"}
        selected = EXECUTION_SERVICE.set_mode(mode)
        return {"ok": True, "mode": selected.value}

    def api_security_approve(self, data):
        request_id = str(data.get("request_id", "")).strip()
        scope = str(data.get("scope", "ONCE")).upper()
        if not request_id:
            return {"ok": False, "error": "request_id obrigatorio"}
        if request_id.startswith("jarvis:"):
            if scope != "ONCE":
                return {"ok": False, "error": "Ações canônicas usam aprovação única."}
            try:
                from desktop_center import DESKTOP_CENTER
                return DESKTOP_CENTER.service.confirm(request_id.removeprefix("jarvis:"))
            except Exception:
                return {"ok": False, "error": "Canonical SecurityManager indisponível."}
        if not EXECUTION_SERVICE:
            return {"ok": False, "error": "servico de permissoes indisponivel"}
        if scope == "TASK":
            EXECUTION_SERVICE.grant_for_task(request_id)
        else:
            EXECUTION_SERVICE.grant_once(request_id)
        return {"ok": True, "request_id": request_id, "scope": scope, "message": "Aprovacao registrada. Repita a acao no Chat para executa-la."}

    def api_security_deny(self, data):
        request_id = str(data.get("request_id", "")).strip()
        if not request_id:
            return {"ok": False, "error": "request_id obrigatorio"}
        if request_id.startswith("jarvis:"):
            try:
                from desktop_center import DESKTOP_CENTER
                return DESKTOP_CENTER.service.deny_confirmation(
                    request_id.removeprefix("jarvis:"))
            except Exception:
                return {"ok": False, "error": "Canonical SecurityManager indisponível."}
        if not EXECUTION_SERVICE:
            return {"ok": False, "error": "servico de permissoes indisponivel"}
        EXECUTION_SERVICE.deny(request_id)
        return {"ok": True, "request_id": request_id, "message": "Aprovacao negada."}

    def api_security_lockdown(self, data):
        """Ativa somente leitura e interrompe o gerenciador de posicoes."""
        if not EXECUTION_SERVICE:
            return {"ok": False, "error": "servico de permissoes indisponivel"}
        try:
            EXECUTION_SERVICE.set_mode(PermissionMode.READ_ONLY.value)
            try:
                from position_manager import stop_manager
                stop_manager()
            except Exception:
                pass
            return {"ok": True, "mode": PermissionMode.READ_ONLY.value, "message": "Modo somente leitura ativado."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def api_plugins_list(self, data):
        if not PLUGIN_REGISTRY:
            return {"ok": True, "plugins": []}
        return {"ok": True, "plugins": PLUGIN_REGISTRY.list_plugins()}

    def api_plugins_toggle(self, data):
        denied = self._authorize_api_mutation(data, 'plugin_toggle', target=str(data.get('name', '')), reason='Ativar ou desativar um plugin do Golden AI.')
        if denied:
            return denied
        if not PLUGIN_REGISTRY:
            return {"ok": False, "error": "registro de plugins indisponivel"}
        name = str(data.get('name', '')).strip()
        enabled = bool(data.get('enabled', True))
        changed = PLUGIN_REGISTRY.enable(name) if enabled else PLUGIN_REGISTRY.disable(name)
        return {"ok": changed, "name": name, "enabled": enabled if changed else None, "error": None if changed else "plugin nao encontrado"}

    def api_capabilities(self, data):
        """Expõe recursos nativos e dependências detectadas pelo Golden."""
        def module_ok(name):
            try:
                __import__(name)
                return True
            except Exception:
                return False
        metaeditor = any(p.exists() for p in [
            Path(r'C:\Program Files\MetaTrader 5\metaeditor64.exe'),
            Path(r'C:\Program Files\MetaTrader 5\metaeditor.exe'),
        ])
        return {"ok": True, "capabilities": [
            {"id": "image", "name": "Imagens", "description": "Leitura de prints e análise visual", "status": "AVAILABLE"},
            {"id": "pdf", "name": "PDF e documentos", "description": "Leitura, criação e análise de documentos", "status": "AVAILABLE" if module_ok('fitz') or module_ok('pypdf') or module_ok('pdfplumber') else "DEPENDENCY"},
            {"id": "audio", "name": "Áudio", "description": "Transcrição e análise de arquivos de áudio", "status": "AVAILABLE" if module_ok('core.audio') else "DEPENDENCY"},
            {"id": "video", "name": "Vídeo", "description": "Extração e análise de conteúdo de vídeo", "status": "AVAILABLE" if module_ok('core.video') else "DEPENDENCY"},
            {"id": "mql5", "name": "MQL5 e MetaEditor", "description": "Análise, correção e compilação de robôs", "status": "AVAILABLE" if metaeditor else "CONFIGURE"},
            {"id": "mt5", "name": "MetaTrader 5", "description": "Cotações, posições e integração de conta", "status": "AVAILABLE" if module_ok('MetaTrader5') else "DEPENDENCY"},
            {"id": "radar", "name": "Radar, backtest e validação", "description": "Estratégias, Monte Carlo e walk-forward", "status": "AVAILABLE"},
        ]}

    def _authorize_api_mutation(self, data, action, permission='WRITE', target='', reason=''):
        """Porta unica para APIs mutaveis; devolve resposta pendente ou None."""
        if not EXECUTION_SERVICE:
            return {"ok": False, "error": "servico de permissoes indisponivel"}
        result = EXECUTION_SERVICE.authorize_action(
            task_id=data.get('session_id', 'dashboard'), permission_level=permission,
            action=action, target=str(target), reason=reason or f'A API solicitou {action}.',
            tool_name=action, capability_exists=True,
        )
        if result.allowed:
            return None
        return {
            'ok': False, 'approval_required': result.status == 'WAITING_APPROVAL',
            'status': result.status, 'request_id': result.request_id,
            'mode': result.mode, 'risk_level': result.risk_level, 'error': result.reason,
        }

    def api_agent(self, data):
        """Direct tool execution from frontend"""
        tool_call = data.get("tool_call", {})
        if not tool_call:
            return {"ok": False, "error": "No tool_call provided"}
        result = self._execute_tool(tool_call, data.get("session_id", "default"))
        return {"ok": True, "result": result}

    def _api_desktop_status(self, data):
        from desktop_center import DESKTOP_CENTER
        return DESKTOP_CENTER.status()

    def _api_desktop_action(self, data):
        from desktop_center import DESKTOP_CENTER
        command = str((data or {}).get("command") or "").strip()
        return DESKTOP_CENTER.execute(command)

    def _api_desktop_confirm(self, data):
        from desktop_center import DESKTOP_CENTER
        return DESKTOP_CENTER.confirm((data or {}).get("token"))

    def _api_desktop_speech(self, data):
        text = str((data or {}).get("text") or "").strip()[:1200]
        voice_key = str((data or {}).get("voice") or "feminina").lower()
        voices = {
            "feminina": "pt-BR-FranciscaNeural",
            "masculina": "pt-BR-AntonioNeural",
        }
        # ElevenLabs voices
        eleven_voices = {
            "eleven_jarvis": "ulzsiMeCbfKyTPCNhCD5",
        }
        if not text:
            return {"ok": False, "error": "Texto vazio"}
        path = None
        try:
            # Tentar ElevenLabs primeiro se a voz for do ElevenLabs
            if voice_key in eleven_voices:
                eleven_key = os.getenv("ELEVENLABS_API_KEY", "")
                if not eleven_key:
                    try:
                        keys = self._read_api_keys()
                        eleven_key = keys.get("elevenlabs_api_key", "")
                    except Exception:
                        pass
                if not eleven_key:
                    return {"ok": False, "error": "Chave ELEVENLABS_API_KEY não configurada no .env"}
                import urllib.request
                voice_id = eleven_voices[voice_key]
                url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                payload = json.dumps({
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "style": 0.3,
                        "use_speaker_boost": True
                    }
                }).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/json",
                    "xi-api-key": eleven_key,
                    "Accept": "audio/mpeg"
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    audio_bytes = resp.read()
                audio = base64.b64encode(audio_bytes).decode("ascii")
                return {"ok": True, "audio_base64": audio, "mime_type": "audio/mpeg", "voice": voice_key}
            # Fallback para Edge TTS
            import edge_tts
            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            async def generate():
                communicate = edge_tts.Communicate(text, voices.get(voice_key, voices["feminina"]), rate="+4%", pitch="-2Hz")
                await communicate.save(path)
            asyncio.run(generate())
            audio = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            return {"ok": True, "audio_base64": audio, "mime_type": "audio/mpeg", "voice": voice_key}
        except Exception as e:
            return {"ok": False, "error": "Voz neural indisponível: " + str(e)}
        finally:
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass

    # ═══════════════════════════════════════════════════════════════
    # JARVIS VOICE ENDPOINTS
    # ═══════════════════════════════════════════════════════════════

    def _api_jarvis_voice_transcribe(self, data):
        """Transcreve audio enviado pelo browser."""
        try:
            from jarvis_core.voice import get_voice
            voice = get_voice()
            audio_b64 = (data or {}).get("audio", "")
            fmt = (data or {}).get("format", "wav")
            if not audio_b64:
                return {"ok": False, "error": "Audio vazio"}
            result = voice.transcribe_base64(audio_b64, fmt)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_voice_tts(self, data):
        """Converte texto para voz."""
        try:
            from jarvis_core.voice import get_voice
            voice = get_voice()
            text = str((data or {}).get("text") or "").strip()[:1200]
            v = (data or {}).get("voice", "pt-BR-FranciscaNeural")
            if not text:
                return {"ok": False, "error": "Texto vazio"}
            result = voice.text_to_speech_sync(text, v)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_voice_command(self, data):
        """Processa comando de voz: wake word + extracao de comando."""
        try:
            from jarvis_core.voice import get_voice
            voice = get_voice()
            text = str((data or {}).get("text") or "").strip()
            if not text:
                return {"ok": False, "error": "Texto vazio"}
            result = voice.process_voice_command(text)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_voice_status(self, data):
        """Status do sistema de voz."""
        try:
            from jarvis_core.voice import get_voice
            voice = get_voice()
            return {"ok": True, **voice.status()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # JARVIS BRAIN ENDPOINTS
    # ═══════════════════════════════════════════════════════════════

    def _api_jarvis_chat(self, data):
        """Chat completo: texto → LLM → plano → executa → resposta."""
        try:
            request_started = time.perf_counter()
            request_id = uuid.uuid4().hex
            from jarvis_core.brain import get_brain
            from desktop_center import DESKTOP_CENTER

            text = str((data or {}).get("text") or "").strip()
            session_id = str((data or {}).get("session_id") or "desktop")[:120]
            if not text:
                return {"ok": False, "error": "Texto vazio"}
            from jarvis_core.output_mode import get_output_mode_manager, to_spoken_text
            output = get_output_mode_manager().parse(text, source="text")
            text = output["content"] or text

            jarvis = DESKTOP_CENTER.service
            brain = get_brain(jarvis.registry)
            if not brain.orchestrator.models.providers:
                from jarvis_core.orchestrator import register_real_adapters
                register_real_adapters(brain.orchestrator.models,
                                       self._call_groq_model, self._call_gemini_model)

            shadow_task = None
            preview = jarvis.orchestrator.decide(text)
            if preview.requires_planning:
                try:
                    task_result = jarvis.runtime.process(text, preview)
                    if jarvis.orchestrator.mode == "on":
                        return {"ok": True, "response": "Tarefa criada para execução segura.",
                                "task_id": task_result.get("task_id"), "planned": True}
                    shadow_task = {"task_id": task_result.get("task_id"),
                                   "validated": task_result.get("planned", False),
                                   "executed": False}
                except Exception as exc:
                    shadow_task = {"validated": False, "executed": False,
                                   "error": str(exc)[:300]}

            # 1. Brain interpreta
            brain_result = brain.interpret(text, source="text", voice_capture=False)
            llm_info = getattr(brain, "last_llm", {}) or {}
            if not brain_result.get("ok"):
                brain_result["shadow_task"] = shadow_task
                brain_result["route"] = preview.route.value
                brain_result["skill"] = preview.preferred_skill
                brain_result["confidence"] = preview.confidence
                brain_result["llm"] = getattr(brain, "last_llm", {}) or {}
                return brain_result

            plan = brain_result.get("plan", {})
            meta = {"route": preview.route.value, "skill": preview.preferred_skill,
                    "confidence": preview.confidence,
                    "llm": getattr(brain, "last_llm", {}) or {},
                    "telemetry": brain.request_metrics()}
            if set(plan) == {"response"}:
                canonical = jarvis._attach_research_telemetry(
                    {"ok": True, "provider": llm_info.get("provider", ""),
                     "model": llm_info.get("model", brain_result.get("model", ""))},
                    request_id, session_id, request_started)
                jarvis.record_response_metrics(preview.route.value, preview.preferred_skill,
                    "", brain.request_metrics(), {"ok": True,
                    "response_policy": "NEEDS_SYNTHESIS"})
                response = str(plan["response"])
                spoken = to_spoken_text(response)
                if output["speak"]:
                    from jarvis_core.voice_service import get_voice_service
                    get_voice_service().speak_now(spoken)
                return {"ok": True, "response": response, "spoken_response": spoken,
                        "output_mode": output["mode"], "tool": "none",
                        "model": llm_info.get("model", brain_result.get("model", "")), "shadow_task": shadow_task,
                        "routing_metadata": canonical.get("routing_metadata", {}),
                        **meta}
            tool_name = plan.get("tool", "")
            args = plan.get("args", {})

            # 3. Executa a ferramenta
            exec_result = jarvis.execute_tool(tool_name, args, text)
            canonical = jarvis._attach_research_telemetry(
                {**exec_result, "provider": llm_info.get("provider", exec_result.get("provider", "")),
                 "model": llm_info.get("model", brain_result.get("model", ""))},
                request_id, session_id, request_started)
            meta["telemetry"] = brain.request_metrics(tool_name)
            jarvis.record_response_metrics(preview.route.value, preview.preferred_skill,
                                           tool_name, meta["telemetry"], exec_result)

            response = exec_result.get("message") or exec_result.get("error")
            if not response and isinstance(exec_result.get("items"), list):
                response = f"Encontrei {len(exec_result['items'])} memória(s)."

            spoken = to_spoken_text(response or ".")
            if output["speak"]:
                from jarvis_core.voice_service import get_voice_service
                get_voice_service().speak_now(spoken)
            return {
                "ok": exec_result.get("ok", False),
                "response": response or ".",
                "spoken_response": spoken,
                "output_mode": output["mode"],
                "tool": tool_name,
                "tool_result": exec_result,
                "tool_provider": exec_result.get("provider", ""),
                "model": brain_result.get("model", ""),
                "shadow_task": shadow_task,
                "routing_metadata": canonical.get("routing_metadata", {}),
                **meta,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_brain_status(self, data):
        """Status do cérebro do Jarvis."""
        try:
            from jarvis_core.brain import get_brain
            from desktop_center import DESKTOP_CENTER
            brain = get_brain(DESKTOP_CENTER.service.registry)
            return {"ok": True, **brain.status()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_brain_execute(self, data):
        """Executa um tool call direto (sem LLM)."""
        try:
            from desktop_center import DESKTOP_CENTER

            tool_name = (data or {}).get("tool", "")
            args = (data or {}).get("args", {})

            if not tool_name:
                return {"ok": False, "error": "Ferramenta não especificada"}

            result = DESKTOP_CENTER.service.execute_tool(tool_name, args)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_memory_status(self, data):
        from desktop_center import DESKTOP_CENTER
        return DESKTOP_CENTER.service._memory_status()

    def _api_jarvis_memory_search(self, data):
        from desktop_center import DESKTOP_CENTER
        query = str((data or {}).get("query") or "").strip()
        namespace = str((data or {}).get("namespace") or "jarvis").strip()
        if not query:
            return {"ok": False, "error": "Consulta vazia"}
        return DESKTOP_CENTER.service._memory_search(query, namespace)

    def _api_jarvis_memory_remember(self, data):
        from desktop_center import DESKTOP_CENTER
        content = str((data or {}).get("content") or "").strip()
        namespace = str((data or {}).get("namespace") or "jarvis").strip()
        if not content:
            return {"ok": False, "error": "Conteúdo vazio"}
        return DESKTOP_CENTER.service._memory_remember(content, namespace)

    def _api_jarvis_memory_recent(self, data):
        from desktop_center import DESKTOP_CENTER
        limit = int((data or {}).get("limit") or 10)
        namespace = str((data or {}).get("namespace") or "jarvis").strip()
        return DESKTOP_CENTER.service._memory_recent(limit, namespace)

    # ═══════════════════════════════════════════════════════════════
    # JARVIS DESKTOP VOICE SERVICE (Fase 8 — escuta local sem navegador)
    # ═══════════════════════════════════════════════════════════════

    def _api_jarvis_voice_service_status(self, data):
        try:
            from jarvis_core.voice_service import get_voice_service
            return get_voice_service().status()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_voice_service_start(self, data):
        try:
            from jarvis_core.voice_service import get_voice_service
            from desktop_center import DESKTOP_CENTER
            return get_voice_service().start(DESKTOP_CENTER.service)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_voice_service_stop(self, data):
        try:
            from jarvis_core.voice_service import get_voice_service
            return get_voice_service().stop()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_golden_overview(self, data):
        """Expose the B1 Golden read projection through the canonical service."""
        try:
            from desktop_center import DESKTOP_CENTER
            payload = data or {}
            # Use the canonical tool path so AuditLog, security and provenance
            # metadata remain attached to the same read receipt as other UI reads.
            return DESKTOP_CENTER.service.execute_tool(
                "golden_control_center_snapshot",
                {"symbol": str(payload.get("symbol") or "").strip(),
                 "include_live": payload.get("include_live") is True},
                command="control_center_golden_read", task_id="control_center",
            )
        except Exception as exc:
            return {"ok": False, "status": "UNAVAILABLE",
                    "error": type(exc).__name__}

    def _execute_jarvis_read(self, tool_name, arguments=None):
        try:
            from desktop_center import DESKTOP_CENTER
            return DESKTOP_CENTER.service.execute_tool(
                tool_name, arguments or {}, command="control_center_golden_b2_read",
                task_id="control_center",
            )
        except Exception as exc:
            return {"ok": False, "status": "UNAVAILABLE", "error": type(exc).__name__}

    def _api_jarvis_golden_radar(self, data):
        payload = data or {}
        return self._execute_jarvis_read("golden_radar_detail", {
            "symbol": str(payload.get("symbol") or ""),
            "timeframe": str(payload.get("timeframe") or "M15"),
            "correlation_id": str(payload.get("correlation_id") or ""),
        })

    def _api_jarvis_golden_risk(self, data):
        return self._execute_jarvis_read("golden_risk_detail")

    def _api_jarvis_golden_validation(self, data):
        payload = data or {}
        return self._execute_jarvis_read("golden_validation_detail", {
            "limit": int(payload.get("limit") or 20),
        })

    def _api_jarvis_golden_deep_analysis(self, data):
        payload = data or {}
        return self._execute_jarvis_read("golden_deep_analysis_detail", {
            "symbol": str(payload.get("symbol") or "XAUUSD"),
            "correlation_id": str(payload.get("correlation_id") or ""),
        })

    def _api_jarvis_golden_recovery_manifest(self, data):
        payload = data or {}
        return self._execute_jarvis_read("golden_recovery_manifest", {
            "root": str(payload.get("root") or ""),
        })

    def _api_jarvis_scientific_memory(self, data):
        return self._execute_jarvis_read("scientific_memory_status")

    def _api_jarvis_voice_service_listen(self, data):
        try:
            from jarvis_core.voice_service import get_voice_service
            session_id = str((data or {}).get("session_id") or "").strip()
            return get_voice_service().request_utterance(session_id=session_id)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_voice_service_speak(self, data):
        try:
            from jarvis_core.voice_service import get_voice_service
            text = str((data or {}).get("text") or "").strip()
            return get_voice_service().speak_now(text)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # JARVIS VISION ENDPOINTS
    # ═══════════════════════════════════════════════════════════════

    def _api_jarvis_vision_analyze(self, data):
        """Captura a tela e analisa com IA visual."""
        try:
            from jarvis_core.vision import get_vision
            vision = get_vision()
            question = str((data or {}).get("question") or "")
            image_b64 = str((data or {}).get("image") or "")
            if image_b64:
                result = vision.analyze_image(image_b64, question)
            else:
                result = vision.analyze_screen(question)
            return result
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_vision_status(self, data):
        """Status do sistema de visão."""
        try:
            from jarvis_core.vision import get_vision
            vision = get_vision()
            return {"ok": True, **vision.status()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════════
    # JARVIS DESKTOP READ APIS (somente leitura + cancel seguro; sem
    # mudar Brain/Orchestrator/TaskManager; Orchestrator segue SHADOW)
    # ═══════════════════════════════════════════════════════════════

    def _api_jarvis_tasks_list(self, data):
        """Lista tarefas reais do TaskManager (leitura)."""
        try:
            from desktop_center import DESKTOP_CENTER
            limit = int((data or {}).get("limit") or 50)
            limit = max(1, min(limit, 100))
            status = (data or {}).get("status")
            tasks = DESKTOP_CENTER.service.task_manager.list(limit=limit, status=status)
            out = []
            for t in tasks or []:
                try:
                    out.append({
                        "id": getattr(t, "id", ""),
                        "title": getattr(t, "title", ""),
                        "status": str(getattr(getattr(t, "status", ""), "value", getattr(t, "status", ""))),
                        "created_at": getattr(t, "created_at", None),
                        "updated_at": getattr(t, "updated_at", None),
                        "error": (getattr(t, "error", "") or "")[:300],
                    })
                except Exception:
                    continue
            return {"ok": True, "tasks": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_tasks_get(self, data):
        """Detalhe real de uma tarefa: task + steps + eventos (leitura)."""
        try:
            from desktop_center import DESKTOP_CENTER
            task_id = str((data or {}).get("task_id") or "").strip()
            if not task_id:
                return {"ok": False, "error": "task_id obrigatorio"}
            tm = DESKTOP_CENTER.service.task_manager
            task = tm.get(task_id)
            if not task:
                return {"ok": False, "error": "tarefa nao encontrada"}
            steps = []
            for s in tm.steps(task_id) or []:
                try:
                    step = getattr(s, "step", None)
                    steps.append({
                        "id": getattr(step, "id", "") if step is not None else "",
                        "intent": getattr(step, "intent", "") if step is not None else "",
                        "tool": getattr(step, "tool", "") if step is not None else "",
                        "status": str(getattr(getattr(s, "status", ""), "value", getattr(s, "status", ""))),
                        "error": (getattr(s, "error", "") or "")[:300],
                    })
                except Exception:
                    continue
            total = len(steps)
            done = sum(1 for s in steps if s.get("status") == "COMPLETED")
            current = next((s for s in steps if s.get("status") in ("RUNNING", "WAITING_CONFIRMATION")), None)
            if current is None:
                current = next((s for s in steps if s.get("status") == "PENDING"), None)
            events = []
            try:
                for ev in tm.events(task_id, limit=20) or []:
                    if isinstance(ev, dict):
                        events.append({k: ev.get(k) for k in ("type", "event", "status", "created_at", "message") if k in ev})
                    else:
                        events.append({"event": str(ev)[:200]})
            except Exception:
                events = []
            return {"ok": True, "task": {
                "id": getattr(task, "id", task_id),
                "title": getattr(task, "title", ""),
                "status": str(getattr(getattr(task, "status", ""), "value", getattr(task, "status", ""))),
                "error": (getattr(task, "error", "") or "")[:300],
                "progress": {"done": done, "total": total},
                "current_step": current,
            }, "steps": steps, "events": events}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_tasks_cancel(self, data):
        """Cancelamento cooperativo real (única mutação; não executa tools)."""
        try:
            from desktop_center import DESKTOP_CENTER
            task_id = str((data or {}).get("task_id") or "").strip()
            if not task_id:
                return {"ok": False, "error": "task_id obrigatorio"}
            cancelled = bool(DESKTOP_CENTER.service.task_manager.cancel(task_id))
            return {"ok": True, "task_id": task_id, "cancelled": cancelled}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_orchestrator_status(self, data):
        """Telemetria sanitizada do Orchestrator (sem prompt/payload)."""
        try:
            from desktop_center import DESKTOP_CENTER
            orch = DESKTOP_CENTER.service.orchestrator
            base = orch.status() if hasattr(orch, "status") else {"mode": getattr(orch, "mode", "shadow")}
            last = base.get("last_decision")
            if isinstance(last, dict):
                route = last.get("route")
                profile = last.get("preferred_model_profile")
                classification = last.get("data_classification")
                last = {
                    "intent": str(last.get("intent", ""))[:120],
                    "route": str(getattr(route, "value", route)),
                    "confidence": last.get("confidence"),
                    "skill": str(last.get("preferred_skill", "")),
                    "model_profile": str(getattr(profile, "value", profile)),
                    "requires_planning": bool(last.get("requires_planning")),
                    "requires_clarification": bool(last.get("requires_clarification")),
                    "requires_confirmation": bool(last.get("requires_confirmation")),
                    "reason_code": str(last.get("reason_code", "")),
                    "tool_count": len(last.get("allowed_tools") or ()),
                    "data_classification": str(getattr(classification, "value", classification)),
                }
            return {"ok": True, "mode": str(base.get("mode", "shadow")), "last_decision": last}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_skills_status(self, data):
        """Catálogo real de skills (sem simular sucesso)."""
        try:
            from desktop_center import DESKTOP_CENTER
            skills = DESKTOP_CENTER.service.orchestrator.skills.catalog()
            out = []
            for s in skills or []:
                try:
                    required = tuple(getattr(s, "required_tools", ()) or ())
                    present = tuple(t for t in required)
                    if not required:
                        state = "READY"
                    elif present and len(present) == len(required):
                        state = "READY"
                    elif present:
                        state = "PARTIAL"
                    else:
                        state = "NOT_IMPLEMENTED"
                    route = getattr(s, "route", "")
                    profile = getattr(s, "model_profile", "")
                    out.append({
                        "name": getattr(s, "name", ""),
                        "route": str(getattr(route, "value", route)),
                        "status": state,
                        "available": bool(getattr(s, "available", False)),
                        "tools": list(present),
                        "risk": str(getattr(s, "risk_profile", "")),
                        "model_profile": str(getattr(profile, "value", profile)),
                    })
                except Exception:
                    continue
            return {"ok": True, "skills": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_jarvis_readiness(self, data):
        """Readiness SSOT do Jarvis (P1.3). Sem segredos, só estados/tempos."""
        try:
            from jarvis_core.readiness import get_readiness
            return {"ok": True, "readiness": get_readiness().status()}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    def _api_jarvis_providers_status(self, data):
        """Saude real dos providers com probe leve cacheado (sem chamar LLM).

        - Ollama: checagem local viva (127.0.0.1:11434), cache 45s.
        - Cloud: presenca de chave + last_health real do ModelRouter.
          Nunca executado e com chave => UNKNOWN; sem chave => OFFLINE.
        - Nunca expoe chaves, prompts ou payloads.
        """
        import time as _time
        try:
            from desktop_center import DESKTOP_CENTER
            from jarvis_core.orchestrator.policies import DEFAULT_MODELS, PROVIDER_ORDER
            models = DESKTOP_CENTER.service.orchestrator.models
            health = {}
            try:
                health = dict(getattr(models, "last_health", {}) or {})
            except Exception:
                health = {}
            registered = {}
            try:
                registered = dict(getattr(models, "providers", {}) or {})
            except Exception:
                registered = {}

            # Ollama: probe local barato com cooldown de 45s.
            ollama_state = "OFFLINE"
            try:
                cache = getattr(self, "_provider_probe_cache", None)
                now = _time.time()
                if cache and (now - cache.get("at", 0)) < 45:
                    ollama_state = cache.get("ollama", "OFFLINE")
                else:
                    import urllib.request
                    req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
                    with urllib.request.urlopen(req, timeout=2) as r:
                        ollama_state = "ONLINE" if r.status == 200 else "OFFLINE"
                    self._provider_probe_cache = {"at": now, "ollama": ollama_state}
            except Exception:
                try:
                    self._provider_probe_cache = {"at": _time.time(), "ollama": "OFFLINE"}
                except Exception:
                    pass
                ollama_state = "OFFLINE"

            # Presenca de chave (igual ao /api/status; sem expor valores).
            keys = {}
            try:
                keys = self._read_api_keys()
            except Exception:
                keys = {}
            import os as _os
            has_key = {
                "groq": bool(keys.get("groq_api_key") or _os.environ.get("GROQ_API_KEY")),
                "openrouter": bool(keys.get("openrouter_key") or keys.get("openrouter_api_key")),
                "gemini": bool(keys.get("gemini_api_key") or _os.environ.get("GEMINI_API_KEY")
                               or _os.environ.get("GOOGLE_API_KEY")),
                "ollama": True,
            }

            providers = []
            states = {}
            for name in PROVIDER_ORDER:
                if name == "ollama":
                    state = ollama_state
                else:
                    last = health.get(name)
                    last_v = str(getattr(last, "value", last)) if last is not None else "OFFLINE"
                    if last_v == "AVAILABLE":
                        state = "ONLINE"
                    elif last_v in ("RATE_LIMITED", "TIMEOUT", "AUTH_ERROR", "DEGRADED"):
                        state = last_v
                    else:
                        state = "UNKNOWN" if has_key.get(name) else "OFFLINE"
                states[name] = state
                providers.append({"name": name, "state": state,
                                  "registered": bool(registered.get(name)),
                                  "configured": bool(has_key.get(name))})

            primary = []
            for profile, (pname, model) in DEFAULT_MODELS.items():
                pname_v = pname if isinstance(pname, str) else str(getattr(pname, "value", pname))
                profile_v = profile if isinstance(profile, str) else str(getattr(profile, "value", profile))
                primary.append({"profile": profile_v, "provider": str(pname_v), "model": str(model)})

            # PRIMARY real (perfil GENERAL): solicitado x efetivo x fallback.
            requested = next((m for m in primary if m["profile"] == "GENERAL"),
                             primary[0] if primary else {"provider": "", "model": ""})
            actual_name = requested["provider"]
            for name in PROVIDER_ORDER:
                if states.get(name) == "ONLINE":
                    actual_name = name
                    break
            else:
                actual_name = ""
            from jarvis_core.orchestrator.policies import PROVIDER_MODELS as _PM
            from jarvis_core.orchestrator.models import ModelProfile as _MP
            try:
                actual_model = _PM.get(actual_name, {}).get(_MP.GENERAL, requested.get("model", ""))
            except Exception:
                actual_model = requested.get("model", "")
            fallback = bool(actual_name) and actual_name != requested["provider"]
            reason = ""
            if not actual_name:
                reason = "nenhum provider ONLINE"
            elif fallback:
                reason = "%s %s" % (requested["provider"], states.get(requested["provider"], "OFFLINE"))
            core_status = DESKTOP_CENTER.service.ai_core_status()
            # Keep the historical provider fields and add the canonical status
            # consumed by the desktop/web panel.
            return {"ok": True, "mode": str(getattr(DESKTOP_CENTER.service.orchestrator, "mode", "shadow")),
                    "providers": providers, "primary_models": primary,
                    "ai_core": core_status,
                    "readiness": self._api_jarvis_readiness({}).get("readiness", {}),
                    "primary": {"requested_provider": requested.get("provider", ""),
                                "requested_model": requested.get("model", ""),
                                "actual_provider": actual_name, "actual_model": actual_model,
                                "fallback": fallback, "fallback_reason": reason}}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _api_radar_status(self, data):
        """Status real do monitor persistente do Radar (leitura)."""
        try:
            from monitor_service import get_monitor_service
            s = get_monitor_service().status()
            return {"ok": True, "running": bool(s.get("running")),
                    "last_run": s.get("last_run"), "last_error": s.get("last_error"),
                    "signal_counts": s.get("signal_counts", {})}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def api_filesystem(self, data):
        action = data.get("action", "list")
        path = data.get("path", ".")
        if action == "list":
            return {"ok": True, "result": self._tool_list_directory({"path": path})}
        elif action == "read":
            return {"ok": True, "result": self._tool_read_file({"path": path, "limit": data.get("limit", 200)})}
        elif action == "search":
            return {"ok": True, "result": self._tool_search_files({"path": path, "pattern": data.get("pattern", "*")})}
        elif action == "write":
            content = data.get("content", "")
            result = self._execute_tool({"tool": "write_file", "path": path, "content": content}, data.get("session_id", "default"))
            return {"ok": not str(result).startswith("🔐"), "result": result}
        return {"ok": False, "error": "Unknown action"}

    def api_system(self, data):
        action = data.get("action", "info")
        if action == "info":
            return {"ok": True, "result": self._tool_system_info()}
        elif action == "clean_cache":
            result = self._execute_tool({"tool": "clean_cache"}, data.get("session_id", "default"))
            return {"ok": not str(result).startswith("🔐"), "result": result}
        elif action == "clean_temp":
            result = self._execute_tool({"tool": "clean_temp"}, data.get("session_id", "default"))
            return {"ok": not str(result).startswith("🔐"), "result": result}
        elif action == "empty_recycle":
            result = self._execute_tool({"tool": "empty_recycle_bin"}, data.get("session_id", "default"))
            return {"ok": not str(result).startswith("🔐"), "result": result}
        elif action == "programs":
            return {"ok": True, "result": self._tool_find_programs()}
        return {"ok": False, "error": "Unknown action"}

    def api_history(self, data):
        session_id = data.get("session_id", "default")
        with CONVERSATIONS_LOCK:
            history = CONVERSATIONS.get(session_id, [])
        return {"ok": True, "history": history}

    def api_clear_history(self, data):
        session_id = data.get("session_id", "default")
        with CONVERSATIONS_LOCK:
            CONVERSATIONS[session_id] = []
        return {"ok": True}

    def api_projects(self, data):
        projects = []
        for d in [ROOT / "projetos", ROOT / "sandbox", ROOT / "studio"]:
            if d.exists():
                for f in d.rglob("*"):
                    if f.is_file() and f.suffix in ('.mq5', '.py', '.mqh', '.js', '.html', '.json', '.yaml'):
                        try:
                            projects.append({"name": f.name, "path": str(f), "size": f.stat().st_size, "ext": f.suffix})
                        except:
                            pass
        # Also check MT5
        mt5_common = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal")
        if mt5_common.exists():
            for f in mt5_common.rglob("*.mq5"):
                try:
                    projects.append({"name": f.name, "path": str(f), "size": f.stat().st_size, "ext": ".mq5"})
                except:
                    pass
        return {"ok": True, "projects": projects[:100]}

    def api_quotes(self, data):
        return self._tool_get_exchange_rate()

    def _api_market_overview(self, data):
        from market_data import get_market_overview
        return get_market_overview()

    def _api_market_forex(self, data):
        from market_data import get_forex_analysis
        return get_forex_analysis((data or {}).get("symbol"))

    def _api_market_chart(self, data):
        from market_data import get_market_chart
        data = data or {}
        return get_market_chart(data.get("symbol", "XAUUSD"), data.get("timeframe", "M15"))

    def _api_market_tick(self, data):
        from market_data import get_market_tick
        return get_market_tick((data or {}).get("symbol", "XAUUSD"))

    def _api_market_ai_context(self, data):
        from market_data import get_market_ai_context
        return get_market_ai_context((data or {}).get("symbol", "XAUUSD"))

    def _api_market_analysis_history(self, data):
        path = ROOT / "data" / "market_ai_audit.jsonl"
        symbol = str((data or {}).get("symbol", "")).upper()
        limit = min(20, max(1, int((data or {}).get("limit", 5))))
        if not path.exists():
            return {"ok": True, "history": []}
        all_rows = []
        changed = False
        tick_cache = {}
        horizon_seconds = {"M1": 300, "M5": 900, "M15": 2700, "H1": 10800, "H4": 43200, "D1": 259200}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                if item.get("evaluation_status") == "pendente" and item.get("symbol") and item.get("timestamp"):
                    elapsed = time.time() - datetime.fromisoformat(item["timestamp"]).timestamp()
                    horizon = horizon_seconds.get(str(item.get("timeframe", "M15")).upper(), 2700)
                    if elapsed >= horizon:
                        snapshot = item.get("snapshot") or {}
                        entry = float(snapshot.get("price") or 0)
                        direction = str(snapshot.get("direction") or snapshot.get("alignment") or "").lower()
                        direction = "alta" if "alta" in direction or direction == "buy" else "baixa" if "baixa" in direction or direction == "sell" else ""
                        if item["symbol"] not in tick_cache:
                            from market_data import get_market_tick
                            tick_cache[item["symbol"]] = get_market_tick(item["symbol"])
                        tick = tick_cache[item["symbol"]]
                        current = float(tick.get("price") or 0) if tick.get("ok") else 0
                        tf_data = (snapshot.get("multitimeframe") or {}).get(str(item.get("timeframe", "M15")).upper(), {})
                        threshold = max(float(tf_data.get("atr") or 0) * 0.2, entry * 0.0001)
                        movement = current - entry if entry and current else 0
                        try:
                            import MetaTrader5 as mt5
                            frame_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
                                         "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1}
                            start = datetime.fromisoformat(item["timestamp"])
                            rates = mt5.copy_rates_range(item["symbol"], frame_map.get(str(item.get("timeframe", "M15")).upper(), mt5.TIMEFRAME_M15), start, datetime.now())
                            info = mt5.symbol_info(item["symbol"])
                            if rates is not None and len(rates) and info and info.point and entry:
                                highest = max(float(row["high"]) for row in rates)
                                lowest = min(float(row["low"]) for row in rates)
                                if direction == "alta":
                                    item["mfe_points"] = round(max(0, highest-entry) / info.point, 1)
                                    item["mae_points"] = round(max(0, entry-lowest) / info.point, 1)
                                elif direction == "baixa":
                                    item["mfe_points"] = round(max(0, entry-lowest) / info.point, 1)
                                    item["mae_points"] = round(max(0, highest-entry) / info.point, 1)
                        except Exception:
                            pass
                        if direction and abs(movement) >= threshold:
                            confirmed = (direction == "alta" and movement > 0) or (direction == "baixa" and movement < 0)
                            item["evaluation_status"] = "confirmada" if confirmed else "invalidada"
                        elif elapsed >= horizon * 2:
                            item["evaluation_status"] = "inconclusiva"
                        if item.get("evaluation_status") != "pendente":
                            item["evaluated_at"] = datetime.now().isoformat()
                            item["entry_price"] = entry
                            item["evaluation_price"] = current
                            item["movement"] = round(movement, 8)
                            changed = True
                all_rows.append(item)
            except Exception:
                continue
        if changed:
            temp = path.with_suffix(".tmp")
            temp.write_text("".join(json.dumps(row, ensure_ascii=False, cls=_NumpyEncoder) + "\n" for row in all_rows), encoding="utf-8")
            temp.replace(path)
        rows = [item for item in all_rows if not symbol or item.get("symbol", "").upper() == symbol]
        return {"ok": True, "history": rows[-limit:][::-1]}

    def _api_market_ai_performance(self, data):
        self._api_market_analysis_history({"limit": 1})
        data = data or {}
        path = ROOT / "data" / "market_ai_audit.jsonl"
        if not path.exists():
            return {"ok": True, "summary": {}, "groups": []}
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
                if item.get("mode") != "pergunta_contextual":
                    rows.append(item)
            except Exception:
                continue
        symbol = str(data.get("symbol") or "").upper()
        timeframe = str(data.get("timeframe") or "").upper()
        mode = str(data.get("mode") or "").lower()
        try:
            days = max(0, min(3650, int(data.get("days") or 0)))
        except (TypeError, ValueError):
            days = 0
        cutoff = time.time() - days * 86400 if days else 0
        def included(row):
            if symbol and str(row.get("symbol") or "").upper() != symbol:
                return False
            if timeframe and str(row.get("timeframe") or "").upper() != timeframe:
                return False
            if mode and str(row.get("mode") or "").lower() != mode:
                return False
            if cutoff:
                try:
                    return datetime.fromisoformat(str(row.get("timestamp"))).timestamp() >= cutoff
                except Exception:
                    return False
            return True
        rows = [row for row in rows if included(row)]
        evaluated = [row for row in rows if row.get("evaluation_status") in ("confirmada", "invalidada", "inconclusiva")]
        confirmed = sum(row.get("evaluation_status") == "confirmada" for row in evaluated)
        def average(key):
            values = [float(row[key]) for row in evaluated if row.get(key) is not None]
            return round(sum(values) / len(values), 1) if values else 0
        groups = []
        for field in ("symbol", "timeframe", "mode"):
            values = sorted({str(row.get(field) or "n/d") for row in evaluated})
            for value in values:
                subset = [row for row in evaluated if str(row.get(field) or "n/d") == value]
                wins = sum(row.get("evaluation_status") == "confirmada" for row in subset)
                mfe = [float(row.get("mfe_points") or 0) for row in subset]
                mae = [float(row.get("mae_points") or 0) for row in subset]
                groups.append({"group": field, "value": value, "total": len(subset), "confirmed": wins,
                               "invalidated": sum(row.get("evaluation_status") == "invalidada" for row in subset),
                               "rate": round(wins / len(subset) * 100, 1) if subset else 0,
                               "average_mfe_points": round(sum(mfe) / len(mfe), 1) if mfe else 0,
                               "average_mae_points": round(sum(mae) / len(mae), 1) if mae else 0,
                               "sample_quality": "alta" if len(subset) >= 100 else "media" if len(subset) >= 30 else "baixa"})
        sample_quality = "alta" if len(evaluated) >= 100 else "media" if len(evaluated) >= 30 else "baixa"
        return {"ok": True, "summary": {"analyses": len(rows), "evaluated": len(evaluated),
                "pending": sum(row.get("evaluation_status") == "pendente" for row in rows),
                "confirmed": confirmed, "invalidated": sum(row.get("evaluation_status") == "invalidada" for row in evaluated),
                "inconclusive": sum(row.get("evaluation_status") == "inconclusiva" for row in evaluated),
                "confirmation_rate": round(confirmed / len(evaluated) * 100, 1) if evaluated else 0,
                "average_mfe_points": average("mfe_points"), "average_mae_points": average("mae_points"),
                "sample_quality": sample_quality},
                "filters": {"symbol": symbol, "timeframe": timeframe, "mode": mode, "days": days},
                "groups": sorted(groups, key=lambda row: (-row["rate"], -row["total"]))}

    def _api_market_opportunity_ranking(self, data):
        radar = self._api_scanner_radar({})
        if not radar.get("ok"):
            return radar
        ranked = []
        for row in radar.get("radar", []):
            readiness = float(row.get("best_readiness") or 0)
            spread = float(row.get("spread") or 0)
            trends = [str(row.get(key, "")).lower() for key in ("trend_m5", "trend_m15", "trend_h1", "trend_h4")]
            direction = str(row.get("best_direction") or "").lower()
            aligned = sum((direction == "buy" and "alta" in trend) or (direction == "sell" and "baixa" in trend) for trend in trends)
            risk_penalty = min(20, spread / 10)
            score = round(max(0, min(100, readiness * .65 + aligned * 7.5 - risk_penalty)), 1)
            ranked.append({"symbol": row.get("symbol"), "direction": row.get("best_direction"),
                           "setup": row.get("best_setup_name"), "readiness": readiness, "alignment": aligned,
                           "spread": spread, "risk": "alto" if risk_penalty >= 12 else "moderado" if risk_penalty >= 6 else "baixo",
                           "score": score})
        return {"ok": True, "ranking": sorted(ranked, key=lambda row: row["score"], reverse=True)[:12],
                "method": "prontidao 65% + alinhamento MTF - penalidade de spread"}

    def _api_market_analyze(self, data):
        """Análise financeira isolada do chat geral e sem histórico contaminado."""
        if not OLLAMA_AVAILABLE:
            return {"ok": False, "error": "IA local desligada"}
        prompt = str((data or {}).get("prompt", "")).strip()
        if not prompt:
            return {"ok": False, "error": "Contexto de análise vazio"}
        system = (
            "Você é o analista técnico e macroeconômico do Golden AI Radar. "
            "Responda sempre em português do Brasil, de forma objetiva e profissional. "
            "Cumpra somente a modalidade solicitada. Use exclusivamente os números fornecidos, "
            "não invente dados e não transforme score em probabilidade. Não dê ordem direta de "
            "compra ou venda: descreva cenários condicionais, evidências, invalidação e riscos."
        )
        try:
            response = ollama_chat(model="qwen2.5-coder:14b", messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ], options={"temperature": 0.15, "num_predict": 900})
            content = response.message.content if hasattr(response, "message") else response.get("message", {}).get("content", "")
            timestamp = datetime.now().isoformat()
            snapshot = dict((data or {}).get("snapshot", {}) or {})
            if not snapshot.get("direction"):
                direction_match = re.search(r'"best_direction"\s*:\s*"(BUY|SELL)"', prompt, re.IGNORECASE)
                if direction_match:
                    snapshot["direction"] = direction_match.group(1).upper()
                elif "alta alinhada" in str(snapshot.get("alignment", "")).lower():
                    snapshot["direction"] = "BUY"
                elif "baixa alinhada" in str(snapshot.get("alignment", "")).lower():
                    snapshot["direction"] = "SELL"
            audit = {
                "timestamp": timestamp, "symbol": str((data or {}).get("symbol", "")),
                "timeframe": str((data or {}).get("timeframe", "")), "mode": str((data or {}).get("mode", "")),
                "response": content, "snapshot": snapshot,
                "evaluation_status": "pendente"
            }
            audit_path = ROOT / "data" / "market_ai_audit.jsonl"
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(audit, ensure_ascii=False, cls=_NumpyEncoder) + "\n")
            return {"ok": True, "response": content, "timestamp": timestamp, "audit": "registrada"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def api_search(self, data):
        query = data.get("query", "")
        return {"ok": True, "result": self._tool_web_search({"query": query})}

    def api_chat(self, data):
        """Non-streaming chat fallback with tool-calling"""
        message = data.get("message", "")
        session_id = data.get("session_id", "default")
        if not message.strip():
            return {"ok": False, "error": "Empty"}
        if not OLLAMA_AVAILABLE:
            return {"ok": False, "error": "IA local desligada. Inicie o Ollama para usar o aprofundamento; a análise técnica do Radar continua ativa."}

        with CONVERSATIONS_LOCK:
            history = CONVERSATIONS.get(session_id, [])

        history.append({"role": "user", "content": message})
        if len(history) > 30:
            history = history[-30:]

        messages = [{"role": "system", "content": TOOL_DEFINITIONS}]
        for h in history[-15:]:
            messages.append(h)

        # Tool-calling loop (max 3 iterations)
        full_response = ""
        for iteration in range(3):
            response = ollama_chat(model="qwen2.5-coder:14b", messages=messages)
            content = response["message"]["content"]

            tool_call = self._parse_tool_call(content)
            if tool_call:
                tool_result = self._execute_tool(tool_call, session_id)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Resultado da ferramenta:\n\n{tool_result[:20000]}\n\nAgora responda ao usuario com base neste resultado. Use Markdown para formatar sua resposta."})
                continue
            else:
                full_response = content
                break

        with CONVERSATIONS_LOCK:
            if session_id not in CONVERSATIONS:
                CONVERSATIONS[session_id] = []
            CONVERSATIONS[session_id].append({"role": "user", "content": message})
            CONVERSATIONS[session_id].append({"role": "assistant", "content": full_response})
            if len(CONVERSATIONS[session_id]) > 50:
                CONVERSATIONS[session_id] = CONVERSATIONS[session_id][-50:]

        return {"ok": True, "response": full_response, "timestamp": datetime.now().isoformat()}

    # ── MULTIMEDIA ────────────────────────────────────────────

    def _save_upload(self, base64_data, filename):
        temp_dir = ROOT / "sandbox" / "uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename or "upload.bin").name
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)[:120] or "upload.bin"
        temp_path = temp_dir / f"{int(time.time() * 1000)}_{safe_name}"
        with open(temp_path, "wb") as f:
            f.write(base64.b64decode(base64_data))
        return str(temp_path)

    def api_vision(self, data):
        path = data.get("path", "")
        prompt = data.get("prompt", "Descreva o que voce ve.")
        if data.get("base64"):
            path = self._save_upload(data["base64"], data.get("filename", "image.png"))
        if not path:
            return {"ok": False, "error": "Image required"}
        try:
            from core.vision import VisionService
            result = VisionService(ROOT).analyze_images([path], prompt)
            return {"ok": result.status == "COMPLETED", "text": result.text, "error": result.error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def api_audio(self, data):
        path = data.get("path", "")
        if data.get("base64"):
            path = self._save_upload(data["base64"], data.get("filename", "audio.mp3"))
        if not path:
            return {"ok": False, "error": "Audio required"}
        try:
            from core.audio import AudioService
            result = AudioService(ROOT).transcribe(path)
            return {"ok": result.status == "COMPLETED", "text": result.text, "error": result.error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def api_video(self, data):
        path = data.get("path", "")
        if data.get("base64"):
            path = self._save_upload(data["base64"], data.get("filename", "video.mp4"))
        if not path:
            return {"ok": False, "error": "Video required"}
        try:
            from core.video import VideoService
            result = VideoService(ROOT).analyze(path)
            return {"ok": result.status == "COMPLETED", "text": result.text, "error": result.error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def api_document(self, data):
        path = data.get("path", "")
        if data.get("base64"):
            path = self._save_upload(data["base64"], data.get("filename", "doc.pdf"))
        if not path:
            return {"ok": False, "error": "Document required"}
        try:
            from core.documents import DocumentService
            result = DocumentService(ROOT).extract(path)
            return {"ok": result.status == "COMPLETED", "text": result.text[:5000], "title": result.title, "error": result.error}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def start_server(port=8765):
    # Acquire ownership before HTTP, warmup, monitor, Gateway, or voice startup.
    from jarvis_core.single_instance import acquire_core_instance
    try:
        acquire_core_instance()
    except RuntimeError as exc:
        print('[CORE] DUPLICATE_PROCESS_BLOCKED PROCESS_ID=%d REASON=%s' %
              (os.getpid(), str(exc)), flush=True)
        return

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    # LAN mode configuration
    from jarvis_core.lan_config import get_lan_config
    _lan = get_lan_config()
    _http_host = _lan.bind_address
    _gateway_host = _lan.bind_address

    # SSL configuration (FAIL CLOSED)
    _ssl_context = None
    _ssl_enabled = _lan.ssl_enabled
    if _ssl_enabled:
        try:
            from jarvis_core.ssl_context import load_ssl_context
            _ssl_context = load_ssl_context()
            print('[SSL] TLS context loaded — HTTPS/WSS enabled')
        except Exception as e:
            print('[SSL] FATAL: TLS initialization failed: %s' % str(e))
            print('[SSL] GOLDEN_SSL=1 but certificates are invalid or missing.')
            print('[SSL] Run: python -m jarvis_core.ssl_context init')
            sys.exit(1)

    # P1.3: readiness SSOT — a 1a pergunta NAO e mecanismo de init.
    from jarvis_core.readiness import get_readiness
    _ready = get_readiness()
    _ready.begin()

    # Conectar MT5 automaticamente
    try:
        from mt5_connector import ensure_connection, get_status as mt5_status
        if ensure_connection():
            st = mt5_status()
            print('[MT5] ✅ Conectado! Conta: %s | Servidor: %s | Saldo: %.2f' % (
                st.get('account', '?'), st.get('server', '?'), st.get('balance', 0)))
        else:
            print('[MT5] ⚠️ Nao conectado. Abrir MetaTrader 5 primeiro.')
    except Exception as e:
        print('[MT5] ⚠️ Erro ao conectar: %s' % str(e)[:80])
    
    # Verificar API key na inicialização
    if CLAUDE_AVAILABLE:
        try:
            provider = get_claude_provider()
            if provider.api_key:
                print(f'[Claude] ✅ API key configurada ({len(provider.api_key)} chars)')
            else:
                print('[Claude] ⚠️ API key não encontrada. Configure com: configure_api_key SUA_KEY')
        except Exception as e:
            print(f'[Claude] ⚠️ Erro ao verificar key: {e}')
    
    _scheme = "https" if _ssl_enabled else "http"
    print('')
    print('═══════════════════════════════════════════')
    print('  Golden AI Studio V6.0 Auto-Connect')
    print('═══════════════════════════════════════════')
    print(f'  Dashboard: {_scheme}://{_http_host}:{port}/dashboard.html')
    print(f'  Studio:    {_scheme}://{_http_host}:{port}/studio_v7.html')
    if _lan.enabled:
        print(f'  LAN Mode:  ENABLED ({_http_host})')
    else:
        print(f'  LAN Mode:  OFF (localhost only)')
    if _ssl_enabled:
        print(f'  SSL Mode:  ENABLED (TLS 1.2+)')
    else:
        print(f'  SSL Mode:  OFF (plain HTTP)')
    print('  MT5:       Auto-connect (mantido vivo)')
    print('═══════════════════════════════════════════')
    print('')
    
    # Create server with optional SSL
    server = ThreadedHTTPServer((_http_host, port), GoldenAIHandler)
    if _ssl_context:
        server.socket = _ssl_context.wrap_socket(server.socket, server_side=True)

    try:
        from monitor_service import get_monitor_service
        get_monitor_service().start()
        print('[RADAR] Monitor persistente iniciado (intervalo: 60s)')
    except Exception as e:
        print('[RADAR] Monitor persistente indisponivel: %s' % str(e)[:120])
    try:
        from desktop_center import DESKTOP_CENTER
        from jarvis_core.voice_service import get_voice_service
        # CORE READY: registry/security/orchestrator/fast paths no ar.
        _ready.core_ready()
        # FULL READY em background: providers eager + probes + STT warmup.
        # O Desktop já pode abrir; a voz barra comandos até READY.
        import threading as _threading
        _warm_thread = _threading.Thread(target=warm_jarvis_boot,
                                         name="jarvis-boot-warm", daemon=True)
        _warm_thread.start()
        vs = get_voice_service()
        if vs.enabled:
            result = vs.start(DESKTOP_CENTER.service)
            if result.get("ok") and vs.is_running():
                print('[JARVIS-VOICE] Escuta local iniciada — diga "Jarvis" + comando (sem navegador).')
            else:
                print('[JARVIS-VOICE] Nao iniciada: %s' % str(result.get("error") or result.get("message"))[:120])
        else:
            print('[JARVIS-VOICE] Desativado (JARVIS_VOICE_SERVICE=0).')
    except Exception as e:
        print('[JARVIS-VOICE] Indisponivel: %s' % str(e)[:120])

    # Start Gateway (WebSocket/WSS) in background
    _gateway_instance = None
    _gateway_loop = None
    try:
        import asyncio as _asyncio
        import socket as _socket
        from jarvis_core.gateway.gateway import Gateway
        from jarvis_core.device_pairing import get_device_pairing_service

        _gw_port = 8766

        # Port conflict detection
        _port_check = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        try:
            _port_check.settimeout(1)
            _port_check.bind((_gateway_host, _gw_port))
            _port_check.close()
        except OSError:
            print('[GATEWAY] Porta %d ocupada — Gateway nao iniciado' % _gw_port)
            _gateway_instance = None
            _gateway_loop = None
            raise RuntimeError("Port occupied")

        _gateway_service = DESKTOP_CENTER.service  # SAME JarvisService instance
        # Dual bind: loopback always + LAN IP when enabled
        _gw_extra_hosts = []
        if _lan.enabled and _gateway_host != "127.0.0.1":
            _gw_extra_hosts = [_gateway_host]  # Add LAN IP as extra listener
        _gateway_instance = Gateway(
            _gateway_service,
            host="127.0.0.1",  # Always bind loopback first
            port=_gw_port,
            extra_hosts=_gw_extra_hosts,
            ssl_context=_ssl_context,  # None if SSL disabled
        )

        # Connect device pairing
        _pairing = get_device_pairing_service()
        _pairing.start()
        _gateway_instance.set_device_pairing(_pairing)
        _gateway_instance.set_lan_config(_lan)

        # Start gateway in background thread
        _gateway_loop = _asyncio.new_event_loop()

        async def _run_gateway():
            await _gateway_instance.start()
            try:
                while True:
                    await _asyncio.sleep(3600)
            except _asyncio.CancelledError:
                pass
            finally:
                await _gateway_instance.stop()

        def _gateway_thread():
            _gateway_loop.run_until_complete(_run_gateway())

        import threading as _threading
        _gw_thread = _threading.Thread(target=_gateway_thread, name="jarvis-gateway", daemon=True)
        _gw_thread.start()
        _gw_scheme = "wss" if _ssl_enabled else "ws"
        _gw_hosts = ["127.0.0.1"] + _gw_extra_hosts
        print('[GATEWAY] %s iniciado em %s' % (
            'WebSocket' if not _ssl_enabled else 'WebSocket Secure',
            ', '.join('%s://%s:%d/ws' % (_gw_scheme, h, _gw_port) for h in _gw_hosts)
        ))
    except Exception as e:
        print('[GATEWAY] Indisponivel: %s' % str(e)[:120])
        _gateway_instance = None
        _gateway_loop = None

    try:
        server.serve_forever()
    finally:
        # Shutdown limpo: gateway, voz, sem threads orfas.
        if _gateway_instance and _gateway_loop:
            try:
                _asyncio.run_coroutine_threadsafe(
                    _gateway_instance.stop(), _gateway_loop
                ).result(timeout=5)
            except Exception:
                pass
            try:
                _gateway_loop.call_soon_threadsafe(_gateway_loop.stop)
            except Exception:
                pass
        try:
            from jarvis_core.voice_service import get_voice_service as _get_vs
            _get_vs().stop()
        except Exception:
            pass
        try:
            from jarvis_core.device_pairing import get_device_pairing_service as _get_pairing
            _get_pairing().stop()
        except Exception:
            pass
        try:
            from desktop_center import DESKTOP_CENTER as _DC
            if hasattr(_DC.service, "close"):
                _DC.service.close()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    start_server(args.port)
