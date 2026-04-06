"""T+0 strategy package."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.strategies.t0.strategy_engine import StrategyEngine

__all__ = ["StrategyEngine"]


def __getattr__(name: str):
    if name == "StrategyEngine":
        from src.strategy.strategies.t0.strategy_engine import StrategyEngine

        return StrategyEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
