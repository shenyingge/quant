"""纯市场状态识别逻辑。"""

import pandas as pd


class RegimeClassifier:
    """不依赖缓存和持久化的市场状态分类器。"""

    def calculate(self, df: pd.DataFrame) -> str:
        if len(df) < 60:
            return "transition"

        close_series = df["close"]
        ma20_series = close_series.rolling(20).mean()
        ma60_series = close_series.rolling(60).mean()

        ma20 = ma20_series.iloc[-1]
        ma60 = ma60_series.iloc[-1]
        close = close_series.iloc[-1]
        trend_spread = ((ma20 / ma60) - 1) * 100 if ma60 > 0 else 0
        ma20_slope = self._calculate_slope(ma20_series, 5)
        ma60_slope = self._calculate_slope(ma60_series, 10)

        if (
            ma20 > ma60
            and trend_spread >= 1.5
            and close > ma20
            and ma20_slope > 0
            and ma60_slope >= 0
        ):
            return "uptrend"

        if (
            ma20 < ma60
            and trend_spread <= -1.5
            and close < ma20
            and ma20_slope < 0
            and ma60_slope <= 0
        ):
            return "downtrend"

        return "transition"

    def _calculate_slope(self, series: pd.Series, window: int) -> float:
        recent = series.tail(window).values
        if len(recent) < 2:
            return 0.0
        base = recent[0]
        if not base:
            return 0.0
        return float((recent[-1] - base) / base * 100)
