"""Market regime identification shared by T0 runtime tools."""

from datetime import date
from typing import Optional

import pandas as pd

from src.infrastructure.db import SessionLocal, StrategyRegimeState
from src.infrastructure.logger_config import logger
from src.strategy.core.regime_classifier import RegimeClassifier


class RegimeIdentifier:
    """Regime classifier with persistence-backed caching."""

    def __init__(self, strategy_name: str = "t0_601138"):
        self.strategy_name = strategy_name
        self.classifier = RegimeClassifier()

    def identify_regime(self, daily_data: pd.DataFrame, trade_date: date) -> str:
        cached = self._load_cached_regime(trade_date)
        if cached:
            logger.debug(f"使用缓存regime: {cached}")
            return cached

        regime = self._calculate_regime(daily_data)
        self._save_regime(trade_date, regime, daily_data)
        return regime

    def _calculate_regime(self, df: pd.DataFrame) -> str:
        try:
            return self.classifier.calculate(df)
        except Exception as e:
            logger.error(f"Regime计算失败: {e}")
            return "transition"

    def _calculate_slope(self, series: pd.Series, window: int) -> float:
        try:
            recent = series.tail(window).values
            if len(recent) < 2:
                return 0.0
            return float((recent[-1] - recent[0]) / recent[0] * 100)
        except Exception:
            return 0.0

    def _load_cached_regime(self, trade_date: date) -> Optional[str]:
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
