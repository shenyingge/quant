from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

from src.account_data_service import AccountDataService


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
