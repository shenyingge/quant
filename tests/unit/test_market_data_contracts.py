from dataclasses import asdict

from src.strategy.t0.contracts.market_data import MarketSnapshot


def test_market_snapshot_to_dict_fields_complete():
    snapshot = MarketSnapshot(
        stock_code="601138.SH",
        time="2026-04-05 09:30:03",
        price=10.23,
        high=10.30,
        low=10.10,
        open=10.15,
        amount=120000.0,
        volume=3500.0,
        pre_close=10.00,
        source="qmt_snapshot",
    )

    payload = asdict(snapshot)

    assert payload["stock_code"] == "601138.SH"
    assert payload["price"] == 10.23
    assert payload["source"] == "qmt_snapshot"
    assert sorted(payload.keys()) == sorted(
        [
            "stock_code",
            "time",
            "price",
            "high",
            "low",
            "open",
            "amount",
            "volume",
            "pre_close",
            "source",
        ]
    )
