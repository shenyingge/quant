from datetime import datetime, time

import pandas as pd

from src.config import settings
from src.strategy.core.engine import T0StrategyEngine
from src.strategy.core.models import SignalEvent
from src.strategy.core.params import T0StrategyParams
from src.strategy.core.regime_classifier import RegimeClassifier


def test_regime_classifier_is_pure_and_returns_transition_for_short_data():
    df = pd.DataFrame({"close": [10 + i * 0.1 for i in range(30)]})

    regime = RegimeClassifier().calculate(df)

    assert regime == "transition"


def test_engine_generates_reverse_t_sell_from_explicit_history_without_database():
    engine = T0StrategyEngine(T0StrategyParams.from_settings(settings))
    features = {
        "day_open": 50.0,
        "current_close": 50.8,
        "high_so_far": 51.2,
        "low_so_far": 49.5,
        "vwap": 50.7,
        "close_vs_vwap": 0.2,
        "bounce_from_low": 2.6,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.7,
    }
    position = {
        "total_position": 3500,
        "available_volume": 900,
        "base_position": 2600,
        "tactical_position": 900,
        "max_position": 3500,
        "t0_sell_available": 900,
        "t0_buy_capacity": 0,
    }
    history = [SignalEvent(action="reverse_t_buy", branch="reverse_t", price=50.0, volume=900)]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 30),
        signal_history=history,
    )

    assert signal["action"] == "reverse_t_sell"
    assert signal["volume"] == 900


def test_engine_blocks_close_before_min_hold_minutes():
    params = T0StrategyParams(t0_min_hold_minutes=20)
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "current_close": 50.8,
        "high_so_far": 51.2,
        "low_so_far": 49.5,
        "vwap": 50.7,
        "close_vs_vwap": 0.2,
        "bounce_from_low": 2.6,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.7,
    }
    position = {
        "total_position": 3500,
        "available_volume": 900,
        "base_position": 2600,
        "tactical_position": 900,
        "max_position": 3500,
        "t0_sell_available": 900,
        "t0_buy_capacity": 0,
    }
    history = [
        SignalEvent(
            action="reverse_t_buy",
            branch="reverse_t",
            price=50.0,
            volume=900,
            signal_time=datetime(2026, 3, 26, 13, 15),
        )
    ]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 30),
        current_datetime=datetime(2026, 3, 26, 13, 30),
        signal_history=history,
    )

    assert signal["action"] == "observe"
    assert "最小持有时间未满足" in signal["reason"]


def test_engine_blocks_reverse_t_sell_when_fees_exceed_profit():
    params = T0StrategyParams(
        t0_trade_unit=100,
        t0_commission_rate=0.0001,
        t0_min_commission=5.0,
        t0_transfer_fee_rate=0.00001,
        t0_stamp_duty_rate=0.0005,
        t0_reverse_sell_min_profit=0.0,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "current_close": 50.05,
        "high_so_far": 50.2,
        "low_so_far": 49.8,
        "vwap": 50.05,
        "close_vs_vwap": 0.0,
        "bounce_from_low": 0.6,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.7,
    }
    position = {
        "total_position": 2700,
        "available_volume": 100,
        "base_position": 2600,
        "tactical_position": 900,
        "max_position": 3500,
        "t0_sell_available": 100,
        "t0_buy_capacity": 0,
    }
    history = [SignalEvent(action="reverse_t_buy", branch="reverse_t", price=50.0, volume=100)]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 30),
        signal_history=history,
    )

    assert signal["action"] == "observe"
    assert "手续费" in signal["reason"]


def test_engine_blocks_positive_t_buyback_when_fees_exceed_spread():
    params = T0StrategyParams(
        t0_trade_unit=100,
        t0_commission_rate=0.0001,
        t0_min_commission=5.0,
        t0_transfer_fee_rate=0.00001,
        t0_stamp_duty_rate=0.0005,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "current_close": 49.98,
        "high_so_far": 50.1,
        "low_so_far": 49.7,
        "vwap": 49.95,
        "close_vs_vwap": 0.06,
        "bounce_from_low": 0.5,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.7,
    }
    position = {
        "total_position": 2600,
        "available_volume": 2600,
        "base_position": 2600,
        "tactical_position": 900,
        "max_position": 3500,
        "t0_sell_available": 0,
        "t0_buy_capacity": 100,
    }
    history = [SignalEvent(action="positive_t_sell", branch="positive_t", price=50.0, volume=100)]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 40),
        signal_history=history,
    )

    assert signal["action"] == "observe"
    assert "手续费" in signal["reason"]
