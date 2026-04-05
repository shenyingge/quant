import sys
from datetime import date as real_date
from types import SimpleNamespace

import pandas as pd

import main as main_module

import src.trading.trading_day_checker as trading_day_checker


def test_is_trading_day_returns_true_when_tushare_marks_open(monkeypatch):
    calls = {}

    class FakePro:
        def trade_cal(self, **kwargs):
            calls.update(kwargs)
            return pd.DataFrame(
                [
                    {
                        "exchange": "SSE",
                        "cal_date": "20260327",
                        "is_open": "1",
                        "pretrade_date": "20260326",
                    }
                ]
            )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 27)) is True
    assert calls == {
        "exchange": "SSE",
        "start_date": "20260327",
        "end_date": "20260327",
        "fields": "exchange,cal_date,is_open,pretrade_date",
    }


def test_is_trading_day_returns_false_when_tushare_marks_closed(monkeypatch):
    class FakePro:
        def trade_cal(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "exchange": "SSE",
                        "cal_date": "20260328",
                        "is_open": "0",
                        "pretrade_date": "20260327",
                    }
                ]
            )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 28)) is False


def test_is_trading_day_falls_back_to_qmt_when_tushare_has_no_data(monkeypatch):
    class FakePro:
        def trade_cal(self, **kwargs):
            return pd.DataFrame(columns=["exchange", "cal_date", "is_open", "pretrade_date"])

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: ["20260327", "20260331"],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 27)) is True


def test_is_trading_day_falls_back_to_qmt_when_tushare_raises(monkeypatch):
    class FakePro:
        def trade_cal(self, **kwargs):
            raise RuntimeError("network unavailable")

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: ["20260327", "20260331"],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 27)) is True


def test_is_trading_day_returns_false_when_both_providers_fail(monkeypatch):
    class FakePro:
        def trade_cal(self, **kwargs):
            raise RuntimeError("network unavailable")

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: [],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 27)) is False


def test_run_t0_strategy_skips_when_not_trading_day(monkeypatch):
    monkeypatch.setattr(main_module, "is_trading_day", lambda: False)
    monkeypatch.setattr(main_module, "STRATEGY_ENGINE_NAME", "策略引擎")
    started = {"value": False}

    class FakeStrategyEngine:
        def __init__(self):
            started["value"] = True

        def run_once(self):
            return {"signal": {"action": "observe"}}

    monkeypatch.setitem(
        sys.modules,
        "src.strategy.strategy_engine",
        SimpleNamespace(StrategyEngine=FakeStrategyEngine),
    )

    main_module.run_t0_strategy()

    assert started["value"] is False
