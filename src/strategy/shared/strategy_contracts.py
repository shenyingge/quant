"""Shared strategy contracts for pure strategies and executable runtimes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional


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
    direction: str
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
        return self.params.name

    @abstractmethod
    def on_bar(self, bar: BarData) -> list[dict] | None:
        """Called when a new bar is available."""

    @abstractmethod
    def on_tick(self, tick: TickData) -> list[dict] | None:
        """Called when a tick arrives."""

    @abstractmethod
    def on_trade(self, trade: TradeData) -> None:
        """Called when a trade execution callback arrives."""

    def reset(self) -> None:
        """Reset strategy state (useful for backtesting)."""
        return None


class StrategyRuntimeBase(ABC):
    """Executable strategy runtime base, similar to Backtrader's strategy shell."""

    strategy_key: ClassVar[str] = ""

    def __init__(self, *, strategy_name: str | None = None):
        default_name = strategy_name or self.strategy_key or self.__class__.__name__.lower()
        self._strategy_name = default_name

    @property
    def runtime_key(self) -> str:
        return self.strategy_key or self.__class__.__name__.lower()

    @property
    def strategy_name(self) -> str:
        return self._strategy_name

    @abstractmethod
    def run_once(self) -> dict:
        """Run one evaluation cycle and return a strategy result payload."""

