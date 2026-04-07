"""无基础设施依赖的 T+0 策略内核入口。"""

from __future__ import annotations

from datetime import datetime, time
from typing import Iterable, Optional

import pandas as pd

from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.models import FeatureSnapshot, PortfolioState, SignalEvent, StrategyDecision
from src.strategy.core.params import T0StrategyParams
from src.strategy.core.regime_classifier import RegimeClassifier
from src.strategy.strategies.t0.feature_calculator import FeatureCalculator


class T0StrategyKernel:
    """最小可嵌入的 T+0 策略入口。

    调用方负责数据抓取、仓位同步、通知和持久化，内核只做策略判断。
    """

    def __init__(self, params: Optional[T0StrategyParams] = None):
        self.params = params or T0StrategyParams()
        self.feature_calculator = FeatureCalculator()
        self.regime_classifier = RegimeClassifier()
        self.engine = T0StrategyEngine(self.params)

    def evaluate(
        self,
        *,
        minute_data: pd.DataFrame,
        daily_data: pd.DataFrame,
        position: PortfolioState | dict,
        current_datetime: Optional[datetime] = None,
        signal_history: Optional[Iterable[SignalEvent | dict]] = None,
    ) -> dict:
        """用原始输入直接产出策略判断结果。"""
        if minute_data is None or minute_data.empty:
            return self._observe("分钟数据为空")
        if daily_data is None or daily_data.empty:
            return self._observe("日线数据为空")

        normalized_minute = self._normalize_time_index(minute_data, name="minute_data")
        normalized_daily = self._normalize_time_index(daily_data, name="daily_data")
        evaluation_datetime = current_datetime or normalized_minute.index[-1].to_pydatetime()

        features = self.feature_calculator.calculate_snapshot(normalized_minute)
        if features is None:
            return self._observe("特征计算失败")

        regime = self.regime_classifier.calculate(normalized_daily)
        normalized_position = self._normalize_position(position)
        decision = self.decide(
            regime=regime,
            features=features,
            position=normalized_position,
            current_datetime=evaluation_datetime,
            signal_history=signal_history,
        )
        return {
            "regime": regime,
            "features": features,
            "signal": decision,
            "position": normalized_position,
        }

    def decide(
        self,
        *,
        regime: str,
        features: FeatureSnapshot | dict,
        position: PortfolioState | dict,
        current_datetime: Optional[datetime] = None,
        current_time: Optional[time] = None,
        signal_history: Optional[Iterable[SignalEvent | dict]] = None,
    ) -> StrategyDecision:
        """基于已准备好的策略上下文直接产出标准化决策。"""
        evaluation_datetime = current_datetime or datetime.now()
        evaluation_time = current_time or evaluation_datetime.time()
        normalized_position = self._normalize_position(position)
        normalized_history = self._normalize_signal_history(signal_history)

        decision = self.engine.generate_signal(
            regime=regime,
            features=self._normalize_features(features),
            position=normalized_position.to_dict(),
            current_time=evaluation_time,
            current_datetime=evaluation_datetime,
            signal_history=normalized_history,
        )
        return self._normalize_decision(decision)

    def _normalize_time_index(self, frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
        if isinstance(frame.index, pd.DatetimeIndex):
            if frame.index.is_monotonic_increasing:
                return frame
            return frame.sort_index()
        working = frame.copy()
        if "datetime" not in working.columns:
            raise ValueError(f"{name} must have a DatetimeIndex or datetime column")
        working["datetime"] = pd.to_datetime(working["datetime"])
        working = working.set_index("datetime")
        return working.sort_index()

    def _normalize_position(self, position: PortfolioState | dict) -> PortfolioState:
        if isinstance(position, PortfolioState):
            return position

        normalized = dict(position)
        total_position = int(normalized.get("total_position") or 0)
        available_volume = int(normalized.get("available_volume") or 0)
        base_position = int(normalized.get("base_position") or self.params.t0_base_position)
        tactical_position = int(
            normalized.get("tactical_position") or self.params.t0_tactical_position
        )
        max_position = int(normalized.get("max_position") or (base_position + tactical_position))
        trade_unit = max(int(self.params.t0_trade_unit), 1)

        def round_down_lot(volume: int) -> int:
            return max(int(volume) // trade_unit * trade_unit, 0)

        return PortfolioState(
            total_position=total_position,
            available_volume=available_volume,
            cost_price=float(normalized.get("cost_price", 0) or 0),
            base_position=base_position,
            tactical_position=tactical_position,
            max_position=max_position,
            t0_sell_available=int(
                normalized.get(
                    "t0_sell_available",
                    round_down_lot(min(available_volume, max(total_position - base_position, 0))),
                )
            ),
            t0_buy_capacity=int(
                normalized.get(
                    "t0_buy_capacity",
                    round_down_lot(max(max_position - total_position, 0)),
                )
            ),
            cash_available=float(normalized.get("cash_available", 0) or 0),
        )

    def _normalize_features(self, features: FeatureSnapshot | dict) -> dict:
        if isinstance(features, FeatureSnapshot):
            return features.to_dict()
        return dict(features)

    def _normalize_signal_history(
        self, signal_history: Optional[Iterable[SignalEvent | dict]]
    ) -> list[SignalEvent]:
        if not signal_history:
            return []

        events: list[SignalEvent] = []
        for item in signal_history:
            if isinstance(item, SignalEvent):
                events.append(item)
                continue

            payload = dict(item)
            signal_time = payload.get("signal_time")
            events.append(
                SignalEvent(
                    action=payload.get("action") or payload.get("signal_action"),
                    branch=payload.get("branch") or payload.get("branch_locked"),
                    price=payload.get("price"),
                    volume=int(payload.get("volume") or payload.get("suggested_volume") or 0),
                    signal_time=(
                        pd.Timestamp(signal_time).to_pydatetime() if signal_time is not None else None
                    ),
                    carry_trading_days=int(payload.get("carry_trading_days") or 0),
                )
            )
        return [event for event in events if event.action]

    def _normalize_decision(self, signal) -> StrategyDecision:
        if isinstance(signal, StrategyDecision):
            return signal
        return StrategyDecision(
            action=signal["action"],
            reason=signal["reason"],
            price=signal["price"],
            volume=signal["volume"],
            branch=signal.get("branch"),
        )

    def _observe(self, reason: str) -> dict:
        return {
            "regime": "transition",
            "features": None,
            "signal": StrategyDecision(action="observe", reason=reason, price=0, volume=0),
            "position": None,
        }
