from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

class Risk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AgentState(str, Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    ERROR = "ERROR"

class ResponsePolicy(str, Enum):
    FINAL = "FINAL"
    NEEDS_SYNTHESIS = "NEEDS_SYNTHESIS"
    STRUCTURED = "STRUCTURED"
    BACKGROUND = "BACKGROUND"


class SideEffectClass(str, Enum):
    """Describes impact metadata; it never grants execution permission."""

    READ_ONLY = "READ_ONLY"
    LOCAL_MUTATION = "LOCAL_MUTATION"
    EXTERNAL_MUTATION = "EXTERNAL_MUTATION"
    SENSITIVE_OPERATION = "SENSITIVE_OPERATION"
    FINANCIAL_OPERATION = "FINANCIAL_OPERATION"


BROWSER_READ = "BROWSER_READ"
BROWSER_ACTION = "BROWSER_ACTION"

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable[..., dict[str, Any]]
    risk: Risk = Risk.LOW
    confirmation: bool = False
    timeout: int = 15
    parameters: dict[str, type] = field(default_factory=dict)
    llm_enabled: bool = True
    parameter_descriptions: dict[str, str] = field(default_factory=dict)
    category: str = "general"
    sensitive_fields: tuple[str, ...] = ()
    dynamic_risk: bool = False
    response_policy: ResponsePolicy = ResponsePolicy.NEEDS_SYNTHESIS
    expected_latency_ms: int = 0
    action_class: str = BROWSER_ACTION
    authorization_scope: str = ""
    provider: str = "jarvis_core"
    side_effect_class: str = ""
    security_requirements: tuple[str, ...] = ()
    approval_requirements: tuple[str, ...] = ()
    availability: str = "registered"
    health: str = "unknown"
    provenance: str = "internal"
