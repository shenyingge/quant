import sys
from datetime import date as real_date
from types import SimpleNamespace

import pandas as pd
import pytest

import main as main_module

import src.trading.calendar.trading_day_checker as trading_day_checker


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    def __init__(self, value):
        self._value = value
        self.closed = False
        self.calls = []

    def execute(self, statement, params):
        self.calls.append({"statement": str(statement), "params": params})
        return FakeScalarResult(self._value)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clear_trading_day_cache():
    trading_day_checker._trading_day_cache.clear()
    yield
    trading_day_checker._trading_day_cache.clear()


def test_is_trading_day_prefers_database_before_qmt_and_tushare(monkeypatch):
    qmt_called = {"value": False}
    tushare_called = {"value": False}
    session = FakeSession(True)

    class FakePro:
        def trade_cal(self, **kwargs):
            tushare_called["value"] = True
            return pd.DataFrame()

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: qmt_called.__setitem__("value", True),
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "meta_db_schema", "gold")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setattr(trading_day_checker, "SessionLocal", lambda: session)
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 27)) is True
    assert session.closed is True
    assert session.calls[0]["params"] == {"check_date": "20260327"}
    assert '"gold".trade_cal' in session.calls[0]["statement"]
    assert qmt_called["value"] is False
    assert tushare_called["value"] is False


def test_is_trading_day_falls_back_to_qmt_when_database_has_no_data(monkeypatch):
    qmt_calls = {}
    session = FakeSession(None)

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: qmt_calls.update(
            {
                "market": market,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        or ["20260328", "20260331"],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "meta_db_schema", "gold")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", None)
    monkeypatch.setattr(trading_day_checker, "SessionLocal", lambda: session)
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 28)) is True
    assert qmt_calls == {
        "market": "SH",
        "start_date": "20260101",
        "end_date": "20261231",
    }


def test_is_trading_day_falls_back_to_tushare_when_database_and_qmt_fail(monkeypatch):
    session = FakeSession(None)

    class FakePro:
        def trade_cal(self, **kwargs):
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

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: [],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "meta_db_schema", "gold")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setattr(trading_day_checker, "SessionLocal", lambda: session)
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
    session = FakeSession(None)

    class FakePro:
        def trade_cal(self, **kwargs):
            raise RuntimeError("network unavailable")

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: [],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "meta_db_schema", "gold")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setattr(trading_day_checker, "SessionLocal", lambda: session)
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.is_trading_day(real_date(2026, 3, 27)) is False


def test_resolve_trading_day_status_returns_none_when_both_providers_fail(monkeypatch):
    session = FakeSession(None)

    class FakePro:
        def trade_cal(self, **kwargs):
            raise RuntimeError("network unavailable")

    fake_xtdata = SimpleNamespace(
        download_holiday_data=lambda: None,
        get_trading_calendar=lambda market, start_date, end_date: [],
    )

    monkeypatch.setattr(trading_day_checker.settings, "test_mode_enabled", False)
    monkeypatch.setattr(trading_day_checker.settings, "trading_day_check_enabled", True)
    monkeypatch.setattr(trading_day_checker.settings, "meta_db_schema", "gold")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_token", "demo-token")
    monkeypatch.setattr(trading_day_checker.settings, "tushare_trade_calendar_exchange", "SSE")
    monkeypatch.setattr(trading_day_checker, "SessionLocal", lambda: session)
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda token: FakePro()))
    monkeypatch.setitem(sys.modules, "xtquant", SimpleNamespace(xtdata=fake_xtdata))

    assert trading_day_checker.resolve_trading_day_status(real_date(2026, 3, 27)) is None
