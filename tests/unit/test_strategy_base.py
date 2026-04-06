"""Tests for StrategyBase and contracts."""

import inspect

from src.strategy.strategies.t0.contracts.strategy import (
    BarData,
    StrategyBase,
    StrategyParams,
    TickData,
    TradeData,
)


def test_strategy_base_is_abstract():
    """StrategyBase is abstract and cannot be instantiated directly."""
    from abc import ABC

    assert issubclass(StrategyBase, ABC)
    try:
        StrategyBase(params=StrategyParams(name="test", stock_code="000001.SZ", max_position=1000))
        assert False, "Should not instantiate"
    except TypeError:
        pass


def test_strategy_params_minimal_init():
    """StrategyParams can be initialized with minimal required fields."""
    params = StrategyParams(
        name="test_strategy",
        stock_code="601138.SH",
        max_position=1000,
    )
    assert params.name == "test_strategy"
    assert params.stock_code == "601138.SH"
    assert params.max_position == 1000


def test_strategy_base_on_bar_callback():
    """on_bar callback signature is correct."""
    sig = inspect.signature(StrategyBase.on_bar)
    params_list = list(sig.parameters.keys())
    assert params_list == ["self", "bar"]


def test_strategy_base_on_tick_callback():
    """on_tick callback signature is correct."""
    sig = inspect.signature(StrategyBase.on_tick)
    params_list = list(sig.parameters.keys())
    assert params_list == ["self", "tick"]


def test_strategy_base_on_trade_callback():
    """on_trade callback signature is correct."""
    sig = inspect.signature(StrategyBase.on_trade)
    params_list = list(sig.parameters.keys())
    assert params_list == ["self", "trade"]


def test_bar_data_frozen():
    """BarData is immutable."""
    bar = BarData(
        stock_code="601138.SH",
        bar_time="2026-04-05 09:30:00",
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=1000,
    )
    try:
        bar.close = 10.5
        assert False, "Should not modify frozen dataclass"
    except (AttributeError, TypeError):
        pass


def test_tick_data_construction():
    """TickData can be constructed with optional fields."""
    tick = TickData(
        stock_code="601138.SH",
        time="2026-04-05 09:30:03",
        price=10.15,
        bid=10.14,
        ask=10.16,
    )
    assert tick.price == 10.15
    assert tick.bid == 10.14


def test_trade_data_construction():
    """TradeData captures execution details."""
    trade = TradeData(
        order_id="order-123",
        stock_code="601138.SH",
        direction="BUY",
        filled_price=10.15,
        filled_volume=100,
        filled_time="2026-04-05 09:30:05",
    )
    assert trade.order_id == "order-123"
    assert trade.filled_volume == 100
