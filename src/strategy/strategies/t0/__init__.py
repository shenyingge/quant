"""T+0 strategy runtime package.

Keep this module import-light so consumers can import submodules (e.g. feature
calculators for backtests) without triggering DB/QMT side effects.
"""

import importlib
import sys
import types
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.shared.strategy_diagnostics import StrategyDiagnostics
    from src.strategy.shared.t0_reconciler import T0Reconciler

__all__ = ["StrategyDiagnostics", "T0Reconciler"]


_EAGER_SUBMODULE_ALIASES = {
    "data_fetcher": "src.strategy.shared.data_fetcher",
    "signal_generator": "src.strategy.shared.signal_generator",
}


_SUBMODULE_ALIASES = {
    "feature_calculator": "src.strategy.core.feature_calculator",
    "position_syncer": "src.strategy.shared.position_syncer",
    "regime_identifier": "src.strategy.shared.regime_identifier",
    "signal_state_repository": "src.strategy.shared.strategy_signal_repository",
    "strategy_diagnostics": "src.strategy.shared.strategy_diagnostics",
    "strategy_status_service": "src.strategy.shared.strategy_status_service",
    "t0_reconciler": "src.strategy.shared.t0_reconciler",
}


class _LazyAliasModule(types.ModuleType):
    def __init__(self, alias_name: str, target_module: str):
        super().__init__(alias_name)
        self._target_module = target_module

    def _load(self):
        module = importlib.import_module(self._target_module)
        sys.modules[self.__name__] = module
        return module

    def __getattr__(self, item: str):
        return getattr(self._load(), item)

    def __dir__(self):
        return dir(self._load())


for alias_name, target_module in _SUBMODULE_ALIASES.items():
    sys.modules.setdefault(
        f"{__name__}.{alias_name}",
        _LazyAliasModule(f"{__name__}.{alias_name}", target_module),
    )


for alias_name, target_module in _EAGER_SUBMODULE_ALIASES.items():
    module = importlib.import_module(target_module)
    sys.modules[f"{__name__}.{alias_name}"] = module


def __getattr__(name: str):
    if name == "StrategyDiagnostics":
        from src.strategy.shared.strategy_diagnostics import StrategyDiagnostics

        return StrategyDiagnostics
    if name == "T0Reconciler":
        from src.strategy.shared.t0_reconciler import T0Reconciler

        return T0Reconciler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
