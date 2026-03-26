"""市场状态识别模块 - 基于MA20/MA60识别趋势"""

from datetime import date
from typing import Optional

import pandas as pd

from src.database import SessionLocal, StrategyRegimeState
from src.logger_config import logger
from src.strategy.core.regime_classifier import RegimeClassifier


class RegimeIdentifier:
    """市场状态识别器"""

    def __init__(self, strategy_name: str = "t0_601138"):
        self.strategy_name = strategy_name
        self.classifier = RegimeClassifier()

    def identify_regime(self, daily_data: pd.DataFrame, trade_date: date) -> str:
        """识别市场状态

        Args:
            daily_data: 日线数据
            trade_date: 交易日期

        Returns:
            regime: uptrend/transition/downtrend
        """
        # 检查缓存
        cached = self._load_cached_regime(trade_date)
        if cached:
            logger.debug(f"使用缓存regime: {cached}")
            return cached

        # 计算regime
        regime = self._calculate_regime(daily_data)

        # 保存到数据库
        self._save_regime(trade_date, regime, daily_data)

        return regime

    def _calculate_regime(self, df: pd.DataFrame) -> str:
        """计算市场状态"""
        try:
            return self.classifier.calculate(df)

        except Exception as e:
            logger.error(f"Regime计算失败: {e}")
            return "transition"

    def _calculate_slope(self, series: pd.Series, window: int) -> float:
        """计算斜率"""
        try:
            recent = series.tail(window).values
            if len(recent) < 2:
                return 0.0
            return float((recent[-1] - recent[0]) / recent[0] * 100)
        except Exception:
            return 0.0

    def _load_cached_regime(self, trade_date: date) -> Optional[str]:
        """从数据库加载缓存的regime"""
        try:
            db = SessionLocal()
            record = (
                db.query(StrategyRegimeState)
                .filter(
                    StrategyRegimeState.strategy_name == self.strategy_name,
                    StrategyRegimeState.trade_date == trade_date,
                )
                .first()
            )
            db.close()
            return record.regime if record else None
        except Exception as e:
            logger.warning(f"加载缓存regime失败: {e}")
            return None

    def _save_regime(self, trade_date: date, regime: str, df: pd.DataFrame):
        """保存regime到数据库"""
        try:
            working = df.copy()
            working["ma20"] = working["close"].rolling(20).mean()
            working["ma60"] = working["close"].rolling(60).mean()
            latest = working.iloc[-1]
            ma20 = latest.get("ma20", 0)
            ma60 = latest.get("ma60", 0)
            trend_spread = ((ma20 / ma60) - 1) * 100 if ma60 > 0 else 0

            db = SessionLocal()
            record = StrategyRegimeState(
                strategy_name=self.strategy_name,
                trade_date=trade_date,
                regime=regime,
                ma20=float(ma20),
                ma60=float(ma60),
                trend_spread=float(trend_spread),
                confirmation_days=0,
            )
            db.add(record)
            db.commit()
            db.close()
            logger.info(f"保存regime: {regime}")
        except Exception as e:
            logger.error(f"保存regime失败: {e}")
