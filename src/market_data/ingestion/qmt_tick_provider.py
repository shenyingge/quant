"""QMT tick provider — wraps xtdata.subscribe_quote."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.infrastructure.logger_config import logger
from src.strategy.t0.contracts.market_data import MarketDataCallback, MarketSnapshot


class QMTTickProvider:
    def __init__(self, xtdata_client: Any) -> None:
        self._xtdata = xtdata_client
        self._seq_by_symbol: dict[str, int] = {}

    def subscribe_tick(self, stock_codes: list[str], callback: MarketDataCallback) -> None:
        for stock_code in stock_codes:
            seq = self._xtdata.subscribe_quote(
                stock_code,
                period="tick",
                count=0,
                callback=self._wrap_callback(stock_code, callback),
            )
            if seq is not None and int(seq) >= 0:
                self._seq_by_symbol[stock_code] = int(seq)

    def subscribe_snapshot(
        self,
        stock_codes: list[str],
        interval_seconds: int,
        callback: MarketDataCallback,
    ) -> None:
        return None

    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None:
        return None

    def get_minute_bars(self, stock_code: str, count: int) -> list[dict]:
        return []

    def _wrap_callback(
        self, stock_code: str, callback: MarketDataCallback
    ) -> Callable[[Any], None]:
        def _inner(payload: Any) -> None:
            quote: Any = payload.get(stock_code) if isinstance(payload, dict) else payload
            if isinstance(quote, list) and quote:
                quote = quote[-1]
            if not isinstance(quote, dict):
                return
            callback(
                MarketSnapshot(
                    stock_code=stock_code,
                    time=str(quote.get("time") or quote.get("timetag") or ""),
                    price=quote.get("lastPrice") or quote.get("price"),
                    high=quote.get("high"),
                    low=quote.get("low"),
                    open=quote.get("open"),
                    amount=quote.get("amount"),
                    volume=quote.get("volume"),
                    pre_close=quote.get("lastClose") or quote.get("pre_close"),
                    source="qmt_tick",
                )
            )

        return _inner

    def close(self) -> None:
        for seq in list(self._seq_by_symbol.values()):
            try:
                self._xtdata.unsubscribe_quote(seq)
            except Exception as exc:
                logger.warning("Failed to unsubscribe tick seq=%s: %s", seq, exc)
        self._seq_by_symbol.clear()
