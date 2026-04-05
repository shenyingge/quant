from src.trading.runtime.engine import TradingEngine


class DummyNotifier:
    def __init__(self):
        self.errors = []
        self.received = []

    def notify_error(self, error_message, context=""):
        self.errors.append((error_message, context))
        return True

    def notify_signal_received(self, signal_data):
        self.received.append(signal_data)
        return True


class DummyQuery:
    def __init__(self, result=None):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class DummySession:
    def __init__(self):
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def query(self, model):
        return DummyQuery(None)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


class DummyPositionSyncer:
    def __init__(self, version):
        self.version = version

    def get_position_version(self, stock_code=None):
        return self.version


def test_handle_trading_signal_rejects_stale_position_version(monkeypatch):
    engine = TradingEngine.__new__(TradingEngine)
    engine.notifier = DummyNotifier()
    session = DummySession()
    executed = []

    monkeypatch.setattr("src.trading.runtime.engine.SessionLocal", lambda: session)
    monkeypatch.setattr(
        "src.trading.runtime.engine.PositionSyncer",
        lambda: DummyPositionSyncer(version=5),
    )
    monkeypatch.setattr(
        TradingEngine,
        "_execute_trade_async",
        lambda self, signal_data, trading_signal: executed.append(signal_data),
    )

    signal_data = {
        "signal_id": "SIG-STALE-1",
        "stock_code": "601138.SH",
        "direction": "BUY",
        "volume": 100,
        "price": 52.3,
        "expected_position_version": 4,
    }

    engine._handle_trading_signal(signal_data)

    assert executed == []
    assert len(session.added) == 1
    assert session.added[0].processed is True
    assert "expected_position_version=4" in session.added[0].error_message
    assert engine.notifier.received == []
    assert engine.notifier.errors
