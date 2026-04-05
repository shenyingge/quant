"""Unit tests for QMT tick and snapshot providers (Phase 3 Task 2)."""
from __future__ import annotations

import threading

from src.market_data.ingestion.qmt_snapshot_provider import QMTSnapshotProvider
from src.market_data.ingestion.qmt_tick_provider import QMTTickProvider


class FakeXtData:
    def __init__(self):
        self.subscriptions = {}
        self.unsubscribed = []

    def subscribe_quote(self, stock_code, period="tick", count=0, callback=None):
        seq = len(self.subscriptions) + 1
        self.subscriptions[seq] = {
            "stock_code": stock_code,
            "period": period,
            "callback": callback,
        }
        return seq

    def unsubscribe_quote(self, seq):
        self.unsubscribed.append(seq)

    def get_full_tick(self, stock_codes):
        return {
            stock_codes[0]: {
                "time": 1712280603000,
                "lastPrice": 10.25,
                "high": 10.30,
                "low": 10.10,
                "open": 10.15,
                "amount": 120000.0,
                "volume": 3500.0,
                "lastClose": 10.00,
            }
        }


def test_qmt_tick_provider_subscribe_and_unsubscribe(monkeypatch):
    fake = FakeXtData()
    provider = QMTTickProvider(xtdata_client=fake)
    received = []

    provider.subscribe_tick(["601138.SH"], lambda snap: received.append(snap))

    seq = list(fake.subscriptions.keys())[0]
    callback = fake.subscriptions[seq]["callback"]
    callback({"601138.SH": [{"time": 1712280603000, "lastPrice": 10.25}]})

    provider.close()

    assert received
    assert fake.unsubscribed == [seq]


def test_qmt_snapshot_provider_poll_once_updates_cache(monkeypatch):
    fake = FakeXtData()
    provider = QMTSnapshotProvider(xtdata_client=fake)

    barrier = threading.Event()

    def _on_snapshot(snapshot):
        if snapshot.stock_code == "601138.SH":
            barrier.set()

    provider.subscribe_snapshot(["601138.SH"], interval_seconds=1, callback=_on_snapshot)
    provider._poll_once()
    latest = provider.get_latest_snapshot("601138.SH")
    provider.close()

    assert latest is not None
    assert latest.price == 10.25
    assert barrier.is_set()
