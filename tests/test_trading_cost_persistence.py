from types import SimpleNamespace

from src.order_record_costs import backfill_order_record_costs
from src.trading_costs import (
    TradingFeeSchedule,
    apply_trade_cost_fields,
    build_trade_cost_fields,
    load_trade_breakdown,
    normalize_filled_trades,
)


def test_build_trade_cost_fields_buy_and_sell():
    fee_schedule = TradingFeeSchedule(
        commission_rate=0.0001,
        min_commission=5.0,
        transfer_fee_rate=0.00001,
        stamp_duty_rate=0.0005,
    )

    buy = build_trade_cost_fields(side="BUY", price=10.0, volume=100, fee_schedule=fee_schedule)
    sell = build_trade_cost_fields(
        side="SELL",
        price=10.5,
        volume=100,
        fee_schedule=fee_schedule,
    )

    assert buy["trade_amount"] == 1000.0
    assert buy["transaction_cost"] == 5.01
    assert buy["settlement_amount"] == 1005.01
    assert buy["net_cash_effect"] == -1005.01

    assert sell["trade_amount"] == 1050.0
    assert sell["transaction_cost"] == 5.53
    assert sell["settlement_amount"] == 1044.47
    assert sell["net_cash_effect"] == 1044.47


def test_build_trade_cost_fields_uses_per_fill_transfer_rounding():
    fee_schedule = TradingFeeSchedule(
        commission_rate=0.0001,
        min_commission=5.0,
        transfer_fee_rate=0.00001,
        stamp_duty_rate=0.0005,
    )

    buy = build_trade_cost_fields(
        side="BUY",
        price=52.14,
        volume=500,
        fee_schedule=fee_schedule,
        trade_breakdown=[
            {"trade_id": "B1", "volume": 100, "price": 52.14},
            {"trade_id": "B2", "volume": 400, "price": 52.14},
        ],
    )
    sell = build_trade_cost_fields(
        side="SELL",
        price=52.66,
        volume=500,
        fee_schedule=fee_schedule,
        trade_breakdown=[
            {"trade_id": "S1", "volume": 100, "price": 52.66},
            {"trade_id": "S2", "volume": 400, "price": 52.66},
        ],
    )

    assert buy["transaction_cost"] == 5.25
    assert buy["transfer_fee"] == 0.25
    assert buy["settlement_amount"] == 26075.25

    assert sell["transaction_cost"] == 18.42
    assert sell["transfer_fee"] == 0.26
    assert sell["stamp_duty"] == 13.16
    assert sell["settlement_amount"] == 26311.58


def test_apply_trade_cost_fields_sets_record_attributes():
    fee_schedule = TradingFeeSchedule(
        commission_rate=0.0001,
        min_commission=5.0,
        transfer_fee_rate=0.00001,
        stamp_duty_rate=0.0005,
    )
    record = SimpleNamespace(direction="SELL", filled_price=10.5, filled_volume=100)

    details = apply_trade_cost_fields(record, fee_schedule=fee_schedule)

    assert record.trade_amount == 1050.0
    assert record.transaction_cost == details["transaction_cost"]
    assert record.total_fee == details["total_fee"]
    assert record.settlement_amount == 1044.47


def test_apply_trade_cost_fields_uses_trade_breakdown_in_error_message():
    fee_schedule = TradingFeeSchedule(
        commission_rate=0.0001,
        min_commission=5.0,
        transfer_fee_rate=0.00001,
        stamp_duty_rate=0.0005,
    )
    record = SimpleNamespace(
        direction="SELL",
        filled_price=52.66,
        filled_volume=500,
        error_message='Reconciled from QMT order/trade query; trade_breakdown=[{"traded_id":"D0001","traded_volume":100,"traded_price":52.66},{"traded_id":"D0002","traded_volume":400,"traded_price":52.66}]',
        trade_breakdown=None,
    )

    details = apply_trade_cost_fields(record, fee_schedule=fee_schedule)

    assert details["transaction_cost"] == 18.42
    assert record.total_fee == 18.42
    assert load_trade_breakdown(record)[0]["trade_id"] == "D0001"


def test_normalize_filled_trades_prefers_persisted_trade_cost_fields():
    fee_schedule = TradingFeeSchedule(
        commission_rate=0.0001,
        min_commission=5.0,
        transfer_fee_rate=0.00001,
        stamp_duty_rate=0.0005,
    )
    record = SimpleNamespace(
        order_id="SELL-1",
        stock_code="601138.SH",
        direction="SELL",
        filled_volume=100,
        filled_price=10.5,
        filled_time="2026-04-04T10:05:00",
        trade_amount=1050.0,
        commission=8.88,
        transfer_fee=0.11,
        stamp_duty=0.22,
        total_fee=9.21,
        transaction_cost=9.21,
        settlement_amount=1040.79,
        net_cash_effect=1040.79,
    )

    normalized = normalize_filled_trades([record], fee_schedule)

    assert len(normalized) == 1
    assert normalized[0]["trade_amount"] == 1050.0
    assert normalized[0]["commission"] == 8.88
    assert normalized[0]["total_fee"] == 9.21
    assert normalized[0]["transaction_cost"] == 9.21
    assert normalized[0]["settlement_amount"] == 1040.79


class _FakeBackfillQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, value):
        self.rows = self.rows[:value]
        return self

    def __iter__(self):
        return iter(self.rows)


class _FakeBackfillSession:
    def __init__(self, rows):
        self.rows = rows
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def query(self, model):
        return _FakeBackfillQuery(self.rows)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


def test_backfill_order_record_costs_updates_missing_fields(monkeypatch):
    row = SimpleNamespace(
        id=1,
        order_id="SELL-1",
        stock_code="601138.SH",
        direction="SELL",
        filled_volume=100,
        filled_price=10.5,
        trade_amount=None,
        commission=None,
        transfer_fee=None,
        stamp_duty=None,
        total_fee=None,
        transaction_cost=None,
        settlement_amount=None,
        net_cash_effect=None,
    )
    session = _FakeBackfillSession([row])

    monkeypatch.setattr("src.order_record_costs.SessionLocal", lambda: session)
    monkeypatch.setattr(
        "src.order_record_costs.ensure_order_record_cost_columns", lambda *args, **kwargs: []
    )

    result = backfill_order_record_costs(batch_size=100, dry_run=False, recalculate=False)

    assert result.inspected == 1
    assert result.updated == 1
    assert result.failed == 0
    assert row.trade_amount == 1050.0
    assert row.total_fee == 5.53
    assert row.transaction_cost == 5.53
    assert row.settlement_amount == 1044.47
    assert session.commit_count == 1


def test_backfill_order_record_costs_hydrates_trade_breakdown_from_error_message(monkeypatch):
    row = SimpleNamespace(
        id=2,
        order_id="SELL-2",
        stock_code="601138.SH",
        direction="SELL",
        filled_volume=500,
        filled_price=52.66,
        filled_time="2026-04-03T11:19:56",
        order_time="2026-04-03T11:19:56",
        trade_breakdown=None,
        error_message='Reconciled from QMT order/trade query on 2026-04-03; trade_breakdown=[{"traded_id":"32186489","traded_volume":100,"traded_price":52.66},{"traded_id":"32186490","traded_volume":400,"traded_price":52.66}]',
        trade_amount=None,
        commission=None,
        transfer_fee=None,
        stamp_duty=None,
        total_fee=None,
        transaction_cost=None,
        settlement_amount=None,
        net_cash_effect=None,
    )
    session = _FakeBackfillSession([row])

    monkeypatch.setattr("src.order_record_costs.SessionLocal", lambda: session)
    monkeypatch.setattr(
        "src.order_record_costs.ensure_order_record_cost_columns", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        "src.order_record_costs.infer_trade_breakdown_from_logs",
        lambda **kwargs: [],
    )

    result = backfill_order_record_costs(batch_size=100, dry_run=False, recalculate=False)

    assert result.updated == 1
    assert row.total_fee == 18.42
    assert '"trade_id":"32186489"' in row.trade_breakdown
