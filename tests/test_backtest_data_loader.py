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
    assert float(df.iloc[0]["pre_close"]) == 10.1


def test_data_loader_filters_symbol_from_parquet(tmp_path: Path):
    file_path = tmp_path / "minute.parquet"
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

    df = BacktestDataLoader().load_minute_data(file_path, symbol="601138.SH")

    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "601138.SH"
