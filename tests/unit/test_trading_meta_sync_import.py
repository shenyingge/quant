import pytest


@pytest.mark.unit
def test_trading_meta_sync_import_available():
    from src.infrastructure.trading_meta_sync import sync_sqlite_to_meta_db

    assert callable(sync_sqlite_to_meta_db)
