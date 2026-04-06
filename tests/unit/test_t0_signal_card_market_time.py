from datetime import datetime

import pandas as pd

from src.strategy.core.models import FeatureSnapshot, PortfolioState
from src.strategy.strategies.t0.feature_calculator import FeatureCalculator
from src.strategy.strategies.t0.strategy_engine import StrategyEngine


def test_feature_calculator_includes_latest_bar_time():
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

    features = FeatureCalculator().calculate_features(minute_data)

    assert features is not None
    assert features["latest_bar_time"] == "2026-03-26 09:31:00"


def test_signal_card_market_contains_bar_time():
    strategy_engine = StrategyEngine()

    signal_card = strategy_engine._build_signal_card(
        trade_date=datetime(2026, 3, 26).date(),
        regime="transition",
        features=FeatureSnapshot(
            latest_bar_time="2026-03-26 10:07:00",
            current_close=51.09,
            vwap=50.57,
            high_so_far=51.15,
            low_so_far=49.85,
            fake_breakout_score=0.3,
            absorption_score=0.6,
            day_open=50.2,
            close_vs_vwap=1.0,
            distance_from_high=-0.1,
            bounce_from_low=2.4,
        ),
        position=PortfolioState(
            total_position=3500,
            available_volume=3500,
            cost_price=72.68,
            base_position=2600,
            tactical_position=900,
            max_position=3500,
            t0_sell_available=900,
            t0_buy_capacity=0,
        ),
        signal={"action": "observe", "reason": "test", "price": 0, "volume": 0},
    )

    assert signal_card["market"]["time"] == "2026-03-26 10:07:00"


def test_signal_card_market_uses_realtime_snapshot_when_available():
    strategy_engine = StrategyEngine()

    signal_card = strategy_engine._build_signal_card(
        trade_date=datetime(2026, 3, 26).date(),
        regime="transition",
        features=FeatureSnapshot(
            latest_bar_time="2026-03-26 10:07:00",
            current_close=51.09,
            vwap=50.57,
            high_so_far=51.15,
            low_so_far=49.85,
            fake_breakout_score=0.3,
            absorption_score=0.6,
            day_open=50.2,
            close_vs_vwap=1.0,
            distance_from_high=-0.1,
            bounce_from_low=2.4,
        ),
        position=PortfolioState(
            total_position=3500,
            available_volume=3500,
            cost_price=72.68,
            base_position=2600,
            tactical_position=900,
            max_position=3500,
            t0_sell_available=900,
            t0_buy_capacity=0,
        ),
        signal={"action": "observe", "reason": "test", "price": 0, "volume": 0},
        snapshot={"time": "2026-03-26 10:14:49", "price": 51.2, "high": 51.5, "low": 49.85},
    )

    assert signal_card["market"]["time"] == "2026-03-26 10:14:49"
    assert signal_card["market"]["price"] == 51.2
    assert signal_card["market"]["high"] == 51.5
    assert signal_card["market"]["vwap"] == 50.57
