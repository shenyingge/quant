"""Strategy base class and typed contracts for T+0 strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .market_data import MarketSnapshot


@dataclass(frozen=True)
class StrategyParams:
    """Strategy configuration parameters."""

    name: str
    stock_code: str
    max_position: int
    other_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BarData:
    """一根 K 线数据（分钟级或更高频）"""

    stock_code: str
    bar_time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: Optional[float] = None


@dataclass(frozen=True)
class TickData:
    """Tick 级数据"""

    stock_code: str
    time: str
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_volume: Optional[int] = None
    ask_volume: Optional[int] = None


@dataclass(frozen=True)
class TradeData:
    """成交回调数据"""

    order_id: str
    stock_code: str
    direction: str  # BUY / SELL
    filled_price: float
    filled_volume: int
    filled_time: str


class StrategyBase(ABC):
    """策略基类，所有策略须继承此类。纯业务逻辑，无 QMT/Redis/DB 依赖。"""

    def __init__(self, params: StrategyParams):
        self.params = params
        self.stock_code = params.stock_code

    @property
    def strategy_name(self) -> str:
        """Strategy name for logging/identification."""
        return self.params.name

    @abstractmethod
    def on_bar(self, bar: BarData) -> list[dict] | None:
        """
        Called when a new bar is available.

        Args:
            bar: BarData object with OHLCV

        Returns:
            List of signal dicts (e.g., [{"type": "BUY", "volume": 100}]) or None
        """
        ...

    @abstractmethod
    def on_tick(self, tick: TickData) -> list[dict] | None:
        """
        Called when a tick arrives (if tick subscription enabled).

        Args:
            tick: TickData object with real-time price

        Returns:
            List of signal dicts or None
        """
        ...

    @abstractmethod
    def on_trade(self, trade: TradeData) -> None:
        """
        Called when a trade execution callback arrives.

        Args:
            trade: TradeData object with execution details
        """
        ...

    def reset(self) -> None:
        """Reset strategy state (useful for backtesting)."""
        pass
