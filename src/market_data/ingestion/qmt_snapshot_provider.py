"""QMT snapshot provider — polls xtdata.get_full_tick on a timer."""
from __future__ import annotations

import threading
from typing import Any

from src.strategy.strategies.t0.contracts.market_data import MarketDataCallback, MarketSnapshot


class QMTSnapshotProvider:
    def __init__(self, xtdata_client: Any) -> None:
        self._xtdata = xtdata_client
        self._callbacks: list[MarketDataCallback] = []
        self._stock_codes: list[str] = []
        self._latest: dict[str, MarketSnapshot] = {}
        self._lock = threading.RLock()

    def subscribe_tick(self, stock_codes: list[str], callback: MarketDataCallback) -> None:
        return None

    def subscribe_snapshot(
        self,
        stock_codes: list[str],
        interval_seconds: int,
        callback: MarketDataCallback,
    ) -> None:
        with self._lock:
            self._stock_codes = sorted(set(stock_codes))
            self._callbacks.append(callback)

    def _poll_once(self) -> None:
        if not self._stock_codes:
            return
        payload = self._xtdata.get_full_tick(self._stock_codes)
        if not isinstance(payload, dict):
            return
        with self._lock:
            for stock_code in self._stock_codes:
                row = payload.get(stock_code)
                if not isinstance(row, dict):
                    continue
                snapshot = MarketSnapshot(
                    stock_code=stock_code,
                    time=str(row.get("time") or row.get("timetag") or ""),
                    price=row.get("lastPrice") or row.get("price"),
                    high=row.get("high"),
                    low=row.get("low"),
                    open=row.get("open"),
                    amount=row.get("amount"),
                    volume=row.get("volume"),
                    pre_close=row.get("lastClose") or row.get("lastSettlementPrice"),
                    source="qmt_snapshot",
                )
                self._latest[stock_code] = snapshot
                for cb in self._callbacks:
                    cb(snapshot)

    def get_latest_snapshot(self, stock_code: str) -> MarketSnapshot | None:
        with self._lock:
            return self._latest.get(stock_code)

    def get_minute_bars(self, stock_code: str, count: int) -> list[dict]:
        return []

    def close(self) -> None:
        with self._lock:
            self._callbacks.clear()
            self._stock_codes.clear()
