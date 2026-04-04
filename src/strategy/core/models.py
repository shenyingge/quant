from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class FeatureSnapshot:
    """平台无关的特征快照。"""

    day_open: float
    current_close: float
    high_so_far: float
    low_so_far: float
    latest_bar_time: str
    vwap: float
    close_vs_vwap: float
    distance_from_high: float
    bounce_from_low: float
    fake_breakout_score: float
    absorption_score: float

    def to_dict(self) -> Dict:
        return {
            "day_open": self.day_open,
            "current_close": self.current_close,
            "high_so_far": self.high_so_far,
            "low_so_far": self.low_so_far,
            "latest_bar_time": self.latest_bar_time,
            "vwap": self.vwap,
            "close_vs_vwap": self.close_vs_vwap,
            "distance_from_high": self.distance_from_high,
            "bounce_from_low": self.bounce_from_low,
            "fake_breakout_score": self.fake_breakout_score,
            "absorption_score": self.absorption_score,
        }


@dataclass(frozen=True)
class PortfolioState:
    """平台无关的仓位状态。"""

    total_position: int
    available_volume: int
    cost_price: float
    base_position: int
    tactical_position: int
    max_position: int
    t0_sell_available: int
    t0_buy_capacity: int
    cash_available: float = 0.0
    position_version: int = 0

    def to_dict(self) -> Dict:
        return {
            "total_position": self.total_position,
            "available_volume": self.available_volume,
            "cost_price": self.cost_price,
            "base_position": self.base_position,
            "tactical_position": self.tactical_position,
            "max_position": self.max_position,
            "t0_sell_available": self.t0_sell_available,
            "t0_buy_capacity": self.t0_buy_capacity,
            "cash_available": self.cash_available,
            "position_version": self.position_version,
        }


@dataclass(frozen=True)
class StrategyDecision:
    """策略动作输出。"""

    action: str
    reason: str
    price: float
    volume: int
    branch: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    def __getitem__(self, key: str):
        return self.to_dict()[key]

    def get(self, key: str, default=None):
        return self.to_dict().get(key, default)


@dataclass(frozen=True)
class MarketSnapshot:
    """实时输出中的市场快照。"""

    time: str
    price: float
    vwap: float
    high: float
    low: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class PositionSnapshot:
    """实时输出中的仓位快照。"""

    total: int
    available: int
    cost_price: float
    base: int
    tactical: int
    max: int
    t0_sell_available: int
    t0_buy_capacity: int
    position_version: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass(frozen=True)
class SignalCard:
    """实时输出卡片。"""

    trade_date: str
    as_of_time: str
    regime: str
    position: PositionSnapshot
    market: MarketSnapshot
    signal: StrategyDecision
    scores: Dict[str, float]

    def to_dict(self) -> Dict:
        payload = asdict(self)
        payload["position"] = self.position.to_dict()
        payload["market"] = self.market.to_dict()
        payload["signal"] = self.signal.to_dict()
        return payload

    def __getitem__(self, key: str):
        return self.to_dict()[key]

    def get(self, key: str, default=None):
        return self.to_dict().get(key, default)


@dataclass(frozen=True)
class SignalEvent:
    """策略事件的标准化表示。"""

    action: str
    branch: Optional[str] = None
    price: Optional[float] = None
    volume: int = 0
    signal_time: Optional[datetime] = None


@dataclass(frozen=True)
class BranchState:
    """单日单分支状态。"""

    branch: Optional[str]
    completed: bool
    volume: int
    entry_price: Optional[float]
    entry_time: Optional[datetime]


@dataclass(frozen=True)
class StrategyState:
    """回测/重放用的单日策略状态。"""

    trade_date: str
    signal_history: tuple
