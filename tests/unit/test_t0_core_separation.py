from datetime import datetime, time

import pandas as pd

from src.infrastructure.config import settings
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


def test_engine_forces_reverse_t_sell_on_adverse_move_stop_loss():
    params = T0StrategyParams(
        t0_reverse_sell_min_profit=99.0,
        t0_reverse_sell_stop_loss_pct=5.0,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "current_close": 47.0,
        "high_so_far": 50.2,
        "low_so_far": 46.8,
        "vwap": 48.0,
        "close_vs_vwap": -2.1,
        "bounce_from_low": 0.3,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.4,
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
        current_datetime=datetime(2026, 3, 26, 13, 30),
        signal_history=history,
    )

    assert signal["action"] == "reverse_t_sell"
    assert "止损卖出" in signal["reason"]


def test_engine_forces_reverse_t_sell_after_carry_timeout():
    params = T0StrategyParams(
        t0_reverse_sell_min_profit=99.0,
        t0_reverse_sell_max_carry_days=5,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "current_close": 49.0,
        "high_so_far": 50.2,
        "low_so_far": 48.8,
        "vwap": 49.4,
        "close_vs_vwap": -0.8,
        "bounce_from_low": 0.2,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.3,
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
            signal_time=datetime(2026, 3, 20, 10, 0),
            carry_trading_days=5,
        )
    ]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 30),
        current_datetime=datetime(2026, 3, 27, 13, 30),
        signal_history=history,
    )

    assert signal["action"] == "reverse_t_sell"
    assert "跨日兜底卖出" in signal["reason"]


def test_engine_allows_reverse_t_sell_after_carry_when_roundtrip_is_positive():
    params = T0StrategyParams(
        t0_reverse_sell_min_profit=5.0,
        t0_reverse_sell_max_vwap_distance=0.1,
        t0_reverse_sell_take_profit_after_carry_days=3,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "current_close": 50.5,
        "high_so_far": 50.8,
        "low_so_far": 49.7,
        "vwap": 49.5,
        "close_vs_vwap": 2.02,
        "bounce_from_low": 1.6,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.6,
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
            signal_time=datetime(2026, 3, 20, 10, 0),
            carry_trading_days=3,
        )
    ]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 30),
        current_datetime=datetime(2026, 3, 27, 13, 30),
        signal_history=history,
    )

    assert signal["action"] == "reverse_t_sell"
    assert "跨日止盈卖出" in signal["reason"]


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


def test_engine_blocks_positive_t_sell_on_large_gap_down_open():
    engine = T0StrategyEngine(T0StrategyParams(t0_positive_sell_gap_down_limit=-1.0))
    features = {
        "day_open": 95.0,
        "prev_close": 100.0,
        "current_close": 96.0,
        "high_so_far": 97.5,
        "low_so_far": 94.8,
        "vwap": 96.2,
        "close_vs_vwap": -0.2,
        "bounce_from_low": 1.3,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.5,
    }
    position = {
        "total_position": 3500,
        "available_volume": 3500,
        "base_position": 3000,
        "tactical_position": 1000,
        "max_position": 4000,
        "t0_sell_available": 500,
        "t0_buy_capacity": 500,
    }

    signal = engine._check_positive_t_sell(features, position)

    assert signal["action"] == "observe"
    assert "低开" in signal["reason"]


def test_engine_forces_positive_t_buyback_after_carry_timeout():
    params = T0StrategyParams(
        t0_positive_buyback_max_carry_days=1,
        t0_positive_buyback_stop_loss_pct=99.0,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 49.5,
        "prev_close": 50.0,
        "current_close": 49.6,
        "high_so_far": 49.8,
        "low_so_far": 49.3,
        "vwap": 49.7,
        "close_vs_vwap": -0.2,
        "bounce_from_low": 0.2,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.1,
    }
    position = {
        "total_position": 3000,
        "available_volume": 3000,
        "base_position": 3000,
        "tactical_position": 1000,
        "max_position": 4000,
        "t0_sell_available": 0,
        "t0_buy_capacity": 1000,
    }
    history = [
        SignalEvent(
            action="positive_t_sell",
            branch="positive_t",
            price=50.0,
            volume=500,
            signal_time=datetime(2026, 3, 26, 9, 45),
            carry_trading_days=1,
        )
    ]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 40),
        current_datetime=datetime(2026, 3, 27, 13, 40),
        signal_history=history,
    )

    assert signal["action"] == "positive_t_buyback"
    assert "跨日兜底回补" in signal["reason"]


def test_engine_uses_trading_day_count_instead_of_natural_day_gap_for_carry_timeout():
    params = T0StrategyParams(
        t0_positive_buyback_max_carry_days=2,
        t0_positive_buyback_stop_loss_pct=99.0,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 49.5,
        "prev_close": 50.0,
        "current_close": 49.6,
        "high_so_far": 49.8,
        "low_so_far": 49.3,
        "vwap": 49.7,
        "close_vs_vwap": -0.2,
        "bounce_from_low": 0.2,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.1,
    }
    position = {
        "total_position": 3000,
        "available_volume": 3000,
        "base_position": 3000,
        "tactical_position": 1000,
        "max_position": 4000,
        "t0_sell_available": 0,
        "t0_buy_capacity": 1000,
    }
    history = [
        SignalEvent(
            action="positive_t_sell",
            branch="positive_t",
            price=50.0,
            volume=500,
            signal_time=datetime(2026, 3, 27, 9, 45),
            carry_trading_days=1,
        )
    ]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 40),
        current_datetime=datetime(2026, 3, 30, 13, 40),
        signal_history=history,
    )

    assert signal["action"] == "observe"
    assert signal["reason"] == "正T回补条件不满足"


def test_engine_forces_positive_t_buyback_on_adverse_move_stop_loss():
    params = T0StrategyParams(
        t0_positive_buyback_max_carry_days=5,
        t0_positive_buyback_stop_loss_pct=1.0,
    )
    engine = T0StrategyEngine(params)
    features = {
        "day_open": 50.0,
        "prev_close": 50.0,
        "current_close": 50.7,
        "high_so_far": 50.9,
        "low_so_far": 49.8,
        "vwap": 50.6,
        "close_vs_vwap": 0.2,
        "bounce_from_low": 0.1,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.2,
    }
    position = {
        "total_position": 3000,
        "available_volume": 3000,
        "base_position": 3000,
        "tactical_position": 1000,
        "max_position": 4000,
        "t0_sell_available": 0,
        "t0_buy_capacity": 1000,
    }
    history = [
        SignalEvent(
            action="positive_t_sell",
            branch="positive_t",
            price=50.0,
            volume=500,
            signal_time=datetime(2026, 3, 26, 9, 45),
        )
    ]

    signal = engine.generate_signal(
        regime="transition",
        features=features,
        position=position,
        current_time=time(13, 40),
        current_datetime=datetime(2026, 3, 26, 13, 40),
        signal_history=history,
    )

    assert signal["action"] == "positive_t_buyback"
    assert "止损回补" in signal["reason"]
