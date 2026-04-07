from src.strategy.shared.strategy_contracts import StrategyRuntimeBase
from src.strategy.shared.strategy_registry import build_strategy_runtime, get_strategy_runtime_class
from src.strategy.strategies.t0.strategy_engine import StrategyEngine


def test_get_strategy_runtime_class_discovers_t0_runtime():
    runtime_cls = get_strategy_runtime_class("t0")

    assert runtime_cls is StrategyEngine
    assert issubclass(runtime_cls, StrategyRuntimeBase)


def test_build_strategy_runtime_instantiates_registered_class(monkeypatch):
    monkeypatch.setattr(StrategyEngine, "__init__", lambda self, strategy_name=None: None)

    runtime = build_strategy_runtime("t0")

    assert isinstance(runtime, StrategyEngine)
