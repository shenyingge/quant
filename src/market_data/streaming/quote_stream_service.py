"""Bridge frontend quote subscriptions to QMT quote callbacks and Redis."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import redis

from src.infrastructure.config import settings
from src.infrastructure.logger_config import configured_logger as logger
from src.infrastructure.redis.connection import build_redis_client_kwargs

try:
    from xtquant import xtdata
except Exception:  # pragma: no cover - depends on local QMT runtime
    xtdata = None


def normalize_stock_code(stock_code: Optional[str]) -> str:
    return str(stock_code or "").strip().upper()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass
    return str(value)


class QuoteStreamService:
    """Maintain QMT quote subscriptions based on Redis-managed frontend demand."""

    def __init__(self) -> None:
        self.redis_client = redis.Redis(
            **build_redis_client_kwargs(
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        )
        self.running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._pubsub = None
        self._subscription_seq_by_stock: Dict[str, int] = {}
        self._subscription_callback_by_stock: Dict[str, Callable[[Any], None]] = {}

    def start(self) -> bool:
        if self.running:
            return True

        if not settings.quote_stream_enabled:
            logger.info("Quote stream service is disabled by configuration")
            return False

        if xtdata is None:
            logger.warning("xtdata is unavailable, quote stream service will not start")
            return False

        try:
            self.redis_client.ping()
        except Exception as exc:
            logger.error(f"Quote stream service cannot connect to Redis: {exc}")
            return False

        self._pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(settings.redis_quote_control_channel)
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(
            target=self._run,
            name="quote-stream-service",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Quote stream service started | channel={} | subscriptions_key={} | period={}",
            settings.redis_quote_stream_channel,
            settings.redis_quote_subscriptions_key,
            settings.quote_stream_period,
        )
        self._reconcile_subscriptions()
        return True

    def stop(self) -> None:
        if not self.running:
            return

        self.running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

        if self._pubsub is not None:
            try:
                self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

        with self._lock:
            for stock_code in list(self._subscription_seq_by_stock.keys()):
                self._unsubscribe_stock(stock_code)

        logger.info("Quote stream service stopped")

    def _run(self) -> None:
        reconcile_interval = max(int(settings.quote_stream_reconcile_interval_seconds), 1)
        next_reconcile_at = 0.0

        while not self._stop_event.is_set():
            try:
                if self._pubsub is not None:
                    message = self._pubsub.get_message(timeout=1)
                    if message is not None:
                        self._reconcile_subscriptions()
            except Exception as exc:
                logger.warning(f"Quote subscription control loop failed: {exc}")
                time.sleep(1)

            now = time.monotonic()
            if now >= next_reconcile_at:
                self._reconcile_subscriptions()
                next_reconcile_at = now + reconcile_interval

    def _reconcile_subscriptions(self) -> None:
        desired = self._load_desired_stock_codes()

        with self._lock:
            current = set(self._subscription_seq_by_stock)

            for stock_code in sorted(desired - current):
                self._subscribe_stock(stock_code)

            for stock_code in sorted(current - desired):
                self._unsubscribe_stock(stock_code)

    def _load_desired_stock_codes(self) -> set[str]:
        try:
            return {
                normalized
                for normalized in (
                    normalize_stock_code(stock_code)
                    for stock_code in self.redis_client.smembers(
                        settings.redis_quote_subscriptions_key
                    )
                )
                if normalized
            }
        except Exception as exc:
            logger.warning(f"Failed to load desired quote subscriptions from Redis: {exc}")
            return set()

    def _subscribe_stock(self, stock_code: str) -> None:
        if not stock_code:
            return

        callback = self._build_callback(stock_code)
        try:
            seq = xtdata.subscribe_quote(
                stock_code,
                period=settings.quote_stream_period,
                count=0,
                callback=callback,
            )
        except Exception as exc:
            logger.warning(f"Failed to subscribe QMT quote for {stock_code}: {exc}")
            return

        if seq is None or (isinstance(seq, int) and seq < 0):
            logger.warning(f"QMT quote subscription rejected for {stock_code}: seq={seq}")
            return

        self._subscription_seq_by_stock[stock_code] = int(seq)
        self._subscription_callback_by_stock[stock_code] = callback
        logger.info("Subscribed QMT quote stream for {} with seq={}", stock_code, seq)

    def _unsubscribe_stock(self, stock_code: str) -> None:
        seq = self._subscription_seq_by_stock.pop(stock_code, None)
        self._subscription_callback_by_stock.pop(stock_code, None)
        if seq is None:
            return

        try:
            if hasattr(xtdata, "unsubscribe_quote"):
                xtdata.unsubscribe_quote(seq)
        except Exception as exc:
            logger.warning(f"Failed to unsubscribe QMT quote for {stock_code}: {exc}")
        else:
            logger.info("Unsubscribed QMT quote stream for {} with seq={}", stock_code, seq)

    def _build_callback(self, stock_code: str) -> Callable[[Any], None]:
        def _on_quote(datas: Any) -> None:
            try:
                payload = self._normalize_quote_payload(stock_code, datas)
                if payload is None:
                    return
                payload_json = json.dumps(payload, ensure_ascii=False)
                self.redis_client.publish(settings.redis_quote_stream_channel, payload_json)
                latest_quote_key = f"{settings.redis_quote_latest_prefix}{stock_code}"
                latest_quote_ttl = int(settings.redis_quote_latest_ttl_seconds)
                if latest_quote_ttl > 0:
                    self.redis_client.setex(latest_quote_key, latest_quote_ttl, payload_json)
                else:
                    self.redis_client.set(latest_quote_key, payload_json)
            except Exception as exc:
                logger.warning(f"Failed to publish QMT quote for {stock_code}: {exc}")

        return _on_quote

    def _normalize_quote_payload(self, stock_code: str, datas: Any) -> Optional[Dict[str, Any]]:
        raw_payload = datas
        if isinstance(datas, dict):
            raw_payload = datas.get(stock_code, datas)

        raw_payload = _json_safe(raw_payload)
        if isinstance(raw_payload, list):
            if not raw_payload:
                return None
            raw_payload = raw_payload[-1]

        payload: Dict[str, Any] = {
            "stock_code": stock_code,
            "source": "qmt",
            "period": settings.quote_stream_period,
            "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "quote": raw_payload,
        }

        if isinstance(raw_payload, dict):
            payload["quote_time"] = (
                raw_payload.get("time")
                or raw_payload.get("timestamp")
                or raw_payload.get("trade_time")
            )
            payload["last_price"] = (
                raw_payload.get("lastPrice")
                or raw_payload.get("last_price")
                or raw_payload.get("price")
                or raw_payload.get("last")
            )
            payload["volume"] = raw_payload.get("volume") or raw_payload.get("vol")

        return payload
