import pandas as pd

from src.strategy.data_fetcher import DataFetcher


def test_normalize_market_data_handles_xtdata_field_dict():
    fetcher = DataFetcher()
    stock_code = "601138.SH"
    timestamps = ["20260326093000", "20260326093100"]
    base_timestamp = int(
        pd.Timestamp("2026-03-26 09:30:00")
        .tz_localize("Asia/Shanghai")
        .tz_convert("UTC")
        .timestamp()
        * 1000
    )

    data = {
        "time": pd.DataFrame(
            [[base_timestamp, base_timestamp + 60000]], index=[stock_code], columns=timestamps
        ),
        "open": pd.DataFrame([[10.1, 10.2]], index=[stock_code], columns=timestamps),
        "high": pd.DataFrame([[10.3, 10.4]], index=[stock_code], columns=timestamps),
        "low": pd.DataFrame([[10.0, 10.1]], index=[stock_code], columns=timestamps),
        "close": pd.DataFrame([[10.2, 10.3]], index=[stock_code], columns=timestamps),
        "volume": pd.DataFrame([[1000, 1200]], index=[stock_code], columns=timestamps),
        "amount": pd.DataFrame([[10200, 12360]], index=[stock_code], columns=timestamps),
    }

    df = fetcher._normalize_market_data(data, stock_code)

    assert list(df.columns) == ["open", "high", "low", "close", "volume", "amount"]
    assert len(df) == 2
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index[0] == pd.Timestamp("2026-03-26 09:30:00")
    assert df.iloc[0]["close"] == 10.2
    assert df.iloc[1]["volume"] == 1200


def test_filter_minute_data_for_trade_date_rejects_stale_data():
    fetcher = DataFetcher()
    df = pd.DataFrame(
        {
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [100, 200],
        },
        index=pd.to_datetime(["2026-03-24 14:56:00", "2026-03-24 14:57:00"]),
    )

    filtered = fetcher._filter_minute_data_for_trade_date(df, pd.to_datetime("2026-03-26").date())

    assert filtered is None


def test_validate_minute_data_rejects_mixed_trade_dates():
    fetcher = DataFetcher()
    df = pd.DataFrame(
        {
            "open": [10.0] * 30,
            "high": [10.2] * 30,
            "low": [9.9] * 30,
            "close": [10.1] * 30,
            "volume": [100] * 30,
        },
        index=pd.to_datetime(["2026-03-26 09:30:00"] * 29 + ["2026-03-25 14:59:00"]),
    )

    valid, message = fetcher._validate_minute_data(df, pd.to_datetime("2026-03-26").date())

    assert not valid
    assert "非目标交易日" in message
