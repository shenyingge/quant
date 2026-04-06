"""Tests for Backtrader adapters."""

import backtrader as bt

from src.strategy.adapters.backtrader_adapter import BacktraderStrategyWrapper
from src.strategy.strategies.t0.contracts.strategy import BarData, StrategyBase, StrategyParams


class SimpleT0Strategy(StrategyBase):
    """Test strategy implementation."""

    def __init__(self, params: StrategyParams):
        super().__init__(params)
        self.buy_count = 0
        self.sell_count = 0

    def on_bar(self, bar: BarData):
        if bar.close > bar.open:
            self.buy_count += 1
            return [{"type": "BUY", "volume": 100}]
        return [{"type": "SELL", "volume": 100}]

    def on_tick(self, tick):
        return None

    def on_trade(self, trade):
        pass


def test_backtrader_strategy_wrapper_is_subclass():
    """BacktraderStrategyWrapper is a backtrader Strategy subclass."""
    assert issubclass(BacktraderStrategyWrapper, bt.Strategy)


def test_backtrader_wrapper_init_with_strategy():
    """BacktraderStrategyWrapper can be initialized with strategy via params."""
    params = StrategyParams(name="test", stock_code="601138.SH", max_position=1000)
    strategy = SimpleT0Strategy(params)

    # params dict for BacktraderStrategyWrapper
    wrapper_params = {"strategy": strategy}
    assert wrapper_params["strategy"] is strategy


def test_qmt_datafeed_is_backtrader_compatible():
    """QMTDataFeed is backtrader DataFeed compatible."""
    from src.strategy.adapters.backtrader_datafeed import QMTDataFeed

    assert issubclass(QMTDataFeed, bt.DataBase)


def test_qmt_broker_interface_is_broker_compatible():
    """QMTBrokerInterface is backtrader Broker compatible."""
    from src.strategy.adapters.backtrader_broker import QMTBrokerInterface

    assert issubclass(QMTBrokerInterface, bt.brokers.BackBroker)


def test_simple_t0_strategy_on_bar():
    """SimpleT0Strategy responds to bar data correctly."""
    params = StrategyParams(name="test", stock_code="601138.SH", max_position=1000)
    strategy = SimpleT0Strategy(params)

    # Up bar (close > open)
    bar = BarData(
        stock_code="601138.SH",
        bar_time="2026-04-05 09:30:00",
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=1000,
    )

    signals = strategy.on_bar(bar)

    assert signals is not None
    assert len(signals) == 1
    assert signals[0]["type"] == "BUY"


def test_simple_t0_strategy_down_bar():
    """SimpleT0Strategy responds to down bar correctly."""
    params = StrategyParams(name="test", stock_code="601138.SH", max_position=1000)
    strategy = SimpleT0Strategy(params)

    # Down bar (close < open)
    bar = BarData(
        stock_code="601138.SH",
        bar_time="2026-04-05 09:35:00",
        open=10.1,
        high=10.2,
        low=9.9,
        close=10.0,
        volume=1000,
    )

    signals = strategy.on_bar(bar)

    assert signals is not None
    assert len(signals) == 1
    assert signals[0]["type"] == "SELL"
