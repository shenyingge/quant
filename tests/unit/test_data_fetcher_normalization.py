from datetime import date, datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.strategy.data_fetcher import DataFetcher


def _build_minute_df(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [10.0] * len(index),
            "high": [10.2] * len(index),
            "low": [9.9] * len(index),
            "close": [10.1] * len(index),
            "volume": [100] * len(index),
        },
        index=index,
    )


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


def test_normalize_market_data_handles_xtdata_tick_structured_array():
    fetcher = DataFetcher(intraday_period="5s")
    stock_code = "601138.SH"
    base_timestamp = int(
        pd.Timestamp("2026-03-27 09:30:01")
        .tz_localize("Asia/Shanghai")
        .tz_convert("UTC")
        .timestamp()
        * 1000
    )
    tick_array = np.array(
        [
            (base_timestamp, 10.20, 10.00, 10.30, 9.90, 9.95, 10200.0, 1000.0),
            (base_timestamp + 3000, 10.25, 10.00, 10.35, 9.90, 9.95, 15375.0, 1500.0),
        ],
        dtype=[
            ("time", "i8"),
            ("lastPrice", "f8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("lastClose", "f8"),
            ("amount", "f8"),
            ("volume", "f8"),
        ],
    )

    df = fetcher._normalize_market_data({stock_code: tick_array}, stock_code)

    assert list(df.columns) == ["close", "open", "high", "low", "pre_close", "amount", "volume"]
    assert list(df.index) == [
        pd.Timestamp("2026-03-27 09:30:01"),
        pd.Timestamp("2026-03-27 09:30:04"),
    ]
    assert df.iloc[-1]["close"] == 10.25
    assert df.iloc[-1]["volume"] == 1500.0


def test_normalize_market_data_handles_xtdata_snapshot_dict():
    fetcher = DataFetcher()
    stock_code = "601138.SH"
    base_timestamp = int(
        pd.Timestamp("2026-03-27 09:30:01")
        .tz_localize("Asia/Shanghai")
        .tz_convert("UTC")
        .timestamp()
        * 1000
    )

    df = fetcher._normalize_market_data(
        {
            stock_code: {
                "time": base_timestamp,
                "lastPrice": 10.20,
                "open": 10.00,
                "high": 10.30,
                "low": 9.90,
                "lastClose": 9.95,
                "amount": 10200.0,
                "volume": 1000.0,
            }
        },
        stock_code,
    )

    assert len(df) == 1
    assert df.index[0] == pd.Timestamp("2026-03-27 09:30:01")
    assert df.iloc[0]["close"] == 10.20
    assert df.iloc[0]["pre_close"] == 9.95


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
    assert message != "OK"


def test_choose_preferred_minute_data_prefers_fresher_rows():
    fetcher = DataFetcher()
    older = _build_minute_df(pd.date_range("2026-03-27 09:30:00", periods=20, freq="min"))
    fresher = _build_minute_df(pd.date_range("2026-03-27 09:30:00", periods=21, freq="min"))

    chosen = fetcher._choose_preferred_minute_data(older, fresher)

    assert chosen is fresher


def test_validate_minute_data_accepts_sparse_current_day_before_signal_window():
    fetcher = DataFetcher()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 27)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 27, 9, 35, 0)

    df = _build_minute_df(pd.date_range("2026-03-27 09:30:00", periods=5, freq="min"))

    with (
        patch("src.strategy.data_fetcher.date", FixedDate),
        patch("src.strategy.data_fetcher.datetime", FixedDateTime),
    ):
        valid, message = fetcher._validate_minute_data(df, FixedDate.today())

    assert valid
    assert message == "OK"


def test_validate_minute_data_accepts_current_day_rows_after_first_signal_window():
    fetcher = DataFetcher()

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 27)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 27, 9, 56, 0)

    df = _build_minute_df(pd.date_range("2026-03-27 09:30:00", periods=21, freq="min"))

    with (
        patch("src.strategy.data_fetcher.date", FixedDate),
        patch("src.strategy.data_fetcher.datetime", FixedDateTime),
    ):
        valid, message = fetcher._validate_minute_data(df, FixedDate.today())

    assert valid
    assert message == "OK"


def test_aggregate_tick_data_supports_subminute_bars():
    fetcher = DataFetcher(intraday_period="15s")
    tick_df = pd.DataFrame(
        {
            "close": [10.00, 10.20, 10.10, 10.30],
            "volume": [100, 160, 220, 260],
            "amount": [1000, 1632, 2643, 3673],
            "pre_close": [9.95, 9.95, 9.95, 9.95],
        },
        index=pd.to_datetime(
            [
                "2026-03-27 09:30:01",
                "2026-03-27 09:30:05",
                "2026-03-27 09:30:14",
                "2026-03-27 09:30:16",
            ]
        ),
    )

    aggregated = fetcher._aggregate_intraday_bars(tick_df, source="tick")

    assert aggregated is not None
    assert list(aggregated.index) == [
        pd.Timestamp("2026-03-27 09:30:15"),
        pd.Timestamp("2026-03-27 09:30:30"),
    ]
    assert aggregated.iloc[0]["open"] == 10.00
    assert aggregated.iloc[0]["high"] == 10.20
    assert aggregated.iloc[0]["low"] == 10.00
    assert aggregated.iloc[0]["close"] == 10.10
    assert aggregated.iloc[0]["volume"] == 220
    assert aggregated.iloc[1]["open"] == 10.30
    assert aggregated.iloc[1]["close"] == 10.30
    assert aggregated.iloc[1]["volume"] == 40


@pytest.mark.parametrize(
    ("intraday_period", "expected_index"),
    [
        (
            "10s",
            [
                pd.Timestamp("2026-03-27 09:30:10"),
                pd.Timestamp("2026-03-27 09:30:20"),
            ],
        ),
        (
            "5s",
            [
                pd.Timestamp("2026-03-27 09:30:05"),
                pd.Timestamp("2026-03-27 09:30:15"),
                pd.Timestamp("2026-03-27 09:30:20"),
            ],
        ),
    ],
)
def test_aggregate_tick_data_supports_higher_frequency_bars(
    intraday_period: str, expected_index: list[pd.Timestamp]
):
    fetcher = DataFetcher(intraday_period=intraday_period)
    tick_df = pd.DataFrame(
        {
            "close": [10.00, 10.20, 10.10, 10.30],
            "volume": [100, 160, 220, 260],
            "amount": [1000, 1632, 2643, 3673],
        },
        index=pd.to_datetime(
            [
                "2026-03-27 09:30:01",
                "2026-03-27 09:30:05",
                "2026-03-27 09:30:14",
                "2026-03-27 09:30:16",
            ]
        ),
    )

    aggregated = fetcher._aggregate_intraday_bars(tick_df, source="tick")

    assert aggregated is not None
    assert list(aggregated.index) == expected_index
    assert aggregated["close"].iloc[-1] == 10.30
    assert aggregated["volume"].sum() == 260


def test_validate_minute_data_uses_subminute_row_requirement():
    fetcher = DataFetcher(intraday_period="15s")

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 27)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 27, 9, 56, 0)

    df = _build_minute_df(pd.date_range("2026-03-27 09:30:00", periods=60, freq="15s"))

    with (
        patch("src.strategy.data_fetcher.date", FixedDate),
        patch("src.strategy.data_fetcher.datetime", FixedDateTime),
    ):
        valid, message = fetcher._validate_minute_data(df, FixedDate.today())

    assert valid
    assert message == "OK"


@pytest.mark.parametrize(
    ("intraday_period", "rows"),
    [
        ("10s", 90),
        ("5s", 180),
    ],
)
def test_validate_minute_data_supports_higher_frequency_row_requirement(
    intraday_period: str, rows: int
):
    fetcher = DataFetcher(intraday_period=intraday_period)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 27)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 27, 9, 56, 0)

    df = _build_minute_df(pd.date_range("2026-03-27 09:30:00", periods=rows, freq=intraday_period))

    with (
        patch("src.strategy.data_fetcher.date", FixedDate),
        patch("src.strategy.data_fetcher.datetime", FixedDateTime),
    ):
        valid, message = fetcher._validate_minute_data(df, FixedDate.today())

    assert valid
    assert message == "OK"
