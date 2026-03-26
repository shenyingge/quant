"""日内特征计算模块"""

import logging
from typing import Dict, Optional

import pandas as pd

from src.strategy.core.models import FeatureSnapshot

logger = logging.getLogger(__name__)


class FeatureCalculator:
    """日内特征计算器"""

    def calculate_features(self, minute_data: pd.DataFrame) -> Optional[Dict]:
        """计算日内特征

        Args:
            minute_data: 分钟数据DataFrame

        Returns:
            特征字典或None
        """
        try:
            if minute_data is None or minute_data.empty:
                return None

            # 基础特征
            day_open = minute_data.iloc[0]["open"]
            current_close = minute_data.iloc[-1]["close"]
            high_so_far = minute_data["high"].max()
            low_so_far = minute_data["low"].min()
            latest_bar_time = minute_data.index[-1]

            # VWAP计算
            vwap = self._calculate_vwap(minute_data)

            # 相对特征
            close_vs_vwap = ((current_close - vwap) / vwap * 100) if vwap > 0 else 0
            distance_from_high = (
                ((current_close - high_so_far) / high_so_far * 100) if high_so_far > 0 else 0
            )
            bounce_from_low = (
                ((current_close - low_so_far) / low_so_far * 100) if low_so_far > 0 else 0
            )

            # 代理评分
            fake_breakout_score = self._calculate_fake_breakout_score(
                minute_data, day_open, high_so_far, current_close, vwap
            )
            absorption_score = self._calculate_absorption_score(
                minute_data, low_so_far, current_close, vwap
            )

            features = {
                "day_open": day_open,
                "current_close": current_close,
                "high_so_far": high_so_far,
                "low_so_far": low_so_far,
                "latest_bar_time": latest_bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                "vwap": vwap,
                "close_vs_vwap": close_vs_vwap,
                "distance_from_high": distance_from_high,
                "bounce_from_low": bounce_from_low,
                "fake_breakout_score": fake_breakout_score,
                "absorption_score": absorption_score,
            }

            return features

        except Exception as e:
            logger.error(f"特征计算失败: {e}")
            return None

    def calculate_snapshot(self, minute_data: pd.DataFrame) -> Optional[FeatureSnapshot]:
        """返回标准化特征快照对象。"""
        features = self.calculate_features(minute_data)
        if features is None:
            return None
        return FeatureSnapshot(**features)

    def _calculate_vwap(self, df: pd.DataFrame) -> float:
        """计算VWAP"""
        try:
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            vwap = (typical_price * df["volume"]).sum() / df["volume"].sum()
            return float(vwap)
        except Exception:
            return float(df["close"].mean())

    def _calculate_fake_breakout_score(
        self, df: pd.DataFrame, day_open: float, high: float, close: float, vwap: float
    ) -> float:
        """计算假突破评分

        逻辑：
        - 先有足够冲高（相对开盘）
        - 再从高点回撤
        - 价格跌回VWAP下方
        """
        try:
            # 冲高幅度
            rise_from_open = ((high - day_open) / day_open * 100) if day_open > 0 else 0

            # 回撤幅度
            pullback_from_high = ((high - close) / high * 100) if high > 0 else 0

            # 相对VWAP位置
            below_vwap = 1.0 if close < vwap else 0.0

            # 综合评分
            score = 0.0
            if rise_from_open >= 1.0:  # 至少涨1%
                score += 0.3
            if pullback_from_high >= 0.5:  # 至少回撤0.5%
                score += 0.3
            if below_vwap:  # 跌破VWAP
                score += 0.4

            return min(score, 1.0)

        except Exception:
            return 0.0

    def _calculate_absorption_score(
        self, df: pd.DataFrame, low: float, close: float, vwap: float
    ) -> float:
        """计算承接评分

        逻辑：
        - 先有明显下探
        - 再从低点反弹
        - 价格回到VWAP附近或上方
        """
        try:
            # 获取昨收（假设第一根K线的pre_close）
            prev_close = df.iloc[0].get("pre_close", df.iloc[0]["open"])

            # 下探幅度
            drop_from_prev = ((low - prev_close) / prev_close * 100) if prev_close > 0 else 0

            # 反弹幅度
            bounce = ((close - low) / low * 100) if low > 0 else 0

            # 相对VWAP位置
            near_vwap = 1.0 if close >= vwap * 0.995 else 0.0

            # 综合评分
            score = 0.0
            if drop_from_prev <= -1.5:  # 至少跌1.5%
                score += 0.4
            if bounce >= 0.4:  # 至少反弹0.4%
                score += 0.3
            if near_vwap:  # 回到VWAP附近
                score += 0.3

            return min(score, 1.0)

        except Exception:
            return 0.0
