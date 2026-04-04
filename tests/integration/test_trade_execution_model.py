# tests/integration/test_trade_execution_model.py
import pytest
from datetime import datetime
from src.database import TradeExecution, OrderCancellation


@pytest.mark.integration
@pytest.mark.db
def test_trade_execution_insert_and_query(pg_session):
    exec_rec = TradeExecution(
        execution_uid="01JRF6Z0000000000000000001",
        broker_trade_id="BT001",
        broker_order_id="BO001",
        stock_code="000001.SZ",
        direction="BUY",
        filled_volume=100,
        filled_price=10.5,
        filled_amount=1050.0,
        filled_time=datetime(2026, 4, 4, 10, 0, 0),
        execution_source="qmt_trade_callback",
        dedupe_key="BT001:BO001:100:10.5",
    )
    pg_session.add(exec_rec)
    pg_session.commit()

    fetched = pg_session.query(TradeExecution).filter_by(broker_trade_id="BT001").first()
    assert fetched is not None
    assert fetched.filled_volume == 100
    assert fetched.direction == "BUY"


@pytest.mark.integration
@pytest.mark.db
def test_trade_execution_dedupe_key_unique(pg_session):
    from sqlalchemy.exc import IntegrityError

    first = TradeExecution(
        execution_uid="01JRF6Z0000000000000000002",
        broker_trade_id="BT002",
        stock_code="000001.SZ",
        direction="BUY",
        filled_volume=100,
        filled_price=10.5,
        filled_amount=1050.0,
        filled_time=datetime(2026, 4, 4, 10, 0, 0),
        execution_source="qmt_trade_callback",
        dedupe_key="UNIQUE_KEY_X",
    )
    duplicate = TradeExecution(
        execution_uid="01JRF6Z0000000000000000003",
        broker_trade_id="BT003",
        stock_code="000001.SZ",
        direction="BUY",
        filled_volume=100,
        filled_price=10.5,
        filled_amount=1050.0,
        filled_time=datetime(2026, 4, 4, 10, 0, 0),
        execution_source="qmt_trade_callback",
        dedupe_key="UNIQUE_KEY_X",
    )
    pg_session.add(first)
    pg_session.commit()
    pg_session.add(duplicate)
    with pytest.raises(IntegrityError):
        pg_session.commit()


@pytest.mark.integration
@pytest.mark.db
def test_order_cancellation_insert(pg_session):
    cancel = OrderCancellation(
        order_uid="01JRF6Z0000000000000000010",
        broker_order_id="BO010",
        stock_code="000001.SZ",
        cancelled_volume=100,
        cancel_time=datetime(2026, 4, 4, 14, 55, 0),
        cancel_reason="timeout",
    )
    pg_session.add(cancel)
    pg_session.commit()

    fetched = pg_session.query(OrderCancellation).filter_by(order_uid="01JRF6Z0000000000000000010").first()
    assert fetched is not None
    assert fetched.cancel_reason == "timeout"
