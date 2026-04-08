from sqlalchemy.engine import make_url

import src.infrastructure.db.meta_db as meta_db


def test_get_meta_db_url_uses_configured_connection(monkeypatch):
    monkeypatch.setattr(meta_db.settings, "meta_db_type", "postgresql+asyncpg")
    monkeypatch.setattr(meta_db.settings, "meta_db_host", "localhost")
    monkeypatch.setattr(meta_db.settings, "meta_db_port", 15432)
    monkeypatch.setattr(meta_db.settings, "meta_db_name", "qsync")
    monkeypatch.setattr(meta_db.settings, "meta_db_user", "qsync")
    monkeypatch.setattr(meta_db.settings, "meta_db_password", "secret")

    url = make_url(meta_db.get_meta_db_url())

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "localhost"
    assert url.port == 15432
    assert url.database == "qsync"
    assert url.username == "qsync"
    assert url.password == "secret"


def test_build_meta_db_trading_metadata_uses_trading_schema(monkeypatch):
    monkeypatch.setattr(meta_db.settings, "meta_db_trading_schema", "trading")

    metadata = meta_db.build_meta_db_trading_metadata()

    assert set(metadata.tables) == {
        "trading.trading_signals",
        "trading.order_records",
        "trading.trade_executions",
        "trading.order_cancellations",
        "trading.trading_calendar",
        "trading.stock_info",
        "trading.account_positions",
    }
    assert "trading.service_logs" not in metadata.tables


def test_validate_meta_db_config_raises_for_missing_required_fields(monkeypatch):
    monkeypatch.setattr(meta_db.settings, "meta_db_host", "")
    monkeypatch.setattr(meta_db.settings, "meta_db_name", "")
    monkeypatch.setattr(meta_db.settings, "meta_db_user", "qsync")
    monkeypatch.setattr(meta_db.settings, "meta_db_password", "")

    try:
        meta_db.validate_meta_db_config()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("validate_meta_db_config should raise when config is incomplete")

    assert "META_DB_HOST" in message
    assert "META_DB_NAME" in message
    assert "META_DB_PASSWORD" in message
