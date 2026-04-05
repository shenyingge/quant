"""Phase 3 Task 3: DataFetcher -> MarketDataProvider bridge tests.

TDD cycle: write failing tests first, then implement.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.strategy.data_fetcher import DataFetcher
from src.strategy.t0.contracts.market_data import MarketSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(stock_code: str = "601138.SH") -> MarketSnapshot:
    return MarketSnapshot(
        stock_code=stock_code,
        time="2026-04-05 10:00:00",
        price=10.25,
        high=10.50,
        low=10.10,
        open=10.15,
        amount=1_200_000.0,
        volume=50_000.0,
        pre_close=10.00,
        source="test_provider",
    )


def _make_provider(snapshot: MarketSnapshot | None) -> MagicMock:
    provider = MagicMock()
    provider.get_latest_snapshot.return_value = snapshot
    return provider


# ---------------------------------------------------------------------------
# Constructor compatibility tests
# ---------------------------------------------------------------------------

def test_default_constructor_has_no_provider():
    """DataFetcher() without market_data_provider stays backward-compatible."""
    fetcher = DataFetcher()
    assert fetcher.market_data_provider is None


def test_constructor_accepts_market_data_provider():
    """DataFetcher(market_data_provider=...) stores the provider."""
    provider = _make_provider(_make_snapshot())
    fetcher = DataFetcher(market_data_provider=provider)
    assert fetcher.market_data_provider is provider


# ---------------------------------------------------------------------------
# Provider-first logic in fetch_realtime_snapshot
# ---------------------------------------------------------------------------

def test_provider_snapshot_returned_as_dict():
    """When provider returns a MarketSnapshot, result is a compatible dict."""
    snap = _make_snapshot("601138.SH")
    provider = _make_provider(snap)
    fetcher = DataFetcher(market_data_provider=provider)

    result = fetcher.fetch_realtime_snapshot("601138.SH")

    assert isinstance(result, dict)

    # Must contain all legacy keys
    for key in ("time", "price", "high", "low", "open", "amount", "volume", "pre_close"):
        assert key in result, f"Missing key: {key}"

    assert result["price"] == 10.25
    assert result["high"] == 10.50
    assert result["low"] == 10.10
    assert result["open"] == 10.15
    assert result["amount"] == 1_200_000.0
    assert result["volume"] == 50_000.0
    assert result["pre_close"] == 10.00
    assert result["time"] == "2026-04-05 10:00:00"


def test_provider_called_with_correct_stock_code():
    """Provider.get_latest_snapshot is called with the requested stock_code."""
    snap = _make_snapshot("000001.SZ")
    provider = _make_provider(snap)
    fetcher = DataFetcher(market_data_provider=provider)

    fetcher.fetch_realtime_snapshot("000001.SZ")

    provider.get_latest_snapshot.assert_called_once_with("000001.SZ")


def test_provider_none_result_falls_back_to_xtdata():
    """When provider.get_latest_snapshot returns None, xtdata fallback is used."""
    provider = _make_provider(None)
    fetcher = DataFetcher(market_data_provider=provider)

    fake_xtdata = MagicMock()
    fake_xtdata.get_full_tick.return_value = {
        "601138.SH": {
            "time": 1_712_280_603_000,
            "lastPrice": 9.99,
            "high": 10.10,
            "low": 9.80,
            "open": 9.90,
            "amount": 500_000.0,
            "volume": 20_000.0,
            "lastClose": 9.85,
        }
    }
    fake_xtdata.get_full_tick.__module__ = "xtquant.xtdata"

    with patch("src.strategy.data_fetcher.xtdata", fake_xtdata):
        result = fetcher.fetch_realtime_snapshot("601138.SH")

    assert result is not None
    assert result["price"] == 9.99
    assert result["pre_close"] == 9.85


def test_no_provider_uses_xtdata_path():
    """DataFetcher without provider falls back directly to xtdata."""
    fetcher = DataFetcher()

    fake_xtdata = MagicMock()
    fake_xtdata.get_full_tick.return_value = {
        "601138.SH": {
            "time": 1_712_280_603_000,
            "lastPrice": 11.11,
            "high": 11.20,
            "low": 11.00,
            "open": 11.05,
            "amount": 300_000.0,
            "volume": 10_000.0,
            "lastClose": 11.00,
        }
    }

    with patch("src.strategy.data_fetcher.xtdata", fake_xtdata):
        result = fetcher.fetch_realtime_snapshot("601138.SH")

    assert result is not None
    assert result["price"] == 11.11


def test_provider_cache_bypassed_on_provider_result():
    """Provider path skips the internal time-based snapshot cache."""
    snap = _make_snapshot()
    provider = _make_provider(snap)
    fetcher = DataFetcher(market_data_provider=provider)

    # Pre-load a stale internal cache entry
    from datetime import datetime
    fetcher._snapshot_cache = {"price": 0.01}
    fetcher._snapshot_cache_time = datetime.now()

    result = fetcher.fetch_realtime_snapshot("601138.SH")

    # Must use provider result, not stale cache
    assert result["price"] == 10.25
