from pathlib import Path

import pandas as pd

from src.backtest.data_loader import BacktestDataLoader


def test_data_loader_normalizes_csv_market_data(tmp_path: Path):
    file_path = tmp_path / "minute.csv"
    pd.DataFrame(
        {
            "datetime": ["2026-03-26 09:30:00", "2026-03-26 09:31:00"],
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [1000, 1200],
        }
    ).to_csv(file_path, index=False)

    df = BacktestDataLoader().load_minute_data(file_path)

    assert list(df.columns) == ["open", "high", "low", "close", "volume", "amount", "pre_close"]
    assert df.index.name == "datetime"
    assert str(df.index.tz) == "Asia/Shanghai"
    assert float(df.iloc[0]["pre_close"]) == 10.0


def test_data_loader_filters_symbol_from_parquet_and_directory(tmp_path: Path):
    file_path = tmp_path / "601138.SH_minute.parquet"
    pd.DataFrame(
        {
            "timestamp": ["2026-03-26 09:30:00", "2026-03-26 09:31:00"],
            "symbol": ["601138.SH", "000001.SZ"],
            "open": [10.0, 20.0],
            "high": [10.2, 20.2],
            "low": [9.9, 19.9],
            "close": [10.1, 20.1],
            "volume": [1000, 2000],
            "amount": [10100, 40200],
            "pre_close": [10.0, 20.0],
        }
    ).to_parquet(file_path, index=False)

    loader = BacktestDataLoader()
    resolved = loader.resolve_data_path(tmp_path, symbol="601138.SH")
    df = loader.load_minute_data(resolved, symbol="601138.SH")

    assert resolved == file_path
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "601138.SH"


def test_data_loader_supports_datetime_index_and_date_filter(tmp_path: Path):
    file_path = tmp_path / "daily.parquet"
    frame = pd.DataFrame(
        {
            "open": [10.0, 10.1, 10.2],
            "high": [10.2, 10.3, 10.4],
            "low": [9.9, 10.0, 10.1],
            "close": [10.1, 10.2, 10.3],
            "volume": [1000, 1100, 1200],
        },
        index=pd.to_datetime(["2026-03-24", "2026-03-25", "2026-03-26"]),
    )
    frame.to_parquet(file_path)

    df = BacktestDataLoader().load_daily_data(
        file_path,
        start="2026-03-25 00:00:00",
        end="2026-03-26 23:59:59",
    )

    assert len(df) == 2
    assert float(df.iloc[0]["open"]) == 10.1


def test_align_minute_pre_close_uses_daily_data(tmp_path: Path):
    loader = BacktestDataLoader()
    minute_file = tmp_path / "minute.csv"
    daily_file = tmp_path / "daily.csv"

    pd.DataFrame(
        {
            "datetime": ["2026-03-26 09:30:00", "2026-03-26 09:31:00"],
            "open": [10.0, 10.1],
            "high": [10.2, 10.3],
            "low": [9.9, 10.0],
            "close": [10.1, 10.2],
            "volume": [1000, 1200],
        }
    ).to_csv(minute_file, index=False)

    pd.DataFrame(
        {
            "datetime": ["2026-03-25", "2026-03-26"],
            "open": [9.8, 10.0],
            "high": [10.0, 10.4],
            "low": [9.7, 9.9],
            "close": [9.9, 10.2],
            "volume": [10000, 11000],
            "pre_close": [9.7, 9.9],
        }
    ).to_csv(daily_file, index=False)

    minute_df = loader.load_minute_data(minute_file)
    daily_df = loader.load_daily_data(daily_file)
    aligned = loader.align_minute_pre_close(minute_df, daily_df)

    assert float(aligned.iloc[0]["pre_close"]) == 9.9
