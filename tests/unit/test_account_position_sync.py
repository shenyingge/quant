import sys
from types import SimpleNamespace

from src.trading import account_position_sync


def test_sync_account_positions_via_qmt_syncs_and_disconnects(monkeypatch):
    events = []

    class FakeTrader:
        def __init__(self, session_id):
            self.session_id = session_id

        def connect(self):
            events.append(("connect", self.session_id))
            return True

        def disconnect(self):
            events.append(("disconnect", self.session_id))

    def fake_sync(trader, *, source):
        events.append(("sync", trader.session_id, source))
        return 2

    monkeypatch.setattr(account_position_sync.settings, "qmt_session_id_trading_service", 24680)
    monkeypatch.setattr(account_position_sync, "sync_account_positions_from_qmt", fake_sync)
    monkeypatch.setitem(
        sys.modules,
        "src.trading.execution.qmt_trader",
        SimpleNamespace(QMTTrader=FakeTrader),
    )

    synced_rows = account_position_sync.sync_account_positions_via_qmt(source="manual_cli")

    assert synced_rows == 2
    assert events == [
        ("connect", 24680),
        ("sync", 24680, "manual_cli"),
        ("disconnect", 24680),
    ]


def test_sync_account_positions_via_qmt_returns_none_when_connect_fails(monkeypatch):
    events = []

    class FakeTrader:
        def __init__(self, session_id):
            self.session_id = session_id

        def connect(self):
            events.append(("connect", self.session_id))
            return False

        def disconnect(self):
            events.append(("disconnect", self.session_id))

    monkeypatch.setattr(account_position_sync.settings, "qmt_session_id_trading_service", None)
    monkeypatch.setattr(account_position_sync.settings, "qmt_session_id", 13579)
    monkeypatch.setitem(
        sys.modules,
        "src.trading.execution.qmt_trader",
        SimpleNamespace(QMTTrader=FakeTrader),
    )

    synced_rows = account_position_sync.sync_account_positions_via_qmt(source="manual_cli")

    assert synced_rows is None
    assert events == [("connect", 13579), ("disconnect", 13579)]
