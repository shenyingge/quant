# tests/unit/test_attribution_service.py
"""
Unit tests for AttributionService.
Uses in-memory SQLite for speed — tests the attribution logic, not the DB driver.
"""
import pytest
from unittest.mock import MagicMock

from src.trading.attribution import AttributionService, build_dedupe_key


@pytest.mark.unit
def test_build_dedupe_key_uses_broker_trade_id_when_available():
    key = build_dedupe_key(
        broker_trade_id="BT123",
        broker_order_id="BO456",
        filled_volume=100,
        filled_price=10.5,
    )
    assert "BT123" in key
    assert len(key) > 5


@pytest.mark.unit
def test_build_dedupe_key_fallback_when_no_broker_trade_id():
    key = build_dedupe_key(
        broker_trade_id=None,
        broker_order_id="BO456",
        filled_volume=100,
        filled_price=10.5,
    )
    assert "BO456" in key


@pytest.mark.unit
def test_attribution_service_matches_by_broker_order_id():
    """
    If broker_order_id matches an existing OrderRecord.order_id,
    the TradeExecution should be linked to that order's order_uid.
    """
    mock_session = MagicMock()
    service = AttributionService(session=mock_session)

    # Simulate an existing order record with a known order_uid
    mock_order = MagicMock()
    mock_order.order_uid = "01ABCDEF0000000000000001"
    mock_order.order_id = "BO001"

    mock_session.query.return_value.filter.return_value.first.return_value = mock_order

    result_uid = service.resolve_order_uid(
        broker_order_id="BO001",
        submit_request_id=None,
    )

    assert result_uid == "01ABCDEF0000000000000001"


@pytest.mark.unit
def test_attribution_service_returns_none_when_no_match():
    """
    When no order matches, resolve_order_uid returns None,
    and the caller should create a synthetic order.
    """
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    service = AttributionService(session=mock_session)

    result_uid = service.resolve_order_uid(
        broker_order_id="UNKNOWN_999",
        submit_request_id=None,
    )

    assert result_uid is None


@pytest.mark.unit
def test_build_dedupe_key_is_deterministic():
    key1 = build_dedupe_key("BT123", "BO456", 100, 10.5)
    key2 = build_dedupe_key("BT123", "BO456", 100, 10.5)
    assert key1 == key2


@pytest.mark.unit
def test_attribution_service_matches_by_submit_request_id_when_broker_order_id_missing():
    """
    When broker_order_id is None, resolve_order_uid falls through to
    submit_request_id and returns the matching order_uid.
    """
    mock_session = MagicMock()
    service = AttributionService(session=mock_session)

    mock_order = MagicMock()
    mock_order.order_uid = "01ABCDEF0000000000000002"

    mock_session.query.return_value.filter.return_value.first.return_value = mock_order

    result_uid = service.resolve_order_uid(
        broker_order_id=None,
        submit_request_id="REQ001",
    )

    assert result_uid == "01ABCDEF0000000000000002"
