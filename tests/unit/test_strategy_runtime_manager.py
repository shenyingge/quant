from src.strategy.shared.strategy_contracts import StrategyRuntimeBase
from src.strategy.shared.strategy_registry import register_strategy_runtime
from src.strategy.shared.strategy_runtime_manager import StrategyRuntimeManager


@register_strategy_runtime("runtime_manager_dummy_a")
class _DummyRuntimeA(StrategyRuntimeBase):
    def run_once(self) -> dict:
        return {"strategy": "a", "status": "ok"}


@register_strategy_runtime("runtime_manager_dummy_b")
class _DummyRuntimeB(StrategyRuntimeBase):
    def run_once(self) -> dict:
        return {"strategy": "b", "status": "ok"}


def test_strategy_runtime_manager_loads_registered_runtimes():
    manager = StrategyRuntimeManager(["runtime_manager_dummy_a", "runtime_manager_dummy_b"])

    runtimes = manager.load_runtimes()

    assert set(runtimes) == {"runtime_manager_dummy_a", "runtime_manager_dummy_b"}


def test_strategy_runtime_manager_runs_all_sequentially():
    manager = StrategyRuntimeManager(["runtime_manager_dummy_a", "runtime_manager_dummy_b"])
    manager.load_runtimes()

    results = manager.run_once_all()

    assert results["runtime_manager_dummy_a"]["status"] == "ok"
    assert results["runtime_manager_dummy_b"]["status"] == "ok"


def test_strategy_runtime_manager_runs_all_in_parallel():
    manager = StrategyRuntimeManager(
        ["runtime_manager_dummy_a", "runtime_manager_dummy_b"],
        max_workers=2,
    )
    manager.load_runtimes()

    results = manager.run_once_all(parallel=True)

    assert set(results) == {"runtime_manager_dummy_a", "runtime_manager_dummy_b"}
