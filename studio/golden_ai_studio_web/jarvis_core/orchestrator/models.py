from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Route(str, Enum):
    DIRECT_TOOL = "DIRECT_TOOL"
    WINDOWS = "WINDOWS"
    SYSTEM = "SYSTEM"
    MARKET_DATA = "MARKET_DATA"
    MEMORY = "MEMORY"
    VISION = "VISION"
    WEB = "WEB"
    BROWSER = "BROWSER"
    CODING = "CODING"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    WHATSAPP = "WHATSAPP"
    GOLDEN = "GOLDEN"
    RADAR = "RADAR"
    MT5 = "MT5"
    TRADING = "TRADING"
    TASK = "TASK"
    CONVERSATION = "CONVERSATION"
    CLARIFY = "CLARIFY"


class ModelProfile(str, Enum):
    FAST = "FAST"
    VOICE_FAST = "VOICE_FAST"
    GENERAL = "GENERAL"
    DEEP = "DEEP"
    CODING = "CODING"
    VISION = "VISION"
    OFFLINE = "OFFLINE"


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"


class ProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    OFFLINE = "OFFLINE"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True)
class PlanStep:
    id: str
    intent: str
    route: Route
    tool: Optional[str] = None
    args: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    future_status: str = "PENDING"
    cancellable: bool = True
    background: bool = False


@dataclass(frozen=True)
class OrchestratorDecision:
    intent: str
    route: Route
    confidence: float
    requires_ai: bool
    requires_planning: bool
    requires_confirmation: bool
    requires_clarification: bool
    preferred_skill: str
    preferred_model_profile: ModelProfile
    steps: tuple[PlanStep, ...] = ()
    reason_code: str = ""
    allowed_tools: tuple[str, ...] = ()
    data_classification: DataClassification = DataClassification.INTERNAL
    research_level: str = "NO_RESEARCH"
    research_reason: str = "GENERAL_KNOWLEDGE_SUFFICIENT"
    router_decision_ms: int = 0
    answer_route: str = "DIRECT"


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    route: Route
    available: bool
    required_tools: tuple[str, ...]
    risk_profile: str
    model_profile: ModelProfile


@dataclass
class ProviderResult:
    ok: bool
    provider: str
    model: str
    state: ProviderState
    output: Any = None
    fallback_used: bool = False
    latency_ms: int = 0
    error: str = ""
    ttft_ms: int = 0
    generation_ms: int = 0
    attempts: tuple[dict[str, Any], ...] = ()
