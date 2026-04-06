"""信号生成模块 - 仅负责组装输入并调用纯策略核心。"""

from datetime import date, datetime
from typing import Dict, Iterable, Optional

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.models import FeatureSnapshot, PortfolioState, SignalEvent, StrategyDecision
from src.strategy.core.params import T0StrategyParams


class SignalGenerator:
    """信号生成器"""

    def __init__(self, strategy_name: str = "t0_601138"):
        self.strategy_name = strategy_name
        self.params = T0StrategyParams.from_settings(settings)
        self.engine = T0StrategyEngine(self.params)

    def generate_signal(
        self,
        regime: str,
        features: Dict,
        position: Dict,
        trade_date: date,
        signal_history: Optional[Iterable] = None,
        current_time=None,
        current_datetime=None,
    ) -> StrategyDecision:
        """生成交易信号

        Args:
            regime: 市场状态
            features: 日内特征
            position: 仓位状态
            trade_date: 交易日期

        Returns:
            信号字典
        """
        try:
            evaluation_datetime = current_datetime or datetime.now()
            evaluation_time = current_time or evaluation_datetime.time()
            normalized_position = self._normalize_position(position)
            history_events = self._normalize_signal_history(signal_history)

            # 记录策略输入
            logger.debug(
                f"信号生成输入: regime={regime}, "
                f"time={evaluation_time.strftime('%H:%M:%S')}, "
                f"history_count={len(history_events)}"
            )

            signal = self.engine.generate_signal(
                regime=regime,
                features=self._normalize_features(features),
                position=normalized_position.to_dict(),
                current_time=evaluation_time,
                current_datetime=evaluation_datetime,
                signal_history=history_events,
            )

            # 记录策略输出
            logger.debug(
                f"信号生成输出: action={signal['action']}, "
                f"reason={signal['reason']}, "
                f"branch={signal.get('branch')}"
            )

            return self._normalize_decision(signal)

        except Exception as e:
            logger.error(f"信号生成异常: {e}")
            return StrategyDecision(
                action="observe",
                reason=f"系统异常: {str(e)}",
                price=0,
                volume=0,
                branch=None,
            )

    def _normalize_position(self, position: Dict) -> PortfolioState:
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

    def _normalize_features(self, features) -> Dict:
        if isinstance(features, FeatureSnapshot):
            return features.to_dict()
        return dict(features)

    def _normalize_signal_history(self, signal_history: Optional[Iterable]) -> list:
        if not signal_history:
            return []

        events = []
        for item in signal_history:
            if isinstance(item, SignalEvent):
                events.append(item)
                continue

            events.append(
                SignalEvent(
                    action=getattr(item, "action", None) or getattr(item, "signal_action", None),
                    branch=getattr(item, "branch", None) or getattr(item, "branch_locked", None),
                    price=getattr(item, "price", None),
                    volume=(
                        getattr(item, "volume", None)
                        or getattr(item, "suggested_volume", None)
                        or 0
                    ),
                    signal_time=getattr(item, "signal_time", None),
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
