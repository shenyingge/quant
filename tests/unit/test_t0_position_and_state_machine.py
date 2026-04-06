from datetime import date, datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from src.strategy.core.models import SignalEvent
from src.strategy.strategies.t0.position_syncer import PositionSyncer
from src.strategy.strategies.t0.signal_generator import SignalGenerator


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
            "total_position": 4000,
            "available_volume": 3500,
            "cost_price": 72.68,
        }
    )

    assert position["base_position"] == 3100
    assert position["tactical_position"] == 900
    assert position["max_position"] == 4000
    assert position["t0_sell_available"] == 900
    assert position["t0_buy_capacity"] == 0


def test_position_syncer_loads_existing_position_file(tmp_path):
    syncer = PositionSyncer(output_dir=str(tmp_path))
    syncer.position_file.write_text(
        json.dumps(
            {
                "stock_code": "601138.SH",
                "total_position": 4000,
                "available_volume": 3500,
                "cost_price": 72.68,
                "base_position": 2600,
                "tactical_position": 900,
            }
        ),
        encoding="utf-8",
    )

    position = syncer.load_position()
    portfolio = syncer.load_portfolio_state()

    assert position is not None
    assert position["total_position"] == 4000
    assert position["base_position"] == 3100
    assert position["t0_sell_available"] == 900
    assert portfolio.total_position == 4000
    assert portfolio.base_position == 3100
    assert portfolio.t0_sell_available == 900


def test_position_syncer_needs_qmt_sync_without_today_snapshot(tmp_path):
    syncer = PositionSyncer(output_dir=str(tmp_path))

    assert syncer.needs_qmt_sync(date(2026, 3, 26)) is True

    syncer.position_file.write_text(
        json.dumps(
            {
                "stock_code": "601138.SH",
                "total_position": 3500,
                "available_volume": 3500,
                "cost_price": 72.68,
                "last_sync_source": "qmt",
                "last_qmt_sync_time": "2026-03-26T09:25:00",
                "last_reconciled_fill_time": "2026-03-26T09:25:00",
            }
        ),
        encoding="utf-8",
    )

    assert syncer.needs_qmt_sync(date(2026, 3, 26)) is False
    assert syncer.needs_qmt_sync(date(2026, 3, 27)) is True


def test_position_syncer_reconciles_local_fills_into_position_state(tmp_path, monkeypatch):
    syncer = PositionSyncer(output_dir=str(tmp_path))
    syncer.position_file.write_text(
        json.dumps(
            {
                "stock_code": "601138.SH",
                "total_position": 4000,
                "available_volume": 3500,
                "cost_price": 50.0,
                "last_sync_source": "qmt",
                "last_qmt_sync_time": "2026-03-26T09:25:00",
                "last_reconciled_fill_time": "2026-03-26T09:25:00",
            }
        ),
        encoding="utf-8",
    )

    fills = [
        SimpleNamespace(
            direction="SELL",
            filled_volume=300,
            filled_price=53.0,
            filled_time=datetime(2026, 3, 26, 10, 0, 0),
        ),
        SimpleNamespace(
            direction="BUY",
            filled_volume=200,
            filled_price=52.5,
            filled_time=datetime(2026, 3, 26, 10, 15, 0),
        ),
    ]

    monkeypatch.setattr(syncer, "_load_filled_orders_since", lambda stock_code, since_time: fills)
    monkeypatch.setattr(syncer, "_utcnow", lambda: datetime(2026, 3, 26, 10, 15, 5))

    position = syncer.load_position()

    assert position["total_position"] == 3900
    assert position["available_volume"] == 3400
    assert round(position["cost_price"], 4) == round((3700 * 50.0 + 200 * 52.5) / 3900, 4)
    assert position["t0_sell_available"] == 800
    assert position["t0_buy_capacity"] == 100
    assert position["last_sync_source"] == "local_db_reconciled"
    assert position["last_reconciled_fill_time"] == "2026-03-26T10:15:00"


def test_position_syncer_builds_fill_state_with_reconcile_marker():
    syncer = PositionSyncer()

    updated = syncer._build_filled_position_state(
        {
            "stock_code": "601138.SH",
            "total_position": 4000,
            "available_volume": 3500,
            "cost_price": 50.0,
            "position_version": 7,
        },
        direction="SELL",
        volume=300,
        price=53.0,
        filled_time=datetime(2026, 3, 26, 10, 5, 0),
        source="trade_callback",
    )

    assert updated["total_position"] == 3700
    assert updated["available_volume"] == 3200
    assert updated["last_sync_source"] == "trade_callback"
    assert updated["last_fill_time"] == "2026-03-26T10:05:00"
    assert updated["last_reconciled_fill_time"] == "2026-03-26T10:05:00"
    assert updated["position_version"] == 7


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

    with patch("src.strategy.strategies.t0.signal_generator.datetime", _MorningDateTime):
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

    with patch("src.strategy.strategies.t0.signal_generator.datetime", _AfternoonDateTime):
        signal = generator.generate_signal(
            "transition", features, position, date(2026, 3, 26), signal_history=history
        )

    assert signal["action"] == "reverse_t_sell"
    assert signal["volume"] == 900
    assert "浮盈" in signal["reason"]
