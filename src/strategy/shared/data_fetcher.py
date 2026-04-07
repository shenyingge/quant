"""Data fetching for T+0 strategy intraday and daily inputs."""

import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.market_data.ingestion.market_data_gateway import NullMarketDataGateway
from src.strategy.shared.tick_cache import RedisTickCache

xtdata = None


class DataFetcher:
    """Fetches intraday bars, daily bars, and realtime snapshots."""

    _PERIOD_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[sm])$", re.IGNORECASE)

    def __init__(
        self,
        cache_dir: str = "./cache",
        intraday_period: Optional[str] = None,
        market_data_provider=None,
        market_data_gateway=None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._daily_cache = {}
        self._snapshot_cache = None
        self._snapshot_cache_time = None
        self.tick_cache = RedisTickCache()
        self.market_data_provider = market_data_provider
        self.market_data_gateway = market_data_gateway or NullMarketDataGateway()
        raw_period = intraday_period or getattr(settings, "t0_intraday_bar_period", "1m")
        self.intraday_period = self._normalize_intraday_period(raw_period)
        self.intraday_period_seconds = self._period_to_seconds(self.intraday_period)

    def fetch_minute_data(
        self, stock_code: str, trade_date: date, retry: int = 3, realtime: bool = False,
        snapshot: Optional[dict] = None,
    ) -> Optional[pd.DataFrame]:
        """Fetches the configured intraday bars for one trade date."""
        if self.market_data_gateway is None:
            logger.error("xtdata未安装")
            return None

        for attempt in range(retry):
            try:
                if not realtime:
                    local_df = self._fetch_minute_data_from_local_cache(stock_code, trade_date)
                else:
                    local_df = None

                market_df = self._fetch_recent_minute_data(stock_code, trade_date)
                if realtime and (market_df is None or market_df.empty):
                    logger.warning(
                        "Realtime intraday source unavailable, falling back to local QMT cache: {} {}",
                        stock_code,
                        trade_date,
                    )
                    local_df = self._fetch_minute_data_from_local_cache(stock_code, trade_date)
                df = self._choose_preferred_minute_data(local_df, market_df)

                if df is None or df.empty:
                    raise ValueError(f"未获取到 {trade_date} 的日内数据")

                snapshot = snapshot or self.fetch_realtime_snapshot(stock_code)
                self._warn_if_minute_data_is_stale(df, stock_code, trade_date, snapshot)

                valid, msg = self._validate_minute_data(df, trade_date)
                if not valid:
                    raise ValueError(msg)

                logger.debug(
                    "获取日内数据成功: {}, period={}, rows={}",
                    stock_code,
                    self.intraday_period,
                    len(df),
                )
                return df

            except Exception as e:
                logger.warning(f"数据获取失败 (尝试 {attempt + 1}/{retry}): {e}")
                if attempt < retry - 1:
                    time.sleep(2**attempt)
                else:
                    logger.error("数据获取失败且无缓存")
                    return None

        return None

    def _fetch_recent_minute_data(
        self, stock_code: str, trade_date: date
    ) -> Optional[pd.DataFrame]:
        """Reads recent live intraday data and converts it to the configured bar period."""
        if self._uses_tick_source():
            tick_df = self._fetch_recent_tick_data(stock_code, trade_date)
            if tick_df is not None and not tick_df.empty:
                return self._aggregate_intraday_bars(tick_df, source="tick")

            logger.warning(
                "tick行情不可用，回退到1分钟K线: stock=%s period=%s",
                stock_code,
                self.intraday_period,
            )

        base_df = self._fetch_recent_base_minute_data(stock_code, trade_date)
        return self._aggregate_intraday_bars(base_df, source="minute")

    def _fetch_recent_base_minute_data(
        self, stock_code: str, trade_date: date
    ) -> Optional[pd.DataFrame]:
        """Reads 1m bars from xtdata recent window and filters to one trade date."""
        data = self.market_data_gateway.fetch_market_data(
            stock_list=[stock_code],
            period="1m",
            count=self._estimate_recent_minute_count(),
            dividend_type="front",
        )

        if data is None:
            return None

        df = self._normalize_market_data(data, stock_code)
        if df is None or df.empty:
            return None

        return self._filter_minute_data_for_trade_date(df, trade_date)

    def _fetch_recent_tick_data(self, stock_code: str, trade_date: date) -> Optional[pd.DataFrame]:
        """Reads recent tick data when sub-minute bars are requested."""
        cached_df = self.tick_cache.get_cached_ticks(stock_code, trade_date)

        if cached_df is not None and not cached_df.empty:
            last_tick_time = cached_df.index.max()
            try:
                data = self.market_data_gateway.fetch_market_data(
                    stock_list=[stock_code],
                    period="tick",
                    count=500,
                    dividend_type="front",
                )
            except Exception as exc:
                logger.warning(f"增量tick拉取失败: {exc}")
                return self._refresh_ticks_from_fallbacks(stock_code, trade_date, cached_df)

            if data is None:
                return self._refresh_ticks_from_fallbacks(stock_code, trade_date, cached_df)

            new_df = self._normalize_market_data(data, stock_code)
            if new_df is None or new_df.empty:
                return self._refresh_ticks_from_fallbacks(stock_code, trade_date, cached_df)

            new_df = self._filter_minute_data_for_trade_date(new_df, trade_date)
            if new_df is None or new_df.empty:
                return self._refresh_ticks_from_fallbacks(stock_code, trade_date, cached_df)

            new_ticks = new_df[new_df.index > last_tick_time]
            if not new_ticks.empty:
                combined_df = pd.concat([cached_df, new_ticks]).drop_duplicates()
                combined_df = combined_df.sort_index()
                combined_df = self._append_snapshot_tick(combined_df, stock_code, trade_date)
                if combined_df is not None and not combined_df.empty:
                    self.tick_cache.save_ticks(stock_code, trade_date, combined_df)
                    logger.info(f"增量tick更新: 新增{len(new_ticks)}条, 总计{len(combined_df)}条")
                return combined_df

            refreshed_df = self._append_snapshot_tick(cached_df, stock_code, trade_date)
            if refreshed_df is not None and not refreshed_df.empty:
                self.tick_cache.save_ticks(stock_code, trade_date, refreshed_df)
            return refreshed_df

        try:
            data = self.market_data_gateway.fetch_market_data(
                stock_list=[stock_code],
                period="tick",
                count=self._estimate_recent_tick_count(),
                dividend_type="front",
            )
        except Exception as exc:
            logger.warning(f"实时tick拉取失败: {exc}")
            return self._refresh_ticks_from_fallbacks(stock_code, trade_date, None)

        if data is None:
            return self._refresh_ticks_from_fallbacks(stock_code, trade_date, None)

        df = self._normalize_market_data(data, stock_code)
        if df is None or df.empty:
            return self._refresh_ticks_from_fallbacks(stock_code, trade_date, None)

        df = self._filter_minute_data_for_trade_date(df, trade_date)
        if df is None or df.empty:
            return self._refresh_ticks_from_fallbacks(stock_code, trade_date, None)

        df = self._append_snapshot_tick(df, stock_code, trade_date)
        if df is not None and not df.empty:
            self.tick_cache.save_ticks(stock_code, trade_date, df)

        return df

    def _choose_preferred_minute_data(
        self, *candidates: Optional[pd.DataFrame]
    ) -> Optional[pd.DataFrame]:
        """Chooses the freshest non-empty candidate."""
        available = [
            candidate for candidate in candidates if candidate is not None and not candidate.empty
        ]
        if not available:
            return None

        return max(available, key=lambda df: (df.index.max(), len(df)))

    def fetch_daily_data(
        self, stock_code: str, days: int = 100, retry: int = 3
    ) -> Optional[pd.DataFrame]:
        """Fetches daily data."""
        cache_key = f"{stock_code}_{days}"
        if cache_key in self._daily_cache:
            cached_time, cached_data = self._daily_cache[cache_key]
            if (datetime.now() - cached_time).seconds < 3600:
                logger.debug(f"使用内存缓存: {cache_key}")
                return cached_data

        if self.market_data_gateway is None:
            logger.error("xtdata未安装")
            return None

        for attempt in range(retry):
            try:
                data = self.market_data_gateway.fetch_market_data(
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

                self._daily_cache[cache_key] = (datetime.now(), df)
                logger.debug(f"获取日线数据成功: {stock_code}, {len(df)}天")
                return df

            except Exception as e:
                logger.warning(f"日线数据获取失败 (尝试 {attempt + 1}/{retry}): {e}")
                if attempt < retry - 1:
                    time.sleep(2**attempt)
                else:
                    logger.error("日线数据获取失败")
                    return None

        return None

    def fetch_realtime_snapshot(self, stock_code: str) -> Optional[dict]:
        """Fetches the latest tick snapshot.

        Provider-first: if a MarketDataProvider is attached, query it first.
        Falls back to xtdata when the provider is absent or returns None.
        """
        if self.market_data_provider is not None:
            snap = self.market_data_provider.get_latest_snapshot(stock_code)
            if snap is not None:
                return {
                    "time": snap.time,
                    "price": snap.price,
                    "high": snap.high,
                    "low": snap.low,
                    "open": snap.open,
                    "amount": snap.amount,
                    "volume": snap.volume,
                    "pre_close": snap.pre_close,
                }

        if self._snapshot_cache is not None and self._snapshot_cache_time is not None:
            elapsed = (datetime.now() - self._snapshot_cache_time).total_seconds()
            if elapsed < settings.t0_poll_interval_seconds:
                return self._snapshot_cache

        if self.market_data_gateway is None:
            return None

        try:
            snapshot_data = self.market_data_gateway.fetch_full_tick([stock_code])
            if snapshot_data is None and xtdata is not None:
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

            result = {
                "time": snapshot_time,
                "price": stock_snapshot.get("lastPrice"),
                "high": stock_snapshot.get("high"),
                "low": stock_snapshot.get("low"),
                "open": stock_snapshot.get("open"),
                "amount": stock_snapshot.get("amount"),
                "volume": stock_snapshot.get("volume"),
                "pre_close": stock_snapshot.get("lastClose")
                or stock_snapshot.get("lastSettlementPrice"),
            }
            self._snapshot_cache = result
            self._snapshot_cache_time = datetime.now()
            return result
        except Exception as e:
            logger.warning(f"获取实时快照失败: {e}")
            return None

    def _fetch_daily_data_from_local_cache(
        self, stock_code: str, days: int
    ) -> Optional[pd.DataFrame]:
        """Reads daily data from local QMT cache as fallback."""
        if self.market_data_gateway is None:
            return None

        try:
            end_date = date.today().strftime("%Y%m%d")
            start_date = (date.today() - pd.Timedelta(days=max(days * 2, 120))).strftime("%Y%m%d")

            self.market_data_gateway.download_history_data(
                stock_code,
                "1d",
                start_date,
                end_date,
            )
            data = self.market_data_gateway.fetch_local_data(
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
        """Reads configured intraday bars from local QMT cache."""
        if self.market_data_gateway is None:
            return None

        if self._uses_tick_source():
            tick_df = self._fetch_tick_data_from_local_cache(stock_code, trade_date)
            if tick_df is not None and not tick_df.empty:
                return self._aggregate_intraday_bars(tick_df, source="tick")

            logger.warning(
                "本地tick缓存不可用，回退到1分钟K线: stock=%s period=%s",
                stock_code,
                self.intraday_period,
            )

        trade_date_str = trade_date.strftime("%Y%m%d")

        try:
            self.market_data_gateway.download_history_data(
                stock_code,
                "1m",
                trade_date_str,
                trade_date_str,
            )
            data = self.market_data_gateway.fetch_local_data(
                stock_list=[stock_code],
                period="1m",
                start_time=trade_date_str,
                end_time=trade_date_str,
            )
            df = self._normalize_market_data(data, stock_code)
            df = self._filter_minute_data_for_trade_date(df, trade_date)
            return self._aggregate_intraday_bars(df, source="minute")
        except Exception as e:
            logger.warning(f"本地缓存分钟数据回退失败: {e}")
            return None

    def _fetch_tick_data_from_local_cache(
        self, stock_code: str, trade_date: date
    ) -> Optional[pd.DataFrame]:
        """Reads tick data from local cache when available."""
        trade_date_str = trade_date.strftime("%Y%m%d")

        try:
            self.market_data_gateway.download_history_data(
                stock_code,
                "tick",
                trade_date_str,
                trade_date_str,
            )
            data = self.market_data_gateway.fetch_local_data(
                stock_list=[stock_code],
                period="tick",
                start_time=trade_date_str,
                end_time=trade_date_str,
            )
        except Exception as exc:
            logger.warning(f"本地tick缓存回退失败: {exc}")
            return None

        df = self._normalize_market_data(data, stock_code)
        return self._filter_minute_data_for_trade_date(df, trade_date)

    def _normalize_market_data(self, data, stock_code: str) -> pd.DataFrame:
        """Normalizes xtdata results into a time-indexed DataFrame."""
        if isinstance(data, pd.DataFrame):
            return self._finalize_market_dataframe(data)

        if not isinstance(data, dict):
            raise ValueError(f"未知的数据格式: {type(data)}")

        if stock_code in data:
            stock_data = data[stock_code]
            if isinstance(stock_data, pd.DataFrame):
                return self._finalize_market_dataframe(stock_data)
            if isinstance(stock_data, dict):
                return self._normalize_market_record_dict(stock_data)
            if self._is_structured_market_array(stock_data):
                return self._normalize_market_structured_array(stock_data)

        normalized_fields = {}
        for field_name, field_value in data.items():
            if not isinstance(field_value, pd.DataFrame):
                continue
            # columns 为空时说明该字段无数据，跳过
            if field_value.columns.empty:
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
            # 所有字段 DataFrame 的 columns 均为空，说明 xtdata 返回了空结构（本地无缓存）
            # 返回空 DataFrame，让上层走 download 回退逻辑
            all_empty_columns = all(
                isinstance(v, pd.DataFrame) and v.columns.empty
                for v in data.values()
            )
            if all_empty_columns:
                logger.warning(
                    "xtdata返回空结构(无本地缓存), keys={}", list(data.keys())[:5]
                )
                return pd.DataFrame()

            inner_type = type(data.get(stock_code)).__name__ if stock_code in data else "missing"
            keys_sample = list(data.keys())[:5]
            logger.error(
                "无法识别xtdata返回结构, keys={}, stock_value_type={}", keys_sample, inner_type
            )
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

    def _normalize_market_record_dict(self, record: dict) -> pd.DataFrame:
        """Normalizes stock-code keyed dict payloads from xtdata."""
        if not record:
            return pd.DataFrame()

        list_like_lengths = []
        for value in record.values():
            if isinstance(value, (str, bytes, dict)):
                continue
            if pd.api.types.is_list_like(value):
                try:
                    list_like_lengths.append(len(value))
                except TypeError:
                    continue

        if any(length > 1 for length in list_like_lengths):
            df = pd.DataFrame(record)
        else:
            df = pd.DataFrame([record])
        return self._finalize_market_dataframe(df)

    def _normalize_market_structured_array(self, values: np.ndarray) -> pd.DataFrame:
        """Normalizes xtdata structured arrays returned by tick queries."""
        if values is None or len(values) == 0:
            return pd.DataFrame()

        df = pd.DataFrame.from_records(values, columns=values.dtype.names)
        return self._finalize_market_dataframe(df)

    def _is_structured_market_array(self, values) -> bool:
        """Checks whether a value is a numpy structured array."""
        return isinstance(values, np.ndarray) and values.dtype.names is not None

    def _finalize_market_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizes index, field aliases, and numeric columns."""
        if df is None or df.empty:
            return df

        normalized = df.copy()

        if "time" in normalized.columns:
            time_values = normalized.pop("time")
            normalized.index = self._convert_market_timestamp(time_values)
        elif not isinstance(normalized.index, pd.DatetimeIndex):
            normalized.index = self._convert_market_timestamp(normalized.index)

        alias_map = {
            "lastPrice": "close",
            "price": "close",
            "turnover": "amount",
            "preClose": "pre_close",
            "lastClose": "pre_close",
            "openInt": "openInterest",
        }
        for source, target in alias_map.items():
            if source in normalized.columns and target not in normalized.columns:
                normalized = normalized.rename(columns={source: target})

        normalized.index.name = "datetime"
        normalized = normalized.sort_index()

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "pre_close",
            "settelementPrice",
            "openInterest",
        ]
        for column in numeric_columns:
            if column in normalized.columns:
                normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

        return normalized

    def _convert_market_timestamp(self, values) -> pd.DatetimeIndex:
        """Converts QMT timestamps to naive Asia/Shanghai datetimes."""
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
        """Keeps only rows that belong to one trade date."""
        if df is None or df.empty:
            return df

        filtered = df[df.index.date == trade_date].copy()
        if filtered.empty:
            logger.warning(
                f"分钟数据交易日不匹配: 期望={trade_date}, 实际范围={df.index.min()} ~ {df.index.max()}"
            )
            return None

        return filtered

    def _warn_if_minute_data_is_stale(
        self, df: pd.DataFrame, stock_code: str, trade_date: date, snapshot: Optional[dict] = None, max_lag_minutes: int = 10
    ) -> None:
        """Warns if the latest intraday bar lags the latest tick snapshot too much."""
        if df is None or df.empty or trade_date != date.today():
            return

        snapshot_time = snapshot.get("time") if snapshot else None
        if not snapshot_time:
            return

        try:
            snapshot_dt = pd.Timestamp(snapshot_time)
        except Exception:
            return

        latest_bar_time = pd.Timestamp(df.index.max())
        lag_minutes = (snapshot_dt - latest_bar_time).total_seconds() / 60
        if lag_minutes > max_lag_minutes:
            logger.warning(
                "分钟数据明显滞后: stock={} latest_bar={} snapshot_time={} lag={:.1f}min",
                stock_code,
                latest_bar_time,
                snapshot_dt,
                lag_minutes,
            )

    def _refresh_ticks_from_fallbacks(
        self, stock_code: str, trade_date: date, cached_df: Optional[pd.DataFrame]
    ) -> Optional[pd.DataFrame]:
        """Refresh tick rows from local cache and the latest snapshot when live pulls stall."""
        candidate = cached_df.copy() if cached_df is not None and not cached_df.empty else None

        local_df = self._fetch_tick_data_from_local_cache(stock_code, trade_date)
        if local_df is not None and not local_df.empty:
            if candidate is None or candidate.empty:
                candidate = local_df
            else:
                candidate = pd.concat([candidate, local_df]).sort_index()
                candidate = candidate[~candidate.index.duplicated(keep="last")]

        candidate = self._append_snapshot_tick(candidate, stock_code, trade_date)
        if candidate is not None and not candidate.empty:
            self.tick_cache.save_ticks(stock_code, trade_date, candidate)
        return candidate

    def _append_snapshot_tick(
        self, df: Optional[pd.DataFrame], stock_code: str, trade_date: date,
        snapshot: Optional[dict] = None,
    ) -> Optional[pd.DataFrame]:
        """Append one synthetic tick row from the latest full-tick snapshot when available."""
        snapshot = snapshot or self.fetch_realtime_snapshot(stock_code)
        if not snapshot:
            return df

        snapshot_time = snapshot.get("time")
        if not snapshot_time:
            return df

        try:
            snapshot_dt = pd.Timestamp(snapshot_time)
        except Exception:
            return df

        if snapshot_dt.date() != trade_date:
            return df

        row = {
            "close": snapshot.get("price"),
            "open": snapshot.get("open"),
            "high": snapshot.get("high"),
            "low": snapshot.get("low"),
            "amount": snapshot.get("amount"),
            "volume": snapshot.get("volume"),
            "pre_close": snapshot.get("pre_close"),
        }
        if row["close"] is None:
            return df

        snapshot_df = pd.DataFrame([row], index=pd.DatetimeIndex([snapshot_dt], name="datetime"))
        if df is None or df.empty:
            return self._finalize_market_dataframe(snapshot_df)

        combined = pd.concat([df, snapshot_df]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
        return self._finalize_market_dataframe(combined)

    def _get_min_required_minute_rows(
        self, trade_date: date, bar_seconds: Optional[int] = None
    ) -> int:
        """Calculates the minimum number of rows expected for the configured bar period."""
        effective_bar_seconds = max(int(bar_seconds or self.intraday_period_seconds), 1)
        if trade_date != date.today():
            return self._bars_for_seconds(30 * 60, bar_seconds=effective_bar_seconds)

        current_time = datetime.now().time()
        first_signal_time = min(
            datetime.strptime(settings.t0_positive_sell_start_time, "%H:%M").time(),
            datetime.strptime(settings.t0_reverse_buy_start_time, "%H:%M").time(),
        )
        if current_time < first_signal_time:
            return 1

        market_open_time = datetime.strptime("09:30", "%H:%M").time()
        elapsed_seconds = int(
            (
                datetime.combine(trade_date, first_signal_time)
                - datetime.combine(trade_date, market_open_time)
            ).total_seconds()
        )
        return max(self._bars_for_seconds(elapsed_seconds, bar_seconds=effective_bar_seconds), 1)

    def _validate_minute_data(self, df: pd.DataFrame, trade_date: date) -> tuple[bool, str]:
        """Validates intraday bar completeness."""
        if df is None or df.empty:
            return False, "数据为空"

        required = ["open", "high", "low", "close", "volume"]
        missing = [field for field in required if field not in df.columns]
        if missing:
            return False, f"缺少字段: {missing}"

        if any(index_date != trade_date for index_date in df.index.date):
            return False, f"存在非目标交易日数据: {trade_date}"

        min_required_rows = self._get_min_required_minute_rows(
            trade_date,
            bar_seconds=self._infer_bar_seconds(df),
        )
        if len(df) < min_required_rows:
            return False, f"数据点不足: {len(df)} < {min_required_rows}"

        return True, "OK"

    def _load_cached_minute_data(self, stock_code: str, trade_date: date) -> Optional[pd.DataFrame]:
        """Loads previously cached parquet intraday data when present."""
        cache_file = self.cache_dir / "minute_data" / f"{stock_code}_{trade_date}.parquet"
        if cache_file.exists():
            try:
                df = pd.read_parquet(cache_file)
                if (
                    datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                ).seconds < 300:
                    return df
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}")
        return None

    def _aggregate_intraday_bars(
        self, df: Optional[pd.DataFrame], *, source: str
    ) -> Optional[pd.DataFrame]:
        """Converts raw minute/tick data into the configured bar period."""
        if df is None or df.empty:
            return df

        if self.intraday_period_seconds == 60:
            return df.copy()

        if self._uses_tick_source():
            if source != "tick":
                return df.copy()
            return self._aggregate_tick_data(df)

        return self._resample_ohlcv(df, self._period_to_rule(self.intraday_period))

    def _aggregate_tick_data(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Aggregates tick rows into OHLCV bars."""
        if df is None or df.empty:
            return df

        working = df.copy().sort_index()
        if "close" not in working.columns:
            return None

        if "volume" not in working.columns:
            working["volume"] = 0.0
        if "amount" not in working.columns:
            working["amount"] = working["close"] * working["volume"]

        working["trade_volume"] = self._normalize_tick_accumulator(working["volume"])
        working["trade_amount"] = self._normalize_tick_accumulator(working["amount"])

        aggregated = working.resample(
            self._period_to_rule(self.intraday_period),
            label="right",
            closed="right",
        ).agg(
            open=("close", "first"),
            high=("close", "max"),
            low=("close", "min"),
            close=("close", "last"),
            volume=("trade_volume", "sum"),
            amount=("trade_amount", "sum"),
        )
        aggregated = aggregated.dropna(subset=["close"])

        if "pre_close" in working.columns:
            pre_close = (
                working["pre_close"]
                .ffill()
                .resample(
                    self._period_to_rule(self.intraday_period),
                    label="right",
                    closed="right",
                )
                .last()
            )
            aggregated["pre_close"] = pre_close.reindex(aggregated.index)

        return aggregated

    def _resample_ohlcv(self, df: pd.DataFrame, rule: str) -> Optional[pd.DataFrame]:
        """Resamples bar data to a slower bar frequency."""
        if df is None or df.empty:
            return df

        aggregations = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
        if "amount" in df.columns:
            aggregations["amount"] = "sum"
        if "pre_close" in df.columns:
            aggregations["pre_close"] = "last"

        aggregated = df.resample(rule, label="right", closed="right").agg(aggregations)
        return aggregated.dropna(subset=["close"])

    def _normalize_tick_accumulator(self, series: pd.Series) -> pd.Series:
        """Turns cumulative tick fields into per-tick deltas when needed."""
        numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
        diffs = numeric.diff()
        if not diffs.dropna().empty and (diffs.dropna() >= 0).all():
            per_tick = diffs.clip(lower=0.0)
            per_tick.iloc[0] = max(float(numeric.iloc[0]), 0.0)
            return per_tick
        return numeric.clip(lower=0.0)

    def _normalize_intraday_period(self, value: str) -> str:
        period = str(value or "1m").strip().lower()
        match = self._PERIOD_RE.match(period)
        if not match:
            raise ValueError(f"Unsupported intraday period: {value}")
        if int(match.group("value")) <= 0:
            raise ValueError(f"Unsupported intraday period: {value}")
        return period

    def _period_to_seconds(self, value: str) -> int:
        match = self._PERIOD_RE.match(value)
        if not match:
            raise ValueError(f"Unsupported intraday period: {value}")

        amount = int(match.group("value"))
        unit = match.group("unit").lower()
        return amount if unit == "s" else amount * 60

    def _period_to_rule(self, value: str) -> str:
        match = self._PERIOD_RE.match(value)
        if not match:
            raise ValueError(f"Unsupported intraday period: {value}")

        amount = int(match.group("value"))
        unit = match.group("unit").lower()
        return f"{amount}{'s' if unit == 's' else 'min'}"

    def _uses_tick_source(self) -> bool:
        return self.intraday_period_seconds < 60

    def _bars_for_seconds(self, elapsed_seconds: int, bar_seconds: Optional[int] = None) -> int:
        effective_bar_seconds = max(int(bar_seconds or self.intraday_period_seconds), 1)
        return max(
            (max(int(elapsed_seconds), 0) + effective_bar_seconds - 1) // effective_bar_seconds,
            1,
        )

    def _infer_bar_seconds(self, df: pd.DataFrame) -> int:
        if df is None or len(df.index) < 2:
            return self.intraday_period_seconds

        deltas = df.index.to_series().diff().dropna().dt.total_seconds()
        if deltas.empty:
            return self.intraday_period_seconds

        positive_deltas = deltas[deltas > 0]
        if positive_deltas.empty:
            return self.intraday_period_seconds

        return max(int(positive_deltas.median()), 1)

    def _estimate_recent_minute_count(self) -> int:
        # 240 trading minutes plus a small buffer for stale cross-day rows.
        return 260

    def _estimate_recent_tick_count(self) -> int:
        # Active symbols can produce many ticks; use a generous window for one session.
        return 20000
