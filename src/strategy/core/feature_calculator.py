"""日内特征计算模块"""

from dataclasses import dataclass
import logging
from typing import Dict, Optional

import pandas as pd

from src.strategy.core.models import FeatureSnapshot

logger = logging.getLogger(__name__)


@dataclass
class IncrementalFeatureState:
    day_open: Optional[float] = None
    prev_close: Optional[float] = None
    high_so_far: float = 0.0
    low_so_far: float = 0.0
    cum_tpv: float = 0.0
    cum_volume: float = 0.0
    cum_close: float = 0.0
    valid_count: int = 0
    last_valid_close: Optional[float] = None
    last_valid_time: Optional[str] = None


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

            # 过滤掉零值数据（集合竞价期间的无效数据）
            valid_data = minute_data[
                (minute_data["open"] > 0) &
                (minute_data["high"] > 0) &
                (minute_data["low"] > 0) &
                (minute_data["close"] > 0)
            ].copy()

            if valid_data.empty:
                logger.warning("过滤零值后无有效数据")
                return None

            # 基础特征
            day_open = valid_data.iloc[0]["open"]
            current_close = valid_data.iloc[-1]["close"]
            high_so_far = valid_data["high"].max()
            low_so_far = valid_data["low"].min()
            latest_bar_time = valid_data.index[-1]
            prev_close = valid_data.iloc[0].get("pre_close", day_open)
            if pd.isna(prev_close) or prev_close <= 0:
                prev_close = day_open

            # VWAP计算
            vwap = self._calculate_vwap(valid_data)
            open_gap_pct = ((day_open - prev_close) / prev_close * 100) if prev_close > 0 else 0

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
                valid_data, day_open, high_so_far, current_close, vwap
            )
            absorption_score = self._calculate_absorption_score(
                valid_data, low_so_far, current_close, vwap
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
                "prev_close": prev_close,
                "open_gap_pct": open_gap_pct,
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

    def initialize_intraday_state(self) -> IncrementalFeatureState:
        return IncrementalFeatureState()

    def update_snapshot_from_bar(
        self,
        state: IncrementalFeatureState,
        *,
        bar: Dict,
        latest_bar_time,
    ) -> Optional[FeatureSnapshot]:
        current_open = float(bar.get("open", 0.0) or 0.0)
        current_high = float(bar.get("high", 0.0) or 0.0)
        current_low = float(bar.get("low", 0.0) or 0.0)
        current_close = float(bar.get("close", 0.0) or 0.0)
        current_volume = float(bar.get("volume", 0.0) or 0.0)
        current_pre_close = float(bar.get("pre_close", current_open) or current_open)

        if self._is_valid_bar(
            open_price=current_open,
            high_price=current_high,
            low_price=current_low,
            close_price=current_close,
        ):
            if state.day_open is None:
                state.day_open = current_open
                state.prev_close = (
                    current_pre_close if pd.notna(current_pre_close) and current_pre_close > 0 else current_open
                )
                state.high_so_far = current_high
                state.low_so_far = current_low
            else:
                state.high_so_far = max(state.high_so_far, current_high)
                state.low_so_far = min(state.low_so_far, current_low)

            typical_price = (current_high + current_low + current_close) / 3
            state.cum_tpv += typical_price * current_volume
            state.cum_volume += current_volume
            state.cum_close += current_close
            state.valid_count += 1
            state.last_valid_close = current_close
            state.last_valid_time = self._format_bar_time(latest_bar_time)

        return self._build_snapshot_from_state(state)

    def calculate_day_snapshots(self, minute_data: pd.DataFrame) -> list[Optional[FeatureSnapshot]]:
        """按单个交易日顺序返回每根 bar 对应的特征快照。

        该实现与逐次调用 ``calculate_snapshot(minute_data.iloc[:i+1])`` 保持语义一致，
        但只做一次线性扫描，避免回测中的重复前缀重算。
        """
        if minute_data is None or minute_data.empty:
            return []

        working = minute_data.copy()
        valid_mask = (
            (working["open"] > 0)
            & (working["high"] > 0)
            & (working["low"] > 0)
            & (working["close"] > 0)
        ).to_numpy()

        index_strings = working.index.strftime("%Y-%m-%d %H:%M:%S")
        open_arr = working["open"].to_numpy(dtype=float)
        high_arr = working["high"].to_numpy(dtype=float)
        low_arr = working["low"].to_numpy(dtype=float)
        close_arr = working["close"].to_numpy(dtype=float)
        volume_arr = working["volume"].to_numpy(dtype=float)
        pre_close_arr = working.get("pre_close", working["open"]).to_numpy(dtype=float)

        snapshots: list[Optional[FeatureSnapshot]] = []
        day_open: Optional[float] = None
        prev_close: Optional[float] = None
        high_so_far = 0.0
        low_so_far = 0.0
        cum_tpv = 0.0
        cum_volume = 0.0
        cum_close = 0.0
        valid_count = 0
        last_valid_pos = -1

        for idx in range(len(working)):
            if valid_mask[idx]:
                current_open = open_arr[idx]
                current_high = high_arr[idx]
                current_low = low_arr[idx]
                current_close = close_arr[idx]
                current_volume = volume_arr[idx]
                current_pre_close = pre_close_arr[idx]

                if day_open is None:
                    day_open = current_open
                    prev_close = current_pre_close if pd.notna(current_pre_close) and current_pre_close > 0 else day_open
                    high_so_far = current_high
                    low_so_far = current_low
                else:
                    high_so_far = max(high_so_far, current_high)
                    low_so_far = min(low_so_far, current_low)

                typical_price = (current_high + current_low + current_close) / 3
                cum_tpv += typical_price * current_volume
                cum_volume += current_volume
                cum_close += current_close
                valid_count += 1
                last_valid_pos = idx

            if day_open is None or prev_close is None or last_valid_pos < 0:
                snapshots.append(None)
                continue

            current_close = close_arr[last_valid_pos]
            if cum_volume > 0:
                vwap = cum_tpv / cum_volume
            else:
                vwap = cum_close / valid_count if valid_count > 0 else current_close
            snapshots.append(
                self._build_snapshot_from_aggregate(
                    day_open=float(day_open),
                    prev_close=float(prev_close),
                    high_so_far=float(high_so_far),
                    low_so_far=float(low_so_far),
                    current_close=float(current_close),
                    vwap=float(vwap),
                    latest_bar_time=index_strings[last_valid_pos],
                )
            )

        return snapshots

    def _build_snapshot_from_state(
        self, state: IncrementalFeatureState
    ) -> Optional[FeatureSnapshot]:
        if (
            state.day_open is None
            or state.prev_close is None
            or state.last_valid_close is None
            or state.last_valid_time is None
            or state.valid_count <= 0
        ):
            return None

        if state.cum_volume > 0:
            vwap = state.cum_tpv / state.cum_volume
        else:
            vwap = state.cum_close / state.valid_count

        return self._build_snapshot_from_aggregate(
            day_open=float(state.day_open),
            prev_close=float(state.prev_close),
            high_so_far=float(state.high_so_far),
            low_so_far=float(state.low_so_far),
            current_close=float(state.last_valid_close),
            vwap=float(vwap),
            latest_bar_time=state.last_valid_time,
        )

    def _build_snapshot_from_aggregate(
        self,
        *,
        day_open: float,
        prev_close: float,
        high_so_far: float,
        low_so_far: float,
        current_close: float,
        vwap: float,
        latest_bar_time: str,
    ) -> FeatureSnapshot:
        open_gap_pct = ((day_open - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        close_vs_vwap = ((current_close - vwap) / vwap * 100) if vwap > 0 else 0.0
        distance_from_high = (
            ((current_close - high_so_far) / high_so_far * 100) if high_so_far > 0 else 0.0
        )
        bounce_from_low = (
            ((current_close - low_so_far) / low_so_far * 100) if low_so_far > 0 else 0.0
        )

        rise_from_open = ((high_so_far - day_open) / day_open * 100) if day_open > 0 else 0.0
        pullback_from_high = ((high_so_far - current_close) / high_so_far * 100) if high_so_far > 0 else 0.0
        fake_breakout_score = 0.0
        if rise_from_open >= 1.0:
            fake_breakout_score += 0.3
        if pullback_from_high >= 0.5:
            fake_breakout_score += 0.3
        if current_close < vwap:
            fake_breakout_score += 0.4

        drop_from_prev = ((low_so_far - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        bounce = ((current_close - low_so_far) / low_so_far * 100) if low_so_far > 0 else 0.0
        absorption_score = 0.0
        if drop_from_prev <= -1.5:
            absorption_score += 0.4
        if bounce >= 0.4:
            absorption_score += 0.3
        if current_close >= vwap * 0.995:
            absorption_score += 0.3

        return FeatureSnapshot(
            day_open=float(day_open),
            current_close=float(current_close),
            high_so_far=float(high_so_far),
            low_so_far=float(low_so_far),
            latest_bar_time=latest_bar_time,
            vwap=float(vwap),
            close_vs_vwap=float(close_vs_vwap),
            distance_from_high=float(distance_from_high),
            bounce_from_low=float(bounce_from_low),
            fake_breakout_score=float(min(fake_breakout_score, 1.0)),
            absorption_score=float(min(absorption_score, 1.0)),
            prev_close=float(prev_close),
            open_gap_pct=float(open_gap_pct),
        )

    def _format_bar_time(self, value) -> str:
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")

    def _is_valid_bar(
        self,
        *,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> bool:
        return (
            pd.notna(open_price)
            and pd.notna(high_price)
            and pd.notna(low_price)
            and pd.notna(close_price)
            and open_price > 0
            and high_price > 0
            and low_price > 0
            and close_price > 0
        )

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
