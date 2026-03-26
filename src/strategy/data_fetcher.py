"""数据获取模块 - 从QMT获取分钟和日线数据"""

import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.logger_config import logger

try:
    from xtquant import xtdata
except ImportError:
    logger.warning("xtquant未安装，数据获取功能将不可用")
    xtdata = None


class DataFetcher:
    """数据获取器"""

    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._daily_cache = {}

    def fetch_minute_data(
        self, stock_code: str, trade_date: date, retry: int = 3
    ) -> Optional[pd.DataFrame]:
        """获取分钟数据

        Args:
            stock_code: 股票代码
            trade_date: 交易日期
            retry: 重试次数

        Returns:
            分钟数据DataFrame或None
        """
        if xtdata is None:
            logger.error("xtdata未安装")
            return None

        for attempt in range(retry):
            try:
                # 使用count方式获取最近的分钟数据
                data = xtdata.get_market_data(
                    stock_list=[stock_code],
                    period="1m",
                    count=240,
                    dividend_type="front",
                )

                if data is None:
                    raise ValueError("数据为空")

                df = self._normalize_market_data(data, stock_code)

                if df is None or df.empty:
                    raise ValueError("数据为空")

                df = self._filter_minute_data_for_trade_date(df, trade_date)

                if df is None or df.empty:
                    df = self._fetch_minute_data_from_local_cache(stock_code, trade_date)

                if df is None or df.empty:
                    raise ValueError(f"未获取到 {trade_date} 的分钟数据")

                # 验证数据
                valid, msg = self._validate_minute_data(df, trade_date)
                if not valid:
                    raise ValueError(msg)

                logger.info(f"获取分钟数据成功: {stock_code}, {len(df)}条")
                return df

            except Exception as e:
                logger.warning(f"数据获取失败 (尝试 {attempt + 1}/{retry}): {e}")
                if attempt < retry - 1:
                    time.sleep(2**attempt)
                else:
                    logger.error("数据获取失败且无缓存")
                    return None

    def fetch_daily_data(
        self, stock_code: str, days: int = 100, retry: int = 3
    ) -> Optional[pd.DataFrame]:
        """获取日线数据

        Args:
            stock_code: 股票代码
            days: 获取天数
            retry: 重试次数

        Returns:
            日线数据DataFrame或None
        """
        # 检查内存缓存
        cache_key = f"{stock_code}_{days}"
        if cache_key in self._daily_cache:
            cached_time, cached_data = self._daily_cache[cache_key]
            if (datetime.now() - cached_time).seconds < 3600:
                logger.debug(f"使用内存缓存: {cache_key}")
                return cached_data

        if xtdata is None:
            logger.error("xtdata未安装")
            return None

        for attempt in range(retry):
            try:
                data = xtdata.get_market_data(
                    stock_list=[stock_code],
                    period="1d",
                    count=days,
                    dividend_type="front",
                )

                if data is None:
                    raise ValueError("数据为空")

                df = self._normalize_market_data(data, stock_code)

                if df is None or df.empty:
                    df = self._fetch_daily_data_from_local_cache(stock_code, days)

                if df is None or df.empty:
                    raise ValueError("数据为空")

                if len(df) < 20:
                    raise ValueError(f"数据不足: {len(df)}天")

                # 缓存到内存
                self._daily_cache[cache_key] = (datetime.now(), df)
                logger.info(f"获取日线数据成功: {stock_code}, {len(df)}天")
                return df

            except Exception as e:
                logger.warning(f"日线数据获取失败 (尝试 {attempt + 1}/{retry}): {e}")
                if attempt < retry - 1:
                    time.sleep(2**attempt)
                else:
                    logger.error("日线数据获取失败")
                    return None

    def fetch_realtime_snapshot(self, stock_code: str) -> Optional[dict]:
        """获取实时快照，用于补齐分钟K线滞后时的最新市场价格。"""
        if xtdata is None or not hasattr(xtdata, "get_full_tick"):
            return None

        try:
            snapshot_data = xtdata.get_full_tick([stock_code])
            if not isinstance(snapshot_data, dict):
                return None

            stock_snapshot = snapshot_data.get(stock_code)
            if not isinstance(stock_snapshot, dict):
                return None

            snapshot_time = stock_snapshot.get("time")
            if snapshot_time is not None:
                snapshot_time = self._convert_market_timestamp(pd.Series([snapshot_time]))[0]
                snapshot_time = snapshot_time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                snapshot_time = stock_snapshot.get("timetag")

            return {
                "time": snapshot_time,
                "price": stock_snapshot.get("lastPrice"),
                "high": stock_snapshot.get("high"),
                "low": stock_snapshot.get("low"),
                "open": stock_snapshot.get("open"),
                "pre_close": stock_snapshot.get("lastClose")
                or stock_snapshot.get("lastSettlementPrice"),
            }
        except Exception as e:
            logger.warning(f"获取实时快照失败: {e}")
            return None

    def _fetch_daily_data_from_local_cache(
        self, stock_code: str, days: int
    ) -> Optional[pd.DataFrame]:
        """从QMT本地缓存回退获取日线数据。"""
        if xtdata is None:
            return None

        try:
            end_date = date.today().strftime("%Y%m%d")
            start_date = (date.today() - pd.Timedelta(days=max(days * 2, 120))).strftime("%Y%m%d")

            xtdata.download_history_data(stock_code, "1d", start_date, end_date)
            data = xtdata.get_local_data(
                stock_list=[stock_code],
                period="1d",
                start_time=start_date,
                end_time=end_date,
            )
            df = self._normalize_market_data(data, stock_code)
            if df is not None and not df.empty:
                return df.tail(days)
        except Exception as e:
            logger.warning(f"本地缓存日线回退失败: {e}")

        return None

    def _fetch_minute_data_from_local_cache(
        self, stock_code: str, trade_date: date
    ) -> Optional[pd.DataFrame]:
        """从QMT本地缓存回退获取指定交易日分钟数据。"""
        if xtdata is None:
            return None

        trade_date_str = trade_date.strftime("%Y%m%d")

        try:
            xtdata.download_history_data(stock_code, "1m", trade_date_str, trade_date_str)
            data = xtdata.get_local_data(
                stock_list=[stock_code],
                period="1m",
                start_time=trade_date_str,
                end_time=trade_date_str,
            )
            df = self._normalize_market_data(data, stock_code)
            return self._filter_minute_data_for_trade_date(df, trade_date)
        except Exception as e:
            logger.warning(f"本地缓存分钟数据回退失败: {e}")
            return None

    def _normalize_market_data(self, data, stock_code: str) -> pd.DataFrame:
        """将xtdata返回结果转换为按时间索引的标准DataFrame。"""
        if isinstance(data, pd.DataFrame):
            return self._finalize_market_dataframe(data)

        if not isinstance(data, dict):
            raise ValueError(f"未知的数据格式: {type(data)}")

        if stock_code in data and isinstance(data[stock_code], pd.DataFrame):
            return self._finalize_market_dataframe(data[stock_code])

        normalized_fields = {}
        for field_name, field_value in data.items():
            if not isinstance(field_value, pd.DataFrame) or field_value.empty:
                continue

            if stock_code in field_value.index:
                series = field_value.loc[stock_code]
            elif stock_code in field_value.columns:
                series = field_value[stock_code]
            elif len(field_value.index) == 1:
                series = field_value.iloc[0]
            else:
                continue

            normalized_fields[field_name] = series

        if not normalized_fields:
            logger.error(f"无法识别xtdata返回结构, keys={list(data.keys())[:5]}")
            raise ValueError("未知的dict结构")

        df = pd.DataFrame(normalized_fields)
        if df.empty:
            return df

        if "time" in df.columns:
            time_values = df.pop("time")
            index = self._convert_market_timestamp(time_values)
        else:
            index = self._convert_market_timestamp(df.index)

        df.index = index
        return self._finalize_market_dataframe(df)

    def _finalize_market_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一整理市场数据DataFrame的时间索引和数值列。"""
        if df is None or df.empty:
            return df

        normalized = df.copy()

        if "time" in normalized.columns:
            time_values = normalized.pop("time")
            normalized.index = self._convert_market_timestamp(time_values)
        elif not isinstance(normalized.index, pd.DatetimeIndex):
            normalized.index = self._convert_market_timestamp(normalized.index)

        normalized.index.name = "datetime"
        normalized = normalized.sort_index()

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "preClose",
            "settelementPrice",
            "openInterest",
        ]
        for column in numeric_columns:
            if column in normalized.columns:
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

        return normalized

    def _convert_market_timestamp(self, values) -> pd.DatetimeIndex:
        """将QMT时间戳统一转换为北京时间的无时区时间索引。"""
        if pd.api.types.is_numeric_dtype(values):
            converted = pd.to_datetime(values, unit="ms", utc=True)
            if isinstance(converted, pd.Series):
                converted = converted.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
                return pd.DatetimeIndex(converted.to_numpy())

            return pd.DatetimeIndex(converted.tz_convert("Asia/Shanghai").tz_localize(None))

        return pd.DatetimeIndex(pd.to_datetime(values))

    def _filter_minute_data_for_trade_date(
        self, df: pd.DataFrame, trade_date: date
    ) -> Optional[pd.DataFrame]:
        """仅保留目标交易日的分钟数据，避免旧交易日数据混入实时卡片。"""
        if df is None or df.empty:
            return df

        filtered = df[df.index.date == trade_date].copy()
        if filtered.empty:
            logger.warning(
                f"分钟数据交易日不匹配: 期望={trade_date}, 实际范围={df.index.min()} ~ {df.index.max()}"
            )
            return None

        return filtered

    def _validate_minute_data(self, df: pd.DataFrame, trade_date: date) -> tuple[bool, str]:
        """验证分钟数据完整性"""
        if df is None or df.empty:
            return False, "数据为空"

        required = ["open", "high", "low", "close", "volume"]
        missing = [f for f in required if f not in df.columns]
        if missing:
            return False, f"缺少字段: {missing}"

        if any(index_date != trade_date for index_date in df.index.date):
            return False, f"存在非目标交易日数据: {trade_date}"

        if len(df) < 30:
            return False, f"数据点不足: {len(df)}"

        return True, "OK"

    def _load_cached_minute_data(self, stock_code: str, trade_date: date) -> Optional[pd.DataFrame]:
        """从缓存加载分钟数据"""
        cache_file = self.cache_dir / "minute_data" / f"{stock_code}_{trade_date}.parquet"
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                # 检查缓存是否过期(超过5分钟)
                if (
                    datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                ).seconds < 300:
                    return df
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}")
        return None
