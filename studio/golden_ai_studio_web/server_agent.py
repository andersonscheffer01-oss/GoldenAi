Warning: truncated output (original token count: 93782)
Total output lines: 7554

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
import uuid
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from datetime import datetime
from threading import Event, Lock, Thread

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

ROOT = Path(
    os.environ.get("GOLDENAI_ROOT")
    or Path(__file__).resolve().parents[2]
).resolve()
MT5_PATH = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis_core.runtime_profile import DEFAULT_PROFILE, resolve_runtime_profile
from jarvis_core.audit import AuditLog
from jarvis_core.security import SecurityManager
from jarvis_core.security_compatibility import ExecutionSecurityFacade
from jarvis_core.gateway.auth import AuthManager
from jarvis_core.http_perimeter import HttpPerimeter
from jarvis_core.lifecycle import CoreLifecycle
from jarvis_core.arena_panel import load_arena_report

ACTIVE_RUNTIME_PROFILE = DEFAULT_PROFILE
ACTIVE_CORE_LIFECYCLE = None

# Legacy operational families remain available for compatibility, but are
# frozen at the authenticated dispatcher until their canonical read/mutation
# contracts are migrated one by one.  Pure catalog/read endpoints are not in
# this list and continue through their existing read-only compatibility path.
LEGACY_ROUTE_FREEZE_EXACT = frozenset({
    "/api/mt5/compile", "/api/mt5/backtest", "/api/mt5/real_backtest",
    "/api/mt5/import_history", "/api/mt5/auto_trade",
    "/api/mt5/close_position", "/api/strategy_catalog",
    "/api/strategy_audit", "/api/portfolio_backtest", "/api/meta_strategy",
    "/api/walk_forward", "/api/risk/config", "/api/validation/real",
    "/api/validation/all_real", "/api/monitor/toggle",
    "/api/strategy_manager/toggle", "/api/strategy_manager/toggle_mode",
    "/api/strategy_manager/preset", "/api/strategy_manager/auto_rank",
})
LEGACY_ROUTE_FREEZE_PREFIXES = (
    "/api/scanner/", "/api/risk/", "/api/validation/", "/api/chart_",
    "/api/position/", "/api/monitor/", "/api/journal/",
)

_canonical_audit = AuditLog(ROOT / "golden_runtime.db")
_canonical_security = SecurityManager(audit_log=_canonical_audit)
HTTP_AUTH_MANAGER = AuthManager()
HTTP_PERIMETER = HttpPerimeter(
    auth_manager=HTTP_AUTH_MANAGER, audit_log=_canonical_audit,
    runtime_profile_provider=lambda: ACTIVE_RUNTIME_PROFILE)

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
    PERMISSION_MANAGER.execution.security_facade = ExecutionSecurityFacade(
        _canonical_security)
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
        return "Erro Gemini: HTTP %s" % e.code
    except (TimeoutError, urllib.error.URLError) as e:
        if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
            return "Erro Gemini: TIMEOUT"
        return "Erro Gemini: TRANSPORT_ERROR"
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return "Erro Gemini: RESPONSE_PARSE_ERROR"
    except Exception:
        return "Erro Gemini: INTERNAL_ERROR"


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


def warm_jarvis_boot(skip_voice=False):
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
    if skip_voice:
        ready.record(stt_warm="disabled_by_profile")
    else:
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

    _JARVIS_SHELL_ASSETS = {
        "/jarvis_ui/jarvis.html",
        "/jarvis_ui/src/desktop-shell.js",
        "/jarvis_ui/src/desktop-shell.css",
    }

    def __init__(self, *args, **kwargs):
        web_dir = str(Path(__file__).parent.resolve())
        super().__init__(*args, directory=web_dir, **kwargs)

    def _request_path(self):
        return HTTP_PERIMETER.path_only(self.path)

    def end_headers(self):
        if self._request_path() in self._JARVIS_SHELL_ASSETS:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _source_ip(self):
        try:
            return str(self.client_address[0])
        except Exception:
            return "unknown"

    def _send_json(self, payload, status_code=200):
        response_bytes = json.dumps(payload, ensure_ascii=False,
                                    cls=_NumpyEncoder).encode('utf-8')
        self.send_response(int(status_code))
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response_bytes)))
        for key, value in HTTP_PERIMETER.cors_headers(
                self.headers.get('Origin', '')).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response_bytes)

    def _authorize_http(self, method, path):
        decision = HTTP_PERIMETER.authorize(
            method, path, self.headers, source_ip=self._source_ip())
        if not decision.allowed:
            self._send_json({"ok": False, "error": decision.reason,
                             "code": decision.code,
                             "request_id": decision.context.get("request_id", "")},
                            decision.status_code)
            return None
        return decision

    @staticmethod
    def _legacy_route_frozen(path):
        path = HTTP_PERIMETER.path_only(path)
        return (path in LEGACY_ROUTE_FREEZE_EXACT or
                any(path.startswith(prefix) for prefix in LEGACY_ROUTE_FREEZE_PREFIXES))

    def _audit_route_boundary(self, data, path, status, reason):
        context = dict((data or {}).get("_http_context") or {})
        request_id = str(context.get("request_id") or uuid.uuid4().hex)
        correlation_id = str(context.get("correlation_id") or request_id)
        envelope = {
            **context,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "route": path,
            "surface": context.get("surface", "http"),
            "operation": "%s %s" % (self.command, path),
            "action": "LEGACY_ROUTE_%s" % status,
            "status": status,
            "runtime_profile": ACTIVE_RUNTIME_PROFILE.name,
            "target": path,
        }
        try:
            _canonical_audit.add(
                task_id=request_id, command="legacy_route_boundary",
                tool="http_route_boundary", risk="HIGH", status=status,
                arguments={"route": path, "method": self.command},
                result={"ok": False, "reason": reason}, envelope=envelope)
        except Exception:
            # The denial itself stays fail-closed if audit storage is degraded.
            pass
        return request_id, correlation_id

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/studio_v7.html"
        path = self._request_path()
        if path == "/health":
            if self._authorize_http("GET", path) is None:
                return
            payload = {"ok": True, "service": "golden-ai",
                       "runtime_profile": ACTIVE_RUNTIME_PROFILE.name}
            if ACTIVE_CORE_LIFECYCLE is not None:
                payload.update(ACTIVE_CORE_LIFECYCLE.snapshot())
            self._send_json(payload, 200)
        elif path.startswith("/api/"):
            self.handle_api()
        elif path.startswith("/stream/"):
            self.handle_stream()
        else:
            super().do_GET()

    def do_POST(self):
        if self._request_path().startswith("/api/"):
            self.handle_api()
        elif self._request_path().startswith("/stream/"):
            self.handle_stream()
        else:
            super().do_POST()

    def do_OPTIONS(self):
        decision = HTTP_PERIMETER.preflight(self.headers)
        self.send_response(decision.status_code)
        for key, value in HTTP_PERIMETER.cors_headers(
                self.headers.get('Origin', '')).items():
            self.send_header(key, value)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',
                         'Content-Type, Authorization, X-Request-ID, X-Correlation-ID')
        self.end_headers()

    def log_message(self, format, *args):
        pass

    def handle_api(self):
        try:
            path = self._request_path()
            decision = self._authorize_http(self.command, path)
            if decision is None:
                return
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length else b'{}'
            try:
                data = json.loads(body) if body else {}
            except:
                data = {}
            try:
                data = dict(data or {})
                data["_http_context"] = decision.context
                response = self.route_api(path, data)
            except Exception as e:
                response = {"ok": False, "error": str(e)}
            # Ensure response is always serializable
            try:
                response_bytes = json.dumps(response, ensure_ascii=False, cls=_NumpyEncoder).encode('utf-8')
            except (TypeError, ValueError) as e:
                response = {"ok": False, "error": f"Resposta nao serializavel: {str(e)}"}
                response_bytes = json.dumps(response, ensure_ascii=False, cls=_NumpyEncoder).encode('utf-8')
            response_status = int(response.pop("_http_status", 200)) if isinstance(response, dict) else 200
            self._send_json(response, response_status)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected, nothing to do
        except Exception as e:
            try:
                err_resp = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False).encode('utf-8')
                self._send_json({"ok": False, "error": str(e)}, 500)
            except:
                pass

    # ═══════════════════════════════════════════════════════════════
    # STREAMING WITH TOOL-CALLING LOOP
    # ═══════════════════════════════════════════════════════════════

    def handle_stream(self):
        """Canonical SSE compatibility route owned by JarvisService."""
        decision = self._authorize_http(self.command, self._request_path())
        if decision is None:
            return
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            data = dict(json.loads(body) if body else {})
        except (TypeError, ValueError):
            data = {}
        message = data.get("message", "")
        session_id = str(data.get("session_id") or "default")[:120]
        cancel_event = Event()

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        for key, value in HTTP_PERIMETER.cors_headers(
                self.headers.get("Origin", "")).items():
            self.send_header(key, value)
        self.end_headers()

        payload_context = self._legacy_audit_context(
            data, session_id, "legacy_stream")
        try:
            service = self._legacy_service()
            events = service.stream_response(
                message,
                surface="legacy_stream",
                conversation_id=session_id,
                source="legacy_stream",
                audit_context=payload_context,
                cancel_event=cancel_event,
                images=data.get("images") or [],
                files=data.get("files") or [],
            )
            for event in events:
                kind = event.get("type")
                if kind == "chunk":
                    outgoing = {"token": event.get("text", ""), "done": False}
                elif kind == "done":
                    outgoing = {
                        "done": True,
                        "full_response": event.get("full_response", ""),
                        "request_id": event.get("request_id", ""),
                        "correlation_id": event.get("correlation_id", ""),
                    }
                elif kind == "provider_selected":
                    outgoing = {"stream_event": "STREAM_PROVIDER_SELECTED",
                                "provider": event.get("provider", ""),
                                "model": event.get("model", "")}
                elif kind == "cancelled":
                    outgoing = {"error": "stream_cancelled", "done": True}
                elif kind == "error":
                    outgoing = {"error": event.get("error", "stream_failed"),
                                "done": True}
                else:
                    continue
                if not self._send_sse(outgoing):
                    cancel_event.set()
                    break
        except (BrokenPipeError, ConnectionResetError):
            cancel_event.set()
        except Exception as exc:
            cancel_event.set()
            self._send_sse({"error": str(exc)[:300], "done": True})

    def _send_sse(self, data):
        try:
            self.wfile.write(f"data: {json.dumps(data, ensure_ascii=False, cls=_NumpyEncoder)}\n\n".encode())
            self.wfile.flush()
            return True
        except:
            return False

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
          …73782 tokens truncated…providers.append({"name": name, "state": state,
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
        return get_market_overview(mt5_enabled=ACTIVE_RUNTIME_PROFILE.mt5_enabled)

    def _api_market_forex(self, data):
        from market_data import get_forex_analysis
        return get_forex_analysis((data or {}).get("symbol"),
                                  mt5_enabled=ACTIVE_RUNTIME_PROFILE.mt5_enabled)

    def _api_market_chart(self, data):
        from market_data import get_market_chart
        data = data or {}
        return get_market_chart(data.get("symbol", "XAUUSD"),
                                data.get("timeframe", "M15"),
                                mt5_enabled=ACTIVE_RUNTIME_PROFILE.mt5_enabled)

    def _api_market_tick(self, data):
        from market_data import get_market_tick
        return get_market_tick((data or {}).get("symbol", "XAUUSD"),
                               mt5_enabled=ACTIVE_RUNTIME_PROFILE.mt5_enabled)

    def _api_market_ai_context(self, data):
        from market_data import get_market_ai_context
        return get_market_ai_context((data or {}).get("symbol", "XAUUSD"),
                                     mt5_enabled=ACTIVE_RUNTIME_PROFILE.mt5_enabled)

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

    @staticmethod
    def _market_analysis_message(mode, symbol, timeframe, question=""):
        instructions = {
            "completa": "Cruze técnica, força relativa, macro, risco, setup e níveis; entregue cenários condicionais, gatilhos, invalidação, riscos e dados ausentes.",
            "tecnica": "Analise candles, estrutura, RSI, ATR, tendências, níveis e confluências; informe gatilho técnico, invalidação e quando não operar.",
            "fundamental": "Analise somente fundamentos disponíveis, juros, inflação, dólar, eventos, notícias e força relativa; diferencie observação de ausência.",
            "risco": "Avalie volatilidade, ATR, spread, distância até níveis, alinhamento temporal, histórico e risco de evento sem sugerir execução.",
            "setup": "Audite o setup do scanner, condições, direção, confluência, relação risco-retorno, gatilho, stop, alvos e cancelamento.",
            "explicar": "Explique suportes e resistências, testes, relevância, distância, rompimentos e troca de polaridade.",
            "pergunta_contextual": "Responda à pergunta contextual usando somente o MarketContext atual e declare dados ausentes.",
        }
        if mode == "pergunta_contextual" and question:
            task = question[:2000]
        else:
            task = instructions.get(mode, instructions["completa"])
        return (
            f"Ativo {symbol} no timeframe {timeframe}. Modalidade {mode or 'completa'}. "
            f"{task} Responda em português do Brasil. Use somente dados observados no "
            "MARKET_CONTEXT estruturado. Não invente valores, não transforme score em "
            "probabilidade e não emita ordem de compra ou venda."
        )

    def _api_market_analyze(self, data):
        """Canonical Market AI response with structured context and no tools."""
        payload = data or {}
        symbol = str(payload.get("symbol") or "XAUUSD").strip()[:32]
        timeframe = str(payload.get("timeframe") or "M15").upper()[:8]
        mode = str(payload.get("mode") or "completa").strip().lower()[:40]
        question = str(payload.get("question") or "").strip()
        from desktop_center import DESKTOP_CENTER
        service = DESKTOP_CENTER.service
        context_result = service.market_context_snapshot({
            "symbol": symbol, "timeframe": timeframe,
        })
        context = context_result.get("context") or {
            "surface": "market", "symbol": symbol, "selected_asset": symbol,
            "timeframe": timeframe, "availability": "UNAVAILABLE",
            "freshness": "UNAVAILABLE", "provenance": {},
        }
        message = self._market_analysis_message(mode, symbol, timeframe, question)
        result = service.generate_response(
            message, surface="market_deep_analysis",
            conversation_id=payload.get("conversation_id") or
            f"market-analysis:{symbol}:{timeframe}",
            market_context=context, source="market",
            audit_context=payload.get("_http_context"))
        timestamp = datetime.now().isoformat()
        response = result.get("response") or result.get("error") or "Sem resposta."
        snapshot = dict(payload.get("snapshot") or {})
        snapshot.update({"context_timestamp": context.get("context_timestamp"),
                         "freshness": context.get("freshness", "UNKNOWN"),
                         "provenance": context.get("provenance", {}),
                         "availability": context.get("availability", "UNKNOWN")})
        audit = {
            "timestamp": timestamp, "symbol": symbol, "timeframe": timeframe,
            "mode": mode, "response": response, "snapshot": snapshot,
            "evaluation_status": "pendente", "provider": result.get("provider", ""),
            "model": result.get("model", ""),
            "request_id": result.get("response_id", ""),
            "surface": "market_deep_analysis",
        }
        audit_path = ROOT / "data" / "market_ai_audit.jsonl"
        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(audit, ensure_ascii=False, cls=_NumpyEncoder) + "\n")
        except Exception as exc:
            return {**result, "ok": False, "error": f"Registro de evidencia indisponível: {exc}",
                    "audit": "falhou"}
        return {**result, "timestamp": timestamp, "audit": "registrada",
                "market_context_status": "AVAILABLE" if context_result.get("ok") else "UNAVAILABLE"}

    def api_search(self, data):
        query = data.get("query", "")
        return {"ok": True, "result": self._tool_web_search({"query": query})}

    def api_chat(self, data):
        """Compatibility chat route delegated to the canonical model boundary."""
        payload = data or {}
        message = str(payload.get("message") or payload.get("text") or "").strip()
        session_id = str(payload.get("session_id") or "default")[:120]
        if not message:
            return {"ok": False, "error": "Empty"}

        service = self._legacy_service()
        result = service.generate_response(
            message,
            surface="legacy_main",
            conversation_id=session_id,
            source="legacy_chat",
            audit_context=self._legacy_audit_context(
                payload, session_id, "legacy_chat"),
        )
        result = dict(result or {})
        result["timestamp"] = datetime.now().isoformat()
        result["compatibility_bridge"] = True
        result["security_owner"] = "jarvis_core.security.SecurityManager"
        result["audit_owner"] = "jarvis_core.audit.AuditLog"
        return result

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


def start_server(port=8765, runtime_profile=None):
    global ACTIVE_RUNTIME_PROFILE, ACTIVE_CORE_LIFECYCLE
    ACTIVE_RUNTIME_PROFILE = resolve_runtime_profile(runtime_profile)
    from desktop_center import DESKTOP_CENTER
    DESKTOP_CENTER.service.apply_runtime_profile(ACTIVE_RUNTIME_PROFILE)
    print('[RUNTIME] profile=%s' % ACTIVE_RUNTIME_PROFILE.name, flush=True)

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

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.additional_servers = []

        def shutdown(self):
            for additional in self.additional_servers:
                additional.shutdown()
            super().shutdown()

        def server_close(self):
            for additional in self.additional_servers:
                try:
                    additional.shutdown()
                finally:
                    additional.server_close()
            super().server_close()

    # LAN mode configuration
    from jarvis_core.lan_config import get_lan_config
    _lan = get_lan_config()
    HTTP_PERIMETER.set_lan_config(_lan)
    _http_hosts = _lan.http_bind_addresses()
    _http_host = _http_hosts[0]
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

    # Conectar MT5 automaticamente apenas no perfil operacional legado.
    if ACTIVE_RUNTIME_PROFILE.mt5_enabled:
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
    else:
        print('[MT5] DISABLED_BY_PROFILE — connector startup skipped', flush=True)
    
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
        print('  LAN Mode:  ENABLED (%s)' % ', '.join(_http_hosts[1:]))
    else:
        print(f'  LAN Mode:  OFF (localhost only)')
    if _ssl_enabled:
        print(f'  SSL Mode:  ENABLED (TLS 1.2+)')
    else:
        print(f'  SSL Mode:  OFF (plain HTTP)')
    print('  MT5:       %s' % ('Auto-connect (mantido vivo)' if ACTIVE_RUNTIME_PROFILE.mt5_enabled else 'DISABLED_BY_PROFILE'))
    print('═══════════════════════════════════════════')
    print('')
    
    # Create server with optional SSL
    server = ThreadedHTTPServer((_http_host, port), GoldenAIHandler)
    additional_threads = []
    if len(_http_hosts) > 1:
        for host in _http_hosts[1:]:
            additional = ThreadedHTTPServer((host, port), GoldenAIHandler)
            server.additional_servers.append(additional)
            additional_threads.append(Thread(
                target=additional.serve_forever,
                name='jarvis-http-lan', daemon=True,
            ))
    if _ssl_context:
        server.socket = _ssl_context.wrap_socket(server.socket, server_side=True)
        for additional in server.additional_servers:
            additional.socket = _ssl_context.wrap_socket(
                additional.socket, server_side=True)
    for listener_thread in additional_threads:
        listener_thread.start()
    ACTIVE_CORE_LIFECYCLE = CoreLifecycle(
        runtime_profile=ACTIVE_RUNTIME_PROFILE.name,
        auth_manager=HTTP_AUTH_MANAGER,
        security_manager=_canonical_security,
        audit_log=_canonical_audit,
        pid=os.getpid(),
        parent_pid=os.getppid(),
        market_live_available=hasattr(
            GoldenAIHandler, "_api_jarvis_golden_market_live"),
    )

    if ACTIVE_RUNTIME_PROFILE.monitor_enabled:
        try:
            from monitor_service import get_monitor_service
            get_monitor_service().start()
            print('[RADAR] Monitor persistente iniciado (intervalo: 60s)')
        except Exception as e:
            print('[RADAR] Monitor persistente indisponivel: %s' % str(e)[:120])
    else:
        print('[RADAR] Monitor persistente DISABLED_BY_PROFILE', flush=True)
    try:
        # CORE READY: registry/security/orchestrator/fast paths no ar.
        _ready.core_ready()
        # FULL READY em background: providers eager + probes + STT warmup.
        # O Desktop já pode abrir; a voz barra comandos até READY.
        import threading as _threading
        _warm_thread = _threading.Thread(target=warm_jarvis_boot,
                                         kwargs={"skip_voice": not ACTIVE_RUNTIME_PROFILE.voice_enabled},
                                         name="jarvis-boot-warm", daemon=True)
        _warm_thread.start()
        if ACTIVE_RUNTIME_PROFILE.voice_enabled:
            from jarvis_core.voice_service import get_voice_service
            vs = get_voice_service()
            if vs.enabled:
                result = vs.start(DESKTOP_CENTER.service)
                if result.get("ok") and vs.is_running():
                    print('[JARVIS-VOICE] Escuta local iniciada — diga "Jarvis" + comando (sem navegador).')
                else:
                    print('[JARVIS-VOICE] Nao iniciada: %s' % str(result.get("error") or result.get("message"))[:120])
            else:
                print('[JARVIS-VOICE] Desativado (JARVIS_VOICE_SERVICE=0).')
        else:
            print('[JARVIS-VOICE] DISABLED_BY_PROFILE', flush=True)
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
            auth_manager=HTTP_AUTH_MANAGER,
            runtime_metadata_provider=ACTIVE_CORE_LIFECYCLE.snapshot,
            lifecycle_controller=ACTIVE_CORE_LIFECYCLE,
            lifecycle_server=server,
        )

        # Connect device pairing
        _pairing = get_device_pairing_service()
        _pairing.set_audit_context(
            _canonical_audit, ACTIVE_CORE_LIFECYCLE.snapshot)
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
        if ACTIVE_RUNTIME_PROFILE.voice_enabled:
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
        ACTIVE_CORE_LIFECYCLE = None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runtime-profile", default="default")
    args = parser.parse_args()
    start_server(args.port, args.runtime_profile)

