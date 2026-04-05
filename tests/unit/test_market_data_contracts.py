import pytest

from src.strategy.t0.contracts.market_data import MarketDataProvider, MarketSnapshot


@pytest.mark.unit
def test_market_snapshot_to_dict_fields_complete():
    snapshot = MarketSnapshot(
        symbol="000001.SZ",
        trade_date="2026-04-04",
        bar_time="10:15:00",
        last_price=12.34,
        day_open=12.10,
        day_high=12.50,
        day_low=12.00,
        vwap=12.28,
        volume=123400,
        amount=1516552.0,
        previous_close=12.05,
    )

    assert snapshot.to_dict() == {
        "symbol": "000001.SZ",
        "trade_date": "2026-04-04",
        "bar_time": "10:15:00",
        "last_price": 12.34,
        "day_open": 12.10,
        "day_high": 12.50,
        "day_low": 12.00,
        "vwap": 12.28,
        "volume": 123400,
        "amount": 1516552.0,
        "previous_close": 12.05,
    }


@pytest.mark.unit
def test_market_snapshot_to_dict_keeps_optional_none():
    snapshot = MarketSnapshot(
        symbol="000001.SZ",
        trade_date="2026-04-04",
        bar_time="10:16:00",
        last_price=12.35,
        day_open=12.10,
        day_high=12.50,
        day_low=12.00,
        vwap=12.29,
        volume=123500,
        amount=1517790.0,
        previous_close=None,
    )

    payload = snapshot.to_dict()
    assert "previous_close" in payload
    assert payload["previous_close"] is None


@pytest.mark.unit
def test_market_data_provider_protocol_runtime_check():
    class StubProvider:
        def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
            return MarketSnapshot(
                symbol=symbol,
                trade_date="2026-04-04",
                bar_time="10:17:00",
                last_price=12.36,
                day_open=12.10,
                day_high=12.50,
                day_low=12.00,
                vwap=12.30,
                volume=123600,
                amount=1519028.0,
                previous_close=12.05,
            )

    provider = StubProvider()

    assert isinstance(provider, MarketDataProvider)
    assert provider.get_market_snapshot("000001.SZ").symbol == "000001.SZ"
