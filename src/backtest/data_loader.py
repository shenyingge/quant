"""Linux/Windows 可复用的回测行情数据加载与标准化入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd


class BacktestDataLoader:
    """读取 csv/parquet 并转换为策略统一格式。"""

    REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]
    OPTIONAL_COLUMNS = ["amount", "pre_close"]
    DATETIME_CANDIDATES = ["datetime", "timestamp", "time", "date", "day"]
    SYMBOL_CANDIDATES = ["symbol", "ts_code", "code"]
    COLUMN_ALIASES = {
        "时间": "datetime",
        "日期": "datetime",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "昨收": "pre_close",
        "昨收盘": "pre_close",
    }

    def resolve_data_path(
        self,
        path_or_dir: Union[str, Path],
        *,
        symbol: Optional[str] = None,
        dataset_kind: Optional[str] = None,
    ) -> Path:
        candidate = Path(path_or_dir)
        if candidate.is_file():
            return candidate
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        if not candidate.is_dir():
            raise ValueError(f"Unsupported data path: {candidate}")
        if not symbol:
            raise ValueError(f"Directory input requires symbol to resolve file: {candidate}")

        code = symbol.split(".", 1)[0]
        patterns = self._build_resolution_patterns(symbol=symbol, code=code, dataset_kind=dataset_kind)
        for pattern in patterns:
            matches = sorted(candidate.rglob(pattern))
            if matches:
                return matches[0]
        raise FileNotFoundError(f"No data file found for {symbol} under {candidate}")

    def load_minute_data(
        self,
        path: Union[str, Path],
        *,
        symbol: Optional[str] = None,
        timezone: str = "Asia/Shanghai",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self._load_file(path)
        return self._normalize_market_data(
            df,
            symbol=symbol,
            timezone=timezone,
            start=start,
            end=end,
        )

    def load_daily_data(
        self,
        path: Union[str, Path],
        *,
        symbol: Optional[str] = None,
        timezone: str = "Asia/Shanghai",
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self._load_file(path)
        return self._normalize_market_data(
            df,
            symbol=symbol,
            timezone=timezone,
            start=start,
            end=end,
        )

    def align_minute_pre_close(self, minute_data: pd.DataFrame, daily_data: pd.DataFrame) -> pd.DataFrame:
        """用日线 pre_close 修正分钟数据。"""
        if minute_data.empty or daily_data.empty:
            return minute_data

        working = minute_data.copy()
        daily_map = self._build_daily_pre_close_map(daily_data)
        trade_date = pd.Series(working.index.date, index=working.index).astype(str)
        mapped = trade_date.map(daily_map)
        if mapped.notna().any():
            working["pre_close"] = mapped.where(mapped.notna(), working["pre_close"])
        if working["pre_close"].isna().any():
            working["pre_close"] = working["pre_close"].ffill().fillna(working["open"])
        return working

    def _build_daily_pre_close_map(self, daily_data: pd.DataFrame) -> dict[str, float]:
        working = daily_data.copy()
        if not isinstance(working.index, pd.DatetimeIndex):
            raise ValueError("daily_data must have DatetimeIndex after normalization")
        return {
            str(idx.date()): float(value)
            for idx, value in working["pre_close"].items()
            if pd.notna(value)
        }

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
        *,
        symbol: Optional[str],
        timezone: str,
        start: Optional[str],
        end: Optional[str],
    ) -> pd.DataFrame:
        working = df.copy()
        working = self._rename_alias_columns(working)
        working = self._ensure_datetime_column(working)
        working = self._filter_symbol(working, symbol)

        working["datetime"] = pd.to_datetime(working["datetime"])
        datetime_series = working["datetime"]
        if getattr(datetime_series.dt, "tz", None) is None:
            working["datetime"] = datetime_series.dt.tz_localize(timezone)
        else:
            working["datetime"] = datetime_series.dt.tz_convert(timezone)

        working = working.set_index("datetime").sort_index()
        working = self._apply_time_filter(working, start=start, end=end)

        lowercase_map = {column: str(column).lower() for column in working.columns}
        working = working.rename(columns=lowercase_map)

        for column in self.REQUIRED_COLUMNS:
            if column not in working.columns:
                raise ValueError(f"Missing required column: {column}")

        if "amount" not in working.columns:
            working["amount"] = working["close"] * working["volume"]
        if "pre_close" not in working.columns:
            working["pre_close"] = working["close"].shift(1)
        if not working.empty:
            working.loc[working.index[0], "pre_close"] = working["pre_close"].iloc[0]
            if pd.isna(working["pre_close"].iloc[0]):
                working.loc[working.index[0], "pre_close"] = working["open"].iloc[0]
        working["pre_close"] = working["pre_close"].ffill().fillna(working["open"])

        keep_columns = self.REQUIRED_COLUMNS + self.OPTIONAL_COLUMNS
        if "symbol" in working.columns:
            keep_columns.append("symbol")
        normalized = working[keep_columns].copy()
        normalized.index.name = "datetime"
        return normalized

    def _rename_alias_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {}
        for column in df.columns:
            rename_map[column] = self.COLUMN_ALIASES.get(str(column), column)
        return df.rename(columns=rename_map)

    def _ensure_datetime_column(self, df: pd.DataFrame) -> pd.DataFrame:
        working = df.copy()
        if isinstance(working.index, pd.DatetimeIndex):
            working = working.reset_index()
            first_column = working.columns[0]
            return working.rename(columns={first_column: "datetime"})

        lower_map = {str(column).lower(): column for column in working.columns}
        for candidate in self.DATETIME_CANDIDATES:
            if candidate in lower_map:
                source_column = lower_map[candidate]
                if source_column != "datetime":
                    working = working.rename(columns={source_column: "datetime"})
                return working
        raise ValueError("Missing datetime column")

    def _filter_symbol(self, df: pd.DataFrame, symbol: Optional[str]) -> pd.DataFrame:
        if not symbol:
            return df

        working = df.copy()
        lower_map = {str(column).lower(): column for column in working.columns}
        for candidate in self.SYMBOL_CANDIDATES:
            if candidate not in lower_map:
                continue
            source_column = lower_map[candidate]
            normalized_symbol = str(symbol).upper()
            code = normalized_symbol.split(".", 1)[0]
            aliases = {
                normalized_symbol,
                normalized_symbol.lower(),
                code,
                code.lower(),
            }
            filtered = working.loc[working[source_column].astype(str).isin(aliases)].copy()
            if source_column != "symbol":
                filtered = filtered.rename(columns={source_column: "symbol"})
            return filtered
        return working

    def _apply_time_filter(
        self,
        df: pd.DataFrame,
        *,
        start: Optional[str],
        end: Optional[str],
    ) -> pd.DataFrame:
        working = df
        if start:
            start_ts = self._coerce_timestamp(start, working.index.tz)
            working = working.loc[working.index >= start_ts]
        if end:
            end_ts = self._coerce_timestamp(end, working.index.tz)
            working = working.loc[working.index <= end_ts]
        return working

    def _coerce_timestamp(self, value: str, tzinfo) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize(tzinfo)
        return timestamp.tz_convert(tzinfo)

    def _build_resolution_patterns(
        self,
        *,
        symbol: str,
        code: str,
        dataset_kind: Optional[str],
    ) -> list[str]:
        patterns: list[str] = []
        if dataset_kind:
            tags = [dataset_kind, dataset_kind.lower(), dataset_kind.upper()]
            for tag in tags:
                patterns.extend(
                    [
                        f"{symbol}_{tag}.parquet",
                        f"{symbol}_{tag}.csv",
                        f"{code}_{tag}.parquet",
                        f"{code}_{tag}.csv",
                        f"*{symbol}*{tag}*.parquet",
                        f"*{symbol}*{tag}*.csv",
                        f"*{code}*{tag}*.parquet",
                        f"*{code}*{tag}*.csv",
                    ]
                )
        patterns.extend(
            [
                f"{symbol}.parquet",
                f"{symbol}.csv",
                f"{code}.parquet",
                f"{code}.csv",
                f"*{symbol}*.parquet",
                f"*{symbol}*.csv",
                f"*{code}*.parquet",
                f"*{code}*.csv",
            ]
        )
        return patterns
