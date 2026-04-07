"""Redis tick data cache shared by strategy market-data utilities."""

import io
from datetime import date, datetime
from typing import Optional

import pandas as pd
import redis

from src.infrastructure.config import settings
from src.infrastructure.logger_config import logger
from src.infrastructure.redis.connection import build_redis_client_kwargs


class RedisTickCache:
    """Redis tick data cache using a dedicated DB."""

    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                **build_redis_client_kwargs(
                    db=settings.redis_tick_cache_db,
                    decode_responses=False,
                    socket_connect_timeout=3,
                    socket_timeout=3,
                )
            )
            self.redis_client.ping()
            self.enabled = True
            logger.info(f"Redis tick缓存已连接: db={settings.redis_tick_cache_db}")
        except Exception as e:
            logger.warning(f"Redis tick缓存连接失败，将降级到全量拉取: {e}")
            self.redis_client = None
            self.enabled = False

    def get_cached_ticks(self, stock_code: str, trade_date: date) -> Optional[pd.DataFrame]:
        """Load cached ticks for one symbol and trade date."""
        if not self.enabled:
            return None

        key = self._make_key(stock_code, trade_date)
        try:
            data = self.redis_client.get(key)
            if data:
                df = pd.read_parquet(io.BytesIO(data))
                logger.debug(f"从Redis加载tick缓存: {key}, rows={len(df)}")
                return df
        except Exception as e:
            logger.warning(f"读取tick缓存失败: {e}")
        return None

    def save_ticks(self, stock_code: str, trade_date: date, df: pd.DataFrame) -> None:
        """Persist ticks and last-tick metadata into Redis."""
        if not self.enabled or df is None or df.empty:
            return

        key = self._make_key(stock_code, trade_date)
        meta_key = self._make_meta_key(stock_code, trade_date)
        try:
            buf = io.BytesIO()
            df.to_parquet(buf, index=True)
            data = buf.getvalue()
            self.redis_client.setex(key, settings.redis_tick_cache_ttl, data)

            last_time = df.index.max()
            self.redis_client.setex(
                meta_key,
                settings.redis_tick_cache_ttl,
                last_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
            )
            logger.debug(f"保存tick缓存: {key}, rows={len(df)}, last={last_time}")
        except Exception as e:
            logger.warning(f"保存tick缓存失败: {e}")

    def get_last_tick_time(self, stock_code: str, trade_date: date) -> Optional[datetime]:
        """Load the last cached tick timestamp."""
        if not self.enabled:
            return None

        meta_key = self._make_meta_key(stock_code, trade_date)
        try:
            data = self.redis_client.get(meta_key)
            if data:
                return pd.Timestamp(data.decode())
        except Exception as e:
            logger.warning(f"读取tick时间戳失败: {e}")
        return None

    def _make_key(self, stock_code: str, trade_date: date) -> str:
        return f"tick:{stock_code}:{trade_date.strftime('%Y%m%d')}"

    def _make_meta_key(self, stock_code: str, trade_date: date) -> str:
        return f"tick_meta:{stock_code}:{trade_date.strftime('%Y%m%d')}"
