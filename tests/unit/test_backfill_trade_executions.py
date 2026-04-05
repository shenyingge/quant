# tests/unit/test_backfill_trade_executions.py
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_parse_trade_breakdown_json():
    from scripts.backfill_trade_executions import parse_trade_breakdown

    raw = json.dumps([
        {
            "trade_id": "TID001",
            "volume": 100,
            "price": 10.5,
            "filled_time": "2026-04-04T10:00:00",
            "source": "order_monitor",
        }
    ])
    legs = parse_trade_breakdown(raw)
    assert len(legs) == 1
    assert legs[0]["volume"] == 100
    assert legs[0]["trade_id"] == "TID001"


@pytest.mark.unit
def test_parse_trade_breakdown_returns_empty_for_invalid():
    from scripts.backfill_trade_executions import parse_trade_breakdown

    assert parse_trade_breakdown(None) == []
    assert parse_trade_breakdown("") == []
    assert parse_trade_breakdown("not-json") == []
