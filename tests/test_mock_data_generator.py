"""模拟数据生成器 - 用于测试T+0策略"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd


class MockDataGenerator:
    """模拟数据生成器"""

    def generate_daily_data(self, days: int = 100, base_price: float = 12.0) -> pd.DataFrame:
        """生成模拟日线数据

        Args:
            days: 天数
            base_price: 基准价格

        Returns:
            日线数据DataFrame
        """
        dates = pd.date_range(end=datetime.now(), periods=days, freq="D")

        # 生成价格序列（带趋势和波动）
        trend = np.linspace(0, 0.2, days)  # 上升趋势
        noise = np.random.randn(days) * 0.02  # 随机波动
        close_prices = base_price * (1 + trend + noise)

        data = {
            "open": close_prices * (1 + np.random.randn(days) * 0.005),
            "high": close_prices * (1 + np.abs(np.random.randn(days)) * 0.01),
            "low": close_prices * (1 - np.abs(np.random.randn(days)) * 0.01),
            "close": close_prices,
            "volume": np.random.randint(1000000, 5000000, days),
            "amount": close_prices * np.random.randint(1000000, 5000000, days),
        }

        df = pd.DataFrame(data, index=dates)
        return df

    def generate_minute_data(
        self, scenario: str = "normal", base_price: float = 12.0
    ) -> pd.DataFrame:
        """生成模拟分钟数据

        Args:
            scenario: 场景类型
                - 'normal': 正常波动
                - 'fake_breakout': 假突破（冲高回落）
                - 'absorption': 急跌反弹
            base_price: 基准价格

        Returns:
            分钟数据DataFrame
        """
        # 生成交易时间（09:30-15:00）
        times = []
        current_date = datetime.now().date()

        # 上午时段 09:30-11:30
        for hour in range(9, 12):
            start_min = 30 if hour == 9 else 0
            end_min = 30 if hour == 11 else 60
            for minute in range(start_min, end_min):
                times.append(
                    datetime.combine(
                        current_date, datetime.min.time().replace(hour=hour, minute=minute)
                    )
                )

        # 下午时段 13:00-15:00
        for hour in range(13, 15):
            for minute in range(0, 60):
                times.append(
                    datetime.combine(
                        current_date, datetime.min.time().replace(hour=hour, minute=minute)
                    )
                )

        n = len(times)

        if scenario == "fake_breakout":
            # 假突破场景：早盘冲高后回落
            prices = self._generate_fake_breakout_prices(n, base_price)
        elif scenario == "absorption":
            # 承接场景：急跌后反弹
            prices = self._generate_absorption_prices(n, base_price)
        else:
            # 正常波动
            prices = self._generate_normal_prices(n, base_price)

        data = {
            "open": prices + np.random.randn(n) * 0.01,
            "high": prices + np.abs(np.random.randn(n)) * 0.02,
            "low": prices - np.abs(np.random.randn(n)) * 0.02,
            "close": prices,
            "volume": np.random.randint(10000, 50000, n),
            "amount": prices * np.random.randint(10000, 50000, n),
            "pre_close": base_price,
        }

        df = pd.DataFrame(data, index=times)
        return df

    def _generate_fake_breakout_prices(self, n: int, base: float) -> np.ndarray:
        """生成假突破价格序列"""
        prices = np.zeros(n)

        # 开盘
        prices[0] = base

        # 早盘冲高（前60分钟涨1.5%）
        for i in range(1, 60):
            prices[i] = base * (1 + 0.015 * i / 60)

        # 回落（60-120分钟跌回0.5%）
        for i in range(60, 120):
            prices[i] = base * (1 + 0.015 - 0.01 * (i - 60) / 60)

        # 下午震荡
        for i in range(120, n):
            prices[i] = base * 1.005 + np.random.randn() * 0.005

        return prices

    def _generate_absorption_prices(self, n: int, base: float) -> np.ndarray:
        """生成承接价格序列"""
        prices = np.zeros(n)

        # 开盘
        prices[0] = base

        # 早盘下跌（前30分钟跌2%）
        for i in range(1, 30):
            prices[i] = base * (1 - 0.02 * i / 30)

        # 反弹（30-90分钟反弹1%）
        for i in range(30, 90):
            prices[i] = base * (0.98 + 0.01 * (i - 30) / 60)

        # 下午稳定
        for i in range(90, n):
            prices[i] = base * 0.99 + np.random.randn() * 0.003

        return prices

    def _generate_normal_prices(self, n: int, base: float) -> np.ndarray:
        """生成正常波动价格序列"""
        prices = np.zeros(n)
        prices[0] = base

        for i in range(1, n):
            prices[i] = prices[i - 1] * (1 + np.random.randn() * 0.002)

        return prices
