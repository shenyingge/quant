from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from src.strategy.core.models import SignalEvent
from src.strategy.position_syncer import PositionSyncer
from src.strategy.signal_generator import SignalGenerator


class _MorningDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 3, 26, 10, 0, 0)


class _AfternoonDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 3, 26, 13, 30, 0)


def test_position_syncer_normalizes_base_and_tactical_capacity():
    syncer = PositionSyncer()

    position = syncer._normalize_position_state(
        {
            "stock_code": "601138.SH",
            "total_position": 3500,
            "available_volume": 3500,
            "cost_price": 72.68,
        }
    )

    assert position["base_position"] == 2600
    assert position["tactical_position"] == 900
    assert position["max_position"] == 3500
    assert position["t0_sell_available"] == 900
    assert position["t0_buy_capacity"] == 0


def test_reverse_t_buy_is_blocked_when_tactical_buy_capacity_is_zero():
    generator = SignalGenerator()
    features = {
        "day_open": 50.0,
        "current_close": 50.8,
        "high_so_far": 51.0,
        "low_so_far": 49.5,
        "vwap": 50.6,
        "close_vs_vwap": 0.4,
        "bounce_from_low": 2.6,
        "fake_breakout_score": 0.0,
        "absorption_score": 0.7,
    }
    position = {
        "total_position": 3500,
        "available_volume": 3500,
        "base_position": 2600,
        "tactical_position": 900,
        "max_position": 3500,
        "t0_sell_available": 900,
        "t0_buy_capacity": 0,
    }

    with patch("src.strategy.signal_generator.datetime", _MorningDateTime):
        signal = generator.generate_signal(
            "transition", features, position, date(2026, 3, 26), signal_history=[]
        )

    assert signal["action"] == "observe"
    assert signal["reason"] in {"无符合条件的信号", "当前无可用机动仓买入"}


def test_reverse_t_buy_can_follow_with_reverse_t_sell_same_day():
    generator = SignalGenerator()
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

    with patch("src.strategy.signal_generator.datetime", _AfternoonDateTime):
        signal = generator.generate_signal(
            "transition", features, position, date(2026, 3, 26), signal_history=history
        )

    assert signal["action"] == "reverse_t_sell"
    assert signal["volume"] == 900
    assert "浮盈" in signal["reason"]
