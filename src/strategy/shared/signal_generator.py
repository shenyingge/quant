"""信号生成模块 - 仅负责组装输入并调用纯策略核心。"""

from datetime import date, datetime, time
from typing import Dict, Iterable, Optional

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.strategy.core import T0StrategyKernel
from src.strategy.core.models import StrategyDecision
from src.strategy.core.params import T0StrategyParams


class SignalGenerator:
    """信号生成器"""

    def __init__(self, strategy_name: str = "t0_601138"):
        self.strategy_name = strategy_name
        self.params = T0StrategyParams.from_settings(settings)
        self.kernel = T0StrategyKernel(self.params)

    def generate_signal(
        self,
        regime: str,
        features: Dict,
        position: Dict,
        trade_date: date,
        signal_history: Optional[Iterable] = None,
        current_time: Optional[time] = None,
        current_datetime: Optional[datetime] = None,
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

            # 记录策略输入
            logger.debug(
                f"信号生成输入: regime={regime}, "
                f"time={evaluation_time.strftime('%H:%M:%S')}, "
                f"history_count={len(signal_history or [])}"
            )

            signal = self.kernel.decide(
                regime=regime,
                features=features,
                position=position,
                current_time=evaluation_time,
                current_datetime=evaluation_datetime,
                signal_history=signal_history,
            )

            # 记录策略输出
            logger.debug(
                f"信号生成输出: action={signal.action}, "
                f"reason={signal.reason}, "
                f"branch={signal.branch}"
            )

            return signal

        except Exception as e:
            logger.error(f"信号生成异常: {e}")
            return StrategyDecision(
                action="observe",
                reason=f"系统异常: {str(e)}",
                price=0,
                volume=0,
                branch=None,
            )
