"""Linux 可复用的行情数据加载与标准化入口。"""

from pathlib import Path
from typing import Iterable, Optional, Union

import pandas as pd


class BacktestDataLoader:
    """读取 csv/parquet 并转换为策略统一格式。"""

    REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]
    OPTIONAL_COLUMNS = ["amount", "pre_close"]
    DATETIME_CANDIDATES = ["datetime", "timestamp", "time", "date"]

    def load_minute_data(
        self,
        path: Union[str, Path],
        symbol: Optional[str] = None,
        timezone: str = "Asia/Shanghai",
    ) -> pd.DataFrame:
        df = self._load_file(path)
        return self._normalize_market_data(df, symbol=symbol, timezone=timezone)

    def load_daily_data(
        self,
        path: Union[str, Path],
        symbol: Optional[str] = None,
        timezone: str = "Asia/Shanghai",
    ) -> pd.DataFrame:
        df = self._load_file(path)
        return self._normalize_market_data(df, symbol=symbol, timezone=timezone)

    def split_by_trade_date(self, df: pd.DataFrame) -> Iterable[pd.DataFrame]:
        if df.empty:
            return []
        return [group.copy() for _, group in df.groupby(df.index.date)]

    def _load_file(self, path: Union[str, Path]) -> pd.DataFrame:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(file_path)
        if suffix in {".parquet", ".pq"}:
            return pd.read_parquet(file_path)

        raise ValueError(f"Unsupported file type: {suffix}")

    def _normalize_market_data(
        self,
        df: pd.DataFrame,
        symbol: Optional[str],
        timezone: str,
    ) -> pd.DataFrame:
        working = df.copy()

        if symbol and "symbol" in working.columns:
            working = working[working["symbol"] == symbol].copy()

        datetime_column = self._find_datetime_column(working)
        if datetime_column is None:
            raise ValueError("Missing datetime column")

        working[datetime_column] = pd.to_datetime(working[datetime_column])
        if getattr(working[datetime_column].dt, "tz", None) is None:
            working[datetime_column] = working[datetime_column].dt.tz_localize(timezone)
        else:
            working[datetime_column] = working[datetime_column].dt.tz_convert(timezone)
        working = working.set_index(datetime_column).sort_index()

        lowercase_map = {column: column.lower() for column in working.columns}
        working = working.rename(columns=lowercase_map)

        for column in self.REQUIRED_COLUMNS:
            if column not in working.columns:
                raise ValueError(f"Missing required column: {column}")

        if "amount" not in working.columns:
            working["amount"] = working["close"] * working["volume"]
        if "pre_close" not in working.columns:
            working["pre_close"] = working["close"].shift(1)
            if not working.empty:
                first_close = working["close"].iloc[0]
                working.loc[working.index[0], "pre_close"] = first_close

        keep_columns = self.REQUIRED_COLUMNS + self.OPTIONAL_COLUMNS
        if "symbol" in working.columns:
            keep_columns.append("symbol")
        normalized = working[keep_columns].copy()
        normalized.index.name = "datetime"
        return normalized

    def _find_datetime_column(self, df: pd.DataFrame) -> Optional[str]:
        lower_map = {column.lower(): column for column in df.columns}
        for candidate in self.DATETIME_CANDIDATES:
            if candidate in lower_map:
                return lower_map[candidate]
        return None
