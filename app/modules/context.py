"""
Golden AI - Contexto Compartilhado

Todas as variáveis globais que eram definidas no topo do golden_ai.py
agora ficam centralizadas aqui. Os módulos importam de:
    from app.modules.context import CFG, SERVICES
"""

import os
import sys
import uuid

# ============================================================
# CAMINHOS BASE
# ============================================================

ROOT_GOLDENAI = r"C:\GoldenAI"

if ROOT_GOLDENAI not in sys.path:
    sys.path.insert(0, ROOT_GOLDENAI)

# ============================================================
# CONFIGURAÇÃO CENTRALIZADA
# ============================================================

class CFG:
    """Configurações do Golden AI (antes eram constantes soltas)."""

    # Modelo padrão (fallback)
    MODELO = "orcarouter/Qwen3.8-27B-Uncensored:iq4_xs"

    # Caminhos principais
    PASTA_APP = r"C:\GoldenAI\app"
    PASTA_PROJETOS = r"C:\\GoldenAI\\projetos"
    PASTA_BACKUPS = r"C:\GoldenAI\backups"
    PASTA_LOGS = r"C:\GoldenAI\logs"

    # MetaEditor
    METAEDITOR = r"C:\Program Files\MetaTrader 5\metaeditor64.exe"

    # MT5
    PASTA_MT5_DADOS = r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\46741B95EA60FD79A8A625DA9A175331"
    PASTA_MT5_MQL5 = os.path.join(PASTA_MT5_DADOS, "MQL5")
    PASTA_MT5_EXPERTS = os.path.join(PASTA_MT5_MQL5, "Experts")

    # Limites
    MAX_CORRECOES = 5

    # Sessão
    SESSION_ID = str(uuid.uuid4())


# ============================================================
# SERVIÇOS (inicializados lazy)
# ============================================================

class SERVICES:
    """
    Container para instâncias de serviços do core.
    Cada serviço é inicializado sob demanda.
    """

    # Core V3
    SETTINGS = None
    PERMISSION_MANAGER = None
    AUDIT_LOGGER = None
    TOOL_REGISTRY = None

    # Model Router
    MODEL_ROUTER = None

    # Internet
    INTERNET = None

    # Browser / Documentos / Audio / Video / Vision
    BROWSER = None
    DOCUMENT = None
    AUDIO = None
    VIDEO = None
    VISION = None
    VECTOR_MEMORY = None

    # Market
    MARKET_SERVICE = None

    # Memory
    MEMORY_SERVICE = None

    # Media
    MEDIA_SERVICE = None

    # Quant
    QUANT_SERVICE = None

    # Agent Orchestrator
    ORCHESTRATOR = None

    # OpenCode
    OPENCODE_AVAILABLE = False


# ============================================================
# ESTADO DE SESSÃO (mutável)
# ============================================================

class SESSION:
    """Estado que muda durante a execução."""

    arquivo_alvo_atual = None
    ultimo_veredito_auditoria = None
    historico = []


# ============================================================
# INICIALIZAÇÃO DOS CORE SERVICES
# ============================================================

def init_core():
    """Inicializa os serviços do Core V3 (chamar uma vez no startup)."""

    # Importa e inicializa cada serviço com tratamento de erro
    try:
        from core.audit import AuditEvent, AuditLogger
        from core.config import load_settings
        from core.permissions import PermissionManager
        from core.tools import ToolDefinition, ToolRegistry

        SERVICES.SETTINGS = load_settings()
        SERVICES.PERMISSION_MANAGER = PermissionManager(SERVICES.SETTINGS)
        SERVICES.AUDIT_LOGGER = AuditLogger(CFG.PASTA_LOGS)
        SERVICES.TOOL_REGISTRY = ToolRegistry(SERVICES.PERMISSION_MANAGER)
        print("[Core V3] Integracao ativa.")
    except Exception as e:
        print(f"[Core V3] Integracao desativada: {e}")

    # Model Router
    try:
        from core.models import ModelRouter
        SERVICES.MODEL_ROUTER = ModelRouter(settings=SERVICES.SETTINGS)
    except Exception as e:
        print(f"[ModelRouter] Desativado: {e}")

    # Internet
    try:
        from core.internet import InternetService
        SERVICES.INTERNET = InternetService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Internet] Desativado: {e}")

    # Browser
    try:
        from core.browser import BrowserService
        SERVICES.BROWSER = BrowserService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Browser] Desativado: {e}")

    # Documentos
    try:
        from core.documents import DocumentService
        SERVICES.DOCUMENT = DocumentService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Documentos] Desativado: {e}")

    # Audio
    try:
        from core.audio import AudioService
        SERVICES.AUDIO = AudioService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Audio] Desativado: {e}")

    # Video
    try:
        from core.video import VideoService
        SERVICES.VIDEO = VideoService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Video] Desativado: {e}")

    # Vision
    try:
        from core.vision import VisionService
        SERVICES.VISION = VisionService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Vision] Desativado: {e}")

    # Vector Memory (Qdrant)
    try:
        from core.memory import VectorMemoryService
        SERVICES.VECTOR_MEMORY = VectorMemoryService(ROOT_GOLDENAI)
    except Exception as e:
        print(f"[Qdrant] Desativado: {e}")

    # Market
    try:
        from market import MarketAnalysisService
        SERVICES.MARKET_SERVICE = MarketAnalysisService()
    except Exception as e:
        print(f"[Market] Desativado: {e}")

    # Memory
    try:
        from core.memory import ScientificMemoryService
        SERVICES.MEMORY_SERVICE = ScientificMemoryService()
    except Exception as e:
        print(f"[Memory] Desativado: {e}")

    # Media
    try:
        from media_study import MediaStudyService
        SERVICES.MEDIA_SERVICE = MediaStudyService()
    except Exception as e:
        print(f"[Media] Desativado: {e}")

    # Quant
    try:
        from quant import QuantService
        SERVICES.QUANT_SERVICE = QuantService()
    except Exception as e:
        print(f"[Quant] Desativado: {e}")

    # Agent Orchestrator
    try:
        from agents import AgentOrchestrator
        SERVICES.ORCHESTRATOR = AgentOrchestrator()
    except Exception as e:
        print(f"[Orchestrator] Desativado: {e}")


def obter_modelo(perfil="CODER"):
    """Retorna o nome do modelo via ModelRouter, com fallback."""
    if SERVICES.MODEL_ROUTER is not None:
        try:
            return SERVICES.MODEL_ROUTER.get_model_name(perfil)
        except Exception:
            pass
    return CFG.MODELO
