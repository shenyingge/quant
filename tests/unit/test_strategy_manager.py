"""Tests for StrategyManager."""

from src.strategy.shared.strategy_manager import StrategyManager
from src.strategy.strategies.t0.contracts.strategy import (
    BarData,
    StrategyBase,
    StrategyParams,
)


class DummyStrategy(StrategyBase):
    """Test implementation of StrategyBase."""

    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.bar_calls = []
        self.tick_calls = []
        self.trade_calls = []
        self.signals = []

    def on_bar(self, bar: BarData):
        self.bar_calls.append(bar)
        return self.signals if self.signals else None

    def on_tick(self, tick):
        self.tick_calls.append(tick)
        return None

    def on_trade(self, trade):
        self.trade_calls.append(trade)


def test_strategy_manager_init():
    """StrategyManager can be initialized."""
    manager = StrategyManager()
    assert isinstance(manager, StrategyManager)
    assert len(manager.strategies) == 0


def test_strategy_manager_register_strategy():
    """StrategyManager can register a strategy."""
    manager = StrategyManager()
    params = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    strategy = DummyStrategy(params)

    manager.register_strategy(strategy)

    assert "s1" in manager.strategies
    assert manager.strategies["s1"] is strategy


def test_strategy_manager_unregister_strategy():
    """StrategyManager can unregister a strategy."""
    manager = StrategyManager()
    params = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    strategy = DummyStrategy(params)

    manager.register_strategy(strategy)
    manager.unregister_strategy("s1")

    assert "s1" not in manager.strategies


def test_strategy_manager_broadcast_bar():
    """StrategyManager broadcasts bar to all strategies."""
    manager = StrategyManager()
    params1 = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    params2 = StrategyParams(name="s2", stock_code="601138.SH", max_position=1000)
    s1 = DummyStrategy(params1)
    s2 = DummyStrategy(params2)

    manager.register_strategy(s1)
    manager.register_strategy(s2)

    bar = BarData(
        stock_code="601138.SH",
        bar_time="2026-04-05 09:30:00",
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=1000,
    )

    results = manager.broadcast_bar(bar)

    assert len(s1.bar_calls) == 1
    assert len(s2.bar_calls) == 1
    assert s1.bar_calls[0] is bar
    assert s2.bar_calls[0] is bar
    assert len(results) == 0  # No signals returned


def test_strategy_manager_broadcast_bar_with_signals():
    """StrategyManager collects signals from strategies."""
    manager = StrategyManager()
    params = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    s1 = DummyStrategy(params)
    s1.signals = [{"type": "BUY", "volume": 100}]

    manager.register_strategy(s1)

    bar = BarData(
        stock_code="601138.SH",
        bar_time="2026-04-05 09:30:00",
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=1000,
    )

    results = manager.broadcast_bar(bar)

    assert len(results) == 1
    assert results[0] == ("s1", [{"type": "BUY", "volume": 100}])


def test_strategy_manager_reset_all():
    """StrategyManager can reset all strategies."""
    manager = StrategyManager()
    params = StrategyParams(name="s1", stock_code="601138.SH", max_position=1000)
    s1 = DummyStrategy(params)

    manager.register_strategy(s1)
    manager.reset_all()

    # Should not raise an exception
    assert "s1" in manager.strategies
