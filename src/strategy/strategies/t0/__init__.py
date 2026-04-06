"""T+0 strategy runtime package.

Keep this module import-light so consumers can import submodules (e.g. feature
calculators for backtests) without triggering DB/QMT side effects.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.strategies.t0.strategy_diagnostics import StrategyDiagnostics
    from src.strategy.strategies.t0.t0_reconciler import T0Reconciler

__all__ = ["StrategyDiagnostics", "T0Reconciler"]


def __getattr__(name: str):
    if name == "StrategyDiagnostics":
        from src.strategy.strategies.t0.strategy_diagnostics import StrategyDiagnostics

        return StrategyDiagnostics
    if name == "T0Reconciler":
        from src.strategy.strategies.t0.t0_reconciler import T0Reconciler

        return T0Reconciler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
