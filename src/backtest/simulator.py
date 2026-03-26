"""分钟级 T+0 策略重放器。"""

from dataclasses import replace
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.models import FeatureSnapshot, PortfolioState, SignalEvent
from src.strategy.core.params import T0StrategyParams
from src.strategy.core.regime_classifier import RegimeClassifier
from src.strategy.feature_calculator import FeatureCalculator


class T0BacktestSimulator:
    """使用纯策略核心逐 bar 重放分钟数据。"""

    def __init__(self, params: Optional[T0StrategyParams] = None):
        self.params = params or T0StrategyParams()
        self.feature_calculator = FeatureCalculator()
        self.regime_classifier = RegimeClassifier()
        self.engine = T0StrategyEngine(self.params)

    def run(
        self,
        minute_data: pd.DataFrame,
        daily_data: pd.DataFrame,
        initial_position: PortfolioState,
        symbol: str = "601138.SH",
    ) -> Dict:
        if minute_data is None or minute_data.empty:
            return {
                "signals": pd.DataFrame(),
                "fills": pd.DataFrame(),
                "final_position": initial_position,
            }

        regime = self.regime_classifier.calculate(daily_data)
        position = initial_position
        signal_history: List[SignalEvent] = []
        signals: List[Dict] = []
        fills: List[Dict] = []

        for idx in range(len(minute_data)):
            window = minute_data.iloc[: idx + 1]
            features = self.feature_calculator.calculate_snapshot(window)
            current_time = window.index[-1].time()
            current_datetime = self._as_datetime(window.index[-1])
            signal = self.engine.generate_signal(
                regime=regime,
                features=features.to_dict(),
                position=position.to_dict(),
                current_time=current_time,
                current_datetime=current_datetime,
                signal_history=signal_history,
            )

            signals.append(
                {
                    "timestamp": window.index[-1],
                    "symbol": symbol,
                    "regime": regime,
                    "action": signal["action"],
                    "reason": signal["reason"],
                    "price": signal["price"],
                    "volume": signal["volume"],
                }
            )

            if signal["action"] != "observe":
                fill_price = float(signal["price"] or window.iloc[-1]["close"])
                fill_volume = int(signal["volume"])
                fills.append(
                    {
                        "timestamp": window.index[-1],
                        "symbol": symbol,
                        "action": signal["action"],
                        "price": fill_price,
                        "volume": fill_volume,
                    }
                )
                signal_history.append(
                    SignalEvent(
                        action=signal["action"],
                        branch=signal.get("branch"),
                        price=fill_price,
                        volume=fill_volume,
                        signal_time=current_datetime,
                    )
                )
                position = self._apply_fill(position, signal["action"], fill_price, fill_volume)

        return {
            "signals": pd.DataFrame(signals),
            "fills": pd.DataFrame(fills),
            "final_position": position,
        }

    def _apply_fill(
        self, position: PortfolioState, action: str, price: float, volume: int
    ) -> PortfolioState:
        total_position = position.total_position
        available_volume = position.available_volume
        cash_available = position.cash_available

        if action == "positive_t_sell":
            total_position -= volume
            available_volume = max(available_volume - volume, 0)
            cash_available += price * volume
        elif action == "positive_t_buyback":
            total_position += volume
            cash_available -= price * volume
        elif action == "reverse_t_buy":
            total_position += volume
            cash_available -= price * volume
        elif action == "reverse_t_sell":
            total_position -= volume
            available_volume = max(available_volume - volume, 0)
            cash_available += price * volume

        max_position = position.base_position + position.tactical_position
        trade_unit = max(self.params.t0_trade_unit, 1)

        def round_down_lot(raw_volume: int) -> int:
            return max(int(raw_volume) // trade_unit * trade_unit, 0)

        normalized_sell = round_down_lot(
            min(available_volume, max(total_position - position.base_position, 0))
        )
        normalized_buy = round_down_lot(max(max_position - total_position, 0))

        return PortfolioState(
            total_position=total_position,
            available_volume=available_volume,
            cost_price=position.cost_price,
            base_position=position.base_position,
            tactical_position=position.tactical_position,
            max_position=max_position,
            t0_sell_available=normalized_sell,
            t0_buy_capacity=normalized_buy,
            cash_available=cash_available,
        )

    def _as_datetime(self, timestamp) -> datetime:
        if isinstance(timestamp, datetime):
            return timestamp
        return pd.Timestamp(timestamp).to_pydatetime()
