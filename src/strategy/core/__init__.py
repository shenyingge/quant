"""平台无关的 T+0 策略核心。"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.core.kernel import T0StrategyKernel

__all__ = ["T0StrategyKernel"]


def __getattr__(name: str):
    if name == "T0StrategyKernel":
        from src.strategy.core.kernel import T0StrategyKernel

        return T0StrategyKernel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
