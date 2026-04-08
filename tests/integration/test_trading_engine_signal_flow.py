import json
import threading
import time
from types import SimpleNamespace

import pytest
import redis

from src.infrastructure.config import settings
from src.infrastructure.db import OrderRecord, SessionLocal, TradeExecution, TradingSignal
from src.infrastructure.redis import RedisSignalListener
from src.infrastructure.redis.connection import build_redis_client_kwargs
from src.trading.execution.qmt_trader import QMTCallback
from src.trading.runtime.engine import TradingEngine


class _SilentNotifier:
    def notify_signal_received(self, signal_data):
        return True

    def notify_order_placed(self, signal_data, order_id):
        return True

    def notify_order_filled(self, order_info):
        return True

    def notify_error(self, error_message, context=""):
        return True

    def notify_service_status(self, status, message=""):
        return True

    def notify_runtime_event(self, component, event, detail="", level="info"):
        return True


class _ImmediateTrader:
    def __init__(self, order_id: str):
        self.order_id = order_id
        self._last_callback_data = {}
        self.active_orders = {}
        self.stats_lock = threading.Lock()
        self.stats = {}
        self.notifier = _SilentNotifier()
        self.is_connected = True

    def place_order_async(self, signal_data, callback):
        callback(self.order_id, None)


@pytest.mark.integration
@pytest.mark.db
def test_trading_engine_processes_stream_signal_and_trade_callback(monkeypatch):
    test_id = f"ITEST_{int(time.time() * 1000)}"
    stream_name = f"test_trading_signals_stream_{test_id}"
    consumer_group = f"test_trading_service_{test_id}"
    consumer_name = f"consumer_{test_id}"
    signal_id = f"{test_id}_SIGNAL"
    order_id = f"{test_id}_ORDER"
    trade_id = f"{test_id}_TRADE"

    monkeypatch.setattr(settings, "redis_message_mode", "stream")
    monkeypatch.setattr(settings, "redis_stream_name", stream_name)
    monkeypatch.setattr(settings, "redis_consumer_group", consumer_group)
    monkeypatch.setattr(settings, "redis_consumer_name", consumer_name)
    monkeypatch.setattr(
        "src.trading.runtime.engine.sync_account_positions_from_qmt",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "src.trading.execution.qmt_trader.sync_account_positions_from_qmt",
        lambda *args, **kwargs: None,
    )

    redis_client = redis.Redis(**build_redis_client_kwargs(decode_responses=True))
    engine = TradingEngine()
    engine.notifier = _SilentNotifier()
    engine.trader = _ImmediateTrader(order_id=order_id)

    listener = RedisSignalListener(engine._handle_trading_signal)
    listener.connect()
    listener.is_running = True

    signal_payload = {
        "signal_id": signal_id,
        "stock_code": "000001.SZ",
        "direction": "BUY",
        "volume": 100,
        "price": 12.34,
    }
    redis_client.xadd(stream_name, {"data": json.dumps(signal_payload, ensure_ascii=False)})

    try:
        listener.check_messages()

        with SessionLocal() as db:
            signal_record = (
                db.query(TradingSignal).filter(TradingSignal.signal_id == signal_id).first()
            )
            order_record = db.query(OrderRecord).filter(OrderRecord.order_id == order_id).first()

            assert signal_record is not None
            assert signal_record.processed is True
            assert signal_record.error_message is None
            assert order_record is not None
            assert order_record.signal_id == signal_id
            assert order_record.order_status == "PENDING"
            assert order_record.filled_volume == 0

        callback = QMTCallback(engine.trader)
        trade = SimpleNamespace(
            account_id="TEST_ACCOUNT",
            stock_code="000001.SZ",
            order_id=order_id,
            traded_volume=100,
            traded_price=12.34,
            trade_id=trade_id,
            traded_time="20260408 14:30:15",
            order_type=23,
            order_remark="integration-test",
        )
        callback._on_stock_trade_impl(trade)

        with SessionLocal() as db:
            updated_order = db.query(OrderRecord).filter(OrderRecord.order_id == order_id).first()
            trade_execution = (
                db.query(TradeExecution)
                .filter(TradeExecution.broker_trade_id == trade_id)
                .first()
            )

            assert updated_order is not None
            assert updated_order.filled_volume == 100
            assert updated_order.filled_price == pytest.approx(12.34)
            assert updated_order.fill_notified is True
            assert updated_order.trade_amount is not None
            assert trade_execution is not None
            assert trade_execution.broker_order_id == order_id
            assert trade_execution.stock_code == "000001.SZ"
            assert trade_execution.filled_volume == 100

    finally:
        listener.stop()
        try:
            redis_client.delete(stream_name)
        except Exception:
            pass
        with SessionLocal() as db:
            db.query(TradeExecution).filter(TradeExecution.broker_trade_id == trade_id).delete()
            db.query(OrderRecord).filter(OrderRecord.signal_id == signal_id).delete()
            db.query(TradingSignal).filter(TradingSignal.signal_id == signal_id).delete()
            db.commit()
