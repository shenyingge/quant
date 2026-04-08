from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketSnapshot:
    stock_code: str
    time: str
    price: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    amount: Optional[float] = None
    volume: Optional[float] = None
    pre_close: Optional[float] = None
    source: str = "qmt"


MarketDataCallback = Callable[[MarketSnapshot], None]
