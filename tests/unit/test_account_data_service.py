from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

from src.trading.account_data_service import AccountDataService


class FakeTradeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, value):
        return self

    def limit(self, value):
        return self

    def count(self):
        return len(self.rows)

    def all(self):
        return list(self.rows)


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return FakeTradeQuery(self.rows)

    def close(self):
        return None


def test_get_trades_page_includes_transaction_cost_and_settlement_amount(monkeypatch):
    service = AccountDataService()
    trades = [
        SimpleNamespace(
            id=1,
            order_id="BUY-1",
            stock_code="601138.SH",
            direction="BUY",
            filled_volume=100,
            filled_price=10.0,
            filled_time=datetime(2026, 4, 4, 10, 0, 0),
        ),
        SimpleNamespace(
            id=2,
            order_id="SELL-1",
            stock_code="601138.SH",
            direction="SELL",
            filled_volume=100,
            filled_price=10.5,
            filled_time=datetime(2026, 4, 4, 10, 5, 0),
        ),
    ]

    @contextmanager
    def fake_open_db_session():
        yield FakeSession(trades)

    monkeypatch.setattr(service, "_open_db_session", fake_open_db_session)

    result = service.get_trades_page(page=1, limit=10)

    assert result["total"] == 2
    assert len(result["data"]) == 2

    trades_by_order_id = {item["order_id"]: item for item in result["data"]}
    buy_trade = trades_by_order_id["BUY-1"]
    sell_trade = trades_by_order_id["SELL-1"]

    assert buy_trade["trade_amount"] == 1000.0
    assert buy_trade["transaction_cost"] == 5.01
    assert buy_trade["settlement_amount"] == 1005.01
    assert buy_trade["net_cash_effect"] == -1005.01
    assert buy_trade["trade_breakdown"] == []

    assert sell_trade["trade_amount"] == 1050.0
    assert sell_trade["transaction_cost"] == 5.53
    assert sell_trade["settlement_amount"] == 1044.47
    assert sell_trade["net_cash_effect"] == 1044.47


def test_get_positions_snapshot_includes_summary(monkeypatch):
    service = AccountDataService()
    positions = [
        SimpleNamespace(
            account_id="demo",
            stock_code="000001.SZ",
            total_volume=1000,
            available_volume=900,
            avg_price=10.0,
            market_value=12340.0,
            last_price=12.34,
            snapshot_source="startup_connect",
            snapshot_time=datetime(2026, 4, 5, 9, 30, 0),
        ),
        SimpleNamespace(
            account_id="demo",
            stock_code="601138.SH",
            total_volume=500,
            available_volume=400,
            avg_price=20.0,
            market_value=11000.0,
            last_price=22.0,
            snapshot_source="startup_connect",
            snapshot_time=datetime(2026, 4, 5, 9, 30, 0),
        ),
    ]

    @contextmanager
    def fake_open_db_session():
        yield FakeSession(positions)

    monkeypatch.setattr(service, "_open_db_session", fake_open_db_session)

    snapshot = service.get_positions_snapshot()

    assert snapshot["available"] is True
    assert len(snapshot["positions"]) == 2
    assert snapshot["summary"] == {
        "stocks": 2,
        "total_volume": 1500,
        "available_volume": 1300,
        "market_value": 23340.0,
    }


def test_get_positions_snapshot_without_data_still_returns_summary(monkeypatch):
    service = AccountDataService()

    monkeypatch.setattr(service, "_get_positions_snapshot_from_db", lambda: None)

    snapshot = service.get_positions_snapshot()

    assert snapshot["available"] is False
    assert snapshot["positions"] == []
    assert snapshot["summary"] == {
        "stocks": 0,
        "total_volume": 0,
        "available_volume": 0,
        "market_value": None,
    }


def test_get_account_overview_includes_positions_by_default(monkeypatch):
    service = AccountDataService()
    fake_snapshot = {"available": True, "positions": [{"stock_code": "000001.SZ"}]}

    monkeypatch.setattr(service, "get_positions_snapshot", lambda: fake_snapshot)
    monkeypatch.setattr(service, "get_strategy_pnl_summary", lambda target_date=None: {"ok": True})

    overview = service.get_account_overview()

    assert overview["positions_included"] is True
    assert overview["positions_snapshot"] == fake_snapshot


def test_get_account_overview_can_disable_positions(monkeypatch):
    service = AccountDataService()

    monkeypatch.setattr(service, "get_strategy_pnl_summary", lambda target_date=None: {"ok": True})

    overview = service.get_account_overview(include_positions=False)

    assert overview["positions_included"] is False
    assert overview["positions_snapshot"] is None
