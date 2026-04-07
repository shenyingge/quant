from datetime import datetime

import pandas as pd

from src.strategy.core import T0StrategyKernel


def test_t0_strategy_kernel_runs_without_runtime_adapters():
    kernel = T0StrategyKernel()

    daily_index = pd.date_range("2026-01-01", periods=70, freq="B")
    daily_close = pd.Series([100 - i * 0.4 for i in range(len(daily_index))], index=daily_index)
    daily_data = pd.DataFrame({"close": daily_close}, index=daily_index)

    minute_index = pd.to_datetime(["2026-03-26 09:45:00", "2026-03-26 09:46:00"])
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 50.5],
            "high": [50.6, 50.8],
            "low": [49.9, 50.2],
            "close": [50.5, 50.2],
            "volume": [1000, 1000],
            "pre_close": [50.0, 50.5],
        },
        index=minute_index,
    )

    result = kernel.evaluate(
        minute_data=minute_data,
        daily_data=daily_data,
        position={
            "total_position": 3500,
            "available_volume": 3500,
            "cost_price": 72.68,
            "base_position": 2600,
            "tactical_position": 900,
        },
        current_datetime=datetime(2026, 3, 26, 9, 46),
        signal_history=[],
    )

    assert result["regime"] == "downtrend"
    assert result["signal"].action == "positive_t_sell"
    assert result["signal"].volume == 900


def test_t0_strategy_kernel_can_decide_from_precomputed_context():
    kernel = T0StrategyKernel()

    signal = kernel.decide(
        regime="transition",
        features={
            "day_open": 50.0,
            "current_close": 50.8,
            "high_so_far": 51.2,
            "low_so_far": 49.5,
            "latest_bar_time": "2026-03-26 13:30:00",
            "vwap": 50.7,
            "close_vs_vwap": 0.2,
            "distance_from_high": -0.8,
            "bounce_from_low": 2.6,
            "fake_breakout_score": 0.0,
            "absorption_score": 0.7,
            "prev_close": 50.0,
            "open_gap_pct": 0.0,
        },
        position={
            "total_position": 3500,
            "available_volume": 900,
            "base_position": 2600,
            "tactical_position": 900,
            "max_position": 3500,
            "t0_sell_available": 900,
            "t0_buy_capacity": 0,
        },
        current_datetime=datetime(2026, 3, 26, 13, 30),
        signal_history=[
            {"action": "reverse_t_buy", "branch": "reverse_t", "price": 50.0, "volume": 900}
        ],
    )

    assert signal.action == "reverse_t_sell"
    assert signal.volume == 900
