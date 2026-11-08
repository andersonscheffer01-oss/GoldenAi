"""Golden Scalper Arena: isolated, simulation-only market laboratory."""

from .arena import GoldenScalperArena
from .agents import build_default_agents
from .contracts import (
    Bar,
    MarketSnapshot,
    PortfolioState,
    Side,
    StrategySignal,
    SymbolSpec,
    Tick,
    TradeRecord,
    VirtualPosition,
)
from .virtual_execution import VirtualExecution, VirtualExecutionConfig
from .replay import ReplayResult, run_replay

__all__ = [
    "Bar", "GoldenScalperArena", "MarketSnapshot", "PortfolioState",
    "Side", "StrategySignal", "SymbolSpec", "Tick", "TradeRecord",
    "VirtualExecution", "VirtualExecutionConfig", "VirtualPosition",
    "ReplayResult", "build_default_agents", "run_replay",
]


