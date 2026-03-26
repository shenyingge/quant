from datetime import datetime

import pandas as pd

from src.backtest.simulator import T0BacktestSimulator
from src.strategy.core.models import PortfolioState
from src.strategy.feature_calculator import FeatureCalculator


def test_feature_calculator_returns_snapshot_object():
    minute_data = pd.DataFrame(
        {
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [1000, 1200],
            "pre_close": [9.95, 9.95],
        },
        index=pd.to_datetime(["2026-03-26 09:30:00", "2026-03-26 09:31:00"]),
    )

    snapshot = FeatureCalculator().calculate_snapshot(minute_data)

    assert snapshot is not None
    assert snapshot.current_close == 10.2
    assert snapshot.latest_bar_time == "2026-03-26 09:31:00"


def test_backtest_simulator_runs_and_emits_signal_log():
    index = pd.to_datetime(
        [
            "2026-03-26 09:50:00",
            "2026-03-26 10:00:00",
            "2026-03-26 13:30:00",
        ]
    )
    minute_data = pd.DataFrame(
        {
            "open": [50.0, 49.6, 50.8],
            "high": [50.1, 50.9, 51.0],
            "low": [49.4, 49.5, 50.6],
            "close": [49.6, 50.8, 50.8],
            "volume": [10000, 15000, 12000],
            "amount": [496000, 762000, 609600],
            "pre_close": [50.5, 50.5, 50.5],
        },
        index=index,
    )
    daily_data = pd.DataFrame({"close": [50 + i * 0.1 for i in range(100)]})
    position = PortfolioState(
        total_position=2600,
        available_volume=2600,
        cost_price=72.0,
        base_position=2600,
        tactical_position=900,
        max_position=3500,
        t0_sell_available=0,
        t0_buy_capacity=900,
        cash_available=70000,
    )

    result = T0BacktestSimulator().run(minute_data, daily_data, position)

    assert not result["signals"].empty
    assert set(result["signals"].columns) >= {"timestamp", "action", "reason"}
    assert result["final_position"].max_position == 3500
