from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class MarketSnapshot:
    stock_code: str
    time: str | None
    price: float | None
    high: float | None
    low: float | None
    open: float | None
    amount: float | None
    volume: float | None
    pre_close: float | None
    source: str


MarketDataCallback = Callable[[MarketSnapshot], None]


class MarketDataProvider(Protocol):
    def subscribe_tick(self, stock_codes: list[str], callback: MarketDataCallback) -> None:
        ...

    def subscribe_snapshot(
        self,
        stock_codes: list[str],
        interval_seconds: int,
        callback: MarketDataCallback,
    ) -> None:
        ...

    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None:
        ...

    def get_minute_bars(self, stock_code: str, count: int) -> list[dict]:
        ...
