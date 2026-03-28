import main

from src.config import settings


def test_sync_t0_position_retries_connect_until_success(monkeypatch):
    attempts = {"count": 0}
    notifications = []
    sync_calls = []
    sleeps = []

    class FakeNotifier:
        def notify_t0_position_sync(self, stock_code, success, detail=""):
            notifications.append((stock_code, success, detail))
            return True

    class FakeTrader:
        def __init__(self, session_id=None):
            self.session_id = session_id

        def connect(self):
            attempts["count"] += 1
            return attempts["count"] >= 3

        def disconnect(self):
            return None

    class FakeSyncer:
        def sync_from_qmt(self, trader, stock_code):
            sync_calls.append((trader.session_id, stock_code))
            return True

    monkeypatch.setattr(main, "_resolve_qmt_session_id", lambda mode: 12347)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(settings, "t0_sync_connect_retry_attempts", 3)
    monkeypatch.setattr(settings, "t0_sync_connect_retry_delay_seconds", 5)
    monkeypatch.setattr(settings, "t0_stock_code", "601138.SH")

    import src.notifications
    import src.strategy.position_syncer
    import src.trader

    monkeypatch.setattr(src.notifications, "FeishuNotifier", FakeNotifier)
    monkeypatch.setattr(src.strategy.position_syncer, "PositionSyncer", FakeSyncer)
    monkeypatch.setattr(src.trader, "QMTTrader", FakeTrader)

    main.sync_t0_position()

    assert attempts["count"] == 3
    assert sleeps == [5, 5]
    assert sync_calls == [(12347, "601138.SH")]
    assert notifications[-1] == ("601138.SH", True, "已从QMT成功同步仓位")
