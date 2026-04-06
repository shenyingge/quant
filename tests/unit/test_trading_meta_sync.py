from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy import MetaData

from src.infrastructure.db import Base
from src.infrastructure.sync.trading_meta_sync import _read_source_rows, sync_sqlite_to_meta_db


def test_read_source_rows_collects_trading_tables(monkeypatch, tmp_path):
    db_path = tmp_path / "sync_source.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url)

    try:
        sqlite_metadata = MetaData()
        for table in Base.metadata.tables.values():
            table.to_metadata(sqlite_metadata, schema=None)

        sqlite_metadata.create_all(bind=engine)
        with engine.begin() as connection:
            connection.execute(
                sqlite_metadata.tables["trading_signals"].insert(),
                [
                    {
                        "id": 1,
                        "signal_id": "SIG-1",
                        "stock_code": "601138.SH",
                        "direction": "BUY",
                        "volume": 100,
                        "price": 10.5,
                        "signal_time": datetime(2026, 3, 29, 9, 35, 0),
                        "processed": False,
                        "error_message": None,
                        "created_at": datetime(2026, 3, 29, 9, 35, 1),
                    }
                ],
            )
            connection.execute(
                sqlite_metadata.tables["trading_calendar"].insert(),
                [
                    {
                        "id": 1,
                        "date": date(2026, 3, 29),
                        "is_trading": False,
                        "year": 2026,
                        "market": "SSE",
                        "created_at": datetime(2026, 3, 29, 0, 0, 0),
                        "updated_at": datetime(2026, 3, 29, 0, 0, 0),
                    }
                ],
            )

        monkeypatch.setattr("src.infrastructure.sync.trading_meta_sync._resolve_source_db_url", lambda: db_url)
        rows_by_table = _read_source_rows()
    finally:
        engine.dispose()

    assert rows_by_table["trading_signals"][0]["signal_id"] == "SIG-1"
    assert rows_by_table["trading_calendar"][0]["year"] == 2026
    assert rows_by_table["order_records"] == []


def test_sync_sqlite_to_meta_db_returns_sync_summary(monkeypatch):
    source_rows = {
        "trading_calendar": [{"id": 1}],
        "stock_info": [],
        "trading_signals": [{"id": 2}],
        "order_records": [{"id": 3}, {"id": 4}],
        "strategy_regime_state": [],
        "strategy_signal_history": [{"id": 5}],
    }

    monkeypatch.setattr("src.infrastructure.sync.trading_meta_sync._read_source_rows", lambda: source_rows)

    async def fake_sync(rows_by_table):
        from src.infrastructure.sync.trading_meta_sync import TradingMetaSyncResult

        assert rows_by_table == source_rows
        return TradingMetaSyncResult(
            schema="trading",
            source_db_url="sqlite:///./trading.db",
            target_db_url="postgresql+asyncpg://user:pass@host/db",
            table_row_counts={name: len(rows) for name, rows in rows_by_table.items()},
        )

    monkeypatch.setattr("src.infrastructure.sync.trading_meta_sync._sync_rows_to_meta_db", fake_sync)

    result = sync_sqlite_to_meta_db()

    assert result.schema == "trading"
    assert result.total_rows == 5
    assert result.table_row_counts["order_records"] == 2
