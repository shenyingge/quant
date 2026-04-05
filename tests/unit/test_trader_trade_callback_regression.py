# tests/unit/test_trader_trade_callback_regression.py
"""
Regression tests: on_stock_trade must still update OrderRecord fields
AND now also call AttributionService.record_execution().
"""
import threading
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_on_stock_trade_calls_attribution_service(monkeypatch):
    """
    When _on_stock_trade_impl runs, it must call
    AttributionService.record_execution() with the correct args.
    """
    recorded_calls = []

    def fake_record_execution(**kwargs):
        recorded_calls.append(kwargs)
        return MagicMock()

    mock_service_instance = MagicMock()
    mock_service_instance.record_execution.side_effect = fake_record_execution

    # Mock out settings.t0_stock_code so PositionSyncer branch is skipped
    monkeypatch.setattr("src.config.settings.t0_stock_code", "NOMATCH.XX", raising=False)

    mock_order_record = MagicMock(
        order_id="BO001",
        order_uid="01TESTULID00000000000001",
        filled_volume=0,
        volume=100,
        fill_notified=False,
        price=10.0,
        stock_code="000001.SZ",
        direction="BUY",
        commission=None,
        transfer_fee=None,
        stamp_duty=None,
        total_fee=None,
    )

    mock_trader = MagicMock()
    mock_trader._last_callback_data = {}
    mock_trader.active_orders = {}
    mock_trader.order_lock = threading.Lock()
    mock_trader.stats_lock = threading.Lock()
    mock_trader.stats = {}
    mock_trader.notifier = MagicMock()

    with patch("src.trading.execution.qmt_trader.AttributionService", return_value=mock_service_instance):
        with patch("src.trading.execution.qmt_trader.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.__enter__ = lambda s: s
            mock_db.__exit__ = MagicMock(return_value=False)

            with patch("src.trading.execution.qmt_trader.sync_account_positions_from_qmt"):
                from src.trading.execution.qmt_trader import QMTCallback, TradingFeeSchedule

                with patch.object(TradingFeeSchedule, "from_settings", return_value=MagicMock()):
                    callback = QMTCallback.__new__(QMTCallback)
                    callback.trader = mock_trader
                    callback.fee_schedule = MagicMock()

                    # Patch the helper methods that touch the DB
                    callback._load_order_record_for_trade = MagicMock(
                        return_value=mock_order_record
                    )
                    callback._apply_trade_fill_to_order_record = MagicMock()
                    callback._apply_trade_costs_to_order_record = MagicMock()

                    trade = MagicMock()
                    trade.stock_code = "000001.SZ"
                    trade.order_id = "BO001"
                    trade.traded_volume = 100
                    trade.traded_price = 10.5
                    trade.trade_id = "TID001"
                    trade.order_status = 56  # ORDER_SUCCEEDED
                    trade.traded_time = datetime(2026, 4, 4, 10, 30, 0)

                    callback._on_stock_trade_impl(trade)

    assert len(recorded_calls) == 1, (
        f"Expected AttributionService.record_execution to be called once, "
        f"but got {len(recorded_calls)} calls. "
        f"Make sure AttributionService is imported and called in _on_stock_trade_impl."
    )
    assert recorded_calls[0]["broker_trade_id"] == "TID001"
    assert recorded_calls[0]["broker_order_id"] == "BO001"
    assert recorded_calls[0]["filled_volume"] == 100
    assert recorded_calls[0]["filled_time"] == datetime(2026, 4, 4, 10, 30, 0)


@pytest.mark.unit
def test_on_stock_trade_attribution_failure_does_not_crash_callback(monkeypatch):
    """
    If AttributionService.record_execution raises, the exception must be
    swallowed — the main db.commit() and notification flow must still proceed.
    """
    mock_service_instance = MagicMock()
    mock_service_instance.record_execution.side_effect = RuntimeError("DB error")

    monkeypatch.setattr("src.config.settings.t0_stock_code", "NOMATCH.XX", raising=False)

    mock_order_record = MagicMock(
        order_id="BO001",
        order_uid="01TESTULID00000000000001",
        filled_volume=0,
        volume=100,
        fill_notified=False,
        price=10.0,
        stock_code="000001.SZ",
        direction="BUY",
        commission=None,
        transfer_fee=None,
        stamp_duty=None,
        total_fee=None,
    )

    mock_trader = MagicMock()
    mock_trader._last_callback_data = {}
    mock_trader.active_orders = {}
    mock_trader.order_lock = threading.Lock()
    mock_trader.stats_lock = threading.Lock()
    mock_trader.stats = {}
    mock_trader.notifier = MagicMock()

    with patch("src.trading.execution.qmt_trader.AttributionService", return_value=mock_service_instance):
        with patch("src.trading.execution.qmt_trader.SessionLocal") as mock_session_cls:
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_db.__enter__ = lambda s: s
            mock_db.__exit__ = MagicMock(return_value=False)

            with patch("src.trading.execution.qmt_trader.sync_account_positions_from_qmt"):
                from src.trading.execution.qmt_trader import QMTCallback, TradingFeeSchedule

                with patch.object(TradingFeeSchedule, "from_settings", return_value=MagicMock()):
                    callback = QMTCallback.__new__(QMTCallback)
                    callback.trader = mock_trader
                    callback.fee_schedule = MagicMock()

                    callback._load_order_record_for_trade = MagicMock(
                        return_value=mock_order_record
                    )
                    callback._apply_trade_fill_to_order_record = MagicMock()
                    callback._apply_trade_costs_to_order_record = MagicMock()

                    trade = MagicMock()
                    trade.stock_code = "000001.SZ"
                    trade.order_id = "BO001"
                    trade.traded_volume = 100
                    trade.traded_price = 10.5
                    trade.trade_id = "TID001"
                    trade.order_status = 56
                    trade.traded_time = datetime(2026, 4, 4, 10, 30, 0)

                    # Should not raise even though record_execution raises
                    callback._on_stock_trade_impl(trade)

    # Main flow still committed despite attribution failure
    mock_db.commit.assert_called()
