# ═══════════════════════════════════════════════════════════════════
# memory/models.py
# √ (Golden Jarvis 2.0) Tipos e estruturas de memória
# ═══════════════════════════════════════════════════════════════════
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# --- Tipos de memória ---------------------------------------------------

class MemoryType(str, Enum):
    SESSION = "session"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MemoryCategory(str, Enum):
    PREFERENCE = "preference"
    PROJECT = "project"
    KNOWLEDGE = "knowledge"
    DECISION = "decision"
    TRADING = "trading"
    GENERAL = "general"


# --- ProveniÊncia ------------------------------------------------------

class MemorySource(str, Enum):
    USER = "user"
    JARVIS = "jarvis"
    TOOL = "tool"
    GOLDEN = "golden"
    RADAR = "radar"
    AGENT = "agent"
    IMPORT = "import"
    SYSTEM = "system"


# --- Dados de sessão ---------------------------------------------------

@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    created_at: float
    last_activity: float
    ended_at: Optional[float]
    status: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# --- Registro genérico de memória --------------------------------------

@dataclass
class MemoryRecord:
    id: Optional[int] = None
    memory_type: MemoryType = MemoryType.SEMANTIC
    category: MemoryCategory = MemoryCategory.GENERAL
    content: str = ""
    summary: str = ""
    importance: int = 50
    confidence: float = 0.5
    source: MemorySource = MemorySource.JARVIS
    source_id: Optional[str] = None
    session_id: Optional[str] = None
    namespace: str = "jarvis"
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    last_accessed_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    access_count: int = 0
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


# --- Resumo de status do subsistema de memória --------------------------

@dataclass
class MemoryStatus:
    ok: bool
    database: str
    sessions: str
    semantic: str
    embedding_model: str
    semantic_search: str
    degraded_features: List[str] = field(default_factory=list)
    message: str = ""
    active_memories: int = 0
    total_memories: int = 0
    current_session: Optional[str] = None
    sessions_count: int = 0
