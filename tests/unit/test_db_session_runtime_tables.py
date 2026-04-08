from contextlib import contextmanager

import src.infrastructure.db.session as db_session


class _FakeConnection:
    def __init__(self):
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)


class _FakeMetadata:
    def __init__(self):
        self.called = False
        self.binds = []

    def create_all(self, bind):
        self.called = True
        self.binds.append(bind)


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        yield self.connection


def test_create_tables_uses_runtime_metadata_instead_of_full_base_metadata(monkeypatch):
    connection = _FakeConnection()
    runtime_metadata = _FakeMetadata()

    monkeypatch.setattr(db_session, "engine", _FakeEngine(connection))
    monkeypatch.setattr(
        db_session,
        "build_meta_db_trading_metadata",
        lambda schema=None: runtime_metadata,
        raising=False,
    )
    monkeypatch.setattr(
        db_session.Base.metadata,
        "create_all",
        lambda bind: (_ for _ in ()).throw(AssertionError("full Base.metadata should not be used")),
    )
    monkeypatch.setattr(
        "src.trading.costs.order_record_costs.ensure_order_record_cost_columns",
        lambda conn: None,
    )

    db_session.create_tables()

    assert runtime_metadata.called is True
    assert runtime_metadata.binds == [connection]
