import threading
from datetime import datetime
from types import SimpleNamespace

from src.infrastructure.db import OrderRecord
from src.trading.execution.qmt_trader import QMTCallback


class DummyNotifier:
    def __init__(self):
        self.payloads = []

    def notify_order_filled(self, payload):
        self.payloads.append(payload)


class DummySession:
    def __init__(self):
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


class DummyTrader:
    def __init__(self):
        self._last_callback_data = {}
        self.notifier = DummyNotifier()
        self.stats_lock = threading.Lock()
        self.stats = {}
        self.active_orders = {}
        self.order_lock = threading.Lock()


class DummyPositionSyncer:
    def __init__(self):
        self.applied = []
        self.publish_calls = []

    def apply_fill_transactional(
        self,
        db,
        direction,
        volume,
        price,
        *,
        stock_code=None,
        filled_time=None,
        source="trade_callback",
    ):
        self.applied.append(
            {
                "direction": direction,
                "volume": volume,
                "price": price,
                "stock_code": stock_code,
                "filled_time": filled_time,
                "source": source,
            }
        )
        return {
            "stock_code": stock_code,
            "position_version": 1,
            "total_position": volume,
            "available_volume": volume,
        }

    def publish_pending_events(self, limit=20):
        self.publish_calls.append(limit)
        return 1


def test_trade_callback_creates_standalone_order_record(monkeypatch):
    trader = DummyTrader()
    callback = QMTCallback(trader)
    session = DummySession()
    sync_calls = []
    position_syncer = DummyPositionSyncer()

    monkeypatch.setattr("src.trading.execution.qmt_trader.SessionLocal", lambda: session)
    monkeypatch.setattr("src.trading.execution.qmt_trader.get_stock_display_name", lambda stock_code: stock_code)
    monkeypatch.setattr("src.strategy.strategies.t0.position_syncer.PositionSyncer", lambda: position_syncer)
    monkeypatch.setattr(
        QMTCallback,
        "_load_order_record_for_trade",
        lambda self, db, raw_order_id, stock_code, traded_volume: None,
    )
    monkeypatch.setattr(
        "src.trading.execution.qmt_trader.sync_account_positions_from_qmt",
        lambda trader_instance, source: sync_calls.append(source),
    )

    trade = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id=0,
        traded_volume=100,
        traded_price=52.14,
        trade_id="T12345",
        order_type=23,
    )

    callback.on_stock_trade(trade)

    assert len(session.added) == 1
    order_record = session.added[0]
    assert order_record.order_id == "MANUAL_T12345"
    assert order_record.stock_code == "601138.SH"
    assert order_record.direction == "BUY"
    assert order_record.volume == 100
    assert order_record.filled_volume == 100
    assert order_record.filled_price == 52.14
    assert order_record.fill_notified is True
    assert "matching order record" in order_record.error_message
    assert trader.notifier.payloads[0]["order_id"] == "MANUAL_T12345"
    assert trader.notifier.payloads[0]["stock_code"] == "601138.SH"
    assert session.commit_count == 2
    assert sync_calls == ["trade_callback"]
    assert position_syncer.applied[0]["direction"] == "BUY"
    assert position_syncer.publish_calls == [20]
    assert trader.stats["total_trade_volume"] == 100


def test_trade_callback_updates_existing_record_when_match_is_resolved(monkeypatch):
    trader = DummyTrader()
    callback = QMTCallback(trader)
    session = DummySession()
    sync_calls = []
    position_syncer = DummyPositionSyncer()
    existing_record = OrderRecord(
        signal_id="sig-1",
        order_id="ORDER-1",
        stock_code="601138.SH",
        direction="BUY",
        volume=200,
        price=52.0,
        order_status="PENDING",
        fill_notified=False,
    )

    monkeypatch.setattr("src.trading.execution.qmt_trader.SessionLocal", lambda: session)
    monkeypatch.setattr("src.trading.execution.qmt_trader.get_stock_display_name", lambda stock_code: stock_code)
    monkeypatch.setattr("src.strategy.strategies.t0.position_syncer.PositionSyncer", lambda: position_syncer)
    monkeypatch.setattr(
        QMTCallback,
        "_load_order_record_for_trade",
        lambda self, db, raw_order_id, stock_code, traded_volume: existing_record,
    )
    monkeypatch.setattr(
        "src.trading.execution.qmt_trader.sync_account_positions_from_qmt",
        lambda trader_instance, source: sync_calls.append(source),
    )

    trade = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id=0,
        traded_volume=100,
        traded_price=52.14,
        trade_id="T67890",
        order_type=23,
    )

    callback.on_stock_trade(trade)

    assert session.added == []
    assert existing_record.filled_volume == 100
    assert existing_record.filled_price == 52.14
    assert existing_record.order_status == "部分成交"
    assert existing_record.fill_notified is True
    assert trader.notifier.payloads[0]["order_id"] == "ORDER-1"
    assert session.commit_count == 2
    assert sync_calls == ["trade_callback"]
    assert position_syncer.applied[0]["direction"] == "BUY"


def test_trade_callback_uses_xtquant_traded_id_when_trade_id_is_missing(monkeypatch):
    trader = DummyTrader()
    callback = QMTCallback(trader)
    session = DummySession()
    sync_calls = []
    position_syncer = DummyPositionSyncer()

    monkeypatch.setattr("src.trading.execution.qmt_trader.SessionLocal", lambda: session)
    monkeypatch.setattr("src.trading.execution.qmt_trader.get_stock_display_name", lambda stock_code: stock_code)
    monkeypatch.setattr("src.strategy.strategies.t0.position_syncer.PositionSyncer", lambda: position_syncer)
    monkeypatch.setattr(
        QMTCallback,
        "_load_order_record_for_trade",
        lambda self, db, raw_order_id, stock_code, traded_volume: None,
    )
    monkeypatch.setattr(
        "src.trading.execution.qmt_trader.sync_account_positions_from_qmt",
        lambda trader_instance, source: sync_calls.append(source),
    )

    trade = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id=0,
        traded_volume=100,
        traded_price=52.66,
        traded_id="D0001",
        order_type=24,
    )

    callback.on_stock_trade(trade)

    assert len(session.added) == 1
    order_record = session.added[0]
    assert order_record.order_id == "MANUAL_D0001"
    assert order_record.direction == "SELL"
    assert trader.notifier.payloads[0]["order_id"] == "MANUAL_D0001"
    assert sync_calls == ["trade_callback"]
    assert position_syncer.applied[0]["direction"] == "SELL"


def test_trade_callback_keeps_distinct_partial_fills_with_different_traded_id(monkeypatch):
    trader = DummyTrader()
    callback = QMTCallback(trader)
    session = DummySession()
    sync_calls = []
    position_syncer = DummyPositionSyncer()

    monkeypatch.setattr("src.trading.execution.qmt_trader.SessionLocal", lambda: session)
    monkeypatch.setattr("src.trading.execution.qmt_trader.get_stock_display_name", lambda stock_code: stock_code)
    monkeypatch.setattr("src.strategy.strategies.t0.position_syncer.PositionSyncer", lambda: position_syncer)
    monkeypatch.setattr(
        QMTCallback,
        "_load_order_record_for_trade",
        lambda self, db, raw_order_id, stock_code, traded_volume: None,
    )
    monkeypatch.setattr(
        "src.trading.execution.qmt_trader.sync_account_positions_from_qmt",
        lambda trader_instance, source: sync_calls.append(source),
    )

    trade_one = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id=0,
        traded_volume=100,
        traded_price=52.66,
        traded_time="20260403111952",
        traded_id="D0001",
        order_type=24,
    )
    trade_two = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id=0,
        traded_volume=100,
        traded_price=52.66,
        traded_time="20260403111952",
        traded_id="D0002",
        order_type=24,
    )

    callback.on_stock_trade(trade_one)
    callback.on_stock_trade(trade_two)

    assert len(session.added) == 2
    assert [item.order_id for item in session.added] == ["MANUAL_D0001", "MANUAL_D0002"]
    assert len(trader.notifier.payloads) == 2
    assert trader.stats["total_trade_volume"] == 200
    assert sync_calls == ["trade_callback", "trade_callback"]
    assert [item["direction"] for item in position_syncer.applied] == ["SELL", "SELL"]


def test_trade_callback_accumulates_trade_breakdown_on_existing_order_record(monkeypatch):
    trader = DummyTrader()
    callback = QMTCallback(trader)
    session = DummySession()
    sync_calls = []
    position_syncer = DummyPositionSyncer()
    existing_record = OrderRecord(
        signal_id="sig-2",
        order_id="ORDER-2",
        stock_code="601138.SH",
        direction="BUY",
        volume=500,
        price=52.14,
        order_status="PENDING",
        fill_notified=False,
    )
    matched_records = [existing_record, existing_record]

    monkeypatch.setattr("src.trading.execution.qmt_trader.SessionLocal", lambda: session)
    monkeypatch.setattr("src.trading.execution.qmt_trader.get_stock_display_name", lambda stock_code: stock_code)
    monkeypatch.setattr("src.strategy.strategies.t0.position_syncer.PositionSyncer", lambda: position_syncer)
    monkeypatch.setattr(
        QMTCallback,
        "_load_order_record_for_trade",
        lambda self, db, raw_order_id, stock_code, traded_volume: matched_records.pop(0),
    )
    monkeypatch.setattr(
        "src.trading.execution.qmt_trader.sync_account_positions_from_qmt",
        lambda trader_instance, source: sync_calls.append(source),
    )

    trade_one = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id="ORDER-2",
        traded_volume=100,
        traded_price=52.14,
        traded_time="20260402132156",
        traded_id="B0001",
        order_type=23,
    )
    trade_two = SimpleNamespace(
        account_id="8884394806",
        stock_code="601138.SH",
        order_id="ORDER-2",
        traded_volume=400,
        traded_price=52.14,
        traded_time="20260402132159",
        traded_id="B0002",
        order_type=23,
    )

    callback.on_stock_trade(trade_one)
    callback.on_stock_trade(trade_two)

    assert existing_record.filled_volume == 500
    assert existing_record.filled_price == 52.14
    assert existing_record.order_status == "FILLED"
    assert existing_record.trade_breakdown is not None
    assert '"trade_id":"B0001"' in existing_record.trade_breakdown
    assert '"trade_id":"B0002"' in existing_record.trade_breakdown
    assert existing_record.transfer_fee == 0.25
    assert existing_record.total_fee == 5.25
    assert sync_calls == ["trade_callback", "trade_callback"]


def test_parse_trade_timestamp_supports_unix_epoch_seconds():
    callback = QMTCallback(DummyTrader())

    parsed = callback._parse_trade_timestamp(1775186396)

    assert parsed == datetime(2026, 4, 3, 11, 19, 56)
