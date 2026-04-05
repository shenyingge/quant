from dataclasses import asdict, dataclass
from typing import Dict, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class MarketSnapshot:
    """Typed market snapshot payload for T+0 signal evaluation."""

    symbol: str
    trade_date: str
    bar_time: str
    last_price: float
    day_open: float
    day_high: float
    day_low: float
    vwap: float
    volume: int
    amount: float
    previous_close: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Contract for adapters that provide latest market snapshots."""

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        """Return the latest market snapshot for a symbol."""
