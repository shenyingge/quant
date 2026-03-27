"""T+0 strategy package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.strategy_engine import StrategyEngine
    from src.strategy.t0_orchestrator import T0Orchestrator

__all__ = ["StrategyEngine", "T0Orchestrator"]


def __getattr__(name: str):
    if name == "StrategyEngine":
        from src.strategy.strategy_engine import StrategyEngine

        return StrategyEngine
    if name == "T0Orchestrator":
        from src.strategy.t0_orchestrator import T0Orchestrator

        return T0Orchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
